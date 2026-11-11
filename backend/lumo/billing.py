"""Prueba gratis y suscripción con Mercado Pago: plan mensual y anual, con precio en dólares y cobro en pesos.

Mercado Pago cobra en pesos. El precio se fija en dólares y se convierte con la cotización del día: al suscribirse
y, después, en cada chequeo diario, que actualiza el monto de las suscripciones activas antes de su próximo cobro.
Si un cobro es rechazado, la cuenta sigue entrando durante los días de gracia; después se suspende, sin borrar nada.
"""
import hashlib
import hmac
import math
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from .models import Subscription, utcnow

TIMEOUT = 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PLANS = ("monthly", "annual")
MONTHS = {"monthly": 1, "annual": 12}
NAMES = {"monthly": "mensual", "annual": "anual"}
RATE_TTL = 3600           # segundos que se reutiliza la cotización
RATE_TOLERANCE = 0.01     # no se toca el monto en Mercado Pago por diferencias menores al 1 %
LIVE = ("pending", "authorized", "paused")  # estados en los que la suscripción sigue existiendo en Mercado Pago

_rate_cache = {}


class MPError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__("%s %s" % (status, message))
        self.status = status
        self.message = message


class RateError(Exception):
    """No se pudo obtener la cotización del dólar."""


# ---------- Planes y precios ----------
def _int(cfg: dict, key: str, default: int) -> int:
    raw = str(cfg.get(key) or default)
    return int(raw) if raw.isdigit() else default


def trial_days(cfg: dict) -> int:
    return _int(cfg, "TRIAL_DAYS", 14)


def grace_days(cfg: dict) -> int:
    return _int(cfg, "GRACE_DAYS", 7)


