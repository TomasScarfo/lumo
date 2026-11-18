"""Mails de Lumo. Las recomendaciones y el resumen semanal solo se envían cuando la persona los pide con un botón del panel.

No hay envíos automáticos de recomendaciones: el único aviso que sale solo es el de la suscripción (cobro rechazado, fin de prueba).
El envío usa la API web de Brevo (BREVO_API_KEY): va por HTTPS, así que funciona en el plan gratuito de Render, que bloquea el SMTP.
Si no hay clave de Brevo, usa SMTP (por defecto el de Gmail con una contraseña de aplicación, SMTP_PASSWORD). Sin ninguno de los dos, el envío queda apagado.
"""
import base64
import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape
from urllib.parse import urlsplit

import requests
from sqlalchemy.orm import Session

from . import exportar
from .ads import DEFAULT_ROAS_TARGET
from .models import Notice

log = logging.getLogger("lumo")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class MailError(Exception):
    """El proveedor de correo rechazó el envío. El mensaje trae el código y el motivo, nunca la clave."""


def why(exc: Exception) -> str:
    """Para el registro: el tipo de error y, si lo rechazó el proveedor de correo, el motivo que dio."""
    return "%s %s" % (type(exc).__name__, exc) if isinstance(exc, MailError) else type(exc).__name__


def _sender(cfg: dict) -> str:
    return cfg.get("MAIL_FROM") or cfg.get("SMTP_USER") or ""


def enabled(cfg: dict) -> bool:
    if cfg.get("BREVO_API_KEY"):
        return bool(_sender(cfg))
    return bool(cfg.get("SMTP_PASSWORD") and cfg.get("SMTP_USER"))


def _send_brevo(cfg: dict, to: str, subject: str, text: str, html: str, attachments=None) -> None:
    body = {"sender": {"name": "Lumo", "email": _sender(cfg)}, "to": [{"email": to}], "subject": subject, "textContent": text, "htmlContent": html}
    if attachments:
        body["attachment"] = [{"name": name, "content": base64.b64encode(content).decode("ascii")} for name, content in attachments]
    resp = requests.post(BREVO_URL, timeout=30, headers={"api-key": cfg["BREVO_API_KEY"], "accept": "application/json"}, json=body)
    if resp.status_code >= 300:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        raise MailError("Brevo respondió %s (%s): %s" % (resp.status_code, body.get("code", "sin código"), str(body.get("message", ""))[:200]))


XLSX = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def send_mail(cfg: dict, to: str, subject: str, text: str, html: str, attachments=None) -> None:
    """attachments: lista de (nombre, bytes) con archivos .xlsx."""
    if cfg.get("BREVO_API_KEY"):
        _send_brevo(cfg, to, subject, text, html, attachments)
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "Lumo <%s>" % cfg["SMTP_USER"]
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    for name, content in attachments or []:
        msg.add_attachment(content, maintype=XLSX[0], subtype=XLSX[1], filename=name)
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


VIS_DOWN = -0.10   # impresiones: caída que se considera pérdida de visibilidad (igual que el panel)
VIS_UP = 0.10
ROAS_DOWN = -0.05


def _prints(c, a, b) -> float:
    return sum(d["prints"] for d in c["daily"][a:b])


