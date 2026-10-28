"""Guardado y renovación de tokens.

El refresh token de Mercado Libre es de un solo uso: cada renovación devuelve uno nuevo y el anterior deja de servir.
Por eso la renovación corre dentro de una transacción con la fila de la cuenta bloqueada (un proceso por cuenta a la vez)
y el token nuevo se guarda antes de usar el access token.
"""
from datetime import timedelta

from sqlalchemy import select

from . import ml
from .crypto import decrypt, encrypt
from .models import Account, utcnow

# Se renueva un poco antes de que venza para no depender del reloj exacto.
MARGIN = timedelta(minutes=5)


class NeedsReconnect(Exception):
    """La cuenta revocó el permiso o el refresh token ya no sirve: hay que volver a autorizar."""


def save_tokens(session, cfg: dict, user_id: int, tok: dict) -> Account:
    key = cfg["ENCRYPTION_KEY"]
    expires_in = int(tok.get("expires_in") or 0)
    acc = session.get(Account, user_id) or Account(user_id=user_id)
    acc.access_token = encrypt(key, tok["access_token"])
    # Si Mercado Libre no devuelve refresh token (falta el acceso offline), se deja vacío y se avisa en pantalla.
    acc.refresh_token = encrypt(key, tok["refresh_token"]) if tok.get("refresh_token") else None
    acc.expires_at = utcnow() + timedelta(seconds=expires_in)
    acc.scope = tok.get("scope")
    acc.status = "connected"
    session.add(acc)
    return acc


def valid_access_token(session, cfg: dict, user_id: int) -> str:
    acc = session.execute(select(Account).where(Account.user_id == user_id).with_for_update()).scalar_one_or_none()
    if acc is None or acc.status != "connected":
        raise NeedsReconnect()
    key = cfg["ENCRYPTION_KEY"]
    if acc.expires_at - utcnow() > MARGIN:
        return decrypt(key, acc.access_token)
    if not acc.refresh_token:
        acc.status = "needs_reconnect"
        session.commit()
        raise NeedsReconnect()
    try:
        tok = ml.refresh(cfg, decrypt(key, acc.refresh_token))
    except ml.MLError as exc:
        if exc.code == "invalid_grant":
            acc.status = "needs_reconnect"
            session.commit()
            raise NeedsReconnect() from exc
        raise
    save_tokens(session, cfg, user_id, tok)
    session.commit()  # el token nuevo queda guardado antes de usarse
    return tok["access_token"]
