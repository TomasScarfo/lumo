"""Configuración de sincronizar.py para el video 1. La base es la voz de mujer (la grabada primero)."""
import shutil
import sys
from pathlib import Path

NAME = "video1-aviso"
VOICES = {"mujer": ("assets/voice/voz-mujer.wav", "audio_meta_mujer.json"),
          "hombre": ("assets/voice/voz-hombre.wav", "audio_meta_hombre.json")}


def base_words(root, caps, script):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from sincronizar import align, heard_words
    return align(script, heard_words(root / "assets/voice/transcript.json"))


def build(root, variant):
    for name in ("s1", "s2", "s3", "s4"):
        shutil.copyfile(root / "tools" / "base" / (name + ".html"), root / "compositions" / (name + ".html"))
    import subprocess
    subprocess.run(["python3", "tools/personaje.py", variant], cwd=root, check=True, stdout=subprocess.DEVNULL)
