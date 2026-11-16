# Métricas y recomendaciones de Lumo

Qué datos muestra Lumo, de dónde salen y en qué se basa cada recomendación. Está armado leyendo el código (`backend/lumo/ads.py`, `cuenta.py`, `notify.py`, `exportar.py` y `panel.html`) en el estado de `main` del 16/11/2026. Si cambia la lógica, este documento hay que actualizarlo.

Convenciones: **API** = dato que Mercado Libre informa tal cual. **Calculada** = la hace Lumo a partir de datos de la API. **Estimada** = calculada repartiendo un total entre partes; no es un dato real de Mercado Libre.

---

## 1. De dónde se leen los datos

Todo es de solo lectura. Lumo hace estas consultas con el permiso que da la persona al conectar su cuenta.

| Consulta a Mercado Libre | Qué trae | Ventana |
|---|---|---|
| `product_ads/campaigns/search` | Lista de campañas: nombre, estado (activa/pausada), presupuesto diario, `roas_target`, `acos_target`, estrategia | Hoy |
| `product_ads/campaigns/{id}` (diario) | Por día y campaña: `cost`, `clicks`, `prints`, `direct_units_quantity`, `indirect_units_quantity`, `direct_amount`, `indirect_amount` | Últimos 90 días (el máximo de Mercado Libre) |
| `product_ads/campaigns/{id}` (participación) | `impression_share`, `top_impression_share`, `lost_impression_share_by_budget`, `lost_impression_share_by_ad_rank`, `acos_benchmark` | Últimos 30 días hasta el último día con datos, sin importar el período que elija la persona |
| `product_ads/ad_groups/search` | Por publicación (grupo de anuncios): `cost`, `clicks`, `prints`, `direct_amount`, `indirect_amount`, `total_amount`, unidades directas/asistidas/totales y **orgánicas** (`organic_units_quantity`, `organic_units_amount`); además título, precio, enlace, campaña, estado, tipo (ITEM o FAMILY), dominio y marca | Dos tramos de 30 días: los últimos 30 y los 30 anteriores |
| `/items` | Stock disponible (`available_quantity`), categoría, marca (atributo BRAND) | Hoy; solo publicaciones individuales (tipo ITEM), hasta 300 |
| `/visits/items` | Visitas de cada publicación | Últimos 30 días |
| `/categories/{id}` | Nombre de la categoría | — |
| `/users/me` | Apodo, sitio, reputación del vendedor, ventas concretadas, email | Hoy |
| `/users/{id}/items/search` | Cantidad de publicaciones activas | Hoy (solo cuentas sin Publicidad) |

Además Lumo **guarda cada día** las cifras diarias de cada campaña (inversión, clics, impresiones, unidades y ventas). Así el historial supera los 90 días de Mercado Libre y llega hasta 2 años, pero solo desde la fecha en que la cuenta se conectó.

El último día con datos completos es ayer (hoy mismo antes de las 10:00 de Argentina no hay datos nuevos, por eso se usa anteayer).

---

## 2. Métricas que vienen directo de Mercado Libre

Se muestran sin transformar, salvo que se suman por período.

| Métrica en Lumo | Campo de la API | Nivel | Dónde se ve |
|---|---|---|---|
| Inversión publicitaria | `cost` | Campaña, día | Métricas, gráfico, tabla de campañas, Excel |
| Clics | `clicks` | Campaña, día | Idem |
| Impresiones | `prints` | Campaña, día | Idem |
| Ventas por publicidad (monto) | `direct_amount` + `indirect_amount` (suma de ventas directas y asistidas) | Campaña, día | Idem |
| Unidades vendidas con publicidad | `direct_units_quantity` + `indirect_units_quantity` | Campaña, día | Gráfico ("Ventas"), tabla por día |
| Presupuesto diario | `budget` | Campaña | Tabla de campañas |
| ROAS objetivo | `roas_target`; si no viene, `100 ÷ acos_target`; si tampoco, **$5 estimado** (se marca "estimado") | Campaña | Tabla, estados, recomendaciones |
| Participación de impresiones | `impression_share` | Campaña (30 días) | Tabla de campañas |
| Impresiones perdidas por presupuesto | `lost_impression_share_by_budget` | Campaña (30 días) | Tabla de campañas |
| Impresiones perdidas por ranking | `lost_impression_share_by_ad_rank` | Campaña (30 días) | Tabla y texto de recomendaciones |
| Unidades vendidas sin publicidad | `organic_units_quantity` | Publicación (30 días y 30 previos) | Alertas, Tendencias |
| Ventas sin publicidad (monto) | `organic_units_amount` | Publicación (30 días y 30 previos) | Alertas, Tendencias |
| Stock | `available_quantity` | Publicación | Alertas |
| Visitas | `total_visits` | Publicación (30 días) | Alertas |
| Categoría, marca | `category_id` (nombre vía categorías), atributo BRAND | Publicación | Alertas, Tendencias |
| Precio | `price` | Publicación | Solo en simulaciones |
| Reputación, ventas concretadas, publicaciones activas, con stock | `/users/me`, `/items` | Cuenta | Solo cuentas sin Publicidad |

