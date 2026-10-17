"""Entrega documental nueva y conservadora: referencias a grandes originales, sin secretos."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import uuid
import zipfile
from artefactos import DATASET_SHA256, DELIVERY_SHA256, RUN_NAME, manifest, sha256, verify_manifest

ROOT = Path(__file__).resolve().parents[1]


def main():
    identity = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    folder = ROOT / 'dist' / ('academico-' + identity)
    folder.mkdir(parents=True)
    dataset, model, results, code, slides = [folder / n for n in (
        '01_DATASET_IMAGENES', '02_MODELO_ENTRENADO', '03_RESULTADOS_Y_METRICAS',
        '04_CODIGO_Y_DOCUMENTACION', '05_PRESENTACION_PPT')]
    for p in (dataset, model, results, code, slides): p.mkdir()
    def copy(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    reference = {'archivo_original': 'ecoguard-validacion.zip', 'sha256': DATASET_SHA256,
                 'ruta_local': 'ecoguard-validacion.zip', 'ruta_drive_prevista': 'HuanucoEcoGuard/datasets/' + DATASET_SHA256,
                 'originales': 165, 'unicas_experimentales': 151, 'train': 105, 'val': 23, 'test': 23,
                 'drive_comprobado_en_auditoria': False, 'nota': 'Reutilizar el respaldo original; no está duplicado en este ZIP.'}
    (dataset / 'REFERENCIA_DATASET.json').write_text(json.dumps(reference, ensure_ascii=False, indent=2))
    for p in (ROOT / 'entrega/dataset').glob('*'):
        if p.is_file() and p.suffix in {'.csv', '.json'}: copy(p, dataset / p.name)
    model_record = {'recuperado': False, 'sha256_zip_original_esperado': DELIVERY_SHA256,
                    'ruta_drive_por_comprobar': 'HuanucoEcoGuard/runs/' + RUN_NAME,
                    'nota': 'No contiene pesos. Recuperar originales y regenerar esta entrega.'}
    original = ROOT / 'entrega/entrega-original.zip'
    if original.is_file():
        from artefactos import verify_original
        verified = verify_original(ROOT / 'entrega/original', original)
        model_record.update(recuperado=True, verificacion=verified,
                            nota='Originales verificados; conservados una sola vez fuera del ZIP documental.')
    (model / 'ESTADO_MODELO.json').write_text(json.dumps(model_record, ensure_ascii=False, indent=2))
    for name in ('metricas_test_recuperadas_historial.json', 'matriz_confusion_desde_historial.csv', 'colab-final-original.txt'):
        copy(ROOT / 'entrega/evidencias' / name, results / name)
    for name in ('README.md','ecoguard.py','requirements.txt','requirements-colab.txt','requirements-production.txt',
                 'requirements-export.txt','render.yaml','.gitignore','.env.example'):
        copy(ROOT / name, code / name)
    for directory, extensions in [('scripts', {'.py'}), ('tests', {'.py'}), ('docs', {'.md', '.txt', '.json'}), ('notebooks', {'.ipynb'})]:
        for p in sorted((ROOT / directory).rglob('*')):
            if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts:
                copy(p, code / p.relative_to(ROOT))
    copy(ROOT / 'docs/PRESENTACION_INNOBEST.pptx', slides / 'PRESENTACION_INNOBEST.pptx')
    copy(ROOT / 'docs/GUION_INNOBEST_5_MIN.md', slides / 'GUION_INNOBEST_5_MIN.md')
    (folder / 'ESTADO_ENTREGA.json').write_text(json.dumps({
        'tipo': 'paquete documental académico; originales grandes referenciados',
        'modelo_recuperado': model_record['recuperado'], 'modelo_incluido': False,
        'atlas_validado': False, 'render_publicado': False, 'drive_validado': False,
        'criterio_finalizacion_cumplido': False}, ensure_ascii=False, indent=2))
    (folder / 'SHA256.json').write_text(json.dumps(manifest(folder), ensure_ascii=False, indent=2))
    count = verify_manifest(folder)
    target = folder.with_suffix('.zip')
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(folder.rglob('*')):
            if p.is_file(): archive.write(p, str(p.relative_to(folder)))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None: raise RuntimeError('Paquete académico corrupto.')
        forbidden = {'.runtime', '.env', '.git', '.aws', '.codex', '__pycache__'}
        if any(forbidden.intersection(Path(n).parts) for n in archive.namelist()):
            raise RuntimeError('Paquete contiene rutas privadas.')
    target.with_suffix('.zip.sha256').write_text(sha256(target) + '  ' + target.name + '\n')
    print(json.dumps({'paquete': str(target.relative_to(ROOT)), 'archivos_verificados': count,
                      'sha256': sha256(target), 'modelo_incluido': False}, indent=2))


if __name__ == '__main__': main()
