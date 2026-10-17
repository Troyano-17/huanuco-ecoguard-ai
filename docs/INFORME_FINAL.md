# Informe académico — HUÁNUCO ECOGUARD AI

## Problema y objetivo

La acumulación de residuos en ríos y suelos y la presencia de humo afectan el
entorno de las comunidades de Huánuco. Una fotografía puede apoyar la educación
ambiental y la observación ciudadana, pero no determina concentraciones de
contaminantes ni sustituye una inspección o un análisis de laboratorio.

El objetivo es demostrar un sistema que recibe una fotografía, identifica la
clase visual más parecida a lo aprendido y ofrece una explicación y acciones
ambientales generales. Su alcance es académico: no certifica calidad del agua,
del aire o del suelo y no debe orientar decisiones sanitarias.

## Tecnologías y arquitectura

Python integra los componentes. Ultralytics ejecuta YOLO11n-cls y PyTorch realiza
los cálculos en CUDA. Pillow verifica y prepara la imagen de entrada; Gradio
ofrece selector, arrastrar y soltar, vista previa y resultados en el navegador.
CSV y JSON conservan métricas, configuración y relación del dataset. SHA256
comprueba que las copias mantienen el contenido original.

La arquitectura es **WSL → Colab Tesla T4 → Google Drive → Gradio → navegador Linux**.
WSL controla archivos y comandos; no procesa masivamente fotografías. Colab
realizó la preparación y el entrenamiento y ejecuta la inferencia. Drive mantiene
el dataset, checkpoints y entrega aunque desaparezca `/content`. Gradio presenta
la inferencia en el navegador. Los enlaces temporales sirven para una sesión;
el notebook y los artefactos persistentes permiten reconstruir la demostración.

Se utilizó Colab con Tesla T4 para disponer de CUDA sin instalar entrenamiento
pesado en la laptop. La GPU acelera el entrenamiento y mantiene una separación
clara entre control local y cómputo remoto. Colab tiene límites de sesión y no
es un alojamiento permanente.

## Dataset y significado de las clases

La validación técnica procesó 165 imágenes y encontró 151 fotografías únicas
por sus píxeles. La relación original está en `entrega/dataset/manifest_original.csv`.
Las candidatas antes de deduplicar fueron: aire 70, agua 50 y suelo 45.
Estos números no equivalen al número de fotografías únicas por clase.

La preparación existente agrupó imágenes similares para evitar cruces entre
train, val y test. La salida de Colab confirma **105 train, 23 val y 23 test**.
La distribución definitiva por clase y partición se verifica al recuperar
`particiones.csv`. El cierre no regeneró ni modificó estas separaciones.

- `aire_contaminado`: patrones de humo o escenas de incendio/quema presentes en
  el material de origen. No identifica gases invisibles ni su concentración.
- `agua_contaminada`: residuos y alteraciones visibles asociadas al agua en las
  fotografías de referencia. Turbidez o color por sí solos no prueban contaminación.
- `suelo_contaminado`: residuos y señales visuales sobre suelo o vegetación.
  No detecta composición química, metales ni patógenos.

La carpeta fuente `INCENDIOS` puede incluir incendios forestales y escenas
ambiguas. El manifiesto histórico conserva campos de revisión semántica y
licencia pendientes. El cierre no convierte esa revisión pendiente en una
aprobación. Tampoco acredita que todas las imágenes sean de Huánuco. La
procedencia, representatividad y derechos de uso deben describirse honestamente
antes de una difusión más amplia.

## Modelo y entrenamiento

YOLO11n-cls es la variante de clasificación de imágenes: asigna puntuaciones a
la imagen completa. No produce cajas de detección ni mapas de contaminación.
«n» identifica la variante nano. En el registro original, el modelo final tiene
1 529 867 parámetros y 47 capas después de fusionar operaciones para inferencia.

Se utilizó transfer learning: pesos previamente entrenados aportan características
visuales generales y se ajustan a las tres clases del proyecto. Esto facilita
trabajar con pocas imágenes, pero no compensa un dataset poco representativo.
La configuración exacta queda en `args.yaml` y `run-config.json` originales.

