"""Genera compositions/s1.html, s2.html y s3.html del video 2.

La vendedora sale del video 1 (v1-aviso/compositions/s3.html) para que sea la misma en todos los videos, y las tres
campañas se escriben una sola vez porque aparecen igual al final de la escena 1 y al principio de la 2 (empalme exacto).
Correr después de cambiar algo:  python3 tools/build_scenes.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT.parent / "v1-aviso" / "compositions"
sys.path.insert(0, str(ROOT.parent / "personajes"))
from personaje import personaje  # noqa: E402

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "mujer"  # mujer | hombre

FONTS = """    @font-face { font-family: "Bricolage Grotesque"; src: url("assets/fonts/BricolageGrotesque.ttf"); font-weight: 200 800; }
    @font-face { font-family: "Figtree"; src: url("assets/fonts/Figtree.ttf"); font-weight: 300 900; }"""

# --- las tres campañas (datos de ejemplo de la portada de Lumo) ---
ROWS = [
    ("r1", "Organizadores", "Superando el objetivo", "#146C43", "#D9F1E3", "$9,8", "$8,0"),
    ("r2", "Mesas y sillas", "Mejorando", "#2446D6", "#E3E9FC", "$4,3", "$5,0"),
    ("r3", "Cortinas blackout", "Con oportunidad", "#8F5200", "#FBEACB", "$3,4", "$4,0"),
]
ROW_TOP = {"r1": 330, "r2": 560, "r3": 790}
ROWS_CSS = """    .row { position: absolute; left: 70px; right: 70px; height: 200px; background: #FFFFFF; border: 4px solid #DAE2E9; border-radius: 34px;
           box-shadow: 0 18px 40px rgba(19,32,44,.10); padding: 26px 34px; }
    .row .name { font-size: 46px; font-weight: 900; }
    .row .chip { position: absolute; left: 34px; bottom: 26px; padding: 6px 16px; border-radius: 12px; font-size: 30px; font-weight: 800; }
    .row .roas { position: absolute; right: 34px; top: 26px; text-align: right; font-size: 28px; font-weight: 700; color: #5A6B7C; }
    .row .roas b { display: block; font-size: 56px; font-weight: 900; color: #13202C; line-height: 1.05; }
    .row .goal { position: absolute; right: 34px; bottom: 28px; font-size: 28px; font-weight: 600; color: #5A6B7C; }
    .row-ring { position: absolute; inset: -4px; border-radius: 34px; border: 7px solid transparent; opacity: 0; }"""


def rows_html(prefix):
    out = []
    for rid, name, state, ink, soft, roas, goal in ROWS:
        out.append(
            '      <div id="%s-%s" class="row" style="top:%dpx"><div class="name">%s</div>'
            '<div class="chip" style="color:%s;background:%s">%s</div>'
            '<div class="roas">ROAS<b>%s</b></div><div class="goal">objetivo %s</div>'
            '<div id="%s-%s-ring" class="row-ring" style="border-color:%s"></div></div>'
            % (prefix, rid, ROW_TOP[rid], name, ink, soft, state, roas, goal, prefix, rid, ink))
    return "\n".join(out)


def character(prefix):
    return personaje(VARIANT, prefix)


# --- escena 1: invierte, la tapan las siglas, Lumo las ordena ---
TILES = [  # (id, etiqueta, valor, x, y, giro, cae en)
    ("t1", "ROAS", "3,8", 40, 1010, -8, 3.30),
    ("t2", "ACOS", "26 %", 380, 1010, 6, 3.80),
    ("t3", "CTR", "1,2 %", 170, 935, 4, 4.30),
    ("t4", "CPC", "$84", 400, 905, -10, 4.80),
    ("t5", "CVR", "3 %", 20, 885, 12, 5.05),
    ("t6", "Impresiones", "48.210", 250, 1000, -4, 5.30),
    ("t7", "Clics", "2.497", 420, 700, 14, 5.55),
    ("t8", "Ventas", "−26 %", 0, 720, -12, 5.80),
]
TILE_ROW = {"t1": "r1", "t3": "r1", "t2": "r2", "t4": "r2", "t7": "r2", "t5": "r3", "t6": "r3", "t8": "r3"}


def s1():
    tiles = "\n".join(
        '      <div id="s1-%s" class="tile" data-layout-allow-overlap data-layout-allow-overflow style="left:%dpx;top:%dpx"><span>%s</span><b>%s</b></div>' % (tid, x, y, lab, val)
        for tid, lab, val, x, y, rot, t in TILES)
    js = []
    for tid, lab, val, x, y, rot, t in TILES:
        js.append('    tl.fromTo("#s1-%s", { y: -1500, rotation: %d }, { y: 0, rotation: %d, duration: 0.7, ease: "bounce.out" }, %.2f);' % (tid, rot - 20, rot, t))
    for i, (tid, lab, val, x, y, rot, t) in enumerate(TILES):
        top = ROW_TOP[TILE_ROW[tid]]
        dx, dy = 540 - (x + 120), top + 100 - (y + 55)
        js.append('    tl.to("#s1-%s", { x: %d, y: %d, rotation: 0, scale: 0.3, opacity: 0, duration: 0.45, ease: "power3.in" }, %.2f);' % (tid, dx, dy, 8.5 + i * 0.04))
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    #s1-hook { position: absolute; left: 60px; right: 60px; top: 272px; text-align: center; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 66px; line-height: 1.02; letter-spacing: -0.02em; }
    #s1-sample { display: none; position: absolute; right: 70px; top: 1296px; font-size: 28px; font-weight: 600; color: #5A6B7C; }
    #s1-char { position: absolute; left: -40px; top: 520px; width: 700px; height: 1700px; }
    #s1-chart { position: absolute; left: 610px; top: 560px; width: 400px; height: 540px; }
    #s1-chart .label { font-size: 30px; font-weight: 700; color: #5A6B7C; text-align: center; }
    #s1-chart .total { font-size: 54px; font-weight: 900; text-align: center; }
    .bar { position: absolute; bottom: 0; width: 92px; border: 5px solid #13202C; border-bottom: none; border-radius: 18px 18px 0 0; background: #CFDBFF; }
    #s1-base { position: absolute; left: -10px; right: -10px; bottom: -5px; height: 6px; border-radius: 3px; background: #13202C; }
    .tile { position: absolute; width: 240px; height: 110px; background: #FFFFFF; border: 4px solid #13202C; border-radius: 18px; padding: 10px 18px;
            box-shadow: 0 10px 0 rgba(19,32,44,.08); }
    .tile span { display: block; font-size: 28px; font-weight: 700; color: #5A6B7C; }
    .tile b { display: block; font-size: 40px; font-weight: 900; line-height: 1.05; }
    #s1-q { position: absolute; left: 330px; top: 400px; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 170px; color: #2446D6; opacity: 0; }
    #s1-badge { position: absolute; left: 0; right: 0; top: 168px; display: flex; align-items: center; justify-content: center; gap: 20px;
                font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 64px; opacity: 0; }
    #s1-badge img { width: 110px; height: 110px; border-radius: 26px; }
    #s1-badge { display: none !important; }  /* el logo fijo de arriba ya muestra la marca */
    #s1-first { position: absolute; left: 640px; top: 300px; padding: 10px 20px; border-radius: 14px; background: #2446D6; color: #FFFFFF; font-size: 30px; font-weight: 800; opacity: 0; }
%s
  </style>
  <div id="root" data-composition-id="s1" data-width="1080" data-height="1920">
    <div id="s1-hook">¿Tu publicidad te deja ganancia?</div>
    <div id="s1-chart">
      <div class="label">Inversión, últimos 7 días</div>
      <div class="total">$209.852</div>
      <div style="position:absolute;left:30px;right:30px;bottom:0;height:380px">
        <div id="s1-bar1" class="bar" style="left:0;height:200px"></div>
        <div id="s1-bar2" class="bar" style="left:124px;height:290px"></div>
        <div id="s1-bar3" class="bar" style="left:248px;height:380px;background:#2446D6"></div>
        <div id="s1-base"></div>
      </div>
    </div>
    %s
%s
    <div id="s1-q">?</div>
    <div id="s1-badge"><img src="assets/logo.svg" alt="">Lumo</div>
%s
    <div id="s1-first">1 · Hacelo primero</div>
    <div id="s1-sample">Datos de ejemplo</div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.set("#s1-head", { svgOrigin: "320 470" }, 0);
    tl.to("#s1-body", { scaleY: 1.008, svgOrigin: "320 1700", duration: 1.5, ease: "sine.inOut", yoyo: true, repeat: 1 }, 0);
    // "Invertís en publicidad": crecen las barras
    tl.fromTo("#s1-bar1, #s1-bar2, #s1-bar3", { scaleY: 0.35, transformOrigin: "50%% 100%%" }, { scaleY: 1, duration: 0.7, ease: "back.out(1.4)", stagger: 0.25 }, 0.4);
    tl.to("#s1-head", { rotation: 4, y: -4, duration: 0.4, ease: "back.out(1.6)" }, 0.5);
    // señala sus barras, orgullosa
    tl.to("#s1-arm-r", { rotation: -55, svgOrigin: "515 690", duration: 0.45, ease: "back.out(1.6)" }, 0.6);
    tl.to("#s1-fore-r", { rotation: -40, svgOrigin: "560 960", duration: 0.45, ease: "back.out(1.6)" }, 0.68);
    tl.to("#s1-look", { x: 9, y: 2, duration: 0.25, ease: "power2.out" }, 0.5);
    tl.to("#s1-eye-l, #s1-eye-r", { scaleY: 0.1, transformOrigin: "50%% 50%%", duration: 0.05, ease: "none" }, 1.9);
    tl.to("#s1-eye-l, #s1-eye-r", { scaleY: 1, duration: 0.06, ease: "none" }, 1.95);
    // "pero entre ROAS, ACOS y CTR": el gráfico se va y le llueven siglas
    tl.to("#s1-chart", { opacity: 0, y: 40, duration: 0.25, ease: "power2.in" }, 3.0);
%s
    tl.set("#s1-m-smile", { opacity: 0 }, 3.45);
    tl.set("#s1-m-o", { opacity: 1 }, 3.45);
    tl.to("#s1-look", { x: 3, y: -9, duration: 0.2, ease: "power2.out" }, 3.4);
    // se cubre de la lluvia de siglas
    tl.to("#s1-arm-r", { rotation: -150, svgOrigin: "515 690", duration: 0.35, ease: "back.out(1.8)" }, 3.2);
    tl.to("#s1-fore-r", { rotation: -50, svgOrigin: "560 960", duration: 0.35, ease: "back.out(1.8)" }, 3.25);
    tl.to("#s1-arm-l", { rotation: 150, svgOrigin: "125 690", duration: 0.35, ease: "back.out(1.8)" }, 3.3);
    tl.to("#s1-fore-l", { rotation: 50, svgOrigin: "80 960", duration: 0.35, ease: "back.out(1.8)" }, 3.35);
    tl.to("#s1-head", { rotation: -6, y: 12, duration: 0.3, ease: "back.out(2)" }, 3.45);
    tl.to("#s1-brow-l", { y: -8, rotation: 12, svgOrigin: "300 246", duration: 0.25, ease: "back.out(2)" }, 4.0);
    tl.to("#s1-brow-r", { y: -2, rotation: -6, svgOrigin: "340 246", duration: 0.25, ease: "back.out(2)" }, 4.05);
    tl.to("#s1-head", { rotation: 5, duration: 0.25, ease: "power2.inOut" }, 4.6);
    tl.to("#s1-head", { rotation: -5, duration: 0.25, ease: "power2.inOut" }, 4.85);
    tl.to("#s1-head", { rotation: 0, duration: 0.3, ease: "power2.out" }, 5.1);
    // "¿sabés si te deja ganancia?"
    tl.fromTo("#s1-q", { opacity: 0, scale: 0.4, rotation: -20 }, { opacity: 1, scale: 1, rotation: 8, duration: 0.4, ease: "back.out(2.6)" }, 6.2);
    tl.to("#s1-eye-l, #s1-eye-r", { scaleY: 0.1, duration: 0.05, ease: "none" }, 6.9);
    tl.to("#s1-eye-l, #s1-eye-r", { scaleY: 1, duration: 0.06, ease: "none" }, 6.95);
    // "Lumo lee tus campañas": se enciende Lumo, las siglas se ordenan en campañas y la vendedora sale de cuadro aliviada
    tl.to("#s1-hook", { opacity: 0, filter: "blur(8px)", duration: 0.2, ease: "power2.in" }, 7.9);
    tl.fromTo("#s1-badge", { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.45, ease: "back.out(2.2)" }, 8.1);
    tl.to("#s1-q", { opacity: 0, scale: 0.6, duration: 0.2, ease: "power2.in" }, 8.15);
    tl.set("#s1-m-o", { opacity: 0 }, 8.2);
    tl.set("#s1-m-grin", { opacity: 1 }, 8.2);
    tl.to("#s1-brow-l, #s1-brow-r", { rotation: 0, y: -10, duration: 0.25, ease: "power2.out" }, 8.2);
    tl.to("#s1-arm-l, #s1-arm-r, #s1-fore-l, #s1-fore-r", { rotation: 0, duration: 0.3, ease: "power2.out" }, 8.2);
%s
    tl.to("#s1-char", { y: 1400, duration: 0.6, ease: "power3.in" }, 8.6);
    tl.fromTo("#s1-r1, #s1-r2, #s1-r3", { clipPath: "inset(0%% 100%% 0%% 0%% round 34px)" }, { clipPath: "inset(0%% 0%% 0%% 0%% round 34px)", duration: 0.45, ease: "power3.out", stagger: 0.15 }, 8.9);
    tl.fromTo("#s1-r1 .chip, #s1-r2 .chip, #s1-r3 .chip", { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2.4)", stagger: 0.15 }, 9.2);
    // "qué funciona", "qué no", "qué hacer primero"
    tl.to("#s1-r1-ring", { opacity: 1, duration: 0.2, ease: "power2.out" }, 10.9);
    tl.fromTo("#s1-r1", { scale: 1 }, { scale: 1.035, duration: 0.18, ease: "power2.out", yoyo: true, repeat: 1 }, 10.9);
    tl.to("#s1-r3-ring", { opacity: 1, duration: 0.2, ease: "power2.out" }, 11.6);
    tl.fromTo("#s1-r3", { scale: 1 }, { scale: 1.035, duration: 0.18, ease: "power2.out", yoyo: true, repeat: 1 }, 11.6);
    tl.fromTo("#s1-first", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 12.8);
    window.__timelines["s1"] = tl;
  </script>
</template>
""" % (FONTS, ROWS_CSS, character("s1"), tiles, rows_html("s1"), "\n".join(js[:len(TILES)]), "\n".join(js[len(TILES):]))


# --- escena 2: la campaña se abre en la recomendación ---
def s2():
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    #s2-badge { position: absolute; left: 0; right: 0; top: 168px; display: flex; align-items: center; justify-content: center; gap: 20px;
                font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 64px; }
    #s2-badge img { width: 110px; height: 110px; border-radius: 26px; }
    #s2-badge { display: none !important; }  /* el logo fijo de arriba ya muestra la marca */
    #s2-first { position: absolute; left: 640px; top: 300px; padding: 10px 20px; border-radius: 14px; background: #2446D6; color: #FFFFFF; font-size: 30px; font-weight: 800; }
    #s2-rec { position: absolute; left: 70px; right: 70px; top: 560px; height: 560px; background: #E3E9FC; border: 4px solid #2446D6; border-radius: 34px; padding: 30px 36px; }
    #s2-rec .label { font-size: 30px; font-weight: 800; color: #2446D6; }
    #s2-rec .title { margin-top: 10px; font-size: 46px; line-height: 1.12; font-weight: 900; }
    #s2-rec .body { margin-top: 14px; font-size: 34px; line-height: 1.25; font-weight: 500; color: #44566A; }
    .cmp { position: absolute; left: 36px; right: 36px; height: 54px; }
    .cmp .fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 14px; }
    .cmp span { position: absolute; left: 18px; top: 0; line-height: 54px; font-size: 30px; font-weight: 800; color: #FFFFFF; }
    #s2-plus { position: absolute; right: 36px; top: 360px; padding: 8px 18px; border-radius: 14px; background: #146C43; color: #FFFFFF; font-size: 34px; font-weight: 900; }
    #s2-sample { display: none; position: absolute; right: 70px; top: 1296px; font-size: 28px; font-weight: 600; color: #5A6B7C; }
%s
  </style>
  <div id="root" data-composition-id="s2" data-width="1080" data-height="1920">
    <div id="s2-badge"><img src="assets/logo.svg" alt="">Lumo</div>
%s
    <div id="s2-first">1 · Hacelo primero</div>
    <div id="s2-rec">
      <div class="label">Recomendación de Lumo</div>
      <div class="title">Organizadores tiene margen para ganar visibilidad</div>
      <div class="body">Su ROAS está 22 %% por encima del objetivo. Podés bajarlo para mostrarte más y ganar clics y ventas.</div>
      <div class="cmp" style="top:410px"><div id="s2-bar-roas" class="fill" style="width:100%%;background:#146C43"></div><span>ROAS $9,8</span></div>
      <div class="cmp" style="top:476px"><div id="s2-bar-goal" class="fill" style="width:82%%;background:#5A6B7C"></div><span>Objetivo $8,0</span></div>
      <div id="s2-plus">+22 %%</div>
    </div>
    <div id="s2-sample">Datos de ejemplo</div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    // empieza igual que terminó la escena 1; las otras dos campañas se van y Organizadores se abre en su recomendación
    tl.set("#s2-r1-ring", { opacity: 1 }, 0);
    tl.set("#s2-r3-ring", { opacity: 1 }, 0);
    tl.to("#s2-r2, #s2-r3", { y: 260, opacity: 0, duration: 0.3, ease: "power3.in", stagger: 0.05 }, 0.15);
    tl.fromTo("#s2-rec", { clipPath: "inset(0%% 0%% 100%% 0%% round 34px)" }, { clipPath: "inset(0%% 0%% 0%% 0%% round 34px)", duration: 0.55, ease: "power3.out" }, 0.4);
    tl.fromTo("#s2-rec .title", { opacity: 0, filter: "blur(8px)" }, { opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power4.out" }, 0.6);
    tl.fromTo("#s2-rec .body", { opacity: 0 }, { opacity: 1, duration: 0.3, ease: "power2.out" }, 0.85);
    // "con tus números": las barras comparan el ROAS con el objetivo
    tl.fromTo("#s2-bar-roas, #s2-bar-goal", { scaleX: 0, transformOrigin: "0%% 50%%" }, { scaleX: 1, duration: 0.6, ease: "expo.out", stagger: 0.15 }, 1.2);
    tl.fromTo("#s2-plus", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 2.0);
    // salida: la tarjeta se queda y el azul del cierre se abre desde ella
    window.__timelines["s2"] = tl;
  </script>
</template>
""" % (FONTS, ROWS_CSS, rows_html("s2"))


def s3():
    src = (ROOT.parent / "v1-aviso" / "tools" / "base" / "s4.html").read_text(encoding="utf-8")
    return src.replace("s4", "s3").replace("at 922px 1122px", "at 540px 840px")


if __name__ == "__main__":
    for name, fn in (("s1", s1), ("s2", s2), ("s3", s3)):
        (ROOT / "compositions" / (name + ".html")).write_text(fn(), encoding="utf-8")
    print("escenas generadas")
