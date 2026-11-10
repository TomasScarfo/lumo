# Privacidad

Lumo trata datos personales **como responsable** frente a quienes lo usan, y usa proveedores como **encargados** (ISO 27701 §7 y §8). Esta página es el registro de tratamientos y el procedimiento para los derechos de las personas. El aviso para el público es `/privacidad`.

> Esto no reemplaza el asesoramiento legal. Antes de crecer o de aceptar clientes fuera de Argentina, conviene que un abogado revise el aviso, la base legal y las obligaciones de registro ante la autoridad de protección de datos que corresponda.

## Registro de tratamientos

| Tratamiento | Datos | Finalidad | Base | Conservación |
|---|---|---|---|---|
| Conexión de la cuenta | ID de Mercado Libre, tokens (cifrados), permisos | Leer las métricas de la persona | Contrato / consentimiento al conectar | Mientras la cuenta esté conectada |
| Panel | Métricas de campañas, estado del panel | Mostrar el servicio | Contrato | Copia: 3 h de validez; historial: 730 días |
| Avisos por email | Email, preferencias, registro de avisos | Resumen semanal y alertas que la persona activó | Consentimiento (opt-in en Alertas) | Hasta que desactive o borre la cuenta; registro de envíos 400 días |
| Control de acceso | ID, nota del administrador, invitaciones | Permitir el ingreso solo a quien corresponde | Interés legítimo | Mientras tenga acceso; invitaciones 90 días tras vencer |
| Auditoría de seguridad | ID, tipo de evento, fecha | Detectar y investigar incidentes | Interés legítimo (seguridad) | 400 días |

No se tratan datos sensibles, ni se toman decisiones automatizadas sobre las personas, ni se hace perfilado ni publicidad.

## Derechos de las personas

| Derecho | Cómo se ejerce | Plazo |
|---|---|---|
| Acceso y portabilidad | Botón «Descargar mis datos» en `/privacidad` (JSON) | Inmediato |
| Rectificación | Cambiar el email en Alertas; para otros datos, escribir al contacto | 10 días |
| Supresión | Botón «Borrar mi cuenta y mis datos» en `/privacidad`, o pedido al contacto (el administrador usa Quitar acceso) | Inmediato / 10 días |
| Oposición al envío de avisos | Desactivarlos en Alertas | Inmediato |
| Consultas y reclamos | Email de contacto de la portada | 10 días |

**Pedidos por correo**: confirmar la identidad respondiendo desde el email registrado o pidiendo que se conecte la cuenta de Mercado Libre; nunca entregar datos a quien no pueda demostrarlo. Anotar fecha, pedido y respuesta.

**Alcance del borrado**: elimina cuenta, tokens, email, copia de datos, historial, panel, avisos y acceso. Quedan el **registro de auditoría** (solo ID y tipo de evento, 400 días, por seguridad) y copias de seguridad de Supabase hasta que vencen según su retención. No revoca la autorización dentro de Mercado Libre: la persona lo hace desde su perfil, y el aviso de borrado se lo explica.

## Subencargados

| Proveedor | Servicio | Datos | Región | Estado de los términos |
|---|---|---|---|---|
| Render | Hosting de la app y la portada | Todos | ⬜ confirmar | ⬜ aceptar el acuerdo de tratamiento (DPA) |
| Supabase | Base de datos | Todos | ⬜ confirmar | ⬜ DPA |
| Google | SMTP de los avisos; Google Fonts | Email y contenido del aviso; IP de quien visita | — | ⬜ DPA de Google Workspace / términos de Gmail |
| GitHub | Código y tarea diaria | Ninguno personal | — | — |
| Mercado Libre | Origen de los datos | — | — | Términos de la API |

Cualquier proveedor nuevo que toque datos personales se agrega acá **antes** de usarlo.

## Privacidad desde el diseño

- Solo lectura y mínimo de datos; no se guardan IPs ni contraseñas.
- Los avisos nacen apagados.
- Cada tabla con datos de una persona se indexa por su ID y está incluida en `privacy.erase_user` y `privacy.export_user`. **Al agregar una tabla nueva con datos personales hay que sumarla a esas dos funciones** (un test falla si falta en el borrado).
