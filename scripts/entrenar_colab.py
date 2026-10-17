"""Preparación, entrenamiento e inferencia. Ejecutar SOLO en Google Colab."""
import collections
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import threading
import tempfile
import traceback
import uuid
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from persistencia_colab import (STORE, require_drive, sha256, copy_verified,
                               commit_snapshot, restore_snapshot, boot_id, retry_io)

ROOT = Path('/content/ecoguard-entrenamiento')
CLASSES = ('agua_contaminada', 'aire_contaminado', 'suelo_contaminado')
DATASET_HASH = os.environ.get('ECOGUARD_DATASET_SHA256', '')
RUN = STORE / 'runs' / ('train100-' + DATASET_HASH)
RUN_ID = 'train100-' + DATASET_HASH


def require_colab():
    if not Path('/content').is_dir() or importlib.util.find_spec('google.colab') is None:
        raise RuntimeError('Solo Google Colab; prohibido procesar imágenes o entrenar localmente.')
    import torch
    if not torch.cuda.is_available() or 'T4' not in torch.cuda.get_device_name(0):
        raise RuntimeError('Se requiere CUDA con NVIDIA Tesla T4 en la sesión existente.')
    print('CUDA:', torch.version.cuda, '| GPU:', torch.cuda.get_device_name(0), flush=True)
    subprocess.run(['nvidia-smi'], check=True)


def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def state(phase, **extra):
    payload = dict(fase=phase, run_id=RUN_ID, dataset_sha256=DATASET_HASH,
                   boot_id=boot_id(), **extra)
    atomic_json(ROOT / 'estado.json', payload)
    if RUN.is_dir():
        from persistencia_colab import atomic_json as persist_json
        persist_json(RUN / 'estado.json', payload)
    print('FASE:', phase, extra, flush=True)


def source_rows(root):
    """Resolver rutas antiguas en memoria, sin modificar el manifiesto respaldado."""
    manifest = root / 'manifest.csv'
    if not manifest.is_file():
        return None
    with manifest.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 165 or len({r['id'] for r in rows}) != 165:
        return None
    for row in rows:
        path = Path(row['convertido'])
        # Algunos manifiestos conservan el prefijo de la sesión anterior.
        if 'revision' in path.parts:
            path = Path(*path.parts[path.parts.index('revision'):])
        resolved = (root / path).resolve()
        if (row['estado_tecnico'] != 'valida' or
                not resolved.is_relative_to(root.resolve()) or
                resolved.suffix.lower() != '.png' or not resolved.is_file()):
            return None
        row['convertido'] = str(resolved.relative_to(root.resolve()))
    if len({r['pixel_sha256'] for r in rows}) != 151:
        return None
    return rows


def restore_source():
    # Esta función nunca extrae fotografías fuera de Google Colab.
    if not Path('/content').is_dir() or importlib.util.find_spec('google.colab') is None:
        raise RuntimeError('La restauración solo se permite en Google Colab.')
    archive_path = STORE / 'datasets' / DATASET_HASH / 'ecoguard-validacion.zip'
    if not archive_path.is_file() or sha256(archive_path) != DATASET_HASH:
        raise RuntimeError('Falta respaldo persistente con SHA256 válido.')
    print('SHA256 DEL RESPALDO RESTAURADO EN COLAB:', sha256(archive_path), flush=True)
    state('restaurando', respaldo=str(archive_path))
    with tempfile.TemporaryDirectory(prefix='.ecoguard-restauracion-', dir='/content') as temp:
        staging = Path(temp)
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                dest = (staging / entry.filename).resolve()
                if (not dest.is_relative_to(staging.resolve()) or
                        (entry.external_attr >> 16) & 0o170000 == 0o120000):
                    raise RuntimeError('Ruta insegura en el respaldo remoto.')
            # extractall comprueba CRC; solo se ejecuta remotamente.
            archive.extractall(staging)
        manifests = list(staging.rglob('manifest.csv'))
        valid = [(p.parent, source_rows(p.parent)) for p in manifests]
        valid = [(p, rows) for p, rows in valid if rows is not None]
        if len(valid) != 1:
            raise RuntimeError('El ZIP debe contener un manifiesto válido con 165 PNG y 151 únicas.')
        source, rows = valid[0]
        from PIL import Image
        for row in rows:
            with Image.open(source / row['convertido']) as picture:
                if picture.format != 'PNG':
                    raise RuntimeError('El respaldo contiene una fotografía que no es PNG.')
                picture.verify()
        target = Path('/content/ecoguard-validacion-restaurado')
        if target.exists():
            # Conservar la extracción incompleta anterior sin tocar originales.
            target.rename(target.with_name('ecoguard-validacion-anterior-' + uuid.uuid4().hex))
        source.rename(target)
    print('Restauración verificada: manifest.csv, 165 PNG, 151 fotografías únicas:',
          target, flush=True)
    return target, source_rows(target)


