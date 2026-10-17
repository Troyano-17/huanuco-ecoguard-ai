"""Validación local de documentos y BSON; no conecta a MongoDB Atlas."""
from datetime import timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from mongo_store import AnalysisStore


class LocalMongoSchemaTests(unittest.TestCase):
    scores = {'aire_contaminado': .8, 'agua_contaminada': .1, 'suelo_contaminado': .1}

    def document(self):
        store = AnalysisStore()
        collection = Mock()
        collection.insert_one.return_value.acknowledged = True
        with patch.object(store, 'connect', return_value=collection):
            ident = store.insert('aire_contaminado', dict(self.scores), 'a' * 64)
        return ident, collection.insert_one.call_args.args[0]

    def test_document_types_identifiers_and_privacy(self):
        ident, record = self.document()
        self.assertEqual(str(uuid.UUID(ident)), ident)
        self.assertEqual(record['_id'], record['analisis_id'])
        self.assertEqual(record['fecha_hora'].utcoffset().total_seconds(), 0)
        self.assertEqual(record['version_modelo'], 'a' * 64)
        self.assertEqual(record['puntuaciones'], self.scores)
        self.assertEqual(set(record), {'_id', 'analisis_id', 'fecha_hora',
                                      'categoria', 'puntuaciones', 'version_modelo'})

    def test_invalid_documents_rejected_before_connection(self):
        store = AnalysisStore()
        cases = [('limpio', self.scores, 'a' * 64),
                 ('aire_contaminado', self.scores, ''),
                 ('aire_contaminado', {'aire_contaminado': 1.0}, 'a' * 64)]
        for value in (float('nan'), float('inf'), -.1, 1.1, .7):
            cases.append(('aire_contaminado', dict(self.scores, aire_contaminado=value), 'a' * 64))
        with patch.object(store, 'connect') as connect:
            for args in cases:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    store.insert(*args)
            connect.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('bson'), 'Requiere el códec BSON de PyMongo')
    def test_real_bson_roundtrip_without_database(self):
        from bson import BSON
        from bson.codec_options import CodecOptions
        _, record = self.document()
        restored = BSON(BSON.encode(record)).decode(codec_options=CodecOptions(tz_aware=True, tzinfo=timezone.utc))
        for key in set(record) - {'fecha_hora'}:
            self.assertEqual(restored[key], record[key])
        # BSON conserva fechas UTC con precisión de milisegundos.
        delta = abs((record['fecha_hora'] - restored['fecha_hora']).total_seconds())
        self.assertLess(delta, .001)
