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
    scope = Column(String(255), nullable=True)
    # connected | needs_reconnect
    status = Column(String(32), nullable=False, default="connected")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
