"""Lectura de Product Ads y armado de los datos que muestra el panel.

Todo lo que se pide acá es de solo lectura. `get(path, params, version)` es la función que hace la llamada
autenticada, así se puede reemplazar en las pruebas.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .ml import MLError

log = logging.getLogger("lumo")

DAYS = 60
AR = timezone(timedelta(hours=-3))  # Argentina no usa horario de verano
MAX_ITEMS = 600
PAGE = 50
WORKERS = 5
DEFAULT_ROAS_TARGET = 5.0  # equivale a un ACOS del 20%, solo si la campaña no informa su objetivo

CAMP_DAILY = "clicks,prints,cost,direct_units_quantity,indirect_units_quantity,direct_amount,indirect_amount"
CAMP_SHARE = "impression_share,top_impression_share,lost_impression_share_by_budget,lost_impression_share_by_ad_rank,acos_benchmark"
ITEM_METRICS = "clicks,prints,cost,organic_units_quantity,organic_units_amount,direct_units_quantity,indirect_units_quantity,direct_amount,indirect_amount"


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


def _share(v):
    """Participación de impresiones: Mercado Libre puede informarla en porcentaje (0-100) o en fracción (0-1)."""
    if v is None:
        return None
    v = _n(v)
    return v / 100.0 if v > 1 else v


def window_end(now: datetime) -> datetime:
    """Último día con datos completos: la API actualiza a las 10:00 (hora de Argentina)."""
    local = now.astimezone(AR)
    back = 1 if local.hour >= 10 else 2
    return (local - timedelta(days=back)).replace(hour=0, minute=0, second=0, microsecond=0)


def _day(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def list_campaigns(get, adv_id) -> list:
    out, offset = [], 0
    while True:
        resp = get("/advertising/advertisers/%s/product_ads/campaigns" % adv_id, {"limit": PAGE, "offset": offset})
        rows = resp.get("results", []) if isinstance(resp, dict) else []
        out.extend(rows)
        total = (resp.get("paging") or {}).get("total", 0) if isinstance(resp, dict) else 0
        offset += PAGE
        if not rows or offset >= total or offset >= 500:
            return out


def campaign_daily(get, cid, start: datetime, end: datetime) -> list:
    resp = get("/advertising/product_ads/campaigns/%s" % cid, {
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


def campaign_shares(get, cid, end: datetime) -> dict:
    resp = get("/advertising/product_ads/campaigns/%s" % cid, {
        "date_from": _day(end - timedelta(days=29)), "date_to": _day(end), "metrics": CAMP_SHARE})
    m = resp.get("metrics", resp) if isinstance(resp, dict) else {}
    return {"share": _share(m.get("impression_share")), "topShare": _share(m.get("top_impression_share")),
            "lostB": _share(m.get("lost_impression_share_by_budget")), "lostR": _share(m.get("lost_impression_share_by_ad_rank")),
            "benchmark": m.get("acos_benchmark")}


def item_sweep(get, adv_id, start: datetime, end: datetime) -> list:
    out, offset = [], 0
    params = {"limit": PAGE, "date_from": _day(start), "date_to": _day(end), "metrics": ITEM_METRICS,
              "filters[statuses]": "active,paused,idle"}
    while len(out) < MAX_ITEMS:
        try:
            resp = get("/advertising/advertisers/%s/product_ads/items" % adv_id, dict(params, offset=offset))
        except MLError as exc:
            if exc.status == 400 and "filters[statuses]" in params:
                params.pop("filters[statuses]")  # por si ese filtro no aplica, se piden todas
                continue
            raise
        rows = resp.get("results", []) if isinstance(resp, dict) else []
        out.extend(rows)
        total = (resp.get("paging") or {}).get("total", 0) if isinstance(resp, dict) else 0
        offset += PAGE
        if not rows or offset >= total:
            break
    return out


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def item_details(get, ids: list) -> dict:
    """Stock y categoría de cada publicación (API de ítems). Si falla, el panel funciona sin esos datos."""
    out = {}
    for chunk in _chunks(ids, 20):
        try:
            resp = get("/items", {"ids": ",".join(chunk), "attributes": "id,available_quantity,category_id"}, None)
        except MLError as exc:
            log.warning("detalle de ítems falló: %s", exc.status)
            continue
        for row in resp if isinstance(resp, list) else []:
            body = row.get("body") or {}
            if row.get("code") == 200 and body.get("id"):
                out[body["id"]] = body
    return out


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


def build_dataset(get, advertiser: dict, now: datetime = None) -> dict:
    now = now or datetime.now(timezone.utc)
    adv_id = advertiser["advertiser_id"]
    end = window_end(now)
    start = end - timedelta(days=DAYS - 1)
    cur_from, prev_to, prev_from = end - timedelta(days=29), end - timedelta(days=30), end - timedelta(days=59)
    notes = []

    camps_raw = list_campaigns(get, adv_id)
    with ThreadPoolExecutor(WORKERS) as pool:
        dailies = list(pool.map(lambda c: campaign_daily(get, c["id"], start, end), camps_raw))
        shares = list(pool.map(lambda c: campaign_shares(get, c["id"], end), camps_raw))
        cur_items, prev_items = pool.map(lambda w: item_sweep(get, adv_id, w[0], w[1]), [(cur_from, end), (prev_from, prev_to)])

    camps, estimated = [], []
    for c, daily, sh in zip(camps_raw, dailies, shares):
        acos = _n(c.get("acos_target"))
        target = 100.0 / acos if acos > 0 else DEFAULT_ROAS_TARGET
        if acos <= 0:
            estimated.append(c.get("name"))
        camps.append({"id": c["id"], "name": c.get("name") or "Campaña %s" % c["id"], "status": c.get("status"),
                      "budget": _n(c.get("budget")), "strategy": c.get("strategy"), "acosTarget": acos if acos > 0 else 100.0 / DEFAULT_ROAS_TARGET,
                      "target": target, "estTarget": acos <= 0, "daily": daily, **sh})
    if estimated:
        notes.append("Estas campañas no informan un ACOS objetivo en Mercado Libre, así que usamos un ROAS objetivo estimado de $%s: %s." % (
            int(DEFAULT_ROAS_TARGET), ", ".join(estimated)))

    camp_ids = {c["id"] for c in camps}
    prev_by_id = {r.get("item_id"): r.get("metrics") or {} for r in prev_items}
    rows = {}
    for r in cur_items:
        rows[r.get("item_id")] = r
    ids = [i for i in rows if i]

    def worth(i):  # el detalle solo se pide para lo que se usa en el panel
        m = rows[i].get("metrics") or {}
        return _n(m.get("organic_units_quantity")) > 0 or rows[i].get("status") == "active"
    detail_ids = [i for i in ids if worth(i)][:300]
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

    totals = {}
    for r in cur_items:
        cid = r.get("campaign_id")
        if r.get("status") == "active" and cid in camp_ids:
            m = r.get("metrics") or {}
            t = totals.setdefault(cid, {"n": 0, "cost": 0.0, "sales": 0.0})
            t["n"] += 1
            t["cost"] += _n(m.get("cost"))
            t["sales"] += _n(m.get("direct_amount")) + _n(m.get("indirect_amount"))

    items = []
    for i in ids:
        r = rows[i]
        m, pm = r.get("metrics") or {}, prev_by_id.get(i, {})
        cid = r.get("campaign_id") if r.get("status") == "active" and r.get("campaign_id") in camp_ids else None
        sp = sa = 0.0
        if cid is not None:
            t = totals[cid]
            sp = _n(m.get("cost")) / t["cost"] if t["cost"] else 1.0 / t["n"]
            sa = (_n(m.get("direct_amount")) + _n(m.get("indirect_amount"))) / t["sales"] if t["sales"] else 1.0 / t["n"]
        d = details.get(i, {})
        units = _n(m.get("organic_units_quantity"))
        vis = visits.get(i)
        cat = cats.get(d.get("category_id")) or _humanize(r.get("domain_id"))
        items.append({"id": i, "name": r.get("title") or i, "cat": cat, "brand": r.get("brand_value_name") or "Sin marca",
                      "camp": cid, "sp": sp, "sa": sa, "price": _n(r.get("price")), "units": units,
                      "prevUnits": _n(pm.get("organic_units_quantity")), "orgAmt": _n(m.get("organic_units_amount")),
                      "prevOrgAmt": _n(pm.get("organic_units_amount")), "visits": vis,
                      "conv": (units / vis) if vis else None, "stock": d.get("available_quantity"), "link": r.get("permalink")})

    return {"advertiser": {"id": adv_id, "name": advertiser.get("advertiser_name") or "Tu cuenta", "site": advertiser.get("site_id") or ""},
            "end": _day(end), "days": DAYS, "fetchedAt": now.astimezone(timezone.utc).isoformat(), "camps": camps, "items": items, "notes": notes}
