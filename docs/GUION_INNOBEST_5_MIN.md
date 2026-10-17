# Guion oral — aproximadamente cinco minutos

## 1. Portada — 20 segundos

Buenos días. Presentamos HUÁNUCO ECOGUARD AI, una aplicación académica en Python para clasificar patrones visuales relacionados con el aire, el agua y el suelo. Nuestro propósito es apoyar la educación ambiental mediante una herramienta comprensible para cualquier persona. La propuesta se presenta en el contexto de INNOBEST; falta incorporar su enunciado específico para documentar la correspondencia exacta.

## 2. Problemática — 30 segundos

Las fotografías permiten documentar humo, residuos y alteraciones visibles en nuestro entorno. Sin embargo, interpretar una imagen puede ser difícil y una observación aislada no sustituye un estudio ambiental. El proyecto organiza estas observaciones y ofrece orientación general. Desde el inicio distinguimos reconocer patrones de medir contaminación: una cámara no determina concentraciones químicas y nuestro sistema tampoco certifica la calidad ambiental.

## 3. Objetivos — 25 segundos

Buscamos que una persona cargue una fotografía, revise sus puntuaciones y reciba una interpretación sencilla junto con recomendaciones ambientales. También queremos conservar un historial de análisis y consultar estadísticas por categoría. La aplicación debe ser accesible desde computadoras y teléfonos. Los resultados necesitan trazabilidad: cada registro lleva fecha, identificador y versión del modelo.

## 4. Solución — 30 segundos

Utilizamos YOLO11n-cls, un modelo de clasificación de imágenes. Clasifica la fotografía completa en una de tres categorías: aire contaminado, agua contaminada o suelo contaminado. Mostramos las puntuaciones de las tres alternativas para hacer visible su decisión. No se entrenó una categoría de ambiente limpio. Por ello, siempre seleccionará alguna clase incluso ante una fotografía ajena al problema. Las puntuaciones no están calibradas como diagnóstico científico.

## 5. Dataset — 30 segundos

El respaldo original contiene 165 fotografías. Se identificaron 151 fotografías únicas para la partición experimental: 105 de entrenamiento, 23 de validación y 23 de prueba. Conservamos el respaldo sin regenerarlo ni modificarlo y comprobamos su huella SHA256. Las particiones originales y los pesos deben recuperarse desde Drive para completar la trazabilidad. El tamaño reducido del conjunto es una limitación central del experimento.

## 6. Arquitectura — 30 segundos

La interfaz de Gradio recibe la fotografía y comprueba formato y tamaño. El motor ejecuta la clasificación en CPU y devuelve las puntuaciones para construir una explicación en español. MongoDB Atlas conserva únicamente metadatos, sin fotografías completas ni información personal innecesaria. Google Drive conserva los originales y la evidencia académica. Render alojará la aplicación. Si Atlas falla, se informa que el resultado no tiene guardado confirmado.

## 7. Entrenamiento — 25 segundos

El entrenamiento finalizó en Google Colab con una NVIDIA Tesla T4 y CUDA durante 100 épocas. El modelo utilizado fue YOLO11n-cls con Ultralytics y Python. La mejor exactitud reportada sobre validación fue 95,7 por ciento. La GPU se utilizó para entrenar; la inferencia se prepara para CPU. No repetiremos el entrenamiento para resolver la recuperación de archivos.

## 8. Resultados — 35 segundos

En el test reservado se lograron 21 aciertos de 23, equivalentes al 91,30 por ciento. La matriz recuperada del historial muestra diez aciertos de aire, siete de suelo y cuatro de las seis imágenes de agua. Dos imágenes de agua se clasificaron como suelo. Estos resultados describen este test pequeño: una sola imagen modifica la exactitud en aproximadamente 4,35 puntos porcentuales. Falta recuperar los archivos originales para verificar toda la evidencia de manera independiente.

## 9. Aplicación — 30 segundos

La aplicación permite cargar una fotografía, verla, analizarla y consultar el historial. Se preparó Render con un motor ONNX más ligero y variables de entorno para Atlas. ONNX no se habilita sin comparar sus predicciones con best.pt usando fotografías reales. Actualmente están pendientes la recuperación autenticada, la conexión real con Atlas y la publicación autorizada. Por eso todavía no presentamos una URL ni afirmamos una demostración en línea.

## 10. Demostración y conclusiones — 25 segundos

Cuando estén disponibles los originales, la demostración consistirá en cargar una fotografía nueva, observar sus tres puntuaciones y localizar su identificador en MongoDB. Hoy podemos mostrar la evidencia del entrenamiento y la preparación técnica; no simularemos una clasificación. Concluimos que la propuesta es viable como apoyo educativo, con límites claros y validaciones pendientes. El cierre requiere demostrar el recorrido completo desde la fotografía hasta el registro persistente.

Duración prevista: 300 segundos. Tras el despliegue, actualizar únicamente los estados comprobados y reservar tiempo de la diapositiva 9 para la demostración real.
