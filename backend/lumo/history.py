"""Historial propio de las campañas.

Mercado Libre solo deja consultar los últimos 90 días. Cada vez que Lumo lee los datos guarda esos días, así que
el historial crece desde que la cuenta se conecta. Los días ya guardados no se vuelven a pedir: solo se reemplazan
los de la ventana actual, que Mercado Libre puede corregir.
"""
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import CampaignDay

KEEP_DAYS = 730  # dos años; más que eso no se guarda
FIELDS = ("spend", "clicks", "prints", "units", "sales")


def _day(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def save(s: Session, uid: int, data: dict) -> None:
    """Guarda (o reemplaza) los días de la ventana actual de cada campaña."""
    end = datetime.strptime(data["end"], "%Y-%m-%d")
    n = data["days"]
    for c in data["camps"]:
        cid = int(c["id"])
        for i, d in enumerate(c["daily"]):
            day = _day(end - timedelta(days=n - 1 - i))
            row = s.get(CampaignDay, (uid, cid, day)) or CampaignDay(user_id=uid, campaign_id=cid, day=day)
            for f in FIELDS:
                setattr(row, f, d[f])
            s.add(row)
    s.execute(delete(CampaignDay).where(CampaignDay.user_id == uid, CampaignDay.day < _day(end - timedelta(days=KEEP_DAYS))))
    s.commit()


def extend(s: Session, uid: int, data: dict) -> dict:
    """Antepone a cada campaña los días guardados anteriores a la ventana. Deja `days` con el largo total."""
    end = datetime.strptime(data["end"], "%Y-%m-%d")
    win = data["days"]
    win_start = _day(end - timedelta(days=win - 1))
    ids = [int(c["id"]) for c in data["camps"]]
    rows = s.execute(select(CampaignDay).where(CampaignDay.user_id == uid, CampaignDay.campaign_id.in_(ids),
                                               CampaignDay.day < win_start)).scalars().all() if ids else []
    if not rows:
        return data
    first = datetime.strptime(min(r.day for r in rows), "%Y-%m-%d")
    extra = (end - timedelta(days=win - 1) - first).days
    by = {(r.campaign_id, r.day): r for r in rows}
    empty = dict.fromkeys(FIELDS, 0)
    for c in data["camps"]:
        old = []
        for i in range(extra):
            r = by.get((int(c["id"]), _day(first + timedelta(days=i))))
            old.append({f: getattr(r, f) for f in FIELDS} if r else dict(empty))
        c["daily"] = old + c["daily"]
    data["days"] = win + extra
    data["since"] = _day(first)
    return data
