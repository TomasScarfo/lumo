"""Derechos de las personas sobre sus datos y plazos de conservación.

Acceso/portabilidad (export_user), supresión (erase_user) y limitación del plazo de conservación (purge).
ISO 27701 7.3.x / 7.4.x · ISO 27001 A.5.34, A.8.10 · SOC 2 P4, P5, P6 y C1.2.
"""
import json
from datetime import timedelta

from sqlalchemy import delete, select, update

from .history import KEEP_DAYS as HISTORY_DAYS
from .models import Access, Account, AdClick, AuditLog, CampaignDay, Invite, Notice, PanelState, Snapshot, Subscription, utcnow

# Plazos de conservación, en días.
AUDIT_DAYS = 400      # un año de auditoría más margen para el cierre del período
NOTICE_DAYS = 400     # el registro de avisos solo evita repetirlos; después no hace falta
INVITE_DAYS = 90      # invitaciones, desde que vencieron (usadas, revocadas o sin usar)

PER_USER = (Access, Account, Snapshot, PanelState, CampaignDay, Notice, AdClick)
# De la suscripción no se borra la fila: queda el id de cuenta y la fecha de la prueba gratis, para que la prueba sea una sola
# por cuenta. Quien borra la cuenta se ocupa antes de cancelar el cobro y vaciar el email de pago (billing.end).
KEPT_MINIMAL = (Subscription,)


def erase_user(db, uid: int) -> None:
    """Borra todo lo que Lumo guarda de una cuenta. No se anula la autorización en Mercado Libre: eso lo hace la persona
    desde su perfil (Mi perfil → Seguridad → Aplicaciones conectadas)."""
    uid = int(uid)
    for model in PER_USER:
        db.execute(delete(model).where(model.user_id == uid))
    db.execute(update(Invite).where(Invite.used_by == uid).values(used_by=0))  # sigue figurando como usada, sin la cuenta


def export_user(db, uid: int) -> dict:
    """Todo lo que Lumo guarda de una cuenta, en un formato que se puede leer y llevar a otro lado. Sin tokens."""
    uid = int(uid)
    acc, snap, st, acs = db.get(Account, uid), db.get(Snapshot, uid), db.get(PanelState, uid), db.get(Access, uid)
    sub, ad = db.get(Subscription, uid), db.get(AdClick, uid)
    iso = lambda d: d.isoformat() + "Z" if d else None
    days = db.execute(select(CampaignDay).where(CampaignDay.user_id == uid).order_by(CampaignDay.campaign_id, CampaignDay.day)).scalars().all()
    notices = db.execute(select(Notice).where(Notice.user_id == uid).order_by(Notice.sent_at)).scalars().all()
    events = db.execute(select(AuditLog).where(AuditLog.actor == uid).order_by(AuditLog.at)).scalars().all()
    return {
        "generado": iso(utcnow()),
        "cuenta": {"id": uid, "email": acc.email if acc else None, "estado": acc.status if acc else None,
                   "permisos": acc.scope if acc else None, "conectada": iso(acc.created_at) if acc else None,
                   "nota_de_acceso": acs.note if acs else None},
        "panel": json.loads(st.data) if st else {},
        "copia_de_datos": {"anunciante": snap.advertiser_id, "actualizada": iso(snap.fetched_at)} if snap else None,
        "historial_de_campanas": [{"campana": d.campaign_id, "dia": d.day, "gasto": d.spend, "clics": d.clicks, "impresiones": d.prints,
                                   "unidades": d.units, "ventas": d.sales} for d in days],
        "suscripcion": {"estado": sub.status, "plan": sub.plan, "email_de_pago": sub.payer_email, "prueba_hasta": iso(sub.trial_ends_at),
                        "pago_hasta": iso(sub.paid_until)} if sub else None,
        "anuncios_de_meta": {"clic_en_anuncio": ad.fbc, "navegador": ad.fbp, "eventos_enviados": [e for e in (ad.sent or "").split(",") if e],
                             "desde": iso(ad.created_at)} if ad else None,
        "avisos_enviados": [{"tipo": n.kind, "referencia": n.ref, "enviado": iso(n.sent_at)} for n in notices],
        "registro_de_actividad": [{"evento": e.event, "fecha": iso(e.at)} for e in events],
        "nota": "Los tokens de acceso a Mercado Libre se guardan cifrados y no se incluyen en esta descarga.",
    }


def purge(db, now=None) -> dict:
    """Aplica los plazos de conservación. Lo corre el chequeo diario."""
    now = now or utcnow()
    out = {}
    out["auditoria"] = db.execute(delete(AuditLog).where(AuditLog.at < now - timedelta(days=AUDIT_DAYS))).rowcount
    out["avisos"] = db.execute(delete(Notice).where(Notice.sent_at < now - timedelta(days=NOTICE_DAYS))).rowcount
    out["invitaciones"] = db.execute(delete(Invite).where(Invite.expires_at < now - timedelta(days=INVITE_DAYS))).rowcount
    cutoff = (now - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    out["historial"] = db.execute(delete(CampaignDay).where(CampaignDay.day < cutoff)).rowcount
    db.commit()
    return out
