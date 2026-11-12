"""Pone el personaje (mujer u hombre) en las escenas del video. Uso:  python3 tools/personaje.py mujer|hombre

El dibujo sale de ../personajes/personaje.py y va entre las marcas <!--personaje--> ... <!--/personaje--> de cada escena.
Las animaciones no cambian: las dos versiones tienen las mismas piezas con los mismos nombres.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "personajes"))
from personaje import personaje  # noqa: E402

SCENES = ("s1", "s3")


def apply(variant: str) -> None:
    for name in SCENES:
        path = ROOT / "compositions" / (name + ".html")
        html = path.read_text(encoding="utf-8")
        block = "<!--personaje-->%s<!--/personaje-->" % personaje(variant, name)
        html, n = re.subn(r"<!--personaje-->.*?<!--/personaje-->", lambda m: block, html, flags=re.S)
        if n != 1:
            raise SystemExit("%s: no encontré las marcas del personaje" % name)
        path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    v = sys.argv[1] if len(sys.argv) > 1 else "mujer"
    if v not in ("mujer", "hombre"):
        raise SystemExit("usar: mujer u hombre")
    apply(v)
    print("personaje:", v)
