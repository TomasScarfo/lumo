import json
import logging
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, abort, jsonify, redirect, render_template, render_template_string, request, session
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from . import access, ads, billing, cuenta, ml
from .models import Access, Account, Base, Invite, PanelState, Snapshot, Subscription, utcnow
from .tokens import NeedsReconnect, save_tokens, valid_access_token

log = logging.getLogger("lumo")

SNAPSHOT_TTL = timedelta(hours=3)  # Mercado Libre actualiza los datos una vez al día
MIN_REFRESH = timedelta(minutes=10)  # tope para el botón "Actualizar"
MAX_STATE_BYTES = 200_000
SESSION_DAYS = 90

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
        "SECRET_KEY": os.environ.get("SECRET_KEY", ""),
        "DATABASE_URL": os.environ.get("DATABASE_URL", "sqlite:///lumo.db"),
        "ML_AUTH_BASE": os.environ.get("ML_AUTH_BASE", "https://auth.mercadolibre.com.ar"),
        "ML_API_BASE": os.environ.get("ML_API_BASE", "https://api.mercadolibre.com"),
        "ADMIN_USER_IDS": os.environ.get("ADMIN_USER_IDS", ""),
        "CONTACT_EMAIL": os.environ.get("CONTACT_EMAIL", "lumoads.ml@gmail.com"),
        "CONTACT_WHATSAPP": os.environ.get("CONTACT_WHATSAPP", "5491145597516"),
        # Cobro con Mercado Pago. Sin MP_ACCESS_TOKEN o sin PLAN_PRICE, la prueba gratis funciona igual pero no se puede pagar.
        "MP_ACCESS_TOKEN": os.environ.get("MP_ACCESS_TOKEN", ""),
        "MP_WEBHOOK_SECRET": os.environ.get("MP_WEBHOOK_SECRET", ""),
        "MP_API_BASE": os.environ.get("MP_API_BASE", "https://api.mercadopago.com"),
        "PLAN_PRICE": os.environ.get("PLAN_PRICE", ""),
        "PLAN_CURRENCY": os.environ.get("PLAN_CURRENCY", "ARS"),
        "TRIAL_DAYS": os.environ.get("TRIAL_DAYS", "14"),
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
    return create_engine(url, pool_pre_ping=True)


