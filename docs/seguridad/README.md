# Seguridad y privacidad de Lumo

Sistema de gestión liviano, alineado con **ISO/IEC 27001:2022** (seguridad de la información), **ISO/IEC 27701:2019** (privacidad) y los **criterios de confianza de SOC 2** (seguridad, disponibilidad, confidencialidad y privacidad).

> **Alcance honesto.** Esto es una base técnica y documental para llegar a una auditoría, no una certificación. Ni ISO ni SOC 2 se obtienen con código: las certifica un auditor externo y exigen evidencia de que los controles *funcionan en el tiempo*. Lo que sigue deja al día los controles técnicos, escribe las políticas y marca con claridad qué falta hacer a mano.

## Índice

| Documento | Para qué sirve |
|---|---|
| [alcance-y-activos.md](alcance-y-activos.md) | Qué protegemos: datos, sistemas, flujos y proveedores |
| [matriz-de-controles.md](matriz-de-controles.md) | Cada control ISO 27001 / SOC 2 / ISO 27701, cómo se cumple y dónde está la evidencia |
| [riesgos.md](riesgos.md) | Registro de riesgos, tratamiento y riesgo residual |
| [politicas.md](politicas.md) | Acceso, criptografía, registros, cambios, vulnerabilidades, conservación, continuidad |
| [incidentes.md](incidentes.md) | Cómo detectar, contener, avisar y aprender de un incidente |
| [privacidad.md](privacidad.md) | Registro de tratamientos, derechos de las personas y subencargados |
| [pendientes-del-titular.md](pendientes-del-titular.md) | Lo que no se puede hacer desde el código: configuraciones en Render, Supabase, GitHub, Google y Mercado Libre |

## Cómo se mantiene

- **Cada cambio** pasa por `.github/workflows/ci.yml`: tests, bandit y pip-audit.
- **Cada lunes** el CI corre solo para detectar vulnerabilidades nuevas en dependencias; Dependabot propone las actualizaciones.
- **Cada trimestre** se revisan: matriz de controles, riesgos, lista de administradores y subencargados (hay un recordatorio en [politicas.md](politicas.md#revisiones-periódicas)).
- **Responsable**: quien administra Lumo (cuentas en `ADMIN_USER_IDS`).
