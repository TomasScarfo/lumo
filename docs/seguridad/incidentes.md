# Respuesta a incidentes

Un incidente es cualquier hecho que ponga en riesgo la confidencialidad, integridad o disponibilidad de Lumo o de los datos de sus clientes: acceso no autorizado, filtración de un secreto, pérdida de datos, caída prolongada, envío de un aviso a quien no corresponde.

## Severidad

| Nivel | Ejemplo | Primera respuesta |
|---|---|---|
| **Crítico** | Filtración de la base o de `ENCRYPTION_KEY`; acceso de un tercero a administración | Inmediata |
| **Alto** | Secreto expuesto sin evidencia de uso; caída de más de 4 h | En 4 h |
| **Medio** | Aviso enviado a destinatario equivocado; vulnerabilidad reportada sin explotación | En 1 día hábil |
| **Bajo** | Intentos de abuso bloqueados por los topes | Revisión semanal |

## Pasos

1. **Detectar y registrar.** Anotar hora, quién lo detectó, qué se vio y de dónde viene (reporte, registro de actividad, Render, un cliente). Abrir una nota privada con la línea de tiempo.
2. **Contener.** Según el caso:
   - Secreto expuesto → rotarlo ya ([políticas](politicas.md#criptografía-y-claves)). Si fue `SECRET_KEY`, se cierran todas las sesiones.
   - Cuenta de administración comprometida → sacar su ID de `ADMIN_USER_IDS`, cambiar `SECRET_KEY`, revisar `audit_log`.
   - Token de Mercado Libre expuesto → pedir a las personas afectadas que revoquen la autorización en su perfil, y quitar la cuenta en `/admin`.
   - Servidor comprometido → suspender el servicio en Render, redesplegar limpio, rotar **todos** los secretos.
3. **Evaluar.** ¿Qué datos, de cuántas personas, durante cuánto tiempo? El registro de actividad y los registros de Render responden la mayor parte.
4. **Avisar.** Si hay datos personales afectados con riesgo para las personas: avisar a cada afectada **sin demora y dentro de las 72 horas** de tener certeza, por el email que Lumo conoce o por WhatsApp. El aviso dice qué pasó, qué datos, qué hicimos, qué conviene que haga la persona (revocar permisos, cambiar su contraseña) y a quién escribir. Revisar con asesoramiento legal si corresponde avisar además a la autoridad de protección de datos que aplique. Avisar a Mercado Libre si hay tokens comprometidos.
5. **Recuperar.** Restaurar, verificar con los tests y con el panel, y vigilar el registro de actividad durante una semana.
6. **Aprender.** En los 5 días hábiles siguientes: causa raíz, qué control falló o faltaba, y una acción concreta con fecha. Se agrega a [riesgos.md](riesgos.md) y, si corresponde, un test.

## Plantilla de registro

```
Fecha y hora de detección:
Detectado por:
Severidad:
Qué pasó:
Datos y personas afectadas:
Contención (hora y acción):
Avisos enviados (a quién y cuándo):
Causa raíz:
Acciones correctivas (responsable y fecha):
```

## Contactos

| Quién | Para qué |
|---|---|
| Administrador de Lumo | Dirige la respuesta |
| Soporte de Render, Supabase, Google | Registros, restauración, bloqueo de cuentas |
| Soporte de Mercado Libre (equipo de desarrolladores) | Tokens comprometidos, cambio del secreto de la aplicación |