def create_app(overrides=None) -> Flask:
    cfg = load_config(overrides)
    app = Flask(__name__)
    app.config["SECRET_KEY"] = cfg["SECRET_KEY"] or secrets.token_hex(32)
    app.config["SESSION_COOKIE_SECURE"] = cfg["REDIRECT_URI"].startswith("https://")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.permanent_session_lifetime = timedelta(days=SESSION_DAYS)
    engine = make_engine(cfg["DATABASE_URL"])
    had_access_table = inspect(engine).has_table("access")
    Base.metadata.create_all(engine)
    _widen_scope(engine)
    if not had_access_table:
        _grandfather(engine)
    app.extensions["lumo_cfg"] = cfg
    app.extensions["lumo_engine"] = engine

    def missing_config():
        return [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "REDIRECT_URI", "ENCRYPTION_KEY") if not cfg[k]]

    @app.get("/healthz")
    def healthz():
        resp = jsonify({"ok": True})
        resp.headers["Access-Control-Allow-Origin"] = "*"  # la portada publicada aparte lo consulta para despertar al servidor
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/favicon.ico")
    def favicon():
        return redirect("/static/logo.png")

    def _contact():
        """Datos de contacto para la portada. Si no hay ninguno configurado, no se muestra la sección."""
        out = {}
        email, wa = cfg.get("CONTACT_EMAIL"), cfg.get("CONTACT_WHATSAPP")
        if email:
            out["email"] = email
            out["mailto"] = "mailto:%s?subject=%s" % (email, quote("Acceso a Lumo"))
        digits = re.sub(r"\D", "", wa or "")
        if digits:
            out["whatsapp"] = "https://wa.me/%s?text=%s" % (digits, quote("Hola, quiero probar Lumo"))
            out["phone"] = "+%s %s %s %s %s" % (digits[:2], digits[2], digits[3:5], digits[5:9], digits[9:]) if len(digits) == 13 and digits.startswith("549") else "+" + digits
        return out or None

    def _offer():
        return {"contact": _contact(), "trial_days": billing.trial_days(cfg), "price": billing.price_label(cfg)}
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

    @app.get("/connect")
    def connect():
        if missing_config():
            return redirect("/")
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
        if not expected or not state or not secrets.compare_digest(expected, state) or not code or not verifier:
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
            if not allowed and s.get(Subscription, user_id) is None:
                billing.start_trial(s, cfg, user_id)  # primer ingreso: empieza la prueba gratis, una sola por cuenta
                allowed = True
            save_tokens(s, cfg, user_id, tok)
            s.commit()
        session.clear()
        session["uid"] = user_id  # Lumo recuerda a la persona en este navegador
        session.permanent = True
        if not allowed:
            log.info("la cuenta %s no tiene la suscripción al día", user_id)
            return redirect("/suscripcion")
        body, ok = _result_body(cfg, tok, user_id)
        if ok:
            return redirect("/panel")
        if access.is_admin(cfg, user_id):
            return redirect("/admin")
        return page(body)

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
        return redirect("/")

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
            st = s.get(PanelState, uid)
            data["estado"] = json.loads(st.data) if st else {}
            data["admin"] = access.is_admin(cfg, uid)
            data["uid"] = uid
            p = access.plan(s, cfg, uid)
            data["plan"] = {"kind": p["kind"], "days": p.get("days")}
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
    def _admin_uid():
        uid = _current_user()
        if not uid or not access.is_admin(cfg, uid):
            abort(404)  # a quien no administra, la página ni siquiera le aparece
        return uid

    def _csrf() -> str:
        if not session.get("csrf"):
            session["csrf"] = secrets.token_urlsafe(24)
        return session["csrf"]

    def _check_csrf():
        if not secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "-")):
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
                subs.append({"user_id": sub.user_id, "kind": p["kind"], "days": p.get("days"), "status": sub.status,
                             "email": sub.payer_email, "trial_ends": sub.trial_ends_at, "paid_until": sub.paid_until})
        return render_template("admin.html", csrf=_csrf(), invites=invites, members=members, subs=subs, admins=sorted(access.admin_ids(cfg)),
                               billing_on=billing.enabled(cfg))

    @app.post("/admin/invitar")
    def admin_invitar():
        _admin_uid(); _check_csrf()
        with Session(engine) as s:
            access.create_invite(s, request.form.get("label", ""))
            s.commit()
        return redirect("/admin#invitaciones")

    @app.post("/admin/invitacion/revocar")
    def admin_revocar():
        _admin_uid(); _check_csrf()
        with Session(engine) as s:
            inv = s.get(Invite, request.form.get("token", ""))
            if inv and inv.used_by is None:
                inv.revoked = True
                s.commit()
        return redirect("/admin#invitaciones")

    @app.post("/admin/acceso/agregar")
    def admin_agregar():
        _admin_uid(); _check_csrf()
        raw = request.form.get("user_id", "").strip()
        if raw.isdigit():
            with Session(engine) as s:
                access.grant(s, int(raw), request.form.get("note", ""))
                s.commit()
        return redirect("/admin#accesos")

    @app.post("/admin/acceso/quitar")
    def admin_quitar():
        _admin_uid(); _check_csrf()
        raw = request.form.get("user_id", "").strip()
        if raw.isdigit():
            uid = int(raw)
            with Session(engine) as s:
                for model in (Access, Account, Snapshot, PanelState):
                    s.execute(delete(model).where(model.user_id == uid))
                _end_subscription(s, uid)  # sin una nueva prueba gratis: para volver tiene que suscribirse
                s.commit()
        return redirect("/admin#accesos")

    def _end_subscription(s, uid):
        sub = s.get(Subscription, uid)
        if sub is None:
            sub = Subscription(user_id=uid, trial_ends_at=utcnow())
            s.add(sub)
        if sub.mp_preapproval_id and sub.status in ("pending", "authorized", "paused") and billing.enabled(cfg):
            try:
                billing.cancel(cfg, sub.mp_preapproval_id)
            except billing.MPError as exc:
                log.warning("no se pudo cancelar la suscripción de %s en Mercado Pago: %s", uid, exc.status)
        sub.status, sub.paid_until = "cancelled", None
        sub.trial_ends_at = min(sub.trial_ends_at, utcnow())

    # ---------- Suscripción con Mercado Pago ----------
    def _base_url():
        uri = cfg["REDIRECT_URI"]
        return uri[: -len("/callback")] if uri.endswith("/callback") else request.url_root.rstrip("/")

    def _suscripcion_page(uid, error=None, status=200):
        with Session(engine) as s:
            p = access.plan(s, cfg, uid)
            sub = s.get(Subscription, uid)
            email = sub.payer_email if sub else ""
            can_cancel = bool(sub and sub.mp_preapproval_id and sub.status in ("pending", "authorized", "paused"))
        return render_template("suscripcion.html", plan=p, email=email or "", csrf=_csrf(), error=error, can_cancel=can_cancel,
                               pending=request.args.get("estado") == "pendiente", billing_on=billing.enabled(cfg), **_offer()), status

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
        email = request.form.get("email", "").strip()
        if not billing.EMAIL_RE.match(email) or len(email) > 254:
            return _suscripcion_page(uid, "Revisá el email: tiene que ser el de tu cuenta de Mercado Pago.", 400)
        with Session(engine) as s:
            if access.plan(s, cfg, uid)["kind"] in ("admin", "free"):
                return redirect("/panel")
            sub = s.get(Subscription, uid)
            if sub is None:
                sub = Subscription(user_id=uid, trial_ends_at=utcnow())
                s.add(sub)
            if sub.status == "authorized":
                return redirect("/suscripcion")
            try:
                url = billing.create_checkout(cfg, sub, email, _base_url() + "/suscripcion/listo")
            except billing.MPError as exc:
                log.warning("crear suscripción falló para %s: %s %s", uid, exc.status, exc.message)
                return _suscripcion_page(uid, "Mercado Pago no pudo iniciar el pago. Probá de nuevo en unos minutos.", 502)
            sub.status = "pending"
            s.commit()
        return redirect(url)

    @app.get("/suscripcion/listo")
    def suscripcion_listo():
        """Mercado Pago vuelve acá después del pago, con el id de la suscripción."""
        uid = _session_uid()
        if not uid:
            return redirect("/")
        pid = request.args.get("preapproval_id", "")
        if pid and billing.enabled(cfg):
            try:
                pre = billing.fetch(cfg, pid)
            except billing.MPError as exc:
                log.warning("consultar suscripción falló: %s", exc.status)
                pre = None
            if pre and str(pre.get("external_reference")) == str(uid):
                with Session(engine) as s:
                    sub = s.get(Subscription, uid)
                    if sub:
                        billing.apply(sub, pre)
                        s.commit()
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
                    billing.apply(sub, billing.cancel(cfg, sub.mp_preapproval_id))
                except billing.MPError as exc:
                    log.warning("cancelar suscripción falló para %s: %s", uid, exc.status)
                    return _suscripcion_page(uid, "No pudimos cancelar en Mercado Pago. Probá de nuevo o escribinos.", 502)
                sub.status = "cancelled"  # sigue entrando hasta la fecha ya paga
                s.commit()
        return redirect("/suscripcion")

    @app.post("/webhooks/mercadopago")
    def webhook_mp():
        """Avisos de Mercado Pago. No se confía en el contenido: se vuelve a consultar la suscripción con el token de Lumo."""
        body = request.get_json(silent=True) or {}
        kind = body.get("type") or request.args.get("type") or request.args.get("topic") or ""
        data_id = str((body.get("data") or {}).get("id") or request.args.get("data.id") or request.args.get("id") or "")
        if not billing.valid_signature(cfg, request.headers, data_id):
            return _json({"error": "firma"}, 401)
        if kind in ("subscription_preapproval", "preapproval") and data_id and billing.enabled(cfg):
            try:
                pre = billing.fetch(cfg, data_id)
            except billing.MPError as exc:
                log.warning("webhook: consultar suscripción falló: %s", exc.status)
                return _json({"error": "mp"}, 502)  # Mercado Pago reintenta
            ref = str(pre.get("external_reference") or "")
            if ref.isdigit():
                with Session(engine) as s:
                    sub = s.get(Subscription, int(ref))
                    if sub and (sub.mp_preapproval_id in (None, data_id)):
                        billing.apply(sub, pre)
                        s.commit()
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
