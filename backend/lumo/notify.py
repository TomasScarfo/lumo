"""Avisos por email: resumen semanal, publicaciones que gastan sin vender y las que venden bien sin publicidad.

Solo reciben avisos las cuentas que los activaron en la pestaña Alertas (m1, m2, m3). Un chequeo diario (ver
`.github/workflows/avisos.yml`) llama a /cron/avisos. Cada aviso se registra en la tabla `notice` para no repetirlo.
El envío usa SMTP (por defecto el de Gmail con una contraseña de aplicación) y queda apagado mientras falte SMTP_PASSWORD.
"""
import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ads import DEFAULT_ROAS_TARGET
from .models import Notice, utcnow

log = logging.getLogger("lumo")

MIN_SPEND = 10000.0       # pesos invertidos en 30 días, sin ventas, para avisar que una publicación gasta sin vender
URGENT_EVERY = timedelta(days=7)
ORGANIC_EVERY = timedelta(days=14)
WEEKLY_DAYS = (0, 1, 2)   # lunes; si el chequeo falló ese día, se reintenta martes y miércoles
KINDS = ("m1", "m2", "m3")


def enabled(cfg: dict) -> bool:
    return bool(cfg.get("SMTP_PASSWORD") and cfg.get("SMTP_USER"))


def send_mail(cfg: dict, to: str, subject: str, text: str, html: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "Lumo <%s>" % cfg["SMTP_USER"]
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"]), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        smtp.send_message(msg)


def money(n: float) -> str:
    return "$" + format(int(round(n)), ",").replace(",", ".")


def _sum(camps, a, b, key):
    return sum(d[key] for c in camps for d in c["daily"][a:b])


def _pct(cur, prev):
    if not prev:
        return None
    d = cur / prev - 1
    if abs(d) < 0.02:
        return "igual que la semana anterior"
    return "%d%% %s que la semana anterior" % (round(abs(d) * 100), "más" if d > 0 else "menos")


def _target(c) -> float:
    return c.get("target") or DEFAULT_ROAS_TARGET


def weekly(data: dict) -> dict:
    camps = data["camps"]
    spend, sales = _sum(camps, -7, None, "spend"), _sum(camps, -7, None, "sales")
    pspend, psales = _sum(camps, -14, -7, "spend"), _sum(camps, -14, -7, "sales")
    below = []
    for c in camps:
        sp, sa = sum(d["spend"] for d in c["daily"][-7:]), sum(d["sales"] for d in c["daily"][-7:])
        if sp > 0 and sa / sp < _target(c):
            below.append((sp * _target(c) - sa, c["name"], sa / sp, _target(c)))
    below.sort(reverse=True)
    return {"spend": spend, "sales": sales, "roas": sales / spend if spend else 0, "dsales": _pct(sales, psales), "dspend": _pct(spend, pspend),
            "below": [(n, r, t) for _, n, r, t in below[:3]]}


def wasteful(data: dict) -> list:
    """Publicaciones con anuncios activos que gastaron y no vendieron nada en 30 días. Devuelve (id, nombre, gasto)."""
    by = {str(c["id"]): c for c in data["camps"]}
    out = []
    for it in data["items"]:
        c = by.get(str(it.get("camp")))
        if not c:
            continue
        sp30 = sum(d["spend"] for d in c["daily"][-30:]) * it["sp"]
        sa30 = sum(d["sales"] for d in c["daily"][-30:]) * it["sa"]
        if sa30 == 0 and sp30 >= MIN_SPEND:
            out.append((it["id"], it["name"], sp30))
    return sorted(out, key=lambda x: -x[2])


def organic(data: dict) -> list:
    """Publicaciones sin publicidad que venden bien solas (mismo criterio que la pestaña Alertas). Devuelve (id, nombre, unidades)."""
    out = []
    for it in data["items"]:
        conv = it.get("conv")
        prev = it.get("prevUnits") or 0
        growth = it["units"] / prev - 1 if prev else 0
        if it.get("camp") is None and it["units"] >= 10 and (conv is None or conv >= 0.03) and growth >= 0:
            out.append((it["id"], it["name"], it["units"]))
    return sorted(out, key=lambda x: -x[2])


def _layout(title: str, blocks_html: str, blocks_text: str, link: str, why: str, button: str = "Abrir mi panel"):
    html = ("<div style='font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;color:#13202C'>"
            "<h2 style='margin:0 0 4px;color:#2446D6'>Lumo</h2><h1 style='font-size:20px;margin:0 0 16px'>%s</h1>%s"
            "<p style='margin:20px 0'><a href='%s' style='background:#2446D6;color:#fff;padding:10px 16px;border-radius:10px;text-decoration:none'>%s</a></p>"
            "<p style='font-size:12px;color:#5A6B7C'>%s</p></div>") % (escape(title), blocks_html, escape(link, quote=True), escape(button), escape(why))
    text = "%s\n\n%s\n%s: %s\n\n%s\n" % (title, blocks_text, button, link, why)
    return text, html


def weekly_mail(data: dict, link: str, why: str):
    w = weekly(data)
    rows = [("Invertiste", money(w["spend"]), w["dspend"]), ("Vendiste con publicidad", money(w["sales"]), w["dsales"]), ("ROAS", "$%s" % format(w["roas"], ".1f").replace(".", ","), None)]
    h = "".join("<p style='margin:6px 0'><b>%s:</b> %s%s</p>" % (escape(a), escape(b), (" <span style='color:#5A6B7C'>(%s)</span>" % escape(c)) if c else "") for a, b, c in rows)
    t = "".join("%s: %s%s\n" % (a, b, " (%s)" % c if c else "") for a, b, c in rows)
    if w["below"]:
        h += "<p style='margin:14px 0 4px'><b>Campañas con oportunidad de mejora (por debajo de su ROAS objetivo)</b></p><ul>" + "".join(
            "<li>%s: ROAS $%s (objetivo $%s)</li>" % (escape(n), format(r, ".1f").replace(".", ","), format(tg, ".1f").replace(".", ",")) for n, r, tg in w["below"]) + "</ul>"
        t += "\nCampañas con oportunidad de mejora (por debajo de su ROAS objetivo):\n" + "".join("- %s: ROAS $%s (objetivo $%s)\n" % (n, format(r, ".1f").replace(".", ","), format(tg, ".1f").replace(".", ",")) for n, r, tg in w["below"])
    else:
        h += "<p>Todas tus campañas con inversión están en su ROAS objetivo o por encima.</p>"
        t += "\nTodas tus campañas con inversión están en su ROAS objetivo o por encima.\n"
    return ("Tu resumen semanal de Lumo",) + _layout("Cómo te fue en los últimos 7 días", h, t, link, why)


def list_mail(subject: str, title: str, intro: str, lines: list, link: str, why: str):
    h = "<p>%s</p><ul>%s</ul>" % (escape(intro), "".join("<li>%s</li>" % escape(x) for x in lines))
    t = intro + "\n" + "".join("- %s\n" % x for x in lines)
    return (subject,) + _layout(title, h, t, link, why)


def billing_mail(kind: str, link: str, until: datetime = None, days: int = None, price: str = None, plan: str = None):
    """Avisos de la suscripción: "pago" (cobro rechazado), "baja" (acceso suspendido) y "prueba" (la prueba gratis termina y viene el primer cobro)."""
    why = "Te escribimos porque tenés una cuenta en Lumo. Este aviso es sobre tu suscripción."
    if kind == "pago":
        subject = title = "No pudimos cobrar tu suscripción de Lumo"
        lines = ["Mercado Pago rechazó el cobro de tu suscripción.",
                 "Tu acceso sigue activo hasta el %s. Para no perderlo, revisá tu medio de pago en Mercado Pago o volvé a suscribirte desde Lumo." % until.strftime("%d/%m/%Y")]
    elif kind == "baja":
        subject = title = "Tu acceso a Lumo quedó en pausa"
        lines = ["No pudimos cobrar tu suscripción y se terminó el plazo para regularizarla.",
                 "No borramos nada: tus datos y tus tareas te esperan. Cuando vuelvas a suscribirte, seguís donde lo dejaste."]
    else:
        subject = title = "Tu prueba gratis de Lumo termina %s" % ("mañana" if days == 1 else "en %d días" % days)
        what = "tu plan %s" % plan if plan else "tu plan"
        lines = ["El %s Mercado Pago hace el primer cobro de %s%s." % (until.strftime("%d/%m/%Y"), what, " (%s)" % price if price else ""),
                 "Si querés seguir, no tenés que hacer nada. Si no, cancelá antes de esa fecha desde tu suscripción y no se te cobra."]
    h = "".join("<p>%s</p>" % escape(x) for x in lines)
    return (subject,) + _layout(title, h, "\n".join(lines) + "\n", link, why, "Ver mi suscripción")


def _due(s: Session, uid: int, kind: str, ref: str, every: timedelta, now) -> bool:
    row = s.get(Notice, (uid, kind, ref))
    return row is None or now - row.sent_at >= every


def _mark(s: Session, uid: int, kind: str, ref: str, now) -> None:
    row = s.get(Notice, (uid, kind, ref)) or Notice(user_id=uid, kind=kind, ref=ref)
    row.sent_at = now
    s.add(row)


def run_for(s: Session, cfg: dict, uid: int, email: str, prefs: dict, data: dict, link: str, now: datetime = None, send=None) -> list:
    """Envía lo que corresponda a una cuenta y devuelve los tipos enviados."""
    send = send or send_mail
    now = now or utcnow()  # hora UTC sin zona, como se guarda en la base
    local = now + timedelta(hours=-3)  # Argentina
    why = "Recibís este mail porque activaste los avisos en Lumo. Podés desactivarlos cuando quieras en la pestaña Alertas de tu panel."
    sent = []
    if prefs.get("m1") and local.weekday() in WEEKLY_DAYS:
        wk = "%d-W%02d" % local.isocalendar()[:2]
        if _due(s, uid, "m1", wk, timedelta(days=1000), now):
            send(cfg, email, *weekly_mail(data, link, why))
            _mark(s, uid, "m1", wk, now)
            sent.append("m1")
    if prefs.get("m2"):
        items = [x for x in wasteful(data) if _due(s, uid, "m2", str(x[0]), URGENT_EVERY, now)]
        if items:
            lines = ["%s: invirtió %s en 30 días y no vendió nada" % (n, money(sp)) for _, n, sp in items[:10]]
            send(cfg, email, *list_mail("Publicaciones que gastan y no venden", "Revisá estas publicaciones", "Tienen anuncios activos, gastaron y no tuvieron ninguna venta por publicidad:", lines, link, why))
            for iid, _, _ in items:
                _mark(s, uid, "m2", str(iid), now)
            sent.append("m2")
    if prefs.get("m3"):
        items = [x for x in organic(data) if _due(s, uid, "m3", str(x[0]), ORGANIC_EVERY, now)]
        if items:
            lines = ["%s: %d unidades vendidas en 30 días sin publicidad" % (n, u) for _, n, u in items[:10]]
            send(cfg, email, *list_mail("Publicaciones que venden bien sin publicidad", "Una oportunidad para activar publicidad", "Estas publicaciones ya venden solas. Activarlas en publicidad puede ayudarlas a vender más:", lines, link, why))
            for iid, _, _ in items:
                _mark(s, uid, "m3", str(iid), now)
            sent.append("m3")
    s.commit()
    return sent
