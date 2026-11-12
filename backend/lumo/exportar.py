"""Excel con las mismas tablas del panel: campañas, publicaciones con publicidad y evolución por día.

`periodo` calcula, para un tramo de días, lo mismo que el panel (ROAS, estado, uso del presupuesto, inversión por publicación);
`excel` lo escribe en un archivo .xlsx. Lo usan el botón "Descargar Excel" del panel y el resumen semanal por email.
"""
import io
from datetime import datetime, timedelta

import xlsxwriter

ESTADOS = {"supera": "Superando el objetivo", "objetivo": "En objetivo", "mejorando": "Mejorando", "oportunidad": "Con oportunidad",
           "revisar": "Revisar", "sindatos": "Sin actividad"}
SUMAS = ("spend", "sales", "clicks", "prints", "units")
DEFAULT_PERIODS = (7, 14, 30, 60, 90)


def _suma(rows) -> dict:
    out = dict.fromkeys(SUMAS, 0.0)
    for r in rows:
        for k in SUMAS:
            out[k] += r.get(k) or 0
    return out


def estado(roas: float, spend: float, sales: float, target: float, trend) -> str:
    """Mismo criterio que el panel (statusOf)."""
    if not spend:
        return "sindatos"
    if sales == 0:
        return "revisar"
    k = roas / target
    if k >= 1.2:
        return "supera"
    if k >= 0.9:
        return "objetivo"
    if trend is not None and trend >= 0.05:
        return "mejorando"
    return "revisar" if k < 0.7 else "oportunidad"


def _div(a: float, b: float) -> float:
    return a / b if b else 0.0


def periodo(data: dict, days: int = 30, off: int = 0) -> dict:
    """Campañas, publicaciones y días del tramo pedido. `off` son los días que se saltan desde hoy hacia atrás (como en el panel)."""
    total = data["days"]
    end = datetime.strptime(data["end"], "%Y-%m-%d")
    days = max(1, min(int(days), total))
    off = max(0, min(int(off), total - days))
    a, b = total - off - days, total - off
    camps, by_id = [], {}
    for c in data["camps"]:
        cur = _suma(c["daily"][a:b])
        prev = _suma(c["daily"][a - days:a]) if a - days >= 0 else None
        roas = _div(cur["sales"], cur["spend"])
        proas = _div(prev["sales"], prev["spend"]) if prev else 0
        trend = roas / proas - 1 if proas and cur["spend"] else None
        target = c.get("target") or 0
        row = {"id": c["id"], "name": c["name"], "paused": c.get("status") == "paused", "budget": c.get("budget") or 0, "target": target,
               "estTarget": bool(c.get("estTarget")), "cur": cur, "roas": roas, "trend": trend,
               "status": estado(roas, cur["spend"], cur["sales"], target, trend),
               "ctr": _div(cur["clicks"], cur["prints"]), "cpc": _div(cur["spend"], cur["clicks"]), "cvr": _div(cur["units"], cur["clicks"]),
               "used": _div(cur["spend"] / days, c.get("budget") or 0), "lostB": c.get("lostB"), "lostR": c.get("lostR"), "share": c.get("share"), "items": []}
        camps.append(row)
        by_id[str(c["id"])] = row
    items = []
    for it in data["items"]:
        c = by_id.get(str(it.get("camp")))
        if not c:
            continue
        spend, sales = c["cur"]["spend"] * it["sp"], c["cur"]["sales"] * it["sa"]
        clicks, prints = c["cur"]["clicks"] * it.get("kc", it["sp"]), c["cur"]["prints"] * it.get("kp", it["sp"])
        roas = _div(sales, spend)
        o = {"id": it["id"], "name": it["name"], "camp": c["name"], "spend": spend, "sales": sales, "roas": roas, "target": c["target"],
             "status": estado(roas, spend, sales, c["target"], None), "shareSpend": it["sp"], "shareSales": it["sa"],
             "clicks": clicks, "ctr": _div(clicks, prints), "cpc": _div(spend, clicks)}
        c["items"].append(o)
        items.append(o)
    daily = []
    for i in range(a, b):
        row = _suma(c["daily"][i] for c in data["camps"])
        row["date"] = end - timedelta(days=total - 1 - i)
        daily.append(row)
    cur = _suma(daily)
    return {"from": daily[0]["date"] if daily else end, "to": daily[-1]["date"] if daily else end, "days": days, "camps": camps, "items": items,
            "daily": daily, "tot": cur, "roas": _div(cur["sales"], cur["spend"])}


def top_publicaciones(per: dict, n: int = 5) -> list:
    """Las publicaciones que más ventas por publicidad aportaron en el tramo."""
    vendio = [o for o in per["items"] if o["sales"] > 0]
    return sorted(vendio, key=lambda o: -o["sales"])[:n]


def _formats(wb):
    base = {"font_name": "Arial", "font_size": 10, "valign": "vcenter"}
    f = lambda **k: wb.add_format(dict(base, **k))
    return {"head": f(bold=True, font_color="#FFFFFF", bg_color="#2446D6", text_wrap=True, align="center", border=1, border_color="#2446D6"),
            "txt": f(), "wrap": f(text_wrap=True), "bold": f(bold=True), "title": f(bold=True, font_size=16, font_color="#2446D6"),
            "money": f(num_format='"$"#,##0'), "roas": f(num_format='"$"0.0'), "pct": f(num_format="0.0%"), "int": f(num_format="#,##0"),
            "date": f(num_format="ddd d mmm yyyy", align="left"), "note": f(italic=True, font_color="#5A6B7C", text_wrap=True),
            "totmoney": f(bold=True, num_format='"$"#,##0', top=1), "totint": f(bold=True, num_format="#,##0", top=1), "tottxt": f(bold=True, top=1)}


