from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, String, Text
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
    email = Column(Text, nullable=True)  # para los avisos por mail; se lee de Mercado Libre
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


class CampaignDay(Base):
    """Un día de una campaña. Lumo lo guarda para que el historial supere los 90 días que deja consultar Mercado Libre."""

    __tablename__ = "campaign_day"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    campaign_id = Column(BigInteger, primary_key=True, autoincrement=False)
    day = Column(String(10), primary_key=True)
    spend = Column(Float, nullable=False, default=0)
    clicks = Column(Float, nullable=False, default=0)
    prints = Column(Float, nullable=False, default=0)
    units = Column(Float, nullable=False, default=0)
    sales = Column(Float, nullable=False, default=0)


class AuditLog(Base):
    """Registro de auditoría de accesos y cambios de administración. No guarda datos personales más allá del id de cuenta."""

    __tablename__ = "audit_log"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    at = Column(DateTime, nullable=False, default=utcnow, index=True)
    event = Column(String(40), nullable=False)
    actor = Column(BigInteger, nullable=True)
    target = Column(String(64), nullable=True)
    detail = Column(String(200), nullable=True)


class Notice(Base):
    """Último aviso enviado de cada tipo y referencia, para no repetirlo."""

    __tablename__ = "notice"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    kind = Column(String(8), primary_key=True)
    ref = Column(String(64), primary_key=True)
    sent_at = Column(DateTime, nullable=False, default=utcnow)


class Subscription(Base):
    """Suscripción de una cuenta. La prueba gratis empieza cuando Mercado Pago confirma el medio de pago, y es una sola por cuenta:
    por eso la fila no se borra."""

    __tablename__ = "subscription"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    trial_started_at = Column(DateTime, nullable=True)  # cuándo empezó la prueba gratis; vacío: todavía no la usó
    trial_ends_at = Column(DateTime, nullable=False, default=utcnow)  # día del primer cobro; solo vale si trial_started_at tiene fecha
    # new | pending | authorized | paused | cancelled (los últimos cuatro son los estados de Mercado Pago)
    status = Column(String(32), nullable=False, default="new")
    mp_preapproval_id = Column(String(64), nullable=True)
    payer_email = Column(String(254), nullable=True)
    paid_until = Column(DateTime, nullable=True)  # próximo cobro informado por Mercado Pago: hasta ahí ya está pago
    plan = Column(String(16), nullable=True)  # monthly | annual
    amount_ars = Column(Float, nullable=True)  # monto en pesos cargado en Mercado Pago: se actualiza con la cotización
    past_due_since = Column(DateTime, nullable=True)  # primer cobro rechazado sin resolver: desde ahí corren los días de gracia
    # Cambio de plan en curso: reemplaza al actual cuando Mercado Pago lo autoriza.
    next_preapproval_id = Column(String(64), nullable=True)
    next_plan = Column(String(16), nullable=True)
    next_amount_ars = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AdClick(Base):
    """De qué anuncio de Meta vino una cuenta (identificadores _fbc/_fbp del Píxel) y qué eventos de conversión ya se mandaron.
    No guarda la IP. Se borra con la cuenta."""

    __tablename__ = "ad_click"

    user_id = Column(BigInteger, primary_key=True, autoincrement=False)
    fbc = Column(String(600), nullable=True)  # clic en un anuncio (fbclid)
    fbp = Column(String(64), nullable=True)  # navegador, según el Píxel
    user_agent = Column(String(400), nullable=True)
    sent = Column(String(80), nullable=False, default="")  # eventos ya enviados, separados por coma
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
