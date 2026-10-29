from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, String, Text
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
