"""Genera las escenas del video 3 ("Por cada $1"). Uso:  python3 tools/build_scenes.py mujer|hombre

Reutiliza el personaje (../personajes), las campañas del video 2 y el cierre del video 1, para que los tres videos
se vean como una serie.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "personajes"))
sys.path.insert(0, str(ROOT.parent / "v2-ganancia" / "tools"))
from personaje import personaje  # noqa: E402
from build_scenes import FONTS, ROWS_CSS, rows_html  # noqa: E402  (video 2)

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "mujer"


def s1():
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    #s1-cam { position: absolute; inset: 0; }
    #s1-hook { position: absolute; left: 50px; right: 50px; top: 272px; text-align: center; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 64px; line-height: 1; letter-spacing: -0.02em; }
    #s1-char { position: absolute; left: -60px; top: 380px; width: 700px; height: 1700px; }
    #s1-machine { position: absolute; left: 600px; top: 330px; width: 420px; height: 560px; }
    #s1-coin { position: absolute; left: 790px; top: 760px; width: 96px; height: 96px; opacity: 0; }
    #s1-ticket { position: absolute; left: 420px; top: 700px; width: 260px; height: 150px; background: #FFFFFF; border: 4px solid #13202C; border-radius: 14px;
                 padding: 14px 18px; box-shadow: 0 10px 0 rgba(19,32,44,.08); opacity: 0; }
    #s1-ticket span { display: block; font-size: 28px; font-weight: 700; color: #5A6B7C; }
    #s1-ticket b { display: block; font-size: 52px; font-weight: 900; letter-spacing: 0.08em; }
    #s1-q { position: absolute; left: 330px; top: 360px; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 150px; color: #2446D6; opacity: 0; }
    #s1-cover { position: absolute; inset: 0; background: #FFFFFF; opacity: 0; }
  </style>
  <div id="root" data-composition-id="s1" data-width="1080" data-height="1920">
    <div id="s1-cam">
      <div id="s1-hook">¿Cuánto vuelve de cada $1?</div>
      <svg id="s1-machine" viewBox="0 0 420 560" aria-hidden="true" fill="none" stroke="#13202C" stroke-width="6" stroke-linejoin="round" stroke-linecap="round">
        <g id="s1-mach">
          <rect x="40" y="60" width="340" height="420" rx="40" fill="#E3E9FC"/>
          <rect x="150" y="40" width="120" height="26" rx="13" fill="#13202C"/>
          <rect x="80" y="120" width="260" height="150" rx="20" fill="#FFFFFF"/>
          <text x="210" y="215" text-anchor="middle" font-family="Figtree" font-weight="900" font-size="46" fill="#2446D6" stroke="none">Publicidad</text>
          <path d="M40 360 L0 360 L0 420 L40 420" fill="#FFFFFF"/>
          <circle cx="140" cy="350" r="22" fill="#FBEACB"/><circle cx="210" cy="350" r="22" fill="#D9F1E3"/><circle cx="280" cy="350" r="22" fill="#FADFDB"/>
          <rect x="90" y="480" width="40" height="40" rx="8" fill="#13202C"/><rect x="290" y="480" width="40" height="40" rx="8" fill="#13202C"/>
        </g>
      </svg>
      <!--personaje-->%s<!--/personaje-->
      <div id="s1-ticket"><span>Ventas</span><b>? ? ?</b></div>
      <svg id="s1-coin" viewBox="0 0 96 96" aria-hidden="true">
        <circle cx="48" cy="48" r="42" fill="#F2C230" stroke="#13202C" stroke-width="6"/>
        <circle cx="48" cy="48" r="30" fill="none" stroke="#D9A21E" stroke-width="5"/>
        <text x="48" y="61" text-anchor="middle" font-family="Figtree" font-weight="900" font-size="34" fill="#13202C">$1</text>
      </svg>
      <div id="s1-q">?</div>
    </div>
    <div id="s1-cover"></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.set("#s1-head", { svgOrigin: "320 470" }, 0);
    tl.to("#s1-body", { scaleY: 1.008, svgOrigin: "320 1700", duration: 1.4, ease: "sine.inOut", yoyo: true, repeat: 3 }, 0);
    // levanta la mano con la moneda
    tl.to("#s1-arm-r", { rotation: -95, svgOrigin: "515 690", duration: 0.45, ease: "back.out(1.6)" }, 0.3);
    tl.to("#s1-fore-r", { rotation: -55, svgOrigin: "560 960", duration: 0.45, ease: "back.out(1.6)" }, 0.38);
    tl.to("#s1-look", { x: 9, y: -6, duration: 0.25, ease: "power2.out" }, 0.4);
    tl.to("#s1-head", { rotation: 5, y: -4, duration: 0.4, ease: "back.out(1.6)" }, 0.4);
    tl.fromTo("#s1-coin", { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 0.2, ease: "back.out(2.4)" }, 0.85);
    // la tira: la moneda vuela en arco hasta la ranura de arriba
    tl.to("#s1-arm-r", { rotation: -120, duration: 0.18, ease: "power2.out" }, 1.6);
    tl.to("#s1-coin", { keyframes: [{ x: 40, y: -330, rotation: 200, duration: 0.45, ease: "power2.out" }, { x: -28, y: -440, rotation: 360, scale: 0.6, duration: 0.3, ease: "power2.in" }] }, 1.65);
    tl.to("#s1-coin", { opacity: 0, duration: 0.06 }, 2.38);
    tl.to("#s1-arm-r, #s1-fore-r", { rotation: 0, duration: 0.45, ease: "power2.inOut" }, 2.1);
    tl.to("#s1-eyes", { scaleY: 0.1, svgOrigin: "320 300", duration: 0.05, ease: "none" }, 2.6);
    tl.to("#s1-eyes", { scaleY: 1, duration: 0.07, ease: "none" }, 2.66);
    // la máquina traga, tiembla y larga un ticket
    tl.to("#s1-mach", { keyframes: [{ x: -6, duration: 0.05 }, { x: 6, duration: 0.05 }, { x: -5, duration: 0.05 }, { x: 5, duration: 0.05 }, { x: 0, duration: 0.06 }] }, 2.45);
    tl.fromTo("#s1-ticket", { opacity: 0, x: 180, y: -120, scale: 0.4, rotation: 0 }, { opacity: 1, x: 0, y: 0, scale: 1, rotation: -6, duration: 0.5, ease: "back.out(1.6)" }, 3.6);
    // "¿cuánto vuelve en ventas?": no entiende
    tl.to("#s1-look", { x: 9, y: 4, duration: 0.2, ease: "power2.out" }, 3.8);
    tl.to("#s1-head", { rotation: 9, y: 6, duration: 0.35, ease: "back.out(1.8)" }, 3.9);
    tl.set("#s1-m-smile", { opacity: 0 }, 3.95);
    tl.set("#s1-m-o", { opacity: 1 }, 3.95);
    tl.to("#s1-brow-l", { y: -6, rotation: 12, svgOrigin: "300 246", duration: 0.25, ease: "back.out(2)" }, 4.0);
    tl.to("#s1-brow-r", { y: -14, duration: 0.25, ease: "back.out(2)" }, 4.05);
    // se rasca la cabeza
    tl.to("#s1-arm-r", { rotation: -150, svgOrigin: "515 690", duration: 0.4, ease: "back.out(1.6)" }, 4.1);
    tl.to("#s1-fore-r", { rotation: -70, svgOrigin: "560 960", duration: 0.4, ease: "back.out(1.6)" }, 4.15);
    tl.to("#s1-fore-r", { keyframes: [{ rotation: -60, duration: 0.12 }, { rotation: -75, duration: 0.12 }, { rotation: -62, duration: 0.12 }, { rotation: -72, duration: 0.12 }], ease: "sine.inOut" }, 4.6);
    tl.fromTo("#s1-q", { opacity: 0, scale: 0.4, rotation: -20 }, { opacity: 1, scale: 1, rotation: 8, duration: 0.4, ease: "back.out(2.6)" }, 4.4);
    // la cámara entra en el ticket: se va a abrir como tarjeta de Lumo
    tl.to("#s1-q", { opacity: 0, duration: 0.15 }, 5.0);
    tl.to("#s1-cam", { scale: 3.2, transformOrigin: "550px 775px", duration: 0.7, ease: "power3.in" }, 5.0);
    tl.to("#s1-cover", { opacity: 1, duration: 0.2, ease: "power2.in" }, 5.45);
    window.__timelines["s1"] = tl;
  </script>
</template>
""" % (FONTS, personaje(VARIANT, "s1"))


