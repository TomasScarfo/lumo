"""Configuración de sincronizar.py. La base son los tiempos aproximados con los que se armaron las escenas."""
import subprocess

NAME = "video3-peso"
VOICES = {"mujer": ("assets/voice/voz-mujer.wav", "audio_meta_mujer.json"),
          "hombre": ("assets/voice/voz-hombre.wav", "audio_meta_hombre.json")}


def base_words(root, caps, script):
    return caps.approx_words()


def build(root, variant):
    subprocess.run(["python3", "tools/build_scenes.py", variant], cwd=root, check=True, stdout=subprocess.DEVNULL)