---

## 3. Métricas que calcula Lumo

| Métrica | Fórmula | Datos que usa | Dónde se ve | Ojo |
|---|---|---|---|---|
| **ROAS** | ventas por publicidad ÷ inversión | Diario de la campaña, en el período elegido | Todo el panel | Real a nivel campaña y cuenta |
| **ACOS** | inversión ÷ ventas por publicidad | Idem | Métricas | Es el inverso del ROAS |
| **CTR** | clics ÷ impresiones | Idem | Métricas, tabla | Real |
| **CPC** | inversión ÷ clics | Idem | Tabla | Real |
| **CVR** | unidades (directas + asistidas) ÷ clics | Idem | Métricas, tabla | Real |
| **Uso del presupuesto** | (inversión ÷ días del período) ÷ presupuesto diario | Diario + presupuesto de **hoy** | Tabla, recomendación de presupuesto | Usa el presupuesto actual aunque haya cambiado en el período |
| **Variación contra el período de comparación** | actual ÷ comparación − 1 | Diario; la comparación es período anterior, mes anterior o personalizado. Si tiene otra cantidad de días, se escala | Flechas de cada métrica | Con poca inversión es ruidosa |
| **Tendencia del ROAS** | ROAS actual ÷ ROAS de la comparación − 1 | Idem | Estados, recomendaciones | Solo campañas y cuenta; las publicaciones no tienen |
| **Variación de visibilidad** | impresiones actuales ÷ impresiones de la comparación − 1 | Idem | Recomendaciones de ROAS objetivo | — |
| **Estado de la campaña** | Ver sección 5.A | ROAS, ROAS objetivo, tendencia, ventas | Tabla, hero, gráfico de ROAS, filtros | Los umbrales son nuestros |
| **ROAS objetivo promedio de la cuenta** | promedio de los objetivos ponderado por inversión | Objetivos + inversión por campaña | Estado general de la cuenta | — |
| **Inversión, ventas, clics, impresiones y ROAS por publicación** | Parte de la campaña según el peso de la publicación en sus últimos 30 días: `inversión de la campaña × parte de la inversión`, y lo mismo con ventas, clics e impresiones | Totales de la campaña en el período + reparto por publicación de los últimos 30 días | Tabla (publicaciones), Alertas, tareas, mail semanal, Excel | **Estimada.** Con 30 días es casi exacta; con otro período es una extrapolación del reparto de 30 días |
| **Faltante de ventas** | inversión × ROAS objetivo − ventas de la publicación | ROAS por publicación estimado | Alertas | Estimada |
| **ROAS de la cuenta sin esa publicación** | (ventas − ventas de la publicación) ÷ (inversión − inversión de la publicación) | Idem | Alertas | Estimada |
| **Crecimiento de ventas orgánicas por publicación** | unidades orgánicas 30 días ÷ unidades 30 días previos − 1 | `organic_units_quantity` | Alertas | Si no había ventas previas, se toma 0% |
| **Conversión por publicación** | unidades orgánicas ÷ visitas | Orgánicas + visitas (30 días) | Alertas | Solo publicaciones individuales; las "familias" no tienen visitas |
| **Ventas totales de la cuenta (30 días)** | ventas orgánicas + ventas por publicidad estimadas por publicación | Orgánicas + ventas de campaña × parte de la publicación | Tendencias | Suma publicaciones estimadas |
| **Parte que vino de publicidad** | ventas por publicidad ÷ ventas totales | Idem | Tendencias | Idem |
| **Crecimiento y cobertura por categoría y marca** | crecimiento = ventas 30 días ÷ 30 días previos − 1; cobertura = publicaciones con publicidad ÷ total | Orgánicas + publicidad estimada, por categoría o marca | Tendencias, recomendaciones | Idem |

---

## 4. Datos que traemos y todavía no usamos

