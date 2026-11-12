"""Personajes de los videos de Lumo: una vendedora y un vendedor de Mercado Libre, mismo estilo y mismo esqueleto.

personaje("mujer" | "hombre", prefijo) devuelve el <svg> listo para pegar en una escena. Todas las piezas que se animan
tienen el mismo id en las dos versiones (con el prefijo adelante), así una escena funciona igual con cualquiera:

  {p}-body   todo el cuerpo (respiración)            {p}-head    cabeza, gira sobre el cuello (HEAD_PIVOT)
  {p}-eyes   los dos ojos (parpadeo: scaleY)         {p}-look    pupilas (hacia dónde mira: x, y)
  {p}-brow-l / {p}-brow-r   cejas
  {p}-m-smile / m-talk / m-o / m-grin / m-worry      bocas: se muestra una por vez (opacity)
  {p}-arm-l / {p}-arm-r     brazo entero, gira en el hombro (ARM_PIVOT)
  {p}-fore-l / {p}-fore-r   antebrazo y mano, gira en el codo (ELBOW_PIVOT)

Estilo: ilustración plana con trazo de 5 px #13202C, una sombra plana por zona, sin degradés (como el logo).
"""

INK = "#13202C"
W, H = 700, 1700  # viewBox; el personaje mira de frente, centrado en x=320

# Puntos de giro en coordenadas del dibujo: usarlos con svgOrigin (no transformOrigin, que GSAP mide desde cada pieza).
HEAD_PIVOT = "320 470"
ARM_PIVOT = {"l": "125 690", "r": "515 690"}
ELBOW_PIVOT = {"l": "80 960", "r": "560 960"}
BROW_PIVOT = {"l": "300 246", "r": "340 246"}
EYES_PIVOT = "320 300"
MOUTH_PIVOT = "320 405"

LOOKS = {
    "mujer": dict(skin="#F2C7A5", skin_shade="#E2AC86", hair="#3B2A22", hair_hi="#5A4034", shirt="#CFDBFF", shirt_shade="#B3C4F4", iris="#5A3A26", pants="#2E3A4F"),
    "hombre": dict(skin="#D9A27E", skin_shade="#C08665", hair="#2B211C", hair_hi="#43352D", shirt="#D9F1E3", shirt_shade="#B9E1C9", iris="#3D4F2E", pants="#3E5A8C"),
}


def _arm(p, side, c):
    """Brazo de dos tramos: manga (color de la remera) hasta el codo y antebrazo con mano."""
    sx, sy = (125, 690) if side == "l" else (515, 690)
    ex, ey = (80, 960) if side == "l" else (560, 960)
    wx, wy = (80, 1190) if side == "l" else (560, 1190)
    return f"""
        <g id="{p}-arm-{side}">
          <path d="M{sx} {sy} L{ex} {ey}" stroke="{INK}" stroke-width="84" stroke-linecap="round"/>
          <path d="M{sx} {sy} L{ex} {ey}" stroke="{c['shirt']}" stroke-width="72" stroke-linecap="round"/>
          <g id="{p}-fore-{side}">
            <path d="M{ex} {ey} L{wx} {wy}" stroke="{INK}" stroke-width="66" stroke-linecap="round"/>
            <path d="M{ex} {ey} L{wx} {wy}" stroke="{c['skin']}" stroke-width="54" stroke-linecap="round"/>
            <path d="M{ex - 34} {ey + 4} L{ex + 34} {ey + 4}" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>
            <path d="M{ex - 34} {ey - 4} C{ex - 34} {ey - 40} {ex + 34} {ey - 40} {ex + 34} {ey - 4} Z" fill="{c['shirt']}" stroke="{INK}" stroke-width="5"/>
            <ellipse id="{p}-hand-{side}" cx="{wx}" cy="{wy + 30}" rx="36" ry="40" fill="{c['skin']}" stroke="{INK}" stroke-width="5"/>
          </g>
        </g>"""


