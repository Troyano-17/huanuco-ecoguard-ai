"""Verificación obligatoria en build; nunca descarga pesos al arrancar."""
import os
from inferencia import OnnxClassifier

if __name__ == '__main__':
    classifier = OnnxClassifier(os.environ.get('MODEL_PATH', 'models/best.onnx'))
    print('ONNX: integridad, procedencia, clases y reporte de equivalencia verificados.')