- `top_impression_share` (participación en las primeras posiciones) y `acos_benchmark` (referencia de ACOS de Mercado Libre): se leen y no se muestran ni intervienen en ninguna recomendación.
- Estrategia de la campaña.
- Separación entre ventas **directas** y **asistidas**: hoy se suman.
- Cantidad de ventas (`*_items_quantity`) y `total_amount` por campaña: figuran en el Glosario pero no se piden a nivel campaña.
- Precio y margen de cada producto: Lumo no conoce el costo, así que el ROAS no se traduce a ganancia real.

---

## 5. Recomendaciones y avisos

### A. Estado de cada campaña (base de las recomendaciones)

Se calcula con el ROAS del período, el ROAS objetivo de la campaña y la tendencia del ROAS contra el período de comparación. Con `k = ROAS ÷ ROAS objetivo`:

| Estado | Condición |
|---|---|
| Sin actividad | No invirtió nada en el período |
| Revisar | Invirtió y **no vendió nada**; o `k < 0,7` y su ROAS no subió 5% o más |
| Superando el objetivo | `k ≥ 1,2` |
| En objetivo | `0,9 ≤ k < 1,2` |
| Mejorando | `k < 0,9` y el ROAS subió **5% o más** contra la comparación |
| Con oportunidad | `0,7 ≤ k < 0,9` sin mejora de 5% |

El mismo criterio se aplica a la cuenta completa (con el ROAS objetivo promedio ponderado) y a cada publicación, **pero las publicaciones no tienen tendencia**: allí solo cuenta la distancia al objetivo.

### B. Recomendaciones por campaña (pestaña Recomendaciones y Tareas)

| Recomendación | Cuándo aparece | Datos y cuentas que toma | Qué recomienda |
|---|---|---|---|
| **Conviene revisarla, bajá el presupuesto** (urgente) | Estado Revisar | Inversión, ventas, ROAS, ROAS objetivo, tendencia del ROAS, variación de ventas (suma el aviso si las ventas cayeron 25% o más), presupuesto diario | Bajar el presupuesto diario a la mitad (redondeado a $500) y revisar las publicaciones en Alertas |
| **Tiene oportunidad de mejora** | Estado Con oportunidad | Inversión, ventas, ROAS, % del objetivo, tendencia | Mejorar las publicaciones que menos venden antes de subir presupuesto; o subir el ROAS objetivo si prefiere rentabilidad |
| **Viene mejorando** (buena noticia) | Estado Mejorando | ROAS, % del objetivo, tendencia | No tocar nada y mirar si llega al objetivo |
| **Está perdiendo visibilidad** | Impresiones del período −10% o peor contra la comparación, **y** con ventas | Variación de impresiones, ROAS, % del objetivo, impresiones perdidas por ranking (si son 20% o más lo agrega), tendencia | Bajar el ROAS objetivo de a poco para mostrarse más, a cambio de algo de rentabilidad. Si ya está por debajo del objetivo, lo advierte |
| **Tiene margen para ganar visibilidad** | Estado Superando el objetivo (si no hay visibilidad en caída) | ROAS vs objetivo, impresiones perdidas por ranking, tendencia | Igual que la anterior |
| **Gana visibilidad, pero cae su ROAS** | Impresiones +10% o más **y** ROAS −5% o peor | Variación de impresiones y de ROAS | Subir un poco el ROAS objetivo para recuperar rentabilidad |
| **Se queda sin presupuesto** | Uso del presupuesto 95% o más **y** estado Superando o En objetivo | Inversión por día, presupuesto diario, ROAS, ROAS objetivo | Subir el presupuesto diario 30% (redondeado a $500) |

Si se dan "gana visibilidad pero cae ROAS" y "margen para ganar visibilidad", solo aparece la primera, para no dar consejos contrarios.

### C. Recomendación por categoría

| Recomendación | Cuándo aparece | Datos | Qué recomienda |
|---|---|---|---|
| **[Categoría] crece X% y tiene poca facturación en campañas** | La categoría crece 10% o más (ventas totales 30 días vs 30 previos) **y** se cumple alguna de dos: menos del 70% de sus publicaciones tienen publicidad, o menos del 30% de su facturación de 30 días está integrada en campañas (ventas por publicidad ÷ ventas totales de la categoría) | Orgánicas + ventas por publicidad estimadas, cobertura y % de facturación en campañas por categoría | Ir a Alertas y activar las publicaciones con stock que ya venden |

La misma lógica aparece como insight "Para mirar primero" en Tendencias (por categoría o marca).

### D. Alertas por publicación (pestaña Alertas y Tareas)