def personaje(variant: str, p: str) -> str:
    c = LOOKS[variant]
    woman = variant == "mujer"
    back_hair = (f'<path d="M175 300 C160 160 240 102 320 102 C410 102 482 165 466 310 C470 420 492 520 502 622 '
                 f'C442 642 392 612 380 562 L260 562 C250 612 200 642 138 622 C150 520 170 420 175 300 Z" fill="{c["hair"]}" stroke="{INK}" stroke-width="5"/>'
                 if woman else "")
    front_hair = (
        f'<path d="M196 288 C198 176 268 126 340 130 C402 134 444 180 446 252 C412 222 372 202 332 198 C302 232 250 264 196 288 Z" fill="{c["hair"]}" stroke="{INK}" stroke-width="5"/>'
        f'<path d="M262 162 Q306 142 356 150" fill="none" stroke="{c["hair_hi"]}" stroke-width="9" stroke-linecap="round"/>'
        f'<circle cx="203" cy="358" r="8" fill="#F2C230" stroke="{INK}" stroke-width="4"/>'
        if woman else
        f'<path d="M194 272 C184 158 250 110 326 110 C402 110 456 158 448 266 C432 232 410 212 380 202 C350 216 282 216 252 202 C228 216 210 238 194 272 Z" fill="{c["hair"]}" stroke="{INK}" stroke-width="5"/>'
        f'<path d="M262 150 Q306 132 352 140" fill="none" stroke="{c["hair_hi"]}" stroke-width="9" stroke-linecap="round"/>'
        f'<path d="M198 268 L214 268 L216 332 L201 332 Z" fill="{c["hair"]}"/><path d="M442 268 L426 268 L424 332 L439 332 Z" fill="{c["hair"]}"/>'
        f'<path d="M210 352 C226 440 276 470 320 470 C364 470 414 440 430 352 C414 418 372 446 320 448 C268 446 226 418 210 352 Z" fill="{c["hair"]}" opacity=".22"/>'
    )
    lashes = (f'<path d="M248 280 l-12 -8 M392 280 l12 -8" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>' if woman else "")
    brow_w = 9 if woman else 13
    collar = (f'<path d="M272 598 L320 676 L368 598 Z" fill="{c["skin"]}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
              if woman else
              f'<path d="M262 596 L300 664 L322 606 Z" fill="{c["shirt"]}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
              f'<path d="M378 596 L340 664 L318 606 Z" fill="{c["shirt"]}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
              f'<circle cx="320" cy="720" r="7" fill="{INK}"/><circle cx="320" cy="800" r="7" fill="{INK}"/>')
    return f"""<svg id="{p}-char" class="personaje {variant}" viewBox="0 0 {W} {H}" style="overflow:visible" data-layout-allow-overflow aria-hidden="true" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <g id="{p}-body">
        {back_hair}
        <path d="M118 1700 L122 1250 L518 1250 L522 1700 Z" fill="{c['pants']}" stroke="{INK}" stroke-width="5"/>
        <path d="M320 1300 L320 1700" stroke="{INK}" stroke-width="5"/>
        <path d="M100 1270 L95 790 C100 660 190 600 320 596 C450 600 540 660 545 790 L540 1270 C420 1290 220 1290 100 1270 Z" fill="{c['shirt']}"/>
        <path d="M450 640 C520 680 545 760 545 900 L540 1270 C520 1274 500 1276 478 1278 Z" fill="{c['shirt_shade']}"/>
        <path d="M100 1270 L95 790 C100 660 190 600 320 596 C450 600 540 660 545 790 L540 1270 C420 1290 220 1290 100 1270 Z" stroke="{INK}" stroke-width="5"/>
        <path d="M285 440 L285 572 C300 586 340 586 355 572 L355 440 Z" fill="{c['skin']}" stroke="{INK}" stroke-width="5"/>
        <path d="M287 470 C305 505 335 505 353 470 L353 512 C335 530 305 530 287 512 Z" fill="{c['skin_shade']}"/>
        {collar}
        {_arm(p, "l", c)}
        {_arm(p, "r", c)}
        <g id="{p}-head">
          <ellipse cx="200" cy="318" rx="22" ry="34" fill="{c['skin']}" stroke="{INK}" stroke-width="5"/>
          <ellipse cx="440" cy="318" rx="22" ry="34" fill="{c['skin']}" stroke="{INK}" stroke-width="5"/>
          <path d="M200 300 C200 200 255 150 320 150 C385 150 440 200 440 300 C440 390 395 462 320 468 C245 462 200 390 200 300 Z" fill="{c['skin']}" stroke="{INK}" stroke-width="5"/>
          <circle cx="252" cy="372" r="22" fill="#F4A9A0" opacity=".5"/>
          <circle cx="388" cy="372" r="22" fill="#F4A9A0" opacity=".5"/>
          {front_hair}
          <path id="{p}-brow-l" d="M246 250 Q272 236 300 246" stroke="{c['hair']}" stroke-width="{brow_w}"/>
          <path id="{p}-brow-r" d="M340 246 Q368 236 394 250" stroke="{c['hair']}" stroke-width="{brow_w}"/>
          <g id="{p}-eyes">
            {lashes}
            <g id="{p}-eye-l"><ellipse cx="275" cy="300" rx="25" ry="29" fill="#FFFFFF" stroke="{INK}" stroke-width="5"/></g>
            <g id="{p}-eye-r"><ellipse cx="365" cy="300" rx="25" ry="29" fill="#FFFFFF" stroke="{INK}" stroke-width="5"/></g>
            <g id="{p}-look">
              <circle cx="275" cy="303" r="15" fill="{c['iris']}"/><circle cx="275" cy="303" r="8" fill="{INK}"/><circle cx="281" cy="296" r="5" fill="#FFFFFF"/>
              <circle cx="365" cy="303" r="15" fill="{c['iris']}"/><circle cx="365" cy="303" r="8" fill="{INK}"/><circle cx="371" cy="296" r="5" fill="#FFFFFF"/>
            </g>
          </g>
          <path d="M322 318 Q310 352 328 357" stroke="{INK}" stroke-width="5"/>
          <path id="{p}-m-smile" d="M290 398 Q320 424 350 398" stroke="{INK}" stroke-width="6"/>
          <path id="{p}-m-talk" d="M297 396 Q320 432 343 396 Z" fill="#7A2E2E" stroke="{INK}" stroke-width="5" opacity="0"/>
          <ellipse id="{p}-m-o" cx="320" cy="410" rx="15" ry="20" fill="#7A2E2E" stroke="{INK}" stroke-width="5" opacity="0"/>
          <g id="{p}-m-grin" opacity="0"><path d="M282 392 Q320 448 358 392 Z" fill="#7A2E2E" stroke="{INK}" stroke-width="5"/><path d="M290 397 Q320 405 350 397 L347 406 Q320 412 293 406 Z" fill="#FFFFFF"/></g>
          <path id="{p}-m-worry" d="M292 414 Q306 400 320 410 Q334 420 348 406" stroke="{INK}" stroke-width="6" opacity="0"/>
        </g>
      </g>
    </svg>"""


