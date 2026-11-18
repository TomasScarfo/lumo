"""Genera las escenas del video 4 ("Black Friday"). Uso:  python3 tools/build_scenes.py mujer|hombre

Reutiliza el personaje (../personajes), el estilo de tarjetas del video 2 y el cierre del video 1.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "personajes"))
sys.path.insert(0, str(ROOT.parent / "v2-ganancia" / "tools"))
from personaje import personaje  # noqa: E402
from build_scenes import FONTS, ROWS_CSS  # noqa: E402  (video 2)

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "mujer"


def s1():
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    #s1-cam { position: absolute; inset: 0; }
    #s1-hook { position: absolute; left: 40px; right: 40px; top: 272px; text-align: center; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 58px; line-height: 1.02; letter-spacing: -0.02em; }
    #s1-char { position: absolute; left: -60px; top: 380px; width: 700px; height: 1700px; }
    #s1-bf { position: absolute; left: 560px; top: 470px; width: 450px; padding: 26px 30px 30px; border-radius: 30px; background: #0E0F12; color: #FFFFFF;
             box-shadow: 0 18px 40px rgba(19,32,44,.25); opacity: 0; }
    #s1-bf b { display: block; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 96px; line-height: 0.9; letter-spacing: -0.02em; }
    #s1-bf span { display: inline-block; margin-top: 18px; padding: 8px 18px; border-radius: 14px; background: #2446D6; font-size: 32px; font-weight: 800; }
    #s1-dial { position: absolute; left: 600px; top: 760px; width: 400px; height: 360px; opacity: 0; }
    #s1-blind { position: absolute; left: 168px; top: 646px; width: 184px; height: 62px; border-radius: 16px; background: #13202C; opacity: 0; }
    #s1-blind::after { content: ""; position: absolute; left: -46px; top: 18px; width: 56px; height: 22px; border-radius: 10px; background: #13202C; transform: rotate(18deg); }
    #s1-cover { position: absolute; inset: 0; background: #FFFFFF; opacity: 0; }
  </style>
  <div id="root" data-composition-id="s1" data-width="1080" data-height="1920">
    <div id="s1-cam">
      <div id="s1-hook">¿Hacés publicidad en Mercado Libre?</div>
      <!--personaje-->%s<!--/personaje-->
      <div id="s1-blind"></div>
      <div id="s1-bf"><b>BLACK<br>FRIDAY</b><span>27 de noviembre</span></div>
      <svg id="s1-dial" viewBox="0 0 400 360" aria-hidden="true" fill="none" stroke-linecap="round">
        <path d="M60 300 A140 140 0 0 1 340 300" stroke="#DAE2E9" stroke-width="36"/>
        <path d="M60 300 A140 140 0 0 1 130 179" stroke="#D9F1E3" stroke-width="36"/>
        <path d="M270 179 A140 140 0 0 1 340 300" stroke="#FADFDB" stroke-width="36"/>
                <g id="s1-needle"><path d="M200 300 L200 180" stroke="#13202C" stroke-width="12"/></g>
        <circle cx="200" cy="300" r="24" fill="#13202C"/>
        <text x="200" y="60" text-anchor="middle" font-family="Figtree" font-weight="900" font-size="40" fill="#13202C">Presupuesto</text>
      </svg>
    </div>
    <div id="s1-cover"></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.set("#s1-head", { svgOrigin: "320 470" }, 0);
    tl.to("#s1-body", { scaleY: 1.008, svgOrigin: "320 1700", duration: 1.6, ease: "sine.inOut", yoyo: true, repeat: 3 }, 0);
    tl.to("#s1-look", { x: 4, y: -6, duration: 0.25, ease: "power2.out" }, 0.4);
    tl.to("#s1-eyes", { scaleY: 0.1, svgOrigin: "320 300", duration: 0.05, ease: "none" }, 1.6);
    tl.to("#s1-eyes", { scaleY: 1, duration: 0.07, ease: "none" }, 1.66);
    // "Se viene el Black Friday": cae el cartel y festeja
    tl.fromTo("#s1-bf", { opacity: 0, y: -760, rotation: 8 }, { opacity: 1, y: 0, rotation: -5, duration: 0.6, ease: "back.out(1.5)" }, 2.6);
    tl.to("#s1-look", { x: 9, y: -2, duration: 0.2, ease: "power2.out" }, 2.75);
    tl.to("#s1-head", { rotation: 6, y: -8, duration: 0.4, ease: "back.out(1.8)" }, 2.8);
    tl.to("#s1-brow-l, #s1-brow-r", { y: -14, duration: 0.25, ease: "back.out(2)" }, 2.8);
    tl.set("#s1-m-smile", { opacity: 0 }, 2.85);
    tl.set("#s1-m-grin", { opacity: 1 }, 2.85);
    tl.to("#s1-arm-r", { rotation: -150, svgOrigin: "515 690", duration: 0.4, ease: "back.out(1.6)" }, 2.9);
    tl.to("#s1-fore-r", { rotation: -25, svgOrigin: "560 960", duration: 0.4, ease: "back.out(1.6)" }, 2.95);
    // "antes de subir el presupuesto a ciegas": venda en los ojos y la perilla al máximo
    tl.to("#s1-bf", { x: 120, y: -150, scale: 0.6, rotation: -8, duration: 0.5, ease: "power3.inOut", transformOrigin: "100%% 0%%" }, 4.4);
        tl.to("#s1-head, #s1-brow-l, #s1-brow-r", { rotation: 0, y: 0, duration: 0.3, ease: "power2.out" }, 4.4);
    tl.fromTo("#s1-blind", { opacity: 0, y: -40, scaleX: 0.6 }, { opacity: 1, y: 0, scaleX: 1, duration: 0.3, ease: "back.out(2)" }, 4.7);
    tl.fromTo("#s1-dial", { opacity: 0, scale: 0.6, transformOrigin: "50%% 80%%" }, { opacity: 1, scale: 1, duration: 0.45, ease: "back.out(1.7)" }, 4.6);
    tl.to("#s1-arm-r", { rotation: -55, svgOrigin: "515 690", duration: 0.4, ease: "back.out(1.6)" }, 4.8);
    tl.to("#s1-fore-r", { rotation: -60, svgOrigin: "560 960", duration: 0.4, ease: "back.out(1.6)" }, 4.85);
    tl.fromTo("#s1-needle", { rotation: -70 }, { rotation: 75, svgOrigin: "200 300", duration: 1.2, ease: "power2.in" }, 5.1);
    tl.to("#s1-needle", { keyframes: [{ rotation: 68, duration: 0.08 }, { rotation: 76, duration: 0.08 }, { rotation: 71, duration: 0.08 }] }, 6.3);
    // "Lumo te muestra": se saca la venda y se ve claro
    tl.to("#s1-blind", { y: -260, rotation: -30, opacity: 0, duration: 0.35, ease: "power3.in" }, 6.4);
    tl.set("#s1-m-grin", { opacity: 0 }, 6.45);
    tl.set("#s1-m-o", { opacity: 1 }, 6.45);
    tl.to("#s1-cover", { opacity: 1, duration: 0.25, ease: "power2.in" }, 6.75);
    window.__timelines["s1"] = tl;
  </script>
</template>
""" % (FONTS, personaje(VARIANT, "s1"))


