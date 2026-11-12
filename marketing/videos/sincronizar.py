"""Exporta un video en sus dos versiones (vendedora y vendedor), cada una sincronizada con su propia voz.

    python3 sincronizar.py v1-aviso        (o v2-ganancia, v3-peso)

Cómo funciona:
- Las escenas se armaron sobre una línea de tiempo "base": la voz de mujer del video 1, o tiempos aproximados en los
  videos 2 y 3. Cada voz real dura distinto, así que el script estira o encoge esa línea de tiempo por tramos: el
  comienzo de cada oración de la base cae justo donde empieza esa oración en la voz real.
- Los subtítulos usan el texto exacto del guion con los tiempos de la voz. Whisper a veces oye mal ("ZACO" por ACOS),
  así que se alinean las palabras del guion con las oídas y las que no coinciden se interpolan.
- Cada proyecto guarda sus archivos base en tools/base/ y su configuración en tools/sync_config.py.
"""
import difflib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
VOICE_START = 0.3  # la voz entra a los 0,3 s del video
VARIANTS = ("mujer", "hombre")


def norm(w):
    w = unicodedata.normalize("NFD", w.lower())
    return re.sub(r"[^a-z0-9ñ]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))


def heard_words(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "voices" in data:
        data = data["voices"][0]["words"]
    elif isinstance(data, dict):
        data = data.get("words", [])
    out = []
    for w in data:
        for part in (["y", "si"] if w["text"] == "Ysi" else [w["text"]]):
            out.append({"text": part, "start": float(w["start"]), "end": float(w["end"])})
    return out


def align(script, heard):
    """Tiempos de la voz para cada palabra del guion."""
    a, b = [norm(w) for w in script], [norm(w["text"]) for w in heard]
    times = [None] * len(script)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            h = heard[blk.b + k]
            times[blk.a + k] = (h["start"], h["end"])
    known = [i for i, t in enumerate(times) if t]
    for i, t in enumerate(times):  # las que no coinciden: se reparten entre las vecinas que sí
        if t:
            continue
        prev = max([k for k in known if k < i], default=None)
        nxt = min([k for k in known if k > i], default=None)
        s = times[prev][1] if prev is not None else (heard[0]["start"] if heard else 0)
        e = times[nxt][0] if nxt is not None else (heard[-1]["end"] if heard else s + 0.4)
        lo = prev if prev is not None else -1
        hi = nxt if nxt is not None else len(script)
        step = (e - s) / (hi - lo)
        times[i] = (s + (i - lo - 1) * step, s + (i - lo) * step)
    first = heard[0]["start"] if heard else 0
    onset = max(first, 0.3) if first < 0.05 else first  # Whisper a veces marca 0 s aunque la voz arranque después
    words = [{"text": w, "start": round(t[0] + VOICE_START, 3), "end": round(t[1] + VOICE_START, 3)} for w, t in zip(script, times)]
    words[0]["start"] = round(max(words[0]["start"], onset + VOICE_START), 3)
    words[0]["end"] = max(words[0]["end"], words[0]["start"] + 0.12)
    return words


def sentence_starts(script):
    idx = [0]
    for i, w in enumerate(script[:-1]):
        if re.search(r"[.?:!…]$", w):
            idx.append(i + 1)
    return idx


def make_warp(pairs):
    pairs = sorted(pairs)

    def f(t):
        if t <= pairs[0][0]:
            return t + (pairs[0][1] - pairs[0][0])
        for (a0, b0), (a1, b1) in zip(pairs, pairs[1:]):
            if t <= a1:
                return b0 + (t - a0) * (b1 - b0) / (a1 - a0)
        return t + (pairs[-1][1] - pairs[-1][0])
    return f


POS = re.compile(r"^(\s*tl\..*,\s*)([0-9]+(?:\.[0-9]+)?)(\);\s*)$")


def warp_scene(path, old_start, new_start, warp):
    lines = path.read_text(encoding="utf-8").split("\n")
    for i, ln in enumerate(lines):
        m = POS.match(ln)
        if m and float(m.group(2)) > 0:
            t = warp(old_start + float(m.group(2))) - new_start
            lines[i] = "%s%s%s" % (m.group(1), ("%.3f" % max(0.0, t)).rstrip("0").rstrip("."), m.group(3))
    path.write_text("\n".join(lines), encoding="utf-8")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def export(project):
    root = HERE / project
    cfg = load(root / "tools" / "sync_config.py", "sync_config")
    caps = load(root / "tools" / "captions.py", "captions_" + project.replace("-", "_"))
    script = caps.SCRIPT.split()
    base_words = cfg.base_words(root, caps, script)
    anchors = sentence_starts(script)
    index_base = (root / "tools" / "base" / "index.html").read_text(encoding="utf-8")
    hosts = [(m.group(1), float(m.group(2)), float(m.group(3)))
             for m in re.finditer(r'<div id="(s\d)"[^>]*data-start="([0-9.]+)" data-duration="([0-9.]+)"', index_base)]
    root_dur = float(re.search(r'data-composition-id="main" data-start="0" data-duration="([0-9.]+)"', index_base).group(1))
    blue_base = caps.BLUE_FROM
    for variant in VARIANTS:
        wav, words_file = cfg.VOICES[variant]
        words = align(script, heard_words(root / words_file))
        warp = make_warp([(base_words[i]["start"], words[i]["start"]) for i in anchors])
        cfg.build(root, variant)  # escenas base con el personaje de esta versión
        html = index_base
        for hid, start, dur in hosts:
            ns, ne = warp(start), warp(start + dur)
            warp_scene(root / "compositions" / (hid + ".html"), start, ns, warp)
            html = re.sub(r'(<div id="%s"[^>]*data-start=")[0-9.]+(" data-duration=")[0-9.]+"' % hid,
                          lambda m: '%s%.3f%s%.3f"' % (m.group(1), ns, m.group(2), ne - ns), html)
        # el botón y el link del cierre entran justo cuando la voz dice "Probalo"
        probalo = next(w["start"] for w in words if norm(w["text"]) == "probalo")
        end_host = max(hosts, key=lambda h: h[1])
        end_id, end_start = end_host[0], warp(end_host[1])
        end_file = root / "compositions" / (end_id + ".html")
        end_file.write_text(re.sub(r"\}, [0-9.]+\); // probalo(?:\+([0-9.]+))?",
                                   lambda m: "}, %.3f); // probalo%s" % (probalo - end_start + float(m.group(1) or 0), "+" + m.group(1) if m.group(1) else ""),
                                   end_file.read_text(encoding="utf-8")), encoding="utf-8")
        new_root = round(max(warp(root_dur), words[-1]["end"] + 2.5), 2)
        html = re.sub(r'data-duration="%s"' % re.escape(("%g" % root_dur)), 'data-duration="%g"' % new_root, html)
        # el cierre dura hasta el final del video (si no, los últimos cuadros quedan en blanco)
        html = re.sub(r'(<div id="%s"[^>]*data-start="[0-9.]+" data-duration=")[0-9.]+"' % end_id,
                      lambda m: '%s%.3f"' % (m.group(1), new_root - end_start), html)
        html = re.sub(r'(<audio id="vo" src=")[^"]+"', lambda m: m.group(1) + wav + '"', html)
        (root / "index.html").write_text(html, encoding="utf-8")
        caps.BLUE_FROM = warp(blue_base)
        caps.build(words)
        out = HERE / "renders" / ("lumo-%s-%s.mp4" % (cfg.NAME, variant))
        print("·", project, variant, "· voz %.1f s · video %.1f s" % (words[-1]["end"], new_root), flush=True)
        subprocess.run(["npx", "hyperframes", "check", "--json"], cwd=root, check=False, capture_output=True)
        subprocess.run(["npx", "hyperframes", "render", "-q", "delivery", "-o", str(out)], cwd=root, check=True,
                       stdout=subprocess.DEVNULL)
        print("  →", out.relative_to(HERE), flush=True)


if __name__ == "__main__":
    for p in sys.argv[1:] or ("v1-aviso", "v2-ganancia", "v3-peso"):
        export(p)
