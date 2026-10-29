"""Quién puede usar Lumo: administradores (variable de entorno), cuentas con acceso e invitaciones de un solo uso."""
import secrets
from datetime import timedelta

from sqlalchemy import update

from .models import Access, Invite, utcnow

INVITE_DAYS = 14


def admin_ids(cfg: dict) -> set:
    out = set()
    for part in (cfg.get("ADMIN_USER_IDS") or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def is_admin(cfg: dict, user_id) -> bool:
    return user_id is not None and int(user_id) in admin_ids(cfg)


def has_access(db, cfg: dict, user_id) -> bool:
    if user_id is None:
        return False
    return is_admin(cfg, user_id) or db.get(Access, int(user_id)) is not None


def create_invite(db, label: str, days: int = INVITE_DAYS) -> Invite:
    inv = Invite(token=secrets.token_urlsafe(32), label=(label or "").strip()[:120] or None, expires_at=utcnow() + timedelta(days=days))
    db.add(inv)
    return inv


def valid_invite(db, token):
    """La invitación si existe, no venció, no se revocó y no se usó."""
    inv = db.get(Invite, token) if token else None
    if inv is None or inv.revoked or inv.used_by is not None or inv.expires_at < utcnow():
        return None
    return inv


def consume_invite(db, token: str, user_id: int) -> bool:
    """Marca la invitación como usada de forma atómica: si dos personas la usan a la vez, solo una gana."""
    res = db.execute(update(Invite).where(Invite.token == token, Invite.used_by.is_(None), Invite.revoked.is_(False),
                                          Invite.expires_at >= utcnow()).values(used_by=int(user_id), used_at=utcnow()))
    return res.rowcount == 1


def grant(db, user_id: int, note: str = None) -> None:
    row = db.get(Access, int(user_id))
    if row is None:
        db.add(Access(user_id=int(user_id), note=(note or "").strip()[:120] or None))
    elif note:
        row.note = note.strip()[:120]
