#!/usr/bin/env python3
"""Entrada final ECOGUARD. Ninguna acción entrena ni modifica checkpoints."""
import argparse
import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
from artefactos import (DATASET_SHA256, DELIVERY_SHA256, RUN_NAME, STORE,
                        sha256, extract_original, verify_original, manifest, verify_manifest)
ROOT = Path(__file__).resolve().parent
DELIVERY = ROOT if (ROOT / 'ESTADO_ENTREGA.json').exists() else ROOT / 'entrega'
ORIGINAL = DELIVERY / 'original'


def package():
    if ROOT != DELIVERY:
        for directory in ('scripts', 'tests', 'docs', 'notebooks'):
            (DELIVERY / directory).mkdir(exist_ok=True)
        for p in (ROOT / 'scripts').iterdir():
            if p.suffix not in ('.py', '.css', '.js'): continue
            shutil.copy2(p, DELIVERY / 'scripts' / p.name)
        for p in (ROOT / 'tests').glob('test_*.py'):
            shutil.copy2(p, DELIVERY / 'tests' / p.name)
        for name in ('ecoguard.py', 'requirements.txt', 'README.md'):
            shutil.copy2(ROOT / name, DELIVERY / name)
        for name in ('INFORME_FINAL.md', 'AUDITORIA_FINAL.md', 'GUION_EXPOSICION.md'):
            shutil.copy2(ROOT / 'docs' / name, DELIVERY / 'docs' / name)
        shutil.copy2(ROOT / 'notebooks/Demostracion_EcoGuard.ipynb', DELIVERY / 'notebooks/Demostracion_EcoGuard.ipynb')
    complete = False
    checked = None
    if ORIGINAL.exists():
        checked = verify_original(ORIGINAL, DELIVERY / 'entrega-original.zip')
        complete = True
    state = {'completo': complete, 'entrenamiento': 'Completado en Colab; evidenciado en historial original',
             'originales_recuperados': complete, 'verificacion_originales': checked,
             'faltantes': [] if complete else ['best.pt', 'last.pt', 'results.csv original de 100 épocas',
                 'args.yaml', 'run-config.json', 'versiones.txt', 'particiones.csv', 'predicciones_test.csv',
                 'matriz y gráficas originales', 'entrega.zip original'],
             'sha256_entrega_original_reportado_colab': DELIVERY_SHA256,
             'nota': 'Las métricas recuperadas del historial no sustituyen los archivos originales pendientes.'}
    (DELIVERY / 'ESTADO_ENTREGA.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n')
    (DELIVERY / 'SHA256.json').write_text(json.dumps(manifest(DELIVERY), ensure_ascii=False, indent=2)+'\n')
    verify_manifest(DELIVERY)
    output = (ROOT.parent if ROOT == DELIVERY else ROOT) / 'dist'
    output.mkdir(exist_ok=True)
    target = output / ('huanuco-ecoguard-' + sha256(DELIVERY / 'SHA256.json')[:12] + '.zip')
    if not target.exists():
        with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(DELIVERY.rglob('*')):
                if p.is_file(): z.write(p, 'entrega/' + str(p.relative_to(DELIVERY)))
    if complete:
        print('Entrega completa verificada.')
    else:
        print('Entrega PARCIAL: faltan originales. Ejecuta python3 ecoguard.py recuperar desde WSL autenticado.')
    print('Paquete:', target)
    checksum = sha256(target)
    target.with_suffix('.zip.sha256').write_text(checksum + '  ' + target.name + '\n')
    print('SHA256:', checksum)


def recover(local_archive=None):
    archive = DELIVERY / 'entrega-original.zip'
    DELIVERY.mkdir(exist_ok=True)
    if local_archive:
        source = Path(local_archive).expanduser().resolve()
        if not source.is_file() or sha256(source) != DELIVERY_SHA256:
            raise RuntimeError('El archivo local no coincide con el SHA256 original; no se copia ni extrae.')
        if not archive.exists():
            with source.open('rb') as src, archive.open('xb') as dst:
                shutil.copyfileobj(src, dst)
    if archive.exists():
        if sha256(archive) != DELIVERY_SHA256:
            raise RuntimeError('ZIP local diferente; se conserva y se detiene la recuperación.')
    else:
        raise RuntimeError('No hay ZIP original local. Recupera desde Drive con scripts/recuperar_drive.py '
                           'o descarga entrega.zip en el navegador y ejecuta: '
                           'python3 ecoguard.py recuperar --archivo /ruta/entrega.zip. No requiere Colab ni GPU.')
    extract_original(archive, ORIGINAL)
    print(json.dumps(verify_original(ORIGINAL, DELIVERY / 'entrega-original.zip'), ensure_ascii=False, indent=2))
    package()


