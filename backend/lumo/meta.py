"""Medición de los anuncios de Meta (Facebook e Instagram): Píxel en la portada y API de Conversiones desde el servidor.

El Píxel solo carga en la portada pública. Dentro de la app (panel, suscripción, admin) no hay ningún script de Meta: los
eventos de conversión los manda el servidor, con el email y el id de cuenta cifrados con SHA-256 como pide Meta.

Eventos:
- Lead: una cuenta nueva conecta Mercado Libre por primera vez.
- StartTrial: Mercado Pago confirma el medio de pago y empieza la prueba gratis.
- Subscribe: primer cobro aprobado.

Sin META_PIXEL_ID y META_CAPI_TOKEN no se manda nada. Un envío fallido nunca frena a la app.
"""
import hashlib
import logging
import re
import threading
import time

import requests

from .models import AdClick, utcnow

log = logging.getLogger("lumo.meta")

TIMEOUT = 8
FBP_RE = re.compile(r"^fb\.\d\.\d{10,14}\.\d{1,20}$")
FBC_RE = re.compile(r"^fb\.\d\.\d{10,14}\.[A-Za-z0-9_\-]{1,500}$")
EVENTS = ("Lead", "StartTrial", "Subscribe")


def pixel_id(cfg: dict) -> str:
    pid = (cfg.get("META_PIXEL_ID") or "").strip()
    return pid if pid.isdigit() else ""


def enabled(cfg: dict) -> bool:
    return bool(pixel_id(cfg) and cfg.get("META_CAPI_TOKEN"))


def clean_fbp(value):
    value = (value or "").strip()
    return value if FBP_RE.match(value) else None


def clean_fbc(value):
    value = (value or "").strip()
    return value if FBC_RE.match(value) else None


def fbc_from_click(fbclid):
    """El formato que usa Meta para el clic de un anuncio, armado desde el parámetro fbclid de la dirección."""
    fbclid = (fbclid or "").strip()
    return clean_fbc("fb.1.%d.%s" % (int(time.time() * 1000), fbclid)) if fbclid else None


def _sha(value) -> str:
    return hashlib.sha256(str(value).strip().lower().encode("utf-8")).hexdigest()


def remember(db, user_id: int, fbc=None, fbp=None, user_agent=None) -> AdClick:
    """Guarda de qué anuncio vino la cuenta (si vino de uno) y el navegador, para atribuir la prueba y el primer cobro."""
    row = db.get(AdClick, int(user_id))
    if row is None:
        row = AdClick(user_id=int(user_id), sent="")
        db.add(row)
    row.fbc = clean_fbc(fbc) or row.fbc
    row.fbp = clean_fbp(fbp) or row.fbp
    if user_agent:
        row.user_agent = user_agent[:400]
    return row


def build_event(cfg: dict, name: str, user_id: int, email=None, row=None, value=None, ip=None, source_url=None) -> dict:
    """Arma un evento de la API de Conversiones. Sin navegador conocido se manda como "system_generated"."""
    ud = {"external_id": [_sha(user_id)], "country": [_sha("ar")]}
    if email:
        ud["em"] = [_sha(email)]
    if row is not None:
        if row.fbc:
            ud["fbc"] = row.fbc
        if row.fbp:
            ud["fbp"] = row.fbp
    ua = row.user_agent if row is not None else None
    event = {"event_name": name, "event_time": int(time.time()), "event_id": "%s-%s" % (name.lower(), user_id), "user_data": ud}
    if ua:
        ud["client_user_agent"] = ua
        if ip:
            ud["client_ip_address"] = ip
        event["action_source"] = "website"
        if source_url:
            event["event_source_url"] = source_url
    else:
        event["action_source"] = "system_generated"
    if value:
        event["custom_data"] = {"currency": "USD", "value": round(float(value), 2)}
    return event


def track(cfg: dict, db, name: str, user_id: int, email=None, value=None, ip=None, source_url=None) -> bool:
    """Manda un evento una sola vez por cuenta. Devuelve True si quedó en camino. Hay que hacer commit de la sesión después."""
    if name not in EVENTS or not enabled(cfg):
        return False
    row = db.get(AdClick, int(user_id))
    if row is None:
        row = remember(db, user_id)
    sent = set(filter(None, (row.sent or "").split(",")))
    if name in sent:
        return False
    event = build_event(cfg, name, user_id, email, row, value, ip, source_url)
    row.sent = ",".join(sorted(sent | {name}))
    row.updated_at = utcnow()
    _dispatch(cfg, event)
    return True


def _payload(cfg: dict, event: dict) -> dict:
    body = {"data": [event]}
    if cfg.get("META_TEST_EVENT_CODE"):
        body["test_event_code"] = cfg["META_TEST_EVENT_CODE"]  # para ver los eventos en "Probar eventos" sin ensuciar los datos reales
    return body


def send(cfg: dict, event: dict) -> bool:
    url = "https://graph.facebook.com/%s/%s/events" % (cfg.get("META_API_VERSION") or "v23.0", pixel_id(cfg))
    try:
        resp = requests.post(url, json=_payload(cfg, event), params={"access_token": cfg["META_CAPI_TOKEN"]}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.warning("Meta: no se pudo enviar %s: %s", event["event_name"], type(exc).__name__)
        return False
    if resp.status_code >= 400:
        log.warning("Meta: %s rechazado (%s): %s", event["event_name"], resp.status_code, resp.text[:300])
        return False
    return True


def _dispatch(cfg: dict, event: dict) -> None:
    """Envía en segundo plano: la respuesta de Meta no demora a quien está usando Lumo."""
    threading.Thread(target=send, args=(cfg, event), daemon=True).start()
