"""Cuenta ficticia pero verosímil para el video de demo: una tienda de deco y hogar en Mercado Libre Argentina."""
import json, math, random, sys
from datetime import datetime, timedelta, timezone

random.seed(7)
END = datetime(2026, 11, 18)
DAYS = 90

CAMPS = [  # id, nombre, presupuesto diario, ROAS objetivo, ROAS real (inicio, fin), cpc, ctr, ticket, share, topShare, lostB, lostR
    (201, "Organizadores de cocina", 18000, 6.0, (7.8, 8.6), 140, 0.016, 21000, .52, .21, .08, .18),
    (202, "Iluminación LED", 22000, 5.0, (5.0, 5.3), 165, 0.012, 34000, .44, .16, .12, .30),
    (203, "Ropa de cama", 15000, 5.0, (3.9, 3.5), 190, 0.010, 52000, .31, .09, .35, .22),
    (204, "Cortinas blackout", 12000, 4.0, (2.3, 3.6), 175, 0.011, 39000, .27, .07, .18, .41),
    (205, "Alfombras", 9000, 5.0, (2.6, 1.4), 210, 0.008, 68000, .19, .04, .10, .55),
]
ITEMS = [  # camp, nombre, categoría, marca, precio, reparto (gasto, ventas), unidades orgánicas 30 días (actual, anterior), stock
    (201, "Organizador giratorio de especias 360°", "Cocina", "Ordenia", 18900, (.45, .55), (64, 51), 140),
    (201, "Set de 6 frascos herméticos de vidrio", "Cocina", "Ordenia", 24500, (.35, .33), (41, 38), 85),
    (201, "Escurridor de platos plegable", "Cocina", "Kasa", 15900, (.20, .12), (22, 25), 60),
    (202, "Tira LED RGB 5 m con control", "Iluminación", "Lumina", 21900, (.40, .48), (57, 44), 210),
    (202, "Lámpara colgante nórdica de madera", "Iluminación", "Lumina", 48900, (.35, .37), (18, 15), 34),
    (202, "Velador táctil recargable", "Iluminación", "Brilla", 26500, (.25, .15), (12, 14), 48),
    (203, "Sábanas 400 hilos 2 plazas", "Dormitorio", "Algodonera", 54900, (.50, .58), (33, 36), 70),
    (203, "Acolchado reversible queen", "Dormitorio", "Algodonera", 79900, (.30, .34), (14, 17), 22),
    (203, "Funda de almohada de bambú (x2)", "Dormitorio", "Sueño Puro", 17900, (.20, .08), (9, 11), 120),
    (204, "Cortina blackout térmica 140x220", "Deco", "Penumbra", 36900, (.55, .62), (29, 21), 95),
    (204, "Barral extensible 1,2 a 2,4 m", "Deco", "Penumbra", 19900, (.45, .38), (26, 19), 130),
    (205, "Alfombra shaggy 160x230", "Deco", "Tejer", 89900, (.60, .70), (6, 8), 12),
    (205, "Alfombra de yute redonda 120 cm", "Deco", "Tejer", 64900, (.40, .30), (3, 5), 9),
    (None, "Perchero de pie de madera", "Deco", "Kasa", 42900, (0, 0), (38, 24), 18),
    (None, "Espejo redondo 60 cm marco negro", "Deco", "Reflejo", 58900, (0, 0), (27, 19), 15),
    (None, "Organizador de cajones (set x6)", "Cocina", "Ordenia", 12900, (0, 0), (85, 79), 260),
]


def series(camp):
    cid, name, budget, target, (r0, r1), cpc, ctr, ticket = camp[:8]
    out = []
    for d in range(DAYS):
        day = END - timedelta(days=DAYS - 1 - d)
        if cid == 206 and d > DAYS - 25:  # pausada hace 3 semanas
            out.append({"spend": 0.0, "clicks": 0.0, "prints": 0.0, "units": 0.0, "sales": 0.0})
            continue
        t = d / (DAYS - 1)
        wk = 1.12 if day.weekday() in (0, 1, 6) else (0.9 if day.weekday() == 5 else 1.0)  # domingo a martes se vende más
        promo = 1.25 if datetime(2026, 11, 3) <= day <= datetime(2026, 11, 5) else 1.0  # CyberMonday
        spend = round(budget * random.uniform(.72, .98) * wk * promo)
        roas = (r0 + (r1 - r0) * (t ** 2 if cid in (204, 205) else t)) * random.uniform(.85, 1.15) * (1.15 if promo > 1 else 1)
        sales = round(spend * roas, -2)
        clicks = round(spend / (cpc * random.uniform(.9, 1.1)))
        prints = round(clicks / (ctr * random.uniform(.85, 1.15)))
        units = max(0, round(sales / ticket + random.uniform(-.4, .4)))
        sales = float(units * ticket * random.uniform(.92, 1.08)) if units else 0.0
        out.append({"spend": float(spend), "clicks": float(clicks), "prints": float(prints), "units": float(units), "sales": round(sales, -2)})
    return out


def build(now_iso):
    camps = []
    for c in CAMPS:
        cid, name, budget, target, _, _, _, _, share, top, lostB, lostR = c
        camps.append({"id": cid, "name": name, "status": "paused" if cid == 206 else "active", "budget": float(budget), "strategy": "PROFITABILITY",
                      "acosTarget": round(100 / target, 1), "target": target, "estTarget": False, "daily": series(c),
                      "share": share, "topShare": top, "lostB": lostB, "lostR": lostR, "benchmark": 18})
    items = []
    for n, (camp, name, cat, brand, price, (sp, sa), (u, pu), stock) in enumerate(ITEMS):
        visits = round(u / random.uniform(.025, .045)) if u else 400
        items.append({"id": "MLA%d" % (1460000000 + n * 7919), "name": name, "cat": cat, "brand": brand, "camp": camp, "sp": sp, "sa": sa, "kc": sp, "kp": sp,
                      "price": float(price), "units": float(u), "prevUnits": float(pu), "orgAmt": float(u * price), "prevOrgAmt": float(pu * price),
                      "visits": float(visits), "conv": round(u / visits, 4), "stock": stock, "link": None})
    return {"advertiser": {"id": 3920417, "name": "Alma Deco Hogar", "site": "MLA"}, "end": END.strftime("%Y-%m-%d"), "days": DAYS,
            "fetchedAt": now_iso, "camps": camps, "items": items, "notes": [],
            "advertisers": [{"id": 3920417, "name": "Alma Deco Hogar", "site": "MLA"}], "estado": {}, "email": "hola@almadeco.com.ar",
            "mailOn": True, "admin": False, "uid": 3920417, "plan": {"kind": "paid", "days": None, "pastDue": False}}


if __name__ == "__main__":
    json.dump(build("2026-11-19T09:12:00-03:00"), open(sys.argv[1], "w"), ensure_ascii=False)
