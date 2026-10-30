# Lumo

Lee tus métricas de Product Ads y te dice qué mejorar con palabras simples.

- `backend/`: servidor (Python, Flask). Conecta con Mercado Libre, guarda los tokens cifrados, lee Product Ads y sirve el panel (`backend/lumo/panel.html`).
- `design/`: prototipo de la interfaz con datos de ejemplo y logos.
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
3. En Render: New, Blueprint, elegir el repositorio. Cargar `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `REDIRECT_URI`, `DATABASE_URL` y `ADMIN_USER_IDS`. Opcionales: `CONTACT_EMAIL`, `CONTACT_WHATSAPP` y `CONTACT_LINKEDIN` (ya tienen valores por defecto).
4. En Mercado Libre: poner en la app la misma dirección que `REDIRECT_URI` (la dirección de Render más `/callback`).
5. Abrir la dirección de Render, ingresar con Mercado Libre y crear invitaciones en `/admin`.

## Acceso

Lumo es por invitación. Entran los administradores (`ADMIN_USER_IDS`), las cuentas habilitadas en `/admin` y quien abre un enlace `/invitacion/...` de un solo uso. Las cuentas que ya estaban conectadas antes de este control siguen entrando.

Los secretos se cargan solo en Render. Nunca van en GitHub ni en el chat.