def find_source():
    # No aceptar extracciones de otra versión del respaldo.
    return restore_source()


def partition(groups, labels, seed=42):
    """Asignación de componentes completos; buscar estratificación sin separar escenas."""
    totals = collections.Counter(labels.values())
    splits = ('train', 'val', 'test')
    ratios = (.70, .15, .15)
    rng = random.Random(seed)
    best = None
    for _ in range(3000):
        order = list(groups)
        rng.shuffle(order)
        order.sort(key=lambda g: -len(groups[g]))
        counts = {s: collections.Counter() for s in splits}
        assignment = {}
        for g in order:
            added = collections.Counter(labels[i] for i in groups[g])
            costs = []
            for s, ratio in zip(splits, ratios):
                delta = sum(((counts[s][c] + added[c] - totals[c]*ratio)**2 -
                             (counts[s][c] - totals[c]*ratio)**2) /
                            max(1, totals[c]*ratio) for c in CLASSES)
                costs.append((delta + rng.random()*.2, s))
            selected = min(costs)[1]
            assignment[g] = selected
            counts[selected].update(added)
        if any(counts[s][c] == 0 for s in splits for c in CLASSES):
            continue
        score = sum((counts[s][c] - totals[c]*ratio)**2 / max(1, totals[c]*ratio)
                    for s, ratio in zip(splits, ratios) for c in CLASSES)
        if best is None or score < best[0]:
            best = score, assignment
    if best is None:
        raise RuntimeError('No hay suficientes grupos independientes para tres particiones por clase.')
    return best[1]


