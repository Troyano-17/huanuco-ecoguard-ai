# HUÁNUCO ECOGUARD AI

Aplicación académica para clasificar escenas en **agua_contaminada**, **aire_contaminado** y **suelo_contaminado**. Incluye cuentas privadas, carga de fotografías, cámara periódica, captura manual, recomendaciones, historial y estadísticas por usuario. No localiza objetos ni mide científicamente la contaminación; sus puntuaciones no están calibradas como probabilidades científicas. Solo presenta y permite guardar una categoría si la mayor puntuación alcanza el 60 % (inclusive). En otro caso muestra orientación para intentar nuevamente, sin categoría ni recomendaciones específicas.

La regla única está en `scripts/inferencia.py`: `MIN_ACCEPTANCE_SCORE = 0.60` y `accepted_label`. Se aplica a fotografía, cámara en vivo, captura manual, presentación y guardado MongoDB, sin alterar las puntuaciones. Consulta [la evaluación del umbral](docs/UMBRAL_60.md) y reproduce la inferencia real con `.venv-auditoria/bin/python scripts/evaluar_umbral.py`.

Producción usa **ONNX Runtime CPU**, sin importar PyTorch ni Ultralytics. Se conservan intactos `best.pt`, `last.pt`, `models/best.onnx` y `models/best.json`. La comparación aprobada con el original está en el manifiesto; no se necesita exportar ni entrenar otra vez.

Consulta la [entrega UX y cámara](docs/UX_CAMARA_INNOBEST.md) para resultados medidos, archivos modificados y pruebas pendientes. Los informes anteriores describen estados históricos.

## Inicio en este repositorio (WSL)

```bash
cd /home/troyano/proyectos/huanuco-ecoguard-ai
export MONGODB_URI='mongodb+srv://USUARIO:CONTRASEÑA@CLUSTER/?retryWrites=true&w=majority'
export SESSION_SECRET="$(openssl rand -hex 32)"
MODEL_PATH=models/best.onnx MONGODB_DB=ecoguard PORT=7860 GRADIO_ANALYTICS_ENABLED=False \
MPLCONFIGDIR=/tmp/ecoguard-mpl .venv-auditoria/bin/python scripts/servidor.py
```

Abre **http://localhost:7860**. Para un entorno nuevo, instala `requirements-production.txt` en un virtualenv de Python 3.11 y usa su ejecutable en el mismo comando. No uses las dependencias de entrenamiento para producción.

`/healthz` comprueba el proceso y el modelo sin revelar secretos. `/readyz` devuelve 503 si MongoDB no está disponible. Sin MongoDB no se admite iniciar sesión, crear una cuenta ni confirmar escrituras.

Las contraseñas usan Argon2id. El navegador conserva únicamente un identificador de sesión aleatorio en una cookie HttpOnly, SameSite=Lax y Secure cuando la solicitud llega por HTTPS. La sesión persistida en MongoDB caduca a las 12 horas y el cierre la revoca. Cinco fallos de acceso dentro de 15 minutos bloquean temporalmente nuevos intentos para esa cuenta. Consulta [la guía de autenticación y despliegue](docs/AUTENTICACION_RENDER.md).

## Fotografías y cámara

- **Analizar fotografía**: carga JPG, PNG o WEBP, revisa la vista previa y pulsa Analizar. Se guardan categoría y puntuaciones si Atlas está configurado. Reiniciar limpia el formulario.
- **Cámara en vivo**: pulsa Iniciar análisis, permite el acceso y pulsa **Grabar / Record** en el control de cámara. Se solicita un fotograma cada 2 segundos. Pulsa **Detener análisis y cámara** para cerrar la captura y conservar el último resultado. Los fotogramas no generan documentos MongoDB.
- **Guardar resultado actual (sin imagen)** guarda únicamente el resultado visible de cámara. Sin Atlas, la interfaz informa que no se almacenó.
- La sección **Captura manual** permite capturar una imagen desde la cámara y analizarla sin streaming. Detén primero el modo periódico.

La cámara necesita **localhost o HTTPS**. Para acceder desde un teléfono a una IP de la red local, HTTP normalmente no habilita la cámara: utiliza un entorno HTTPS autorizado. Se solicita la cámara posterior como preferencia y Gradio expone su selector de dispositivos. Android/iOS y el cambio frontal/posterior **no están verificados**.

## Pruebas locales

```bash
GRADIO_ANALYTICS_ENABLED=False MPLCONFIGDIR=/tmp/ecoguard-mpl \
.venv-auditoria/bin/python -m unittest discover -s tests -v
GRADIO_ANALYTICS_ENABLED=False MPLCONFIGDIR=/tmp/ecoguard-mpl \
.venv-auditoria/bin/python scripts/benchmark_camera.py
.venv-auditoria/bin/python scripts/verificar_modelo_render.py
```

En un entorno de pruebas nuevo instala `requirements-test.txt`. Las nuevas pruebas ejecutan ONNX real sobre las 23 imágenes reservadas y los callbacks/componentes Gradio; no sustituyen una cámara física. Los contratos MongoDB usan dobles y codificación BSON local; no prueban Atlas real.

Comprobación opcional con Playwright **de desarrollo**, servidor local y Chromium instalados:

```bash
node scripts/check_ui_browser.cjs
```

Admite `PLAYWRIGHT_MODULE`, `CHROMIUM_EXECUTABLE` y `ECOGUARD_URL`. Captura escritorio y ancho de teléfono emulado, carga imágenes y prueba una cámara sintética. No certifica dispositivos móviles físicos. La ejecución aquí quedó bloqueada por bibliotecas de Chromium ausentes.

## MongoDB y Render

Configura `MONGODB_URI` y `SESSION_SECRET` como secretos y `MONGODB_DB=ecoguard`; no se carga `.env` automáticamente. No se almacenan fotografías en MongoDB. Gradio utiliza archivos temporales y limpia periódicamente su caché, por lo que no debe interpretarse como procesamiento sin escritura temporal en disco.

`render.yaml` mantiene `plan: free`, un worker, modelo ONNX, comprobación de integridad y despliegue automático desactivado. **No se ha publicado**. La capacidad y latencia real en Render Free, HTTPS/cámara, Atlas y navegadores siguen pendientes. Si el modo periódico no resulta estable en ese entorno, utiliza la captura manual ya incluida.
