"""Integración REAL: ejecutar con el original con ECOGUARD_REAL_TESTS=1. Una foto, sin entrenar."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from artefactos import STORE, DATASET_SHA256, sha256


@unittest.skipUnless(os.environ.get('ECOGUARD_REAL_TESTS') == '1', 'Requiere best.pt original, fotografías reales y dependencias de inferencia')
class RealApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from inferencia import Classifier
        cls.weights=Path(os.environ.get('ECOGUARD_WEIGHTS', os.environ.get('MODEL_PATH', 'entrega/original/train100/weights/best.pt')))
        cls.classifier=Classifier(cls.weights)
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.sample=Path(cls.temp.name)/'sample.png'
        source=os.environ.get('ECOGUARD_SAMPLE')
        if source:
            import shutil
            shutil.copyfile(source,cls.sample)
        else:
            prepared=STORE/'datasets'/DATASET_SHA256/'preparado.zip'
            metadata=json.loads(prepared.with_suffix('.json').read_text())
            if metadata['dataset_sha256'] != DATASET_SHA256 or sha256(prepared) != metadata['sha256']:
                raise RuntimeError('El respaldo preparado no supera la verificación SHA256.')
            with zipfile.ZipFile(prepared) as z:
                names=[n for n in z.namelist() if '/test/' in '/'+n and n.endswith('.png')]
                if not names: raise RuntimeError('No se encontró una fotografía del test original.')
                cls.sample.write_bytes(z.read(sorted(names)[0]))

    def test_model_load_and_real_mapping(self):
        from inferencia import CLASSES
        self.assertEqual(self.classifier.model.task,'classify')
        self.assertEqual(set(self.classifier.names.values()),CLASSES)
        print('Orden REAL del checkpoint:', self.classifier.names)

    def test_valid_image_real_inference(self):
        label,scores=self.classifier.predict(self.sample)
        self.assertIn(label,scores)
        self.assertEqual(len(scores),3)
        self.assertAlmostEqual(sum(scores.values()),1,places=4)

    def test_invalid_file_and_missing_image(self):
        from inferencia import AnalysisError
        invalid=Path(self.temp.name)/'invalid.jpg'; invalid.write_bytes(b'not-an-image')
        for source in (invalid,None):
            with self.assertRaises(AnalysisError): self.classifier.predict(source)

    def test_gradio_browser_and_api(self):
        import urllib.request
        from gradio_client import Client, handle_file
        from app_gradio import build_app
        app, infer=build_app(self.weights)
        try:
            _, url, _=app.launch(server_name='127.0.0.1',server_port=7862,share=False,
                                 prevent_thread_lock=True,show_error=False)
            self.assertEqual(urllib.request.urlopen(url,timeout=10).status,200)
            client=Client(url,verbose=False)
            output=client.predict(handle_file(str(self.sample)),api_name='/analizar')
            self.assertTrue(output[0])
            self.assertIn('completado',output[-1])
            self.assertEqual(output[1].count('role="meter"'),3)
            invalid=Path(self.temp.name)/'bad.jpg'; invalid.write_bytes(b'not-an-image')
            output=client.predict(handle_file(str(invalid)),api_name='/analizar')
            self.assertEqual(output[0],'')
            self.assertNotIn('Traceback',output[-1])
            self.assertEqual(infer(None)[0],'')
            reset=client.predict(api_name='/reiniciar')
            self.assertIsNone(reset[0])
            self.assertIsNone(reset[1])
            self.assertEqual(reset[2],'')
            # UI includes explicit limits and reset action.
            from gradio.routes import ORJSONResponse
            config=ORJSONResponse._render_str(app.get_config_file())
            self.assertIn('Limpiar',config)
            self.assertIn('No reemplaza una evaluación técnica o ambiental',config)
        finally:
            app.close()


if __name__ == '__main__': unittest.main(verbosity=2)