**D1. Con publicidad y oportunidad de mejora.** Publicaciones con anuncios activos cuyo estado es Con oportunidad o Revisar (ROAS estimado menor al 90% del objetivo de su campaña). Se ordenan por faltante de ventas. Cada una muestra inversión, ventas, ROAS actual y objetivo, el faltante y el ROAS de la cuenta con y sin ella. La recomendación depende del caso, en este orden:

| Caso | Condición | Dice |
|---|---|---|
| Pausar | Invirtió y **no vendió nada** con publicidad | Pausar y revisar precio, fotos y stock antes de reactivar |
| Probar pausar | Se vende bien sola (10 o más unidades orgánicas y conversión 3% o más, o conversión desconocida) | Probablemente mantenga ventas sin anuncios; pausar unos días y comparar |
| Pausar o sacar de la campaña | ROAS menor al 70% del objetivo | Pausar o sacar de la campaña mientras mejora precio, fotos y título |
| Mejorar | El resto (entre 70% y 90%) | Mejorar título, fotos y precio; si no sube, probar pausar |

Si la campaña de esa publicación **viene mejorando** (ROAS +5% o más), todas agregan "darle unos días antes de decidir".

**D2. Vendiendo bien sin publicidad.** Publicaciones sin campaña activa con 10 o más unidades orgánicas en 30 días, conversión de 3% o más (si se conoce) y sin caída contra los 30 días previos. Se ordenan por ventas orgánicas. Datos que toma: unidades y ventas orgánicas, crecimiento, conversión, visitas, stock, categoría y marca, más las campañas de la misma categoría. La recomendación:

| Caso | Dice |
|---|---|
| No hay campaña en esa categoría | Crear una nueva con presupuesto chico y mirar una semana |
| La mejor campaña de la categoría (mayor ROAS) está en Revisar o Con oportunidad | Crear una campaña aparte, con presupuesto chico, para no mezclarla |
| La mejor campaña está bien | Sumarla a esa campaña, tomando su ROAS como referencia; si usa 95% o más de su presupuesto, sugiere subirlo |
| Stock menor a 10 unidades (se agrega a cualquiera de las anteriores) | Reponer antes de invertir |

### E. Tareas

Salen de lo anterior, sin datos nuevos:

- "Hoy": hasta 3 publicaciones de D1 (las de mayor faltante) y las recomendaciones urgentes.
- "Esta semana": el resto de las recomendaciones (menos las "buena noticia") y las publicaciones de D2.

### F. Seguimiento (antes y después de una acción)

Cuando la persona marca una recomendación como hecha, Lumo guarda la fecha y compara. Tipos de acción registrables: bajar o subir presupuesto, mejorar publicaciones, bajar o subir el ROAS objetivo, pausar y activar publicidad.

- **Si pasaron 3 días o más:** compara hasta 14 días antes contra hasta 14 días después, con datos reales. Mira ROAS, ventas, inversión y clics por día; para las acciones por campaña también el ROAS de toda la cuenta.
- **Si pasaron menos de 3:** dice "Muy pronto". Si la persona lo pide, muestra una **simulación** con factores fijos (por ejemplo, subir presupuesto = inversión ×1,3, clics ×1,25, ventas ×1,2). Son supuestos de Lumo, no resultados, y la pantalla lo marca como simulado.

Cuándo se considera que **mejoró / empeoró** (si no, "sin cambios claros"):

| Acción | Mejoró | Empeoró |
|---|---|---|
| Pausar | ROAS de la cuenta +2% o más | ROAS de la cuenta −3% o peor |
| Subir presupuesto | Ventas +8% o más | ROAS menor al 85% del objetivo **y** −5% o peor |
| Bajar presupuesto | ROAS +8% o más | ROAS −8% o peor |
| Bajar ROAS objetivo | Ventas +8% o más | ROAS −25% o peor |
| Subir ROAS objetivo | ROAS +8% o más | ROAS −8% o peor |
| Activar publicidad | Ventas +5% o más | ROAS menor al 85% del objetivo **y** −5% o peor |
| Mejorar publicaciones | ROAS +5% o más, o ventas +10% con ROAS no peor que −3% | ROAS −5% o peor |

### G. Avisos por email

Se envían desde `lumoads.ml@gmail.com` (o el remitente configurado) a quien activó cada interruptor en Alertas. Un chequeo diario a las 11:00 de Argentina los dispara. Solo funcionan si el servidor tiene configurado el envío (Brevo o SMTP); si no, el panel los muestra como "Próximamente".