def remote_demo(action):
    from entrenar_165_wsl import remote
    payload = {name: base64.b64encode((ROOT / 'scripts' / name).read_bytes()).decode()
               for name in ('app_gradio.py', 'camera_analysis.py', 'ecoguard_ui.css', 'camera_browser.js',
                            'inferencia.py', 'mongo_store.py', 'artefactos.py', 'demo_colab.py')}
    payload['test_app_real.py'] = base64.b64encode((ROOT / 'tests/test_app_real.py').read_bytes()).decode()
    # Cada versión usa un directorio distinto; no toca código ni procesos del entrenador.
    import hashlib
    version = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:12]
    code = ('require_drive()\nimport base64\n'
            f'folder = STORE / "demostracion" / {version!r}\nfolder.mkdir(parents=True, exist_ok=True)\n'
            f'payload = {payload!r}\n'
            'for name, value in payload.items():\n'
            '    path = folder / name\n    raw = base64.b64decode(value)\n'
            '    if path.exists() and path.read_bytes() != raw: raise RuntimeError("Código existente diferente")\n'
            '    if not path.exists(): path.write_bytes(raw)\n'
            'import subprocess, sys\n'
            f'p = subprocess.run([sys.executable, str(folder / "demo_colab.py"), {action!r}], capture_output=True, text=True, timeout=100)\n'
            'if p.returncode: raise RuntimeError(p.stdout[-1000:] + p.stderr[-1000:])\n'
            'result = {"salida": p.stdout}\n')
    result = remote(code, retry=False)
    print(result['salida'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--en-vivo', action='store_true', help='Con demo, inicia también la aplicación en Colab')
    parser.add_argument('--archivo', type=Path, help='ZIP original descargado desde Drive; se verifica antes de copiar')
    parser.add_argument('action', choices=['estado','verificar','recuperar','app','pruebas','pruebas-colab','evidencias','demo','empaquetar'])
    args = parser.parse_args()
    if args.action == 'estado':
        state = json.loads((DELIVERY / 'ESTADO_ENTREGA.json').read_text()) if (DELIVERY / 'ESTADO_ENTREGA.json').exists() else {'completo':False}
        print(json.dumps(state,ensure_ascii=False,indent=2))
        print('best.pt:', ORIGINAL / 'train100/weights/best.pt', '(presente)' if (ORIGINAL / 'train100/weights/best.pt').is_file() else '(pendiente de descarga)')
    elif args.action == 'verificar':
        print('Archivos con SHA256 correcto:', verify_manifest(DELIVERY))
        backup = ROOT / 'ecoguard-validacion.zip'
        if backup.exists() and sha256(backup) != DATASET_SHA256: raise RuntimeError('El respaldo del dataset difiere del original.')
        print('Respaldo dataset:', 'SHA256 correcto' if backup.exists() else 'No incluido en este paquete; conservado en Drive')
        if not ORIGINAL.exists(): raise RuntimeError('Integridad documental correcta; entrega incompleta por originales pendientes.')
        if sha256(DELIVERY / 'entrega-original.zip') != DELIVERY_SHA256: raise RuntimeError('ZIP original modificado.')
        print(json.dumps(verify_original(ORIGINAL, DELIVERY / 'entrega-original.zip'),ensure_ascii=False,indent=2))
    elif args.action == 'recuperar': recover(args.archivo)
    elif args.action == 'app':
        raise SystemExit(subprocess.call([sys.executable, str(ROOT / 'scripts/servidor.py')], cwd=ROOT))
    elif args.action == 'pruebas-colab': remote_demo('test')
    elif args.action == 'pruebas':
        raise SystemExit(subprocess.call([sys.executable,'-m','unittest','discover','-s',str(ROOT / 'tests'),'-v'],cwd=ROOT))
    elif args.action == 'empaquetar': package()
    elif args.action == 'evidencias':
        print((DELIVERY / 'evidencias/metricas_test_recuperadas_historial.json').read_text())
        print('Salida original:', DELIVERY / 'evidencias/colab-final-original.txt')
        print('Evidencias adicionales originales:', ORIGINAL)
    elif args.action == 'demo':
        print((ROOT / 'docs/GUION_EXPOSICION.md').read_text())
        print('\nAcceso a la aplicación: python3 ecoguard.py app')
        if args.en_vivo: remote_demo('app')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print('ECOGUARD:', str(exc), file=sys.stderr)
        sys.exit(1)