def weekly(data: dict) -> dict:
    """Resumen de los últimos 7 días contra los 7 anteriores, con el mismo criterio de estados y de visibilidad que el panel."""
    camps = data["camps"]
    spend, sales = _sum(camps, -7, None, "spend"), _sum(camps, -7, None, "sales")
    pspend, psales = _sum(camps, -14, -7, "spend"), _sum(camps, -14, -7, "sales")
    raw = {c["id"]: c for c in camps}
    opp, up, vis = [], [], []
    for r in exportar.periodo(data, 7)["camps"]:
        c = raw[r["id"]]
        cur_p, prev_p = _prints(c, -7, None), _prints(c, -14, -7)
        v = cur_p / prev_p - 1 if prev_p else None
        row = {"name": r["name"], "roas": r["roas"], "target": r["target"], "trend": r["trend"], "vis": v, "spend": r["cur"]["spend"]}
        if r["status"] in ("oportunidad", "revisar"):
            opp.append((r["target"] * r["cur"]["spend"] - r["cur"]["sales"], row))
        elif r["status"] == "mejorando":
            up.append((r["cur"]["spend"], row))
        if r["cur"]["sales"] > 0 and v is not None and v <= VIS_DOWN:
            vis.append((r["cur"]["spend"], dict(row, kind="baja")))
        elif v is not None and v >= VIS_UP and r["trend"] is not None and r["trend"] <= ROAS_DOWN:
            vis.append((r["cur"]["spend"], dict(row, kind="sube")))
        elif r["status"] == "supera":
            vis.append((r["cur"]["spend"], dict(row, kind="margen")))
    top = lambda lst: [row for _, row in sorted(lst, key=lambda x: -x[0])[:3]]
    return {"spend": spend, "sales": sales, "roas": sales / spend if spend else 0, "dsales": _pct(sales, psales), "dspend": _pct(spend, pspend),
            "opp": top(opp), "up": top(up), "vis": top(vis)}


def _logo(link: str) -> str:
    """El logo (el amanecer) como imagen: los mails no pueden usar SVG, así que se pide el PNG que sirve la app."""
    u = urlsplit(link)
    if u.scheme not in ("http", "https") or not u.netloc:
        return ""
    src = "%s://%s/static/logo.png" % (u.scheme, u.netloc)
    return "<img src='%s' width='44' height='44' alt='Lumo' style='display:block;border:0;border-radius:11px'>" % escape(src, quote=True)


def _layout(title: str, blocks_html: str, blocks_text: str, link: str, why: str, button: str = "Abrir mi panel"):
    html = ("<div style='font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;color:#13202C'>"
            "<table role='presentation' cellpadding='0' cellspacing='0' style='margin:0 0 14px'><tr>"
            "<td style='padding-right:10px;vertical-align:middle'>%s</td>"
            "<td style='vertical-align:middle'><span style='font-size:24px;font-weight:bold;color:#2446D6'>Lumo</span></td></tr></table>"
            "<h1 style='font-size:20px;margin:0 0 16px'>%s</h1>%s"
            "<p style='margin:20px 0'><a href='%s' style='background:#2446D6;color:#fff;padding:10px 16px;border-radius:10px;text-decoration:none'>%s</a></p>"
            "<p style='font-size:12px;color:#5A6B7C'>%s</p></div>") % (_logo(link), escape(title), blocks_html, escape(link, quote=True), escape(button), escape(why))
    text = "%s\n\n%s\n%s: %s\n\n%s\n" % (title, blocks_text, button, link, why)
    return text, html


DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _roas(n: float) -> str:
    return "$" + format(n, ".1f").replace(".", ",")


def _evolucion(per: dict):
    """Inversión día por día del período, con una barra por día (hecha con tablas: los mails no admiten gráficos ni scripts)."""
    daily = per["daily"]
    top = max((d["spend"] for d in daily), default=0)
    if top <= 0:
        return "<p style='color:#5A6B7C'>No hubo inversión en estos días.</p>", "No hubo inversión en estos días.\n"
    rows, text = "", ""
    for d in daily:
        label = "%s %d" % (DIAS[d["date"].weekday()], d["date"].day)
        w = max(1, round(d["spend"] / top * 100)) if d["spend"] > 0 else 0
        bar = "<div style='background:#2446D6;height:12px;border-radius:3px;width:%d%%'></div>" % w if w else ""
        rows += ("<tr><td style='width:58px;padding:3px 8px 3px 0;font-size:13px;color:#44566A;white-space:nowrap'>%s</td>"
                 "<td style='padding:3px 0'>%s</td><td style='width:84px;padding:3px 0 3px 8px;font-size:13px;text-align:right;white-space:nowrap'>%s</td></tr>") % (label, bar, money(d["spend"]))
        text += "  %s: %s\n" % (label, money(d["spend"]))
    return "<table role='presentation' cellpadding='0' cellspacing='0' width='100%%'>%s</table>" % rows, text