def s2():
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    #s2-badge { position: absolute; left: 0; right: 0; top: 190px; display: flex; align-items: center; justify-content: center; gap: 20px;
                font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 64px; }
    #s2-badge img { width: 110px; height: 110px; border-radius: 26px; }
    #s2-badge { display: none !important; }  /* el logo fijo de arriba ya muestra la marca */
    #s2-card { position: absolute; left: 70px; right: 70px; top: 320px; height: 720px; background: #FFFFFF; border: 4px solid #DAE2E9; border-radius: 40px;
               box-shadow: 0 18px 40px rgba(19,32,44,.10); padding: 40px 44px; }
    #s2-card .lead { font-size: 40px; line-height: 1.2; font-weight: 700; color: #44566A; }
    #s2-num { margin-top: 10px; height: 230px; overflow: hidden; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 220px; line-height: 230px; letter-spacing: -0.04em; color: #2446D6; }
    #s2-num-in div { height: 230px; }
    #s2-card .tail { font-size: 40px; font-weight: 700; color: #44566A; }
    #s2-kpis { position: absolute; left: 44px; right: 44px; bottom: 40px; display: flex; gap: 24px; }
    #s2-kpis div { flex: 1; background: #F2F5F8; border-radius: 24px; padding: 20px 24px; font-size: 28px; font-weight: 700; color: #5A6B7C; }
    #s2-kpis b { display: block; font-size: 44px; font-weight: 900; color: #13202C; }
    #s2-sample { display: none; position: absolute; right: 70px; top: 1296px; font-size: 28px; font-weight: 600; color: #5A6B7C; }
  </style>
  <div id="root" data-composition-id="s2" data-width="1080" data-height="1920">
    <div id="s2-badge"><img src="assets/logo.svg" alt="">Lumo</div>
    <div id="s2-card">
      <div class="lead">Por cada $1 invertido en los últimos 7 días, vendiste</div>
      <div id="s2-num"><div id="s2-num-in"><div>$0</div><div>$1,2</div><div>$2,5</div><div>$3,8</div></div></div>
      <div class="tail">en ventas por publicidad.</div>
      <div id="s2-kpis"><div>Inversión<b>$209.852</b></div><div>Ventas<b>$798.000</b></div></div>
    </div>
    <div id="s2-sample">Datos de ejemplo</div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#s2-badge", { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.4, ease: "back.out(2.2)" }, 0.1);
    tl.fromTo("#s2-card", { opacity: 0, scale: 1.08, filter: "blur(10px)" }, { opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.45, ease: "expo.out" }, 0.05);
    // "vendiste tres con ochenta": el número sube como un contador
    tl.to("#s2-num-in", { keyframes: [{ y: -230, duration: 0.18 }, { y: -460, duration: 0.18 }, { y: -690, duration: 0.3, ease: "back.out(2)" }], ease: "power2.inOut" }, 3.4);
    tl.fromTo("#s2-kpis div", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.45, ease: "expo.out", stagger: 0.12 }, 4.2);
    tl.to("#s2-card, #s2-sample", { opacity: 0, y: -40, filter: "blur(6px)", duration: 0.3, ease: "power3.in" }, 5.65);
    window.__timelines["s2"] = tl;
  </script>
