# Políticas

Cada política es corta a propósito: se cumple y se puede probar. Aprobadas por quien administra Lumo; se revisan cada año o ante un cambio grande.

## Control de acceso

1. El acceso a Lumo es por invitación o por alta explícita del administrador. No hay registro abierto.
2. Los administradores son los IDs de `ADMIN_USER_IDS`. Se agrega o quita un administrador cambiando esa variable en Render; el cambio queda anotado en el registro de cambios del equipo.
3. Todo administrador y todo titular técnico usa **verificación en dos pasos** en Mercado Libre, Render, Supabase, GitHub y Google. Sin excepciones.
4. Un acceso se quita el mismo día que deja de hacer falta. Quitar una cuenta de cliente borra sus datos (`/admin` → Quitar acceso).
5. Los accesos a Render, Supabase, GitHub y Google son personales, nunca compartidos.

## Criptografía y claves

- Tokens de Mercado Libre: cifrados con `ENCRYPTION_KEY` antes de guardarse. Se descifran solo en memoria.
- Secretos: solo en variables de entorno de Render y secretos de GitHub. Nunca en el repositorio, en chats ni en tickets.
- Mínimos: `SECRET_KEY` y `ENCRYPTION_KEY` de 32 caracteres aleatorios o más; `CRON_TOKEN` de 32 o más. La app avisa en el registro si alguno es más corto.
- Copia de `ENCRYPTION_KEY`: guardada en un gestor de contraseñas, fuera de Render. Si se pierde, todas las cuentas tienen que reconectarse.

**Rotación de `ENCRYPTION_KEY`** (cada 12 meses o ante sospecha de filtración):

1. Generar una clave nueva: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. En Render: poner la nueva en `ENCRYPTION_KEY` y la anterior en `ENCRYPTION_KEY_PREVIOUS`. Desplegar.
3. En la consola de Render: `cd backend && python rotate_keys.py`. Debe informar 0 cuentas que no se pudieron leer.
4. Borrar `ENCRYPTION_KEY_PREVIOUS`. Desplegar.

**Rotación de los demás secretos**: `SECRET_KEY` (cierra todas las sesiones, es aceptable), `CRON_TOKEN` (cambiarlo en Render y en el secreto de GitHub a la vez), `SMTP_PASSWORD` (generar otra contraseña de aplicación y revocar la anterior), `ML_CLIENT_SECRET` (regenerar en el panel de desarrolladores de Mercado Libre). Todos, ante cualquier sospecha y al menos una vez al año.

## Registros y monitoreo

- La app registra en `audit_log`: ingresos, accesos denegados, altas y bajas de acceso, invitaciones, descargas y borrados de datos, rotación de claves y corridas del chequeo diario.
- No se guardan contraseñas, tokens, emails ni IPs en la base.
- Se revisa el registro de actividad en `/admin` cada semana y siempre que haya un aviso de seguridad. Señales que se investigan: muchos `login_denied` seguidos, un `access_grant` que nadie pidió, un `account_erase` inesperado.
- Los registros técnicos de Render se leen ante cualquier error 5xx repetido o intento de abuso (`tope de pedidos superado`, `pedido de otro origen rechazado`).

## Gestión de cambios

1. Todo cambio entra por pull request; no se empuja a `main`.
2. El CI (tests, bandit, pip-audit) tiene que estar en verde.
3. Quien aprueba no es quien escribió el cambio, salvo que haya una sola persona; en ese caso se deja constancia en la descripción del PR.
4. Los cambios que tocan acceso, cifrado, sesiones o privacidad agregan o actualizan un test en `backend/tests/test_seguridad.py`.
5. Se despliega desde `main`; si algo falla, se vuelve atrás con *Rollback* en Render.

## Vulnerabilidades y dependencias

- Todas las dependencias están fijadas (también las indirectas).
- Dependabot propone actualizaciones cada semana y el CI corre pip-audit cada lunes.
- Plazos para corregir: **crítica 48 h · alta 7 días · media 30 días · baja a criterio**.
- Los reportes externos entran por `SECURITY.md` y se contestan en 3 días hábiles.

## Conservación y borrado

| Dato | Plazo | Cómo |
|---|---|---|
| Datos de la cuenta, panel, avisos | Mientras la cuenta esté activa | Borrado a pedido o por baja |
| Historial de campañas | 730 días | Automático (`history.save`, `privacy.purge`) |
| Registro de auditoría | 400 días | Automático (`privacy.purge`) |
| Registro de avisos enviados | 400 días | Automático |
| Invitaciones | 90 días después de vencer | Automático |
| Cuentas sin entrar en 12 meses | Se avisa y se borran | Revisión trimestral manual |

## Continuidad y recuperación

- **Objetivos**: restaurar el servicio en 24 h (RTO) con una pérdida de datos máxima de 24 h (RPO). Son metas; hay que comprobarlas con una prueba.
- **Pérdida del servidor**: redesplegar desde `main` en Render con las mismas variables de entorno.
- **Pérdida de la base**: restaurar la última copia de Supabase y reconectar.
- **Prueba de restauración**: una vez por semestre se restaura una copia en un proyecto aparte y se verifica que el panel abre. Se anota la fecha y el resultado en `docs/seguridad/registro-de-pruebas.md`.
- La tarea de avisos reintenta sola (`curl --retry`) mientras Render despierta.

## Revisiones periódicas

| Cuándo | Qué |
|---|---|
| Cada semana | Registro de actividad en `/admin`; pull requests de Dependabot |
| Cada trimestre | Lista de administradores y titulares técnicos; cuentas inactivas; subencargados; matriz de controles y riesgos |
| Cada semestre | Prueba de restauración; simulacro de incidente |
| Cada año | Rotación de secretos; revisión de estas políticas; capacitación breve para quien tenga acceso |