def _top(per: dict):
    """Las 5 publicaciones que más ventas por publicidad aportaron. Las cifras por publicación son una estimación (se reparten según su peso en la campaña)."""
    top = exportar.top_publicaciones(per, 5)
    if not top:
        return "<p style='color:#5A6B7C'>Todavía no hay publicaciones con ventas por publicidad en este período.</p>", "Todavía no hay publicaciones con ventas por publicidad en este período.\n"
    total = per["tot"]["sales"]
    h, t = "<ol style='padding-left:20px;margin:6px 0'>", ""
    for o in top:
        pct = round(o["sales"] / total * 100) if total else 0
        name = o["name"] if len(o["name"]) <= 70 else o["name"][:67] + "…"
        detail = "vendió %s con publicidad (%d%% del total), invirtió %s, ROAS %s" % (money(o["sales"]), pct, money(o["spend"]), _roas(o["roas"]))
        h += "<li style='margin:7px 0'><b>%s</b><br><span style='font-size:13px;color:#44566A'>%s</span></li>" % (escape(name), escape(detail))
        t += "  %d. %s: %s\n" % (top.index(o) + 1, name, detail)
    return h + "</ol>", t


def weekly_mail(data: dict, link: str, why: str):
    w = weekly(data)
    per = exportar.periodo(data, 7)
    rows = [("Invertiste", money(w["spend"]), w["dspend"]), ("Vendiste con publicidad", money(w["sales"]), w["dsales"]), ("ROAS", _roas(w["roas"]), None)]
    h = "".join("<p style='margin:6px 0'><b>%s:</b> %s%s</p>" % (escape(a), escape(b), (" <span style='color:#5A6B7C'>(%s)</span>" % escape(c)) if c else "") for a, b, c in rows)
    t = "".join("%s: %s%s\n" % (a, b, " (%s)" % c if c else "") for a, b, c in rows)
    evo_h, evo_t = _evolucion(per)
    h += "<h3 style='font-size:16px;margin:22px 0 6px'>Cómo evolucionó tu inversión</h3>" + evo_h
    t += "\nCómo evolucionó tu inversión:\n" + evo_t
    top_h, top_t = _top(per)
    h += "<h3 style='font-size:16px;margin:22px 0 2px'>Las 5 publicaciones que más aportaron</h3>" + top_h
    h += "<p style='font-size:12px;color:#5A6B7C;margin:2px 0 0'>Las cifras por publicación son estimadas: se reparten según lo que cada una aportó a su campaña.</p>"
    t += "\nLas 5 publicaciones que más aportaron (cifras estimadas):\n" + top_t
    def seccion(titulo, nota, items, linea):
        nonlocal h, t
        if not items:
            return
        h += "<h3 style='font-size:16px;margin:22px 0 4px'>%s</h3><p style='margin:0;color:#5A6B7C;font-size:13px'>%s</p><ul>%s</ul>" % (
            escape(titulo), escape(nota), "".join("<li>%s</li>" % escape(linea(x)) for x in items))
        t += "\n%s (%s):\n%s" % (titulo, nota, "".join("- %s\n" % linea(x) for x in items))

    def vs(x):
        return "ROAS %s (objetivo %s)" % (_roas(x["roas"]), _roas(x["target"]))

    def cambio(x, k, que):
        return " Sus %s %s %d%% contra la semana anterior." % (que, "subieron" if x[k] > 0 else "bajaron", round(abs(x[k]) * 100))

    seccion("Campañas con oportunidad de mejora", "Están por debajo de su ROAS objetivo: no es que estén mal, hay margen para mejorarlas.", w["opp"], lambda x: "%s: %s." % (x["name"], vs(x)))
    seccion("Campañas que vienen mejorando", "Siguen por debajo de su objetivo, pero su ROAS sube y se acerca.", w["up"],
            lambda x: "%s: %s." % (x["name"], vs(x)) + (" Su ROAS subió %d%% contra la semana anterior." % round(x["trend"] * 100) if x["trend"] else ""))

    def linea_vis(x):
        if x["kind"] == "baja":
            return "%s perdió visibilidad.%s Bajar un poco el ROAS objetivo ayuda a recuperarla, a cambio de algo de rentabilidad." % (x["name"], cambio(x, "vis", "impresiones"))
        if x["kind"] == "sube":
            return "%s gana visibilidad pero cae su ROAS.%s Subir un poco el ROAS objetivo recupera rentabilidad." % (x["name"], cambio(x, "vis", "impresiones"))
        return "%s rinde por encima de su objetivo (%s). Tiene margen para ganar visibilidad bajando el ROAS objetivo." % (x["name"], vs(x))

    seccion("Visibilidad y ROAS objetivo", "Un ROAS objetivo más bajo hace que te muestres más, con menos rentabilidad. Uno más alto, al revés.", w["vis"], linea_vis)
    if not (w["opp"] or w["up"] or w["vis"]):
        h += "<p>Todas tus campañas con inversión están en su ROAS objetivo.</p>"
        t += "\nTodas tus campañas con inversión están en su ROAS objetivo.\n"
    h += "<p style='font-size:13px;color:#44566A;margin:16px 0 0'>Te adjuntamos un Excel con las mismas tablas que ves en el panel: campañas, publicaciones y días.</p>"
    t += "\nTe adjuntamos un Excel con las mismas tablas que ves en el panel: campañas, publicaciones y días.\n"
    return ("Tu resumen semanal de Lumo",) + _layout("Cómo te fue en los últimos 7 días", h, t, link, why)


