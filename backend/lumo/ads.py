"""Lectura de Product Ads y armado de los datos que muestra el panel.

Usa los endpoints vigentes de Product Ads (con el sitio en la ruta y Ad Groups). Los anteriores, sin sitio, se dieron
de baja en 2026 y responden 404. Todo es de solo lectura. `get(path, params, version)` hace la llamada autenticada,
así se puede reemplazar en las pruebas.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .ml import MLError

log = logging.getLogger("lumo")

DAYS = 60
AR = timezone(timedelta(hours=-3))  # Argentina no usa horario de verano
MAX_GROUPS = 800
PAGE = 200
WORKERS = 5
DEFAULT_ROAS_TARGET = 5.0  # equivale a un ACOS del 20%, solo si la campaña no informa su objetivo

CAMP_DAILY = "clicks,prints,cost,direct_units_quantity,indirect_units_quantity,direct_amount,indirect_amount"
CAMP_SHARE = "impression_share,top_impression_share,lost_impression_share_by_budget,lost_impression_share_by_ad_rank,acos_benchmark"
GROUP_METRICS = ("CLICKS,PRINTS,COST,DIRECT_AMOUNT,INDIRECT_AMOUNT,TOTAL_AMOUNT,DIRECT_UNITS_QUANTITY,INDIRECT_UNITS_QUANTITY,"
                 "UNITS_QUANTITY,ORGANIC_UNITS_QUANTITY,ORGANIC_UNITS_AMOUNT")


def _n(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _rows(resp) -> list:
    """Las respuestas diarias vienen como lista o envueltas en un objeto."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for key in ("results", "data", "metrics"):
            if isinstance(resp.get(key), list):
                return resp[key]
    return []


def _pct(v):
    """Mercado Libre informa los porcentajes de 0 a 100 (por ejemplo acos 19.41, ctr 1.4). Acá se guardan como fracción."""
    return None if v is None else _n(v) / 100.0


def window_end(now: datetime) -> datetime:
    """Último día con datos completos: la API actualiza a las 10:00 (hora de Argentina)."""
    local = now.astimezone(AR)
    back = 1 if local.hour >= 10 else 2
    return (local - timedelta(days=back)).replace(hour=0, minute=0, second=0, microsecond=0)


