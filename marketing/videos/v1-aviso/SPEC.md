# SPEC · Video 1 "Te llegó un aviso"

GOAL:    una vendedora de Mercado Libre entiende que Lumo le avisa qué publicación conviene sumar a la publicidad y cuál gasta sin vender, y toca "Probalo gratis".
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps (Reels / Stories de Meta).
TIME:    22 s x 30 = 660 frames. Voz en off con tiempos APROXIMADOS (2,6 palabras/s) hasta tener la grabación real; música suave por debajo, a definir.

LOOK:
- Fondo: blanco #FFFFFF plano, sin textura. Superficies de interfaz #F2F5F8, bordes #DAE2E9.
- Tinta: #13202C (texto y trazo del personaje, 6 px). Texto secundario #44566A.
- Acento: azul Lumo #2446D6, solo en: el ícono de Lumo, la recomendación (palabra «Organizadores»), el cierre a pantalla llena.
- Bueno #146C43 / #D9F1E3 (sumar). Malo #B42318 / #FADFDB (solo la alerta del segundo aviso).
- Display: Bricolage Grotesque 800, 76-96 px, tracking -2%. Texto: Figtree 600/700, 34-44 px.
- Medio: ilustración vectorial plana de trazo negro de 6 px con rellenos planos, como el logo; sombras de interfaz 0 18px 40px rgba(19,32,44,.12). Nada de gradientes.

OBJECTS:
- Vendedora: cabeza redonda con rodete, flequillo, ojos de punto con brillo, cejas, boca por estados (sonrisa, "o" de sorpresa, preocupada, contenta); remera azul clara; brazo derecho sostiene el celular.
- Celular: 420 x 860, marco #13202C de 14 px, radio 64, pantalla de bloqueo con hora "10:24" y notificaciones con el ícono real de Lumo.
- Mail de Lumo: asunto real "Publicaciones que venden bien sin publicidad" y la línea con el formato de notify.py.
- Recomendación: el texto del panel "Sumala a «Organizadores», que hoy tiene ROAS $9,8".
- Frasco de monedas con una pérdida (segundo aviso): monedas amarillas #F2C230 con trazo.

MOTION:
- Llegadas: expo.out 0.5 s. Salidas: power3.in 0.25 s. Cámara: power2.inOut 0.6 s.
- Personaje: resortes back.out(1.6) en posición y escala (nunca en opacidad); cabeza adelanta 3 cuadros a los brazos; parpadeo de 3 cuadros en 2.1 s y 7.4 s.
- Títulos quietos al llegar. Subtítulos de 3 a 5 palabras, palabra activa en tinta y el resto en #44566A.

SHOTS:
- 0.0-4.6 · notif: frame 0 ya muestra a la vendedora con el celular y la notificación (miniatura). 0.3 vibra el celular; 0.7 ella gira la cabeza (sorpresa). 3.8-4.6 la cámara empuja hacia el celular y la pantalla se vuelve el mundo siguiente.
- 4.6-10.8 · mail: el mail de Lumo a pantalla llena. 5.4 se resalta la línea "Organizador de cajones: 24 unidades vendidas en 30 días sin publicidad". 6.6 la línea se transforma en la tarjeta de recomendación azul. 8.6 la tarjeta de la campaña "Organizadores" recibe la publicación (4 publicaciones) y se tilda "Hecho". 10.3 la cámara se aleja.
- 10.8-16.0 · alerta: la vendedora otra vez, ahora con un frasco de monedas que pierde. 11.3 llega el aviso rojo "Publicaciones que gastan y no venden" con "Mesa plegable: invirtió $18.400 en 30 días y no vendió nada". 13.6 el aviso tapa el agujero como un parche y deja de perder. Cara preocupada → aliviada.
- 16.0-22.0 · cierre: el azul inunda desde el aviso; el amanecer se dibuja (línea, después el sol sube); "Lumo"; "Avisos y recomendaciones para tu publicidad"; botón "Probalo gratis 14 días"; "Datos de ejemplo" chico abajo. Se mantiene 2.5 s.

BANNED: fondo oscuro con cosas flotando; brillos, partículas, gradientes; papel crema con serif; todo centrado y apareciendo a la vez; tarjetas de a tres; logo de Mercado Libre o su amarillo como marca; logo en una esquina; títulos que se siguen moviendo después de llegar; botones en forma de píldora.

QA: 0.0 (miniatura legible: celular + notificación + cara), 5.6 (línea resaltada legible), 7.4 (recomendación legible), 9.4 (Hecho), 12.4 (aviso rojo legible), 14.2 (frasco ya no pierde), 21.0 (cierre completo). Todo texto entre y=168 y y=1330; subtítulos en y≈1130-1290.
