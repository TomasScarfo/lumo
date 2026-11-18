"""Usuarios de Lumo: se registran con su email y entran con un enlace de un solo uso (sin contraseña).
Después conectan su cuenta de Mercado Libre. Todo lo que ya existía (datos, suscripción, accesos) sigue guardado por el id
de la cuenta de Mercado Libre; el usuario de Lumo solo la lleva asociada.
"""
import hashlib
import re
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import LoginToken, User, utcnow

TOKEN_MINUTES = 30
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,}$")


def normalize_email(raw):
    """El email en minúsculas y sin espacios, o None si no parece un email."""
    if not isinstance(raw, str):
        return None
    email = raw.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email) or ".." in email:
        return None
    return email


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_login_token(s: Session, email: str, plan=None, invite=None, now=None) -> str:
    """Crea un enlace de un solo uso para ese email y devuelve el valor que va en el mail (en la base queda su hash)."""
    now = now or utcnow()
    token = secrets.token_urlsafe(32)
    s.add(LoginToken(token_hash=_hash(token), email=email, plan=plan, invite=invite, created_at=now,
                     expires_at=now + timedelta(minutes=TOKEN_MINUTES)))
    return token


def peek_login_token(s: Session, token: str, now=None):
    """El enlace si todavía sirve (existe, no venció y no se usó), sin gastarlo."""
    now = now or utcnow()
    if not isinstance(token, str) or not (20 <= len(token) <= 100):
        return None
    row = s.get(LoginToken, _hash(token))
    return row if row and row.used_at is None and row.expires_at > now else None


def consume_login_token(s: Session, token: str, now=None):
    """Gasta el enlace de forma atómica: si dos pedidos llegan a la vez, solo uno lo consigue."""
    now = now or utcnow()
    if peek_login_token(s, token, now) is None:
        return None
    h = _hash(token)
    won = s.execute(update(LoginToken).where(LoginToken.token_hash == h, LoginToken.used_at.is_(None), LoginToken.expires_at > now)
                    .values(used_at=now)).rowcount
    return s.get(LoginToken, h) if won else None


def get_or_create(s: Session, email: str, now=None) -> User:
    """El usuario con ese email; si no existe, lo crea. Solo se llama con un email que ya demostró ser de quien lo pidió (abrió el enlace)."""
    now = now or utcnow()
    user = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, created_at=now)
        s.add(user)
        s.flush()
    user.last_login_at = now
    return user


def by_ml(s: Session, ml_user_id: int):
    return s.execute(select(User).where(User.ml_user_id == int(ml_user_id))).scalar_one_or_none()


def link_conflict(s: Session, user: User, ml_user_id: int):
    """Por qué esta cuenta de Mercado Libre no se puede asociar a este usuario, o None si se puede."""
    other = by_ml(s, ml_user_id)
    if other is not None and other.id != user.id:
        return "tomada"          # ya la usa otro usuario de Lumo
    if user.ml_user_id is not None and user.ml_user_id != int(ml_user_id):
        return "otra"            # este usuario ya tiene otra cuenta de Mercado Libre
    return None


def link(s: Session, user: User, ml_user_id: int) -> None:
    user.ml_user_id = int(ml_user_id)
