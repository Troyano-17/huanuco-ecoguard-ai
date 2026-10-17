"""Evaluación exploratoria posterior al entrenamiento; no modifica datos/modelos."""
import json
from pathlib import Path
from artefactos import sha256
from inferencia import OnnxClassifier, accepted_label, MIN_ACCEPTANCE_SCORE

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = (
    'entrega/original/train100/weights/best.pt',
    'entrega/original/train100/weights/last.pt',
    'models/best.onnx', 'models/best.json',
)
EXPECTED = (
    '57b2194e8cfb26de44eb93960193392965e4c46be3c75f8f22c81b5a37b7ed32',
    '005ecb8bd05c6f2bfba95d3deccdc2f9c112840fea398aae07807d15c8e8d72f',
    'b90eb5240038be75cea6b1477ef23665882abad69c126c7257a5578722812eef',
    'b24374fea80eb90015ae53ceca2673188104fc46b1acd506911c1f7273d5b178',
)


def main():
    before = {name: sha256(ROOT / name) for name in PROTECTED}
    assert tuple(before.values()) == EXPECTED, 'Los artefactos protegidos cambiaron.'
    model = OnnxClassifier(ROOT / 'models/best.onnx')
    samples = sorted((ROOT / 'artifacts/test-original').rglob('*.png'))
    assert len(samples) == 23, 'Se requieren las 23 fotografías originales.'
    rows = []
    for sample in samples:
        label, scores = model.predict(sample)
        rows.append({'image': str(sample.relative_to(ROOT)), 'expected': sample.parent.name,
                     'predicted': label, 'scores': scores, 'maximum': max(scores.values()),
                     'accepted': accepted_label(scores) is not None,
                     'correct': label == sample.parent.name})
    accepted = sum(r['accepted'] for r in rows)
    correct = sum(r['accepted'] and r['correct'] for r in rows)
    report = {
        'scope': 'Exploratorio, posterior al entrenamiento sobre el mismo test original; no es una prueba independiente ni evidencia de mejora del modelo.',
        'threshold': MIN_ACCEPTANCE_SCORE,
        'historical': {'epochs': 100, 'correct': 21, 'total': 23, 'accuracy_percent': 91.3043},
        'observed': {'total': len(rows), 'accepted': accepted, 'inconclusive': len(rows)-accepted,
                     'correct_accepted': correct, 'incorrect_accepted': accepted-correct,
                     'incorrect_rejected': sum(not r['accepted'] and not r['correct'] for r in rows),
                     'coverage_percent': accepted/len(rows)*100,
                     'accuracy_accepted_percent': correct/accepted*100 if accepted else None},
        'clean_unrelated_sample': 'No se encontró una muestra local identificada y validada de escenas limpias o ajenas a las tres categorías. No se estima su tasa de rechazo.',
        'images': rows, 'sha256_before': before,
        'sha256_after': {name: sha256(ROOT / name) for name in PROTECTED},
    }
    assert report['sha256_before'] == report['sha256_after']
    output = ROOT / 'docs/evidencias/umbral-60/evaluacion.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['observed'], indent=2))
    for row in rows:
        if not row['correct']:
            print(row['image'], row['predicted'], row['maximum'], row['accepted'])


if __name__ == '__main__':
    main()
