"""Quién puede usar Lumo: administradores (variable de entorno), cuentas con acceso sin cargo, invitaciones de un solo uso
y cuentas en prueba gratis o con la suscripción al día."""
import secrets
from datetime import timedelta

from sqlalchemy import update

from . import billing
from .models import Access, Invite, Subscription, utcnow

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


def plan(db, cfg: dict, user_id) -> dict:
    """Por qué entra (o no) una cuenta: admin, free (acceso sin cargo), paid, trial, expired o none (nunca ingresó)."""
    if user_id is None:
        return {"kind": "none"}
    if is_admin(cfg, user_id):
        return {"kind": "admin"}
    if db.get(Access, int(user_id)) is not None:
        return {"kind": "free"}
    sub = db.get(Subscription, int(user_id))
    if sub is None:
        return {"kind": "none"}  # nunca se suscribió: puede empezar su prueba gratis
    now = utcnow()
    base = {"status": sub.status, "plan": sub.plan, "next_plan": sub.next_plan}
    if sub.past_due_since:
        # Cobro rechazado: entra durante los días de gracia y después se suspende hasta que regularice.
        limit = billing.grace_end(cfg, sub)
        if now < limit:
            return dict(base, kind="paid", past_due=True, grace_ends=limit, days=billing.days_left(limit))
        return dict(base, kind="expired", reason="unpaid")
    if sub.status == "authorized" and billing.in_trial(sub):
        # Prueba gratis: ya cargó su medio de pago y todavía no se le cobró nada.
        return dict(base, kind="trial", days=billing.days_left(sub.trial_ends_at), ends=sub.trial_ends_at)
    if sub.status == "authorized" or (sub.paid_until and sub.paid_until > now):
        return dict(base, kind="paid", until=sub.paid_until)
    if sub.trial_started_at is None:
        return dict(base, kind="expired", reason="new")  # todavía no empezó su prueba gratis
    return dict(base, kind="expired", reason="cancelled")


def has_access(db, cfg: dict, user_id) -> bool:
    return plan(db, cfg, user_id)["kind"] in ("admin", "free", "paid", "trial")


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
