"""Pruebas locales: ONNX real y contratos de cámara (sin dispositivo físico)."""
import copy
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from artefactos import sha256
from camera_analysis import CameraAnalyzer, CameraSession
from inferencia import LABELS, AnalysisError, OnnxClassifier

ROOT = Path(__file__).resolve().parents[1]
SCORES = {'agua_contaminada': .8, 'aire_contaminado': .15, 'suelo_contaminado': .05}


class CameraContracts(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.image = Image.new('RGB', (1920, 1080))
        self.model = Mock()
        self.model.predict.return_value = ('agua_contaminada', SCORES)
        self.engine = CameraAnalyzer(self.model)
        self.session = CameraSession()

    def test_start_stop_and_null(self):
        self.assertIsNone(self.engine.frame(self.image, self.session))
        self.session.start()
        with self.assertRaises(AnalysisError): self.engine.frame(None, self.session)
        self.session.stop()
        self.assertIsNone(self.engine.frame(self.image, self.session))

    def test_scores_resolution_interval_and_no_images_in_state(self):
        self.session.start()
        self.assertEqual(self.engine.frame(self.image, self.session)['scores'], SCORES)
        image = self.model.predict.call_args.args[0]
        self.assertEqual(image.size, (960, 540))
        self.assertEqual(self.image.size, (1920, 1080))
        self.assertIsNone(self.engine.frame(self.image, self.session))
        self.assertEqual(self.model.predict.call_count, 1)
        self.assertEqual(set(self.session.latest), {'label','scores','ms'})

    def test_busy_frame_is_discarded_without_wait(self):
        self.session.start()
        with self.engine.engine_lock:
            self.assertIsNone(self.engine.frame(self.image, self.session))
        self.model.predict.assert_not_called()

    def test_stop_discards_inflight_result(self):
        self.session.start()
        entered, release = threading.Event(), threading.Event()
        def predict(image):
            entered.set()
            release.wait(3)
            return 'agua_contaminada', SCORES
        self.model.predict.side_effect = predict
        results = []
        thread = threading.Thread(target=lambda: results.append(self.engine.frame(self.image, self.session)))
        thread.start()
        self.assertTrue(entered.wait(3))
        self.session.stop()
        release.set()
        thread.join(3)
        self.assertEqual(results, [None])
        self.assertIsNone(self.session.latest)

    def test_sessions_are_isolated_and_snapshots_are_copies(self):
        other = copy.deepcopy(self.session)
        self.session.start()
        self.engine.frame(self.image, self.session)
        snap = self.engine.snapshot(self.session)
        snap['scores']['agua_contaminada'] = 0
        self.assertEqual(self.session.latest['scores']['agua_contaminada'], .8)
        self.assertIsNone(other.latest)
        self.assertFalse(other.active)

    def test_error_clears_stale_result_and_unlocks_engine(self):
        self.engine.frame(self.image, self.session, manual=True)
        self.model.predict.side_effect = RuntimeError('unit failure')
        with self.assertRaises(RuntimeError): self.engine.frame(self.image, self.session, manual=True)
        self.assertIsNone(self.session.latest)
        self.assertFalse(self.engine.engine_lock.locked())

    def test_manual_capture_when_stream_is_stopped(self):
        self.assertEqual(self.engine.frame(self.image, self.session, manual=True)['label'], 'agua_contaminada')
        self.assertFalse(self.session.active)


class OnnxUXIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = OnnxClassifier(ROOT / 'models/best.onnx')
        cls.samples = sorted((ROOT / 'artifacts/test-original').rglob('*.png'))
        if len(cls.samples) != 23: raise RuntimeError('Se requieren las 23 fotografías reales reservadas.')

    def test_real_onnx_all_reserved_images_and_camera_update(self):
        from PIL import Image
        engine = CameraAnalyzer(self.model, interval=0)
        session = CameraSession(); session.start()
        predictions = set()
        for sample in self.samples:
            label, scores = self.model.predict(sample)
            self.assertEqual(set(scores), set(LABELS))
            self.assertAlmostEqual(sum(scores.values()), 1, places=4)
            with Image.open(sample) as image:
                result = engine.frame(image, session)
            self.assertIn(result['label'], LABELS)
            self.assertEqual(session.latest['label'], result['label'])
            predictions.add(label)
        self.assertEqual(predictions, set(LABELS))
        session.stop()
        self.assertIsNone(engine.frame(None, session))

    def test_real_gradio_events_upload_save_history_and_reset(self):
        from app_gradio import build_app
        from gradio.data_classes import FileData
        with patch.dict(os.environ, {'MONGODB_URI': ''}):
            app, infer = build_app(ROOT / 'models/best.onnx')
            # Callbacks reales, con preprocesamiento Gradio real del archivo.
            # HTTP/navegador se comprueban aparte; no se simula un permiso físico.
            from PIL import Image
            functions = {f.api_name: f for f in app.fns.values()}
            data = infer(self.samples[0])
            self.assertIn(data[0], LABELS.values())
            self.assertEqual(data[1].count('role="meter"'), 3)
            self.assertIn('no se ha guardado', data[-1])
            self.assertEqual(infer(None)[0], '')
            session = CameraSession()
            functions['iniciar_camara'].fn(session)
            input_component = functions['fotograma'].inputs[0]
            cache = app.move_resource_to_block_cache(str(self.samples[0]))
            frame = input_component.preprocess(FileData(path=cache))
            self.assertIsInstance(frame, Image.Image)
            data = functions['fotograma'].fn(frame, session)
            self.assertIn('Resultado principal', data[0])
            self.assertIn('Aún no se ha guardado', data[1])
            self.assertIn('no se ha guardado', functions['guardar_camara'].fn(session))
            # La cámara no escribe nada hasta la acción explícita.
            with patch('mongo_store.AnalysisStore.insert', return_value='confirmed-unit-id') as insert:
                session.start()
                functions['fotograma'].fn(frame, session)
                insert.assert_not_called()
                self.assertIn('confirmed-unit-id', functions['guardar_camara'].fn(session))
                insert.assert_called_once()
                self.assertEqual(len(insert.call_args.args), 3)
            fresh = CameraSession(); fresh.start()
            self.assertIn('No hay imagen de la cámara', functions['fotograma'].fn(None, fresh)[1])
            self.assertIn('No hay un resultado', functions['guardar_camara'].fn(fresh))
            functions['detener_camara'].fn(session)
            self.assertEqual(functions['fotograma'].fn(frame, session)[0], {'__type__':'update'})
            self.assertIn('no se ha guardado', functions['historial'].fn()[-1])
            reset = functions['reiniciar'].fn()
            self.assertIsNone(reset[0]); self.assertIsNone(reset[1]); self.assertEqual(reset[2], '')
            config = app.get_config_file()
            from gradio.routes import ORJSONResponse
            self.assertIn('Cámara en vivo', ORJSONResponse._render_str(config))
            stream = next(d for d in config['dependencies'] if d['api_name'] == 'fotograma')
            self.assertEqual(stream['stream_every'], 2)
            self.assertEqual(stream['trigger_mode'], 'once')
            self.assertTrue(stream['queue'])
            self.assertIsNone(functions['fotograma'].concurrency_limit)
            self.assertTrue(any(c['props'].get('label') == 'Cámara en vivo' for c in config['components']))

    def test_models_unchanged(self):
        expected = {
            'models/best.onnx':'b90eb5240038be75cea6b1477ef23665882abad69c126c7257a5578722812eef',
            'models/best.json':'b24374fea80eb90015ae53ceca2673188104fc46b1acd506911c1f7273d5b178',
            'entrega/original/train100/weights/best.pt':'57b2194e8cfb26de44eb93960193392965e4c46be3c75f8f22c81b5a37b7ed32',
            'entrega/original/train100/weights/last.pt':'005ecb8bd05c6f2bfba95d3deccdc2f9c112840fea398aae07807d15c8e8d72f',
        }
        for name, digest in expected.items():
            with self.subTest(file=name): self.assertEqual(sha256(ROOT / name), digest)


if __name__ == '__main__': unittest.main(verbosity=2)
