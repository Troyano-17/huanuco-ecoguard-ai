"""Control remoto sin bucle WSL; ejecutar mediante colab exec."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    if not Path('/content').is_dir() or importlib.util.find_spec('google.colab') is None:
        raise RuntimeError('Este control solo se ejecuta en Colab.')
    sys.path.insert(0, '/content')
    from persistencia_colab import require_drive, STORE, atomic_json, claim_owner
    require_drive()
    digest = os.environ['ECOGUARD_DATASET_SHA256']
    run = STORE / 'runs' / ('train100-' + digest)
    run.mkdir(parents=True, exist_ok=True)
    root = Path('/content/ecoguard-entrenamiento')
    root.mkdir(exist_ok=True)
    lock = (root / 'worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        alive = False
    except BlockingIOError:
        alive = True
    action = os.environ.get('ECOGUARD_ACTION', 'status')
    if action not in ('start', 'status'):
        raise ValueError('Acción desconocida')
    if action == 'start' and not alive:
        deployment = json.loads((root / 'deployment.json').read_text())
        from persistencia_colab import sha256
        if any(sha256(Path('/content') / name) != digest for name, digest in deployment.items()):
            raise RuntimeError('Código remoto incompleto o modificado; ejecutar prepare')
        archive = STORE / 'datasets' / digest / 'ecoguard-validacion.zip'
        if not archive.is_file() or sha256(archive) != digest:
            raise RuntimeError('Falta respaldo persistente con SHA256 válido; no entrenar')
        if not (archive.parent / 'arquitectura-validada.json').is_file():
            raise RuntimeError('Falta prueba remota de persistencia; no entrenar')
        claim_owner(run, os.environ.get('ECOGUARD_RECOVER_BOOT'))
        atomic_json(run / 'estado.json', dict(fase='iniciando', dataset_sha256=digest))
        env = dict(os.environ, ECOGUARD_LOCK_FD=str(lock.fileno()), REQUEST_TIMEOUT='180')
        with (run / 'terminal.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-u', '/content/entrenar_colab.py'],
                                       cwd='/content', stdout=log, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, start_new_session=True,
                                       pass_fds=(lock.fileno(),), env=env)
        atomic_json(run / 'worker.json', {'pid': process.pid})
        alive = True
    lock.close()
    statefile = run / 'estado.json'
    status = json.loads(statefile.read_text()) if statefile.exists() else {'fase': 'pendiente'}
    offset = int(os.environ.get('ECOGUARD_LOG_OFFSET', '-1'))
    logpath = run / 'terminal.log'
    if logpath.exists():
        if offset < 0:
            offset = max(0, logpath.stat().st_size - 128000)
        with logpath.open('rb') as log:
            if offset > logpath.stat().st_size:
                offset = 0
            log.seek(offset)
            payload = log.read(128000)
            offset = log.tell()
        print(payload.decode('utf-8', errors='replace'), end='')
    else:
        offset = 0
    owner = run / 'owner.json'
    status.update(vivo=alive, offset=offset, run_dir=str(run),
                  owner=json.loads(owner.read_text()) if owner.exists() else None,
                  entrega=(run / 'entrega.zip').is_file())
    print('\nECOGUARD_ESTADO=' + json.dumps(status, ensure_ascii=False), flush=True)
    return status


if __name__ == '__main__':
    main()
