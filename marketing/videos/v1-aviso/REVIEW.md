# REVIEW · Video 1 "Te llegó un aviso" (primer armado, sin voz)

**Decisiones.** El personaje es una vendedora de trazo simple, con el estilo plano del logo. El mail de la segunda escena aparece desde la pantalla del celular, como si la cámara entrara en ella. En la tercera, el aviso rojo se convierte en un parche que tapa el agujero del frasco. El cierre se abre en azul desde ese parche y dibuja el amanecer: primero la línea, después el sol. Los textos de Lumo son los reales: el asunto de `notify.py` y la recomendación del panel. Los números son de ejemplo y lo dice en pantalla.

**Qué medí.** `check` pasa sin errores. Hice los snapshots del armado completo (`--review`) y de los momentos que corregí. Arreglé dos cosas: dos subtítulos superpuestos en el segundo 2 y el torso de la vendedora, que estaba cortado.

**Voz y música (tercera pasada).**
- **Voz:** `assets/voice/voz.wav`, generada por la persona (24,7 s). Entra a los 0,3 s. Los subtítulos salen de la transcripción de Whisper (`assets/voice/transcript.json`) con el texto corregido por el guion: "sumalo", "Probalo", "Y si". Las escenas se retimaron a la voz y el video ahora dura 26,5 s.
- **Música:** `assets/bgm/musica.mp3`, del catálogo de HeyGen ("light playful ukulele"). Entra desde el segundo 9 del tema, donde arranca la parte principal, al 13 % de volumen, con fundido de entrada de 0,3 s y de salida de 1,5 s. **La medí, no la escuché:** puede que haya que cambiar el tema.
- **Niveles:** la voz está en -18,5 LUFS con pico de -1,5 dBTP. No la subí a -16 porque se pasaría del pico permitido. Meta normaliza el volumen de los Reels igual.

**Avisos que dejé a propósito.**
- `content_overlap` en 13,9 s: es el aviso mientras se encoge para convertirse en parche, dura 0,4 s.
- `canvas_overflow`: es el aviso entrando desde arriba de la pantalla.

**Ajustes de la segunda pasada.**
- **Escena 2 a 3:** ahora el mail vuelve a entrar en el celular de la vendedora, que ya está detrás. Ella lo guarda y aparece el frasco. Antes había un cuadro en blanco en el corte.
- **Monedas:** ya no se ven antes de empezar a caer.
- **Aviso rojo:** entra desde fuera de la pantalla, sin asomarse antes de tiempo.

**La toma más débil.** El cierre: el subtítulo repite el texto que ya está en pantalla ("…para tu publicidad"). Con la voz real, se pueden ocultar los subtítulos en el cierre si molesta.
