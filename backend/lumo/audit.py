"""Registro de auditoría: quién hizo qué y cuándo. Sin contraseñas, tokens ni emails; solo ids y tipos de evento.

ISO 27001 A.8.15 · SOC 2 CC7.2, CC7.3. Se conserva AUDIT_DAYS (ver privacy.purge).
"""
import logging

from .models import AuditLog

log = logging.getLogger("lumo.audit")


def record(db, event: str, actor=None, target=None, detail: str = None) -> None:
    """Agrega un evento a la sesión de base de datos; quien llama hace el commit junto con el resto del cambio."""
    db.add(AuditLog(event=event[:40], actor=int(actor) if actor is not None else None,
                    target=str(target)[:64] if target is not None else None, detail=(detail or None) and detail[:200]))
    log.info("audit event=%s actor=%s target=%s", event, actor, target)
