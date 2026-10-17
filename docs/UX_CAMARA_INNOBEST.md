# Entrega UX/UI y cámara — 16 de octubre de 2026

Implementación sobre el proyecto existente, sin entrenar, alterar dataset, cambiar clases ni publicar. Modelos y manifiesto conservados byte a byte; hashes comprobados por `test_models_unchanged`.

## Archivos

- `scripts/app_gradio.py`: dos pestañas; resultado destacado, barras accesibles, recomendaciones y estado sin textareas; webcam nativa Gradio 5.49.1; alternativa manual; guardado explícito de cámara; historial y estadísticas conservados.
- `scripts/camera_analysis.py`: sesiones aisladas, límite de frecuencia, copia de inferencia de hasta 960 × 960, bloqueo compartido del motor y descarte de fotogramas ocupados; invalidación de resultados en curso al detener/reiniciar. No conserva imágenes en el estado.
- `scripts/ecoguard_ui.css`: estilos solo sobre identificadores/clases propios, sin reglas globales, estilos por posición ni `!important`.
- `scripts/camera_browser.js`: mensajes de permisos/dispositivos/contexto inseguro, interrupciones de tracks y liberación al abandonar la página. El botón Detener en `app_gradio.py` cierra el control nativo y los tracks.
- `scripts/benchmark_camera.py`: medición local reproducible.
- `scripts/check_ui_browser.cjs`: comprobación de escritorio, teléfono emulado y cámara sintética; requiere Playwright de desarrollo.
- `tests/test_camera_ux.py`: 10 pruebas nuevas, incluidas inferencias reales, callbacks Gradio y hashes.
- `tests/test_app_real.py`: contrato visual del test opcional del original actualizado de tabla a tres barras.
- `ecoguard.py`: incluye módulos y estilos nuevos al preparar paquetes o la demo histórica. No se ejecutó ninguna acción remota ni empaquetado.
- `README.md`, este informe y `docs/evidencias/ux-camera/`: instrucciones y evidencia vigente.

## Aspecto y uso

Cabecera pizarra oscura, texto claro y acento verde. Aviso ambiental de alto contraste bajo la cabecera. Pestañas **Analizar fotografía** y **Cámara en vivo**. En escritorio, entrada y resultado se distribuyen en columnas; en anchos pequeños, las columnas de Gradio se apilan. Los resultados usan tres barras con valor numérico y rol accesible `meter`, interpretación y orientación general. El historial comparte el lenguaje visual del tema y queda en un acordeón.

Esta es una **descripción de la interfaz implementada**, no una aprobación visual ni una captura del navegador. El navegador no arrancó en este entorno; revisión visual, contraste renderizado, teclado y ancho efectivo están pendientes.

Para fotografías: cargar, revisar vista previa, pulsar Analizar fotografía, revisar categoría/barras/orientación/estado y Reiniciar. Confirmar el análisis guarda metadatos si Atlas está configurado; la carga sola no guarda un registro.

Para cámara: **Iniciar análisis → permitir cámara → Grabar / Record en la vista previa**. La frecuencia solicitada es un fotograma cada 2 segundos. El control nativo también permite parar; **Detener análisis y cámara** invalida inferencias en curso y libera tracks. El último resultado válido queda disponible para **Guardar resultado actual (sin imagen)**. Iniciar otra sesión limpia ese resultado. El streaming nativo tiene un límite de evento de 300 segundos; tras cerrarse, vuelve a iniciar/grabar si deseas continuar.

Captura manual: detener el modo periódico, abrir el acordeón correspondiente, permitir cámara, pulsar el icono de captura y Analizar captura. Comparte el panel de resultados y el guardado explícito.

Se solicita `facingMode: ideal environment`, vista de 960 × 720 ideal y sin espejo. El selector nativo puede mostrar dispositivos disponibles; no se afirma que Android/iOS o el cambio frontal/posterior funcionen hasta probarlos.

## API exacta verificada localmente

Instalación: **Gradio 5.49.1**, Python 3.12.3 sobre WSL2. Se inspeccionaron firmas y código instalado de `Image`, `Image.stream`, `WebcamOptions`, `Webcam.svelte` y `stream_utils.ts`.

`Image(sources=['webcam'], type='pil', streaming=True, webcam_options=WebcamOptions(...))` y `.stream(..., stream_every=2, trigger_mode='once', concurrency_limit=None, time_limit=300)` existen en esa versión. `Image` no tiene eventos Python `start_recording`/`stop_recording`: se utilizan el control nativo y botones de sesión propios. Los frames no esperan detrás del motor: la callback de streaming puede despacharse sin límite de concurrencia de cola y el bloqueo del motor descarta inmediatamente las entradas ocupadas. `trigger_mode='once'` impide solicitudes solapadas de la misma sesión en la interfaz. Fotografía/captura manual mantienen concurrencia de cola de uno; cola total limitada a cuatro. ONNX mantiene un hilo de inferencia y su bloqueo interno.

