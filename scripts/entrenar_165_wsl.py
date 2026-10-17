"""WSL controla bytes y metadatos; preparación e inferencia se ejecutan en Colab."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path('/home/troyano/proyectos/gpu-t4/.venv/bin/python')
CLI = [str(PYTHON), str(ROOT / 'scripts/colab_workspace.py')]
SESSION = ['-s', 'laboratorio-t4']
REQUEST_TIMEOUT = 180
PART_SIZE = 1024 * 1024


class TransportError(RuntimeError):
    pass


def transient(output):
    return bool(re.search(r'NameResolutionError|name resolution|Failed to resolve|SSLEOFError|'
                          r'SSLError|ConnectionError|Timeout|timed out|ConnectionReset|'
                          r'\b(?:408|429|500|502|503|504)\b', output, re.I))


def cli(*args):
    try:
        result = subprocess.run([*CLI, *args], cwd=ROOT, text=True, capture_output=True,
                                env={**os.environ, 'REQUEST_TIMEOUT': '180'}, timeout=210)
    except subprocess.TimeoutExpired:
        raise TransportError('Timeout de transporte (210 s); resultado remoto ambiguo') from None
    output = result.stdout + result.stderr
    if result.returncode or 'Traceback (most recent call last)' in output:
        # No volcar trazas de requests: pueden contener credenciales de la sesión.
        if transient(output):
            raise TransportError('Error transitorio DNS/TLS/HTTP; operación remota por comprobar')
        recovery = re.search(r'--recover-boot ([a-f0-9-]+)', output)
        if recovery:
            raise RuntimeError('Propietario de otro runtime. Confirma que terminó y usa --recover-boot ' + recovery[1])
        if 'Drive no está montado' in output:
            raise RuntimeError('Drive no está montado. En WSL: colab drivemount -s laboratorio-t4 /content/drive')
        raise RuntimeError('CLI falló; comprueba sesión/autenticación en WSL (sin reintento automático)')
    return output


def retry_read(operation, attempts=4, sleep=time.sleep):
    for attempt in range(attempts):
        try:
            return operation()
        except TransportError:
            if attempt + 1 == attempts:
                raise
            delay = min(16, 2 ** attempt) + random.random()
            print(f'RED: reintento {attempt+1}/{attempts-1}; backoff {delay:.1f}s', flush=True)
            sleep(delay)


def remote(code, *, retry=True, env=()):
    # Biblioteca enviada como texto: no depende de que /content haya sobrevivido.
    library = (ROOT / 'scripts/persistencia_colab.py').read_text()
    import textwrap
    script = library + ('\nimport types, sys\n'
                        'module = types.ModuleType("persistencia_colab")\n'
                        'module.__dict__.update(globals())\n'
                        'sys.modules["persistencia_colab"] = module\ntry:\n') + textwrap.indent(
        code + "\nprint('ECOGUARD_RESPUESTA=' + json.dumps(result, ensure_ascii=False), flush=True)", '    ')
    script += ("\nexcept Exception as exc:\n"
               "    print('ECOGUARD_ERROR=' + json.dumps({'tipo': type(exc).__name__, 'error': str(exc)}), flush=True)\n")
    cache = ROOT / '.runtime'
    cache.mkdir(exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', suffix='.py', dir=cache) as file:
        file.write(script)
        file.flush()
        args = ['exec', *SESSION, '-f', file.name, '--timeout', '180']
        for key, value in env:
            args.extend(['--env', f'{key}={value}'])
        def operation():
            output = cli(*args)
            lines = output.splitlines()
            errors = [line for line in lines if line.startswith('ECOGUARD_ERROR=')]
            if errors:
                error = json.loads(errors[-1].split('=', 1)[1])
                raise RuntimeError('Remoto: ' + error['tipo'] + ': ' + error['error'])
            responses = [line for line in lines if line.startswith('ECOGUARD_RESPUESTA=')]
            if not responses:
                if transient(output):
                    raise TransportError('Respuesta remota ambigua por fallo de red')
                raise RuntimeError('Respuesta remota incompleta; no se confirma la operación')
            for line in lines:
                if not line.startswith(('ECOGUARD_RESPUESTA=', '[colab]')):
                    print(line, flush=True)
            return json.loads(responses[-1].split('=', 1)[1])
        return retry_read(operation) if retry else operation()


def transport_manifest(path):
    digest = hashlib.sha256()
    parts = []
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(PART_SIZE), b''):
            digest.update(block)
            parts.append(dict(size=len(block), sha256=hashlib.sha256(block).hexdigest()))
    return dict(name=Path(path).name, size=Path(path).stat().st_size,
                sha256=digest.hexdigest(), part_size=PART_SIZE, parts=parts)


def transfer(path, manifest):
    prefix = 'require_drive()\nm = ' + repr(manifest) + '\n'
    if remote(prefix + 'result = archive_valid(m)'):
        remote(prefix + 'result = str(finish_archive(m))')
        return
    present = remote(prefix + 'result = [valid_part(m, i) for i in range(len(m["parts"]))]')
    with Path(path).open('rb') as stream:
        for index, expected in enumerate(manifest['parts']):
            block = stream.read(expected['size'])
            if present[index]:
                print(f'FRAGMENTO {index+1}/{len(present)}: reutilizado SHA256 válido', flush=True)
                continue
            incoming = f'/content/ecoguard-{manifest["sha256"]}-{index:05d}.part'
            # Cada intento comienza comprobando Drive y el staging temporal.
            for attempt in range(4):
                try:
                    if remote(prefix + f'result = valid_part(m, {index})'):
                        break
                    staged = remote(prefix + f'p = Path({incoming!r})\nresult = p.is_file() and sha256(p) == {expected["sha256"]!r}')
                    if not staged:
                        with tempfile.NamedTemporaryFile(dir=ROOT / '.runtime') as fragment:
                            fragment.write(block)
                            fragment.flush()
                            cli('upload', *SESSION, fragment.name, incoming)
                    remote(prefix + f'accept_part(m, {index}, {incoming!r})\nresult = valid_part(m, {index})')
                    break
                except TransportError:
                    if attempt == 3:
                        raise
                    print(f'FRAGMENTO {index+1}: respuesta ambigua; comprobar antes de reenviar', flush=True)
                    time.sleep(2 ** attempt + random.random())
            else:
                raise RuntimeError('Fragmento sin confirmar')
            print(f'FRAGMENTO {index+1}/{len(present)}: persistido y verificado', flush=True)
    result = remote(prefix + 'result = str(finish_archive(m))')
    print('DATASET PERSISTENTE:', result, 'SHA256:', manifest['sha256'], flush=True)


def status(digest, action='status', recover_boot=None):
    source = (ROOT / 'scripts/control_entrenamiento_colab.py').read_text()
    # Ejecutar main en un namespace aislado sin depender de módulos subidos.
    code = 'ns = {"__name__": "ecoguard_control"}\nexec(compile(' + repr(source) + ", 'control_entrenamiento_colab.py', 'exec'), ns)\nresult = ns['main']()"
    env = [('ECOGUARD_DATASET_SHA256', digest), ('ECOGUARD_ACTION', action),
           ('ECOGUARD_RECOVER_BOOT', recover_boot or ''), ('ECOGUARD_LOG_OFFSET', '-1')]
    return remote(code, retry=action == 'status', env=env)


def install_code():
    payloads = {name: base64.b64encode((ROOT / 'scripts' / name).read_bytes()).decode()
                for name in ('persistencia_colab.py', 'entrenar_colab.py', 'app_gradio.py')}
    code = ('import base64, fcntl\n'
            'Path("/content/ecoguard-entrenamiento").mkdir(exist_ok=True)\n'
            'with Path("/content/ecoguard-entrenamiento/worker.lock").open("a") as lock:\n'
            '    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
            '    payloads = ' + repr(payloads) + '\n    result = {}\n'
            '    for name, encoded in payloads.items():\n'
            '        p = Path("/content") / name\n'
            '        payload = base64.b64decode(encoded)\n'
            '        digest = hashlib.sha256(payload).hexdigest()\n'
            '        if not p.is_file() or sha256(p) != digest:\n'
            '            temporary = p.with_suffix(".uploading")\n'
            '            temporary.write_bytes(payload)\n            temporary.replace(p)\n'
            '        result[name] = sha256(p)\n'
            '    atomic_json(Path("/content/ecoguard-entrenamiento/deployment.json"), result)')
    print('CÓDIGO VERIFICADO:', remote(code), flush=True)


def storage_selftest(digest):
    """Dos peticiones independientes; simula pérdida de /content, sin CUDA."""
    import uuid
    token = uuid.uuid4().hex
    folder = '/content/drive/MyDrive/HuanucoEcoGuard/pruebas/' + token
    code = ('require_drive()\nimport tempfile\n'
            f'run = Path({folder!r})\n'
            'with tempfile.TemporaryDirectory(dir="/content") as temp:\n'
            '    local = Path(temp)\n'
            '    (local / "checkpoint-sintetico.txt").write_text("epoch=37; optimizer=sintetico")\n'
            '    commit_snapshot(run, local, ["checkpoint-sintetico.txt"], '
            f'{{"epoch": 37, "run_id": {token!r}, "dataset_sha256": {digest!r}}})\n'
            'result = {"prueba": "snapshot persistido; almacenamiento temporal eliminado"}')
    print('AUTOPRUEBA REMOTA 1:', remote(code), flush=True)
    code = ('require_drive()\nimport tempfile\n'
            f'run = Path({folder!r})\n'
            'with tempfile.TemporaryDirectory(dir="/content") as temp:\n'
            f'    recovered = restore_snapshot(run, Path(temp), {digest!r})\n'
            '    assert recovered["epoch"] == 37\n'
            '    assert (Path(temp) / "checkpoint-sintetico.txt").read_text().startswith("epoch=37")\n'
            'atomic_json(STORE / "datasets" / ' + repr(digest) + ' / "arquitectura-validada.json", '
            f'{{"dataset_sha256": {digest!r}, "test": "reconexion y restauracion sintética", "at": time.time()}})\n'
            'shutil.rmtree(run)\nresult = {"prueba": "segunda conexión recupera época 37", "gpu": "no utilizada"}')
    print('AUTOPRUEBA REMOTA 2:', remote(code), flush=True)


def verify_delivery(output):
    """Verificar evidencias descargadas; no cargar modelos ni fotografías."""
    import csv
    import math
    for name, count in (('prueba/results.csv', 2), ('train100/results.csv', 100)):
        with (output / name).open() as stream:
            rows = list(csv.DictReader(stream))
        if [int(r['epoch'].strip()) for r in rows] != list(range(1, count + 1)):
            raise RuntimeError(f'No se verificaron las {count} épocas en {name}.')
        if not all(math.isfinite(float(v)) for r in rows for v in r.values()):
            raise RuntimeError('Métricas descargadas no finitas.')
    for name in ('train100/weights/best.pt', 'train100/weights/last.pt',
                 'metricas_test.json', 'particiones.csv', 'predicciones_test.csv'):
        if not (output / name).is_file() or not (output / name).stat().st_size:
            raise RuntimeError('Falta un resultado requerido: ' + name)
    print('Descarga verificada: prueba de 2 épocas, entrenamiento de 100 y pesos.', flush=True)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'start', 'status', 'download'), nargs='?', default='prepare')
    parser.add_argument('--recover-boot', help='Boot ID anterior, SOLO después de confirmar que su máquina terminó')
    args = parser.parse_args()
    manifest = transport_manifest(ROOT / 'ecoguard-validacion.zip')
    print('DATASET LOCAL SHA256:', manifest['sha256'], 'bytes:', manifest['size'],
          'fragmentos:', len(manifest['parts']), flush=True)
    print('REQUEST_TIMEOUT=180; WSL solo bytes/metadatos; no se crea una sesión.', flush=True)
    remote('require_drive()\nresult = {"drive": str(STORE), "lectura_escritura": "OK"}')
    if args.action in ('prepare', 'run'):
        existing = status(manifest['sha256'])
        if existing['vivo']:
            print('TRABAJADOR EXISTENTE:', existing, flush=True)
            return
        transfer(ROOT / 'ecoguard-validacion.zip', manifest)
        storage_selftest(manifest['sha256'])
        install_code()
        print('Persistencia, SHA256 remoto y recuperación de almacenamiento validados.', flush=True)
        if args.action == 'prepare':
            return
    if args.action == 'status':
        print('ESTADO:', status(manifest['sha256']), flush=True)
        return
    if args.action == 'download':
        current = status(manifest['sha256'])
        run = current['run_dir']
        metadata = remote(f'result = json.loads((Path({run!r}) / "entrega.json").read_text())')
        output = ROOT / 'models/entrega-colab'
        output.mkdir(parents=True, exist_ok=True)
        target = output / 'entrega.zip'
        retry_read(lambda: cli('download', *SESSION, run + '/entrega.zip', str(target.with_suffix('.partial'))))
        partial = target.with_suffix('.partial')
        if hashlib.sha256(partial.read_bytes()).hexdigest() != metadata['sha256']:
            raise RuntimeError('Entrega descargada no coincide con SHA256 remoto')
        partial.replace(target)
        import zipfile
        with zipfile.ZipFile(target) as archive:
            for entry in archive.infolist():
                if not (output / entry.filename).resolve().is_relative_to(output.resolve()):
                    raise RuntimeError('Ruta insegura en entrega')
            archive.extractall(output)
        verify_delivery(output)
        return
    current = status(manifest['sha256'])
    if current['vivo']:
        print('TRABAJADOR EXISTENTE:', current, flush=True)
        return
    # No instalar ni lanzar sin SHA completo persistente.
    prefix = 'require_drive()\nm = ' + repr(manifest) + '\n'
    if not remote(prefix + 'result = archive_valid(m)'):
        raise RuntimeError('Primero ejecuta prepare; dataset persistente aún no verificado')
    if not remote(prefix + 'result = (dataset_dir(m) / "arquitectura-validada.json").is_file()'):
        raise RuntimeError('Primero ejecuta prepare; falta autoprueba remota de almacenamiento')
    install_code()
    try:
        current = status(manifest['sha256'], 'start', args.recover_boot)
    except TransportError:
        print('START ambiguo: consultando estado, sin repetir el lanzamiento.', flush=True)
        current = status(manifest['sha256'])
        if not current['vivo']:
            raise RuntimeError('No se confirmó el lanzamiento. Consulta status antes de iniciar otra vez')
    print('ESTADO:', current, flush=True)
    print('Trabajador autónomo. Puedes cerrar WSL. Consulta: python scripts/entrenar_165_wsl.py status', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print('FASE BLOQUEADA:', exc, file=sys.stderr, flush=True)
        sys.exit(1)
