# Lumo

## La idea

Lumo muestra **luz y claridad entre tantos números**. Todo lo que se diseñe o se escriba tiene que transmitir eso: pantallas despejadas, palabras simples, lo importante primero y un toque de luz (el logo que se enciende, el brillo cálido) en vez de ruido.

## Logo

El logo de Lumo es el **amanecer**: un semicírculo blanco sobre una línea blanca, en un cuadrado azul `#2446D6` con esquinas redondeadas.

- Archivos: `backend/lumo/static/logo.svg` y `logo.png` (los que usa la app), y `design/logo/lumo-logo.svg` / `.png` (copia de `lumo-c-amanecer`).
- En el panel (`backend/lumo/panel.html`) y en el prototipo (`design/lumo-prototipo.html`) el ícono `#i-lumo` dibuja el mismo amanecer.
- El logo viejo con la **"L"** ya no se usa. No volver a ponerlo en ninguna pantalla, ícono, favicon ni documento.
- Cualquier pantalla nueva usa `/static/logo.svg` (y `<link rel="icon" href="/static/logo.svg">`).

## Portada estática

- `site/` se genera con `cd backend && python build_site.py`. Regenerarla siempre que cambie `landing.html`, `site.css` o el logo; un test falla si quedó vieja.
- En `landing.html`, los enlaces a la app llevan el prefijo `{{ app }}` y el atributo `data-app`.

## Tests

```bash
cd backend && python -m unittest discover -s tests
```
