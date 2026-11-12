"""Arma compositions/captions.html con los subtítulos del video.

Sin grabación todavía: reparte el tiempo de cada frase entre sus palabras según su largo (tiempos APROXIMADOS)
y los guarda en assets/transcript-aprox.json. Cuando esté la voz real, se transcribe con
    npx hyperframes transcribe assets/voice/voz.wav --model small --language es
y se corre este script con ese archivo:  python3 tools/captions.py assets/transcript.json
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLUE_FROM = 17.2  # desde acá el fondo es azul (cierre): subtítulos en blanco
MAX_WORDS = 4
VOICE_START = 0.3
VOICE_ONSET = 0.3  # ajustar al primer sonido del archivo de voz

LINES = [
    (0.4, 3.6, "Por cada peso que ponés en publicidad en Mercado Libre…"),
    (3.8, 5.3, "¿cuánto vuelve en ventas?"),
    (5.8, 10.8, "Lumo te lo dice en una frase: por cada peso invertido, vendiste tres con ochenta."),
    (11.6, 16.6, "Y campaña por campaña te recomienda qué hacer: subir, mantener o bajar el presupuesto."),
    (17.4, 22.0, "Lumo: tu asistente de publicidad en Mercado Libre, para gastar mejor y vender más. Probalo gratis 14 días."),
]
SCRIPT = " ".join(line for _, _, line in LINES)  # el texto exacto del guion corrige lo que Whisper escribe mal


def approx_words():
    out = []
    for start, end, text in LINES:
        words = text.split()
        weights = [len(w) + 2 for w in words]
        span, t = end - start, start
        for w, k in zip(words, weights):
            d = span * k / sum(weights)
            out.append({"text": w, "start": round(t, 3), "end": round(t + d * 0.92, 3)})
            t += d
    return out


def groups(words):
    """Grupos de hasta MAX_WORDS palabras. Se corta en la puntuación y en las pausas largas, y cada frase se reparte
    en partes parejas (7 palabras: 4 + 3, no 4 + 3 + ... de a una). "Mercado Libre" nunca se separa."""
    phrases, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = nxt is not None and nxt["start"] - w["end"] >= 0.3
        if re.search(r"[.,:;?!]$", w["text"]) or pause or nxt is None:
            phrases.append(cur)
            cur = []
    out = []
    for ph in phrases:
        k = -(-len(ph) // MAX_WORDS)
        sizes = [len(ph) // k + (1 if r < len(ph) % k else 0) for r in range(k)]
        pos = 0
        for n in sizes:
            chunk = ph[pos:pos + n]
            if chunk and chunk[-1]["text"] == "Mercado" and pos + n < len(ph):
                n -= 1
                chunk = ph[pos:pos + n]
            out.append(chunk)
            pos += n
        if pos < len(ph):
            out[-1] = out[-1] + ph[pos:]
    return [g for g in out if g]


def build(words):
    css, divs, js = [], [], []
    gs = groups(words)
    for gi, g in enumerate(gs):
        gid = "cap-g%d" % gi
        start = max(0.1, g[0]["start"] - 0.05)
        end = g[-1]["end"] + 0.15
        if gi + 1 < len(gs):  # un solo grupo a la vez: se va antes de que entre el siguiente
            end = min(end, max(0.1, gs[gi + 1][0]["start"] - 0.05) - 0.02)
        blue = g[0]["start"] >= BLUE_FROM
        spans = " ".join('<span id="%s-w%d">%s</span>' % (gid, wi, w["text"]) for wi, w in enumerate(g))
        divs.append('      <div id="%s" class="cap%s"><span class="box">%s</span></div>' % (gid, " blue" if blue else "", spans))
        js.append('    tl.set("#%s", { visibility: "visible" }, %.3f);' % (gid, start))
        js.append('    tl.fromTo("#%s", { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.12, ease: "power2.out" }, %.3f);' % (gid, start))
        for wi, w in enumerate(g):
            js.append('    tl.set("#%s-w%d", { className: "on" }, %.3f);' % (gid, wi, w["start"]))
        js.append('    tl.to("#%s", { opacity: 0, duration: 0.12, ease: "power2.in" }, %.3f);' % (gid, end - 0.12))
        js.append('    tl.set("#%s", { opacity: 0, visibility: "hidden" }, %.3f);' % (gid, end))
    html = """<template>
  <style>
    @font-face { font-family: "Figtree"; src: url("assets/fonts/Figtree.ttf"); font-weight: 300 900; }
    #root { position: absolute; inset: 0; pointer-events: none; }
    .cap { position: absolute; left: 0; right: 0; top: 1150px; padding: 0 60px; text-align: center; font-family: "Figtree", sans-serif;
           font-weight: 800; font-size: 60px; line-height: 1.2; overflow: visible; opacity: 0; visibility: hidden; }
    .cap .box { display: inline-block; padding: 12px 26px 14px; border-radius: 20px; background: rgba(19, 32, 44, 0.9); color: #FFFFFF;
                box-shadow: 0 8px 24px rgba(19, 32, 44, 0.25); }
    .cap .box span.on { color: #FFD24D; }
    .cap.blue .box { background: rgba(10, 20, 70, 0.55); }
  </style>
  <div id="root" data-composition-id="captions" data-width="1080" data-height="1920">
%s
  </div>
  <script>
    // Generado por tools/captions.py: no editar a mano los tiempos, regenerar.
    const tl = gsap.timeline({ paused: true });
%s
    window.__timelines["captions"] = tl;
  </script>
</template>
""" % ("\n".join(divs), "\n".join(js))
    (ROOT / "compositions" / "captions.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        raw = [w for w in (data.get("words", data) if isinstance(data, dict) else data) if w.get("text", "").strip()]
        words = []
        for w in raw:  # Whisper a veces junta dos palabras ("Ysi"): se reparten el tiempo
            parts = ["Y", "si"] if w["text"] == "Ysi" else [w["text"]]
            step = (w["end"] - w["start"]) / len(parts)
            for i, part in enumerate(parts):
                words.append({"text": part, "start": w["start"] + i * step, "end": w["start"] + (i + 1) * step})
        script = SCRIPT.split()
        if len(script) == len(words):
            for w, s in zip(words, script):
                w["text"] = s
        else:
            print("ojo: la transcripción tiene %d palabras y el guion %d; quedan las de Whisper" % (len(words), len(script)))
        words[0]["start"] = max(words[0]["start"], VOICE_ONSET)  # donde arranca la voz dentro del archivo
        words[0]["end"] = max(words[0]["end"], words[0]["start"] + 0.12)
        for w in words:
            w["start"] = round(w["start"] + VOICE_START, 3)
            w["end"] = round(w["end"] + VOICE_START, 3)
    else:
        words = approx_words()
        (ROOT / "assets" / "transcript-aprox.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    build(words)
    print("subtítulos:", len(words), "palabras,", len(groups(words)), "grupos")
