# Rediseño visual de HUÁNUCO ECOGUARD AI

## Alcance

Cambios de presentación y lenguaje sobre la aplicación Gradio existente. Se conservan fotografía, cámara en vivo, captura manual, guardado, historial y totales. No se entrenó, publicó ni desplegó la aplicación. No se editó el dataset ni la arquitectura.

## Archivos modificados

- `scripts/app_gradio.py`: tema, composición de tarjetas, estados vacíos y textos de presentación. Los eventos y las llamadas al modelo y almacenamiento se conservan.
- `scripts/ecoguard_ui.css`: fondo oscuro, verdes, contraste, tarjetas, barras, botones, espaciado, foco visible y adaptación móvil. Pie de página simplificado.
- `scripts/camera_browser.js`: mensajes amigables y traducción de textos nativos visibles de carga y acceso a cámara. Se conservan el manejo de permisos y la liberación de la cámara.
- `scripts/check_ui_browser.cjs`: selectores actualizados a los nuevos textos y capturas de revisión. Cuenta también los fotogramas enviados por el transporte de streaming de Gradio.
- `tests/test_camera_ux.py` y `tests/test_app_real.py`: actualización de las expectativas de textos; se conservan las comprobaciones funcionales.

Se añadieron este documento y las capturas e informe de `docs/evidencias/ui-refinement/`.

## Cambios visuales y textos

- Encabezado: «Observa tu entorno y aprende a cuidarlo», con una explicación breve de agua, aire y suelo.
- Aviso: «Importante: Este resultado es una orientación visual. No reemplaza una evaluación técnica o ambiental».
- Pestañas: «Fotografía» y «Cámara».
- «Categoría predicha» pasa a «Resultado principal» y las puntuaciones se presentan como «Coincidencia visual», con sus valores originales.
- «Interpretación visual» pasa a «¿Por qué dio este resultado?».
- «Recomendaciones generales» pasa a «¿Qué podrías hacer en una situación así?».
- Se retiran de los avisos cotidianos referencias a MongoDB, Atlas, inferencia y tiempos del servidor. Los errores siguen comunicando si no se confirmó el guardado.
- «Vertimientos» se explica como «descargas de residuos en el agua» y las recomendaciones comienzan directamente con una acción.
- El historial se presenta como «Resultados guardados». Si la consulta funciona y no hay registros, muestra «Todavía no hay resultados guardados». Una conexión no disponible se comunica como tal, sin afirmar que el historial está vacío.
- El pie muestra únicamente el nombre del proyecto y una frase breve; se oculta el pie estándar de Gradio con enlaces técnicos.

## Fotografía

Dos pasos claros: elegir una imagen y consultar el resultado. La vista previa solo ocupa espacio después de cargar la fotografía. El estado inicial muestra una invitación breve; la explicación y las recomendaciones aparecen al existir un resultado. «Analizar imagen» destaca en verde y «Limpiar» reinicia los mismos campos que antes. Se mantiene el intento de guardado al analizar y se explica que el historial no incluye fotografías.

## Cámara

Tres instrucciones cortas para iniciar, dar permiso y grabar. Se conservan los controles de detener y guardar, la selección de dispositivo cuando está disponible y la alternativa de captura manual. La cámara sigue revisando escenas aproximadamente cada dos segundos y no guarda automáticamente sus resultados. La tarjeta de resultado usa las mismas barras y secciones que fotografía.

## Validación

- 10 pruebas de `test_camera_ux.py` aprobadas, incluyendo el modelo ONNX real con las 23 imágenes reservadas, contratos de cámara y eventos de Gradio.
- Ruff y comprobación de sintaxis JavaScript aprobados.
- Navegador Chromium: carga y análisis de fotografía en escritorio y móvil emulado; tres barras y ausencia de desbordamiento horizontal.
- Cámara simulada: inicio, resultados periódicos, detener y liberar las pistas de cámara.
- Vistas de cámara a 320, 390 y 768 píxeles; limpiar, estado vacío, textos de carga en español e historial sin guardado habilitado.
- Huellas SHA256 verificadas sin cambios para `best.pt`, `last.pt`, `best.onnx`, `best.json`, `inferencia.py`, `camera_analysis.py` y `mongo_store.py`.

Las pruebas de `test_app_real.py` requieren su entorno explícito de integración; aquí solo se actualizaron los textos esperados. No se verificó una conexión real a MongoDB ni se guardaron registros externos.

## Pendiente en móvil físico

Revisar Android y Safari de iPhone: permiso de cámara, selección de cámara posterior/frontal, orientación vertical/horizontal, selector de archivos y tamaño de controles con texto ampliado. La emulación de ancho y la cámara simulada no sustituyen esas comprobaciones.

## Evidencias

- `evidencias/ui-refinement/desktop-empty.png`
- `evidencias/ui-refinement/desktop.png`
- `evidencias/ui-refinement/phone-emulated-empty.png`
- `evidencias/ui-refinement/phone-emulated.png`
- `evidencias/ui-refinement/camera-synthetic.png`
- `evidencias/ui-refinement/camera-320.png`
- `evidencias/ui-refinement/camera-390.png`
- `evidencias/ui-refinement/camera-768.png`
- `evidencias/ui-refinement/history-unavailable.png`
- `evidencias/ui-refinement/browser-report.json`
