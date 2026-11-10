# Pendientes del titular

Lo que el código no puede hacer por sí solo. Sin esto, varios controles de la [matriz](matriz-de-controles.md) quedan en ⬜. Ordenado por impacto; marcá cada punto con la fecha cuando lo hagas.

## Esta semana

- [ ] **Verificación en dos pasos** en Mercado Libre (cuenta administradora), Render, Supabase, GitHub y la cuenta de Google de `lumoads.ml@gmail.com`.
- [ ] **Render → variables de entorno**: confirmar que `SECRET_KEY` y `ENCRYPTION_KEY` tienen 32 caracteres o más y que `CRON_TOKEN` tiene 32 o más. Si el actual es más corto, cambiarlo en Render **y** en el secreto `CRON_TOKEN` de GitHub a la vez. La app lo avisa en el registro con «es demasiado corta».
- [ ] **Guardar una copia de `ENCRYPTION_KEY`** en un gestor de contraseñas, fuera de Render.
- [ ] **GitHub → Settings → Branches**: proteger `main` (pull request obligatorio, CI «test» requerido, sin push directo ni force-push).
- [ ] **GitHub → Settings → Security**: activar *Secret scanning*, *Push protection* y *Dependabot alerts*.
- [ ] **Supabase**: confirmar cifrado en reposo, plan de copias de seguridad y retención. Si hay acceso desde internet, restringirlo a las IPs de Render o usar el pooler con contraseña larga.

## Este mes

- [ ] **Prueba de restauración**: restaurar una copia de Supabase en un proyecto aparte y abrir el panel. Anotar fecha y resultado en `registro-de-pruebas.md`.
- [ ] **Monitor externo** (UptimeRobot, Better Stack u otro gratuito) sobre `https://TU-APP/healthz` con alerta por email.
- [ ] **Registros de Render**: revisar la retención y, si el plan lo permite, enviarlos a un destino con alertas.
- [ ] **Acuerdos de tratamiento de datos (DPA)** con Render, Supabase y Google; guardar sus informes SOC 2 / ISO 27001. Completar la región de cada uno en [privacidad.md](privacidad.md#subencargados).
- [ ] **Revisión legal** del aviso `/privacidad` y de las obligaciones de registro de la base de datos ante la autoridad de protección de datos.
- [ ] Revisar quién tiene acceso a Render, Supabase, GitHub y Google, y quitar lo que sobre.

## Cuando se pueda

- [ ] Alojar las tipografías en `static/` y sacar Google Fonts (cierra R-09).
- [ ] Mover los scripts y estilos del panel a archivos o usar nonces, y sacar `unsafe-inline` de la CSP (cierra R-07).
- [ ] Un entorno de prueba en Render con su propia base (cierra R-10).
- [ ] Plan de pago de Render y Supabase si el servicio pasa a ser crítico para los clientes (R-05).
- [ ] Una auditoría externa cuando se necesite el sello: ISO 27001 y SOC 2 Tipo II exigen meses de evidencia operando, no solo controles escritos.

## Al desplegar esta versión

- Las tablas nuevas (`audit_log`) se crean solas al arrancar.
- Las sesiones de administración existentes piden volver a conectar una vez (ahora vencen a las 12 h).
- Las sesiones de clientes pasan a durar 30 días en vez de 90, y la cookie cambia de nombre: todos tendrán que volver a entrar una vez.
- `ENCRYPTION_KEY_PREVIOUS` solo se usa durante una rotación; dejarla vacía.
