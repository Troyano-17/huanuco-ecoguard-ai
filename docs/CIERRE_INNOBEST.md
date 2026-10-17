# Cierre INNOBEST — comprobación posterior a la recuperación, 16/10/2026

**Recuperación resuelta. Cierre funcional pendiente por dependencias de inferencia no disponibles en este entorno y credenciales Atlas ausentes. No se entrenó, no se publicó en Render y no se enviaron secretos a GitHub.**

Este informe reemplaza el diagnóstico anterior de recuperación. No se consultó Colab ni Drive. El directorio `.git` continúa sin metadatos utilizables; no se realizaron commits ni publicaciones.

## Integridad comprobada

`python3 ecoguard.py verificar` terminó con código 0: **83 archivos del manifiesto correctos** y respaldo del dataset con SHA256 correcto. Una segunda comprobación comparó **los 30 archivos originales extraídos** byte a byte mediante SHA256 con el ZIP original, antes y después de los intentos de inferencia/exportación. No se modificaron archivos de entrenamiento.

- ZIP original: SHA256 `ac10f88a010ef3fd0a7480cd984482496c77aa486e2548ff740c6da2fbf6f284`.
- `entrega/original/train100/weights/best.pt`: 3.195.010 bytes; SHA256 `57b2194e8cfb26de44eb93960193392965e4c46be3c75f8f22c81b5a37b7ed32`.
- `entrega/original/train100/weights/last.pt`: 3.195.010 bytes; SHA256 `005ecb8bd05c6f2bfba95d3deccdc2f9c112840fea398aae07807d15c8e8d72f`.
- Verificados también checkpoints intermedios, estados, `results.csv`, argumentos, gráficas, métricas, particiones y predicciones originales. Inventario completo con tamaños y hashes: [verificacion.json](evidencias/posrecuperacion/verificacion.json).
- Historial: 100 épocas consecutivas; particiones originales train=105, val=23, test=23, sin cruce de grupos ni píxeles. Las predicciones conservadas reconstruyen 21/23 aciertos (91,3043 %). **Es el resultado original, no una nueva evaluación CPU.**
- Se localizaron las **23 fotografías reales del test reservado**, verificando el hash de píxeles RGB y dimensiones contra `particiones.csv`: aire=10, agua=6, suelo=7. Copias para validación en `artifacts/test-original/<clase>/`, sin cambiar las particiones ni generar imágenes. No se evaluó una fotografía externa nueva.

## Entorno y resultados exactos

Se reutilizó el entorno virtual aislado `.venv-auditoria` (Python 3.12.3). `pip install -r requirements-export.txt` terminó con **código 1**: falló la resolución de nombres de los índices PyPI/PyTorch. La caché fue inspeccionada: no contiene Gradio, ONNX, ONNX Runtime ni Ultralytics 8.4.178. No se sustituyó el modelo ni se usó otro motor.

Desde la caché se instalaron Pillow 11.3.0, NumPy 2.2.6, PyMongo 4.18.1, dnspython 2.8.0 y requests con sus dependencias. **PyMongo 4.18.1 solo se usó para el códec BSON de auditoría; producción mantiene 4.15.3 y todavía no se ha instalado ni verificado.** `pip check` terminó con código 0; esto solo verifica el conjunto instalado, que está incompleto para ejecutar la aplicación. [Inventario](evidencias/posrecuperacion/dependencias-instaladas.txt), [instalación de red](evidencias/posrecuperacion/instalacion-red.txt), [instalación local](evidencias/posrecuperacion/instalacion-local.txt).

| Comprobación ejecutada | Resultado |
| --- | --- |
| Suite local, sin habilitar integraciones externas | 58 pruebas: 53 correctas, 5 omitidas; código 0; 1,943 s |
| Suite con `ECOGUARD_REAL_TESTS=1` y fotografía original | 54 pruebas contabilizadas: 53 correctas, Atlas omitida; además 1 error en `setUpClass` por ausencia de `torch`; código 1; 2,043 s |
| Compilación `python3 -m compileall -q scripts tests ecoguard.py` | Código 0 |
| Inferencia CPU con `Classifier(best.pt)` y ECO-005 | Código 1: `ModuleNotFoundError: torch`; no produjo predicción |
| Exportación ONNX usando las 23 fotografías verificadas | Código 1: falta `torch`; no se generó ni aprobó ONNX |
| Arranque Gradio con el `best.pt` original | Código 1: falta `gradio`; no abrió servicio HTTP |
| Verificador obligatorio del build Render | Código 1: falta `models/best.json`; tampoco existe `models/best.onnx` |

Las cinco integraciones anteriormente pendientes eran cuatro métodos de `RealApplicationTests` y uno de Atlas. Las cuatro primeras se habilitaron, pero **ninguna llegó a ejecutarse**: la preparación común se detuvo al importar PyTorch. Son carga/mapeo, inferencia de imagen válida, rechazo de archivo inválido y Gradio HTTP/API/reinicio. Atlas se mantuvo deliberadamente omitida, sin credenciales. No se presentan estos intentos como pruebas aprobadas. [Suite local](evidencias/posrecuperacion/pruebas-locales.txt), [intento de integraciones](evidencias/posrecuperacion/pruebas-integraciones.txt).

La primera suite detectó una prueba de pesos ajenos que seleccionaba el ZIP real recién recuperado en lugar de su ZIP sintético. Se aisló `ORIGINAL_ARCHIVE` dentro de esa prueba; no se cambió la verificación de procedencia del modelo. Se añadieron tres pruebas locales de esquema MongoDB.

## MongoDB local