def _tabla(ws, fmt, headers, rows, widths):
    """headers: [(texto, formato de la columna)]; rows: listas de valores (None deja la celda vacía)."""
    for c, (h, _) in enumerate(headers):
        ws.write(0, c, h, fmt["head"])
        ws.set_column(c, c, widths[c])
    ws.set_row(0, 32)
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            if v is None:
                ws.write_blank(r, c, None, fmt[headers[c][1]])
            elif isinstance(v, datetime):
                ws.write_datetime(r, c, v, fmt[headers[c][1]])
            else:
                ws.write(r, c, v, fmt[headers[c][1]])
    ws.freeze_panes(1, 1)
    if rows:
        ws.autofilter(0, 0, len(rows), len(headers) - 1)


def excel(data: dict, days: int = 30, off: int = 0) -> bytes:
    per = periodo(data, days, off)
    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True, "default_date_format": "d mmm yyyy"})
    wb.set_properties({"title": "Lumo", "author": "Lumo"})
    fmt = _formats(wb)
    adv = (data.get("advertiser") or {}).get("name") or "Tu cuenta"
    t = per["tot"]

    ws = wb.add_worksheet("Resumen")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 22)
    ws.write(0, 0, "Lumo", fmt["title"])
    ws.write(1, 0, adv, fmt["bold"])
    ws.write(2, 0, "Período: del %s al %s (%d días)" % (per["from"].strftime("%d/%m/%Y"), per["to"].strftime("%d/%m/%Y"), per["days"]), fmt["txt"])
    resumen = [("Inversión", t["spend"], "money"), ("Ventas por publicidad", t["sales"], "money"), ("ROAS", per["roas"], "roas"),
               ("Clics", t["clicks"], "int"), ("Impresiones", t["prints"], "int"), ("Unidades vendidas por publicidad", t["units"], "int")]
    for i, (k, v, f) in enumerate(resumen, start=4):
        ws.write(i, 0, k, fmt["bold"])
        ws.write(i, 1, v, fmt[f])
    ws.merge_range(11, 0, 14, 1, "Las ventas por publicidad suman las ventas directas y las asistidas. La inversión, las ventas y los clics de cada publicación son una "
                                 "estimación: se reparten según lo que cada una aportó a su campaña en los últimos 30 días. Lumo solo lee tus datos.", fmt["note"])

    ws = wb.add_worksheet("Campañas")
    heads = [("Campaña", "txt"), ("Estado", "txt"), ("ROAS", "roas"), ("ROAS objetivo", "roas"), ("Inversión", "money"), ("Ventas por publicidad", "money"),
             ("Clics", "int"), ("CTR", "pct"), ("CPC", "money"), ("CVR", "pct"), ("Presupuesto diario", "money"), ("Uso del presupuesto", "pct"),
             ("Perdidas por presupuesto", "pct"), ("Perdidas por ranking", "pct"), ("Participación de impresiones", "pct")]
    rows = [[c["name"] + (" (pausada)" if c["paused"] else ""), ESTADOS[c["status"]], c["roas"], c["target"], c["cur"]["spend"], c["cur"]["sales"],
             c["cur"]["clicks"], c["ctr"], c["cpc"], c["cvr"], c["budget"], c["used"], c["lostB"], c["lostR"], c["share"]]
            for c in sorted(per["camps"], key=lambda c: -c["cur"]["spend"])]
    _tabla(ws, fmt, heads, rows, [34, 22, 9, 12, 14, 18, 10, 9, 10, 9, 16, 14, 16, 16, 18])

    ws = wb.add_worksheet("Publicaciones")
    heads = [("Publicación", "txt"), ("Campaña", "txt"), ("Estado", "txt"), ("ROAS", "roas"), ("ROAS objetivo", "roas"), ("Inversión (estimada)", "money"),
             ("Ventas por publicidad (estimadas)", "money"), ("Clics (estimados)", "int"), ("CTR", "pct"), ("CPC", "money"),
             ("Parte de la inversión de su campaña", "pct"), ("Parte de las ventas de su campaña", "pct")]
    rows = [[o["name"], o["camp"], ESTADOS[o["status"]], o["roas"], o["target"], o["spend"], o["sales"], o["clicks"], o["ctr"], o["cpc"], o["shareSpend"], o["shareSales"]]
            for o in sorted(per["items"], key=lambda o: -o["sales"])]
    _tabla(ws, fmt, heads, rows, [48, 30, 22, 9, 12, 16, 20, 14, 9, 10, 20, 20])

    ws = wb.add_worksheet("Por día")
    heads = [("Día", "date"), ("Ventas", "int"), ("Ingresos", "money"), ("Inversión", "money"), ("Clics", "int"), ("Impresiones", "int")]
    rows = [[d["date"], d["units"], d["sales"], d["spend"], d["clicks"], d["prints"]] for d in reversed(per["daily"])]
    _tabla(ws, fmt, heads, rows, [20, 10, 16, 14, 10, 14])
    wb.close()
    return out.getvalue()


def nombre_archivo(data: dict, per_days: int = 30, off: int = 0) -> str:
    per = periodo(data, per_days, off)
    return "lumo-%s-a-%s.xlsx" % (per["from"].strftime("%Y-%m-%d"), per["to"].strftime("%Y-%m-%d"))
