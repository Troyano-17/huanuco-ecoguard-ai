"""Regla inclusiva y contratos UI/almacenamiento, sin cámara física ni Atlas."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inferencia import (accepted_label, class_mapping, LABELS, INCONCLUSIVE_TITLE,
                        INCONCLUSIVE_DESCRIPTION, MIN_ACCEPTANCE_SCORE)
from camera_analysis import CameraAnalyzer, CameraSession
from mongo_store import AnalysisStore, StorageError
from app_gradio import build_app, result_html
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['agua_contaminada', 'aire_contaminado', 'suelo_contaminado']


def scores_at(value, label='agua_contaminada'):
    return {name: value if name == label else (1-value)/2 for name in NAMES}


class AcceptanceRule(unittest.TestCase):
    def test_inclusive_boundary_and_unchanged_scores(self):
        self.assertEqual(MIN_ACCEPTANCE_SCORE, .60)
        for value in (.59, .5999, .60, .6001, .75, .95):
            with self.subTest(value=value):
                scores = scores_at(value)
                original = copy.deepcopy(scores)
                self.assertEqual(accepted_label(scores), NAMES[0] if value >= .60 else None)
                self.assertEqual(scores, original)

    def test_mapping_all_three_categories(self):
        self.assertEqual(class_mapping(NAMES), dict(enumerate(NAMES)))
        for label in NAMES:
            self.assertEqual(accepted_label(scores_at(.75, label)), label)

    def test_no_category_bars_or_advice_for_rejected_result(self):
        html = result_html({'label': NAMES[0], 'scores': scores_at(.5999)})
        self.assertIn(INCONCLUSIVE_TITLE, html)
        self.assertIn(INCONCLUSIVE_DESCRIPTION, html)
        for title in LABELS.values():
            self.assertNotIn(title, html)
        self.assertNotIn('role="meter"', html)
        self.assertNotIn('eco-recommendation', html)

    def test_store_rejects_low_scores_and_wrong_category_before_connection(self):
        store = AnalysisStore()
        with patch.object(store, 'connect') as connect:
            for value in (.59, .5999):
                with self.assertRaises(StorageError):
                    store.insert(NAMES[0], scores_at(value), 'unit-version')
            with self.assertRaises(StorageError):
                store.insert(NAMES[1], scores_at(.95), 'unit-version')
            connect.assert_not_called()

    def test_store_accepts_exact_boundary_with_original_scores(self):
        store = AnalysisStore()
        collection = Mock()
        collection.insert_one.return_value.acknowledged = True
        scores = scores_at(.60)
        with patch.object(store, 'connect', return_value=collection):
            store.insert(NAMES[0], scores, 'unit-version')
        self.assertEqual(collection.insert_one.call_args.args[0]['puntuaciones'], scores)

    def test_live_and_manual_alternation_clear_previous_and_isolate_sessions(self):
        for manual in (False, True):
            with self.subTest(manual=manual):
                model = Mock()
                engine = CameraAnalyzer(model, interval=0)
                session, other = CameraSession(), CameraSession()
                session.start(); other.start()
                image = Image.new('RGB', (32, 32))
                model.predict.return_value = (NAMES[1], scores_at(.95, NAMES[1]))
                engine.frame(image, other, manual=manual)
                for value in (.75, .59, .60, .5999, .95):
                    model.predict.return_value = (NAMES[0], scores_at(value))
                    result = engine.frame(image, session, manual=manual)
                    self.assertEqual(result['scores'], scores_at(value))
                    self.assertEqual(result['label'], NAMES[0] if value >= .60 else None)
                    self.assertEqual(engine.snapshot(session) is not None, value >= .60)
                    self.assertEqual(engine.snapshot(other)['label'], NAMES[1])
                session.start()
                self.assertIsNone(engine.snapshot(session))


class AcceptanceUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Mock(version='unit-version')
        with patch('app_gradio.create_classifier', return_value=cls.model):
            cls.app, infer = build_app(ROOT / 'models/best.onnx')
            cls.infer = staticmethod(infer)
        cls.functions = {f.api_name: f.fn for f in cls.app.fns.values()}

    def setUp(self):
        self.model.predict.return_value = (NAMES[0], scores_at(.75))

    def test_photo_accept_reject_reset_and_preview_clear(self):
        with patch('mongo_store.AnalysisStore.insert', return_value='unit-id') as insert:
            self.assertEqual(self.infer('fixture')[0], LABELS[NAMES[0]])
            insert.assert_called_once()
            insert.reset_mock()
            self.model.predict.return_value = (NAMES[0], scores_at(.59))
            result = self.infer('fixture')
            self.assertEqual(result[0], '')
            self.assertIn(INCONCLUSIVE_TITLE, result[1])
            self.assertEqual(result[2:4], ('', ''))
            self.assertNotIn('Resultado guardado', result[-1])
            insert.assert_not_called()
        self.assertEqual(self.functions['reiniciar']()[0:6], (None, None, '', '', '', ''))
        preview_fn = next(f.fn for f in self.app.fns.values() if f.fn.__name__ == 'update_preview')
        self.assertEqual(preview_fn(None)[0:5], (None, '', '', '', ''))

    def test_camera_buttons_stale_save_and_fresh_session(self):
        session = CameraSession()
        image = Image.new('RGB', (32, 32))
        self.assertFalse(self.functions['iniciar_camara'](session)[2]['interactive'])
        with patch('mongo_store.AnalysisStore.insert', return_value='unit-id') as insert:
            self.assertTrue(self.functions['captura_manual'](image, session)[2]['interactive'])
            insert.assert_not_called()
            self.assertIn('unit-id', self.functions['guardar_camara'](session))
            insert.reset_mock()
            self.model.predict.return_value = (NAMES[0], scores_at(.5999))
            output = self.functions['captura_manual'](image, session)
            self.assertIn(INCONCLUSIVE_TITLE, output[0])
            self.assertFalse(output[2]['interactive'])
            self.assertIn('No hay un resultado', self.functions['guardar_camara'](session))
            self.assertIn('No hay un resultado', self.functions['guardar_camara'](CameraSession()))
            insert.assert_not_called()

    def test_live_callback_alternation_and_restart(self):
        session = CameraSession()
        image = Image.new('RGB', (32, 32))
        self.functions['iniciar_camara'](session)
        with patch('camera_analysis.time.monotonic', side_effect=[10, 13, 16, 19]), \
                patch('mongo_store.AnalysisStore.insert') as insert:
            for value in (.95, .59, .60, .5999):
                self.model.predict.return_value = (NAMES[0], scores_at(value))
                output = self.functions['fotograma'](image, session)
                self.assertEqual(output[2]['interactive'], value >= .60)
                if value < .60:
                    self.assertIn(INCONCLUSIVE_TITLE, output[0])
                    self.assertNotIn(LABELS[NAMES[0]], output[0])
                    self.assertIn('No hay un resultado', self.functions['guardar_camara'](session))
            insert.assert_not_called()
        self.functions['iniciar_camara'](session)
        self.assertIsNone(session.latest)



if __name__ == '__main__':
    unittest.main(verbosity=2)
