# Registro de riesgos

Probabilidad (P) e impacto (I) de 1 a 3. Riesgo = P × I: 1–2 bajo, 3–4 medio, 6–9 alto. Se revisa cada trimestre.

| ID | Riesgo | P | I | Tratamiento | Residual |
|---|---|---|---|---|---|
| R-01 | Robo de la base de datos: filtra tokens, emails y métricas | 2 | 3 | Tokens cifrados con clave que no vive en la base; base solo por TLS; acceso a Supabase con MFA (⬜) | Medio: emails y métricas quedan en claro (el cifrado en reposo lo da Supabase) |
| R-02 | Pérdida o filtración de `ENCRYPTION_KEY` | 1 | 3 | Rotación (`rotate_keys.py`), copia guardada fuera de Render | Bajo |
| R-03 | Cuenta de administración comprometida | 2 | 3 | Sesión de 12 h, auditoría, MFA de Mercado Libre (⬜), alta/baja registradas | Medio |
| R-04 | Abuso de la API de Mercado Libre con un token robado (solo lectura) | 1 | 2 | Alcance de solo lectura; revocación desde Mercado Libre | Bajo |
| R-05 | Caída del servicio o pérdida de datos (plan gratuito, un único servidor) | 3 | 2 | Copias de Supabase (⬜ probar restauración), monitor externo (⬜) | Medio: se acepta mientras no haya acuerdo de nivel de servicio |
| R-06 | Dependencia vulnerable | 2 | 2 | Versiones fijadas, pip-audit semanal, Dependabot | Bajo |
| R-07 | XSS por scripts embebidos (CSP con `unsafe-inline`) | 1 | 2 | Todo dato externo se escapa; CSP cierra frames, bases, formularios y orígenes. Pendiente: sacar los scripts a archivos o usar nonces | Bajo |
| R-08 | Exposición de datos técnicos en mensajes de error | 2 | 1 | Solo código y ruta de Mercado Libre; sin trazas ni claves | Bajo |
| R-09 | Fuga de la IP de quien visita hacia Google Fonts | 2 | 1 | Pendiente: alojar las tipografías en `static/` | Bajo |
| R-10 | Error de un cambio llega a producción (no hay staging) | 2 | 2 | CI obligatorio, tests, protección de `main` (⬜) | Bajo |
| R-11 | Token de invitación visible en los registros de acceso de Render | 2 | 1 | Un solo uso, vence a los 14 días, revocable | Bajo |
| R-12 | Dato de una persona retenido sin necesidad | 2 | 2 | Plazos automáticos; borrado a pedido; revisión de cuentas inactivas (⬜ trimestral) | Bajo |
| R-13 | Aviso por email que revela datos comerciales a un destinatario equivocado | 1 | 2 | El email viene de Mercado Libre o lo carga la propia persona; opt-in; prueba de envío | Bajo |
| R-14 | Compromiso de la contraseña de aplicación de Gmail | 2 | 2 | Contraseña de aplicación (no la principal), solo en Render; MFA en la cuenta de Google (⬜) | Medio |

## Riesgos aceptados

R-05 y la parte de R-01 correspondiente a datos en claro dentro de la base se aceptan por el tamaño actual del servicio. Se proponen volver a evaluar al crecer la cantidad de cuentas o al sumar a alguien que acceda a los datos.
