"""Hoja de prueba de los dos personajes: los muestra lado a lado actuando (mirar, sorpresa, preocupación, alegría, saludo).
Correr:  python3 build_preview.py   y abrir la vista previa del proyecto personajes/.
"""
from pathlib import Path

from personaje import ARM_PIVOT, BROW_PIVOT, ELBOW_PIVOT, HEAD_PIVOT, idle_js, mouth_js, personaje

ROOT = Path(__file__).resolve().parent


def acting(p, d):
    """El mismo guion para los dos, desfasado `d` segundos para que no se muevan en espejo."""
    t = lambda x: x + d
    js = [idle_js(p, 8, blinks=(t(1.2), t(4.6), t(7.1)))]
    js.append('    tl.to("#%s-look", { x: 9, y: 3, duration: 0.2, ease: "power2.out" }, %.2f);' % (p, t(0.6)))
    # sorpresa: anticipación, cabeza atrás, cejas arriba, boca en "o"
    js.append('    tl.to("#%s-head", { rotation: -3, y: 6, duration: 0.12, ease: "power2.in", svgOrigin: "%s" }, %.2f);' % (p, HEAD_PIVOT, t(1.6)))
    js.append('    tl.to("#%s-head", { rotation: 6, y: -10, duration: 0.45, ease: "back.out(1.8)" }, %.2f);' % (p, t(1.72)))
    js.append('    tl.to("#%s-brow-l, #%s-brow-r", { y: -16, duration: 0.25, ease: "back.out(2)", stagger: 0.04 }, %.2f);' % (p, p, t(1.72)))
    js.append(mouth_js(p, "o", t(1.75)))
    # preocupación
    js.append('    tl.to("#%s-brow-l", { y: -4, rotation: 12, svgOrigin: "%s", duration: 0.3, ease: "back.out(2)" }, %.2f);' % (p, BROW_PIVOT["l"], t(3.0)))
    js.append('    tl.to("#%s-brow-r", { y: -4, rotation: -12, svgOrigin: "%s", duration: 0.3, ease: "back.out(2)" }, %.2f);' % (p, BROW_PIVOT["r"], t(3.04)))
    js.append('    tl.to("#%s-head", { rotation: -4, y: 8, duration: 0.4, ease: "power2.inOut" }, %.2f);' % (p, t(3.0)))
    js.append('    tl.to("#%s-look", { x: -6, y: 10, duration: 0.25, ease: "power2.out" }, %.2f);' % (p, t(3.0)))
    js.append(mouth_js(p, "worry", t(3.05)))
    # alegría y saludo: el brazo sube desde el hombro, el antebrazo saluda
    js.append('    tl.to("#%s-brow-l, #%s-brow-r", { y: -8, rotation: 0, duration: 0.3, ease: "power2.out" }, %.2f);' % (p, p, t(4.8)))
    js.append('    tl.to("#%s-head", { rotation: 3, y: -6, duration: 0.45, ease: "back.out(1.8)" }, %.2f);' % (p, t(4.8)))
    js.append('    tl.to("#%s-look", { x: 0, y: 0, duration: 0.25, ease: "power2.out" }, %.2f);' % (p, t(4.8)))
    js.append(mouth_js(p, "grin", t(4.85)))
    js.append('    tl.to("#%s-arm-r", { rotation: -150, svgOrigin: "%s", duration: 0.5, ease: "back.out(1.4)" }, %.2f);' % (p, ARM_PIVOT["r"], t(5.2)))
    js.append('    tl.to("#%s-fore-r", { keyframes: [{ rotation: 25, duration: 0.22 }, { rotation: -15, duration: 0.22 }, { rotation: 25, duration: 0.22 }, { rotation: 0, duration: 0.25 }], ease: "sine.inOut", svgOrigin: "%s" }, %.2f);' % (p, ELBOW_PIVOT["r"], t(5.6)))
    js.append(mouth_js(p, "smile", t(7.0)))
    return "\n".join(js)


html = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      @font-face { font-family: "Bricolage Grotesque"; src: url("assets/fonts/BricolageGrotesque.ttf"); font-weight: 200 800; }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { width: 1080px; height: 1920px; overflow: hidden; background: #FFFFFF; }
      #root { position: relative; width: 100%%; height: 100%%; }
      .personaje { position: absolute; top: 380px; width: 560px; height: 1360px; }
      #a-char { left: -30px; }
      #b-char { left: 500px; }
      h1 { position: absolute; left: 0; right: 0; top: 190px; text-align: center; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 72px; color: #13202C; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="8.5" data-width="1080" data-height="1920">
      <h1>Personajes de Lumo</h1>
      %s
      %s
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });
%s
%s
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
""" % (personaje("mujer", "a"), personaje("hombre", "b"), acting("a", 0), acting("b", 0.15))

(ROOT / "index.html").write_text(html, encoding="utf-8")
print("vista previa generada")