</template>
""" % FONTS


RECS = [("r1", "↑ Subí el presupuesto", "#146C43"), ("r2", "= Mantené", "#2446D6"), ("r3", "↓ Bajá el presupuesto", "#8F5200")]


def s3():
    chips = "\n".join('    <div id="s3-%s-rec" class="rec" style="top:%dpx;background:%s">%s</div>' % (rid, top, ink, text)
                      for (rid, text, ink), top in zip(RECS, (338, 568, 798)))
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    #s3-badge { position: absolute; left: 0; right: 0; top: 190px; display: flex; align-items: center; justify-content: center; gap: 20px;
                font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 64px; }
    #s3-badge img { width: 110px; height: 110px; border-radius: 26px; }
    #s3-badge { display: none !important; }  /* el logo fijo de arriba ya muestra la marca */
    .rec { position: absolute; right: 100px; padding: 8px 18px; border-radius: 14px; color: #FFFFFF; font-size: 30px; font-weight: 800; }
    .row .roas { top: 70px; }
    .row .goal { display: none; }
    #s3-sample { display: none; position: absolute; right: 70px; top: 1296px; font-size: 28px; font-weight: 600; color: #5A6B7C; }
%s
  </style>
  <div id="root" data-composition-id="s3" data-width="1080" data-height="1920">
    <div id="s3-badge"><img src="assets/logo.svg" alt="">Lumo</div>
%s
%s
    <div id="s3-sample">Datos de ejemplo</div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#s3-r1, #s3-r2, #s3-r3", { clipPath: "inset(0%% 100%% 0%% 0%% round 34px)" }, { clipPath: "inset(0%% 0%% 0%% 0%% round 34px)", duration: 0.45, ease: "power3.out", stagger: 0.15 }, 0.15);
    tl.fromTo("#s3-r1 .chip, #s3-r2 .chip, #s3-r3 .chip", { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2.4)", stagger: 0.15 }, 0.45);
    // "subir, mantener o bajar": cada campaña recibe su recomendación
    tl.fromTo("#s3-r1-rec", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 3.3);
    tl.to("#s3-r1-ring", { opacity: 1, duration: 0.2 }, 3.3);
    tl.fromTo("#s3-r2-rec", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 3.8);
    tl.to("#s3-r2-ring", { opacity: 1, duration: 0.2 }, 3.8);
    tl.fromTo("#s3-r3-rec", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 4.3);
    tl.to("#s3-r3-ring", { opacity: 1, duration: 0.2 }, 4.3);
    window.__timelines["s3"] = tl;
  </script>
</template>
""" % (FONTS, ROWS_CSS, rows_html("s3"), chips)


def s4():
    src = (ROOT.parent / "v1-aviso" / "tools" / "base" / "s4.html").read_text(encoding="utf-8")
    return src.replace("at 922px 1122px", "at 540px 560px")


if __name__ == "__main__":
    for name, fn in (("s1", s1), ("s2", s2), ("s3", s3), ("s4", s4)):
        (ROOT / "compositions" / (name + ".html")).write_text(fn(), encoding="utf-8")
    print("escenas generadas:", VARIANT)