La vista previa se conserva aparte de la copia reducida de procesamiento. ONNX sigue utilizando su transformación validada a 224 × 224. La reducción previa de cámara forma parte de esta modalidad; no es una nueva afirmación de equivalencia con el original para todas las resoluciones.

## Pruebas y rendimiento

[Suite ejecutada](evidencias/ux-camera/suite-tests.txt): **68 pruebas, 63 correctas, 5 omitidas**. Se ejecutaron las 10 nuevas, incluido ONNX real sobre las 23 imágenes reservadas y actualizaciones de cámara usando esas imágenes. Se probaron inicio/detención, resultado en curso descartado al detener, entradas nulas, liberación del bloqueo tras errores, aislamiento, reducción de imagen, límite de frecuencia, descarte con motor ocupado, ausencia de guardado automático, guardado explícito con doble técnico, historial/estadísticas y privacidad BSON con dobles, reset e integridad de cuatro artefactos.

Las cinco omitidas son cuatro pruebas opcionales con checkpoint original y HTTP y una integración Atlas; no se declaran aprobadas. No se importaron PyTorch ni Ultralytics en el proceso de medición de producción.

[Medición WSL](evidencias/ux-camera/benchmark.json): 69 fotogramas (23 imágenes × 3), proceso con FastAPI + Gradio + un clasificador ONNX. RAM RSS cargada: **186,84 MiB**; tras inferencias: **198,68 MiB**; pico: **216,20 MiB**. `predict` (preprocesamiento del clasificador + ONNX): media **6,45 ms**, mediana **6,35 ms**, p95 **7,80 ms**. Fotograma completo desde PIL, con copia y reducción: media **17,46 ms**, p95 **41,04 ms**. No incluye apertura/decodificación inicial del archivo, red, navegador, cola, MongoDB ni servidor HTTP activo. No mide FPS de cámara ni rendimiento real de Render.

Bloqueos documentados: Uvicorn no pudo abrir el puerto 7860 dentro del sandbox; la prueba HTTP/ASGI también se bloqueó al esperar trabajo de AnyIO entre hilos. Chromium/Playwright no arrancó por falta de `libnspr4.so`; [intento registrado](evidencias/ux-camera/browser-attempt.txt). No se generaron capturas falsas. La inferencia y callbacks reales sí se ejecutaron; el streaming extremo a extremo y la liberación física de cámara permanecen pendientes.

## Lista de aceptación pendiente

- Escritorio Chrome/Firefox: ejecutar `check_ui_browser.cjs` con servidor accesible; revisar capturas, barras, ausencia de desbordamiento, errores de consola, teclado y foco.
- Cámara física: permitir, rechazar y revocar permiso; cámara ausente/ocupada; desconectar; iniciar, parar y reiniciar; comprobar luz apagada y tracks liberados; detener durante una inferencia.
- Chrome Android y Safari iOS sobre HTTPS: permisos, vista previa, captura manual, intervalo periódico, orientación y cambio de cámara frontal/posterior. Teléfono emulado no sustituye esas pruebas.
- Verificar que guardar cámara genera exactamente un documento sin imagen, que cada análisis de foto confirmado genera uno y que los fotogramas periódicos no generan documentos.
- Render Free: medir arranque, RAM bajo carga, latencia de red y comportamiento con varias sesiones, suspensión y reactivación. Si el streaming no es estable, usar captura manual y documentar su rendimiento.

## MongoDB y Render

MongoDB **no configurado** en este proceso. No se contactó Atlas ni se realizaron escrituras externas. La interfaz informa que el análisis no fue almacenado. Se conserva el esquema sin imágenes, IP ni nombre de archivo, el historial compartido limitado a 100 y las estadísticas existentes. Gradio utiliza archivos temporales, con limpieza periódica configurada cada 60 segundos para archivos de más de 120 segundos; no se promete eliminación inmediata ni que no haya escrituras temporales.

Render conserva CPU ONNX, dependencias de producción sin PyTorch/Ultralytics, un worker, comprobación de integridad y `autoDeploy: false`. Código preparado para evaluación; **sin publicación y sin aceptación final de Render Free**. La cámara requiere HTTPS (o localhost); una IP LAN por HTTP normalmente no basta. El HTTPS real de Render y móviles no se probaron.

## Comando exacto

```bash
cd /home/troyano/proyectos/huanuco-ecoguard-ai
MODEL_PATH=models/best.onnx PORT=7860 GRADIO_ANALYTICS_ENABLED=False \
MPLCONFIGDIR=/tmp/ecoguard-mpl .venv-auditoria/bin/python scripts/servidor.py
```

Abrir `http://localhost:7860` desde el equipo WSL fuera de la restricción de puertos del agente. No hacen falta nuevos pesos, entrenamiento ni acciones remotas.
