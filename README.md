# Lumo

Lee tus métricas de Product Ads y te dice qué mejorar con palabras simples.

- `backend/`: servidor (Python, Flask). Conecta con Mercado Libre, guarda los tokens cifrados, lee Product Ads y sirve el panel (`backend/lumo/panel.html`).
- `design/`: prototipo de la interfaz con datos de ejemplo y logos.
- `site/`: la portada estática, generada con `backend/build_site.py`. Se publica aparte para que cargue al instante aunque el servidor esté dormido.
- `render.yaml`: configuración para publicar en Render (la app y la portada).

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
5. Para cobrar: en Mercado Pago (Tus integraciones, crear aplicación) copiar el Access Token de producción y cargarlo en Render como `MP_ACCESS_TOKEN`, junto con `PLAN_PRICE` (precio mensual, por ejemplo `15000`).
6. En esa misma aplicación de Mercado Pago, en Webhooks, poner `https://TU-APP.onrender.com/webhooks/mercadopago`, marcar el evento "Planes y suscripciones" y copiar la clave secreta en Render como `MP_WEBHOOK_SECRET`.
7. Abrir la dirección de Render e ingresar con Mercado Libre. En `/admin` se ven las pruebas y suscripciones.

## Acceso y cobro

- Cualquier cuenta nueva de Mercado Libre empieza una prueba gratis de 14 días (`TRIAL_DAYS`), sin tarjeta. Es una sola por cuenta.
- Al terminar la prueba, la persona va a `/suscripcion` y se suscribe con Mercado Pago (cobro mensual automático). Si se suscribe durante la prueba, el primer cobro es el día que termina.
- Si cancela, sigue entrando hasta la fecha ya paga.
- Entran gratis los administradores (`ADMIN_USER_IDS`), las cuentas habilitadas en `/admin` y quien abre un enlace `/invitacion/...`.
- Sin `MP_ACCESS_TOKEN` o `PLAN_PRICE`, la prueba funciona pero no se puede pagar (la página invita a escribir por email).
- Para probar pagos sin dinero real, usar las credenciales y usuarios de prueba de Mercado Pago.

Los secretos se cargan solo en Render. Nunca van en GitHub ni en el chat.

## Portada estática

En el plan gratuito, Render apaga la app cuando nadie la usa y al volver muestra su pantalla de espera. Por eso la portada se publica aparte, como sitio estático (servicio `lumo-sitio`), que nunca se apaga:

- Al abrir la portada, despierta la app en segundo plano.
- Si alguien toca "Ingresar" antes de que la app esté lista, ve la espera de Lumo ("Abriendo Lumo…") en vez de la de Render, y entra solo cuando la app responde.

Para activarla en Render:

1. En el servicio `lumo-sitio`, cargar `APP_URL` con la dirección de la app (por ejemplo `https://lumo-xxxx.onrender.com`).
2. En el servicio `lumo`, cargar `SITE_URL` con la dirección de `lumo-sitio`. Así quien entra a la app sin sesión (o sale) va a la portada.

Después de cambiar la portada, los estilos o el logo, regenerarla (un test avisa si quedó vieja):

```bash
cd backend && python build_site.py
```