| Aviso | Cuándo se envía | Datos y cuentas | Qué dice |
|---|---|---|---|
| **Resumen semanal** (m1) | Lunes (si falló, martes o miércoles), una vez por semana | Últimos 7 días contra los 7 anteriores: inversión, ventas por publicidad, ROAS, inversión por día, top 5 publicaciones por ventas (estimadas), campañas con ROAS menor al objetivo (hasta 3). Adjunta un Excel con campañas, publicaciones y días | Resumen y campañas "con oportunidad de mejora" |
| **Publicaciones que gastan y no venden** (m2) | Una vez por día si hay alguna nueva; no se repite por publicación en 7 días | Publicaciones con anuncios activos que en 30 días gastaron **$10.000 o más** y tuvieron **ventas por publicidad en cero** (estimadas con el reparto de la campaña) | Lista de hasta 10 con lo invertido |
| **Publicaciones que venden bien sin publicidad** (m3) | No se repite por publicación en 14 días | Mismo criterio que D2 | Lista de hasta 10 con las unidades vendidas |
| Avisos de suscripción | Cobro rechazado, acceso en pausa, fin de prueba gratis | Estado de la suscripción en Mercado Pago | No son recomendaciones de publicidad |

---

## 6. Todos los umbrales que puso Lumo (no vienen de Mercado Libre)

| Umbral | Valor | Dónde |
|---|---|---|
| Superando el objetivo | ROAS ≥ 120% del objetivo | Estado |
| En objetivo | 90% a 120% | Estado |
| Lejos del objetivo (Revisar) | menos de 70% | Estado, alertas |
| Mejora de tendencia | ROAS +5% | Estado "Mejorando", avisos de visibilidad |
| Visibilidad en caída / en alza | impresiones −10% / +10% | Recomendaciones de ROAS objetivo |
| ROAS en caída | −5% | "Gana visibilidad, pero cae su ROAS" |
| Ventas en caída (suma aviso) | −25% | Recomendación de revisar |
| Uso de presupuesto al tope | 95% | "Se queda sin presupuesto" |
| Bajar presupuesto | a la mitad (redondeo $500) | Recomendación urgente |
| Subir presupuesto | +30% (redondeo $500) | Recomendación de presupuesto |
| Venta orgánica fuerte | 10 unidades en 30 días y conversión 3% o más | Alertas, tareas, mail m3 |
| Stock bajo | menos de 10 unidades | Alertas |
| Categoría que crece | +10% y (cobertura menor a 70% o facturación en campañas menor a 30%) | Recomendación por categoría, Tendencias |
| "En alza" / "En baja" | ±10% | Tendencias |
| Gasto sin ventas | $10.000 en 30 días | Mail m2 |
| ROAS objetivo por defecto | $5 (ACOS 20%) | Campañas que no informan objetivo |
| Veredictos de Seguimiento | ver sección F | Seguimiento |
| Factores de simulación | ver sección F | Seguimiento |

---

## 7. Límites que afectan el valor de las recomendaciones

Para tener en cuenta al decidir qué mejorar:

1. **Las cifras por publicación son estimadas.** Mercado Libre informa la inversión y las ventas reales por publicación, pero solo en tramos de 30 días. Para otros períodos Lumo reparte el total de la campaña según ese peso. Las alertas de "pausar" y "mejorar" y el aviso m2 se apoyan en eso.
2. **No hay tamaño mínimo de muestra.** Una campaña con muy poca inversión puede quedar en Revisar, o mostrar una tendencia fuerte, por el ruido de pocos clics.
3. **No se conoce el margen.** El ROAS y el ROAS objetivo no dicen si el producto deja ganancia. Los consejos asumen que el objetivo configurado es el correcto.
4. **Los porcentajes de las acciones son fijos**: "a la mitad" y "+30%" no consideran el nivel de gasto ni la estacionalidad.
5. **Uso del presupuesto con el presupuesto de hoy**, aunque se haya cambiado dentro del período.
6. **La participación de impresiones y las pérdidas** son siempre de los últimos 30 días, aunque el período elegido sea otro.
7. **El mail semanal no usa el mismo criterio que el panel**: marca "oportunidad de mejora" a toda campaña con ROAS menor al objetivo, sin distinguir las que vienen mejorando ni mencionar visibilidad. Conviene alinearlo.
8. **Las publicaciones tipo "familia"** no traen stock, marca ni visitas, así que quedan fuera de conversión y de recomendaciones de stock.
9. **Hay datos útiles sin usar** (sección 4), en particular la participación en primeras posiciones y la referencia de ACOS de Mercado Libre.
10. **Las simulaciones de Seguimiento** son supuestos y deben leerse como tales.
