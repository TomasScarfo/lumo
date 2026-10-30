"""Foto de la cuenta de Mercado Libre para cuando todavía no tiene Publicidad.

Solo lectura y de mejor esfuerzo: si una consulta falla, ese dato queda en None y el panel lo muestra como "sin dato".
`get(path, params, version)` hace la llamada autenticada, igual que en ads.py.
"""
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .ml import MLError

log = logging.getLogger("lumo")

MAX_ITEMS = 100
BATCH = 20
TOP_CATS = 4
TOP_PRODUCTS = 3

REPUTATION = {
    "5_green": "Verde", "4_light_green": "Verde claro", "3_yellow": "Amarilla", "2_orange": "Naranja", "1_red": "Roja",
}
GOOD_REPUTATION = ("5_green", "4_light_green", "3_yellow")


def _try(fn, default=None):
    try:
        return fn()
    except (MLError, ValueError, KeyError, TypeError) as exc:
        log.info("lectura de cuenta incompleta: %s", exc)
        return default


def build(get) -> dict:
    me = _try(lambda: get("/users/me", None, None), {}) or {}
    uid = me.get("id")
    rep = (me.get("seller_reputation") or {})
    level = rep.get("level_id")
    out = {
        "nick": me.get("nickname"),
        "site": me.get("site_id"),
        "reputacion": {"id": level, "nombre": REPUTATION.get(level), "buena": level in GOOD_REPUTATION} if me else None,
        "ventas": ((rep.get("transactions") or {}).get("completed")) if me else None,
        "activas": None, "con_stock": None, "categorias": [], "productos": [],
    }
    if not uid:
        out["requisitos"] = requisitos(out)
        return out

    search = _try(lambda: get("/users/%s/items/search" % uid, {"status": "active", "limit": 50}, None))
    ids = list((search or {}).get("results") or [])
    if search is not None:
        out["activas"] = ((search.get("paging") or {}).get("total")) or len(ids)
    ids = ids[:MAX_ITEMS]

    def fetch(chunk):
        res = _try(lambda: get("/items", {"ids": ",".join(chunk), "attributes": "id,title,category_id,price,currency_id,sold_quantity,available_quantity,status"}, None), [])
        return [r.get("body") for r in res if isinstance(r, dict) and r.get("code") == 200 and isinstance(r.get("body"), dict)]

    chunks = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        items = [it for part in pool.map(fetch, chunks) for it in part]
    if items:
        out["con_stock"] = sum(1 for it in items if (it.get("available_quantity") or 0) > 0)
        stocked = [it for it in items if (it.get("available_quantity") or 0) > 0]
        stocked.sort(key=lambda it: it.get("sold_quantity") or 0, reverse=True)
        out["productos"] = [
            {"titulo": it.get("title"), "vendidas": it.get("sold_quantity") or 0, "stock": it.get("available_quantity") or 0,
             "precio": it.get("price"), "moneda": it.get("currency_id")}
            for it in stocked[:TOP_PRODUCTS]
        ]
        cats = defaultdict(lambda: {"publicaciones": 0, "vendidas": 0})
        for it in items:
            if it.get("category_id"):
                c = cats[it["category_id"]]
                c["publicaciones"] += 1
                c["vendidas"] += it.get("sold_quantity") or 0
        top = sorted(cats.items(), key=lambda kv: (kv[1]["vendidas"], kv[1]["publicaciones"]), reverse=True)[:TOP_CATS]

        def name(cid):
            return (_try(lambda: get("/categories/%s" % cid, None, None), {}) or {}).get("name") or cid

        with ThreadPoolExecutor(max_workers=4) as pool:
            names = list(pool.map(name, [cid for cid, _ in top]))
        out["categorias"] = [dict(nombre=n, **v) for n, (_, v) in zip(names, top)]
    out["requisitos"] = requisitos(out)
    return out


def requisitos(c: dict) -> list:
    """Lo que Mercado Libre pide en general para anunciar. Estado: ok, falta, revisar o sindato."""
    def state(known, ok):
        return "sindato" if known is None else ("ok" if ok else "falta")

    rep = c.get("reputacion")
    if not rep or rep.get("id") is None:
        rep_state, rep_txt = "revisar", "Todavía no tenés reputación asignada. Con tus primeras ventas se va a generar."
    elif rep["buena"]:
        rep_state, rep_txt = "ok", "Tu reputación es %s." % rep["nombre"].lower()
    else:
        rep_state, rep_txt = "revisar", "Tu reputación es %s. Una reputación baja puede limitar el acceso a Publicidad." % (rep["nombre"] or "baja").lower()

    return [
        {"titulo": "Cuenta de vendedor con publicaciones activas",
         "estado": state(c.get("activas"), (c.get("activas") or 0) > 0),
         "detalle": "Tenés %s publicaciones activas." % c["activas"] if c.get("activas") else "Necesitás al menos una publicación activa para anunciar."},
        {"titulo": "Publicaciones con stock disponible",
         "estado": state(c.get("con_stock"), (c.get("con_stock") or 0) > 0),
         "detalle": "%s de tus publicaciones tienen stock." % c["con_stock"] if c.get("con_stock") else "Los anuncios solo se muestran si hay stock."},
        {"titulo": "Reputación del vendedor", "estado": rep_state, "detalle": rep_txt},
        {"titulo": "Publicidad activada en tu perfil", "estado": "falta",
         "detalle": "Es el paso que falta: se activa desde Mercado Libre, en Mi perfil → Publicidad."},
        {"titulo": "Presupuesto para tus campañas", "estado": "revisar",
         "detalle": "Lo definís al crear tu primera campaña. Mercado Libre cobra solo cuando alguien hace clic."},
    ]
