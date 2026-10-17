"""Pruebas ligeras de contrato e integridad. Los dobles nunca se usan en la app."""
import json
import csv
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import artefactos
import inferencia


class CierreTests(unittest.TestCase):
    def test_mapping_preserves_actual_model_order(self):
        order = {0:'suelo_contaminado',1:'aire_contaminado',2:'agua_contaminada'}
        self.assertEqual(inferencia.class_mapping(order), order)
        self.assertEqual(inferencia.class_mapping(list(order.values())), order)

    def test_bad_mapping_rejected(self):
        for mapping in ({0:'aire_contaminado'}, {0:'a',1:'b',2:'c'},
                        {1:'aire_contaminado',2:'agua_contaminada',3:'suelo_contaminado'}):
            with self.assertRaises(RuntimeError): inferencia.class_mapping(mapping)

    def test_missing_original_rejected_before_heavy_import(self):
        with patch.object(inferencia.Path, 'is_dir', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'best.pt original'):
                inferencia.Classifier('/does/not/exist/best.pt')

    def test_foreign_checkpoint_rejected_before_torch_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); run=root/'runs'/artefactos.RUN_NAME; run.mkdir(parents=True)
            archive=run/'entrega.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('train100/weights/best.pt',b'trusted synthetic unit fixture')
            foreign=root/'best.pt'; foreign.write_bytes(b'foreign synthetic unit fixture')
            with patch.dict('os.environ', {'ORIGINAL_ARCHIVE': str(archive)}), patch.object(artefactos,'STORE',root), patch.object(artefactos,'DELIVERY_SHA256',artefactos.sha256(archive)):
                with self.assertRaisesRegex(RuntimeError,'best.pt original'):
                    inferencia.Classifier(foreign)

    def test_score_indices_follow_model_names(self):
        # Doble de contrato; no ejecuta ni afirma inferencia real.
        obj = inferencia.Classifier.__new__(inferencia.Classifier)
        obj.names = {0:'suelo_contaminado',1:'aire_contaminado',2:'agua_contaminada'}
        obj.lock = threading.Lock()
        data = Mock(); data.detach.return_value.cpu.return_value.tolist.return_value = [.1,.7,.2]
        obj.model = Mock(); obj.model.predict.return_value = [SimpleNamespace(names=obj.names, probs=SimpleNamespace(data=data))]
        image = object()
        with patch.object(inferencia, 'load_image', return_value=image):
            label, scores = obj.predict('contract-only')
        self.assertEqual(label, 'aire_contaminado')
        self.assertEqual(scores['agua_contaminada'], .2)
        obj.model.predict.assert_called_once_with(image, device='cpu', imgsz=224, verbose=False)

    def test_invalid_scores_rejected(self):
        obj = inferencia.Classifier.__new__(inferencia.Classifier)
        obj.names = dict(enumerate(sorted(inferencia.CLASSES))); obj.lock = threading.Lock()
        for values in ([float('nan'),0,1], [1,0], [-.1,.5,.6]):
            data=Mock(); data.detach.return_value.cpu.return_value.tolist.return_value=values
            obj.model=Mock(); obj.model.predict.return_value=[SimpleNamespace(names=obj.names,probs=SimpleNamespace(data=data))]
            with patch.object(inferencia,'load_image',return_value=object()), self.assertRaises(RuntimeError): obj.predict('contract')

    def test_archive_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); archive=folder/'original.zip'; output=folder/'output'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('weights/best.pt',b'unit-test-only')
            artefactos.extract_original(archive,output)
            artefactos.extract_original(archive,output)
            (output/'weights/best.pt').write_bytes(b'existing-different-content')
            with self.assertRaisesRegex(RuntimeError,'sobrescribe'): artefactos.extract_original(archive,output)
            self.assertEqual((output/'weights/best.pt').read_bytes(),b'existing-different-content')

    def test_archive_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('../escape',b'x')
            with self.assertRaises(RuntimeError): artefactos.extract_original(archive,Path(temp)/'output')
            self.assertFalse((Path(temp)/'escape').exists())

    def test_sha_manifest_detects_tampering_missing_and_extra(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); target=root/'evidence.txt'; target.write_text('original')
            (root/'SHA256.json').write_text(json.dumps(artefactos.manifest(root)))
            self.assertEqual(artefactos.verify_manifest(root),1)
            target.write_text('changed')
            with self.assertRaises(RuntimeError): artefactos.verify_manifest(root)
            target.unlink()
            with self.assertRaises(RuntimeError): artefactos.verify_manifest(root)

    def test_original_verifier_checks_epochs_matrix_and_reserved_test(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('train100/weights/best.pt','train100/weights/last.pt','train100/args.yaml',
                         'train100/results.png','matriz_confusion.png','run-config.json','versiones.txt'):
                p=root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('synthetic unit fixture only')
            def write_csv(name, rows):
                with (root/name).open('w') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            epochs=[{'epoch':i,'loss':.5} for i in range(1,101)]
            write_csv('train100/results.csv',epochs)
            metrics={'accuracy':21/23,'muestras':23,'clases':artefactos.EXPECTED_CLASSES,'matriz':artefactos.EXPECTED_MATRIX}
            (root/'metricas_test.json').write_text(json.dumps(metrics))
            write_csv('matriz_confusion.csv',[dict(real=c,**dict(zip(artefactos.EXPECTED_CLASSES,row)))
                     for c,row in zip(artefactos.EXPECTED_CLASSES,artefactos.EXPECTED_MATRIX)])
            predictions=[]
            for real,row in zip(artefactos.EXPECTED_CLASSES,artefactos.EXPECTED_MATRIX):
                for predicted,count in zip(artefactos.EXPECTED_CLASSES,row):
                    for _ in range(count): predictions.append(dict(id=str(len(predictions)),real=real,prediccion=predicted))
            write_csv('predicciones_test.csv',predictions)
            partitions=[dict(id=r['id'],clase=r['real'],particion='test',grupo=r['id'],pixel_sha256=r['id']) for r in predictions]
            for split,count in (('train',105),('val',23)):
                for _ in range(count):
                    ident=str(len(partitions));partitions.append(dict(id=ident,clase=artefactos.EXPECTED_CLASSES[0],particion=split,grupo=ident,pixel_sha256=ident))
            write_csv('particiones.csv',partitions)
            self.assertEqual(artefactos.verify_original(root)['epocas'],100)
            write_csv('train100/results.csv',epochs[:-1])
            with self.assertRaisesRegex(RuntimeError,'100 épocas'): artefactos.verify_original(root)
            write_csv('train100/results.csv',epochs)
            predictions[0]['prediccion']='aire_contaminado'
            write_csv('predicciones_test.csv',predictions)
            with self.assertRaisesRegex(RuntimeError,'Predicciones'): artefactos.verify_original(root)

    def test_recorded_metrics_match_original_stdout(self):
        root=Path(__file__).resolve().parents[1]/'entrega'
        if not root.exists(): root=root.parent
        metrics=json.loads((root/'evidencias/metricas_test_recuperadas_historial.json').read_text())
        self.assertEqual(metrics['clases'],artefactos.EXPECTED_CLASSES)
        self.assertEqual(metrics['matriz'],artefactos.EXPECTED_MATRIX)
        self.assertAlmostEqual(metrics['accuracy'],21/23)
        text=(root/'evidencias/colab-final-original.txt').read_text()
        self.assertIn('100 epochs completed',text)
        self.assertIn(artefactos.DELIVERY_SHA256,text)


if __name__ == '__main__': unittest.main()