def _num(raw):
    try:
        value = float(str(raw or "").replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


def price_usd(cfg: dict, plan: str):
    return _num(cfg.get("PLAN_PRICE_ANNUAL_USD" if plan == "annual" else "PLAN_PRICE_USD"))


def usd_label(value: float) -> str:
    text = "%d" % value if value == int(value) else ("%.2f" % value).replace(".", ",")
    return "US$" + text


def saving(cfg: dict):
    """Cuánto se ahorra con el plan anual frente a pagar doce meses: (dólares, porcentaje). None si no hay ahorro."""
    monthly, annual = price_usd(cfg, "monthly"), price_usd(cfg, "annual")
    if not monthly or not annual or annual >= monthly * 12:
        return None
    full = monthly * 12
    return round(full - annual, 2), int(round((1 - annual / full) * 100))


def offer(cfg: dict) -> dict:
    """Lo que muestran la portada y la página de suscripción."""
    monthly, annual, save = price_usd(cfg, "monthly"), price_usd(cfg, "annual"), saving(cfg)
    return {"monthly": usd_label(monthly) if monthly else None, "annual": usd_label(annual) if annual else None,
            "saving_pct": save[1] if save else None, "saving_usd": usd_label(save[0]) if save else None}


def enabled(cfg: dict) -> bool:
    """El cobro está activo solo si hay token de Mercado Pago y precio mensual."""
    return bool(cfg.get("MP_ACCESS_TOKEN")) and price_usd(cfg, "monthly") is not None


def available_plans(cfg: dict) -> tuple:
    return tuple(p for p in PLANS if price_usd(cfg, p))


# ---------- Cotización ----------
def rate(cfg: dict) -> float:
    """Pesos por dólar. USD_ARS_RATE fija un valor a mano; si no, se consulta USD_RATE_URL (campo "venta")."""
    fixed = _num(cfg.get("USD_ARS_RATE"))
    if fixed:
        return fixed
    url = cfg.get("USD_RATE_URL") or ""
    hit = _rate_cache.get(url)
    if hit and time.time() - hit[1] < RATE_TTL:
        return hit[0]
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        value = _num(resp.json().get("venta")) if resp.status_code == 200 else None
    except (requests.RequestException, ValueError, AttributeError):
        value = None
    if not value:
        if hit:  # si el servicio no responde, sirve la última cotización conocida
            return hit[0]
        raise RateError(url)
    _rate_cache[url] = (value, time.time())
    return value


def ars_amount(cfg: dict, plan: str) -> float:
    return round(price_usd(cfg, plan) * rate(cfg), 2)


# ---------- Prueba gratis ----------
def trial_available(sub) -> bool:
    """La prueba gratis es una sola por cuenta y empieza cuando Mercado Pago confirma el medio de pago."""
    return sub is None or sub.trial_started_at is None


def in_trial(sub) -> bool:
    return sub.trial_started_at is not None and sub.trial_ends_at > utcnow()


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


def create_checkout(cfg: dict, sub: Subscription, plan: str, email: str, back_url: str) -> str:
    """Crea la suscripción pendiente en Mercado Pago y devuelve el enlace donde la persona carga su medio de pago.

    Quien nunca usó la prueba gratis no paga nada los primeros días: el primer cobro se agenda para cuando termina la prueba,
    que empieza a correr recién cuando Mercado Pago confirma el medio de pago. En los demás casos, el primer cobro se hace
    cuando termina lo que ya tiene (lo que queda de prueba o el período pago del plan anterior).
    Si la cuenta ya tiene una suscripción activa, la nueva queda "en espera" (next_*) y reemplaza a la anterior
    recién cuando Mercado Pago la autoriza: así nadie se queda sin plan por abandonar el pago a mitad de camino."""
    amount = ars_amount(cfg, plan)
    recurring = {"frequency": MONTHS[plan], "frequency_type": "months", "transaction_amount": amount, "currency_id": "ARS"}
    now = utcnow()
    replacing = sub.status == "authorized" and bool(sub.mp_preapproval_id)
    if trial_available(sub) and not replacing:
        sub.trial_ends_at = now + timedelta(days=trial_days(cfg))  # provisorio: vale cuando Mercado Pago autoriza
        starts = [sub.trial_ends_at]
    else:
        starts = [d for d in (sub.trial_ends_at if in_trial(sub) else None, None if sub.past_due_since else sub.paid_until) if d and d > now + timedelta(minutes=10)]
    if starts:
        recurring["start_date"] = _mp_date(max(starts))
    data = _request(cfg, "POST", "/preapproval", {
        "reason": "Lumo · plan %s" % NAMES[plan],
        "external_reference": str(sub.user_id),
        "payer_email": email,
        "auto_recurring": recurring,
        "back_url": back_url,
        "status": "pending",
    })
    pid = str(data.get("id") or "")
    if not pid or not data.get("init_point"):
        raise MPError(502, "respuesta incompleta")
    sub.payer_email = email
    if replacing:
        sub.next_preapproval_id, sub.next_plan, sub.next_amount_ars = pid, plan, amount
    else:
        sub.mp_preapproval_id, sub.plan, sub.amount_ars, sub.status = pid, plan, amount, "pending"
        sub.next_preapproval_id = sub.next_plan = sub.next_amount_ars = None
    return data["init_point"]


def fetch(cfg: dict, preapproval_id: str) -> dict:
    return _request(cfg, "GET", "/preapproval/%s" % preapproval_id)


def fetch_payment(cfg: dict, payment_id: str) -> dict:
    """Un cobro de una suscripción (authorized_payment): dice a qué suscripción pertenece y si se aprobó o se rechazó."""
    return _request(cfg, "GET", "/authorized_payments/%s" % payment_id)


def cancel(cfg: dict, preapproval_id: str) -> dict:
    return _request(cfg, "PUT", "/preapproval/%s" % preapproval_id, {"status": "cancelled"})


def owns(sub: Subscription, preapproval_id: str) -> bool:
    return bool(preapproval_id) and preapproval_id in (sub.mp_preapproval_id, sub.next_preapproval_id)


def apply(cfg: dict, sub: Subscription, pre: dict) -> None:
    """Copia a la base lo que informa Mercado Pago sobre una suscripción de esta cuenta."""
    pid, status = str(pre.get("id") or ""), pre.get("status")
    if pid and pid == sub.next_preapproval_id:
        if status == "authorized":  # el plan nuevo quedó confirmado: reemplaza al anterior
            old = sub.mp_preapproval_id
            sub.mp_preapproval_id, sub.plan, sub.amount_ars = pid, sub.next_plan, sub.next_amount_ars
            sub.next_preapproval_id = sub.next_plan = sub.next_amount_ars = None
            sub.status, sub.past_due_since = "authorized", None
            if old and old != pid:
                try:
                    cancel(cfg, old)
                except MPError:
                    pass  # el chequeo diario no la vuelve a mirar; si quedó viva, Mercado Pago avisa y se ve en /admin
        elif status == "cancelled":
            sub.next_preapproval_id = sub.next_plan = sub.next_amount_ars = None
        return
    if sub.mp_preapproval_id and pid != sub.mp_preapproval_id:
        return
    if status == "authorized" and sub.status == "pending":
        sub.past_due_since = None  # volvió a suscribirse después de un cobro rechazado
    if status == "authorized" and sub.trial_started_at is None:
        sub.trial_started_at = utcnow()  # medio de pago confirmado: acá empieza la prueba gratis
    if status in ("pending", "authorized", "paused", "cancelled"):
        sub.status = status
    sub.mp_preapproval_id = pid or sub.mp_preapproval_id
    nxt = _parse_date(pre.get("next_payment_date"))
    if status == "authorized" and nxt:
        sub.paid_until = max(nxt, sub.paid_until or nxt)


def apply_payment(sub: Subscription, payment: dict):
    """Registra el resultado de un cobro. Devuelve "ok", "rejected" o None si todavía no hay resultado."""
    inner = payment.get("payment") if isinstance(payment.get("payment"), dict) else {}
    result, state = inner.get("status"), payment.get("status")
    if result == "approved":
        sub.past_due_since = None
        return "ok"
    if result == "rejected" or state == "recycling":  # recycling: Mercado Pago está reintentando el cobro
        if sub.past_due_since is None:
            sub.past_due_since = utcnow()
        return "rejected"
    return None


def grace_end(cfg: dict, sub: Subscription):
    return sub.past_due_since + timedelta(days=grace_days(cfg)) if sub.past_due_since else None


def refresh_amount(cfg: dict, sub: Subscription) -> bool:
    """Lleva el monto en pesos de una suscripción activa a la cotización de hoy. Devuelve True si lo cambió."""
    if sub.status != "authorized" or not sub.mp_preapproval_id or sub.plan not in PLANS or not price_usd(cfg, sub.plan):
        return False
    amount = ars_amount(cfg, sub.plan)
    if sub.amount_ars and abs(amount - sub.amount_ars) / sub.amount_ars < RATE_TOLERANCE:
        return False
    _request(cfg, "PUT", "/preapproval/%s" % sub.mp_preapproval_id, {"auto_recurring": {"transaction_amount": amount, "currency_id": "ARS"}})
    sub.amount_ars = amount
    return True


def end(cfg: dict, sub: Subscription, keep_email: bool = False) -> None:
    """Da de baja la suscripción en Mercado Pago y deja solo la marca de que la prueba gratis ya se usó."""
    if enabled(cfg):
        for pid in (sub.mp_preapproval_id if sub.status in LIVE else None, sub.next_preapproval_id):
            if pid:
                try:
                    cancel(cfg, pid)
                except MPError:
                    pass
    sub.status, sub.paid_until, sub.past_due_since = "cancelled", None, None
    if not keep_email:
        sub.payer_email = None
    sub.next_preapproval_id = sub.next_plan = sub.next_amount_ars = None
    sub.trial_ends_at = min(sub.trial_ends_at or utcnow(), utcnow())


def monthly_revenue_usd(cfg: dict, subs) -> float:
    """Ingreso mensual recurrente de las suscripciones que están pagando, en dólares (el anual cuenta un doceavo)."""
    total = 0.0
    for sub in subs:
        if sub.status == "authorized" and sub.plan in PLANS and not sub.past_due_since and not in_trial(sub):  # en la prueba todavía no paga
            total += (price_usd(cfg, sub.plan) or 0) / MONTHS[sub.plan]
    return round(total, 2)


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