def prepare():
    persistent = STORE / 'datasets' / DATASET_HASH
    prepared = persistent / 'preparado.zip'
    marker = persistent / 'preparado.json'
    if marker.is_file():
        metadata = json.loads(marker.read_text())
        if metadata['dataset_sha256'] != DATASET_HASH or sha256(prepared) != metadata['sha256']:
            raise RuntimeError('Dataset preparado corrupto; no reutilizar ni reemplazar silenciosamente.')
        with zipfile.ZipFile(prepared) as archive:
            for entry in archive.infolist():
                if not (ROOT / entry.filename).resolve().is_relative_to(ROOT.resolve()):
                    raise RuntimeError('Ruta insegura en dataset preparado')
            archive.extractall(ROOT)
        with (ROOT / 'particiones.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            row['origen'] = str(ROOT / 'dataset' / row['particion'] / row['clase'] / (row['id'] + '.png'))
        print('DATASET PREPARADO RECUPERADO, SHA256:', metadata['sha256'], flush=True)
        return rows
    source, rows = find_source()
    print('Reutilizando archivos procesados:', source, flush=True)
    seen, unique, canonical = {}, [], {}
    for r in rows:
        key = r['pixel_sha256']
        if key not in seen:
            seen[key] = r
            unique.append(r)
        elif seen[key]['clase_propuesta'] != r['clase_propuesta']:
            raise RuntimeError('Una imagen idéntica tiene etiquetas contradictorias.')
        canonical[r['id']] = seen[key]['id']
    if len(unique) != 151:
        raise RuntimeError(f'Se requieren 151 imágenes únicas, encontradas {len(unique)}')
    parent = {r['id']: r['id'] for r in unique}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a, b):
        a, b = find(canonical[a]), find(canonical[b])
        if a != b:
            parent[max(a, b)] = min(a, b)

    # Conservar todas las alertas previas como restricciones de agrupación.
    pairs = source / 'pares_similares.json'
    if pairs.exists():
        for pair in json.loads(pairs.read_text()):
            join(pair['a'], pair['b'])
    # Comprobar similitudes sobre PNG existentes, únicamente en Colab.
    import imagehash
    from PIL import Image, ImageOps
    hashes = {}
    for r in unique:
        with Image.open(source / r['convertido']) as image:
            variants = [image, ImageOps.mirror(image)]
            hashes[r['id']] = [(imagehash.phash(v), imagehash.dhash(v)) for v in variants]
    for i, a in enumerate(unique):
        for b in unique[i+1:]:
            if any(pa-pb <= 10 or da-db <= 6
                   for pa, da in hashes[a['id']] for pb, db in hashes[b['id']]):
                join(a['id'], b['id'])
    groups = collections.defaultdict(list)
    labels = {r['id']: r['clase_propuesta'] for r in unique}
    for ident in parent:
        groups[find(ident)].append(ident)
    for g, members in sorted(groups.items()):
        if len(members) > 1:
            print('Grupo visual conservador:', g, ', '.join(members), flush=True)
    print('Agrupación automática por dHash/pHash y alertas previas; '
          'no equivale a una verificación semántica de todas las escenas.', flush=True)
    assignments = partition(groups, labels)
    output = []
    for r in unique:
        g = find(r['id'])
        output.append(dict(id=r['id'], clase=labels[r['id']], grupo=g,
                           particion=assignments[g], pixel_sha256=r['pixel_sha256'],
                           origen=str(source / r['convertido'])))
    splitfile = ROOT / 'particiones.csv'
    if splitfile.exists():
        with splitfile.open() as stream:
            previous = list(csv.DictReader(stream))
        stable = lambda records: [{k: v for k, v in r.items() if k != 'origen'}
                                  for r in records]
        if stable(previous) != stable(output):
            raise RuntimeError('La partición existente difiere; no se reemplaza un dataset en uso.')
    if not splitfile.exists() or previous != output:
        temporary = splitfile.with_suffix('.tmp')
        with temporary.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(output[0]))
            writer.writeheader()
            writer.writerows(output)
        temporary.replace(splitfile)
    for split in ('train', 'val', 'test'):
        for cls in CLASSES:
            (ROOT / 'dataset' / split / cls).mkdir(parents=True, exist_ok=True)
    for r in output:
        target = ROOT / 'dataset' / r['particion'] / r['clase'] / (r['id'] + '.png')
        if not target.exists():
            os.link(r['origen'], target)  # Sin conversión ni copias adicionales.
    assert len(output) == 151
    for key in ('grupo', 'pixel_sha256'):
        membership = collections.defaultdict(set)
        for r in output:
            membership[r[key]].add(r['particion'])
        assert all(len(s) == 1 for s in membership.values()), f'Fuga detectada: {key}'
    for split in ('train', 'val', 'test'):
        print(split, dict(collections.Counter(r['clase'] for r in output
                                              if r['particion'] == split)), flush=True)
    print('165 originales conservados; 151 únicas; grupos sin cruces entre particiones.', flush=True)
    packed = bundle('preparado.zip', [splitfile, *(ROOT / 'dataset').rglob('*.png')])
    prepared_hash = copy_verified(packed, prepared)
    from persistencia_colab import atomic_json as persist_json
    persist_json(marker, dict(dataset_sha256=DATASET_HASH, sha256=prepared_hash))
    packed.unlink()
    return output


def bundle(name, files):
    target = ROOT / name
    tmp = target.with_suffix('.tmp')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_file():
                archive.write(path, path.relative_to(ROOT))
    tmp.replace(target)
    return target


def recover(trainer):
    if trainer.device.type != 'cuda':
        raise RuntimeError('El entrenamiento no está utilizando CUDA.')
    epoch = trainer.epoch + 1
    loss = float(trainer.loss.detach().cpu())
    if not math.isfinite(loss):
        raise RuntimeError('Pérdida no finita; entrenamiento detenido por fallo técnico.')
    # on_model_save ocurre antes de que la evaluación final elimine el optimizador.
    recovery = ROOT / 'recuperacion.pt'
    shutil.copy2(trainer.last, recovery.with_suffix('.tmp'))
    recovery.with_suffix('.tmp').replace(recovery)
    import torch
    checkpoint = torch.load(recovery, map_location='cpu', weights_only=False)
    if checkpoint.get('epoch') != epoch - 1 or checkpoint.get('optimizer') is None:
        raise RuntimeError('Checkpoint no reanudable; falta época u optimizador.')
    # Estado adicional exacto, además del optimizador/EMA incluidos por Ultralytics.
    import numpy as np
    torch.save(dict(scheduler=trainer.scheduler.state_dict(), scaler=trainer.scaler.state_dict(),
                    python_rng=random.getstate(), numpy_rng=np.random.get_state(),
                    torch_rng=torch.get_rng_state(), cuda_rng=torch.cuda.get_rng_state_all()),
               ROOT / 'runtime-state.pt')
    files = ['recuperacion.pt', 'runtime-state.pt', 'particiones.csv', 'versiones.txt',
             'run-config.json', 'prueba/results.csv', 'prueba/args.yaml', 'smoke-ok.json',
             'train100/results.csv', 'train100/args.yaml', 'train100/weights/last.pt',
             'train100/weights/best.pt']
    retry_io(lambda: commit_snapshot(RUN, ROOT, files, dict(epoch=epoch, run_id=RUN_ID,
                    dataset_sha256=DATASET_HASH, model='yolo11n-cls',
                    optimizer='AdamW', scheduler='LambdaLR',
                    metrics={k: float(v) for k, v in trainer.metrics.items()},
                    config=vars(trainer.args))))
    state('entrenando', epoca=epoch, perdida=loss)


