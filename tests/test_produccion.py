"""Contratos con dobles técnicos; nunca afirman una conexión real a Atlas."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from mongo_store import AnalysisStore, StorageError
from inferencia import OnnxClassifier, AnalysisError, load_image
from artefactos import DELIVERY_SHA256, sha256


class ProductionContracts(unittest.TestCase):
    def test_unconfigured_mongodb_does_not_claim_success(self):
        with patch.dict(os.environ, {'MONGODB_URI': ''}):
            with self.assertRaises(StorageError): AnalysisStore().history()

    def test_mongo_document_privacy_and_acknowledgement(self):
        store = AnalysisStore()
        collection = Mock(); collection.insert_one.return_value.acknowledged = True
        scores = {'aire_contaminado': .8, 'agua_contaminada': .1, 'suelo_contaminado': .1}
        with patch.object(store, 'connect', return_value=collection):
            ident = store.insert('aire_contaminado', scores, 'sha256-unit-contract')
            document = collection.insert_one.call_args.args[0]
            self.assertEqual(document['_id'], ident)
            self.assertEqual(set(document), {'_id','analisis_id','fecha_hora','categoria','puntuaciones','version_modelo'})
            self.assertIsNotNone(document['fecha_hora'].tzinfo)
            collection.insert_one.return_value.acknowledged = False
            with self.assertRaises(StorageError): store.insert('aire_contaminado', scores, 'sha256-unit-contract')
            collection.insert_one.side_effect = Exception('private URI must never appear')
            with self.assertRaises(StorageError) as exc: store.insert('aire_contaminado', scores, 'sha256-unit-contract')
            self.assertNotIn('private URI', str(exc.exception))

    def test_onnx_refuses_unvalidated_conversion_before_runtime_import(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'best.onnx'; p.write_bytes(b'synthetic unit fixture, never a model')
            p.with_suffix('.json').write_text(json.dumps({'original_archive_sha256': DELIVERY_SHA256,
                'onnx_sha256': sha256(p), 'parity': {'passed': False, 'images': 23}}))
            with self.assertRaisesRegex(RuntimeError, 'comparación real'): OnnxClassifier(p)

    def test_local_recovery_rejects_wrong_zip_without_colab(self):
        import ecoguard
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); wrong = root/'wrong.zip'; wrong.write_bytes(b'not original')
            with patch.object(ecoguard, 'DELIVERY', root/'delivery'):
                with self.assertRaisesRegex(RuntimeError, 'SHA256 original'): ecoguard.recover(wrong)
            self.assertFalse((root/'delivery/entrega-original.zip').exists())

    def test_history_and_statistics_are_real_queries(self):
        store = AnalysisStore(); collection = Mock()
        collection.find.return_value.sort.return_value.limit.return_value = [{'analisis_id':'unit-contract'}]
        collection.aggregate.return_value = [{'_id':'agua_contaminada','cantidad':2}]
        with patch.object(store, 'connect', return_value=collection):
            self.assertEqual(store.history()[0]['analisis_id'], 'unit-contract')
            self.assertEqual(store.stats()['agua_contaminada'], 2)
            self.assertEqual(store.stats()['aire_contaminado'], 0)
        collection.find.return_value.sort.return_value.limit.assert_called_with(100)


@unittest.skipUnless(os.environ.get('ECOGUARD_ATLAS_REAL_TESTS') == '1', 'Falta habilitar integración real con modelo original y MongoDB Atlas')
class RealAtlasAcceptance(unittest.TestCase):
    def test_prediction_insert_query(self):
        from inferencia import create_classifier
        model = create_classifier(os.environ['MODEL_PATH'])
        label, scores = model.predict(os.environ['ECOGUARD_SAMPLE'])
        version = getattr(model, 'version', None) or sha256(os.environ['MODEL_PATH'])
        store = AnalysisStore()
        ident = store.insert(label, scores, version)
        record = store.connect().find_one({'_id': ident})
        self.assertEqual(record['categoria'], label)
        self.assertEqual(record['puntuaciones'], scores)
        self.assertGreaterEqual(store.stats()[label], 1)
        # Registro auténtico conservado como evidencia; no se borra automáticamente.


if __name__ == '__main__': unittest.main()
