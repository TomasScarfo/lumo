# Matriz de controles

Estado: ✅ implementado y con evidencia en el repositorio · 🟡 parcial · ⬜ depende de una acción manual (ver [pendientes-del-titular.md](pendientes-del-titular.md)).

Referencias: **ISO 27001:2022** Anexo A · **SOC 2** criterios comunes (CC) y adicionales (A disponibilidad, C confidencialidad, P privacidad) · **ISO 27701:2019** (7 = responsable, 8 = encargado).

## Control de acceso e identidad

| Control | ISO 27001 | SOC 2 | Estado | Cómo se cumple / evidencia |
|---|---|---|---|---|
| Acceso solo por invitación o alta del administrador | A.5.15, A.5.18 | CC6.1, CC6.2 | ✅ | `access.py`; `test_access.py` |
| Baja inmediata de acceso | A.5.18, A.8.2 | CC6.2, CC6.3 | ✅ | `_current_user()` revalida el acceso en **cada** pedido; `erase_user` borra todo. `test_seguridad.Privacidad` |
| Mínimo privilegio: administración separada | A.8.2 | CC6.3 | ✅ | `_admin_uid()`; a quien no administra la página le da 404 |
| Autenticación delegada y fuerte | A.5.17, A.8.5 | CC6.1 | 🟡 | OAuth 2 + PKCE + `state` (`ml.py`). La fuerza de la contraseña y el MFA dependen de la cuenta de Mercado Libre: ⬜ exigir MFA a los administradores |
| Sesiones acotadas | A.8.5 | CC6.1 | ✅ | Cookie `__Host-`, Secure, HttpOnly, SameSite=Lax; 30 días; administración 12 h. `test_seguridad.Sesiones` |
| Protección contra CSRF | A.8.26 | CC6.1 | ✅ | Token CSRF en formularios; verificación de `Origin`/`Sec-Fetch-Site` en todo POST. `test_seguridad.Pedidos` |
| Protección contra fuerza bruta y abuso | A.8.6, A.8.20 | CC6.6, A1.1 | ✅ | `security.RateLimiter` por IP y ruta; tope de cuerpo 1 MB |
| Revisión periódica de accesos | A.5.18 | CC6.2 | ⬜ | Trimestral, ver [políticas](politicas.md#revisiones-periódicas) |

## Criptografía y secretos

| Control | ISO 27001 | SOC 2 | Estado | Evidencia |
|---|---|---|---|---|
| Tokens cifrados en reposo | A.8.24 | CC6.1, C1.1 | ✅ | `crypto.py` (Fernet). `test_seguridad.Cifrado` |
| Gestión y rotación de claves | A.8.24 | CC6.1 | ✅ | `ENCRYPTION_KEY_PREVIOUS` + `rotate_keys.py`; procedimiento en [políticas](politicas.md#criptografía-y-claves) |
| Cifrado en tránsito | A.8.24, A.5.14 | CC6.7 | ✅ | HTTPS + HSTS; `sslmode=require` hacia Postgres; STARTTLS al enviar mail |
| Secretos fuera del código | A.5.17, A.8.4 | CC6.1 | ✅ | Variables de entorno; `.env` en `.gitignore`; `render.yaml` con `sync: false` |
| Arranque seguro | A.8.9 | CC6.1 | ✅ | Sin `SECRET_KEY` en producción la app no arranca; avisa si hay claves cortas |
| Cifrado de la base en reposo | A.8.24 | CC6.1 | ⬜ | Lo provee Supabase; confirmarlo |

## Seguridad de la aplicación

| Control | ISO 27001 | SOC 2 | Estado | Evidencia |
|---|---|---|---|---|
| Encabezados (CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy) | A.8.26, A.8.28 | CC6.6, CC6.8 | ✅ | `security.py`; `render.yaml` para la portada. `test_seguridad.Encabezados` |
| Escape de salida (XSS) | A.8.28 | CC6.8 | ✅ | Jinja autoescape; `_esc()`; el panel escapa con `esc()` |
| Sin caché de contenido privado | A.8.26 | C1.1 | ✅ | `no-store` salvo páginas públicas |
| Comparaciones en tiempo constante | A.8.28 | CC6.1 | ✅ | `security.safe_eq` (no falla con Unicode) |
| Validación de entradas | A.8.28 | CC6.8 | ✅ | Email, IDs acotados a 63 bits, tamaño de estado |
| Mensajes de error sin detalles internos | A.8.28 | CC7.2 | 🟡 | `/api/datos` devuelve código y ruta de Mercado Libre en `detail`; sin trazas. Aceptado (R-08) |
| Análisis estático | A.8.28, A.8.29 | CC7.1, CC8.1 | ✅ | bandit en `ci.yml` |
| CSP sin `unsafe-inline` | A.8.28 | CC6.8 | 🟡 | El panel usa scripts y estilos embebidos. Riesgo residual R-07 |

## Registros, monitoreo e incidentes

| Control | ISO 27001 | SOC 2 | Estado | Evidencia |
|---|---|---|---|---|
| Registro de auditoría | A.8.15 | CC7.2, CC7.3 | ✅ | Tabla `audit_log` (ingresos, denegaciones, altas/bajas, descargas, borrados, rotación, cron); visible en `/admin`. `test_seguridad.Auditoria` |
| Sin datos sensibles en los registros | A.8.15, A.8.11 | C1.1, P6 | ✅ | Solo ids; test que verifica que no hay emails ni tokens |
| Sincronización y retención de registros | A.8.15, A.8.17 | CC7.2 | 🟡 | 400 días en base; los registros de Render tienen retención propia: ⬜ configurar envío a un destino con alertas |
| Gestión de incidentes | A.5.24–A.5.28, A.6.8 | CC7.3–CC7.5 | ✅ | [incidentes.md](incidentes.md) |
| Contacto para reportes | A.5.5, A.6.8 | CC2.3 | ✅ | `SECURITY.md`, `/.well-known/security.txt` |

## Vulnerabilidades y cambios

| Control | ISO 27001 | SOC 2 | Estado | Evidencia |
|---|---|---|---|---|
| Gestión de vulnerabilidades técnicas | A.8.8 | CC7.1 | ✅ | Dependencias fijadas; pip-audit semanal y por cambio; Dependabot. Auditoría actual: 0 vulnerabilidades |
| Gestión de cambios | A.8.32 | CC8.1 | 🟡 | CI obligatorio en código; ⬜ activar protección de la rama `main` (revisión + CI requerido) |
| Menor privilegio en la automatización | A.8.2, A.8.9 | CC6.3 | ✅ | Workflows con `permissions` mínimos; acciones fijadas por SHA |
| Separación de ambientes | A.8.31 | CC8.1 | 🟡 | Local con SQLite y datos de prueba; no hay staging. Riesgo R-10 |

## Disponibilidad y continuidad

| Control | ISO 27001 | SOC 2 | Estado | Evidencia |
|---|---|---|---|---|
| Copias de seguridad y restauración | A.8.13 | A1.2, A1.3 | ⬜ | Supabase: confirmar plan, retención y **hacer una prueba de restauración** |
| Continuidad | A.5.29, A.5.30 | A1.2 | 🟡 | [políticas](politicas.md#continuidad-y-recuperación); sin alta disponibilidad (plan gratuito de Render, R-05) |
| Monitoreo de disponibilidad | A.8.16 | A1.1 | 🟡 | `/healthz` listo; ⬜ conectar un monitor externo con alerta |
| Recursos y capacidad | A.8.6 | A1.1 | ✅ | Topes de pedidos y de tamaño; pool con `pre_ping` |

## Proveedores

| Control | ISO 27001 | SOC 2 | Estado | Evidencia |
|---|---|---|---|---|
| Inventario y evaluación de proveedores | A.5.19–A.5.22 | CC9.2 | 🟡 | Listado en [privacidad.md](privacidad.md#subencargados); ⬜ guardar los informes SOC 2 / ISO de Render, Supabase y Google |

## Privacidad (ISO 27701 y SOC 2 P)

| Control | ISO 27701 | SOC 2 | Estado | Evidencia |
|---|---|---|---|---|
| Aviso de privacidad claro | 7.3.2, 7.3.3 | P1.1 | ✅ | `/privacidad`, enlace desde la portada |
| Registro de tratamientos | 7.2.8 | P1.1 | ✅ | [privacidad.md](privacidad.md) |
| Consentimiento y opt-in de avisos | 7.2.3, 7.2.4 | P2.1 | ✅ | Los avisos están apagados hasta que la persona los activa en Alertas |
| Minimización | 7.4.1–7.4.4 | P3.1, P3.2 | ✅ | Lumo solo lee y nunca ve contraseñas; sin IP en la base |
| Acceso y portabilidad | 7.3.9 | P5.1 | ✅ | `GET /api/cuenta/exportar` |
| Rectificación | 7.3.6 | P5.2 | ✅ | El email se corrige en Alertas |
| Supresión | 7.3.6, 7.4.5 | P4.3 | ✅ | `POST /cuenta/eliminar` y baja desde administración, con todos los datos |
| Plazos de conservación | 7.4.7 | P4.2 | ✅ | `privacy.purge` en el chequeo diario |
| Transferencias y subencargados | 7.5.x, 8.5.x | P6.1 | 🟡 | Listados; ⬜ confirmar región de Render/Supabase y términos de tratamiento de datos |
| Notificación de brechas | 7.3.x, 6.13.1.5 | P6.3 | ✅ | [incidentes.md](incidentes.md) |
| Evaluación de impacto | 7.2.5 | P1.1 | 🟡 | Riesgos de privacidad en [riesgos.md](riesgos.md); no hay datos sensibles ni decisiones automatizadas |
