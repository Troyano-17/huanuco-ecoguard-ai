"""Restaurar y demostrar el modelo terminado desde Drive; nunca entrena."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from artefactos import STORE, RUN_NAME, DELIVERY_SHA256, sha256, extract_original, verify_original

WORK = Path('/content/ecoguard-demo')


def prepare():
    if not Path('/content').is_dir() or importlib.util.find_spec('google.colab') is None:
        raise RuntimeError('Ejecuta este programa en Google Colab.')
    if not Path('/content/drive').is_mount():
        raise RuntimeError('Monta Google Drive en /content/drive antes de continuar.')
    archive = STORE / 'runs' / RUN_NAME / 'entrega.zip'
    if not archive.is_file() or sha256(archive) != DELIVERY_SHA256:
        raise RuntimeError('No se encuentra la entrega original con SHA256 correcto en Drive.')
    WORK.mkdir(exist_ok=True)
    original = WORK / 'original'
    extract_original(archive, original)
    checked = verify_original(original, archive)
    print(json.dumps(checked, ensure_ascii=False, indent=2), flush=True)
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['app', 'test', 'prepare'], default='prepare', nargs='?')
    args = parser.parse_args()
    original = prepare()
    weights = original / 'train100/weights/best.pt'
    if args.action == 'prepare': return
    folder = Path(__file__).resolve().parent
    if args.action == 'test':
        env = {**os.environ, 'ECOGUARD_REAL_TESTS':'1', 'ECOGUARD_WEIGHTS': str(weights)}
        test_file = folder / 'test_app_real.py'
        if not test_file.exists(): test_file = folder.parent / 'tests/test_app_real.py'
        subprocess.run([sys.executable, str(test_file)], env=env, check=True)
        return
    import fcntl
    with (WORK / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = WORK / 'app-status.json'
        pidfile = WORK / 'app-pid.json'
        if pidfile.exists():
            record = json.loads(pidfile.read_text())
            pid = record['pid']
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                if record['code'] != str(folder):
                    raise RuntimeError('Hay una demostración de otra versión activa. Cierra solo ese proceso antes de cambiar de versión.')
                if status.exists():
                    print('Aplicación ya activa:', status.read_text())
                    return
                raise RuntimeError('La aplicación sigue iniciando; consulta nuevamente sin duplicar procesos.')
        status.unlink(missing_ok=True)
        with (WORK / 'app.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, str(folder / 'app_gradio.py'), '--weights', str(weights),
                                        '--share', '--status-file', str(status)], stdout=log, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
        pidfile.write_text(json.dumps({'pid': process.pid, 'code': str(folder)}))
        for _ in range(45):
            if status.exists():
                data = json.loads(status.read_text())
                if not data.get('url'): raise RuntimeError('Servidor iniciado, pero no se obtuvo enlace temporal. Usa el notebook con interfaz integrada.')
                print('Abre en el navegador de Linux:', data['url'])
                return
            if process.poll() is not None:
                raise RuntimeError('La aplicación no pudo iniciar. Revisa /content/ecoguard-demo/app.log e instala requirements.txt en Colab.')
            time.sleep(1)
        raise RuntimeError('Inicio todavía pendiente; consulta otra vez. No se ha lanzado entrenamiento.')


if __name__ == '__main__':
    main()
