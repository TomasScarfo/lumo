"""Genera la portada estática en site/ (en la raíz del repositorio), para publicarla aparte en Render.

La portada estática carga al instante aunque el servidor de Lumo esté dormido. Sus botones apuntan a la app,
cuya dirección se completa al publicar: Render reemplaza __APP_URL__ por la variable APP_URL.

Correr después de cambiar la portada, los estilos o el logo:
    cd backend && python build_site.py
"""
import shutil
from pathlib import Path

from flask import render_template

from lumo import create_app

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"
STATIC = Path(__file__).resolve().parent / "lumo" / "static"
ASSETS = ("site.css", "logo.svg", "logo.png")
APP_PLACEHOLDER = "__APP_URL__"


def render() -> str:
    # Solo hace falta lo mínimo para armar la app; el contacto sale de los valores por defecto de load_config.
    app = create_app({"DATABASE_URL": "sqlite://", "SECRET_KEY": "build", "ML_CLIENT_ID": "build"})
    with app.test_request_context("/"):
        return render_template("landing.html", contact=app.extensions["lumo_contact"](), invited=False, label=None, app=APP_PLACEHOLDER)


def build() -> None:
    (OUT / "static").mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render(), encoding="utf-8")
    for name in ASSETS:
        shutil.copyfile(STATIC / name, OUT / "static" / name)


if __name__ == "__main__":
    build()
    print("Portada generada en", OUT)
