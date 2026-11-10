# Alcance y activos

## Alcance

Lumo: la aplicación web (`backend/`), la portada estática (`site/`), la base de datos, la tarea diaria de avisos y los proveedores que intervienen. Fuera de alcance: Mercado Libre (es la fuente de los datos y tiene su propio régimen) y los dispositivos de las personas.

## Qué hace el sistema

Una persona conecta su cuenta de Mercado Libre (OAuth 2 con PKCE). Lumo **solo lee** sus métricas de Publicidad, las muestra en un panel y, si la persona lo activa, le envía avisos por email. El acceso es por invitación.

## Datos y clasificación

| Dato | Dónde | Clasificación | Protección |
|---|---|---|---|
| Tokens de Mercado Libre (`account.access_token`, `refresh_token`) | Base de datos | **Secreto** | Cifrado Fernet (AES-128-CBC + HMAC) con `ENCRYPTION_KEY`; rotación con `ENCRYPTION_KEY_PREVIOUS` |
| `ENCRYPTION_KEY`, `SECRET_KEY`, `ML_CLIENT_SECRET`, `SMTP_PASSWORD`, `CRON_TOKEN` | Variables de entorno de Render / secretos de GitHub | **Secreto** | Nunca en el repositorio; `.env` ignorado por git |
| ID de Mercado Libre, email (`account.email`) | Base de datos | **Personal** | Acceso solo por la sesión de esa persona; borrado y descarga disponibles |
| Métricas de campañas (`snapshot`, `campaign_day`) | Base de datos | **Confidencial** (datos comerciales del cliente) | Aislado por `user_id`; conservación limitada a 730 días |
| Estado del panel (`panel_state`) | Base de datos | Confidencial | Solo esa cuenta; tamaño tope 200 KB |
| Invitaciones (`invite`) | Base de datos | Confidencial | Token de 256 bits, un solo uso, vence a los 14 días |
| Registro de auditoría (`audit_log`) | Base de datos | Interno | Solo ids y tipos de evento; se conserva 400 días |

## Sistemas y proveedores

| Pieza | Proveedor | Datos que toca |
|---|---|---|
| Aplicación Flask (gunicorn) | Render (servicio `lumo`) | Todos |
| Portada estática | Render (servicio `lumo-sitio`) | Ninguno personal |
| Base de datos PostgreSQL | Supabase | Todos |
| Envío de avisos | Google (Gmail SMTP, `lumoads.ml@gmail.com`) | Email, texto del aviso |
| Tarea diaria | GitHub Actions | Ninguno (solo `APP_URL` y `CRON_TOKEN`) |
| Origen de los datos | Mercado Libre | Tokens y métricas |
| Tipografías | Google Fonts | IP de quien visita (ver riesgo R-09) |
| Código | GitHub | Código y secretos de Actions |

## Flujo de datos

```
Persona ──HTTPS──▶ Render (Flask) ──HTTPS──▶ API de Mercado Libre
                        │
                        ├──TLS (sslmode=require)──▶ Supabase (PostgreSQL)
                        └──STARTTLS──▶ Gmail SMTP ──▶ email de la persona
GitHub Actions ──HTTPS + X-Cron-Token──▶ /cron/avisos
```

## Roles

| Rol | Quién | Puede |
|---|---|---|
| Administrador | IDs en `ADMIN_USER_IDS` | Crear/revocar invitaciones, habilitar/quitar cuentas, ver el registro de actividad. La sesión vence a las 12 h |
| Cliente | Cuenta con fila en `access` | Ver su panel, descargar y borrar sus datos |
| Titular técnico | Quien tiene acceso a Render, Supabase, GitHub y Google | Ver y cambiar la configuración y los secretos |
