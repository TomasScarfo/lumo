"""Respuestas simuladas de la API de Mercado Libre, con la misma forma que la documentación de Product Ads."""
import random
from datetime import datetime, timedelta

from lumo.ml import MLError

ADVERTISER = {"advertiser_id": 3646719, "site_id": "MLA", "advertiser_name": "Casa de prueba", "account_name": "MLA - X"}

CAMPAIGNS = [
    {"id": 101, "name": "Mesas y sillas", "status": "active", "budget": 12000.0, "currency_id": "ARS", "acos_target": 20.0, "strategy": "profitability"},
    {"id": 102, "name": "Almohadones & fundas", "status": "active", "budget": 6000.0, "currency_id": "ARS", "acos_target": 25.0, "strategy": "growth"},
    {"id": 103, "name": "Sin objetivo", "status": "active", "budget": 4000.0, "currency_id": "ARS", "acos_target": None, "strategy": "visibility"},
    {"id": 104, "name": "Pausada", "status": "paused", "budget": 3000.0, "currency_id": "ARS", "acos_target": 20.0, "strategy": "profitability"},
]
# id, título, campaña (None = sin publicidad), estado del anuncio, precio, ventas orgánicas 30d, ventas orgánicas 30d previos
ITEMS = [
    ("MLA1", "Mesa de comedor <roble>", 101, "active", 185000.0, 5, 5),
    ("MLA2", "Silla tapizada (set x2)", 101, "active", 64000.0, 10, 9),
    ("MLA3", "Funda de almohadón 50x50", 102, "active", 14500.0, 22, 20),
    ("MLA4", "Pack x4 fundas", 102, "active", 28500.0, 9, 10),
    ("MLA5", "Cortina sin objetivo", 103, "active", 31000.0, 7, 11),
    ("MLA6", "Manta tejida", None, "idle", 38000.0, 31, 21),
    ("MLA7", "Banqueta alta", None, "idle", 54000.0, 12, 10),
    ("MLA8", "Vela de coco", None, "paused", 9800.0, 3, 3),
]


def _days(params):
    d0 = datetime.strptime(params["date_from"], "%Y-%m-%d")
    d1 = datetime.strptime(params["date_to"], "%Y-%m-%d")
    while d0 <= d1:
        yield d0
        d0 += timedelta(days=1)


def _daily(cid, day):
    r = random.Random(cid * 100000 + day.toordinal())
    clicks = 0 if cid == 104 else r.randint(10, 60)
    cost = clicks * r.randint(90, 520)
    units = clicks * r.randint(1, 4) // 50
    return {"date": day.strftime("%Y-%m-%d"), "clicks": clicks, "prints": clicks * 70, "cost": float(cost),
            "direct_units_quantity": units, "indirect_units_quantity": 1 if units else 0,
            "direct_amount": float(units * 30000), "indirect_amount": 12000.0 if units else 0.0}


def _item_metrics(item, params):
    iid, _, camp, _, price, now_units, prev_units = item
    prev = datetime.strptime(params["date_to"], "%Y-%m-%d") < datetime.now() - timedelta(days=30)
    units = prev_units if prev else now_units
    ads = camp is not None
    return {"clicks": 40 if ads else 0, "prints": 3000 if ads else 0, "cost": 4000.0 if ads else 0.0,
            "organic_units_quantity": units, "organic_units_amount": units * price,
            "direct_units_quantity": 1 if ads else 0, "indirect_units_quantity": 0,
            "direct_amount": price if ads else 0.0, "indirect_amount": 0.0}


def api_get(cfg, token, path, params=None, version="2"):
    params = params or {}
    if path.endswith("/product_ads/campaigns") and "/advertisers/" in path:
        lo = params.get("offset", 0)
        lim = params.get("limit", 50)
        return {"paging": {"total": len(CAMPAIGNS), "offset": lo, "limit": lim}, "results": CAMPAIGNS[lo:lo + lim]}
    if "/product_ads/campaigns/" in path:
        cid = int(path.rsplit("/", 1)[1])
        if params.get("aggregation_type") == "DAILY":
            return [_daily(cid, d) for d in _days(params)]
        return {"id": cid, "metrics": {"impression_share": 38.5, "top_impression_share": 12.0, "lost_impression_share_by_budget": 20.0,
                                       "lost_impression_share_by_ad_rank": 41.5, "acos_benchmark": 18}}
    if path.endswith("/product_ads/items"):
        lo, lim = params.get("offset", 0), params.get("limit", 50)
        rows = []
        for it in ITEMS:
            iid, title, camp, status, price = it[:5]
            rows.append({"item_id": iid, "campaign_id": camp or 0, "price": price, "title": title, "status": status,
                         "brand_value_name": "Nogal" if camp == 101 else None, "domain_id": "MLA-DINING_TABLES",
                         "permalink": "https://articulo.mercadolibre.com.ar/" + iid, "metrics": _item_metrics(it, params)})
        return {"paging": {"offset": lo, "last_item_id": None, "total": len(rows), "limit": lim}, "results": rows[lo:lo + lim]}
    if path == "/items":
        out = []
        for iid in params["ids"].split(","):
            out.append({"code": 200, "body": {"id": iid, "available_quantity": 7 if iid == "MLA6" else 50, "category_id": "MLA1574"}})
        return out
    if path.startswith("/categories/"):
        return {"id": path.rsplit("/", 1)[1], "name": "Comedor"}
    if path == "/visits/items":
        return [{"item_id": i, "total_visits": 800} for i in params["ids"].split(",")]
    raise MLError(404, "not_found", path)