El entrenamiento completó **100 épocas** en Tesla T4. Una época es una pasada
por el conjunto de entrenamiento. El sistema seleccionó `best.pt` según
validación y conservó `last.pt`. El cierre no repitió entrenamiento, modificó
pesos ni alteró checkpoints. El `results.csv` original de 100 filas sigue
pendiente de descarga local; el historial sí conserva la finalización.

## Resultados reales

Fuente: salida original de Colab, recuperada del historial local del CLI. No se
ha generado una evaluación nueva. Los originales CSV/JSON se contrastan al
recuperar la entrega mediante SHA256 y comprobaciones de contenido.

| Conjunto / clase | Resultado |
|---|---:|
| Test total | 21/23 = 91.3043 % |
| Aire en test | 10/10 |
| Agua en test | 4/6 |
| Suelo en test | 7/7 |
| Validación del mejor modelo | 0.957, precisión de impresión del registro |

La matriz de test conserva el orden original **agua_contaminada,
aire_contaminado, suelo_contaminado**. Filas: clase real; columnas: predicción.
Este orden de presentación no se presupone como orden de índices del checkpoint.
La aplicación consulta `model.names` antes de interpretar sus puntuaciones.

| Real / Predicción | agua_contaminada | aire_contaminado | suelo_contaminado |
|---|---:|---:|---:|
| agua_contaminada | 4 | 0 | 2 |
| aire_contaminado | 0 | 10 | 0 |
| suelo_contaminado | 0 | 0 | 7 |

Los dos errores corresponden a fotografías de agua clasificadas como suelo.
La exactitud es aciertos/total; 91.3043 % describe estas 23 fotografías. El 10/10
o 7/7 no implica rendimiento perfecto fuera de este test. Las tres puntuaciones
de cada fotografía son salidas del clasificador, sin calibración científica.

## Limitaciones y posible sobreajuste

151 fotografías únicas constituyen una muestra pequeña. En 100 épocas existe
riesgo de memorizar rasgos de las escenas, fondos o procedencias. La exactitud
alta de validación no descarta sobreajuste. Las curvas originales de pérdida
y exactitud deben revisarse al recuperar `results.csv` y `results.png`; sin
ellas no se afirma haber completado un análisis cuantitativo del sobreajuste.

El test de 23 imágenes tiene alta incertidumbre; una sola imagen cambia la
exactitud en aproximadamente 4.35 puntos porcentuales. El agrupamiento por
similitud reduce cruces evidentes pero no demuestra independencia geográfica,
temporal o de todas las escenas. No hay evaluación externa ni calibración.

El modelo siempre elige una de tres clases; puede etiquetar erróneamente un
ambiente limpio. Escenas mixtas, niebla, iluminación, recortes, fondos e imágenes
de nuevos lugares pueden causar errores. No mide severidad, concentraciones,
causas ni riesgos sanitarios. Las recomendaciones son educativas y generales.

## Calidad y demostración

La batería local comprueba guardas, contratos de clase e integridad sin importar
PyTorch. Los dobles de prueba validan contratos y no constituyen inferencia real.
Las pruebas de integración en Colab cargan `best.pt`, verifican su orden real,
analizan una fotografía válida, rechazan un archivo inválido y comprueban Gradio
mediante HTTP/API. La verificación visual en escritorio y teléfono se realiza
con el procedimiento del guion. Estas comprobaciones remotas quedan pendientes
por autenticación; no se sustituyeron con resultados simulados.

## Referencias técnicas

- [Ultralytics: clasificación de imágenes](https://docs.ultralytics.com/tasks/classify/),
  interfaz de `probs` y nombres de clases.
- [Ultralytics: inferencia](https://docs.ultralytics.com/modes/predict/), salida del modelo.
- [Gradio: Blocks](https://www.gradio.app/docs/gradio/blocks), interfaz y lanzamiento.
- [Gradio 5.49.1: código oficial de Blocks](https://github.com/gradio-app/gradio/blob/gradio%405.49.1/gradio/blocks.py),
  parámetros de la familia de versiones seleccionada.