def restore_runtime(trainer):
    import torch
    import numpy as np
    path = ROOT / 'runtime-state.pt'
    if not path.is_file():
        raise RuntimeError('Falta estado del scheduler/scaler para reanudar.')
    saved = torch.load(path, map_location='cpu', weights_only=False)
    trainer.scheduler.load_state_dict(saved['scheduler'])
    trainer.scaler.load_state_dict(saved['scaler'])
    random.setstate(saved['python_rng'])
    np.random.set_state(saved['numpy_rng'])
    torch.set_rng_state(saved['torch_rng'])
    torch.cuda.set_rng_state_all(saved['cuda_rng'])
    print('Optimizador/EMA, scheduler, scaler y RNG restaurados.', flush=True)


def pretrained_weights():
    """Descarga TLS verificada solo en Colab; pesos base persistentes y versionados por hash."""
    import inspect
    import requests
    from ultralytics.utils.downloads import attempt_download_asset
    release = inspect.signature(attempt_download_asset).parameters['release'].default
    folder = STORE / 'pretrained' / release
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'yolo11n-cls.pt'
    marker = folder / 'sha256.json'
    if marker.is_file():
        expected = json.loads(marker.read_text())['sha256']
        if sha256(target) != expected:
            raise RuntimeError('Pesos preentrenados persistentes corruptos')
    else:
        import time
        url = f'https://github.com/ultralytics/assets/releases/download/{release}/yolo11n-cls.pt'
        temporary = target.with_name('yolo11n-cls.download.pt')
        for attempt in range(4):
            try:
                with requests.get(url, stream=True, timeout=180) as response:
                    response.raise_for_status()
                    with temporary.open('wb') as stream:
                        for chunk in response.iter_content(1024 * 1024):
                            stream.write(chunk)
                if temporary.stat().st_size < 100000:
                    raise RuntimeError('Descarga de pesos incompleta')
                from ultralytics import YOLO
                YOLO(str(temporary))
                temporary.replace(target)
                break
            except requests.exceptions.RequestException as exc:
                status = getattr(exc.response, 'status_code', None)
                if attempt == 3 or (status is not None and status not in (408, 429, 500, 502, 503, 504)):
                    raise
                print('RED COLAB: descarga de pesos, reintento controlado', attempt+1, flush=True)
                time.sleep(2 ** attempt)
        from persistencia_colab import atomic_json as persist_json
        persist_json(marker, dict(sha256=sha256(target), url=url))
    local = ROOT / 'yolo11n-cls.pt'
    copy_verified(target, local)
    return local


def completed_epochs(path, expected):
    with path.open() as stream:
        records = list(csv.DictReader(stream))
    epochs = [int(r['epoch'].strip()) for r in records]
    if epochs != list(range(1, expected+1)):
        raise RuntimeError(f'No se completaron exactamente {expected} épocas: {epochs}')
    for r in records:
        if not all(math.isfinite(float(v)) for v in r.values()):
            raise RuntimeError('Métricas de entrenamiento no finitas.')
    return records