Pasaron las tres nuevas pruebas: campos y tipos del documento, UUID e identificadores iguales, fecha UTC, ausencia de fotografía/nombre/IP; rechazo de categoría, clases, versión vacía y puntuaciones inválidas antes de conectar; codificación/decodificación **BSON real**, incluidas fechas con precisión de milisegundos. También pasaron los contratos existentes de escritura confirmada, historial ordenado/limitado, agregación y mensajes seguros.

Las operaciones de colección se verificaron mediante dobles; **no se ejecutó un servidor MongoDB local ni un validador del lado del servidor**. El esquema es validado por la aplicación. Conexión, permisos, índice e inserción/consulta reales en Atlas siguen pendientes de credenciales. No se configuraron ni imprimieron URI secretos.

## Render: correspondencia y recursos

El código corresponde a la configuración declarada: `requirements-production.txt` usa Gradio 5.49.1, Pillow 11.3.0, NumPy 2.2.6, ONNX Runtime 1.22.1, PyMongo 4.15.3, Uvicorn 0.37.0 y FastAPI 0.118.0. No incluye PyTorch, Ultralytics ni CUDA. El entorno de exportación sí necesita PyTorch 2.8.0+cpu, torchvision 0.23.0+cpu, Ultralytics 8.4.178 y ONNX 1.19.0.

`render.yaml`: Python 3.11.13, `plan: free`, `autoDeploy: false`, build `pip install -r requirements-production.txt && python scripts/verificar_modelo_render.py`, inicio `python scripts/servidor.py`. El servidor usa `PORT`, `0.0.0.0`, un worker y carga el modelo antes de servir `/healthz`. `/readyz` comprueba MongoDB y devuelve 503 si no está disponible. Esto se revisó en código; no se comprobó por HTTP.

**El paquete para Render aún no está completo:** necesita `models/best.onnx` y `models/best.json` procedentes de una exportación aprobada. El build actual falla ante su ausencia. La comparación exige al menos 23 fotografías, la misma categoría en todas y error absoluto máximo de puntuación ≤0,0001. No se cambió el motor activo ni se fabricó un manifiesto.

Se mantienen inferencia serial, cola de cuatro, un hilo ONNX/BLAS y pool MongoDB de tres conexiones. No hay dependencias de entrenamiento en producción. El plan Free ofrece 512 MB y 0,1 CPU ([planes oficiales](https://render.com/docs/compute-plans), revisados en esta comprobación). Usa disco efímero y se suspende tras 15 minutos sin tráfico ([limitaciones oficiales](https://render.com/docs/free)). **No se midió RAM, latencia ni concurrencia reales: no se puede certificar que quepa en Free.** En particular debe medirse una fotografía cercana al límite de 20 megapíxeles junto con la vista previa, las copias RGB y el resto del proceso. No se aumentó el plan ni se solicitó gasto.

## Comandos locales y requisitos para continuar

En un entorno con acceso a los índices, instalar las versiones declaradas sin tocar los originales:

```bash
.venv-auditoria/bin/python -m pip install -r requirements-export.txt
ECOGUARD_REAL_TESTS=1 \
ECOGUARD_SAMPLE=revision_ecoguard/revision/aire_contaminado/ECO-005.png \
.venv-auditoria/bin/python -m unittest discover -s tests -v
```

Inicio local con el **checkpoint original**, sin requerir Atlas para clasificar:

```bash
MODEL_PATH=entrega/original/train100/weights/best.pt \
PORT=7860 GRADIO_ANALYTICS_ENABLED=False \
.venv-auditoria/bin/python scripts/servidor.py
```

Abrir `http://127.0.0.1:7860`. **Este comando está bloqueado hoy por las dependencias ausentes.** Sin URI el resultado debe indicar que no se guardó; `/readyz` debe devolver 503.

Después de instalar las dependencias y aprobar las integraciones originales:

```bash
.venv-auditoria/bin/python scripts/exportar_onnx.py --imagenes artifacts/test-original
.venv-auditoria/bin/python scripts/verificar_modelo_render.py
MODEL_PATH=models/best.onnx PORT=7860 \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 GRADIO_ANALYTICS_ENABLED=False \
/usr/bin/time -v .venv-auditoria/bin/python scripts/servidor.py
```

Comprobar HTTP, inferencia mediante API, memoria durante imágenes reales y grandes, y funcionamiento desde navegador. La prueba no debe confundirse con el uso completo bajo la cuota CPU de Render. Repetir instalación y aceptación en **Python 3.11.13 con solo dependencias de producción**, porque esta auditoría usó Python 3.12.3.

Producción requiere: ONNX y manifiesto aprobados, las siete dependencias fijadas, variables `MODEL_PATH`, `PORT`, `MONGODB_DB` y URI Atlas como secreto externo, permisos de lectura/escritura y acceso de red restringido apropiados. Solo después de disponer de credenciales se habilitará `ECOGUARD_ATLAS_REAL_TESTS=1` con `MODEL_PATH` y `ECOGUARD_SAMPLE`. No se publicará nada sin autorización.

## Bloqueos restantes

1. Acceso a los índices de paquetes o wheelhouse completo y compatible para instalar las dependencias exactas. Bloquea inferencia CPU, cuatro integraciones, ONNX, Gradio y medición de recursos.
2. Credenciales y acceso de red Atlas. Bloquean únicamente la aceptación real de persistencia, que queda pendiente según lo solicitado.
3. Exportación/paridad y mediciones aprobadas antes de considerar preparado Render; hoy faltan los dos artefactos derivados y la instalación de producción comprobada.

Las pruebas históricas de Colab y los paquetes `dist/` se conservan sin modificarlos. El paquete generado durante la recuperación no incorpora automáticamente este informe actualizado. No hay despliegue ni URL pública verificada.