def weekly_excel(data: dict):
    """El Excel que acompaña al resumen semanal: las mismas tablas del panel, de los últimos 7 días."""
    return exportar.nombre_archivo(data, 7), exportar.excel(data, 7)


def recommendation_mail(title: str, text: str, action: str, link: str, why: str):
    """Una recomendación del panel, tal como la ve la persona. Todo el texto se escapa: viene del navegador."""
    h = "<p style='margin:0 0 10px'>%s</p>" % escape(text)
    if action:
        h += "<p style='margin:12px 0;padding:12px;background:#E3E9FC;border-radius:10px'><b>Qué podés hacer:</b> %s</p>" % escape(action)
    t = text + ("\n\nQué podés hacer: " + action if action else "")
    return ("Recomendación de Lumo: " + title,) + _layout(title, h, t, link, why)


def login_mail(link: str, minutes: int):
    """El enlace para entrar a Lumo sin contraseña."""
    h = "<p style='margin:6px 0'>Tocá el botón para entrar a Lumo. El enlace sirve <b>una sola vez</b> y vence en %d minutos.</p>" % minutes
    t = "Tocá el enlace para entrar a Lumo. Sirve una sola vez y vence en %d minutos." % minutes
    why = "Te escribimos porque alguien pidió entrar a Lumo con este email. Si no fuiste vos, ignorá este mensaje: no pasa nada."
    return ("Tu enlace para entrar a Lumo",) + _layout("Entrá a Lumo", h, t, link, why, button="Entrar a Lumo")


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


def admin_mail(title: str, rows: list, link: str):
    """Aviso para quien administra Lumo: qué pasó con una suscripción, en una línea por dato."""
    h = "<table style='border-collapse:collapse'>" + "".join(
        "<tr><td style='padding:4px 12px 4px 0;color:#5B6B7B'>%s</td><td style='padding:4px 0'><b>%s</b></td></tr>" % (escape(k), escape(str(v)))
        for k, v in rows if v not in (None, "")) + "</table>"
    t = "\n".join("%s: %s" % (k, v) for k, v in rows if v not in (None, "")) + "\n"
    return ("Lumo · " + title,) + _layout(title, h, t, link, "Te escribimos porque administrás Lumo.", "Abrir la administración")


def _due(s: Session, uid: int, kind: str, ref: str, every: timedelta, now) -> bool:
    row = s.get(Notice, (uid, kind, ref))
    return row is None or now - row.sent_at >= every


def _mark(s: Session, uid: int, kind: str, ref: str, now) -> None:
    row = s.get(Notice, (uid, kind, ref)) or Notice(user_id=uid, kind=kind, ref=ref)
    row.sent_at = now
    s.add(row)