def evaluate(model, rows):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    selected = [r for r in rows if r['particion'] == 'test']
    true, predicted, predictions = [], [], []
    for r in selected:
        result = model.predict(r['origen'], device=0, imgsz=224, verbose=False)[0]
        probs = result.probs.data.detach().cpu().numpy()
        if len(probs) != 3 or not np.isfinite(probs).all():
            raise RuntimeError('Inferencia inválida.')
        label = result.names[int(probs.argmax())]
        true.append(r['clase'])
        predicted.append(label)
        predictions.append(dict(id=r['id'], real=r['clase'], prediccion=label,
                                **{result.names[i]: float(v) for i, v in enumerate(probs)}))
    matrix = confusion_matrix(true, predicted, labels=CLASSES)
    report = classification_report(true, predicted, labels=CLASSES,
                                   output_dict=True, zero_division=0)
    metrics = dict(accuracy=accuracy_score(true, predicted), muestras=len(true),
                   clases=list(CLASSES), reporte=report, matriz=matrix.tolist())
    atomic_json(ROOT / 'metricas_test.json', metrics)
    for name, records in [('predicciones_test.csv', predictions),
                          ('matriz_confusion.csv', [dict(real=c, **dict(zip(CLASSES, row)))
                                                   for c, row in zip(CLASSES, matrix)])]:
        with (ROOT / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(matrix, cmap='Blues')
    ax.set(xticks=range(3), yticks=range(3), xticklabels=CLASSES, yticklabels=CLASSES,
           xlabel='Predicción', ylabel='Clase real', title='Prueba reservada')
    plt.setp(ax.get_xticklabels(), rotation=25, ha='right')
    for (i, j), value in np.ndenumerate(matrix):
        ax.text(j, i, str(value), ha='center', va='center')
    fig.tight_layout()
    fig.savefig(ROOT / 'matriz_confusion.png', dpi=160)
    plt.close(fig)
    print('=== EVALUACIÓN REAL EN TEST ===', flush=True)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    return selected[0]['origen']


def launch_app(sample):
    from app_gradio import build_app
    app, infer = build_app(ROOT / 'train100/weights/best.pt')
    from PIL import Image
    with Image.open(sample) as image:
        print('Prueba real Gradio:', infer(image.convert('RGB')), flush=True)
    _, local, public = app.launch(share=True, server_name='0.0.0.0',
                                  prevent_thread_lock=True, show_error=True)
    if not public:
        raise RuntimeError('Modelo evaluado, pero Gradio no obtuvo URL pública.')
    state('completo', epocas=100, url=public, local=local)
    threading.Event().wait()  # Mantener servidor remoto disponible.


def main():
    # El descriptor heredado es obligatorio: la entrada directa no puede duplicar el trabajo.
    lock_fd = int(os.environ.get('ECOGUARD_LOCK_FD', '-1'))
    if lock_fd < 0:
        raise RuntimeError('Inicia mediante el controlador remoto con bloqueo.')
    os.fstat(lock_fd)
    require_drive()
    RUN.mkdir(parents=True, exist_ok=True)
    require_colab()
    ROOT.mkdir(exist_ok=True)
    restored = restore_snapshot(RUN, ROOT, DATASET_HASH)
    state('preparando')
    # Inspeccionar primero; instalar solo lo que falte, dentro de Colab.
    packages = {'ultralytics': 'ultralytics>=8.3,<9', 'gradio': 'gradio>=5,<7',
                'imagehash': 'ImageHash>=4.3,<5', 'sklearn': 'scikit-learn>=1.5,<2'}
    config_file = RUN / 'config.json'
    saved_config = json.loads(config_file.read_text()) if config_file.exists() else None
    if saved_config:
        packages['ultralytics'] = 'ultralytics==' + saved_config['ultralytics']
    missing = [spec for module, spec in packages.items()
               if importlib.util.find_spec(module) is None]
    if missing:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--retries', '3',
                        '--timeout', '180', *missing], check=True, timeout=900)
    with (ROOT / 'versiones.txt').open('w') as stream:
        subprocess.run([sys.executable, '-m', 'pip', 'freeze'], check=True, stdout=stream)
    rows = prepare()
    from ultralytics import YOLO
    import ultralytics
    import torch
    common = dict(data=str(ROOT / 'dataset'), imgsz=224, batch=16, device=0,
                  workers=2, seed=42, deterministic=True, patience=0, save=True,
                  cache=False, project=str(ROOT), exist_ok=True, plots=True,
                  optimizer='AdamW', lr0=.001, time=None)
    config = dict(run_id=RUN_ID, dataset_sha256=DATASET_HASH, model='yolo11n-cls.pt',
                  epochs=100, smoke_epochs=2, ultralytics=ultralytics.__version__,
                  torch=torch.__version__, training=common,
                  code_sha256=sha256(Path(__file__)),
                  pretrained_sha256=(saved_config['pretrained_sha256'] if saved_config
                                     else sha256(pretrained_weights())))
    if saved_config and saved_config != config:
        raise RuntimeError('Configuración/versiones cambiaron; no reanudar silenciosamente.')
    from persistencia_colab import atomic_json as persist_json
    if not config_file.exists():
        persist_json(config_file, config)
    atomic_json(ROOT / 'run-config.json', config)
    full = ROOT / 'train100/results.csv'
    if full.exists():
        with full.open() as stream:
            full_records = list(csv.DictReader(stream))
    else:
        full_records = []
    if len(full_records) < 100:
        recovery = ROOT / 'recuperacion.pt'
        if restored and restored['epoch'] > 0:
            checkpoint = torch.load(recovery, map_location='cpu', weights_only=False)
            if (checkpoint.get('epoch') != restored['epoch'] - 1 or
                    checkpoint.get('optimizer') is None or
                    checkpoint['train_args']['epochs'] != 100):
                raise RuntimeError('Checkpoint incompatible con recuperación de 100 épocas.')
            state('reanudando')
            model = YOLO(str(recovery))
            model.add_callback('on_model_save', recover)
            model.add_callback('on_pretrain_routine_end', restore_runtime)
            model.train(resume=True, device=0)
        else:
            if full_records:
                raise RuntimeError('Hay épocas previas pero falta recuperacion.pt; no reiniciar.')
            if not (restored and (ROOT / 'smoke-ok.json').is_file()):
                state('prueba_tecnica')
                weights = pretrained_weights()
                smoke = YOLO(str(weights))
                smoke.train(**common, epochs=2, name='prueba', warmup_epochs=0)
                completed_epochs(ROOT / 'prueba/results.csv', 2)
                if smoke.trainer.device.type != 'cuda':
                    raise RuntimeError('Prueba técnica fuera de CUDA.')
                result = smoke.predict(next(r['origen'] for r in rows if r['particion']=='val'),
                                       device=0, imgsz=224, verbose=False)[0]
                if result.probs is None or not result.probs.data.isfinite().all():
                    raise RuntimeError('Prueba de inferencia fallida.')
                atomic_json(ROOT / 'smoke-ok.json', dict(epochs=2, inference='OK', dataset_sha256=DATASET_HASH))
                retry_io(lambda: commit_snapshot(RUN, ROOT, ['prueba/results.csv', 'prueba/args.yaml',
                    'smoke-ok.json', 'run-config.json', 'particiones.csv', 'versiones.txt'],
                    dict(epoch=0, run_id=RUN_ID, dataset_sha256=DATASET_HASH)))
            print('PRUEBA TÉCNICA SATISFACTORIA. Iniciando 100 épocas desde pesos preentrenados.',
                  flush=True)
            model = YOLO(str(pretrained_weights()))
            model.add_callback('on_model_save', recover)
            model.train(**common, epochs=100, name='train100', save_period=10)
    completed_epochs(ROOT / 'prueba/results.csv', 2)
    completed_epochs(full, 100)
    state('evaluando', epocas=100)
    model = YOLO(str(ROOT / 'train100/weights/best.pt'))
    if set(model.names.values()) != set(CLASSES):
        raise RuntimeError('Clases del modelo incorrectas.')
    sample = evaluate(model, rows)
    shutil.copy2('/content/app_gradio.py', ROOT / 'app_gradio.py')
    shutil.copy2('/content/entrenar_colab.py', ROOT / 'entrenar_colab.py')
    shutil.copy2('/content/persistencia_colab.py', ROOT / 'persistencia_colab.py')
    necessary = [ROOT / n for n in ('particiones.csv', 'versiones.txt', 'recuperacion.pt',
        'metricas_test.json', 'predicciones_test.csv', 'matriz_confusion.csv',
        'matriz_confusion.png', 'app_gradio.py', 'entrenar_colab.py', 'persistencia_colab.py',
        'runtime-state.pt', 'run-config.json', 'smoke-ok.json')]
    necessary += [ROOT / 'prueba/results.csv', ROOT / 'prueba/args.yaml']
    necessary += [p for p in (ROOT / 'train100').rglob('*')
                  if p.is_file() and (p.suffix in ('.pt', '.yaml', '.csv') or
                                      p.name == 'results.png')]
    delivery = bundle('entrega.zip', necessary)
    print('ENTREGA:', delivery, 'SHA256:', hashlib.sha256(delivery.read_bytes()).hexdigest(),
          flush=True)
    delivery_hash = copy_verified(delivery, RUN / 'entrega.zip')
    persist_json(RUN / 'entrega.json', dict(sha256=delivery_hash, run_id=RUN_ID,
                                          dataset_sha256=DATASET_HASH, epochs=100))
    state('iniciando_gradio', epocas=100)
    launch_app(sample)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if ROOT.is_dir():
            state('error', error=f'{type(exc).__name__}: {exc}')
        traceback.print_exc()
        raise
