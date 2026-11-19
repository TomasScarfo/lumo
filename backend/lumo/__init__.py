import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from itsdangerous import BadSignature, URLSafeSerializer
from flask import Flask, Response, abort, has_request_context, jsonify, redirect, render_template, render_template_string, request, session
from sqlalchemy import create_engine, func, inspect, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import access, ads, audit, billing, cuenta, exportar, guias, history, meta, ml, notify, privacy, security, usuarios
from .models import Access, Account, AuditLog, Base, Invite, Notice, PanelState, Snapshot, Subscription, User, utcnow
from .tokens import NeedsReconnect, save_tokens, valid_access_token

log = logging.getLogger("lumo")

SNAPSHOT_TTL = timedelta(hours=3)  # Mercado Libre actualiza los datos una vez al día
MIN_REFRESH = timedelta(minutes=10)  # tope para el botón "Actualizar"
MAX_STATE_BYTES = 200_000
MAX_REQUEST_BYTES = 1_000_000
PUBLIC_URL = "https://lumoads.com.ar"  # dirección pública de la portada: la canónica para Google y la de las imágenes al compartir
TERMS_UPDATED = "10 de noviembre de 2026"  # cambiar cuando cambien los términos y condiciones
ACTIVITY_PAGE = 20  # filas por página en la actividad de /admin
SESSION_DAYS = 30
ADMIN_SESSION_HOURS = 12  # quien administra vuelve a pasar por Mercado Libre pasadas estas horas

PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lumo</title>
<style>
:root{color-scheme:light dark;--bg:#f2f5f8;--card:#fff;--ink:#13202c;--ink2:#44566a;--accent:#2446d6;--ok:#146c43;--bad:#b42318;--line:#dae2e9}
@media (prefers-color-scheme:dark){:root{--bg:#0b131a;--card:#131e28;--ink:#e7edf3;--ink2:#b1becb;--accent:#8ba0ff;--ok:#52cc8c;--bad:#ff8f83;--line:#263543}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;padding:24px 16px}
main{max-width:560px;margin:8vh auto 0;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px}
h1{margin:0 0 8px;font-size:1.6rem}p{color:var(--ink2);margin:8px 0}
.btn{display:inline-block;margin-top:16px;background:var(--accent);color:#fff;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:10px}
@media (prefers-color-scheme:dark){.btn{color:#0b131a}}
.ok{color:var(--ok);font-weight:700}.bad{color:var(--bad);font-weight:700}
ul{padding-left:20px}li{margin:4px 0}code{background:var(--line);padding:1px 6px;border-radius:6px}
</style></head><body><main>{{ body|safe }}</main></body></html>"""


ERRORES = {
    400: ("No pudimos entender el pedido", "Algo del enlace o del formulario no llegó bien. Volvé al inicio y probá de nuevo."),
    403: ("No tenés permiso para ver esto", "Esta pantalla no está disponible para tu cuenta. Si creés que es un error, escribinos."),
    404: ("No encontramos esta página", "Puede que el enlace esté mal escrito o que la página ya no exista. Volvé al inicio y seguí desde ahí."),
    405: ("Esa acción no está disponible acá", "Volvé al inicio y probá de nuevo desde el panel."),
    413: ("El archivo es demasiado grande", "Probá con uno más liviano."),
    429: ("Estás yendo muy rápido", "Esperá un momento y probá de nuevo."),
    500: ("Algo salió mal de nuestro lado", "No es culpa tuya. Ya quedó registrado. Probá de nuevo en un rato y, si sigue, avisanos."),
    502: ("Lumo está despertando", "Esperá unos segundos y recargá la página."),
    503: ("Lumo está descansando un momento", "Esperá unos segundos y recargá la página."),
    504: ("Lumo tardó demasiado en responder", "Esperá unos segundos y recargá la página."),
}
ERRORES_4XX = ("No pudimos abrir esto", "Volvé al inicio y probá de nuevo.")
ERRORES_5XX = ERRORES[500]


def page(body: str, status: int = 200):
    return render_template_string(PAGE, body=body), status


def load_config(overrides=None) -> dict:
    cfg = {
        "ML_CLIENT_ID": os.environ.get("ML_CLIENT_ID", ""),
        "ML_CLIENT_SECRET": os.environ.get("ML_CLIENT_SECRET", ""),
        "REDIRECT_URI": os.environ.get("REDIRECT_URI", ""),
        "ENCRYPTION_KEY": os.environ.get("ENCRYPTION_KEY", ""),
        # Claves anteriores (separadas por coma) mientras se rota ENCRYPTION_KEY. Ver crypto.py.
        "ENCRYPTION_KEY_PREVIOUS": os.environ.get("ENCRYPTION_KEY_PREVIOUS", ""),
        "SECRET_KEY": os.environ.get("SECRET_KEY", ""),
        "DATABASE_URL": os.environ.get("DATABASE_URL", "sqlite:///lumo.db"),
        "ML_AUTH_BASE": os.environ.get("ML_AUTH_BASE", "https://auth.mercadolibre.com.ar"),
        "ML_API_BASE": os.environ.get("ML_API_BASE", "https://api.mercadolibre.com"),
        "ADMIN_USER_IDS": os.environ.get("ADMIN_USER_IDS", ""),
        "CONTACT_EMAIL": os.environ.get("CONTACT_EMAIL", "lumoads.ml@gmail.com"),
        "ADMIN_NOTIFY_EMAIL": os.environ.get("ADMIN_NOTIFY_EMAIL", ""),  # adónde llegan los avisos de suscripciones; vacío: CONTACT_EMAIL
        # Avisos por email. Se envían por la API de Brevo (BREVO_API_KEY), que sirve en el plan gratis de Render; MAIL_FROM es el remitente
        # verificado en Brevo: con una casilla de Gmail, Brevo lo reemplaza por una suya (…@brevosend.com); con un dominio propio
        # autenticado en Brevo (por ejemplo admin@lumoads.com.ar) sale tal cual. Las respuestas van a CONTACT_EMAIL. Sin Brevo, usa SMTP (SMTP_PASSWORD, contraseña de aplicación de Gmail). Sin ninguno no se envía nada.
        "BREVO_API_KEY": os.environ.get("BREVO_API_KEY", ""),
        "MAIL_FROM": os.environ.get("MAIL_FROM", ""),
        "SMTP_HOST": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "SMTP_PORT": os.environ.get("SMTP_PORT", "587"),
        "SMTP_USER": os.environ.get("SMTP_USER", os.environ.get("CONTACT_EMAIL", "lumoads.ml@gmail.com")),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", ""),
        "CRON_TOKEN": os.environ.get("CRON_TOKEN", ""),
        # Cobro con Mercado Pago. Sin MP_ACCESS_TOKEN, la prueba gratis funciona igual pero no se puede pagar.
        "MP_ACCESS_TOKEN": os.environ.get("MP_ACCESS_TOKEN", ""),
        "MP_WEBHOOK_SECRET": os.environ.get("MP_WEBHOOK_SECRET", ""),
        "MP_API_BASE": os.environ.get("MP_API_BASE", "https://api.mercadopago.com"),
        # Precios en dólares. Se muestran y se cobran en pesos a la cotización del día (USD_RATE_URL, campo "venta"; USD_ARS_RATE la fija a mano).
        "PLAN_PRICE_USD": os.environ.get("PLAN_PRICE_USD", "10"),
        "PLAN_PRICE_ANNUAL_USD": os.environ.get("PLAN_PRICE_ANNUAL_USD", "100"),
        "USD_RATE_URL": os.environ.get("USD_RATE_URL", "https://dolarapi.com/v1/dolares/oficial"),
        "USD_ARS_RATE": os.environ.get("USD_ARS_RATE", ""),
        # Dominios donde Mercado Pago muestra el pago. La página de suscripción solo deja salir hacia ellos.
        "MP_CHECKOUT_ORIGINS": os.environ.get("MP_CHECKOUT_ORIGINS", "https://www.mercadopago.com.ar https://www.mercadopago.com https://sandbox.mercadopago.com.ar"),
        "TRIAL_DAYS": os.environ.get("TRIAL_DAYS", "14"),
        "GRACE_DAYS": os.environ.get("GRACE_DAYS", "7"),  # días que sigue entrando una cuenta con un cobro rechazado
        # Dirección de la portada publicada aparte (servicio estático de Render). Vacía: la app sirve la portada.
        "SITE_URL": os.environ.get("SITE_URL", "").rstrip("/"),
        # Anuncios de Meta: Píxel en la portada y API de Conversiones desde el servidor (lumo/meta.py). Vacíos: no se mide nada.
        "META_PIXEL_ID": os.environ.get("META_PIXEL_ID", ""),
        "META_CAPI_TOKEN": os.environ.get("META_CAPI_TOKEN", ""),
        "META_TEST_EVENT_CODE": os.environ.get("META_TEST_EVENT_CODE", ""),
        "META_API_VERSION": os.environ.get("META_API_VERSION", "v23.0"),
    }
    cfg.update(overrides or {})
    return cfg


def make_engine(url: str):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    if url in ("sqlite://", "sqlite:///:memory:"):
        return create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    if url.startswith("postgresql") and "sslmode" not in url:
        return create_engine(url, pool_pre_ping=True, connect_args={"sslmode": "require"})  # la base siempre por conexión cifrada
    return create_engine(url, pool_pre_ping=True)


def create_app(overrides=None) -> Flask:
    cfg = load_config(overrides)
    prod = cfg["REDIRECT_URI"].startswith("https://")
    if prod and not cfg["SECRET_KEY"]:
        # Sin clave fija cada proceso firmaría las sesiones con una distinta y la app quedaría a medias: mejor no arrancar.
        raise RuntimeError("Falta SECRET_KEY: sin ella no se pueden firmar las sesiones")
    for name, minimum in (("SECRET_KEY", 16), ("ENCRYPTION_KEY", 32), ("CRON_TOKEN", 32)):
        if prod and cfg[name] and len(cfg[name]) < minimum:
            log.error("%s es demasiado corta (menos de %d caracteres): reemplazala por un valor largo y aleatorio", name, minimum)
    app = Flask(__name__)
    app.jinja_env.globals.update(public_url=PUBLIC_URL, guia_ruta=guias.ruta, guias=guias.GUIAS)
    app.config["SECRET_KEY"] = cfg["SECRET_KEY"] or secrets.token_hex(32)
    app.config["SESSION_COOKIE_SECURE"] = prod
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if prod:
        app.config["SESSION_COOKIE_NAME"] = "__Host-lumo"  # el navegador la acepta solo por HTTPS, sin Domain y con Path=/
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # Render termina el HTTPS: así vemos la IP y el esquema reales
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    app.permanent_session_lifetime = timedelta(days=SESSION_DAYS)
    limiter = security.RateLimiter()
    engine = make_engine(cfg["DATABASE_URL"])
    had_access_table = inspect(engine).has_table("access")
    Base.metadata.create_all(engine)
    _widen_scope(engine)
    _add_email_column(engine)
    if not had_access_table:
        _grandfather(engine)
    app.extensions["lumo_cfg"] = cfg
    app.extensions["lumo_engine"] = engine

    def missing_config():
        return [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "REDIRECT_URI", "ENCRYPTION_KEY") if not cfg[k]]

    def _too_many(retry):
        if request.path.startswith("/api/"):
            resp = _json({"error": "espera"}, 429)
        else:
            resp = Response("Demasiados intentos. Esperá un momento y probá de nuevo.", 429, mimetype="text/plain")
        resp.headers["Retry-After"] = str(retry)
        return resp

    @app.before_request
    def _guard():
        path = request.path
        if path.startswith("/static/") or path == "/healthz":
            return None
        rule = security.limit_for(path, request.method)
        if rule and not limiter.allow("%s|%s" % (rule[0], request.remote_addr), rule[1], rule[2]):
            log.warning("tope de pedidos superado en %s", rule[0])
            return _too_many(rule[2])
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not path.startswith("/cron/"):
            # Los navegadores mandan Origin en cada POST: si no es esta misma app, el pedido vino de otro sitio.
            origin = request.headers.get("Origin")
            if (origin and not security.same_origin(origin, request.host)) or request.headers.get("Sec-Fetch-Site") == "cross-site":
                log.warning("pedido de otro origen rechazado en %s", path)
                return Response("Pedido rechazado.", 403, mimetype="text/plain")
        return None

    @app.after_request
    def _secure_headers(resp):
        return security.apply_headers(resp, request.path, prod)

    @app.get("/.well-known/security.txt")
    def security_txt():
        """Cómo avisar de un problema de seguridad (RFC 9116)."""
        contact = cfg.get("CONTACT_EMAIL")
        if not contact:
            abort(404)
        expires = (utcnow() + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Response("Contact: mailto:%s\nExpires: %s\nPreferred-Languages: es, en\n" % (contact, expires), mimetype="text/plain")

    @app.get("/api/precios")
    def api_precios():
        """Precios en pesos para la portada publicada aparte, que no puede calcularlos sola."""
        o = billing.offer(cfg)
        resp = jsonify({k: o[k] for k in ("currency", "monthly", "annual", "saving", "saving_pct")})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "public, max-age=600"
        return resp

    @app.get("/healthz")
    def healthz():
        resp = jsonify({"ok": True})
        resp.headers["Access-Control-Allow-Origin"] = "*"  # la portada publicada aparte lo consulta para despertar al servidor
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/favicon.ico")
    def favicon():
        return redirect("/static/logo.png")

    def _contact(user_id=None, user_email=None):
        """Datos de contacto para la portada. Si no hay ninguno configurado, no se muestra la sección.
        Con el ID (y el email) de quien pide acceso, el mensaje ya sale escrito para que lo habiliten sin pedirle nada más."""
        out = {}
        msg = "Hola, quiero probar Lumo."
        if user_id:
            msg += " Mi ID de Mercado Libre es %s" % user_id + (" y mi email es %s." % user_email if user_email else ".")
        email = cfg.get("CONTACT_EMAIL")
        if email:
            out["email"] = email
            out["mailto"] = "mailto:%s?subject=%s&body=%s" % (email, quote("Acceso a Lumo"), quote(msg))
        return out or None

    def _home():
        site = cfg.get("SITE_URL", "")
        return site if site.startswith("https://") else "/"

    def _error_page(code, ref=None):
        """Pantalla de error en lenguaje simple. Las rutas /api/ responden JSON; todo lo demás, una página de Lumo."""
        title, text = ERRORES.get(code) or (ERRORES_5XX if code >= 500 else ERRORES_4XX)
        if request.path.startswith("/api/") or (request.accept_mimetypes.best == "application/json"):
            resp = jsonify({"error": "not_found" if code == 404 else "error", "status": code, "message": title})
            resp.status_code = code
        else:
            email = cfg.get("CONTACT_EMAIL")
            mailto = None
            if email and code != 404:
                body = "Hola, me apareció el error %s en Lumo (%s)." % (code, request.path) + (" Código: %s." % ref if ref else "")
                mailto = "mailto:%s?subject=%s&body=%s" % (email, quote("Error en Lumo"), quote(body))
            home = "/" if _session_uid() else _home()
            resp = Response(render_template("error.html", code=code, title=title, text=text, ref=ref, home=home, mailto=mailto), code)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(HTTPException)
    def _http_error(exc):
        if exc.code is None or exc.code < 400 or exc.response is not None:
            return exc  # redirecciones y respuestas armadas a mano (por ejemplo abort(redirect(...))) pasan tal cual
        return _error_page(exc.code)

    @app.errorhandler(Exception)
    def _unexpected_error(exc):
        ref = secrets.token_hex(3).upper()
        log.exception("error inesperado %s en %s %s", ref, request.method, request.path)
        return _error_page(500, ref)

    def _offer():
        return {"contact": _contact(), "trial_days": billing.trial_days(cfg), "grace_days": billing.grace_days(cfg), "price": billing.offer(cfg)}
    app.extensions["lumo_offer"] = _offer  # build_site.py la usa para generar la portada estática

    @app.get("/")
    def index():
        miss = missing_config()
        if miss:
            return page("<h1>Lumo</h1><p class='bad'>Falta configurar: %s</p>" % ", ".join("<code>%s</code>" % m for m in miss), 500)
        uid = _current_user()
        if uid:
            return redirect("/admin" if access.is_admin(cfg, uid) else "/panel")
        if _session_uid() or _luid():
            return redirect(_after_login())
        if cfg.get("SITE_URL", "").startswith("https://"):
            return redirect(cfg["SITE_URL"])  # la portada vive aparte y carga al instante
        pixel = meta.pixel_id(cfg)
        resp = Response(render_template("landing.html", invited=False, label=None, pixel=pixel, gtm=security.GTM_ID, **_offer()), mimetype="text/html")
        csp = security.with_gtm(security.CSP)  # solo la portada carga Google Tag Manager y el Píxel
        resp.headers["Content-Security-Policy"] = security.with_meta_pixel(csp) if pixel else csp
        return resp

    @app.get("/invitacion/<token>")
    def invitacion(token):
        with Session(engine) as s:
            inv = access.valid_invite(s, token)
            label = inv.label if inv else None
        if inv is None:
            return render_template("landing.html", invited=False, label=None, invite_error=True, **_offer()), 404
        session["invite"] = token
        return render_template("landing.html", invited=True, label=label, **_offer())

    def _luid():
        """El usuario de Lumo (registrado con su email) de esta sesión, si existe."""
        luid = session.get("luid")
        if not isinstance(luid, int):
            return None
        with Session(engine) as s:
            return luid if s.get(User, luid) else None

    def _after_login():
        """A dónde va quien acaba de entrar: al panel, a elegir su plan o a conectar Mercado Libre."""
        uid = _session_uid()
        if uid:
            if access.is_admin(cfg, uid):
                return "/admin"
            return "/panel" if _current_user() else "/suscripcion"
        pending = _pending()
        if pending:
            with Session(engine) as s:
                if s.get(Subscription, pending).status == "authorized":
                    return "/suscripcion/conectar"
        return "/suscripcion"

    def _entrar_page(state="form", email=None, error=None, status=200):
        resp = Response(render_template("entrar.html", title="Entrar", state=state, email=email, error=error, plan=session.get("plan"),
                                        invited=bool(session.get("invite")), minutes=usuarios.TOKEN_MINUTES, home=_home()), status, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/entrar", methods=["GET", "POST"])
    def entrar():
        """Registro e ingreso: la persona escribe su email y recibe un enlace de un solo uso (sin contraseña).
        Quien ya tiene sesión en este navegador va directo. Mercado Libre se conecta después, desde adentro."""
        if missing_config():
            return redirect("/")
        if request.method == "GET":
            if _session_uid() or _luid():
                return redirect(_after_login())
            _remember_origin()
            return _entrar_page()
        if request.form.get("plan") in billing.PLANS:
            session["plan"] = request.form["plan"]
        email = usuarios.normalize_email(request.form.get("email"))
        if not email:
            return _entrar_page(error="Revisá el email: no parece válido.", status=400)
        if not notify.enabled(cfg):
            log.warning("no se puede mandar el enlace de ingreso: falta configurar el envío de mails")
            return _entrar_page(email=email, error="Hoy no podemos mandar el enlace. Probá más tarde o ingresá con Mercado Libre.", status=503)
        if not limiter.allow("mail|" + email, 3, 900):
            return _entrar_page(state="sent", email=email)  # ya se le mandó hace un momento: no se manda otro ni se avisa distinto
        with Session(engine) as s:
            token = usuarios.create_login_token(s, email, session.get("plan"), session.get("invite"))
            s.commit()
        try:
            notify.send_mail(cfg, email, *notify.login_mail("%s/acceso/%s" % (_base_url(), token), usuarios.TOKEN_MINUTES))
        except Exception as exc:  # proveedor de correo o red: se muestra un mensaje amable y el motivo queda en el registro
            log.warning("el enlace de ingreso no salió: %s", notify.why(exc))
            return _entrar_page(email=email, error="No pudimos mandar el enlace. Probá de nuevo en un rato.", status=502)
        return _entrar_page(state="sent", email=email)

    def _acceso_page(state, email=None, status=200):
        resp = Response(render_template("acceso.html", title="Entrar", state=state, email=email, minutes=usuarios.TOKEN_MINUTES, home=_home()), status, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        # El enlace trae el código: no se le pasa a ningún otro sitio (ni a las tipografías). Con "no-referrer" el navegador
        # mandaría "Origin: null" en el botón y Lumo lo rechazaría como pedido de otro origen, por eso es "same-origin".
        resp.headers["Referrer-Policy"] = "same-origin"
        return resp

    @app.get("/acceso/<token>")
    def acceso(token):
        """Abrir el enlace solo muestra una confirmación: así los programas que revisan los enlaces de los mails no lo gastan."""
        with Session(engine) as s:
            row = usuarios.peek_login_token(s, token)
            email = row.email if row else None
        return _acceso_page("confirm", email) if email else _acceso_page("invalid", status=410)

    @app.post("/acceso/<token>")
    def acceso_entrar(token):
        with Session(engine) as s:
            row = usuarios.consume_login_token(s, token)
            if row is None:
                return _acceso_page("invalid", status=410)
            user = usuarios.get_or_create(s, row.email)
            plan, invite, ml_id, luid = row.plan, row.invite, user.ml_user_id, user.id
            acc = s.get(Account, ml_id) if ml_id else None
            reconnect = bool(ml_id and not (acc and acc.status == "connected"))
            audit.record(s, "login_email", actor=ml_id, detail="usuario %s" % luid)
            s.commit()
        pending = session.get("pending_sub")  # si empezó a pagar antes de entrar, no se pierde
        session.clear()
        session["luid"] = luid
        if pending:
            session["pending_sub"] = pending
        if plan in billing.PLANS:
            session["plan"] = plan
        if invite:
            session["invite"] = invite
        if ml_id:
            session["uid"] = ml_id
        session["at"] = int(time.time())
        session["via"] = "email"  # la administración pide confirmar con Mercado Libre
        session.permanent = True
        return redirect("/connect" if reconnect else _after_login())

    def _remember_origin():
        """El plan que eligió en la portada y de qué anuncio de Meta vino (la portada estática pasa sus cookies del Píxel en la dirección)."""
        if request.args.get("plan") in billing.PLANS:
            session["plan"] = request.args["plan"]
        fbc = meta.clean_fbc(request.args.get("fbc") or request.cookies.get("_fbc")) or meta.fbc_from_click(request.args.get("fbclid"))
        fbp = meta.clean_fbp(request.args.get("fbp") or request.cookies.get("_fbp"))
        if fbc:
            session["fbc"] = fbc
        if fbp:
            session["fbp"] = fbp

    @app.get("/connect")
    def connect():
        if missing_config():
            return redirect("/")
        _remember_origin()
        verifier, challenge = ml.new_pkce()
        state = secrets.token_urlsafe(24)
        session["oauth_state"] = state
        session["pkce_verifier"] = verifier
        return redirect(ml.auth_url(cfg, state, challenge))

    @app.get("/callback")
    def callback():
        if request.args.get("error"):
            return page("<h1>No se pudo conectar</h1><p>Mercado Libre respondió: <code>%s</code></p><a class='btn' href='/'>Volver</a>" % _esc(request.args["error"]), 400)
        expected = session.pop("oauth_state", None)
        verifier = session.pop("pkce_verifier", None)
        state, code = request.args.get("state"), request.args.get("code")
        if not expected or not state or not security.safe_eq(expected, state) or not code or not verifier:
            return page("<h1>No se pudo conectar</h1><p>La sesión venció o el enlace no es válido. Probá de nuevo.</p><a class='btn' href='/'>Volver</a>", 400)
        try:
            tok = ml.exchange_code(cfg, code, verifier)
        except ml.MLError as exc:
            log.warning("exchange_code falló: %s %s", exc.status, exc.code)
            return page("<h1>No se pudo conectar</h1><p>Mercado Libre rechazó el intercambio (<code>%s</code>). Revisá que la dirección de redirección de la app sea exactamente <code>%s</code>.</p>" % (_esc(exc.code), _esc(cfg["REDIRECT_URI"])), 502)
        user_id = int(tok["user_id"])
        invite_token = session.get("invite")
        pending = session.get("pending_sub")
        luid = session.get("luid")
        with Session(engine) as s:
            lumo_user = s.get(User, luid) if isinstance(luid, int) else usuarios.by_ml(s, user_id)
            if lumo_user and usuarios.link_conflict(s, lumo_user, user_id):
                log.warning("la cuenta %s no se puede asociar al usuario %s: %s", user_id, lumo_user.id, usuarios.link_conflict(s, lumo_user, user_id))
                return page("<h1>No se pudo conectar</h1><p>Esa cuenta de Mercado Libre ya está asociada a otro usuario de Lumo, o tu usuario ya tiene otra cuenta conectada. "
                            "Escribinos y lo resolvemos.</p><a class='btn' href='/entrar'>Volver</a>", 409)
            is_new = s.get(Account, user_id) is None
            if pending:
                _claim(s, pending, user_id)  # pagó antes de conectar: la suscripción pasa a esta cuenta
            allowed = access.has_access(s, cfg, user_id)
            if not allowed and invite_token and access.valid_invite(s, invite_token):
                if access.consume_invite(s, invite_token, user_id):
                    inv = s.get(Invite, invite_token)
                    access.grant(s, user_id, inv.label)
                    allowed = True
            acc = save_tokens(s, cfg, user_id, tok)
            acc.email = _read_email(tok["access_token"], acc) or acc.email
            if lumo_user:
                usuarios.link(s, lumo_user, user_id)
                acc.email = lumo_user.email  # los avisos van al email con el que se registró
                lumo_user.last_login_at = utcnow()
            audit.record(s, "login_ok", actor=user_id)
            if meta.enabled(cfg) and not access.is_admin(cfg, user_id):
                meta.remember(s, user_id, session.get("fbc"), session.get("fbp"), request.headers.get("User-Agent"))
                if is_new:
                    _meta_track(s, "Lead", user_id, live=True)
                sub = s.get(Subscription, user_id) if pending else None
                if sub and sub.trial_started_at:  # pagó antes de conectar: la prueba ya empezó (Meta recibe cada evento una sola vez)
                    _meta_track(s, "StartTrial", user_id, billing.price_usd(cfg, sub.plan or "monthly"), live=True)
            s.commit()
            luid = lumo_user.id if lumo_user else None
        chosen, wanted, trial_used = session.get("plan"), session.get("next"), session.get("trial_used")
        session.clear()
        if trial_used:
            session["trial_used"] = True
        if chosen in billing.PLANS:
            session["plan"] = chosen
        if luid:
            session["luid"] = luid
        session["uid"] = user_id  # Lumo recuerda a la persona en este navegador
        session["at"] = int(time.time())  # cuándo entró: las sesiones de administración vencen antes
        session["via"] = "ml"  # entró con Mercado Libre: es lo que pide la administración
        session.permanent = True
        if wanted == "/admin" and not access.is_admin(cfg, user_id):
            # Quería entrar a la administración con una cuenta que no administra: se le dice cuál usó, en vez de mandarlo a pagar.
            log.warning("la cuenta %s quiso entrar a la administración y no es administradora", user_id)
            return page("<h1>Esta cuenta no administra Lumo</h1><p>Entraste con la cuenta de Mercado Libre número <code>%d</code>, "
                        "que no figura entre las cuentas administradoras.</p><p>Si entraste con otra cuenta por error, cerrá la sesión en "
                        "mercadolibre.com.ar y volvé a intentarlo. Si es tu cuenta, agregá ese número en la variable <code>ADMIN_USER_IDS</code> "
                        "de la app en Render.</p><a class='btn' href='/salir'>Salir</a>" % user_id, 403)
        if not allowed:
            log.info("la cuenta %s no tiene una suscripción activa", user_id)  # nueva: va a empezar su prueba gratis
            return redirect("/suscripcion")
        if wanted == "/admin" and access.is_admin(cfg, user_id):
            return redirect("/admin")  # venía de abrir la administración
        body, ok = _result_body(cfg, tok, user_id)
        if ok:
            return redirect("/panel")
        if access.is_admin(cfg, user_id):
            return redirect("/admin")
        return page(body)

    def _read_email(token, acc=None):
        """El email de la cuenta de Mercado Libre, para los avisos. Si no se puede leer, los avisos quedan sin destino.
        Con acc, además guarda en la cuenta el email y el apodo de Mercado Libre tal cual, para la administración."""
        try:
            body = ml.api_get(cfg, token, "/users/me", None, None)
        except ml.MLError as exc:
            log.warning("no se pudo leer el email: %s", exc.status)
            return None
        except requests.RequestException as exc:  # sin red o Mercado Libre no responde: la persona entra igual
            log.warning("no se pudo leer el email: %s", type(exc).__name__)
            return None
        mail = body.get("email") if isinstance(body, dict) else None
        if acc is not None and isinstance(body, dict):
            nick = body.get("nickname")
            acc.ml_nickname = nick[:120] if isinstance(nick, str) and nick else acc.ml_nickname
            acc.ml_email = mail if isinstance(mail, str) and "@" in mail else acc.ml_email
        if not (isinstance(mail, str) and "@" in mail):
            log.warning("Mercado Libre no devolvió el email; campos recibidos: %s", sorted(body)[:30] if isinstance(body, dict) else type(body).__name__)
            return None
        return mail

    def _session_uid():
        """El id de la cuenta de esta sesión, si está conectada (tenga o no la suscripción al día)."""
        uid = session.get("uid")
        if not uid:
            return None
        with Session(engine) as s:
            acc = s.get(Account, uid)
            return uid if acc and acc.status == "connected" else None

    def _current_user():
        """El id de la cuenta de esta sesión, solo si está conectada y sigue teniendo acceso."""
        uid = _session_uid()
        if not uid:
            return None
        with Session(engine) as s:
            return uid if access.has_access(s, cfg, uid) else None

    @app.get("/panel")
    def panel():
        if not _current_user():
            return redirect("/suscripcion" if _session_uid() else "/")
        data = json.dumps(_contact() or {}).replace("<", "\\u003c")
        resp = Response(PANEL_HTML.replace("</head>", "<script>window.LUMO_CONTACT=%s;</script></head>" % data, 1), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/salir")
    def salir():
        session.clear()
        return redirect(_home())

    def _json(data, status=200):
        resp = jsonify(data)
        resp.status_code = status
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _api_error(exc, advertisers=False):
        """Solo un 404 al listar anunciantes significa que no hay Publicidad habilitada; en otras rutas es otro problema."""
        if exc.status == 404 and advertisers:
            return _json({"error": "no_ads"}, 404)
        kind = {401: "forbidden", 403: "forbidden", 429: "busy"}.get(exc.status, "api")
        detail = ("%s %s %s" % (exc.status, exc.code, exc.path or "/advertising/advertisers")).strip()
        return _json({"error": kind, "detail": detail}, 503 if kind == "busy" else 502)

    def _no_ads(token):
        """Sin Publicidad: se responde con lo que tiene y lo que le falta a la cuenta, para que el panel lo explique."""
        get = lambda path, params=None, version="2": ml.api_get(cfg, token, path, params, version)
        return _json({"error": "no_ads", "cuenta": cuenta.build(get)}, 404)

    @app.get("/api/datos")
    def api_datos():
        uid = _current_user()
        if not uid:
            return _json({"error": "plan"}, 402) if _session_uid() else _json({"error": "login"}, 401)
        want = request.args.get("adv", type=int)
        refresh = request.args.get("refresh") == "1"
        with Session(engine) as s:
            snap = s.get(Snapshot, uid)
            age = utcnow() - snap.fetched_at if snap else None
            limit = MIN_REFRESH if refresh else SNAPSHOT_TTL  # "Actualizar" salta la copia, pero no más de una vez cada 10 minutos
            usable = snap and (want is None or snap.advertiser_id == want) and age < limit
            if usable:
                data = json.loads(snap.data)
            else:
                try:
                    token = valid_access_token(s, cfg, uid)
                except NeedsReconnect:
                    return _json({"error": "reconnect"}, 401)
                try:
                    advs = ml.advertisers(cfg, token)
                except ml.MLError as exc:
                    log.warning("anunciantes falló: %s %s", exc.status, exc.code)
                    if exc.status == 404:
                        return _no_ads(token)
                    return _api_error(exc, advertisers=True)
                if not advs:
                    return _no_ads(token)
                adv = next((a for a in advs if a["advertiser_id"] == want), advs[0])
                get = lambda path, params=None, version="2": ml.api_get(cfg, token, path, params, version)
                try:
                    data = ads.build_dataset(get, adv)
                except ml.MLError as exc:
                    log.warning("lectura de datos falló: %s %s %s", exc.status, exc.code, exc.path)
                    return _api_error(exc)
                data["advertisers"] = [{"id": a["advertiser_id"], "name": a.get("advertiser_name"), "site": a.get("site_id")} for a in advs]
                row = snap or Snapshot(user_id=uid)
                row.advertiser_id, row.data, row.fetched_at = data["advertiser"]["id"], json.dumps(data), utcnow()
                s.add(row)
                s.commit()
                history.save(s, uid, data)
            data = history.extend(s, uid, data)
            st = s.get(PanelState, uid)
            data["estado"] = json.loads(st.data) if st else {}
            acc = s.get(Account, uid)
            if acc and not acc.email and notify.enabled(cfg) and notify._due(s, uid, "mailread", "x", timedelta(hours=1), utcnow()):
                # Cuentas conectadas antes de los avisos: se intenta leer el email una vez por hora, sin pedir que reconecten.
                try:
                    acc.email = _read_email(valid_access_token(s, cfg, uid), acc)
                except NeedsReconnect:
                    pass
                notify._mark(s, uid, "mailread", "x", utcnow())
                s.commit()
            data["email"] = acc.email if acc else None
            data["mailOn"] = notify.enabled(cfg)
            data["admin"] = access.is_admin(cfg, uid)
            data["uid"] = uid
            p = access.plan(s, cfg, uid)
            data["plan"] = {"kind": p["kind"], "days": p.get("days"), "pastDue": bool(p.get("past_due"))}
        return _json(data)

    @app.get("/api/exportar")
    def api_exportar():
        """Excel con las tablas del panel (campañas, publicaciones y días) del período que se está viendo."""
        uid = _current_user()
        if not uid:
            return _json({"error": "plan"}, 402) if _session_uid() else _json({"error": "login"}, 401)
        with Session(engine) as s:
            snap = s.get(Snapshot, uid)
            if not snap:
                return _json({"error": "sin_datos"}, 404)
            data = history.extend(s, uid, json.loads(snap.data))
        days, off = request.args.get("days", 30, type=int), request.args.get("off", 0, type=int)
        resp = Response(exportar.excel(data, days, off), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp.headers["Content-Disposition"] = 'attachment; filename="%s"' % exportar.nombre_archivo(data, days, off)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/api/estado")
    def api_estado():
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _json({"error": "formato"}, 400)
        clean = {k: body[k] for k in ("done", "actions", "custom", "sw") if k in body}
        raw = json.dumps(clean)
        if len(raw) > MAX_STATE_BYTES:
            return _json({"error": "grande"}, 413)
        with Session(engine) as s:
            row = s.get(PanelState, uid) or PanelState(user_id=uid)
            row.data = raw
            s.add(row)
            s.commit()
        return _json({"ok": True})

    # ---------- Administración: invitaciones y accesos ----------
    def _app_link(tab="recomendaciones"):
        base = cfg["REDIRECT_URI"].rsplit("/callback", 1)[0] if cfg["REDIRECT_URI"] else ""
        return base + "/panel#" + tab

    @app.post("/api/email")
    def api_email():
        """La persona escribe su email cuando Mercado Libre no lo informa."""
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        body = request.get_json(silent=True)
        mail = str(body.get("email", "")).strip() if isinstance(body, dict) else ""
        if len(mail) > 200 or not re.fullmatch(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}", mail):
            return _json({"error": "formato"}, 400)
        with Session(engine) as s:
            acc = s.get(Account, uid)
            acc.email = mail
            audit.record(s, "email_set", actor=uid)
            s.commit()
        return _json({"ok": True, "email": mail})

    MAIL_WHY = "Te lo mandamos porque lo pediste desde tu panel de Lumo. No enviamos nada que no pidas."
    MAIL_PER_HOUR = 10  # tope de mails pedidos por persona

    def _mail_request(uid, kind, ref):
        """Valida lo común de los mails a pedido. Devuelve (email, error): el error ya es una respuesta."""
        if not notify.enabled(cfg):
            return None, _json({"error": "apagado"}, 503)
        with Session(engine) as s:
            acc = s.get(Account, uid)
            if not acc or not acc.email:
                return None, _json({"error": "sin_email"}, 400)
            now = utcnow()
            pedidos = s.execute(select(func.count()).select_from(Notice).where(
                Notice.user_id == uid, Notice.kind.in_(("rec", "resumen")), Notice.sent_at > now - timedelta(hours=1))).scalar()
            if pedidos >= MAIL_PER_HOUR or not notify._due(s, uid, kind, ref, timedelta(minutes=1), now):
                return None, _json({"error": "espera"}, 429)
            return acc.email, None

    def _mail_sent(uid, kind, ref):
        with Session(engine) as s:
            notify._mark(s, uid, kind, ref, utcnow())
            s.commit()

    @app.post("/api/recomendacion/mail")
    def recomendacion_mail():
        """Manda a la propia cuenta la recomendación que la persona eligió. Nunca a otra dirección."""
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        title, text, action = (" ".join(str(body.get(k) or "").split()) if k == "title" else str(body.get(k) or "").strip() for k in ("title", "text", "action"))
        if not title or len(title) > 200 or not text or len(text) > 1500 or len(action) > 800:
            return _json({"error": "formato"}, 400)
        ref = hashlib.sha256(title.encode()).hexdigest()[:16]
        email, err = _mail_request(uid, "rec", ref)
        if err:
            return err
        try:
            notify.send_mail(cfg, email, *notify.recommendation_mail(title, text, action, _app_link(), MAIL_WHY))
        except Exception as exc:  # proveedor y red: al usuario no se le detalla, pero el motivo queda en el registro
            log.warning("mail de recomendación falló: %s", notify.why(exc))
            return _json({"error": "envio"}, 502)
        _mail_sent(uid, "rec", ref)
        return _json({"ok": True, "email": email})

    @app.post("/api/resumen/mail")
    def resumen_mail():
        """El resumen de los últimos 7 días con su Excel, a la propia cuenta y solo cuando la persona lo pide."""
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        email, err = _mail_request(uid, "resumen", "x")
        if err:
            return err
        with Session(engine) as s:
            snap = s.get(Snapshot, uid)
            data = json.loads(snap.data) if snap else None
        if not data:
            return _json({"error": "sin_datos"}, 409)
        try:
            attachments = [notify.weekly_excel(data)]
        except Exception as exc:  # sin el Excel igual se manda el resumen
            log.warning("el Excel del resumen falló: %s", type(exc).__name__)
            attachments = []
        try:
            notify.send_mail(cfg, email, *notify.weekly_mail(data, _app_link("principal"), MAIL_WHY), **({"attachments": attachments} if attachments else {}))
        except Exception as exc:
            log.warning("mail de resumen falló: %s", notify.why(exc))
            return _json({"error": "envio"}, 502)
        _mail_sent(uid, "resumen", "x")
        return _json({"ok": True, "email": email})

    @app.post("/cron/avisos")
    def cron_avisos():
        """Tarea diaria (la llama GitHub Actions con la clave CRON_TOKEN): cobros, vencimientos y plazos de conservación de datos.
        No envía recomendaciones: esas solo salen cuando la persona las pide con un botón del panel."""
        token = cfg["CRON_TOKEN"]
        if not token:
            abort(404)
        if not security.safe_eq(request.headers.get("X-Cron-Token", ""), token):
            log.warning("cron/avisos: clave incorrecta")
            abort(403)
        cobros = _billing_tick()
        with Session(engine) as s:
            purged = privacy.purge(s)  # plazos de conservación: se aplican una vez por día
            audit.record(s, "cron_run", detail="tarea diaria")
            s.commit()
        return _json({"ok": True, "purga": purged, "cobros": cobros})

    def _admin_uid():
        if not _session_uid() and request.method == "GET":
            session["next"] = "/admin"  # sin sesión: inicia sesión con Mercado Libre y vuelve a la administración
            abort(redirect("/connect"))
        uid = _current_user()
        if not uid or not access.is_admin(cfg, uid):
            if uid:
                log.warning("la cuenta %s intentó entrar a la administración", uid)
            abort(404)  # a quien no administra, la página ni siquiera le aparece
        if session.get("via") != "ml" or time.time() - session.get("at", 0) > ADMIN_SESSION_HOURS * 3600:
            session["next"] = "/admin"
            abort(redirect("/connect"))  # entró con el email, o la sesión venció: la administración se confirma con Mercado Libre
        return uid

    def _csrf() -> str:
        if not session.get("csrf"):
            session["csrf"] = secrets.token_urlsafe(24)
        return session["csrf"]

    def _check_csrf():
        if not session.get("csrf") or not security.safe_eq(request.form.get("csrf", ""), session["csrf"]):
            abort(400)

    @app.get("/admin")
    def admin():
        _admin_uid()
        base = request.url_root.rstrip("/")
        now = utcnow()
        with Session(engine) as s:
            invites = []
            for inv in s.execute(select(Invite).order_by(Invite.created_at.desc())).scalars():
                state = "revocada" if inv.revoked else "usada" if inv.used_by else "vencida" if inv.expires_at < now else "pendiente"
                invites.append({"token": inv.token, "label": inv.label or "Sin nombre", "state": state, "url": "%s/invitacion/%s" % (base, inv.token),
                                "expires": inv.expires_at, "used_by": inv.used_by})
            members = []
            for row in s.execute(select(Access).order_by(Access.created_at.desc())).scalars():
                acc, snap = s.get(Account, row.user_id), s.get(Snapshot, row.user_id)
                name = None
                if snap:
                    try:
                        name = json.loads(snap.data).get("advertiser", {}).get("name")
                    except ValueError:
                        pass
                members.append({"user_id": row.user_id, "note": row.note, "since": row.created_at,
                                "status": acc.status if acc else "sin conectar", "advertiser": name})
            subs, unclaimed = [], []
            for sub in s.execute(select(Subscription).order_by(Subscription.created_at.desc())).scalars():
                if sub.user_id < 0:  # pagó y todavía no conectó Mercado Libre
                    if sub.status in ("authorized", "paused"):
                        unclaimed.append({"email": sub.payer_email, "plan": billing.NAMES.get(sub.plan), "since": sub.created_at,
                                          "trial_ends": sub.trial_ends_at if billing.in_trial(sub) else None, "status": sub.status,
                                          "url": "%s/suscripcion/conectar?c=%s" % (base, _claim_token(sub.user_id))})
                    continue
                p = access.plan(s, cfg, sub.user_id)
                acc, user = s.get(Account, sub.user_id), usuarios.by_ml(s, sub.user_id)
                snap = s.get(Snapshot, sub.user_id)
                try:
                    advertiser = json.loads(snap.data).get("advertiser", {}).get("name") if snap else None
                except ValueError:
                    advertiser = None
                subs.append({"user_id": sub.user_id, "kind": p["kind"], "days": p.get("days"), "status": sub.status, "reason": p.get("reason"),
                             "plan": billing.NAMES.get(sub.plan), "next_plan": billing.NAMES.get(sub.next_plan), "past_due": bool(p.get("past_due")),
                             "grace_ends": p.get("grace_ends"), "email": sub.payer_email, "trial_ends": sub.trial_ends_at, "paid_until": sub.paid_until,
                             # cuenta de Mercado Libre: email y apodo tal cual los informa (las cuentas viejas lo completan en su próximo ingreso)
                             "ml_email": (acc.ml_email if acc else None) or (acc.email if acc and not user else None),
                             "nickname": acc.ml_nickname if acc else None, "lumo_email": user.email if user else None,
                             "advertiser": advertiser, "conn": acc.status if acc else None, "connected_at": acc.created_at if acc else None,
                             "last_login": (user.last_login_at if user else None) or (acc.updated_at if acc else None),
                             "since": sub.created_at, "trial_started": sub.trial_started_at, "amount": notify.money(sub.amount_ars) if sub.amount_ars else None,
                             "past_due_since": sub.past_due_since, "mp_id": sub.mp_preapproval_id})
            all_subs = s.execute(select(Subscription)).scalars().all()
            stats = {"paying": sum(1 for x in subs if x["kind"] == "paid" and x["status"] == "authorized" and not x["past_due"]),
                     "trial": sum(1 for x in subs if x["kind"] == "trial"), "past_due": sum(1 for x in subs if x["past_due"]),
                     "mrr": billing.usd_label(billing.monthly_revenue_usd(cfg, all_subs))}
            total = s.execute(select(func.count()).select_from(AuditLog)).scalar_one()
            pages = max(1, -(-total // ACTIVITY_PAGE))
            page = min(max(request.args.get("act", 1, type=int) or 1, 1), pages)
            events = s.execute(select(AuditLog).order_by(AuditLog.id.desc()).offset((page - 1) * ACTIVITY_PAGE).limit(ACTIVITY_PAGE)).scalars().all()
            events = [{"at": e.at, "event": e.event, "actor": e.actor, "target": e.target, "detail": e.detail} for e in events]
        return render_template("admin.html", csrf=_csrf(), invites=invites, members=members, subs=subs, unclaimed=unclaimed, admins=sorted(access.admin_ids(cfg)),
                               billing_on=billing.enabled(cfg), stats=stats, events=events,
                               act={"page": page, "pages": pages})

    @app.post("/admin/invitar")
    def admin_invitar():
        admin_uid = _admin_uid(); _check_csrf()
        with Session(engine) as s:
            access.create_invite(s, request.form.get("label", ""))
            audit.record(s, "invite_create", actor=admin_uid)
            s.commit()
        return redirect("/admin#invitaciones")

    @app.post("/admin/invitacion/borrar")
    def admin_borrar_invitacion():
        """Saca la invitación de la lista. Si estaba pendiente, el enlace deja de funcionar; quien ya la usó conserva su acceso."""
        admin_uid = _admin_uid(); _check_csrf()
        with Session(engine) as s:
            inv = s.get(Invite, request.form.get("token", ""))
            if inv:
                audit.record(s, "invite_delete", actor=admin_uid, target=inv.token[:6])
                s.delete(inv)
                s.commit()
        return redirect("/admin#invitaciones")

    @app.post("/admin/invitacion/revocar")
    def admin_revocar():
        admin_uid = _admin_uid(); _check_csrf()
        with Session(engine) as s:
            inv = s.get(Invite, request.form.get("token", ""))
            if inv and inv.used_by is None:
                inv.revoked = True
                audit.record(s, "invite_revoke", actor=admin_uid, target=inv.token[:6])
                s.commit()
        return redirect("/admin#invitaciones")

    @app.post("/admin/acceso/agregar")
    def admin_agregar():
        admin_uid = _admin_uid(); _check_csrf()
        raw = request.form.get("user_id", "").strip()
        if raw.isdigit() and 0 < int(raw) < 2**63:
            with Session(engine) as s:
                access.grant(s, int(raw), request.form.get("note", ""))
                audit.record(s, "access_grant", actor=admin_uid, target=int(raw))
                s.commit()
        return redirect("/admin#accesos")

    @app.post("/admin/acceso/quitar")
    def admin_quitar():
        admin_uid = _admin_uid(); _check_csrf()
        raw = request.form.get("user_id", "").strip()
        if raw.isdigit() and 0 < int(raw) < 2**63:
            uid = int(raw)
            with Session(engine) as s:
                privacy.erase_user(s, uid)
                _end_subscription(s, uid)  # sin una nueva prueba gratis: para volver tiene que suscribirse
                audit.record(s, "access_remove", actor=admin_uid, target=uid)
                s.commit()
        return redirect("/admin#accesos")

    # ---------- Privacidad: transparencia, descarga y borrado de los propios datos ----------
    def guia_page(slug=None):
        """Las guías se sirven igual que en la portada estática (build_site.py las genera con esta misma función)."""
        g = guias.POR_SLUG.get(slug) if slug else None
        if slug and g is None:
            abort(404)
        datos = {"guia": g, "titulo": g["titulo"] if g else "Guías de publicidad en Mercado Libre",
                 "descripcion": g["descripcion"] if g else "Guías simples de Product Ads de Mercado Libre: ROAS, ACOS, presupuesto y cómo mejorar tus campañas.",
                 "trial_days": billing.trial_days(cfg), "gtm": security.GTM_ID}
        return render_template("guias/%s.html" % (slug or "index"), **datos)
    app.extensions["lumo_guia"] = guia_page

    @app.get("/guias/")
    @app.get("/guias/<slug>/")
    def guia(slug=None):
        resp = Response(guia_page(slug), mimetype="text/html")
        resp.headers["Content-Security-Policy"] = security.with_gtm(security.CSP)
        return resp

    # ---------- Pedido de demo: el formulario de la portada llega por mail a quien administra ----------
    DEMO_OPCIONES = {
        "perfiles": ("Vendedor", "Agencia o consultor", "Marca o fabricante"),
        "usos": ("Sí, hace tiempo", "Sí, hace poco", "No, quiero empezar"),
        "inversiones": ("No sé / prefiero no decir", "Menos de $100.000", "$100.000 a $500.000", "$500.000 a $2.000.000", "Más de $2.000.000"),
        "campanas": ("No sé", "1", "2 a 5", "6 a 15", "Más de 15"),
        "publicaciones": ("No sé", "Menos de 20", "20 a 100", "100 a 500", "Más de 500"),
        "objetivos": ("Vender más", "Gastar menos por venta", "Entender las métricas", "Saber qué hacer primero", "Ahorrar tiempo", "Seguir a mis clientes"),
        "horarios": ("Cualquier momento", "Mañana (9 a 12)", "Mediodía (12 a 15)", "Tarde (15 a 19)"),
        "origenes": ("Anuncio en Instagram o Facebook", "Google", "Recomendación", "Otro"),
    }
    DEMO_TEXTO = (("nombre", 120), ("telefono", 40), ("tienda", 120), ("rubro", 200), ("dolor", 1000))

    def _demo_page(f=None, error=None, sent=False, status=200):
        f = f or {"objetivos": []}
        resp = Response(render_template("demo.html", csrf=_csrf(), f=f, error=error, sent=sent, home=_home(), **DEMO_OPCIONES), status, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/demo")
    def demo():
        _remember_origin()
        return _demo_page()

    @app.post("/demo")
    def demo_pedir():
        _check_csrf()
        form = request.form
        f = {k: (form.get(k) or "").strip()[:n] for k, n in DEMO_TEXTO}
        f["email"] = (form.get("email") or "").strip()[:254]
        for key, opts in (("perfil", "perfiles"), ("ads", "usos"), ("inversion", "inversiones"), ("campanas", "campanas"),
                          ("publicaciones", "publicaciones"), ("horario", "horarios"), ("origen", "origenes")):
            f[key] = form.get(key) if form.get(key) in DEMO_OPCIONES[opts] else ""
        f["objetivos"] = [o for o in form.getlist("objetivos") if o in DEMO_OPCIONES["objetivos"]]
        if form.get("web"):
            return _demo_page(sent=True)  # lo completó un robot: se le agradece y no se manda nada
        if not billing.EMAIL_RE.match(f["email"]):
            return _demo_page(f, "Revisá el email: lo necesitamos para contactarte.", status=400)
        to = cfg.get("ADMIN_NOTIFY_EMAIL") or _tagged(cfg.get("CONTACT_EMAIL"), "demos")
        if not to or not notify.enabled(cfg):
            log.warning("pedido de demo sin envío de mails configurado")
            return _demo_page(f, "Hoy no pudimos recibir tu pedido. Escribinos a %s y coordinamos." % (cfg.get("CONTACT_EMAIL") or "nuestro email"), status=503)
        rows = [("Nombre", f["nombre"]), ("Email", f["email"]), ("WhatsApp / teléfono", f["telefono"]), ("Tienda en Mercado Libre", f["tienda"]),
                ("Perfil", f["perfil"]), ("Qué vende", f["rubro"]), ("Usa Product Ads", f["ads"]), ("Inversión mensual", f["inversion"]),
                ("Campañas activas", f["campanas"]), ("Publicaciones activas", f["publicaciones"]), ("Objetivos", ", ".join(f["objetivos"])),
                ("Lo que más le cuesta", f["dolor"]), ("Horario para la demo", f["horario"]), ("Cómo conoció Lumo", f["origen"])]
        subject, text, html = notify.admin_mail("Pedido de demo de %s" % (f["nombre"] or f["email"]), rows, _base_url() + "/admin")
        try:
            notify.send_mail(cfg, to, subject, text, html, reply_to=f["email"])  # responder el mail le escribe a la persona
        except Exception as exc:
            log.warning("el pedido de demo no salió: %s", notify.why(exc))
            return _demo_page(f, "No pudimos mandar tu pedido. Probá de nuevo en un rato o escribinos a %s." % cfg.get("CONTACT_EMAIL", ""), status=502)
        with Session(engine) as s:
            audit.record(s, "demo_pedido", detail=(f["perfil"] or "")[:40])
            s.commit()
        return _demo_page(sent=True)

    @app.get("/privacidad")
    def privacidad():
        uid = _current_user()
        return render_template("privacidad.html", contact=_contact(), home=_home(), logged=bool(uid), csrf=_csrf() if uid else "",
                               audit_days=privacy.AUDIT_DAYS, history_days=privacy.HISTORY_DAYS)

    @app.get("/terminos")
    def terminos():
        return render_template("terminos.html", home=_home(), updated=TERMS_UPDATED, **_offer())

    @app.get("/arrepentimiento")
    def arrepentimiento():
        """Botón de arrepentimiento: revocar la contratación dentro de los 10 días (Ley 24.240, art. 34; Res. 424/2020)."""
        uid = _session_uid()
        return render_template("arrepentimiento.html", home=_home(), contact=_contact(), logged=bool(uid), csrf=_csrf() if uid else "", code=None)

    @app.post("/arrepentimiento")
    def arrepentimiento_revocar():
        uid = _session_uid()
        if not uid:
            return redirect("/arrepentimiento")
        _check_csrf()
        code = "ARR-%d-%s" % (uid, secrets.token_hex(3).upper())
        with Session(engine) as s:
            sub, acc = s.get(Subscription, uid), s.get(Account, uid)
            had = bool(sub and sub.status in billing.LIVE and sub.mp_preapproval_id)
            to = (acc.email if acc else None) or (sub.payer_email if sub else None)
            if sub and sub.status != "new":
                billing.end(cfg, sub, keep_email=True)  # corta el cobro y el acceso; el email queda para poder devolver el dinero
            audit.record(s, "arrepentimiento", actor=uid, detail=code)
            s.commit()
        if notify.enabled(cfg):
            # A quien administra Lumo, para que revise si hay un cobro que devolver; a la persona, como constancia.
            aviso = ("Arrepentimiento %s" % code, "La cuenta %d revocó su contratación (código %s).%s\n\nRevisá en Mercado Pago si tuvo un cobro "
                     "en los últimos 10 días y devolvelo.\n" % (uid, code, " Email: %s." % to if to else ""))
            copia = ("Tu pedido de arrepentimiento en Lumo: %s" % code, "Recibimos tu pedido de arrepentimiento. Tu código de identificación es %s.\n\n"
                     "Tu suscripción quedó cancelada y no se te va a volver a cobrar. Si se te cobró en los últimos 10 días, te devolvemos el importe.\n" % code)
            for dest, (subject, text) in ((cfg.get("CONTACT_EMAIL"), aviso), (to, copia)):
                if dest:
                    try:
                        notify.send_mail(cfg, dest, subject, text, "<pre style='font-family:Arial,sans-serif;white-space:pre-wrap'>%s</pre>" % _esc(text))
                    except Exception as exc:  # la constancia ya quedó en pantalla y en el registro de actividad
                        log.warning("aviso de arrepentimiento falló: %s", notify.why(exc))
        resp = Response(render_template("arrepentimiento.html", home=_home(), contact=_contact(), logged=True, csrf="", code=code, had_subscription=had), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/api/cuenta/exportar")
    def cuenta_exportar():
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        with Session(engine) as s:
            data = privacy.export_user(s, uid)
            audit.record(s, "data_export", actor=uid)
            s.commit()
        resp = _json(data)
        resp.headers["Content-Disposition"] = 'attachment; filename="mis-datos-lumo.json"'
        return resp

    @app.post("/cuenta/eliminar")
    def cuenta_eliminar():
        uid = _current_user()
        if not uid:
            return redirect("/")
        _check_csrf()
        with Session(engine) as s:
            privacy.erase_user(s, uid)
            _end_subscription(s, uid)  # deja de cobrarse; no vuelve a tener prueba gratis
            audit.record(s, "account_erase", actor=uid)
            s.commit()
        session.clear()
        return page("<h1>Listo, borramos tus datos</h1><p>Eliminamos tu cuenta de Lumo y todo lo que guardábamos de ella.</p>"
                    "<p>Para que Lumo deje de tener permiso sobre tu cuenta de Mercado Libre, también podés quitarlo desde <b>Mi perfil → Seguridad → Aplicaciones conectadas</b>.</p>"
                    "<a class='btn' href='%s'>Volver al inicio</a>" % _esc(_home()))

    def _end_subscription(s, uid):
        """Corta el cobro en Mercado Pago y deja solo la marca de que la prueba gratis ya se usó (sin email ni datos de pago)."""
        sub = s.get(Subscription, uid)
        if sub is not None:  # quien nunca se suscribió no tiene nada que cortar
            billing.end(cfg, sub)

    # ---------- Suscripción con Mercado Pago ----------
    def _base_url():
        uri = cfg["REDIRECT_URI"]
        return uri[: -len("/callback")] if uri.endswith("/callback") else request.url_root.rstrip("/")

    def _suscripcion_page(uid, error=None, status=200, detail=None):
        """uid es la cuenta de Mercado Libre de la sesión, o, para quien todavía no la conectó, su suscripción provisoria (número negativo)."""
        with Session(engine) as s:
            p = access.plan(s, cfg, uid) if uid else {"kind": "none"}
            sub = s.get(Subscription, uid) if uid else None
            acc = s.get(Account, uid) if uid and uid > 0 else None
            luid = session.get("luid")
            lumo_user = s.get(User, luid) if isinstance(luid, int) else None
            email = (sub.payer_email if sub else None) or (acc.email if acc else None) or (lumo_user.email if lumo_user else None) or ""
            can_cancel = bool(sub and sub.mp_preapproval_id and sub.status in billing.LIVE)
            trial_offer = billing.trial_available(sub)
        html = render_template("suscripcion.html", plan=p, email=email, csrf=_csrf(), error=error, detail=detail, can_cancel=can_cancel, home=_home(), trial_offer=trial_offer,
                               chosen=request.form.get("plan") or session.get("plan"),
                               names=billing.NAMES, estado=request.args.get("estado"), billing_on=billing.enabled(cfg),
                               anon=not (uid and uid > 0), registered=bool(lumo_user), **_offer())
        resp = Response(html, status, mimetype="text/html")
        # El formulario de pago termina en Mercado Pago: esta página, y solo esta, puede enviar hacia sus dominios de pago.
        # Sin esto, los navegadores bloquean la redirección por la regla form-action 'self'.
        resp.headers["Content-Security-Policy"] = security.CSP.replace("form-action 'self'", "form-action 'self' " + " ".join(_checkout_origins()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _checkout_origins():
        return [o for o in cfg["MP_CHECKOUT_ORIGINS"].split() if o.startswith("https://") or not prod]

    # Quien llega desde la portada primero elige su plan y paga en Mercado Pago, y después conecta Mercado Libre.
    # Mientras no la conecta, su suscripción vive con un número provisorio negativo (no hay cuentas de Mercado Libre negativas)
    # y se pasa a su cuenta en el /callback. Si pierde la sesión, el enlace firmado de /suscripcion/conectar la recupera.
    claims = URLSafeSerializer(cfg["SECRET_KEY"], salt="lumo-pago-sin-conectar")

    def _claim_token(pending_id):
        return claims.dumps(-int(pending_id))

    def _pending_from(token):
        try:
            value = int(claims.loads(token or ""))
        except (BadSignature, ValueError, TypeError):
            return None
        return -value if value > 0 else None

    def _pending():
        """La suscripción provisoria de este navegador, si todavía existe (se borra cuando se pasa a una cuenta)."""
        pid = session.get("pending_sub")
        if not isinstance(pid, int) or pid >= 0:
            return None
        with Session(engine) as s:
            return pid if s.get(Subscription, pid) else None

    def _claim(s, pending_id, uid):
        """Pasa la suscripción pagada antes de conectar a la cuenta de Mercado Libre que se acaba de conectar."""
        session.pop("pending_sub", None)
        tmp = s.get(Subscription, pending_id) if isinstance(pending_id, int) and pending_id < 0 else None
        if tmp is None:
            return
        p, cur = access.plan(s, cfg, uid), s.get(Subscription, uid)
        if p["kind"] in ("admin", "free") or (cur and cur.status == "authorized" and p["kind"] in ("paid", "trial")):
            # Ya entraba sin pagar, o ya tiene un plan al día: no se le cobra dos veces.
            billing.end(cfg, tmp)
            s.delete(tmp)
            audit.record(s, "sub_claim_dup", actor=uid, detail=tmp.plan)
            return
        used = cur.trial_started_at if cur else None
        if used and billing.in_trial(tmp):
            # Ya usó su prueba gratis con esta cuenta y pagó antes de conectar como si fuera nueva: Mercado Pago le cobraría
            # recién al terminar otra prueba. Se cancela ese pago y se le pide suscribirse de nuevo, con el cobro de hoy.
            billing.end(cfg, tmp)
            s.delete(tmp)
            audit.record(s, "sub_claim_trial_used", actor=uid, detail=tmp.plan)
            session["trial_used"] = True
            return
        data = {c.name: getattr(tmp, c.name) for c in Subscription.__table__.columns if c.name != "user_id"}
        if cur:
            billing.end(cfg, cur)  # una suscripción vieja sin terminar no puede seguir viva en Mercado Pago
            s.delete(cur)
        s.delete(tmp)
        s.flush()
        sub = Subscription(user_id=uid, **data)
        if used:  # la prueba gratis es una sola por cuenta: quien ya la usó entra como plan pago
            sub.trial_started_at = min(used, sub.trial_started_at or used)
            sub.trial_ends_at = min(sub.trial_ends_at or utcnow(), utcnow())
        s.add(sub)
        audit.record(s, "sub_claim", actor=uid, detail=sub.plan)
        _admin_alert(s, "Conectó Mercado Libre después de pagar", sub)

    @app.get("/suscripcion")
    def suscripcion():
        uid = _session_uid()
        if uid:
            if session.pop("trial_used", None):
                return _suscripcion_page(uid, "Esta cuenta ya usó su prueba gratis, así que cancelamos ese pago en Mercado Pago (no se te cobró nada). "
                                              "Para seguir usando Lumo, elegí tu plan: el primer cobro es hoy.")
            return _suscripcion_page(uid)
        _remember_origin()
        pending = _pending()
        if pending:
            with Session(engine) as s:
                if s.get(Subscription, pending).status == "authorized":
                    return redirect("/suscripcion/conectar")
        return _suscripcion_page(pending)

    @app.get("/suscripcion/conectar")
    def suscripcion_conectar():
        """Pagó y le falta conectar Mercado Libre. El enlace con ?c= (el de la vuelta de Mercado Pago o el que manda el admin)
        recupera la suscripción en otro navegador."""
        if request.args.get("c"):
            pid = _pending_from(request.args["c"])
            if pid:
                session["pending_sub"] = pid
            return redirect("/suscripcion/conectar")
        pending = _pending()
        if not pending:
            return redirect("/suscripcion")
        with Session(engine) as s:
            sub = s.get(Subscription, pending)
            ok, plan_name, days = sub.status == "authorized", billing.NAMES.get(sub.plan, ""), billing.trial_days(cfg)
        head = ("<h1>Listo, tu prueba gratis empezó</h1><p>Mercado Pago confirmó tu medio de pago para el plan %s. No se cobra nada durante %d días.</p>" % (_esc(plan_name), days)
                if ok else "<h1>Ya casi</h1><p>Estamos esperando la confirmación de Mercado Pago. Mientras tanto, ya podés conectar tu cuenta.</p>")
        return page(head + "<p><b>Último paso:</b> conectá tu cuenta de Mercado Libre para que Lumo lea tu publicidad. "
                    "Tu contraseña no pasa por Lumo.</p><a class='btn' href='/connect'>Conectar Mercado Libre</a>")

    @app.post("/suscripcion")
    def suscripcion_pagar():
        uid = _session_uid() or _pending()  # sin cuenta conectada: paga primero y conecta después
        _check_csrf()
        if not billing.enabled(cfg):
            return _suscripcion_page(uid, "El pago todavía no está disponible.", 503)
        plan = request.form.get("plan", "monthly")
        if plan not in billing.available_plans(cfg):
            return _suscripcion_page(uid, "Elegí un plan para continuar.", 400)
        email = request.form.get("email", "").strip()
        if not billing.EMAIL_RE.match(email) or len(email) > 254:
            return _suscripcion_page(uid, "Revisá el email: tiene que ser el de tu cuenta de Mercado Pago.", 400)
        with Session(engine) as s:
            if uid and access.plan(s, cfg, uid)["kind"] in ("admin", "free"):
                return redirect("/panel")
            sub = s.get(Subscription, uid) if uid else None
            if uid and uid < 0 and sub and sub.status == "authorized":
                return redirect("/suscripcion/conectar")  # ya pagó: le falta conectar
            if sub is None:
                sub = Subscription(user_id=uid or -(secrets.randbits(52) + 1))
                s.add(sub)
            if sub.status == "authorized" and sub.plan == plan and not sub.past_due_since:
                return redirect("/suscripcion")  # ya tiene ese plan al día
            back = "/suscripcion/listo" if sub.user_id > 0 else "/suscripcion/listo/" + _claim_token(sub.user_id)
            try:
                used = s.execute(select(Subscription.user_id).where(Subscription.trial_email_hash == billing.email_hash(email),
                                                                  Subscription.user_id != sub.user_id)).first()
                url = billing.create_checkout(cfg, sub, plan, email, _base_url() + back, trial_ok=used is None)
            except billing.RateError:
                log.warning("no se pudo obtener la cotización del dólar")
                return _suscripcion_page(uid, "No pudimos calcular el precio en pesos en este momento. Probá de nuevo en unos minutos.", 503)
            except billing.MPError as exc:
                log.warning("crear suscripción falló para %s: %s %s", uid, exc.status, exc.message)
                detail = "Mercado Pago respondió %s: %s" % (exc.status, exc.message or "sin detalle")
                if "test" in (exc.message or "").lower():
                    # Con credenciales de prueba, Mercado Pago solo acepta usuarios de prueba (y al revés).
                    return _suscripcion_page(uid, "Lumo está en modo de prueba de Mercado Pago: para pagar hay que usar el email de un usuario de prueba "
                                                  "de Mercado Pago, no una cuenta real.", 502, detail)
                return _suscripcion_page(uid, "Mercado Pago no pudo iniciar el pago. Revisá el email y probá de nuevo en unos minutos.", 502, detail)
            if not any(url == o or url.startswith(o + "/") for o in _checkout_origins()):
                host = url.split("/")[2] if url.count("/") >= 2 else url
                log.warning("Mercado Pago devolvió un enlace de pago fuera de los dominios permitidos: %s", host)
                return _suscripcion_page(uid, "Mercado Pago no pudo iniciar el pago. Probá de nuevo en unos minutos.", 502,
                                         "El enlace de pago es de %s, que no está en MP_CHECKOUT_ORIGINS." % host)
            audit.record(s, "sub_checkout", actor=sub.user_id if sub.user_id > 0 else None, detail=plan)
            s.commit()
            if sub.user_id < 0:
                session["pending_sub"] = sub.user_id
        return redirect(url)

    @app.get("/suscripcion/listo/<token>")
    def suscripcion_listo_sin_conectar(token):
        """Vuelta de Mercado Pago para quien pagó antes de conectar Mercado Libre."""
        pending = _pending_from(token)
        if not pending:
            return redirect("/suscripcion")
        with Session(engine) as s:
            sub = s.get(Subscription, pending)
            if sub is None:
                return redirect(_home())  # ya se pasó a una cuenta
            pid = request.args.get("preapproval_id") or sub.mp_preapproval_id
            if pid and billing.owns(sub, pid) and billing.enabled(cfg):
                try:
                    pre = billing.fetch(cfg, pid)
                except billing.MPError as exc:
                    log.warning("consultar suscripción falló: %s", exc.status)
                    pre = None
                if pre and str(pre.get("external_reference")) == str(pending):
                    _apply_preapproval(s, sub, pre)
                    s.commit()
        session["pending_sub"] = pending
        uid = _session_uid()
        if uid:  # ya tenía Mercado Libre conectado en este navegador
            with Session(engine) as s:
                _claim(s, pending, uid)
                s.commit()
            return redirect("/panel" if _current_user() else "/suscripcion")
        return redirect("/suscripcion/conectar")

    @app.get("/suscripcion/listo")
    def suscripcion_listo():
        """Mercado Pago vuelve acá después del pago, con el id de la suscripción."""
        uid = _session_uid()
        if not uid:
            return redirect("/")
        pid = request.args.get("preapproval_id", "")
        change = False
        if pid and billing.enabled(cfg):
            try:
                pre = billing.fetch(cfg, pid)
            except billing.MPError as exc:
                log.warning("consultar suscripción falló: %s", exc.status)
                pre = None
            if pre and str(pre.get("external_reference")) == str(uid):
                with Session(engine) as s:
                    sub = s.get(Subscription, uid)
                    if sub and billing.owns(sub, pid):
                        change = pid == sub.next_preapproval_id
                        _apply_preapproval(s, sub, pre)
                        s.commit()
        if change:
            return redirect("/suscripcion?estado=cambio")
        if _current_user():
            with Session(engine) as s:
                sub = s.get(Subscription, uid)
                if sub and sub.status == "authorized":
                    return redirect("/panel")
        return redirect("/suscripcion?estado=pendiente")

    @app.post("/suscripcion/cancelar")
    def suscripcion_cancelar():
        uid = _session_uid()
        if not uid:
            return redirect("/")
        _check_csrf()
        with Session(engine) as s:
            sub = s.get(Subscription, uid)
            if sub and sub.mp_preapproval_id and billing.enabled(cfg):
                try:
                    for pid in (sub.next_preapproval_id, sub.mp_preapproval_id):
                        if pid:
                            billing.cancel(cfg, pid)
                except billing.MPError as exc:
                    log.warning("cancelar suscripción falló para %s: %s", uid, exc.status)
                    return _suscripcion_page(uid, "No pudimos cancelar en Mercado Pago. Probá de nuevo o escribinos.", 502)
                sub.status = "cancelled"  # sigue entrando hasta la fecha ya paga
                sub.next_preapproval_id = sub.next_plan = sub.next_amount_ars = None
                audit.record(s, "sub_cancel", actor=uid)
                _admin_alert(s, "Suscripción cancelada", sub, ("Acceso hasta", (sub.paid_until or sub.trial_ends_at).strftime("%d/%m/%Y")))
                s.commit()
        return redirect("/suscripcion")

    def _meta_track(s, name, uid, value=None, live=None):
        """Evento de conversión para Meta. La IP solo se manda si el pedido es de la misma persona, en este momento; no se guarda."""
        if not meta.enabled(cfg) or uid < 0:  # sin cuenta conectada todavía: se manda al conectar
            return
        acc, sub = s.get(Account, uid), s.get(Subscription, uid)
        email = (acc.email if acc else None) or (sub.payer_email if sub else None)
        if live is None:
            live = has_request_context() and session.get("uid") == uid
        ip = request.remote_addr if live else None
        meta.track(cfg, s, name, uid, email=email, value=value, ip=ip, source_url=cfg.get("SITE_URL") or _base_url())

    def _tagged(email, tag):
        """En Gmail, nombre+etiqueta@gmail.com llega a la misma casilla y se puede filtrar a una etiqueta."""
        user, at, domain = (email or "").partition("@")
        return "%s+%s@%s" % (user, tag, domain) if at and domain.lower() in ("gmail.com", "googlemail.com") and "+" not in user else email

    def _admin_alert(s, title, sub, *rows, once=None):
        """Mail a quien administra Lumo cuando alguien empieza la prueba, conecta, paga, falla un cobro o cancela.
        once: referencia para mandarlo una sola vez (Mercado Pago puede repetir sus avisos)."""
        to = cfg.get("ADMIN_NOTIFY_EMAIL") or _tagged(cfg.get("CONTACT_EMAIL"), "suscripciones")
        if not to or not notify.enabled(cfg):
            return
        if once and s.get(Notice, (sub.user_id, "adm", once[:64])):
            return
        acc = s.get(Account, sub.user_id) if sub.user_id > 0 else None
        info = [("Email de pago", sub.payer_email), ("Email de Mercado Libre", acc.email if acc and acc.email != sub.payer_email else None),
                ("Cuenta de Mercado Libre", sub.user_id if sub.user_id > 0 else "todavía no la conectó"),
                ("Plan", billing.NAMES.get(sub.plan, "").capitalize()), ("Monto", notify.money(sub.amount_ars) if sub.amount_ars else None)]
        subject, text, html = notify.admin_mail(title, list(rows) + info, _base_url() + "/admin")
        try:
            notify.send_mail(cfg, to, subject, text, html)
        except Exception as exc:  # un aviso que no sale no puede frenar el cobro ni el ingreso
            log.warning("aviso al administrador falló: %s", notify.why(exc))
            return
        if once:
            notify._mark(s, sub.user_id, "adm", once[:64], utcnow())

    def _apply_preapproval(s, sub, pre):
        before, had_trial = (sub.status, sub.plan), sub.trial_started_at
        billing.apply(cfg, sub, pre)
        if sub.trial_started_at and not had_trial:
            sub.trial_email_hash = billing.email_hash(sub.payer_email)  # ese email ya no tiene otra prueba gratis
            audit.record(s, "trial_start", target=sub.user_id, detail=sub.plan)
            _meta_track(s, "StartTrial", sub.user_id, billing.price_usd(cfg, sub.plan or "monthly"))
            _admin_alert(s, "Nueva prueba gratis", sub, ("Primer cobro", sub.trial_ends_at.strftime("%d/%m/%Y")))
        if (sub.status, sub.plan) != before:
            audit.record(s, "sub_" + sub.status, target=sub.user_id, detail=sub.plan)
            if before[0] == "authorized" and sub.status in ("cancelled", "paused"):
                _admin_alert(s, "Suscripción cancelada" if sub.status == "cancelled" else "Suscripción pausada en Mercado Pago", sub,
                             ("Acceso hasta", sub.paid_until.strftime("%d/%m/%Y") if sub.paid_until else None))

    def _billing_notices(s, sub) -> int:
        """Avisos por email de la suscripción: cobro rechazado, acceso suspendido y prueba por terminar. Cada uno se manda una vez."""
        if not notify.enabled(cfg) or sub.user_id < 0:
            return 0
        p = access.plan(s, cfg, sub.user_id)
        if p["kind"] in ("admin", "free", "none"):
            return 0
        acc = s.get(Account, sub.user_id)
        to = (acc.email if acc else None) or sub.payer_email
        if not to:
            return 0
        now, kind, ref, args = utcnow(), None, None, {}
        if sub.past_due_since:
            ref = sub.past_due_since.strftime("%Y-%m-%d")
            if p.get("past_due"):
                kind, args = "pago", {"until": p["grace_ends"]}
            else:
                kind = "baja"
        elif p["kind"] == "trial" and p["days"] <= 3:  # se viene el primer cobro: que no sea una sorpresa
            price = billing.offer(cfg).get("annual" if sub.plan == "annual" else "monthly")
            kind, ref, args = "prueba", sub.trial_ends_at.strftime("%Y-%m-%d"), {"days": p["days"], "until": sub.trial_ends_at,
                                                                               "price": price, "plan": billing.NAMES.get(sub.plan)}
        if not kind or s.get(Notice, (sub.user_id, kind, ref)):
            return 0
        subject, text, html = notify.billing_mail(kind, _base_url() + "/suscripcion", **args)
        try:
            notify.send_mail(cfg, to, subject, text, html)
        except Exception as exc:  # el correo no puede frenar el registro del cobro
            log.warning("aviso de suscripción a %s falló: %s", sub.user_id, notify.why(exc))
            return 0
        notify._mark(s, sub.user_id, kind, ref, now)
        return 1

    def _billing_tick() -> dict:
        """Chequeo diario: sincroniza cada suscripción con Mercado Pago, actualiza el monto en pesos y manda los avisos."""
        out = {"suscripciones": 0, "montos": 0, "avisos": 0, "errores": 0}
        with Session(engine) as s:
            ids = [u for (u,) in s.execute(select(Subscription.user_id)).all()]
        for uid in ids:
            try:
                with Session(engine) as s:
                    sub = s.get(Subscription, uid)
                    if uid < 0 and sub.status in ("new", "pending") and sub.created_at < utcnow() - timedelta(days=3):
                        billing.end(cfg, sub)  # empezó a pagar sin conectar y lo dejó: no queda nada que guardar
                        s.delete(sub)
                        s.commit()
                        continue
                    if billing.enabled(cfg) and sub.mp_preapproval_id and sub.status in billing.LIVE:
                        out["suscripciones"] += 1
                        _apply_preapproval(s, sub, billing.fetch(cfg, sub.mp_preapproval_id))
                        if sub.next_preapproval_id:
                            _apply_preapproval(s, sub, billing.fetch(cfg, sub.next_preapproval_id))
                        if billing.refresh_amount(cfg, sub):
                            out["montos"] += 1
                    out["avisos"] += _billing_notices(s, sub)
                    s.commit()
            except Exception as exc:  # una suscripción con problemas no frena a las demás
                out["errores"] += 1
                log.warning("chequeo de la suscripción de %s falló: %s", uid, type(exc).__name__, exc_info=True)
        return out

    @app.post("/webhooks/mercadopago")
    def webhook_mp():
        """Avisos de Mercado Pago. No se confía en el contenido: se vuelve a consultar a Mercado Pago con el token de Lumo."""
        body = request.get_json(silent=True) or {}
        kind = body.get("type") or request.args.get("type") or request.args.get("topic") or ""
        data_id = str((body.get("data") or {}).get("id") or request.args.get("data.id") or request.args.get("id") or "")
        if not billing.valid_signature(cfg, request.headers, data_id):
            return _json({"error": "firma"}, 401)
        if not data_id or not billing.enabled(cfg):
            return _json({"ok": True})
        try:
            if kind in ("subscription_preapproval", "preapproval"):
                pre = billing.fetch(cfg, data_id)
                ref = str(pre.get("external_reference") or "")
                with Session(engine) as s:
                    # Por el id de Mercado Pago: quien pagó antes de conectar quedó con una referencia provisoria que ya no es su cuenta.
                    sub = s.execute(select(Subscription).where(or_(Subscription.mp_preapproval_id == data_id,
                                                                   Subscription.next_preapproval_id == data_id))).scalars().first()
                    if sub is None and re.fullmatch(r"-?\d{1,19}", ref):
                        sub = s.get(Subscription, int(ref))
                        sub = sub if sub and sub.mp_preapproval_id is None else None
                    if sub:
                        _apply_preapproval(s, sub, pre)
                        s.commit()
            elif kind in ("subscription_authorized_payment", "authorized_payment"):
                pay = billing.fetch_payment(cfg, data_id)
                pid = str(pay.get("preapproval_id") or "")
                with Session(engine) as s:
                    sub = s.execute(select(Subscription).where(Subscription.mp_preapproval_id == pid)).scalars().first() if pid else None
                    if sub:
                        result = billing.apply_payment(sub, pay)
                        if result:
                            audit.record(s, "sub_pago_" + ("ok" if result == "ok" else "rechazado"), target=sub.user_id)
                            _admin_alert(s, "Cobro aprobado" if result == "ok" else "Cobro rechazado", sub, once="pago-" + data_id)
                            if result == "ok":
                                _meta_track(s, "Subscribe", sub.user_id, billing.price_usd(cfg, sub.plan or "monthly"))
                            _apply_preapproval(s, sub, billing.fetch(cfg, pid))
                            _billing_notices(s, sub)
                        s.commit()
        except billing.MPError as exc:
            log.warning("webhook: consultar a Mercado Pago falló: %s", exc.status)
            return _json({"error": "mp"}, 502)  # Mercado Pago reintenta
        return _json({"ok": True})

    return app


PANEL_HTML = (Path(__file__).parent / "panel.html").read_text(encoding="utf-8")


def _grandfather(engine) -> None:
    """Al estrenar el control de acceso, las cuentas que ya estaban conectadas siguen entrando."""
    with Session(engine) as s:
        for (uid,) in s.execute(select(Account.user_id)).all():
            s.add(Access(user_id=uid, note="Conectada antes de las invitaciones"))
        s.commit()


def _widen_scope(engine) -> None:
    """La primera versión creó scope como varchar(255) y Mercado Libre devuelve listas más largas."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE account ALTER COLUMN scope TYPE TEXT"))


def _add_email_column(engine) -> None:
    """La tabla account ya existía sin las columnas de email (y después sin el email y el apodo de Mercado Libre)."""
    have = {c["name"] for c in inspect(engine).get_columns("account")}
    with engine.begin() as conn:
        for col in ("email", "ml_email", "ml_nickname"):
            if col not in have:
                conn.execute(text("ALTER TABLE account ADD COLUMN %s TEXT" % col))
        if "trial_email_hash" not in {c["name"] for c in inspect(engine).get_columns("subscription")}:
            conn.execute(text("ALTER TABLE subscription ADD COLUMN trial_email_hash VARCHAR(64)"))
            # Las pruebas que ya se usaron también cuentan: se guarda el resumen de su email de pago.
            for uid, mail in conn.execute(text("SELECT user_id, payer_email FROM subscription WHERE trial_started_at IS NOT NULL AND payer_email IS NOT NULL")).all():
                conn.execute(text("UPDATE subscription SET trial_email_hash = :h WHERE user_id = :u"), {"h": billing.email_hash(mail), "u": uid})


def _esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _result_body(cfg: dict, tok: dict, user_id: int):
    """Devuelve (html, ok). ok es True cuando se puede pasar directo al panel."""
    lines = ["<h1>¡Listo, tu cuenta está conectada!</h1><p class='ok'>Lumo ya puede mostrarte cómo van tus publicidades de Mercado Libre.</p>"]
    has_refresh = bool(tok.get("refresh_token"))
    if not has_refresh:
        lines.append("<p class='bad'>La conexión quedó a medias: Mercado Libre no nos dio permiso para mantenerla activa, así que se vencería en unas horas.</p><p>Si ves este mensaje, avisanos y lo resolvemos.</p>")
    try:
        found = ml.advertisers(cfg, tok["access_token"])
    except ml.MLError as exc:
        if exc.status == 404:
            lines.append("<p class='bad'>Todavía no tenés Publicidad activada en Mercado Libre.</p><p>Para activarla entrá a Mercado Libre, andá a <b>Mi perfil</b> y después a <b>Publicidad</b>. Cuando esté lista, volvé acá y conectá tu cuenta de nuevo.</p>")
        elif exc.status in (401, 403):
            lines.append("<p class='bad'>Mercado Libre no nos dejó ver tus publicidades con esta cuenta.</p><p>Probá conectar de nuevo con la cuenta principal de tu negocio. Si sigue igual, escribinos.</p>")
        else:
            lines.append("<p class='bad'>No pudimos traer tus publicidades en este momento.</p><p>Probá de nuevo en unos minutos. Si sigue pasando, escribinos.</p>")
        return "".join(lines), False
    if not found:
        lines.append("<p>Tu cuenta está conectada, pero todavía no encontramos publicidades en ella.</p><p>Cuando crees tu primera campaña en Mercado Libre, va a aparecer acá.</p>")
        return "".join(lines), False
    lines.append("<p>Encontramos estas cuentas de publicidad:</p><ul>")
    for a in found:
        lines.append("<li><b>%s</b></li>" % _esc(a.get("advertiser_name", "")))
    lines.append("</ul>")
    if not has_refresh:
        lines.append("<a class='btn' href='/panel'>Entrar igual al panel</a>")
    return "".join(lines), has_refresh
