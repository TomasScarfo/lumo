# Lumo

## Logo

El logo de Lumo es el **amanecer**: un semicírculo blanco sobre una línea blanca, en un cuadrado azul `#2446D6` con esquinas redondeadas.

- Archivos: `backend/lumo/static/logo.svg` y `logo.png` (los que usa la app), y `design/logo/lumo-logo.svg` / `.png` (copia de `lumo-c-amanecer`).
- En el panel (`backend/lumo/panel.html`) y en el prototipo (`design/lumo-prototipo.html`) el ícono `#i-lumo` dibuja el mismo amanecer.
- El logo viejo con la **"L"** ya no se usa. No volver a ponerlo en ninguna pantalla, ícono, favicon ni documento.
- Cualquier pantalla nueva usa `/static/logo.svg` (y `<link rel="icon" href="/static/logo.svg">`).

## Tests

```bash
cd backend && python -m unittest discover -s tests
```
