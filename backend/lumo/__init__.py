import json
import logging
import os
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, Response, abort, jsonify, redirect, render_template, render_template_string, request, session
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from werkzeug.middleware.proxy_fix import ProxyFix

from . import access, ads, audit, billing, cuenta, history, ml, notify, privacy, security
from .models import Access, Account, AuditLog, Base, Invite, Notice, PanelState, Snapshot, Subscription, utcnow
from .tokens import NeedsReconnect, save_tokens, valid_access_token

log = logging.getLogger("lumo")

SNAPSHOT_TTL = timedelta(hours=3)  # Mercado Libre actualiza los datos una vez al día
MIN_REFRESH = timedelta(minutes=10)  # tope para el botón "Actualizar"
MAX_STATE_BYTES = 200_000
MAX_REQUEST_BYTES = 1_000_000
TERMS_UPDATED = "10 de noviembre de 2026"  # cambiar cuando cambien los términos y condiciones
SESSION_DAYS = 30
ADMIN_SESSION_HOURS = 12  # quien administra vuelve a pasar por Mercado Libre pasadas estas horas

PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lumo</title>
<style>
:root{color-scheme:light dark;--bg:#f2f5f8;--card:#fff;--ink:#13202c;--ink2:#44566a;--accent:#2446d6;--ok:#146c43;--bad:#b42318;--line:#dae2e9}
@media (prefers-color-scheme:dark){:root{--bg:#0b131a;--card:#131e28;--ink:#e7edf3;--ink2:#b1becb;--accent:#8ba0ff;--ok:#52cc8c;--bad:#ff8f83;--line:#263543}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;padding:24px 16px}
main{max-width:560px;margin:8vh auto 0;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px}
h1{margin:0 0 8px;font-size:1.6rem}p{color:var(--ink2);margin:8px 0}
.btn{display:inline-block;margin-top:16px;background:var(--accent);color:#fff;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:10px}
@media (prefers-color-scheme:dark){.btn{color:#0b131a}}
.ok{color:var(--ok);font-weight:700}.bad{color:var(--bad);font-weight:700}
ul{padding-left:20px}li{margin:4px 0}code{background:var(--line);padding:1px 6px;border-radius:6px}
</style></head><body><main>{{ body|safe }}</main></body></html>"""


def page(body: str, status: int = 200):
    return render_template_string(PAGE, body=body), status


def load_config(overrides=None) -> dict:
    cfg = {
        "ML_CLIENT_ID": os.environ.get("ML_CLIENT_ID", ""),
        "ML_CLIENT_SECRET": os.environ.get("ML_CLIENT_SECRET", ""),
        "REDIRECT_URI": os.environ.get("REDIRECT_URI", ""),
        "ENCRYPTION_KEY": os.environ.get("ENCRYPTION_KEY", ""),
        # Claves anteriores (separadas por coma) mientras se rota ENCRYPTION_KEY. Ver crypto.py.
        "ENCRYPTION_KEY_PREVIOUS": os.environ.get("ENCRYPTION_KEY_PREVIOUS", ""),
        "SECRET_KEY": os.environ.get("SECRET_KEY", ""),
        "DATABASE_URL": os.environ.get("DATABASE_URL", "sqlite:///lumo.db"),
        "ML_AUTH_BASE": os.environ.get("ML_AUTH_BASE", "https://auth.mercadolibre.com.ar"),
        "ML_API_BASE": os.environ.get("ML_API_BASE", "https://api.mercadolibre.com"),
        "ADMIN_USER_IDS": os.environ.get("ADMIN_USER_IDS", ""),
        "CONTACT_EMAIL": os.environ.get("CONTACT_EMAIL", "lumoads.ml@gmail.com"),
        # Avisos por email. Sin SMTP_PASSWORD (contraseña de aplicación de Gmail) no se envía nada.
        "SMTP_HOST": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "SMTP_PORT": os.environ.get("SMTP_PORT", "587"),
        "SMTP_USER": os.environ.get("SMTP_USER", os.environ.get("CONTACT_EMAIL", "lumoads.ml@gmail.com")),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", ""),
        "CRON_TOKEN": os.environ.get("CRON_TOKEN", ""),
        "CONTACT_WHATSAPP": os.environ.get("CONTACT_WHATSAPP", "5491145597516"),
        # Cobro con Mercado Pago. Sin MP_ACCESS_TOKEN, la prueba gratis funciona igual pero no se puede pagar.
        "MP_ACCESS_TOKEN": os.environ.get("MP_ACCESS_TOKEN", ""),
        "MP_WEBHOOK_SECRET": os.environ.get("MP_WEBHOOK_SECRET", ""),
        "MP_API_BASE": os.environ.get("MP_API_BASE", "https://api.mercadopago.com"),
        # Precios en dólares. Se cobran en pesos a la cotización del día (USD_RATE_URL, campo "venta"; USD_ARS_RATE la fija a mano).
        "PLAN_PRICE_USD": os.environ.get("PLAN_PRICE_USD", "5.99"),
        "PLAN_PRICE_ANNUAL_USD": os.environ.get("PLAN_PRICE_ANNUAL_USD", "59.99"),
        "USD_RATE_URL": os.environ.get("USD_RATE_URL", "https://dolarapi.com/v1/dolares/oficial"),
        "USD_ARS_RATE": os.environ.get("USD_ARS_RATE", ""),
        # Dominios donde Mercado Pago muestra el pago. La página de suscripción solo deja salir hacia ellos.
        "MP_CHECKOUT_ORIGINS": os.environ.get("MP_CHECKOUT_ORIGINS", "https://www.mercadopago.com.ar https://www.mercadopago.com https://sandbox.mercadopago.com.ar"),
        "TRIAL_DAYS": os.environ.get("TRIAL_DAYS", "14"),
        "GRACE_DAYS": os.environ.get("GRACE_DAYS", "7"),  # días que sigue entrando una cuenta con un cobro rechazado
        # Dirección de la portada publicada aparte (servicio estático de Render). Vacía: la app sirve la portada.
        "SITE_URL": os.environ.get("SITE_URL", "").rstrip("/"),
    }
    cfg.update(overrides or {})
    return cfg


def make_engine(url: str):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    if url in ("sqlite://", "sqlite:///:memory:"):
        return create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    if url.startswith("postgresql") and "sslmode" not in url:
        return create_engine(url, pool_pre_ping=True, connect_args={"sslmode": "require"})  # la base siempre por conexión cifrada
    return create_engine(url, pool_pre_ping=True)


def create_app(overrides=None) -> Flask:
    cfg = load_config(overrides)
    prod = cfg["REDIRECT_URI"].startswith("https://")
    if prod and not cfg["SECRET_KEY"]:
        # Sin clave fija cada proceso firmaría las sesiones con una distinta y la app quedaría a medias: mejor no arrancar.
        raise RuntimeError("Falta SECRET_KEY: sin ella no se pueden firmar las sesiones")
    for name, minimum in (("SECRET_KEY", 16), ("ENCRYPTION_KEY", 32), ("CRON_TOKEN", 32)):
        if prod and cfg[name] and len(cfg[name]) < minimum:
            log.error("%s es demasiado corta (menos de %d caracteres): reemplazala por un valor largo y aleatorio", name, minimum)
    app = Flask(__name__)
    app.config["SECRET_KEY"] = cfg["SECRET_KEY"] or secrets.token_hex(32)
    app.config["SESSION_COOKIE_SECURE"] = prod
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if prod:
        app.config["SESSION_COOKIE_NAME"] = "__Host-lumo"  # el navegador la acepta solo por HTTPS, sin Domain y con Path=/
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # Render termina el HTTPS: así vemos la IP y el esquema reales
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    app.permanent_session_lifetime = timedelta(days=SESSION_DAYS)
    limiter = security.RateLimiter()
    engine = make_engine(cfg["DATABASE_URL"])
    had_access_table = inspect(engine).has_table("access")
    Base.metadata.create_all(engine)
    _widen_scope(engine)
    _add_email_column(engine)
    if not had_access_table:
        _grandfather(engine)
    app.extensions["lumo_cfg"] = cfg
    app.extensions["lumo_engine"] = engine

    def missing_config():
        return [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "REDIRECT_URI", "ENCRYPTION_KEY") if not cfg[k]]

    def _too_many(retry):
        if request.path.startswith("/api/"):
            resp = _json({"error": "espera"}, 429)
        else:
            resp = Response("Demasiados intentos. Esperá un momento y probá de nuevo.", 429, mimetype="text/plain")
        resp.headers["Retry-After"] = str(retry)
        return resp

    @app.before_request
    def _guard():
        path = request.path
        if path.startswith("/static/") or path == "/healthz":
            return None
        rule = security.limit_for(path, request.method)
        if rule and not limiter.allow("%s|%s" % (rule[0], request.remote_addr), rule[1], rule[2]):
            log.warning("tope de pedidos superado en %s", rule[0])
            return _too_many(rule[2])
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not path.startswith("/cron/"):
            # Los navegadores mandan Origin en cada POST: si no es esta misma app, el pedido vino de otro sitio.
            origin = request.headers.get("Origin")
            if (origin and not security.same_origin(origin, request.host)) or request.headers.get("Sec-Fetch-Site") == "cross-site":
                log.warning("pedido de otro origen rechazado en %s", path)
                return Response("Pedido rechazado.", 403, mimetype="text/plain")
        return None

    @app.after_request
    def _secure_headers(resp):
        return security.apply_headers(resp, request.path, prod)

    @app.get("/.well-known/security.txt")
    def security_txt():
        """Cómo avisar de un problema de seguridad (RFC 9116)."""
        contact = cfg.get("CONTACT_EMAIL")
        if not contact:
            abort(404)
        expires = (utcnow() + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Response("Contact: mailto:%s\nExpires: %s\nPreferred-Languages: es, en\n" % (contact, expires), mimetype="text/plain")

    @app.get("/healthz")
    def healthz():
        resp = jsonify({"ok": True})
        resp.headers["Access-Control-Allow-Origin"] = "*"  # la portada publicada aparte lo consulta para despertar al servidor
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/favicon.ico")
    def favicon():
        return redirect("/static/logo.png")

    def _contact(user_id=None, user_email=None):
        """Datos de contacto para la portada. Si no hay ninguno configurado, no se muestra la sección.
        Con el ID (y el email) de quien pide acceso, el mensaje ya sale escrito para que lo habiliten sin pedirle nada más."""
        out = {}
        msg = "Hola, quiero probar Lumo."
        if user_id:
            msg += " Mi ID de Mercado Libre es %s" % user_id + (" y mi email es %s." % user_email if user_email else ".")
        email, wa = cfg.get("CONTACT_EMAIL"), cfg.get("CONTACT_WHATSAPP")
        if email:
            out["email"] = email
            out["mailto"] = "mailto:%s?subject=%s&body=%s" % (email, quote("Acceso a Lumo"), quote(msg))
        digits = re.sub(r"\D", "", wa or "")
        if digits:
            out["whatsapp"] = "https://wa.me/%s?text=%s" % (digits, quote(msg))
            out["phone"] = "+%s %s %s %s %s" % (digits[:2], digits[2], digits[3:5], digits[5:9], digits[9:]) if len(digits) == 13 and digits.startswith("549") else "+" + digits
        return out or None

    def _home():
        site = cfg.get("SITE_URL", "")
        return site if site.startswith("https://") else "/"

    def _offer():
        return {"contact": _contact(), "trial_days": billing.trial_days(cfg), "grace_days": billing.grace_days(cfg), "price": billing.offer(cfg)}
    app.extensions["lumo_offer"] = _offer  # build_site.py la usa para generar la portada estática

    @app.get("/")
    def index():
        miss = missing_config()
        if miss:
            return page("<h1>Lumo</h1><p class='bad'>Falta configurar: %s</p>" % ", ".join("<code>%s</code>" % m for m in miss), 500)
        uid = _current_user()
        if uid:
            return redirect("/admin" if access.is_admin(cfg, uid) else "/panel")
        if _session_uid():
            return redirect("/suscripcion")
        if cfg.get("SITE_URL", "").startswith("https://"):
            return redirect(cfg["SITE_URL"])  # la portada vive aparte y carga al instante
        return render_template("landing.html", invited=False, label=None, **_offer())

    @app.get("/invitacion/<token>")
    def invitacion(token):
        with Session(engine) as s:
            inv = access.valid_invite(s, token)
            label = inv.label if inv else None
        if inv is None:
            return render_template("landing.html", invited=False, label=None, invite_error=True, **_offer()), 404
        session["invite"] = token
        return render_template("landing.html", invited=True, label=label, **_offer())

    @app.get("/entrar")
    def entrar():
        """"Ingresar" de la portada: quien ya tiene sesión en este navegador va directo, sin pasar por Mercado Libre."""
        uid = _session_uid()
        if uid:
            return redirect("/admin" if access.is_admin(cfg, uid) else "/panel" if _current_user() else "/suscripcion")
        return redirect("/connect")

    @app.get("/connect")
    def connect():
        if missing_config():
            return redirect("/")
        if request.args.get("plan") in billing.PLANS:
            session["plan"] = request.args["plan"]  # el plan que eligió en la portada: queda marcado al volver de Mercado Libre
        verifier, challenge = ml.new_pkce()
        state = secrets.token_urlsafe(24)
        session["oauth_state"] = state
        session["pkce_verifier"] = verifier
        return redirect(ml.auth_url(cfg, state, challenge))

    @app.get("/callback")
    def callback():
        if request.args.get("error"):
            return page("<h1>No se pudo conectar</h1><p>Mercado Libre respondió: <code>%s</code></p><a class='btn' href='/'>Volver</a>" % _esc(request.args["error"]), 400)
        expected = session.pop("oauth_state", None)
        verifier = session.pop("pkce_verifier", None)
        state, code = request.args.get("state"), request.args.get("code")
        if not expected or not state or not security.safe_eq(expected, state) or not code or not verifier:
            return page("<h1>No se pudo conectar</h1><p>La sesión venció o el enlace no es válido. Probá de nuevo.</p><a class='btn' href='/'>Volver</a>", 400)
        try:
            tok = ml.exchange_code(cfg, code, verifier)
        except ml.MLError as exc:
            log.warning("exchange_code falló: %s %s", exc.status, exc.code)
            return page("<h1>No se pudo conectar</h1><p>Mercado Libre rechazó el intercambio (<code>%s</code>). Revisá que la dirección de redirección de la app sea exactamente <code>%s</code>.</p>" % (_esc(exc.code), _esc(cfg["REDIRECT_URI"])), 502)
        user_id = int(tok["user_id"])
        invite_token = session.get("invite")
        with Session(engine) as s:
            allowed = access.has_access(s, cfg, user_id)
            if not allowed and invite_token and access.valid_invite(s, invite_token):
                if access.consume_invite(s, invite_token, user_id):
                    inv = s.get(Invite, invite_token)
                    access.grant(s, user_id, inv.label)
                    allowed = True
            acc = save_tokens(s, cfg, user_id, tok)
            acc.email = _read_email(tok["access_token"]) or acc.email
            audit.record(s, "login_ok", actor=user_id)
            s.commit()
        chosen = session.get("plan")
        session.clear()
        if chosen in billing.PLANS:
            session["plan"] = chosen
        session["uid"] = user_id  # Lumo recuerda a la persona en este navegador
        session["at"] = int(time.time())  # cuándo entró: las sesiones de administración vencen antes
        session.permanent = True
        if not allowed:
            log.info("la cuenta %s no tiene una suscripción activa", user_id)  # nueva: va a empezar su prueba gratis
            return redirect("/suscripcion")
        body, ok = _result_body(cfg, tok, user_id)
        if ok:
            return redirect("/panel")
        if access.is_admin(cfg, user_id):
            return redirect("/admin")
        return page(body)

    def _read_email(token):
        """El email de la cuenta de Mercado Libre, para los avisos. Si no se puede leer, los avisos quedan sin destino."""
        try:
            body = ml.api_get(cfg, token, "/users/me", None, None)
        except ml.MLError as exc:
            log.warning("no se pudo leer el email: %s", exc.status)
            return None
        except requests.RequestException as exc:  # sin red o Mercado Libre no responde: la persona entra igual
            log.warning("no se pudo leer el email: %s", type(exc).__name__)
            return None
        mail = body.get("email") if isinstance(body, dict) else None
        if not (isinstance(mail, str) and "@" in mail):
            log.warning("Mercado Libre no devolvió el email; campos recibidos: %s", sorted(body)[:30] if isinstance(body, dict) else type(body).__name__)
            return None
        return mail

    def _session_uid():
        """El id de la cuenta de esta sesión, si está conectada (tenga o no la suscripción al día)."""
        uid = session.get("uid")
        if not uid:
            return None
        with Session(engine) as s:
            acc = s.get(Account, uid)
            return uid if acc and acc.status == "connected" else None

    def _current_user():
        """El id de la cuenta de esta sesión, solo si está conectada y sigue teniendo acceso."""
        uid = _session_uid()
        if not uid:
            return None
        with Session(engine) as s:
            return uid if access.has_access(s, cfg, uid) else None

    @app.get("/panel")
    def panel():
        if not _current_user():
            return redirect("/suscripcion" if _session_uid() else "/")
        data = json.dumps(_contact() or {}).replace("<", "\\u003c")
        resp = Response(PANEL_HTML.replace("</head>", "<script>window.LUMO_CONTACT=%s;</script></head>" % data, 1), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/salir")
    def salir():
        session.clear()
        return redirect(_home())

    def _json(data, status=200):
        resp = jsonify(data)
        resp.status_code = status
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _api_error(exc, advertisers=False):
        """Solo un 404 al listar anunciantes significa que no hay Publicidad habilitada; en otras rutas es otro problema."""
        if exc.status == 404 and advertisers:
            return _json({"error": "no_ads"}, 404)
        kind = {401: "forbidden", 403: "forbidden", 429: "busy"}.get(exc.status, "api")
        detail = ("%s %s %s" % (exc.status, exc.code, exc.path or "/advertising/advertisers")).strip()
        return _json({"error": kind, "detail": detail}, 503 if kind == "busy" else 502)

    def _no_ads(token):
        """Sin Publicidad: se responde con lo que tiene y lo que le falta a la cuenta, para que el panel lo explique."""
        get = lambda path, params=None, version="2": ml.api_get(cfg, token, path, params, version)
        return _json({"error": "no_ads", "cuenta": cuenta.build(get)}, 404)

    @app.get("/api/datos")
    def api_datos():
        uid = _current_user()
        if not uid:
            return _json({"error": "plan"}, 402) if _session_uid() else _json({"error": "login"}, 401)
        want = request.args.get("adv", type=int)
        refresh = request.args.get("refresh") == "1"
        with Session(engine) as s:
            snap = s.get(Snapshot, uid)
            age = utcnow() - snap.fetched_at if snap else None
            limit = MIN_REFRESH if refresh else SNAPSHOT_TTL  # "Actualizar" salta la copia, pero no más de una vez cada 10 minutos
            usable = snap and (want is None or snap.advertiser_id == want) and age < limit
            if usable:
                data = json.loads(snap.data)
            else:
                try:
                    token = valid_access_token(s, cfg, uid)
                except NeedsReconnect:
                    return _json({"error": "reconnect"}, 401)
                try:
                    advs = ml.advertisers(cfg, token)
                except ml.MLError as exc:
                    log.warning("anunciantes falló: %s %s", exc.status, exc.code)
                    if exc.status == 404:
                        return _no_ads(token)
                    return _api_error(exc, advertisers=True)
                if not advs:
                    return _no_ads(token)
                adv = next((a for a in advs if a["advertiser_id"] == want), advs[0])
                get = lambda path, params=None, version="2": ml.api_get(cfg, token, path, params, version)
                try:
                    data = ads.build_dataset(get, adv)
                except ml.MLError as exc:
                    log.warning("lectura de datos falló: %s %s %s", exc.status, exc.code, exc.path)
                    return _api_error(exc)
                data["advertisers"] = [{"id": a["advertiser_id"], "name": a.get("advertiser_name"), "site": a.get("site_id")} for a in advs]
                row = snap or Snapshot(user_id=uid)
                row.advertiser_id, row.data, row.fetched_at = data["advertiser"]["id"], json.dumps(data), utcnow()
                s.add(row)
                s.commit()
                history.save(s, uid, data)
            data = history.extend(s, uid, data)
            st = s.get(PanelState, uid)
            data["estado"] = json.loads(st.data) if st else {}
            acc = s.get(Account, uid)
            if acc and not acc.email and notify.enabled(cfg) and notify._due(s, uid, "mailread", "x", timedelta(hours=1), utcnow()):
                # Cuentas conectadas antes de los avisos: se intenta leer el email una vez por hora, sin pedir que reconecten.
                try:
                    acc.email = _read_email(valid_access_token(s, cfg, uid))
                except NeedsReconnect:
                    pass
                notify._mark(s, uid, "mailread", "x", utcnow())
                s.commit()
            data["email"] = acc.email if acc else None
            data["mailOn"] = notify.enabled(cfg)
            data["admin"] = access.is_admin(cfg, uid)
            data["uid"] = uid
            p = access.plan(s, cfg, uid)
            data["plan"] = {"kind": p["kind"], "days": p.get("days"), "pastDue": bool(p.get("past_due"))}
        return _json(data)

    @app.post("/api/estado")
    def api_estado():
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _json({"error": "formato"}, 400)
        clean = {k: body[k] for k in ("done", "actions", "custom", "sw") if k in body}
        raw = json.dumps(clean)
        if len(raw) > MAX_STATE_BYTES:
            return _json({"error": "grande"}, 413)
        with Session(engine) as s:
            row = s.get(PanelState, uid) or PanelState(user_id=uid)
            row.data = raw
            s.add(row)
            s.commit()
        return _json({"ok": True})

    # ---------- Administración: invitaciones y accesos ----------
    def _app_link():
        base = cfg["REDIRECT_URI"].rsplit("/callback", 1)[0] if cfg["REDIRECT_URI"] else ""
        return base + "/panel#alertas"

    @app.post("/api/email")
    def api_email():
        """La persona escribe su email cuando Mercado Libre no lo informa."""
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        body = request.get_json(silent=True)
        mail = str(body.get("email", "")).strip() if isinstance(body, dict) else ""
        if len(mail) > 200 or not re.fullmatch(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}", mail):
            return _json({"error": "formato"}, 400)
        with Session(engine) as s:
            acc = s.get(Account, uid)
            acc.email = mail
            audit.record(s, "email_set", actor=uid)
            s.commit()
        return _json({"ok": True, "email": mail})

    @app.post("/api/avisos/prueba")
    def avisos_prueba():
        """Manda un mail de prueba a la propia cuenta, para comprobar que los avisos llegan."""
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        if not notify.enabled(cfg):
            return _json({"error": "apagado"}, 503)
        with Session(engine) as s:
            acc = s.get(Account, uid)
            if not acc or not acc.email:
                return _json({"error": "sin_email"}, 400)
            now = utcnow()
            if not notify._due(s, uid, "test", "x", timedelta(minutes=1), now):
                return _json({"error": "espera"}, 429)
            try:
                notify.send_mail(cfg, acc.email, "Prueba de avisos de Lumo", "Si leés esto, los avisos de Lumo te van a llegar a este mail.\n",
                                 "<p>Si leés esto, los avisos de Lumo te van a llegar a este mail.</p>")
            except Exception as exc:  # smtplib y red: no se detalla al usuario
                log.warning("mail de prueba falló: %s", type(exc).__name__)
                return _json({"error": "envio"}, 502)
            notify._mark(s, uid, "test", "x", now)
            s.commit()
            return _json({"ok": True, "email": acc.email})

    @app.post("/cron/avisos")
    def cron_avisos():
        """Lo llama una tarea programada una vez por día. Se protege con la clave CRON_TOKEN."""
        token = cfg["CRON_TOKEN"]
        if not token:
            abort(404)
        if not security.safe_eq(request.headers.get("X-Cron-Token", ""), token):
            log.warning("cron/avisos: clave incorrecta")
            abort(403)
        cobros = _billing_tick()  # no depende del correo: mantiene al día las suscripciones aunque no haya SMTP
        if not notify.enabled(cfg):
            return _json({"ok": False, "motivo": "SMTP_PASSWORD sin configurar", "cobros": cobros}, 503)
        result = {"cuentas": 0, "enviados": 0, "errores": 0}
        with Session(engine) as s:
            rows = s.execute(select(PanelState)).scalars().all()
        for st in rows:
            try:
                prefs = (json.loads(st.data) or {}).get("sw") or {}
            except ValueError:
                continue
            if not any(prefs.get(k) for k in notify.KINDS):
                continue
            result["cuentas"] += 1
            try:
                with Session(engine) as s:
                    acc = s.get(Account, st.user_id)
                    if not acc or acc.status != "connected" or not access.has_access(s, cfg, st.user_id):
                        continue  # sin acceso (prueba vencida o suscripción suspendida) no se mandan resúmenes
                    token_ml = valid_access_token(s, cfg, st.user_id)
                    if not acc.email:
                        acc.email = _read_email(token_ml)
                        s.commit()
                    if not acc.email:
                        continue
                    advs = ml.advertisers(cfg, token_ml)
                    if not advs:
                        continue
                    snap = s.get(Snapshot, st.user_id)
                    adv = next((a for a in advs if snap and a["advertiser_id"] == snap.advertiser_id), advs[0])
                    get = lambda path, params=None, version="2": ml.api_get(cfg, token_ml, path, params, version)
                    data = ads.build_dataset(get, adv)
                    sent = notify.run_for(s, cfg, st.user_id, acc.email, prefs, data, _app_link())
                    result["enviados"] += len(sent)
            except Exception as exc:  # una cuenta con problemas no frena a las demás
                result["errores"] += 1
                log.warning("avisos de %s fallaron: %s", st.user_id, type(exc).__name__, exc_info=True)
        with Session(engine) as s:
            purged = privacy.purge(s)  # plazos de conservación: se aplican una vez por día
            audit.record(s, "cron_run", detail="cuentas=%(cuentas)s enviados=%(enviados)s errores=%(errores)s" % result)
            s.commit()
        return _json(dict(result, ok=True, purga=purged, cobros=cobros))

    def _admin_uid():
        uid = _current_user()
        if not uid or not access.is_admin(cfg, uid):
            if uid:
                log.warning("la cuenta %s intentó entrar a la administración", uid)
            abort(404)  # a quien no administra, la página ni siquiera le aparece
        if time.time() - session.get("at", 0) > ADMIN_SESSION_HOURS * 3600:
            abort(redirect("/connect"))  # sesión de administración vencida: se vuelve a confirmar con Mercado Libre
        return uid

    def _csrf() -> str:
        if not session.get("csrf"):
            session["csrf"] = secrets.token_urlsafe(24)
        return session["csrf"]

    def _check_csrf():
        if not session.get("csrf") or not security.safe_eq(request.form.get("csrf", ""), session["csrf"]):
            abort(400)

    @app.get("/admin")
    def admin():
        _admin_uid()
        base = request.url_root.rstrip("/")
        now = utcnow()
        with Session(engine) as s:
            invites = []
            for inv in s.execute(select(Invite).order_by(Invite.created_at.desc())).scalars():
                state = "revocada" if inv.revoked else "usada" if inv.used_by else "vencida" if inv.expires_at < now else "pendiente"
                invites.append({"token": inv.token, "label": inv.label or "Sin nombre", "state": state, "url": "%s/invitacion/%s" % (base, inv.token),
                                "expires": inv.expires_at, "used_by": inv.used_by})
            members = []
            for row in s.execute(select(Access).order_by(Access.created_at.desc())).scalars():
                acc, snap = s.get(Account, row.user_id), s.get(Snapshot, row.user_id)
                name = None
                if snap:
                    try:
                        name = json.loads(snap.data).get("advertiser", {}).get("name")
                    except ValueError:
                        pass
                members.append({"user_id": row.user_id, "note": row.note, "since": row.created_at,
                                "status": acc.status if acc else "sin conectar", "advertiser": name})
            subs = []
            for sub in s.execute(select(Subscription).order_by(Subscription.created_at.desc())).scalars():
                p = access.plan(s, cfg, sub.user_id)
                subs.append({"user_id": sub.user_id, "kind": p["kind"], "days": p.get("days"), "status": sub.status, "reason": p.get("reason"),
                             "plan": billing.NAMES.get(sub.plan), "next_plan": billing.NAMES.get(sub.next_plan), "past_due": bool(p.get("past_due")),
                             "grace_ends": p.get("grace_ends"), "email": sub.payer_email, "trial_ends": sub.trial_ends_at, "paid_until": sub.paid_until})
            all_subs = s.execute(select(Subscription)).scalars().all()
            stats = {"paying": sum(1 for x in subs if x["kind"] == "paid" and x["status"] == "authorized" and not x["past_due"]),
                     "trial": sum(1 for x in subs if x["kind"] == "trial"), "past_due": sum(1 for x in subs if x["past_due"]),
                     "mrr": billing.usd_label(billing.monthly_revenue_usd(cfg, all_subs))}
            events = s.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(40)).scalars().all()
            events = [{"at": e.at, "event": e.event, "actor": e.actor, "target": e.target, "detail": e.detail} for e in events]
        return render_template("admin.html", csrf=_csrf(), invites=invites, members=members, subs=subs, admins=sorted(access.admin_ids(cfg)),
                               billing_on=billing.enabled(cfg), stats=stats, events=events)

    @app.post("/admin/invitar")
    def admin_invitar():
        admin_uid = _admin_uid(); _check_csrf()
        with Session(engine) as s:
            access.create_invite(s, request.form.get("label", ""))
            audit.record(s, "invite_create", actor=admin_uid)
            s.commit()
        return redirect("/admin#invitaciones")

    @app.post("/admin/invitacion/revocar")
    def admin_revocar():
        admin_uid = _admin_uid(); _check_csrf()
        with Session(engine) as s:
            inv = s.get(Invite, request.form.get("token", ""))
            if inv and inv.used_by is None:
                inv.revoked = True
                audit.record(s, "invite_revoke", actor=admin_uid, target=inv.token[:6])
                s.commit()
        return redirect("/admin#invitaciones")

    @app.post("/admin/acceso/agregar")
    def admin_agregar():
        admin_uid = _admin_uid(); _check_csrf()
        raw = request.form.get("user_id", "").strip()
        if raw.isdigit() and 0 < int(raw) < 2**63:
            with Session(engine) as s:
                access.grant(s, int(raw), request.form.get("note", ""))
                audit.record(s, "access_grant", actor=admin_uid, target=int(raw))
                s.commit()
        return redirect("/admin#accesos")

    @app.post("/admin/acceso/quitar")
    def admin_quitar():
        admin_uid = _admin_uid(); _check_csrf()
        raw = request.form.get("user_id", "").strip()
        if raw.isdigit() and 0 < int(raw) < 2**63:
            uid = int(raw)
            with Session(engine) as s:
                privacy.erase_user(s, uid)
                _end_subscription(s, uid)  # sin una nueva prueba gratis: para volver tiene que suscribirse
                audit.record(s, "access_remove", actor=admin_uid, target=uid)
                s.commit()
        return redirect("/admin#accesos")

    # ---------- Privacidad: transparencia, descarga y borrado de los propios datos ----------
    @app.get("/privacidad")
    def privacidad():
        uid = _current_user()
        return render_template("privacidad.html", contact=_contact(), home=_home(), logged=bool(uid), csrf=_csrf() if uid else "",
                               audit_days=privacy.AUDIT_DAYS, history_days=privacy.HISTORY_DAYS)

    @app.get("/terminos")
    def terminos():
        return render_template("terminos.html", home=_home(), updated=TERMS_UPDATED, **_offer())

    @app.get("/arrepentimiento")
    def arrepentimiento():
        """Botón de arrepentimiento: revocar la contratación dentro de los 10 días (Ley 24.240, art. 34; Res. 424/2020)."""
        uid = _session_uid()
        return render_template("arrepentimiento.html", home=_home(), contact=_contact(), logged=bool(uid), csrf=_csrf() if uid else "", code=None)

    @app.post("/arrepentimiento")
    def arrepentimiento_revocar():
        uid = _session_uid()
        if not uid:
            return redirect("/arrepentimiento")
        _check_csrf()
        code = "ARR-%d-%s" % (uid, secrets.token_hex(3).upper())
        with Session(engine) as s:
            sub, acc = s.get(Subscription, uid), s.get(Account, uid)
            had = bool(sub and sub.status in billing.LIVE and sub.mp_preapproval_id)
            to = (acc.email if acc else None) or (sub.payer_email if sub else None)
            if sub and sub.status != "new":
                billing.end(cfg, sub, keep_email=True)  # corta el cobro y el acceso; el email queda para poder devolver el dinero
            audit.record(s, "arrepentimiento", actor=uid, detail=code)
            s.commit()
        if notify.enabled(cfg):
            # A quien administra Lumo, para que revise si hay un cobro que devolver; a la persona, como constancia.
            aviso = ("Arrepentimiento %s" % code, "La cuenta %d revocó su contratación (código %s).%s\n\nRevisá en Mercado Pago si tuvo un cobro "
                     "en los últimos 10 días y devolvelo.\n" % (uid, code, " Email: %s." % to if to else ""))
            copia = ("Tu pedido de arrepentimiento en Lumo: %s" % code, "Recibimos tu pedido de arrepentimiento. Tu código de identificación es %s.\n\n"
                     "Tu suscripción quedó cancelada y no se te va a volver a cobrar. Si se te cobró en los últimos 10 días, te devolvemos el importe.\n" % code)
            for dest, (subject, text) in ((cfg.get("CONTACT_EMAIL"), aviso), (to, copia)):
                if dest:
                    try:
                        notify.send_mail(cfg, dest, subject, text, "<pre style='font-family:Arial,sans-serif;white-space:pre-wrap'>%s</pre>" % _esc(text))
                    except Exception as exc:  # la constancia ya quedó en pantalla y en el registro de actividad
                        log.warning("aviso de arrepentimiento falló: %s", type(exc).__name__)
        resp = Response(render_template("arrepentimiento.html", home=_home(), contact=_contact(), logged=True, csrf="", code=code, had_subscription=had), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/api/cuenta/exportar")
    def cuenta_exportar():
        uid = _current_user()
        if not uid:
            return _json({"error": "login"}, 401)
        with Session(engine) as s:
            data = privacy.export_user(s, uid)
            audit.record(s, "data_export", actor=uid)
            s.commit()
        resp = _json(data)
        resp.headers["Content-Disposition"] = 'attachment; filename="mis-datos-lumo.json"'
        return resp

    @app.post("/cuenta/eliminar")
    def cuenta_eliminar():
        uid = _current_user()
        if not uid:
            return redirect("/")
        _check_csrf()
        with Session(engine) as s:
            privacy.erase_user(s, uid)
            _end_subscription(s, uid)  # deja de cobrarse; no vuelve a tener prueba gratis
            audit.record(s, "account_erase", actor=uid)
            s.commit()
        session.clear()
        return page("<h1>Listo, borramos tus datos</h1><p>Eliminamos tu cuenta de Lumo y todo lo que guardábamos de ella.</p>"
                    "<p>Para que Lumo deje de tener permiso sobre tu cuenta de Mercado Libre, también podés quitarlo desde <b>Mi perfil → Seguridad → Aplicaciones conectadas</b>.</p>"
                    "<a class='btn' href='%s'>Volver al inicio</a>" % _esc(_home()))

    def _end_subscription(s, uid):
        """Corta el cobro en Mercado Pago y deja solo la marca de que la prueba gratis ya se usó (sin email ni datos de pago)."""
        sub = s.get(Subscription, uid)
        if sub is not None:  # quien nunca se suscribió no tiene nada que cortar
            billing.end(cfg, sub)

    # ---------- Suscripción con Mercado Pago ----------
    def _base_url():
        uri = cfg["REDIRECT_URI"]
        return uri[: -len("/callback")] if uri.endswith("/callback") else request.url_root.rstrip("/")

    def _suscripcion_page(uid, error=None, status=200, detail=None):
        with Session(engine) as s:
            p = access.plan(s, cfg, uid)
            sub = s.get(Subscription, uid)
            acc = s.get(Account, uid)
            email = (sub.payer_email if sub else None) or (acc.email if acc else None) or ""
            can_cancel = bool(sub and sub.mp_preapproval_id and sub.status in billing.LIVE)
            trial_offer = billing.trial_available(sub)
        pesos = {}
        if billing.enabled(cfg):
            try:
                pesos = {k: notify.money(billing.ars_amount(cfg, k)) for k in billing.available_plans(cfg)}
            except billing.RateError:
                log.warning("no se pudo obtener la cotización del dólar")
        html = render_template("suscripcion.html", plan=p, email=email, csrf=_csrf(), error=error, detail=detail, can_cancel=can_cancel, pesos=pesos, home=_home(), trial_offer=trial_offer,
                               chosen=request.form.get("plan") or session.get("plan"),
                               names=billing.NAMES, estado=request.args.get("estado"), billing_on=billing.enabled(cfg), **_offer())
        resp = Response(html, status, mimetype="text/html")
        # El formulario de pago termina en Mercado Pago: esta página, y solo esta, puede enviar hacia sus dominios de pago.
        # Sin esto, los navegadores bloquean la redirección por la regla form-action 'self'.
        resp.headers["Content-Security-Policy"] = security.CSP.replace("form-action 'self'", "form-action 'self' " + " ".join(_checkout_origins()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _checkout_origins():
        return [o for o in cfg["MP_CHECKOUT_ORIGINS"].split() if o.startswith("https://") or not prod]

    @app.get("/suscripcion")
    def suscripcion():
        uid = _session_uid()
        if not uid:
            return redirect("/")
        return _suscripcion_page(uid)

    @app.post("/suscripcion")
    def suscripcion_pagar():
        uid = _session_uid()
        if not uid:
            return redirect("/")
        _check_csrf()
        if not billing.enabled(cfg):
            return _suscripcion_page(uid, "El pago todavía no está disponible.", 503)
        plan = request.form.get("plan", "monthly")
        if plan not in billing.available_plans(cfg):
            return _suscripcion_page(uid, "Elegí un plan para continuar.", 400)
        email = request.form.get("email", "").strip()
        if not billing.EMAIL_RE.match(email) or len(email) > 254:
            return _suscripcion_page(uid, "Revisá el email: tiene que ser el de tu cuenta de Mercado Pago.", 400)
        with Session(engine) as s:
            if access.plan(s, cfg, uid)["kind"] in ("admin", "free"):
                return redirect("/panel")
            sub = s.get(Subscription, uid)
            if sub is None:
                sub = Subscription(user_id=uid)
                s.add(sub)
            if sub.status == "authorized" and sub.plan == plan and not sub.past_due_since:
                return redirect("/suscripcion")  # ya tiene ese plan al día
            try:
                url = billing.create_checkout(cfg, sub, plan, email, _base_url() + "/suscripcion/listo")
            except billing.RateError:
                log.warning("no se pudo obtener la cotización del dólar")
                return _suscripcion_page(uid, "No pudimos calcular el precio en pesos en este momento. Probá de nuevo en unos minutos.", 503)
            except billing.MPError as exc:
                log.warning("crear suscripción falló para %s: %s %s", uid, exc.status, exc.message)
                detail = "Mercado Pago respondió %s: %s" % (exc.status, exc.message or "sin detalle")
                if "test" in (exc.message or "").lower():
                    # Con credenciales de prueba, Mercado Pago solo acepta usuarios de prueba (y al revés).
                    return _suscripcion_page(uid, "Lumo está en modo de prueba de Mercado Pago: para pagar hay que usar el email de un usuario de prueba "
                                                  "de Mercado Pago, no una cuenta real.", 502, detail)
                return _suscripcion_page(uid, "Mercado Pago no pudo iniciar el pago. Revisá el email y probá de nuevo en unos minutos.", 502, detail)
            if not any(url == o or url.startswith(o + "/") for o in _checkout_origins()):
                host = url.split("/")[2] if url.count("/") >= 2 else url
                log.warning("Mercado Pago devolvió un enlace de pago fuera de los dominios permitidos: %s", host)
                return _suscripcion_page(uid, "Mercado Pago no pudo iniciar el pago. Probá de nuevo en unos minutos.", 502,
                                         "El enlace de pago es de %s, que no está en MP_CHECKOUT_ORIGINS." % host)
            audit.record(s, "sub_checkout", actor=uid, detail=plan)
            s.commit()
        return redirect(url)

    @app.get("/suscripcion/listo")
    def suscripcion_listo():
        """Mercado Pago vuelve acá después del pago, con el id de la suscripción."""
        uid = _session_uid()
        if not uid:
            return redirect("/")
        pid = request.args.get("preapproval_id", "")
        change = False
        if pid and billing.enabled(cfg):
            try:
                pre = billing.fetch(cfg, pid)
            except billing.MPError as exc:
                log.warning("consultar suscripción falló: %s", exc.status)
                pre = None
            if pre and str(pre.get("external_reference")) == str(uid):
                with Session(engine) as s:
                    sub = s.get(Subscription, uid)
                    if sub and billing.owns(sub, pid):
                        change = pid == sub.next_preapproval_id
                        _apply_preapproval(s, sub, pre)
                        s.commit()
        if change:
            return redirect("/suscripcion?estado=cambio")
        if _current_user():
            with Session(engine) as s:
                sub = s.get(Subscription, uid)
                if sub and sub.status == "authorized":
                    return redirect("/panel")
        return redirect("/suscripcion?estado=pendiente")

    @app.post("/suscripcion/cancelar")
    def suscripcion_cancelar():
        uid = _session_uid()
        if not uid:
            return redirect("/")
        _check_csrf()
        with Session(engine) as s:
            sub = s.get(Subscription, uid)
            if sub and sub.mp_preapproval_id and billing.enabled(cfg):
                try:
                    for pid in (sub.next_preapproval_id, sub.mp_preapproval_id):
                        if pid:
                            billing.cancel(cfg, pid)
                except billing.MPError as exc:
                    log.warning("cancelar suscripción falló para %s: %s", uid, exc.status)
                    return _suscripcion_page(uid, "No pudimos cancelar en Mercado Pago. Probá de nuevo o escribinos.", 502)
                sub.status = "cancelled"  # sigue entrando hasta la fecha ya paga
                sub.next_preapproval_id = sub.next_plan = sub.next_amount_ars = None
                audit.record(s, "sub_cancel", actor=uid)
                s.commit()
        return redirect("/suscripcion")

    def _apply_preapproval(s, sub, pre):
        before, had_trial = (sub.status, sub.plan), sub.trial_started_at
        billing.apply(cfg, sub, pre)
        if sub.trial_started_at and not had_trial:
            audit.record(s, "trial_start", target=sub.user_id, detail=sub.plan)
        if (sub.status, sub.plan) != before:
            audit.record(s, "sub_" + sub.status, target=sub.user_id, detail=sub.plan)

    def _billing_notices(s, sub) -> int:
        """Avisos por email de la suscripción: cobro rechazado, acceso suspendido y prueba por terminar. Cada uno se manda una vez."""
        if not notify.enabled(cfg):
            return 0
        p = access.plan(s, cfg, sub.user_id)
        if p["kind"] in ("admin", "free", "none"):
            return 0
        acc = s.get(Account, sub.user_id)
        to = (acc.email if acc else None) or sub.payer_email
        if not to:
            return 0
        now, kind, ref, args = utcnow(), None, None, {}
        if sub.past_due_since:
            ref = sub.past_due_since.strftime("%Y-%m-%d")
            if p.get("past_due"):
                kind, args = "pago", {"until": p["grace_ends"]}
            else:
                kind = "baja"
        elif p["kind"] == "trial" and p["days"] <= 3:  # se viene el primer cobro: que no sea una sorpresa
            price = billing.price_usd(cfg, sub.plan or "monthly")
            kind, ref, args = "prueba", sub.trial_ends_at.strftime("%Y-%m-%d"), {"days": p["days"], "until": sub.trial_ends_at,
                                                                               "price": billing.usd_label(price) if price else None, "plan": billing.NAMES.get(sub.plan)}
        if not kind or s.get(Notice, (sub.user_id, kind, ref)):
            return 0
        subject, text, html = notify.billing_mail(kind, _base_url() + "/suscripcion", **args)
        try:
            notify.send_mail(cfg, to, subject, text, html)
        except Exception as exc:  # el correo no puede frenar el registro del cobro
            log.warning("aviso de suscripción a %s falló: %s", sub.user_id, type(exc).__name__)
            return 0
        notify._mark(s, sub.user_id, kind, ref, now)
        return 1

    def _billing_tick() -> dict:
        """Chequeo diario: sincroniza cada suscripción con Mercado Pago, actualiza el monto en pesos y manda los avisos."""
        out = {"suscripciones": 0, "montos": 0, "avisos": 0, "errores": 0}
        with Session(engine) as s:
            ids = [u for (u,) in s.execute(select(Subscription.user_id)).all()]
        for uid in ids:
            try:
                with Session(engine) as s:
                    sub = s.get(Subscription, uid)
                    if billing.enabled(cfg) and sub.mp_preapproval_id and sub.status in billing.LIVE:
                        out["suscripciones"] += 1
                        _apply_preapproval(s, sub, billing.fetch(cfg, sub.mp_preapproval_id))
                        if sub.next_preapproval_id:
                            _apply_preapproval(s, sub, billing.fetch(cfg, sub.next_preapproval_id))
                        if billing.refresh_amount(cfg, sub):
                            out["montos"] += 1
                    out["avisos"] += _billing_notices(s, sub)
                    s.commit()
            except Exception as exc:  # una suscripción con problemas no frena a las demás
                out["errores"] += 1
                log.warning("chequeo de la suscripción de %s falló: %s", uid, type(exc).__name__, exc_info=True)
        return out

    @app.post("/webhooks/mercadopago")
    def webhook_mp():
        """Avisos de Mercado Pago. No se confía en el contenido: se vuelve a consultar a Mercado Pago con el token de Lumo."""
        body = request.get_json(silent=True) or {}
        kind = body.get("type") or request.args.get("type") or request.args.get("topic") or ""
        data_id = str((body.get("data") or {}).get("id") or request.args.get("data.id") or request.args.get("id") or "")
        if not billing.valid_signature(cfg, request.headers, data_id):
            return _json({"error": "firma"}, 401)
        if not data_id or not billing.enabled(cfg):
            return _json({"ok": True})
        try:
            if kind in ("subscription_preapproval", "preapproval"):
                pre = billing.fetch(cfg, data_id)
                ref = str(pre.get("external_reference") or "")
                if ref.isdigit():
                    with Session(engine) as s:
                        sub = s.get(Subscription, int(ref))
                        if sub and (sub.mp_preapproval_id is None or billing.owns(sub, data_id)):
                            _apply_preapproval(s, sub, pre)
                            s.commit()
            elif kind in ("subscription_authorized_payment", "authorized_payment"):
                pay = billing.fetch_payment(cfg, data_id)
                pid = str(pay.get("preapproval_id") or "")
                with Session(engine) as s:
                    sub = s.execute(select(Subscription).where(Subscription.mp_preapproval_id == pid)).scalars().first() if pid else None
                    if sub:
                        result = billing.apply_payment(sub, pay)
                        if result:
                            audit.record(s, "sub_pago_" + ("ok" if result == "ok" else "rechazado"), target=sub.user_id)
                            _apply_preapproval(s, sub, billing.fetch(cfg, pid))
                            _billing_notices(s, sub)
                        s.commit()
        except billing.MPError as exc:
            log.warning("webhook: consultar a Mercado Pago falló: %s", exc.status)
            return _json({"error": "mp"}, 502)  # Mercado Pago reintenta
        return _json({"ok": True})

    return app


PANEL_HTML = (Path(__file__).parent / "panel.html").read_text(encoding="utf-8")


def _grandfather(engine) -> None:
    """Al estrenar el control de acceso, las cuentas que ya estaban conectadas siguen entrando."""
    with Session(engine) as s:
        for (uid,) in s.execute(select(Account.user_id)).all():
            s.add(Access(user_id=uid, note="Conectada antes de las invitaciones"))
        s.commit()


def _widen_scope(engine) -> None:
    """La primera versión creó scope como varchar(255) y Mercado Libre devuelve listas más largas."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE account ALTER COLUMN scope TYPE TEXT"))


def _add_email_column(engine) -> None:
    """La tabla account ya existía sin la columna email."""
    if "email" in {c["name"] for c in inspect(engine).get_columns("account")}:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE account ADD COLUMN email TEXT"))


def _esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _result_body(cfg: dict, tok: dict, user_id: int):
    """Devuelve (html, ok). ok es True cuando se puede pasar directo al panel."""
    lines = ["<h1>¡Listo, tu cuenta está conectada!</h1><p class='ok'>Lumo ya puede mostrarte cómo van tus publicidades de Mercado Libre.</p>"]
    has_refresh = bool(tok.get("refresh_token"))
    if not has_refresh:
        lines.append("<p class='bad'>La conexión quedó a medias: Mercado Libre no nos dio permiso para mantenerla activa, así que se vencería en unas horas.</p><p>Si ves este mensaje, avisanos y lo resolvemos.</p>")
    try:
        found = ml.advertisers(cfg, tok["access_token"])
    except ml.MLError as exc:
        if exc.status == 404:
            lines.append("<p class='bad'>Todavía no tenés Publicidad activada en Mercado Libre.</p><p>Para activarla entrá a Mercado Libre, andá a <b>Mi perfil</b> y después a <b>Publicidad</b>. Cuando esté lista, volvé acá y conectá tu cuenta de nuevo.</p>")
        elif exc.status in (401, 403):
            lines.append("<p class='bad'>Mercado Libre no nos dejó ver tus publicidades con esta cuenta.</p><p>Probá conectar de nuevo con la cuenta principal de tu negocio. Si sigue igual, escribinos.</p>")
        else:
            lines.append("<p class='bad'>No pudimos traer tus publicidades en este momento.</p><p>Probá de nuevo en unos minutos. Si sigue pasando, escribinos.</p>")
        return "".join(lines), False
    if not found:
        lines.append("<p>Tu cuenta está conectada, pero todavía no encontramos publicidades en ella.</p><p>Cuando crees tu primera campaña en Mercado Libre, va a aparecer acá.</p>")
        return "".join(lines), False
    lines.append("<p>Encontramos estas cuentas de publicidad:</p><ul>")
    for a in found:
        lines.append("<li><b>%s</b></li>" % _esc(a.get("advertiser_name", "")))
    lines.append("</ul>")
    if not has_refresh:
        lines.append("<a class='btn' href='/panel'>Entrar igual al panel</a>")
    return "".join(lines), has_refresh
