"""Exportación CPU derivada del original; publica ONNX solo tras equivalencia real."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from artefactos import DELIVERY_SHA256, sha256, verify_original
from inferencia import Classifier, CLASSES, load_image, onnx_tensor


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, default=Path('entrega/original'))
    p.add_argument('--archivo', type=Path, default=Path('entrega/entrega-original.zip'))
    p.add_argument('--imagenes', type=Path, required=True, help='Carpeta de fotografías reales con subcarpetas de las tres clases')
    p.add_argument('--salida', type=Path, default=Path('models/best.onnx'))
    args = p.parse_args()
    verified = verify_original(args.original, args.archivo)
    os.environ['ORIGINAL_ARCHIVE'] = str(args.archivo.resolve())
    weights = args.original / 'train100/weights/best.pt'
    reference = Classifier(weights)
    images = sorted(p for p in args.imagenes.rglob('*') if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'})
    if len({sha256(p) for p in images}) < 23 or not all(any(c in p.parts for p in images) for c in CLASSES):
        raise RuntimeError('Se requieren al menos 23 fotografías distintas representando las tres clases.')
    if args.salida.exists() or args.salida.with_suffix('.json').exists():
        raise RuntimeError('Destino existente; utiliza otra ruta. No se sobrescribe.')
    import onnxruntime as ort
    import numpy as np
    from ultralytics import YOLO
    records = []
    with tempfile.TemporaryDirectory() as temp:
        staged = Path(temp) / 'best.pt'
        shutil.copyfile(weights, staged)  # El exportador solo toca esta copia temporal.
        exported = Path(YOLO(str(staged), task='classify').export(format='onnx', imgsz=224,
                        batch=1, device='cpu', half=False, dynamic=False, simplify=False, opset=17))
        options = ort.SessionOptions(); options.intra_op_num_threads = 1
        session = ort.InferenceSession(str(exported), sess_options=options, providers=['CPUExecutionProvider'])
        for path in images:
            label, scores = reference.predict(path)
            start = time.perf_counter()
            values = session.run(None, {session.get_inputs()[0].name: onnx_tensor(load_image(path))})[0][0]
            expected = np.array([scores[reference.names[i]] for i in range(3)])
            error = float(np.max(np.abs(values - expected)))
            same = reference.names[int(np.argmax(values))] == label
            records.append({'image_sha256': sha256(path), 'max_abs_error': error, 'same_class': same,
                            'onnx_ms': (time.perf_counter()-start)*1000})
        passed = all(r['same_class'] and r['max_abs_error'] <= 1e-4 for r in records)
        report = {'original_archive_sha256': DELIVERY_SHA256, 'best_sha256': verified['best_sha256'],
                  'onnx_sha256': sha256(exported), 'names': reference.names, 'imgsz': 224,
                  'parity': {'passed': passed, 'images': len(records), 'tolerance': 1e-4, 'details': records}}
        if not passed:
            diagnostic = Path('docs/evidencias/paridad-fallida-' + str(time.time_ns()) + '.json')
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            diagnostic.write_text(json.dumps(report, indent=2))
            raise RuntimeError('La comparación real falló; ONNX no se incorpora a producción. Revisa ' + str(diagnostic))
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        with exported.open('rb') as src, args.salida.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        with args.salida.with_suffix('.json').open('x') as out:
            json.dump(report, out, indent=2)
    if sha256(weights) != verified['best_sha256']:
        raise RuntimeError('El original cambió durante la exportación.')
    print('Exportación y comparación real aprobadas:', args.salida)


if __name__ == '__main__':
    main()
