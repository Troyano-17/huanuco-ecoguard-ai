# Guion de exposición — aproximadamente 5 minutos

## 0:00–0:40 · Problema y objetivo

«Buenos días. Presento HUÁNUCO ECOGUARD AI, un proyecto de clasificación visual
ambiental. Partimos de tres situaciones: humo en el aire, residuos en el agua y
residuos sobre el suelo. Queremos que una persona cargue una fotografía y reciba
una orientación comprensible para aprender a observar y cuidar su entorno.
El sistema no mide químicamente la contaminación ni reemplaza un laboratorio».

## 0:40–1:25 · Dataset

«Procesamos 165 imágenes y encontramos 151 fotografías únicas. Se distribuyeron
en 105 de entrenamiento, 23 de validación y 23 de prueba. Las imágenes similares
se agruparon para reducir cruces entre conjuntos. Mantuvimos el test reservado.
El conjunto es pequeño; hay límites de representatividad y revisión semántica
que están documentados. No afirmamos que todas las fotografías sean de Huánuco».

Muestra `python3 ecoguard.py evidencias` y la relación del dataset si se solicita.

## 1:25–2:10 · Modelo y arquitectura

«Utilizamos Python y YOLO11n-cls, una red de clasificación de imágenes completas.
Aplicamos transfer learning, adaptando características aprendidas previamente
a nuestras tres clases. El entrenamiento completó 100 épocas en Google Colab
con GPU Tesla T4. Así evitamos cargar la laptop con entrenamiento. WSL controla
el proyecto, Colab realiza los cálculos, Drive conserva los artefactos y Gradio
presenta los resultados en el navegador. El checkpoint elegido es best.pt».

Muestra la salida `100 epochs completed` y, cuando esté recuperado, `results.csv`.

## 2:10–3:35 · Demostración en vivo

Abre la URL que devuelve `python3 ecoguard.py app`, o ejecuta el notebook con el
proxy autenticado de Colab. Carga una fotografía y señala su vista previa.
Pulsa **Analizar fotografía**.

«Aquí aparece la categoría que más puntuación recibió. También mostramos las
tres puntuaciones en porcentaje. No son probabilidades científicamente
calibradas y no expresan la concentración de contaminantes. La explicación
describe la asociación visual; las recomendaciones son ambientales y generales».

Pulsa **Reiniciar análisis**, carga otra fotografía y comprueba que no quedan
resultados anteriores. Si el modelo se equivoca, explica el error con honestidad.
Carga un archivo de texto pequeño para mostrar el mensaje de archivo inválido.
En teléfono o vista de 390 px comprueba que se puede cargar, leer y reiniciar.

## 3:35–4:25 · Métricas y matriz

«En el test reservado acertó 21 de 23 fotografías: 91.3043 %. Aire tuvo 10 de 10,
agua 4 de 6 y suelo 7 de 7. Las dos fotografías incorrectas eran de agua y se
clasificaron como suelo. La matriz usa las etiquetas originales; las filas son
la clase real y las columnas la predicción. La validación del mejor modelo
reportó 0.957. Esto describe nuestros conjuntos y no garantiza el mismo
rendimiento ante cualquier fotografía».

Muestra `entrega/evidencias/matriz_confusion_desde_historial.csv` o la imagen
original cuando ya esté descargada. Identifica siempre la procedencia.

## 4:25–5:00 · Límites y cierre

«El dataset es pequeño y existe riesgo de sobreajuste. No tenemos una clase de
ambiente limpio; por eso el modelo siempre escogerá una de las tres categorías.
Tampoco determina severidad o causas. Nuestro aporte es una demostración
reproducible, con pesos persistentes en Drive, verificaciones SHA256 y una
interfaz comprensible. Como trabajo futuro proponemos una evaluación externa
y una revisión más amplia del dataset, sin cambiar los resultados que hoy presentamos».

## Preparación antes de entrar al aula

Desde la raíz del proyecto:

```bash
python3 ecoguard.py recuperar
python3 ecoguard.py verificar
python3 ecoguard.py pruebas
python3 ecoguard.py pruebas-colab
python3 ecoguard.py app
python3 ecoguard.py demo --en-vivo
```

Ten Drive montado, una GPU de Colab activa, el notebook disponible, dos
fotografías elegidas con criterio explícito y el ZIP con su SHA256. Comprueba
la interfaz en escritorio y teléfono. No ejecutes los scripts de entrenamiento.
Si falta red, expón las evidencias guardadas y declara que la inferencia en vivo
no está disponible; no la sustituyas con una predicción predefinida.
