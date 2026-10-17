"""Historial académico sin fotografías, direcciones IP ni nombres de archivo."""
import logging
import math
import os
import uuid
from datetime import UTC, datetime

from inferencia import CLASSES, INCONCLUSIVE_TITLE, accepted_label

LOG = logging.getLogger('ecoguard.mongo')


class StorageError(RuntimeError):
    pass


class AnalysisStore:
    def __init__(self):
        self.uri = os.environ.get('MONGODB_URI', '')
        self.database = os.environ.get('MONGODB_DB', 'ecoguard')
        self.client = None
        self.collection = None

    def connect(self):
        if not self.uri:
            raise StorageError('MongoDB Atlas no está configurado. El análisis no se ha guardado.')
        try:
            if self.client is None:
                from pymongo import MongoClient
                self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
                                          socketTimeoutMS=5000, maxPoolSize=3, tz_aware=True)
                self.collection = self.client[self.database]['analisis']
            self.client.admin.command('ping')
            self.collection.create_index([('usuario_id', 1), ('fecha_hora', -1)],
                                         name='historial_por_usuario')
            self.collection.create_index('analisis_id', unique=True, name='analisis_unico')
            return self.collection
        except Exception as exc:  # noqa: BLE001 - frontera de disponibilidad MongoDB
            LOG.warning('Conexión MongoDB falló (%s)', type(exc).__name__)
            raise StorageError('MongoDB Atlas no está disponible. No se confirma el guardado.') from None

    def insert(self, category, scores, version):
        """Contrato histórico sin propietario; solo se conserva para compatibilidad interna.

        La aplicación web utiliza exclusivamente ``insert_for_user``.
        """
        return self._insert(category, scores, version, None)

    def insert_for_user(self, user_id, category, scores, version):
        if not isinstance(user_id, str) or not user_id.strip():
            raise StorageError('Se requiere una sesión válida para guardar el resultado.')
        return self._insert(category, scores, version, user_id)

    def _insert(self, category, scores, version, user_id):
        if (category not in CLASSES or set(scores) != CLASSES or not version
                or any(not math.isfinite(v) or not 0 <= v <= 1 for v in scores.values())
                or not math.isclose(sum(scores.values()), 1, abs_tol=1e-4)):
            raise ValueError('Análisis incompatible.')
        if accepted_label(scores) != category:
            raise StorageError(INCONCLUSIVE_TITLE + '. No se ha guardado el resultado.')
        ident = str(uuid.uuid4())
        record = {'_id': ident, 'analisis_id': ident, 'fecha_hora': datetime.now(UTC),
                  'categoria': category, 'puntuaciones': scores, 'version_modelo': version}
        if user_id is not None:
            record['usuario_id'] = user_id
        collection = self.connect()
        try:
            result = collection.insert_one(record)
            if not result.acknowledged:
                raise StorageError('MongoDB no confirmó la escritura.')
        except Exception as exc:  # noqa: BLE001 - confirma toda falla como escritura fallida
            LOG.warning('Inserción MongoDB falló (%s)', type(exc).__name__)
            raise StorageError('No se confirmó el guardado en MongoDB. El resultado sigue visible.') from None
        return ident

    def history(self):
        collection = self.connect()
        try:
            return list(collection.find({}, {'_id': 0}).sort('fecha_hora', -1).limit(100))
        except Exception:  # noqa: BLE001 - mensaje público sin detalles del controlador
            raise StorageError('No se pudo consultar el historial de MongoDB.') from None

    def history_for_user(self, user_id):
        if not isinstance(user_id, str) or not user_id.strip():
            raise StorageError('Se requiere una sesión válida para consultar el historial.')
        collection = self.connect()
        try:
            return list(collection.find({'usuario_id': user_id}, {'_id': 0, 'usuario_id': 0})
                        .sort('fecha_hora', -1).limit(100))
        except Exception:  # noqa: BLE001 - mensaje público sin detalles del controlador
            raise StorageError('No se pudo consultar el historial de MongoDB.') from None

    def stats(self):
        collection = self.connect()
        try:
            counts = {r['_id']: r['cantidad'] for r in collection.aggregate([
                {'$group': {'_id': '$categoria', 'cantidad': {'$sum': 1}}}])}
            return {name: counts.get(name, 0) for name in sorted(CLASSES)}
        except Exception:  # noqa: BLE001 - mensaje público sin detalles del controlador
            raise StorageError('No se pudieron consultar las estadísticas de MongoDB.') from None


    def stats_for_user(self, user_id):
        if not isinstance(user_id, str) or not user_id.strip():
            raise StorageError('Se requiere una sesión válida para consultar las estadísticas.')
        collection = self.connect()
        try:
            counts = {r['_id']: r['cantidad'] for r in collection.aggregate([
                {'$match': {'usuario_id': user_id}},
                {'$group': {'_id': '$categoria', 'cantidad': {'$sum': 1}}}])}
            return {name: counts.get(name, 0) for name in sorted(CLASSES)}
        except Exception:  # noqa: BLE001 - mensaje público sin detalles del controlador
            raise StorageError('No se pudieron consultar las estadísticas de MongoDB.') from None
