# Video de demo: recorrido por la app

`../renders/lumo-demo-recorrido.mp4` (1280×720, ~1:40): presentación, recorrido por el panel real con una cuenta ficticia
(“Alma Deco Hogar”, deco y hogar) y cierre con lumoads.com.ar. Sirve para mostrar Lumo a posibles usuarios o en una demo.

Para volver a generarlo (después de cambiar el panel):

```bash
cd marketing/videos/demo
python3 datos.py datos.json   # cuenta ficticia: 5 campañas y 90 días de historia
node grabar.js                # graba con Playwright en raw/*.webm
ffmpeg -ss 0.4 -i raw/*.webm -c:v libx264 -crf 22 -pix_fmt yuv420p -movflags +faststart -r 30 ../renders/lumo-demo-recorrido.mp4
```

`serve.js` sirve `backend/lumo/panel.html` con esos datos, sin servidor. Los textos de cada paso están en `grabar.js`.
