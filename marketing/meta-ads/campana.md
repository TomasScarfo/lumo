# Campaña de lanzamiento en Meta Ads

Primer mes: **USD 150**, solo **Argentina**, cuenta nueva y sin usuarios todavía. Hay poco presupuesto, así que va todo en **una sola campaña con un solo conjunto de anuncios**, y Meta decide qué anuncio rinde más.

## Estructura

| Nivel | Configuración |
|---|---|
| **Campaña** | "Lumo · Lanzamiento". Objetivo: **Ventas**, con conversión en el sitio web. Presupuesto de campaña (Advantage) de **unos USD 5 por día**, en pesos según la cotización del día. Arranca **en pausa**. |
| **Conjunto** | Conversión: evento **`InitiateCheckout`** del Píxel (clic en "Probar gratis"). Ubicación: Argentina. Edad: 22 a 60. Público Advantage+ con estas sugerencias: Mercado Libre, comercio electrónico, emprendedores, Tienda Nube, ventas por internet. **Ubicaciones manuales:** Reels y Stories de Instagram y Facebook, porque los videos son verticales y el feed los recorta. |
| **Anuncios** | 6: los 3 videos en sus dos versiones (mujer y hombre). |

**Por qué `InitiateCheckout`:** con USD 5 por día y sin historial, Meta necesita un evento que pase seguido para aprender. Cuando haya unas 50 pruebas iniciadas por semana, pasamos a optimizar por `StartTrial`.

**Plan B:** si a los 4 días hay menos de 5 `InitiateCheckout`, cambiamos el objetivo a **Tráfico**, optimizando por visitas a la página de destino, para juntar datos más baratos.

## Enlace de cada anuncio

`https://lumoads.com.ar/?utm_source=meta&utm_medium=paid_social&utm_campaign=lanzamiento&utm_content=<video>-<versión>`

Por ejemplo: `utm_content=v1-mujer`.

## Textos

**Texto principal** (lo que se ve arriba del video):

- **V1 · Aviso:** "¿Tenés publicaciones que venden solas en Mercado Libre? Lumo te avisa cuáles conviene sumar a tu publicidad y cuáles gastan sin vender."
- **V2 · Ganancia:** "ROAS, ACOS, CTR… ¿y tu publicidad te deja ganancia? Lumo lee tus campañas de Mercado Libre y te dice qué hacer primero, en palabras simples."
- **V3 · Por cada $1:** "Por cada $1 que ponés en publicidad en Mercado Libre, ¿cuánto vuelve? Lumo te lo dice en una frase y te recomienda qué hacer con cada presupuesto."

**Título:** "Probalo gratis 14 días"
**Descripción:** "Tu asistente de publicidad en Mercado Libre."
**Botón:** "Registrarte"

## Reglas para que Meta no rechace los anuncios

- No usar el logo de Mercado Libre ni su amarillo. Nombrarlo solo como el lugar donde vende la persona.
- No prometer resultados ("vas a vender el doble"). Hablar de lo que Lumo hace: avisa, recomienda, explica.
- No apelar a datos personales de quien mira el anuncio. Por ejemplo, evitar "¿Estás perdiendo plata?", que da a entender que sabemos algo de esa persona.

## Seguimiento

| Cuándo | Qué se mira y qué se hace |
|---|---|
| Todos los días | Gasto, CTR, costo por clic y por `InitiateCheckout`. |
| Día 7 | Se pausan los 2 anuncios con peor costo por `InitiateCheckout`. |
| Día 14 | Comparar mujer contra hombre y video contra video. El presupuesto va a lo que gane. |
| Día 30 | Informe: pruebas iniciadas, costo por prueba, cuántas pasaron a pago. Decidir si se escala. |

Para que Meta mida sin depender del navegador, Lumo además manda desde el servidor los eventos `Lead`, `StartTrial` y `Subscribe` (ver `backend/lumo/meta.py`).
