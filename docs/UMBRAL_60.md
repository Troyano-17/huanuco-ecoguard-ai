# Umbral mínimo de aceptación del 60 %

Implementado sobre el ONNX existente, sin entrenamiento, exportación, cambios de clases o modificación del dataset. No se publicó en Render.

## Regla y archivos

`scripts/inferencia.py` define `MIN_ACCEPTANCE_SCORE = 0.60` y `accepted_label(scores)`. La función obtiene la categoría con puntuación máxima y la acepta con comparación inclusiva `>=`; no modifica las tres puntuaciones. Un resultado no concluyente es un estado de aplicación, sin cuarta clase.

Archivos modificados o agregados:

- `scripts/inferencia.py`: constante, regla y textos comunes.
- `scripts/camera_analysis.py`: aplicar la regla por fotograma y bloquear instantáneas guardables rechazadas.
- `scripts/app_gradio.py`: fotografía, presentación, captura manual y cámara; habilitación del botón Guardar según el resultado actual.
- `scripts/ecoguard_ui.css`: mostrar la orientación en fotografías y ocultar el resultado anterior y las secciones de recomendaciones.
- `scripts/mongo_store.py`: comprobar la misma regla antes de conectar o insertar; verificar que la categoría guardada sea la máxima aceptada.
- `tests/test_acceptance_threshold.py`: nueve pruebas deterministas nuevas, con casos de frontera y transiciones.
- `scripts/evaluar_umbral.py`: evaluación reproducible del ONNX y SHA256.
- `README.md` y este documento: comportamiento y reproducción.
- `docs/evidencias/umbral-60/`: `evaluacion.json`, `pruebas-nuevas.txt` y `suite-completa.txt`.

Se mantienen el orden real `agua_contaminada`, `aire_contaminado`, `suelo_contaminado`, las 100 épocas y la exactitud histórica 21/23 (91.3043 %).

## Comportamiento

**Fotografía:** se conserva la carga, vista previa y controles. Una categoría aceptada muestra puntuaciones originales, interpretación y recomendaciones generales con el aviso de orientación visual. El guardado automático existente solo se intenta para resultados aceptados. Una fotografía rechazada elimina la categoría y recomendaciones anteriores y presenta exactamente:

> No pudimos identificar la escena con suficiente claridad
>
> Intenta mostrar mejor el agua, el aire o el suelo que deseas analizar. Puedes acercar la cámara, mejorar la iluminación o elegir otra fotografía.

No se muestran barras ni categorías en ese estado. Se puede volver a analizar; Limpiar elimina archivo, vista previa y resultados.

**Cámara en vivo y captura manual:** se usa la misma regla. Un resultado rechazado reemplaza el resultado previo, conserva las puntuaciones originales internamente y deja `label=None`. No se proporciona una instantánea guardable y se deshabilita Guardar resultado. La siguiente escena aceptada vuelve a habilitarlo. Reiniciar el análisis borra el resultado previo. Se conservan el intervalo de 2 segundos, bloqueo compartido del motor, descarte de fotogramas ocupados o de generaciones anteriores, selector de cámara, parada y captura manual. No se agrega confirmación por varios fotogramas. Cada usuario mantiene su propio `CameraSession`; los estados no se comparten.

**MongoDB:** el esquema y las consultas de historial se conservan. Se guardan únicamente categoría aceptada, puntuaciones originales, versión, identificadores y fecha; ninguna fotografía. La cámara requiere guardado explícito. La validación previa a insertar impide guardar una puntuación rechazada incluso si se invoca directamente el almacén. El historial histórico permanece intacto; no se borran ni recalifican registros anteriores.

## Evaluación real

Ejecutada con `models/best.onnx` y las 23 imágenes de `artifacts/test-original`. Es un análisis **exploratorio posterior al entrenamiento sobre el mismo test original**, no una evaluación independiente. El umbral cambia la aceptación en la aplicación; no mejora el modelo ni calibra sus puntuaciones.

| Categoría real | Fotografías | Aceptadas | No concluyentes | Aciertos aceptados | Errores aceptados | Cobertura | Exactitud entre aceptadas |
|---|---:|---:|---:|---:|---:|---:|---:|
| agua_contaminada | 6 | 6 | 0 | 4 | 2 | 100 % | 66.6667 % |
| aire_contaminado | 10 | 10 | 0 | 10 | 0 | 100 % | 100 % |
| suelo_contaminado | 7 | 7 | 0 | 7 | 0 | 100 % | 100 % |
| **Total** | **23** | **23** | **0** | **21** | **2** | **100 %** | **91.3043 %** |

