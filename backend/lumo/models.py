from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow() -> datetime:
    """Hora UTC sin zona horaria: se guarda igual en SQLite y en Postgres."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Account(Base):
    """Una cuenta de Mercado Libre que autorizó a Lumo. Los tokens se guardan cifrados."""

    __tablename__ = "account"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    scope = Column(Text, nullable=True)
    # connected | needs_reconnect
    status = Column(String(32), nullable=False, default="connected")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Snapshot(Base):
    """Última lectura de datos de Product Ads de una cuenta. Evita volver a pedirlo todo a Mercado Libre en cada visita."""

    __tablename__ = "snapshot"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    advertiser_id = Column(BigInteger, nullable=False)
    data = Column(Text, nullable=False)
    fetched_at = Column(DateTime, nullable=False, default=utcnow)


class PanelState(Base):
    """Lo que la persona marca en el panel: tareas hechas, acciones registradas, tareas propias y avisos."""

    __tablename__ = "panel_state"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    data = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Access(Base):
    """Cuentas de Mercado Libre que pueden usar Lumo. Quien no figura acá (y no es administrador) no entra."""

    __tablename__ = "access"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    note = Column(String(120), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Invite(Base):
    """Invitación de un solo uso. El enlace /invitacion/<token> permite conectar una cuenta nueva."""

    __tablename__ = "invite"

    token = Column(String(64), primary_key=True)
    label = Column(String(120), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    used_by = Column(BigInteger, nullable=True)
    used_at = Column(DateTime, nullable=True)


class Subscription(Base):
    """Prueba gratis y suscripción paga de una cuenta. Se crea al primer ingreso y no se borra: la prueba es una sola por cuenta."""

    __tablename__ = "subscription"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    trial_ends_at = Column(DateTime, nullable=False)
    # trial | pending | authorized | paused | cancelled (los últimos cuatro son los estados de Mercado Pago)
    status = Column(String(32), nullable=False, default="trial")
    mp_preapproval_id = Column(String(64), nullable=True)
    payer_email = Column(String(254), nullable=True)
    paid_until = Column(DateTime, nullable=True)  # próximo cobro informado por Mercado Pago: hasta ahí ya está pago
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