ITEMS = [  # (id, publicación, estado, color, fondo, dato, valor, recomendación, color recomendación)
    ("p1", "Organizador de cajones", "Vende bien, poca publicidad", "#146C43", "#D9F1E3", "Ventas en 30 días", "24", "↑ Sumale publicidad", "#146C43"),
    ("p2", "Mesa plegable", "Gasta y no vende", "#B42318", "#FADFDB", "Invirtió", "$18.400", "✕ Pausala", "#B42318"),
    ("p3", "Cortinas blackout", "En su objetivo", "#2446D6", "#E3E9FC", "ROAS", "$3,4", "= Mantené", "#2446D6"),
]
TOPS = (330, 560, 790)


def s2():
    rows = "\n".join(
        '    <div id="s2-%s" class="row" style="top:%dpx"><div class="name">%s</div>'
        '<div class="chip" style="color:%s;background:%s">%s</div>'
        '<div class="roas">%s<b>%s</b></div>'
        '<div id="s2-%s-ring" class="row-ring" style="border-color:%s"></div></div>\n'
        '    <div id="s2-%s-rec" class="rec" style="top:%dpx;background:%s">%s</div>'
        % (i, top, name, ink, soft, state, lab, val, i, ink, i, top - 22, rink, rec)
        for (i, name, state, ink, soft, lab, val, rec, rink), top in zip(ITEMS, TOPS))
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    .rec { position: absolute; right: 100px; padding: 8px 18px; border-radius: 14px; color: #FFFFFF; font-size: 30px; font-weight: 800; opacity: 0; }
%s
  </style>
  <div id="root" data-composition-id="s2" data-width="1080" data-height="1920">
%s
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#s2-p1, #s2-p2, #s2-p3", { opacity: 0, filter: "blur(10px)", y: 30 }, { opacity: 1, filter: "blur(0px)", y: 0, duration: 0.45, ease: "expo.out", stagger: 0.12 }, 0.05);
    tl.fromTo("#s2-p1 .chip, #s2-p2 .chip, #s2-p3 .chip", { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2.4)", stagger: 0.12 }, 0.4);
    // "qué publicaciones venden y merecen más publicidad"
    tl.to("#s2-p1-ring", { opacity: 1, duration: 0.2 }, 1.9);
    tl.fromTo("#s2-p1-rec", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 1.9);
    // "y cuáles gastan sin vender"
    tl.to("#s2-p2-ring", { opacity: 1, duration: 0.2 }, 3.6);
    tl.fromTo("#s2-p2-rec", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 3.6);
    tl.fromTo("#s2-p3-rec", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)" }, 4.0);
    tl.to("#s2-p1, #s2-p2, #s2-p3, #s2-p1-rec, #s2-p2-rec, #s2-p3-rec", { opacity: 0, y: -40, filter: "blur(6px)", duration: 0.3, ease: "power3.in" }, 4.5);
    window.__timelines["s2"] = tl;
  </script>
</template>
""" % (FONTS, ROWS_CSS, rows)


def s3():
    return """<template>
  <style>
%s
    #root { position: absolute; inset: 0; background: #FFFFFF; overflow: hidden; font-family: "Figtree", sans-serif; color: #13202C; }
    .notif { position: absolute; left: 50px; right: 50px; background: #FFFFFF; border-radius: 34px; padding: 24px 28px 26px 44px; overflow: hidden;
             box-shadow: 0 18px 40px rgba(19,32,44,.16); border: 4px solid #DAE2E9; }
    .notif .bar { position: absolute; left: 0; top: 0; bottom: 0; width: 16px; }
    .notif .head { display: flex; align-items: center; gap: 14px; font-size: 30px; font-weight: 800; }
    .notif .head img { width: 52px; height: 52px; border-radius: 13px; }
    .notif .head span { margin-left: auto; font-weight: 500; color: #5A6B7C; }
    .notif .title { margin-top: 12px; font-size: 40px; line-height: 1.1; font-weight: 900; }
    .notif .text { margin-top: 8px; font-size: 32px; line-height: 1.25; font-weight: 600; color: #44566A; }
    #s3-cmp { position: absolute; left: 70px; right: 70px; top: 330px; height: 720px; background: #FFFFFF; border: 4px solid #DAE2E9; border-radius: 40px;
              box-shadow: 0 18px 40px rgba(19,32,44,.10); padding: 40px 44px; opacity: 0; }
    #s3-cmp .lead { font-size: 30px; font-weight: 800; color: #2446D6; }
    #s3-cmp .title { margin-top: 8px; font-family: "Bricolage Grotesque"; font-weight: 800; font-size: 64px; line-height: 1.02; letter-spacing: -0.02em; }
    .metric { position: absolute; left: 44px; right: 44px; }
    .metric .lab { font-size: 32px; font-weight: 800; }
    .metric .cmpbar { position: relative; height: 58px; margin-top: 12px; }
    .metric .fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 14px; }
    .metric .fill span { position: absolute; left: 18px; top: 0; line-height: 58px; font-size: 30px; font-weight: 800; color: #FFFFFF; white-space: nowrap; }
    .metric .up { position: absolute; right: 0; top: -6px; padding: 6px 16px; border-radius: 14px; background: #146C43; color: #FFFFFF; font-size: 32px; font-weight: 900; }
  </style>
  <div id="root" data-composition-id="s3" data-width="1080" data-height="1920">
    <div id="s3-n1" class="notif" style="top:330px"><div class="bar" style="background:#146C43"></div>
      <div class="head"><img src="assets/logo.svg" alt="">Lumo<span>ahora</span></div>
      <div class="title" style="color:#146C43">Publicaciones que venden bien sin publicidad</div>
      <div class="text"><b>Organizador de cajones:</b> 24 unidades vendidas en 30 días</div></div>
    <div id="s3-n2" class="notif" style="top:640px"><div class="bar" style="background:#B42318"></div>
      <div class="head"><img src="assets/logo.svg" alt="">Lumo<span>ahora</span></div>
      <div class="title" style="color:#B42318">Publicaciones que gastan y no venden</div>
      <div class="text"><b>Mesa plegable:</b> invirtió $18.400 y no vendió nada</div></div>
    <div id="s3-cmp">
      <div class="lead">Comparación con la semana anterior</div>
      <div class="title">Black Friday</div>
      <div class="metric" style="top:250px"><div class="lab">Ventas por publicidad</div><div class="up">+57 %%</div>
        <div class="cmpbar"><div id="s3-b1" class="fill" style="width:100%%;background:#146C43"><span>Black Friday · $1.250.000</span></div></div>
        <div class="cmpbar"><div id="s3-b2" class="fill" style="width:64%%;background:#5A6B7C"><span>Semana anterior · $798.000</span></div></div></div>
      <div class="metric" style="top:480px"><div class="lab">ROAS</div><div class="up">+21 %%</div>
        <div class="cmpbar"><div id="s3-b3" class="fill" style="width:100%%;background:#146C43"><span>Black Friday · $4,6</span></div></div>
        <div class="cmpbar"><div id="s3-b4" class="fill" style="width:83%%;background:#5A6B7C"><span>Semana anterior · $3,8</span></div></div></div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    // "durante la semana te avisa todos los días"
    tl.fromTo("#s3-n1", { y: -700 }, { y: 0, duration: 0.55, ease: "back.out(1.3)" }, 0.2);
    tl.fromTo("#s3-n2", { y: -1000 }, { y: 0, duration: 0.55, ease: "back.out(1.3)" }, 1.1);
    // "y después comparás cuánto te dejó la promo"
    tl.to("#s3-n1, #s3-n2", { y: -900, duration: 0.45, ease: "power3.in", stagger: 0.06 }, 3.1);
    tl.fromTo("#s3-cmp", { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.5, ease: "expo.out" }, 3.3);
    tl.fromTo("#s3-b1, #s3-b2, #s3-b3, #s3-b4", { clipPath: "inset(0%% 100%% 0%% 0%% round 14px)" }, { clipPath: "inset(0%% 0%% 0%% 0%% round 14px)", duration: 0.6, ease: "expo.out", stagger: 0.12 }, 3.6);
    tl.fromTo("#s3-cmp .up", { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2.4)", stagger: 0.25 }, 4.2);
    window.__timelines["s3"] = tl;
  </script>
</template>
""" % FONTS


def s4():
    src = (ROOT.parent / "v1-aviso" / "tools" / "base" / "s4.html").read_text(encoding="utf-8")
    return src.replace("at 922px 1122px", "at 540px 690px")


if __name__ == "__main__":
    for name, fn in (("s1", s1), ("s2", s2), ("s3", s3), ("s4", s4)):
        (ROOT / "compositions" / (name + ".html")).write_text(fn(), encoding="utf-8")
    print("escenas generadas:", VARIANT)