Exactitud histórica original: **21/23 = 91.3043 %**. Exactitud observada entre aceptadas: **21/23 = 91.3043 %**. Cobertura: **23/23 = 100 %**. Errores evitados por el umbral en este conjunto: **0**.

Predicciones equivocadas que siguen superando el 60 %:

| Fotografía | Categoría real | Predicción aceptada | Puntuación máxima original |
|---|---|---|---:|
| agua_contaminada/ECO-088.png | agua_contaminada | suelo_contaminado | 0.8920842409133911 (89.2084 %) |
| agua_contaminada/ECO-112.png | agua_contaminada | suelo_contaminado | 0.6852061152458191 (68.5206 %) |

`evaluacion.json` contiene las tres puntuaciones sin redondear para cada imagen. No se encontró una muestra local identificada y validada de fotografías limpias o ajenas a las tres clases; las fotografías disponibles están organizadas como contaminación y las otras imágenes son capturas de interfaz. No se afirma una tasa de rechazo para escenas limpias o no relacionadas. Una puntuación alta puede ser incorrecta.

## Validación y límites

- Nuevas pruebas: **9 ejecutadas, 9 correctas**. Cubren 0.59, 0.5999, 0.60, 0.6001, 0.75 y 0.95; tres categorías; puntuaciones intactas; limpieza, alternancia aceptado/no concluyente, sesiones aisladas y prevención de guardado en UI y almacén.
- Suite completa: **77 descubiertas, 72 ejecutadas correctamente y 5 omitidas**, sin fallos. Las omitidas son cuatro pruebas opcionales del checkpoint PyTorch original y una de MongoDB Atlas real. Los contratos del protocolo de entrenamiento usan fixtures, sin entrenar el modelo.
- ONNX real: inferencia directa sobre las 23 fotografías y, en la suite existente, procesamiento de esas imágenes mediante `CameraAnalyzer`. Las pruebas también ejecutan callbacks y preprocesamiento Gradio reales para fotografía/cámara, configuración de eventos, intervalo, protección de concurrencia y estado.
- MongoDB: contratos con dobles y codificación BSON real local; no se ejecutó una escritura en Atlas.
- No se ejecutaron pruebas en navegador ni con cámara física durante este cambio. La presentación se revisó en código y callbacks; la visualización CSS en navegador y los permisos/dispositivos quedan pendientes. No se certifican teléfonos físicos.
- Gradio emite advertencias `ResourceWarning` de bucles asyncio sin cerrar al construir aplicaciones de prueba; no causaron fallos.

Comandos ejecutados (desde la raíz):

```bash
MPLCONFIGDIR=/tmp/ecoguard-mpl GRADIO_ANALYTICS_ENABLED=False .venv-auditoria/bin/python -m unittest discover -s tests -p test_acceptance_threshold.py -v
MPLCONFIGDIR=/tmp/ecoguard-mpl GRADIO_ANALYTICS_ENABLED=False .venv-auditoria/bin/python -m unittest discover -s tests -v
.venv-auditoria/bin/python scripts/evaluar_umbral.py
sha256sum entrega/original/train100/weights/best.pt entrega/original/train100/weights/last.pt models/best.onnx models/best.json
```

Para ejecutar la aplicación:

```bash
cd /home/troyano/proyectos/huanuco-ecoguard-ai
MODEL_PATH=models/best.onnx PORT=7860 GRADIO_ANALYTICS_ENABLED=False MPLCONFIGDIR=/tmp/ecoguard-mpl .venv-auditoria/bin/python scripts/servidor.py
```

Abrir `http://localhost:7860`. La configuración existente de MongoDB sigue utilizando `MONGODB_URI` y `MONGODB_DB`; no se carga `.env` automáticamente.

## Integridad SHA256

Verificados antes y después de implementar. Los cuatro archivos permanecen idénticos. El script de evaluación compara además estos hashes esperados y comprueba la integridad antes/después de inferir.

| Archivo protegido | SHA256 inicial = final |
|---|---|
| entrega/original/train100/weights/best.pt | `57b2194e8cfb26de44eb93960193392965e4c46be3c75f8f22c81b5a37b7ed32` |
| entrega/original/train100/weights/last.pt | `005ecb8bd05c6f2bfba95d3deccdc2f9c112840fea398aae07807d15c8e8d72f` |
| models/best.onnx | `b90eb5240038be75cea6b1477ef23665882abad69c126c7257a5578722812eef` |
| models/best.json | `b24374fea80eb90015ae53ceca2673188104fc46b1acd506911c1f7273d5b178` |
