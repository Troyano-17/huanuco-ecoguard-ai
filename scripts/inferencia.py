"""Inferencia de una fotografía. No descarga modelos ni permite entrenamiento."""
import importlib.util
import hashlib
import zipfile
import math
from pathlib import Path
import threading
import warnings
import os
import json

CLASSES = frozenset(('aire_contaminado', 'agua_contaminada', 'suelo_contaminado'))
# Regla de aplicación; no cambia las puntuaciones ni las clases del modelo.
MIN_ACCEPTANCE_SCORE = 0.60
INCONCLUSIVE_TITLE = 'No pudimos identificar la escena con suficiente claridad'
INCONCLUSIVE_DESCRIPTION = 'Intenta mostrar mejor el agua, el aire o el suelo que deseas analizar. Puedes acercar la cámara, mejorar la iluminación o elegir otra fotografía.'


def accepted_label(scores):
    """Devuelve la clase de mayor puntuación si alcanza el mínimo inclusivo."""
    label = max(scores, key=scores.get)
    return label if scores[label] >= MIN_ACCEPTANCE_SCORE else None


LABELS = {'aire_contaminado': 'Aire contaminado', 'agua_contaminada': 'Agua contaminada',
          'suelo_contaminado': 'Suelo contaminado'}
DESCRIPTIONS = {
    'aire_contaminado': 'La fotografía presenta patrones que el modelo asocia con humo o contaminación del aire.',
    'agua_contaminada': 'La fotografía presenta patrones que el modelo asocia con residuos o alteraciones visibles en el agua.',
    'suelo_contaminado': 'La fotografía presenta patrones que el modelo asocia con residuos sobre el suelo o la vegetación.'}
ADVICE = {
    'aire_contaminado': 'Como orientación general, evita quemar residuos, mantente lejos del humo y comunica las quemas a las autoridades locales.',
    'agua_contaminada': 'Como orientación general, evita arrojar residuos a los ríos, participa en campañas de limpieza organizadas y comunica vertimientos a las autoridades locales.',
    'suelo_contaminado': 'Como orientación general, separa los residuos, utiliza puntos de recolección autorizados y comunica acumulaciones de basura a la municipalidad.'}


class AnalysisError(ValueError):
    """Mensaje seguro para mostrar a la persona usuaria."""


def class_mapping(names):
    mapping = dict(enumerate(names)) if isinstance(names, (list, tuple)) else dict(names)
    if set(mapping) != {0, 1, 2} or set(mapping.values()) != CLASSES:
        raise RuntimeError('El modelo no contiene exactamente las tres clases ECOGUARD.')
    return mapping


def require_colab():
    if not Path('/content').is_dir() or importlib.util.find_spec('google.colab') is None:
        raise RuntimeError('La inferencia se ejecuta en Colab. Desde Linux utiliza: python3 ecoguard.py app')


def load_image(source):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if source is None:
        raise AnalysisError('Carga una fotografía antes de analizar.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            if isinstance(source, Image.Image):
                if source.width * source.height > 20_000_000:
                    raise AnalysisError('Utiliza una imagen de hasta 20 megapíxeles.')
                image = ImageOps.exif_transpose(source).copy()
            else:
                path = Path(source)
                if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                    raise AnalysisError('Utiliza una fotografía de hasta 20 MB.')
                with Image.open(path) as original:
                    if original.format not in ('JPEG', 'PNG', 'WEBP'):
                        raise AnalysisError('Utiliza una fotografía JPG, PNG o WEBP.')
                    if original.width * original.height > 20_000_000:
                        raise AnalysisError('Utiliza una imagen de hasta 20 megapíxeles.')
                    original.load()
                    image = ImageOps.exif_transpose(original).copy()
            if image.width * image.height > 20_000_000:
                raise AnalysisError('Utiliza una imagen de hasta 20 megapíxeles.')
            return image.convert('RGB')
    except AnalysisError:
        raise
    except (OSError, ValueError, TypeError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AnalysisError('No se pudo leer la imagen. Carga una fotografía JPG, PNG o WEBP válida.') from None


class Classifier:
    def __init__(self, weights):
        path = Path(weights)
        if path.name != 'best.pt' or not path.is_file() or not path.stat().st_size:
            raise RuntimeError('Falta el best.pt original. Recupera y verifica la entrega.')
        from artefactos import STORE, RUN_NAME, DELIVERY_SHA256, sha256
        archive = Path(os.environ.get('ORIGINAL_ARCHIVE', str(Path(__file__).resolve().parents[1] / 'entrega/entrega-original.zip')))
        if not archive.is_file():
            archive = STORE / 'runs' / RUN_NAME / 'entrega.zip'
        if not archive.is_file() or sha256(archive) != DELIVERY_SHA256:
            raise RuntimeError('La entrega original de Drive no supera la verificación SHA256.')
        with zipfile.ZipFile(archive) as original:
            expected = hashlib.sha256(original.read('train100/weights/best.pt')).hexdigest()
        if sha256(path) != expected:
            raise RuntimeError('Los pesos no corresponden al best.pt original de ECOGUARD.')
        import torch
        torch.set_num_threads(1)
        from ultralytics import YOLO
        self.model = YOLO(str(path), task='classify')
        if self.model.task != 'classify':
            raise RuntimeError('Se requiere el checkpoint de clasificación.')
        self.names = class_mapping(self.model.names)
        self.lock = threading.Lock()

    def predict(self, source):
        image = load_image(source)
        with self.lock:
            result = self.model.predict(image, device='cpu', imgsz=224, verbose=False)[0]
        if class_mapping(result.names) != self.names or result.probs is None:
            raise RuntimeError('Salida del modelo incompatible.')
        values = result.probs.data.detach().cpu().tolist()
        if len(values) != 3 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            raise RuntimeError('Puntuaciones inválidas.')
        scores = {self.names[i]: float(v) for i, v in enumerate(values)}
        label = max(scores, key=scores.get)
        return label, scores


def onnx_tensor(image):
    """Resize bilineal y CenterCrop de classify_transforms(224), sin torch."""
    import numpy as np
    from PIL import Image
    w, h = image.size
    size = (224, int(224 * h / w)) if w <= h else (int(224 * w / h), 224)
    image = image.resize(size, Image.Resampling.BILINEAR)
    left, top = round((size[0] - 224) / 2), round((size[1] - 224) / 2)
    image = image.crop((left, top, left + 224, top + 224))
    return (np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0)[None].copy()


class OnnxClassifier:
    def __init__(self, weights):
        from artefactos import sha256, DELIVERY_SHA256
        path = Path(weights)
        record = json.loads(path.with_suffix('.json').read_text())
        if (record['original_archive_sha256'] != DELIVERY_SHA256 or record['onnx_sha256'] != sha256(path)
                or record['parity']['passed'] is not True or record['parity']['images'] < 23):
            raise RuntimeError('ONNX sin integridad o comparación real aprobada contra best.pt.')
        self.names = class_mapping({int(k): v for k, v in record['names'].items()})
        self.version = record['best_sha256']
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
        self.lock = threading.Lock()

    def predict(self, source):
        tensor = onnx_tensor(load_image(source))
        with self.lock:
            values = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0][0].tolist()
        if (len(values) != 3 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values)
                or not math.isclose(sum(values), 1, abs_tol=1e-4)):
            raise RuntimeError('Salida ONNX incompatible.')
        scores = {self.names[i]: float(v) for i, v in enumerate(values)}
        return max(scores, key=scores.get), scores


def create_classifier(weights):
    return OnnxClassifier(weights) if Path(weights).suffix == '.onnx' else Classifier(weights)
