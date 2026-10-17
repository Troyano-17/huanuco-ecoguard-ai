"""Integridad y extracción conservadora, sin importar bibliotecas de visión."""
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

DATASET_SHA256 = 'f17a403815f2d184c668ebda60c9e963916bef296522d98e70b43721d3ceeca5'
DELIVERY_SHA256 = 'ac10f88a010ef3fd0a7480cd984482496c77aa486e2548ff740c6da2fbf6f284'
RUN_NAME = 'train100-' + DATASET_SHA256
STORE = Path('/content/drive/MyDrive/HuanucoEcoGuard')
EXPECTED_MATRIX = [[4, 0, 2], [0, 10, 0], [0, 0, 7]]
EXPECTED_CLASSES = ['agua_contaminada', 'aire_contaminado', 'suelo_contaminado']


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def extract_original(archive_path, destination):
    """Rechaza rutas, enlaces y colisiones antes de escribir; nunca reemplaza archivos."""
    destination = Path(destination)
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        seen = set()
        if sum(e.file_size for e in entries) > 2 * 1024**3:
            raise RuntimeError('Entrega demasiado grande.')
        for entry in entries:
            p = PurePosixPath(entry.filename)
            if (p.is_absolute() or '..' in p.parts or '\\' in entry.filename or
                    not p.parts or ':' in entry.filename or entry.filename in seen or
                    stat.S_ISLNK(entry.external_attr >> 16)):
                raise RuntimeError('Ruta insegura o repetida dentro del ZIP.')
            seen.add(entry.filename)
            target = destination / entry.filename
            if not target.resolve().is_relative_to(destination.resolve()):
                raise RuntimeError('Destino fuera de la entrega.')
            if entry.is_dir():
                continue
            if target.exists() and (not target.is_file() or sha256(target) != hashlib.sha256(archive.read(entry)).hexdigest()):
                raise RuntimeError('Archivo existente diferente; no se sobrescribe: ' + entry.filename)
        if archive.testzip() is not None:
            raise RuntimeError('ZIP corrupto.')
        for entry in entries:
            target = destination / entry.filename
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)


def verify_original(folder, archive_path=None):
    folder = Path(folder)
    if archive_path is not None:
        if not Path(archive_path).is_file() or sha256(archive_path) != DELIVERY_SHA256:
            raise RuntimeError('El ZIP original no coincide con SHA256 de Colab.')
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                if entry.is_dir(): continue
                path = folder / entry.filename
                if not path.is_file() or sha256(path) != hashlib.sha256(archive.read(entry)).hexdigest():
                    raise RuntimeError('Original extraído diferente del ZIP: ' + entry.filename)
    required = ['train100/weights/best.pt', 'train100/weights/last.pt',
                'train100/results.csv', 'train100/args.yaml', 'train100/results.png',
                'metricas_test.json', 'particiones.csv', 'predicciones_test.csv',
                'matriz_confusion.csv', 'matriz_confusion.png', 'run-config.json', 'versiones.txt']
    missing = [name for name in required if not (folder / name).is_file() or not (folder / name).stat().st_size]
    if missing:
        raise RuntimeError('Faltan originales: ' + ', '.join(missing))
    with (folder / 'train100/results.csv').open() as f:
        rows = [{k.strip(): v.strip() for k, v in r.items()} for r in csv.DictReader(f)]
    if [int(r['epoch']) for r in rows] != list(range(1, 101)):
        raise RuntimeError('No constan las 100 épocas consecutivas.')
    if not all(math.isfinite(float(v)) for r in rows for v in r.values()):
        raise RuntimeError('Métricas de entrenamiento no finitas.')
    metrics = json.loads((folder / 'metricas_test.json').read_text())
    if (metrics['clases'] != EXPECTED_CLASSES or metrics['matriz'] != EXPECTED_MATRIX or
            metrics['muestras'] != 23 or not math.isclose(metrics['accuracy'], 21 / 23, abs_tol=1e-12)):
        raise RuntimeError('Métricas de test diferentes de las evidencias originales.')
    with (folder / 'matriz_confusion.csv').open() as f:
        matrix = list(csv.DictReader(f))
    if [r['real'] for r in matrix] != EXPECTED_CLASSES or [[int(r[c]) for c in EXPECTED_CLASSES] for r in matrix] != EXPECTED_MATRIX:
        raise RuntimeError('Matriz CSV o etiquetas incompatibles.')
    with (folder / 'predicciones_test.csv').open() as f:
        predictions = list(csv.DictReader(f))
    if len(predictions) != 23 or sum(r['real'] == r['prediccion'] for r in predictions) != 21:
        raise RuntimeError('Predicciones originales incompatibles.')
    with (folder / 'particiones.csv').open() as f:
        partitions = list(csv.DictReader(f))
    from collections import Counter
    distribution = Counter(r['particion'] for r in partitions)
    if distribution != {'train': 105, 'val': 23, 'test': 23} or len({r['id'] for r in partitions}) != 151:
        raise RuntimeError('Particiones originales incompatibles.')
    for key in ('grupo', 'pixel_sha256'):
        membership = {}
        for row in partitions:
            membership.setdefault(row[key], set()).add(row['particion'])
        if any(len(splits) != 1 for splits in membership.values()):
            raise RuntimeError('Cruce entre particiones originales: ' + key)
    selected = {r['id']: r['clase'] for r in partitions if r['particion'] == 'test'}
    if len({r['id'] for r in predictions}) != 23 or {r['id']:r['real'] for r in predictions} != selected:
        raise RuntimeError('Predicciones no corresponden al test reservado.')
    actual = [[sum(r['real'] == real and r['prediccion'] == predicted for r in predictions)
               for predicted in EXPECTED_CLASSES] for real in EXPECTED_CLASSES]
    if actual != EXPECTED_MATRIX:
        raise RuntimeError('Las predicciones no reconstruyen la matriz original.')
    by_class = {s: dict(Counter(r['clase'] for r in partitions if r['particion'] == s)) for s in distribution}
    return {'epocas': len(rows), 'accuracy_test': metrics['accuracy'], 'clases_matriz': metrics['clases'],
            'particiones': dict(distribution), 'distribucion_por_clase': by_class,
            'best_sha256': sha256(folder / 'train100/weights/best.pt')}


def manifest(folder):
    folder = Path(folder)
    return {str(p.relative_to(folder)): {'bytes': p.stat().st_size, 'sha256': sha256(p)}
            for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'SHA256.json'
            and not {'__pycache__', '.runtime', 'dist'}.intersection(p.relative_to(folder).parts)}


def verify_manifest(folder):
    folder = Path(folder)
    records = json.loads((folder / 'SHA256.json').read_text())
    for name, expected in records.items():
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file():
            raise RuntimeError('Falta archivo del manifiesto: ' + name)
        if path.stat().st_size != expected['bytes'] or sha256(path) != expected['sha256']:
            raise RuntimeError('Integridad SHA256 incorrecta: ' + name)
    extra = set(manifest(folder)) - set(records)
    if extra:
        raise RuntimeError('Archivos fuera del manifiesto: ' + ', '.join(sorted(extra)))
    return len(records)
