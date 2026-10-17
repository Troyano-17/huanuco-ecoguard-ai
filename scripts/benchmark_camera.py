"""Medición reproducible WSL/CPU. No representa el rendimiento de Render."""
import json
import platform
import resource
import statistics
import sys
import time
from pathlib import Path

from camera_analysis import CameraAnalyzer, CameraSession
from inferencia import OnnxClassifier
from PIL import Image


def rss_mib():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'): return int(line.split()[1]) / 1024


def main():
    root = Path(__file__).resolve().parents[1]
    # Incluye FastAPI + Gradio + ONNX, con un único clasificador compartido.
    from unittest.mock import patch
    model = OnnxClassifier(root / 'models/best.onnx')
    with patch('app_gradio.create_classifier', return_value=model):
        from servidor import create_server
        server = create_server()
        assert server.title == 'HUÁNUCO ECOGUARD AI'
    loaded = rss_mib()
    samples = sorted((root / 'artifacts/test-original').rglob('*.png'))
    camera = CameraAnalyzer(model, interval=0)
    session = CameraSession(); session.start()
    times, complete = [], []
    for _ in range(3):
        for sample in samples:
            with Image.open(sample) as image:
                t = time.perf_counter()
                result = camera.frame(image, session)
                complete.append((time.perf_counter() - t) * 1000)
                times.append(result['ms'])
    report = {'environment': platform.platform(), 'python': platform.python_version(),
              'frames': len(times), 'source_images': len(samples),
              'rss_loaded_mib': loaded, 'rss_after_mib': rss_mib(),
              'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
              'predict_ms_mean': statistics.mean(times), 'predict_ms_median': statistics.median(times),
              'predict_ms_p95': sorted(times)[int(.95 * (len(times)-1))],
              'frame_total_ms_mean': statistics.mean(complete),
              'frame_total_ms_p95': sorted(complete)[int(.95 * (len(complete)-1))],
              'production_imports': {'torch': 'torch' in sys.modules, 'ultralytics': 'ultralytics' in sys.modules},
              'scope': 'Proceso local WSL: FastAPI+Gradio+ONNX; 69 fotogramas, sin navegador/red/MongoDB ni servidor HTTP. No es una medición de Render.'}
    output = root / 'docs/evidencias/ux-camera/benchmark.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
