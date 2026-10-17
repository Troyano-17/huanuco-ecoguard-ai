"""Pruebas de metadatos y guardas; no procesan imágenes ni importan modelos."""
import importlib.util
import csv
import json
import runpy
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/entrenar_colab.py'
spec = importlib.util.spec_from_file_location('remote_training', SCRIPT)
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


class RemoteTrainingTests(unittest.TestCase):
    def test_downloaded_delivery_requires_all_100_epochs(self):
        spec = importlib.util.spec_from_file_location('wsl_training', SCRIPT.with_name('entrenar_165_wsl.py'))
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, count in (('prueba/results.csv', 2), ('train100/results.csv', 100)):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('epoch,loss\n' + ''.join(f'{i},0.5\n' for i in range(1, count+1)))
            for name in ('train100/weights/best.pt', 'train100/weights/last.pt',
                         'metricas_test.json', 'particiones.csv', 'predicciones_test.csv'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('test metadata placeholder')
            client.verify_delivery(root)
            path = root / 'train100/results.csv'
            path.write_text(path.read_text().rsplit('100,', 1)[0])
            with self.assertRaisesRegex(RuntimeError, '100 épocas'):
                client.verify_delivery(root)

    def test_manifest_paths_are_adapted_without_changing_original(self):
        # Archivos vacíos de prueba: solo metadatos, ninguna fotografía procesada.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'revision/agua_contaminada'
            folder.mkdir(parents=True)
            rows = []
            for i in range(165):
                name = f'ECO-{i:03d}.png'
                (folder / name).touch()
                rows.append(dict(id=f'ECO-{i:03d}', estado_tecnico='valida',
                                 convertido='/content/sesion-anterior/revision/agua_contaminada/' + name,
                                 pixel_sha256=str(i % 151)))
            manifest = root / 'manifest.csv'
            with manifest.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            original = manifest.read_bytes()
            resolved = remote.source_rows(root)
            self.assertEqual(len(resolved), 165)
            self.assertEqual(resolved[0]['convertido'], 'revision/agua_contaminada/ECO-000.png')
            self.assertEqual(manifest.read_bytes(), original)
            (folder / 'ECO-000.png').unlink()
            self.assertIsNone(remote.source_rows(root))

    def test_local_restoration_is_rejected(self):
        from unittest.mock import patch
        with patch.object(remote.Path, 'is_dir', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'restauración solo'):
                remote.restore_source()

    def test_grouped_split_covers_all_classes_and_is_reproducible(self):
        groups, labels = {}, {}
        for c in remote.CLASSES:
            for g in range(12):
                ids = [f'{c}-{g}-{i}' for i in range(1 + g % 3)]
                groups[f'{c}-{g}'] = ids
                labels.update(dict.fromkeys(ids, c))
        assignment = remote.partition(groups, labels)
        self.assertEqual(assignment, remote.partition(groups, labels))
        self.assertEqual(set(groups), set(assignment))
        for split in ('train', 'val', 'test'):
            self.assertEqual(set(remote.CLASSES),
                             {labels[i] for g in groups if assignment[g] == split
                              for i in groups[g]})

    def test_impossible_independent_groups_fail(self):
        groups = {c: [c] for c in remote.CLASSES}
        with self.assertRaises(RuntimeError):
            remote.partition(groups, {c: c for c in remote.CLASSES})

    def test_evidence_rejects_missing_or_duplicate_epochs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'results.csv'
            path.write_text('epoch,loss\n1,1.0\n2,0.5\n')
            self.assertEqual(len(remote.completed_epochs(path, 2)), 2)
            with self.assertRaises(RuntimeError):
                remote.completed_epochs(path, 100)
            path.write_text('epoch,loss\n1,1.0\n1,0.5\n')
            with self.assertRaises(RuntimeError):
                remote.completed_epochs(path, 2)
            path.write_text('epoch,loss\n1,nan\n2,0.5\n')
            with self.assertRaises(RuntimeError):
                remote.completed_epochs(path, 2)

    def test_local_environment_is_rejected_before_torch_import(self):
        from unittest.mock import patch
        with patch.object(remote.Path, 'is_dir', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'Solo Google Colab'):
                remote.require_colab()


if __name__ == '__main__':
    unittest.main()
