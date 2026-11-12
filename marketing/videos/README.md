# Videos de Lumo para Meta Ads

Tres Reels verticales (1080×1920, 30 fps), cada uno en dos versiones: con la vendedora (`-mujer`) y con el vendedor (`-hombre`). Los MP4 terminados están en `renders/`.

| Video | Idea |
|---|---|
| `lumo-video1-aviso` | Llega un aviso de Lumo: una publicación vende sola y conviene sumarla a la campaña. Después, el aviso de una que gasta y no vende. |
| `lumo-video2-ganancia` | Le llueven siglas (ROAS, ACOS, CTR…). Lumo las ordena en campañas con su estado y recomienda qué hacer. |
| `lumo-video3-peso` | Tira $1 a la publicidad. Lumo le dice cuánto volvió ($3,8) y qué hacer con cada presupuesto. |

Voces: la versión de mujer del video 1 usa la voz que generaste en AI Studio. Las otras cinco salen de Gemini (voz Kore para la mujer y Charon para el hombre), con la clave guardada en `.env`, que no se sube a git. Cada versión está sincronizada con su propia voz.

Los guiones completos, con la voz en off de cada video, están en `GUIONES.md`. Los personajes se dibujan en `personajes/personaje.py`; para verlos actuando, abrí la vista previa de `personajes/`.

## Volver a exportar

Desde esta carpeta: `python3 sincronizar.py` exporta los 6 videos, o uno solo con `python3 sincronizar.py v2-ganancia`. Las escenas base de cada video están en `tools/base/` y en `tools/build_scenes.py`; las voces, en `assets/voice/`.

Para regenerar una voz: `node ~/.claude/skills/media-use/audio/scripts/audio.mjs --request ./audio_request_mujer.json --hyperframes . --out ./audio_meta_mujer.json --only tts` desde la carpeta del video, con la clave cargada (`set -a; . ../.env; set +a`).
