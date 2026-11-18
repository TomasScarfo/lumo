"""Genera la portada estática en site/ (en la raíz del repositorio), para publicarla aparte en Render.

La portada estática carga al instante aunque el servidor de Lumo esté dormido. Sus botones apuntan a la app,
cuya dirección se completa al publicar: Render reemplaza __APP_URL__ por la variable APP_URL.

Correr después de cambiar la portada, los estilos o el logo:
    cd backend && python build_site.py
"""
import shutil
from pathlib import Path

from flask import render_template

from lumo import ERRORES, PUBLIC_URL, create_app, guias
from lumo.security import GTM_ID

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"
STATIC = Path(__file__).resolve().parent / "lumo" / "static"
ASSETS = ("site.css", "logo.svg", "logo.png")
APP_PLACEHOLDER = "__APP_URL__"
PIXEL_PLACEHOLDER = "__META_PIXEL_ID__"  # Render lo reemplaza por META_PIXEL_ID; vacío, el Píxel no carga


def render() -> str:
    # Solo hace falta lo mínimo para armar la app. El contacto, el precio (PLAN_PRICE) y los días de prueba (TRIAL_DAYS)
    # salen de load_config: de las variables de entorno si están, o de sus valores por defecto.
    # Sin cotización: la página queda igual en cualquier máquina y los pesos los completa el navegador al abrirla.
    app = create_app({"DATABASE_URL": "sqlite://", "SECRET_KEY": "build", "ML_CLIENT_ID": "build", "USD_ARS_RATE": "", "USD_RATE_URL": ""})
    with app.test_request_context("/"):
        return render_template("landing.html", invited=False, label=None, app=APP_PLACEHOLDER, pixel=PIXEL_PLACEHOLDER, gtm=GTM_ID, **app.extensions["lumo_offer"]())


def render_404() -> str:
    """Render sirve 404.html de la carpeta publicada cuando alguien abre una dirección que no existe."""
    app = create_app({"DATABASE_URL": "sqlite://", "SECRET_KEY": "build", "ML_CLIENT_ID": "build"})
    title, text = ERRORES[404]
    with app.test_request_context("/"):
        return render_template("error.html", code=404, title=title, text=text, ref=None, home="/", mailto=None)


def render_guia(slug=None) -> str:
    """Una guía (o el índice de guías), tal como la sirve la app en /guias/<slug>/."""
    app = create_app({"DATABASE_URL": "sqlite://", "SECRET_KEY": "build", "ML_CLIENT_ID": "build"})
    with app.test_request_context("/"):
        return app.extensions["lumo_guia"](slug)


def paginas_guias() -> dict:
    """Ruta dentro de site/ -> HTML. Render sirve cada index.html en la dirección de su carpeta, con barra final."""
    out = {"guias/index.html": render_guia()}
    for g in guias.GUIAS:
        out["guias/%s/index.html" % g["slug"]] = render_guia(g["slug"])
    return out


def robots() -> str:
    """Deja que los buscadores lean toda la portada y les dice dónde está el mapa del sitio."""
    return "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % PUBLIC_URL


def sitemap() -> str:
    """Mapa del sitio para Google y Bing: la portada, el índice de guías y cada guía."""
    urls = ['  <url><loc>%s/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>' % PUBLIC_URL,
            '  <url><loc>%s%s</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>' % (PUBLIC_URL, guias.ruta())]
    urls += ['  <url><loc>%s%s</loc><lastmod>%s</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>'
             % (PUBLIC_URL, guias.ruta(g["slug"]), g.get("actualizada", g["publicada"])) for g in guias.GUIAS]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def build() -> None:
    (OUT / "static").mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render(), encoding="utf-8")
    (OUT / "404.html").write_text(render_404(), encoding="utf-8")
    for path, html in paginas_guias().items():
        (OUT / path).parent.mkdir(parents=True, exist_ok=True)
        (OUT / path).write_text(html, encoding="utf-8")
    (OUT / "robots.txt").write_text(robots(), encoding="utf-8")
    (OUT / "sitemap.xml").write_text(sitemap(), encoding="utf-8")
    for name in ASSETS:
        shutil.copyfile(STATIC / name, OUT / "static" / name)


if __name__ == "__main__":
    build()
    print("Portada generada en", OUT)
