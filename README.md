# Lumo

Lee tus métricas de Product Ads y te dice qué mejorar con palabras simples.

- `backend/`: servidor (Python, Flask). Conecta con Mercado Libre y guarda los tokens cifrados.
- `design/`: prototipo de la interfaz y logos.
- `render.yaml`: configuración para publicar en Render.

## Probar en tu computadora

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests
```

## Publicar

1. Subir esta carpeta a un repositorio de GitHub.
2. En Supabase, copiar la cadena de conexión "Session pooler" (Project Settings, Database).
3. En Render: New, Blueprint, elegir el repositorio. Cargar `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `REDIRECT_URI` y `DATABASE_URL`.
4. En Mercado Libre: poner en la app la misma dirección que `REDIRECT_URI` (la dirección de Render más `/callback`).
5. Abrir la dirección de Render y tocar "Conectar con Mercado Libre".

Los secretos se cargan solo en Render. Nunca van en GitHub ni en el chat.