MOUTHS = ("smile", "talk", "o", "grin", "worry")


def mouth_js(p: str, mouth: str, at: float) -> str:
    """Cambia de boca en un instante (una sola visible). Devuelve líneas de GSAP."""
    lines = ['    tl.set("#%s-m-%s", { opacity: %d }, %.2f);' % (p, m, 1 if m == mouth else 0, at) for m in MOUTHS]
    lines.append('    tl.fromTo("#%s-m-%s", { scale: 0.75 }, { scale: 1, duration: 0.28, ease: "back.out(2.4)", svgOrigin: "%s" }, %.2f);' % (p, mouth, MOUTH_PIVOT, at))
    return "\n".join(lines)


def idle_js(p: str, duration: float, blinks=()) -> str:
    """Vida en reposo: respira (un ciclo cada 3,2 s) y parpadea en los momentos dados."""
    cycles = max(1, int(duration / 1.6))
    out = ['    tl.to("#%s-body", { scaleY: 1.012, svgOrigin: "320 1700", duration: 1.6, ease: "sine.inOut", yoyo: true, repeat: %d }, 0);' % (p, cycles - 1)]
    for b in blinks:
        out.append('    tl.to("#%s-eyes", { scaleY: 0.1, svgOrigin: "%s", duration: 0.05, ease: "none" }, %.2f);' % (p, EYES_PIVOT, b))
        out.append('    tl.to("#%s-eyes", { scaleY: 1, duration: 0.07, ease: "none" }, %.2f);' % (p, b + 0.06))
    return "\n".join(out)
