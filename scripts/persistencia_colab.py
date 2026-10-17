"""Almacenamiento verificado; biblioteca estándar, sin CUDA ni imágenes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid


def retry_io(operation, attempts=4):
    """Solo para copias y publicaciones idempotentes en Drive."""
    for attempt in range(attempts):
        try:
            return operation()
        except OSError:
            if attempt + 1 == attempts:
                raise
            delay = 2 ** attempt
            print(f'DRIVE: error de E/S, reintento {attempt+1}/{attempts-1} en {delay}s', flush=True)
            time.sleep(delay)

DRIVE = Path('/content/drive')
STORE = DRIVE / 'MyDrive/HuanucoEcoGuard'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def require_drive():
    if not DRIVE.is_mount() or not (DRIVE / 'MyDrive').is_dir():
        raise RuntimeError('Drive no está montado. Ejecuta: colab drivemount -s laboratorio-t4 /content/drive')
    STORE.mkdir(parents=True, exist_ok=True)
    probe = STORE / ('.prueba-' + uuid.uuid4().hex)
    value = uuid.uuid4().hex
    probe.write_text(value)
    if probe.read_text() != value:
        raise RuntimeError('Drive falló la prueba de escritura/lectura.')
    probe.unlink()
    return STORE


def dataset_dir(manifest):
    digest = manifest['sha256']
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('SHA256 inválido')
    if manifest['size'] <= 0 or sum(p['size'] for p in manifest['parts']) != manifest['size']:
        raise ValueError('Tamaños de fragmentos inválidos')
    folder = STORE / 'datasets' / digest
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def part_path(manifest, index):
    return dataset_dir(manifest) / 'parts' / f'{index:05d}.part'


def valid_part(manifest, index):
    path = part_path(manifest, index)
    expected = manifest['parts'][index]
    return (path.is_file() and path.stat().st_size == expected['size'] and
            sha256(path) == expected['sha256'])


def accept_part(manifest, index, incoming):
    """Una respuesta perdida se resuelve consultando valid_part antes de reenviar."""
    if valid_part(manifest, index):
        return
    expected = manifest['parts'][index]
    incoming = Path(incoming)
    if incoming.stat().st_size != expected['size'] or sha256(incoming) != expected['sha256']:
        raise RuntimeError('Fragmento de transporte corrupto')
    target = part_path(manifest, index)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    shutil.copyfile(incoming, temporary)
    if sha256(temporary) != expected['sha256']:
        raise RuntimeError('Fragmento corrupto al persistir en Drive')
    temporary.replace(target)
    incoming.unlink(missing_ok=True)


def archive_valid(manifest):
    path = dataset_dir(manifest) / 'ecoguard-validacion.zip'
    return (path.is_file() and path.stat().st_size == manifest['size'] and
            sha256(path) == manifest['sha256'])


def finish_archive(manifest):
    folder = dataset_dir(manifest)
    target = folder / 'ecoguard-validacion.zip'
    if not archive_valid(manifest):
        temporary = target.with_suffix('.assembling')
        with temporary.open('wb') as output:
            for index in range(len(manifest['parts'])):
                if not valid_part(manifest, index):
                    raise RuntimeError(f'Fragmento {index} ausente o corrupto')
                with part_path(manifest, index).open('rb') as source:
                    shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        if sha256(temporary) != manifest['sha256']:
            raise RuntimeError('SHA256 del respaldo restaurado no coincide')
        temporary.replace(target)
    atomic_json(folder / 'manifest-transporte.json', manifest)
    print('RESPALDO DRIVE VERIFICADO SHA256:', sha256(target), flush=True)
    return target


def copy_verified(source, target):
    source, target = Path(source), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.copying')
    digest = sha256(source)
    shutil.copyfile(source, temporary)
    if sha256(temporary) != digest:
        raise RuntimeError('Copia corrupta: ' + str(target))
    temporary.replace(target)
    return digest


def commit_snapshot(run, local, files, metadata):
    """Generaciones inmutables; COMMITTED se publica después de verificar todos los bytes."""
    generation = Path(run) / 'checkpoints' / f"{metadata['epoch']:03d}-{uuid.uuid4().hex}"
    generation.mkdir(parents=True)
    hashes = {}
    for relative in files:
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Ruta de snapshot insegura')
        hashes[str(relative)] = copy_verified(Path(local) / relative, generation / relative)
    record = dict(metadata, files=hashes, committed_at=time.time())
    atomic_json(generation / 'COMMITTED.json', record)
    if valid_snapshot(generation, metadata['dataset_sha256']) is None:
        raise RuntimeError('Snapshot no supera verificación posterior')
    print('CHECKPOINT PERSISTENTE:', generation.name, 'época:', metadata['epoch'], flush=True)
    return generation


def valid_snapshot(path, dataset_hash):
    try:
        record = json.loads((path / 'COMMITTED.json').read_text())
        if record['dataset_sha256'] != dataset_hash or not record['files']:
            return None
        for name, digest in record['files'].items():
            target = path / name
            if not target.resolve().is_relative_to(path.resolve()) or sha256(target) != digest:
                return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def latest_snapshot(run, dataset_hash):
    candidates = []
    had_training = False
    for path in (Path(run) / 'checkpoints').glob('*'):
        if (path / 'COMMITTED.json').is_file():
            try:
                had_training |= int(path.name.split('-', 1)[0]) > 0
            except ValueError:
                had_training = True
        record = valid_snapshot(path, dataset_hash)
        if record is not None:
            candidates.append((record['epoch'], record['committed_at'], path, record))
        else:
            print('CHECKPOINT IGNORADO (incompleto/corrupto/dataset distinto):', path.name, flush=True)
    if candidates:
        _, _, path, record = max(candidates)
        if had_training and record['epoch'] == 0:
            raise RuntimeError('Hay entrenamiento previo, pero solo es recuperable la prueba técnica; no reiniciar 100 épocas.')
        return path, record
    if any((Path(run) / 'checkpoints').glob('*/COMMITTED.json')):
        raise RuntimeError('Existen checkpoints comprometidos pero ninguno es válido; no reiniciar.')
    return None


def restore_snapshot(run, local, dataset_hash):
    latest = latest_snapshot(run, dataset_hash)
    if latest:
        path, record = latest
        for name in record['files']:
            copy_verified(path / name, Path(local) / name)
        print('RECUPERACIÓN VERIFICADA:', record['run_id'], 'época:', record['epoch'], flush=True)
        return record
    return None


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def claim_owner(run, recover_boot=None):
    """Llamar bajo flock local. Nunca robar un dueño por expirar su heartbeat."""
    path = Path(run) / 'owner.json'
    guard = Path(run) / 'owner.guard'
    try:
        guard.mkdir()
    except FileExistsError:
        if not path.exists():
            raise RuntimeError('Reclamación de propietario incompleta; inspeccionar owner.guard antes de recuperar.')
    if path.exists():
        owner = json.loads(path.read_text())
        if owner['boot_id'] != boot_id() and recover_boot != owner['boot_id']:
            raise RuntimeError('Otro runtime posee la ejecución. Confirma que terminó y usa '
                               '--recover-boot ' + owner['boot_id'])
    owner = dict(boot_id=boot_id(), claimed_at=time.time())
    atomic_json(path, owner)
    if json.loads(path.read_text()) != owner:
        raise RuntimeError('Conflicto de propiedad remota; no lanzar trabajador')
    return owner
