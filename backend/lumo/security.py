"""Defensas de la app: encabezados de seguridad, tope de pedidos, comparaciones seguras y origen de los POST.

ISO 27001 A.8.9 / A.8.20 / A.8.26 · SOC 2 CC6.1, CC6.6, CC6.8.
"""
import secrets
import threading
import time
from collections import deque
from urllib.parse import urlsplit

# Las páginas de Lumo traen scripts y estilos propios dentro del HTML, por eso script-src y style-src llevan 'unsafe-inline'.
# Todo lo demás queda cerrado: nada de otros orígenes, ni frames, ni <base>, ni formularios hacia afuera.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # same-origin: las invitaciones viajan en la dirección y no se filtran a otros sitios por el Referer.
    # No usar no-referrer: con esa política los navegadores mandan "Origin: null" en los formularios
    # y el control de origen los rechaza a todos ("Pedido rechazado").
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
HSTS = "max-age=31536000; includeSubDomains"

# Páginas públicas que se pueden guardar en caché; todo lo demás (panel, admin, API, invitaciones) no se guarda nunca.
CACHEABLE = ("/", "/privacidad", "/.well-known/security.txt")


def apply_headers(resp, request_path: str, secure: bool):
    for k, v in HEADERS.items():
        resp.headers.setdefault(k, v)
    if secure:
        resp.headers.setdefault("Strict-Transport-Security", HSTS)
    if "Cache-Control" not in resp.headers and not request_path.startswith("/static/") and request_path not in CACHEABLE:
        resp.headers["Cache-Control"] = "no-store"
    return resp


def safe_eq(a, b) -> bool:
    """Comparación en tiempo constante que no falla con caracteres que no son ASCII."""
    return secrets.compare_digest(str(a or "").encode("utf-8"), str(b or "").encode("utf-8"))


def same_origin(origin: str, host: str) -> bool:
    """El Origin que mandan los navegadores en los POST tiene que ser el de esta misma app."""
    try:
        return urlsplit(origin).netloc.lower() == host.lower()
    except ValueError:
        return False


class RateLimiter:
    """Ventana deslizante en memoria. Cada proceso cuenta por separado: con 2 procesos el tope real es el doble."""

    MAX_KEYS = 20000

    def __init__(self, clock=time.monotonic):
        self._hits = {}
        self._lock = threading.Lock()
        self._clock = clock

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = self._clock()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) >= self.MAX_KEYS:
                    self._prune(now)
                q = self._hits[key] = deque()
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def _prune(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 3600]:
            del self._hits[k]
        if len(self._hits) >= self.MAX_KEYS:  # bajo ataque: se descarta lo más viejo
            for k in list(self._hits)[: self.MAX_KEYS // 2]:
                del self._hits[k]


# (prefijo de la ruta, solo POST, pedidos, segundos). El primero que coincide es el que se aplica.
LIMITS = (
    ("/cron/", False, 10, 60),
    ("/connect", False, 20, 300),
    ("/callback", False, 20, 300),
    ("/invitacion/", False, 20, 300),
    ("/admin", True, 60, 60),
    ("/api/avisos", True, 10, 60),
    ("/api/email", True, 10, 60),
    ("/api/cuenta", False, 10, 60),
    ("/cuenta", True, 10, 60),
    ("/api/", False, 120, 60),
)


def limit_for(path: str, method: str):
    for prefix, post_only, n, window in LIMITS:
        if path.startswith(prefix) and (not post_only or method == "POST"):
            return prefix, n, window
    return None
