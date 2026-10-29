import json
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template_string, request, session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from . import ads, ml
from .models import Account, Base, PanelState, Snapshot, utcnow
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
    Base.metadata.create_all(engine)
    _widen_scope(engine)
    app.extensions["lumo_cfg"] = cfg
    app.extensions["lumo_engine"] = engine

    def missing_config():
        return [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "REDIRECT_URI", "ENCRYPTION_KEY") if not cfg[k]]

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def index():
        miss = missing_config()
        if miss:
            return page("<h1>Lumo</h1><p class='bad'>Falta configurar: %s</p>" % ", ".join("<code>%s</code>" % m for m in miss), 500)
        if _logged_in():
            return redirect("/panel")
        return page(
            "<h1>Lumo</h1><p>Entendé tus métricas de Product Ads y qué mejorar, con palabras simples.</p>"
            "<p>Lumo <b>solo lee</b> tus datos de publicidad. Nunca modifica tus campañas.</p>"
            "<a class='btn' href='/connect'>Conectar con Mercado Libre</a>"
        )

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
        with Session(engine) as s:
            save_tokens(s, cfg, user_id, tok)
            s.commit()
        session.clear()
        session["uid"] = user_id  # Lumo recuerda a la persona en este navegador
        session.permanent = True
        body, ok = _result_body(cfg, tok, user_id)
        if ok:
            return redirect("/panel")
        return page(body)

    def _logged_in() -> bool:
        uid = session.get("uid")
        if not uid:
            return False
        with Session(engine) as s:
            acc = s.get(Account, uid)
            return bool(acc and acc.status == "connected")

    @app.get("/panel")
    def panel():
        if not _logged_in():
            return redirect("/")
        resp = Response(PANEL_HTML, mimetype="text/html")
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

    @app.get("/api/datos")
    def api_datos():
        uid = session.get("uid")
        if not uid:
            return _json({"error": "login"}, 401)
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
                    return _api_error(exc, advertisers=True)
                if not advs:
                    return _json({"error": "no_ads"}, 404)
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
        return _json(data)

    @app.post("/api/estado")
    def api_estado():
        uid = session.get("uid")
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

    return app


PANEL_HTML = (Path(__file__).parent / "panel.html").read_text(encoding="utf-8")


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
    lines = ["<h1>Conectado</h1><p class='ok'>Lumo ya puede leer tu cuenta de Mercado Libre.</p>"]
    lines.append("<p>Cuenta: <code>%s</code></p>" % user_id)
    lines.append("<p>Permisos recibidos: <code>%s</code></p>" % _esc(tok.get("scope") or "sin dato"))
    has_refresh = bool(tok.get("refresh_token"))
    if not has_refresh:
        lines.append("<p class='bad'>Mercado Libre no entregó un refresh token. Hay que activar el acceso offline en la app para que Lumo pueda renovar el permiso sola.</p>")
    try:
        found = ml.advertisers(cfg, tok["access_token"])
    except ml.MLError as exc:
        if exc.status == 404:
            lines.append("<p class='bad'>Tu cuenta todavía no tiene Publicidad habilitada.</p><p>Entrá a Mercado Libre, Mi perfil, Publicidad, activala y volvé a conectar.</p>")
        elif exc.status in (401, 403):
            lines.append("<p class='bad'>Mercado Libre no dejó que Lumo lea Product Ads con esta cuenta (error %s).</p><p>Puede ser un permiso restringido a desarrolladores autorizados.</p>" % exc.status)
        else:
            lines.append("<p class='bad'>La consulta de anunciantes falló (error %s, <code>%s</code>).</p>" % (exc.status, _esc(exc.code)))
        return "".join(lines), False
    if not found:
        lines.append("<p>No encontramos anunciantes de Product Ads en esta cuenta.</p>")
        return "".join(lines), False
    lines.append("<p>Anunciantes de Product Ads:</p><ul>")
    for a in found:
        lines.append("<li><b>%s</b> · sitio <code>%s</code> · id <code>%s</code></li>" % (_esc(a.get("advertiser_name", "")), _esc(a.get("site_id", "")), _esc(a.get("advertiser_id", ""))))
    lines.append("</ul>")
    if not has_refresh:
        lines.append("<a class='btn' href='/panel'>Entrar igual al panel</a>")
    return "".join(lines), has_refresh
