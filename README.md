# Lumo

Lee tus métricas de Product Ads y te dice qué mejorar con palabras simples.

- `backend/`: servidor (Python, Flask). Conecta con Mercado Libre, guarda los tokens cifrados, lee Product Ads y sirve el panel (`backend/lumo/panel.html`).
- `design/`: prototipo de la interfaz con datos de ejemplo y logos.
- `site/`: la portada estática, generada con `backend/build_site.py`. Se publica aparte para que cargue al instante aunque el servidor esté dormido.
- `render.yaml`: configuración para publicar en Render (la app y la portada).
- `docs/seguridad/`: políticas, matriz de controles (ISO 27001, SOC 2, ISO 27701), riesgos, incidentes y privacidad. Ver también `SECURITY.md`.

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
3. En Render: New, Blueprint, elegir el repositorio. Cargar `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `REDIRECT_URI`, `DATABASE_URL` y `ADMIN_USER_IDS`. Opcionales: `CONTACT_EMAIL` (ya tienen valores por defecto).
4. En Mercado Libre: poner en la app la misma dirección que `REDIRECT_URI` (la dirección de Render más `/callback`).
5. Para cobrar: en Mercado Pago (Tus integraciones, crear aplicación) copiar el Access Token de producción y cargarlo en Render como `MP_ACCESS_TOKEN`. Los precios ya vienen cargados (`PLAN_PRICE_USD` y `PLAN_PRICE_ANNUAL_USD`).
6. En esa misma aplicación de Mercado Pago, en Webhooks, poner `https://TU-APP.onrender.com/webhooks/mercadopago`, marcar los eventos "Planes y suscripciones" y "Pagos de suscripciones" (así Lumo se entera de los cobros rechazados) y copiar la clave secreta en Render como `MP_WEBHOOK_SECRET`.
7. Abrir la dirección de Render e ingresar con Mercado Libre. En `/admin` se ven las pruebas y suscripciones.

## Acceso y cobro

- **Prueba gratis:** 14 días (`TRIAL_DAYS`), una sola por cuenta. Empieza cuando la persona elige un plan y Mercado Pago confirma su medio de pago; no se cobra nada hasta el día 15. Si cancela antes, no paga.
- **Planes:** mensual (`PLAN_PRICE_USD`) y anual (`PLAN_PRICE_ANNUAL_USD`). El ahorro del anual se calcula solo y se muestra como descuento.
- **Dólares y pesos:** el precio se muestra en dólares y Mercado Pago cobra en pesos. Lumo convierte con el dólar oficial vendedor (`USD_RATE_URL`) al suscribirse y, cada día, actualiza el monto de las suscripciones activas si la cotización se movió más de 1 %. `USD_ARS_RATE` fija la cotización a mano.
- **Renovación:** automática, cada mes o cada año. Tres días antes del primer cobro se manda un email de aviso.
- **Legales:** `/terminos` (términos y condiciones) y `/arrepentimiento` (botón de arrepentimiento: cancela en el momento, da un código y avisa por email a `CONTACT_EMAIL` para devolver el cobro si lo hubo). Las devoluciones se hacen a mano desde Mercado Pago. La factura todavía no se emite desde Lumo.
- **Cobro rechazado:** la cuenta sigue entrando 7 días (`GRACE_DAYS`) y recibe un email. Si no regulariza, el acceso se pausa; no se borra nada.
- **Cambio de plan:** desde `/suscripcion`. El plan nuevo empieza cuando termina lo ya pago y reemplaza al anterior recién cuando Mercado Pago lo confirma.
- **Cancelación:** desde `/suscripcion`; sigue entrando hasta la fecha ya paga. Borrar la cuenta o quitar el acceso desde `/admin` también corta el cobro.
- **Acceso sin cargo:** administradores (`ADMIN_USER_IDS`), cuentas habilitadas en `/admin` y quien abre un enlace `/invitacion/...` entran gratis, sin vencimiento.
- **Chequeo diario:** la tarea de GitHub que llama a `/cron/avisos` también sincroniza las suscripciones con Mercado Pago, actualiza montos y manda los avisos (prueba por terminar, cobro rechazado, acceso pausado). Necesita `CRON_TOKEN` y, para los emails, `BREVO_API_KEY` y `MAIL_FROM` (Brevo envía por HTTPS, así que sirve en el plan gratis de Render, que bloquea el SMTP). Sin Brevo, usa `SMTP_PASSWORD` solo si el plan de Render permite SMTP.
- Sin `MP_ACCESS_TOKEN`, la prueba funciona pero no se puede pagar (la página invita a escribir).
- Para probar pagos sin dinero real, usar las credenciales y usuarios de prueba de Mercado Pago.

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
