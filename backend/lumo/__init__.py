import logging
import os
import secrets

from flask import Flask, redirect, render_template_string, request, session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from . import ml
from .models import Base
from .tokens import save_tokens

log = logging.getLogger("lumo")

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
        return page(_result_body(cfg, tok, user_id))

    return app


def _widen_scope(engine) -> None:
    """La primera versión creó scope como varchar(255) y Mercado Libre devuelve listas más largas."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE account ALTER COLUMN scope TYPE TEXT"))


def _esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _result_body(cfg: dict, tok: dict, user_id: int) -> str:
    lines = ["<h1>Conectado</h1><p class='ok'>Lumo ya puede leer tu cuenta de Mercado Libre.</p>"]
    lines.append("<p>Cuenta: <code>%s</code></p>" % user_id)
    lines.append("<p>Permisos recibidos: <code>%s</code></p>" % _esc(tok.get("scope") or "sin dato"))
    if not tok.get("refresh_token"):
        lines.append("<p class='bad'>Mercado Libre no entregó un refresh token. Hay que activar el acceso offline en la app para que Lumo pueda renovar el permiso sola.</p>")
    try:
        ads = ml.advertisers(cfg, tok["access_token"])
    except ml.MLError as exc:
        if exc.status == 404:
            lines.append("<p class='bad'>Tu cuenta todavía no tiene Publicidad habilitada.</p><p>Entrá a Mercado Libre, Mi perfil, Publicidad, activala y volvé a conectar.</p>")
        elif exc.status in (401, 403):
            lines.append("<p class='bad'>Mercado Libre no dejó que Lumo lea Product Ads con esta cuenta (error %s).</p><p>Puede ser un permiso restringido a desarrolladores autorizados.</p>" % exc.status)
        else:
            lines.append("<p class='bad'>La consulta de anunciantes falló (error %s, <code>%s</code>).</p>" % (exc.status, _esc(exc.code)))
        return "".join(lines)
    if not ads:
        lines.append("<p>No encontramos anunciantes de Product Ads en esta cuenta.</p>")
    else:
        lines.append("<p>Anunciantes de Product Ads:</p><ul>")
        for a in ads:
            lines.append("<li><b>%s</b> · sitio <code>%s</code> · id <code>%s</code></li>" % (_esc(a.get("advertiser_name", "")), _esc(a.get("site_id", "")), _esc(a.get("advertiser_id", ""))))
        lines.append("</ul>")
    return "".join(lines)
