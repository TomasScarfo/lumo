"""Prueba gratis y suscripción mensual con Mercado Pago (suscripciones sin plan asociado, una por cuenta)."""
import hashlib
import hmac
import math
import re
from datetime import datetime, timedelta, timezone

import requests

from .models import Subscription, utcnow

TIMEOUT = 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MPError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__("%s %s" % (status, message))
        self.status = status
        self.message = message


def trial_days(cfg: dict) -> int:
    raw = str(cfg.get("TRIAL_DAYS") or "14")
    return int(raw) if raw.isdigit() else 14


def price(cfg: dict):
    try:
        value = float(str(cfg.get("PLAN_PRICE") or "").replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


def price_label(cfg: dict):
    value = price(cfg)
    if value is None:
        return None
    text = "{:,.0f}".format(value).replace(",", ".") if value == int(value) else "{:,.2f}".format(value).replace(",", "X").replace(".", ",").replace("X", ".")
    return "$%s %s" % (text, cfg.get("PLAN_CURRENCY") or "ARS")


def enabled(cfg: dict) -> bool:
    """El cobro está activo solo si hay token de Mercado Pago y precio."""
    return bool(cfg.get("MP_ACCESS_TOKEN")) and price(cfg) is not None


def start_trial(db, cfg: dict, user_id: int) -> Subscription:
    sub = Subscription(user_id=int(user_id), status="trial", trial_ends_at=utcnow() + timedelta(days=trial_days(cfg)))
    db.add(sub)
    return sub


def days_left(when) -> int:
    return max(0, math.ceil((when - utcnow()).total_seconds() / 86400))


# ---------- Mercado Pago ----------
def _request(cfg: dict, method: str, path: str, body: dict = None) -> dict:
    resp = requests.request(method, (cfg.get("MP_API_BASE") or "https://api.mercadopago.com") + path, json=body, timeout=TIMEOUT,
                            headers={"Authorization": "Bearer " + cfg["MP_ACCESS_TOKEN"], "Content-Type": "application/json"})
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code not in (200, 201):
        raise MPError(resp.status_code, str(data.get("message", "")) if isinstance(data, dict) else "")
    return data if isinstance(data, dict) else {}


def _mp_date(when: datetime) -> str:
    return when.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def create_checkout(cfg: dict, sub: Subscription, email: str, back_url: str) -> str:
    """Crea la suscripción pendiente en Mercado Pago y devuelve el enlace donde la persona carga su medio de pago.
    Si todavía le quedan días de prueba, el primer cobro se hace cuando termina la prueba."""
    recurring = {"frequency": 1, "frequency_type": "months", "transaction_amount": price(cfg), "currency_id": cfg.get("PLAN_CURRENCY") or "ARS"}
    if sub.trial_ends_at > utcnow() + timedelta(minutes=10):
        recurring["start_date"] = _mp_date(sub.trial_ends_at)
    data = _request(cfg, "POST", "/preapproval", {
        "reason": "Lumo · suscripción mensual",
        "external_reference": str(sub.user_id),
        "payer_email": email,
        "auto_recurring": recurring,
        "back_url": back_url,
        "status": "pending",
    })
    sub.mp_preapproval_id = str(data.get("id") or "") or None
    sub.payer_email = email
    if not data.get("init_point"):
        raise MPError(502, "sin init_point")
    return data["init_point"]


def fetch(cfg: dict, preapproval_id: str) -> dict:
    return _request(cfg, "GET", "/preapproval/%s" % preapproval_id)


def cancel(cfg: dict, preapproval_id: str) -> dict:
    return _request(cfg, "PUT", "/preapproval/%s" % preapproval_id, {"status": "cancelled"})


def apply(sub: Subscription, pre: dict) -> None:
    """Copia a la base lo que informa Mercado Pago sobre la suscripción."""
    status = pre.get("status")
    if status in ("pending", "authorized", "paused", "cancelled"):
        sub.status = status
    sub.mp_preapproval_id = str(pre.get("id") or sub.mp_preapproval_id or "") or None
    nxt = _parse_date(pre.get("next_payment_date"))
    if status == "authorized" and nxt:
        sub.paid_until = max(nxt, sub.paid_until or nxt)


def valid_signature(cfg: dict, headers, data_id: str) -> bool:
    """Verifica la firma x-signature de las notificaciones de Mercado Pago. Sin MP_WEBHOOK_SECRET no se verifica:
    igual Lumo nunca confía en el contenido de la notificación y vuelve a consultar la suscripción a Mercado Pago."""
    secret = cfg.get("MP_WEBHOOK_SECRET")
    if not secret:
        return True
    parts = dict(p.strip().split("=", 1) for p in (headers.get("x-signature") or "").split(",") if "=" in p)
    ts, v1 = parts.get("ts"), parts.get("v1")
    if not ts or not v1:
        return False
    manifest = "id:%s;request-id:%s;ts:%s;" % (data_id.lower() if data_id.isalnum() else data_id, headers.get("x-request-id", ""), ts)
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)