def _day(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _page(get, path, params, limit, cap):
    out, offset = [], 0
    while len(out) < cap:
        resp = get(path, dict(params, limit=limit, offset=offset))
        rows = resp.get("results", []) if isinstance(resp, dict) else []
        out.extend(rows)
        total = (resp.get("paging") or {}).get("total", 0) if isinstance(resp, dict) else 0
        offset += limit
        if not rows or offset >= total:
            break
    return out


def list_campaigns(get, site, adv_id) -> list:
    return _page(get, "/advertising/%s/advertisers/%s/product_ads/campaigns/search" % (site, adv_id), {}, 50, 500)


def campaign_daily(get, site, cid, start: datetime, end: datetime) -> list:
    resp = get("/advertising/%s/product_ads/campaigns/%s" % (site, cid), {
        "date_from": _day(start), "date_to": _day(end), "metrics": CAMP_DAILY, "aggregation_type": "DAILY"})
    by_date = {}
    for r in _rows(resp):
        by_date[str(r.get("date", ""))[:10]] = {
            "spend": _n(r.get("cost")), "clicks": _n(r.get("clicks")), "prints": _n(r.get("prints")),
            "units": _n(r.get("direct_units_quantity")) + _n(r.get("indirect_units_quantity")),
            "sales": _n(r.get("direct_amount")) + _n(r.get("indirect_amount")),
        }
    empty = {"spend": 0, "clicks": 0, "prints": 0, "units": 0, "sales": 0}
    return [by_date.get(_day(start + timedelta(days=i)), empty) for i in range(DAYS)]


def campaign_shares(get, site, cid, end: datetime) -> dict:
    resp = get("/advertising/%s/product_ads/campaigns/%s" % (site, cid), {
        "date_from": _day(end - timedelta(days=29)), "date_to": _day(end), "metrics": CAMP_SHARE})
    m = resp.get("metrics", resp) if isinstance(resp, dict) else {}
    return {"share": _pct(m.get("impression_share")), "topShare": _pct(m.get("top_impression_share")),
            "lostB": _pct(m.get("lost_impression_share_by_budget")), "lostR": _pct(m.get("lost_impression_share_by_ad_rank")),
            "benchmark": m.get("acos_benchmark")}


def group_sweep(get, site, adv_id, start: datetime, end: datetime) -> list:
    params = {"date_from": _day(start), "date_to": _day(end), "metrics": GROUP_METRICS, "sort": "desc", "sort_by": "cost"}
    return _page(get, "/advertising/%s/advertisers/%s/product_ads/ad_groups/search" % (site, adv_id), params, PAGE, MAX_GROUPS)


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def item_details(get, ids: list) -> dict:
    """Stock, categoría y marca de cada publicación (API de ítems). Si falla, el panel funciona sin esos datos."""
    out = {}
    for chunk in _chunks(ids, 20):
        try:
            resp = get("/items", {"ids": ",".join(chunk), "attributes": "id,available_quantity,category_id,attributes"}, None)
        except MLError as exc:
            log.warning("detalle de ítems falló: %s", exc.status)
            continue
        for row in resp if isinstance(resp, list) else []:
            body = row.get("body") or {}
            if row.get("code") == 200 and body.get("id"):
                out[body["id"]] = body
    return out


def _brand(detail: dict):
    for a in detail.get("attributes") or []:
        if a.get("id") == "BRAND" and a.get("value_name"):
            return a["value_name"]
    return None


def category_names(get, ids) -> dict:
    out = {}
    for cid in ids:
        try:
            resp = get("/categories/%s" % cid, None, None)
            out[cid] = resp.get("name") if isinstance(resp, dict) else None
        except MLError:
            out[cid] = None
    return out


def item_visits(get, ids: list, start: datetime, end: datetime) -> dict:
    """Visitas de los últimos 30 días por publicación. Es opcional: si falla, no se muestra la conversión."""
    out = {}
    for chunk in _chunks(ids, 20):
        try:
            resp = get("/visits/items", {"ids": ",".join(chunk), "date_from": _day(start), "date_to": _day(end)}, None)
        except MLError as exc:
            log.warning("visitas falló: %s", exc.status)
            return out
        if isinstance(resp, list):
            for r in resp:
                if isinstance(r, dict) and r.get("item_id") is not None:
                    out[r["item_id"]] = _n(r.get("total_visits", r.get("total")))
        elif isinstance(resp, dict):
            for k, v in resp.items():
                if isinstance(v, (int, float)):
                    out[k] = float(v)
    return out


def _humanize(domain: str) -> str:
    name = (domain or "").split("-", 1)[-1].replace("_", " ").strip().lower()
    return name.capitalize() if name else "Sin categoría"


def _sales(m: dict) -> float:
    return _n(m.get("direct_amount")) + _n(m.get("indirect_amount")) or _n(m.get("total_amount"))


def build_dataset(get, advertiser: dict, now: datetime = None) -> dict:
    now = now or datetime.now(timezone.utc)
    adv_id = advertiser["advertiser_id"]
    site = advertiser.get("site_id") or "MLA"
    end = window_end(now)
    start = end - timedelta(days=DAYS - 1)
    cur_from, prev_to, prev_from = end - timedelta(days=29), end - timedelta(days=30), end - timedelta(days=59)
    notes = []

    camps_raw = list_campaigns(get, site, adv_id)
    with ThreadPoolExecutor(WORKERS) as pool:
        dailies = list(pool.map(lambda c: campaign_daily(get, site, c["id"], start, end), camps_raw))
        shares = list(pool.map(lambda c: campaign_shares(get, site, c["id"], end), camps_raw))
        cur_groups, prev_groups = pool.map(lambda w: group_sweep(get, site, adv_id, w[0], w[1]), [(cur_from, end), (prev_from, prev_to)])

    camps, estimated = [], []
    for c, daily, sh in zip(camps_raw, dailies, shares):
        roas_t, acos_t = _n(c.get("roas_target")), _n(c.get("acos_target"))
        target = roas_t if roas_t > 0 else 100.0 / acos_t if acos_t > 0 else DEFAULT_ROAS_TARGET
        if roas_t <= 0 and acos_t <= 0:
            estimated.append(c.get("name"))
        camps.append({"id": c["id"], "name": c.get("name") or "Campaña %s" % c["id"], "status": c.get("status"),
                      "budget": _n(c.get("budget")), "strategy": c.get("strategy"), "acosTarget": 100.0 / target,
                      "target": target, "estTarget": roas_t <= 0 and acos_t <= 0, "daily": daily, **sh})
    if estimated:
        notes.append("Estas campañas no informan un ROAS objetivo en Mercado Libre, así que usamos uno estimado de $%s: %s." % (
            int(DEFAULT_ROAS_TARGET), ", ".join(estimated)))

    camp_ids = {c["id"] for c in camps}
    prev_by_id = {r.get("id"): r.get("metrics") or {} for r in prev_groups}
    rows = {r.get("id"): r for r in cur_groups if r.get("id") is not None}

    def single_item(g):  # solo las publicaciones individuales traen un item_id para pedir stock, marca y visitas
        return g.get("ad_group_external_id") if g.get("ad_group_type") == "ITEM" else None
    detail_ids = [single_item(g) for g in rows.values() if single_item(g)][:300]
    with ThreadPoolExecutor(WORKERS) as pool:
        details_f = pool.submit(item_details, get, detail_ids)
        visits_f = pool.submit(item_visits, get, detail_ids, cur_from, end)
        details, visits = details_f.result(), visits_f.result()
    cat_ids = sorted({d.get("category_id") for d in details.values() if d.get("category_id")})
    cats = category_names(get, cat_ids) if cat_ids else {}
    if not details and detail_ids:
        notes.append("No pudimos leer el stock de tus publicaciones, por eso no lo mostramos.")
    if not visits and detail_ids:
        notes.append("No pudimos leer las visitas de tus publicaciones, por eso no mostramos su conversión.")

    def in_campaign(g):
        cid = g.get("campaign_id")
        return cid if str(g.get("status", "")).lower() == "active" and cid in camp_ids else None

    totals = {}
    for g in rows.values():
        cid = in_campaign(g)
        if cid is not None:
            m = g.get("metrics") or {}
            t = totals.setdefault(cid, {"n": 0, "cost": 0.0, "sales": 0.0})
            t["n"] += 1
            t["cost"] += _n(m.get("cost"))
            t["sales"] += _sales(m)

    items = []
    for gid, g in rows.items():
        m, pm = g.get("metrics") or {}, prev_by_id.get(gid, {})
        cid = in_campaign(g)
        sp = sa = 0.0
        if cid is not None:
            t = totals[cid]
            sp = _n(m.get("cost")) / t["cost"] if t["cost"] else 1.0 / t["n"]
            sa = _sales(m) / t["sales"] if t["sales"] else 1.0 / t["n"]
        iid = single_item(g)
        d = details.get(iid, {}) if iid else {}
        units = _n(m.get("organic_units_quantity"))
        vis = visits.get(iid) if iid else None
        cat = cats.get(d.get("category_id")) or _humanize(g.get("domain_id"))
        items.append({"id": str(gid), "name": g.get("title") or str(gid), "cat": cat,
                      "brand": _brand(d) or g.get("brand_value_name") or "Sin marca",
                      "camp": cid, "sp": sp, "sa": sa, "price": _n(g.get("price")), "units": units,
                      "prevUnits": _n(pm.get("organic_units_quantity")), "orgAmt": _n(m.get("organic_units_amount")),
                      "prevOrgAmt": _n(pm.get("organic_units_amount")), "visits": vis,
                      "conv": (units / vis) if vis else None, "stock": d.get("available_quantity"), "link": g.get("permalink")})

    return {"advertiser": {"id": adv_id, "name": advertiser.get("advertiser_name") or "Tu cuenta", "site": site},
            "end": _day(end), "days": DAYS, "fetchedAt": now.astimezone(timezone.utc).isoformat(), "camps": camps, "items": items, "notes": notes}
