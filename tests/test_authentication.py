"""Autenticación, autorización y aislamiento local; no afirma conexión real a Atlas."""
import asyncio
import hashlib
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

import gradio as gr
import mongomock
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from auth_store import (
    PASSWORD_HASHER,
    SESSION_COOKIE,
    AuthError,
    AuthStore,
    DuplicateEmail,
    InvalidCredentials,
    LoginBlocked,
    utcnow,
)
from inferencia import MIN_ACCEPTANCE_SCORE
from mongo_store import AnalysisStore, StorageError

SECRET = 'unit-test-session-secret-with-more-than-32-bytes'
PASSWORD = 'BosqueSeguro2026'
SCORES_OK = {'aire_contaminado': .8, 'agua_contaminada': .1, 'suelo_contaminado': .1}
SCORES_LOW = {'aire_contaminado': .59, 'agua_contaminada': .21, 'suelo_contaminado': .20}


def auth_store():
    return AuthStore(client=mongomock.MongoClient(tz_aware=True), database='test', secret=SECRET)


class AuthenticationStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = auth_store()

    def test_valid_registration_normalizes_email_and_uses_argon2id(self):
        user_id = self.store.register('  Ana   Torres ', ' ANA@Example.COM ', PASSWORD)
        user = self.store.connect().usuarios.find_one({'_id': user_id})
        self.assertEqual(user['nombre'], 'Ana Torres')
        self.assertEqual(user['correo_normalizado'], 'ana@example.com')
        self.assertTrue(user['password_hash'].startswith('$argon2id$'))
        self.assertTrue(PASSWORD_HASHER.verify(user['password_hash'], PASSWORD))
        self.assertNotIn(PASSWORD, repr(user))

    def test_duplicate_email_and_wrong_password_have_safe_errors(self):
        self.store.register('Ana Torres', 'ana@example.com', PASSWORD)
        with self.assertRaises(DuplicateEmail):
            self.store.register('Otra Persona', 'ANA@example.com', PASSWORD)
        with self.assertRaises(InvalidCredentials) as error:
            self.store.authenticate('ana@example.com', 'ClaveIncorrecta7')
        self.assertNotIn('hash', str(error.exception).lower())

    def test_login_logout_and_closed_session_reuse(self):
        user_id = self.store.register('Ana Torres', 'ana@example.com', PASSWORD)
        user = self.store.authenticate('ana@example.com', PASSWORD)
        self.assertEqual(user['_id'], user_id)
        token = self.store.create_session(user_id)
        self.assertEqual(self.store.resolve_session(token)['_id'], user_id)
        self.store.revoke_session(token)
        self.assertIsNone(self.store.resolve_session(token))

    def test_expired_session(self):
        user_id = self.store.register('Ana Torres', 'ana@example.com', PASSWORD)
        token = self.store.create_session(user_id)
        self.store.connect().sesiones.update_one({}, {'$set': {'expira_en': utcnow() - timedelta(seconds=1)}})
        self.assertIsNone(self.store.resolve_session(token))

    def test_repeated_login_attempts_are_blocked_persistently(self):
        self.store.register('Ana Torres', 'ana@example.com', PASSWORD)
        for _ in range(5):
            with self.assertRaises(InvalidCredentials):
                self.store.authenticate('ana@example.com', 'ClaveIncorrecta7')
        with self.assertRaises(LoginBlocked):
            self.store.authenticate('ana@example.com', PASSWORD)
        self.assertEqual(self.store.connect().intentos_login.count_documents({}), 1)

    def test_mongodb_unavailable_fails_closed(self):
        unavailable = AuthStore(uri='', database='test', secret=SECRET)
        with self.assertRaises(AuthError):
            unavailable.register('Ana Torres', 'ana@example.com', PASSWORD)
        self.assertIsNone(unavailable.resolve_session('invented-token'))


class OwnedAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.mongo = mongomock.MongoClient(tz_aware=True)
        self.store = AnalysisStore()
        self.collection = self.mongo.test.analisis
        self.connect = patch.object(self.store, 'connect', return_value=self.collection)
        self.connect.start()

    def tearDown(self):
        self.connect.stop()

    def test_history_and_statistics_are_isolated_between_two_users(self):
        self.store.insert_for_user('user-a', 'aire_contaminado', SCORES_OK, 'v1')
        self.store.insert_for_user('user-b', 'agua_contaminada',
            {'aire_contaminado': .1, 'agua_contaminada': .8, 'suelo_contaminado': .1}, 'v1')
        self.assertEqual([x['categoria'] for x in self.store.history_for_user('user-a')], ['aire_contaminado'])
        self.assertEqual(self.store.stats_for_user('user-a')['aire_contaminado'], 1)
        self.assertEqual(self.store.stats_for_user('user-a')['agua_contaminada'], 0)
        self.assertEqual(self.store.stats_for_user('user-b')['agua_contaminada'], 1)

    def test_accepted_analysis_is_saved_without_image(self):
        ident = self.store.insert_for_user('user-a', 'aire_contaminado', SCORES_OK, 'v1')
        record = self.collection.find_one({'_id': ident})
        self.assertEqual(record['usuario_id'], 'user-a')
        self.assertEqual(set(record), {'_id', 'analisis_id', 'usuario_id', 'fecha_hora',
                                      'categoria', 'puntuaciones', 'version_modelo'})

    def test_below_sixty_percent_is_never_saved(self):
        self.assertEqual(MIN_ACCEPTANCE_SCORE, .60)
        with self.assertRaises(StorageError):
            self.store.insert_for_user('user-a', 'aire_contaminado', SCORES_LOW, 'v1')
        self.assertEqual(self.collection.count_documents({}), 0)


class ProtectedServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth = auth_store()
        with gr.Blocks() as blocks:
            gr.Markdown('área privada')
        cls.blocks = blocks
        environment = {'SESSION_SECRET': SECRET, 'MONGODB_URI': 'mongodb://unit.invalid'}
        with patch.dict(os.environ, environment), \
             patch('auth_store.AuthStore', return_value=cls.auth), \
             patch('app_gradio.build_app', return_value=(blocks, lambda value: value)):
            from servidor import create_server
            cls.app = create_server()

    def setUp(self):
        self.auth.connect().usuarios.delete_many({})
        self.auth.connect().sesiones.delete_many({})
        self.auth.connect().intentos_login.delete_many({})

    @classmethod
    def endpoint(cls, path, method):
        return next(r.endpoint for r in cls.app.routes
                    if getattr(r, 'path', None) == path and method in getattr(r, 'methods', set()))

    @staticmethod
    def request(path, data=None, cookie=None, https=False):
        body = urlencode(data or {}).encode()
        headers = [(b'host', b'testserver')]
        if body:
            headers.append((b'content-type', b'application/x-www-form-urlencoded'))
        if cookie:
            headers.append((b'cookie', f'{SESSION_COOKIE}={cookie}'.encode()))
        if https:
            headers.append((b'x-forwarded-proto', b'https'))
        sent = False
        async def receive():
            nonlocal sent
            if sent:
                return {'type': 'http.disconnect'}
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'method': 'POST' if body else 'GET', 'scheme': 'http', 'path': path,
                 'raw_path': path.encode(), 'query_string': b'', 'headers': headers,
                 'client': ('127.0.0.1', 1), 'server': ('testserver', 80), 'state': {}}
        return Request(scope, receive)

    def register_and_login(self, https=False):
        register = asyncio.run(self.endpoint('/register', 'POST')(self.request('/register', {
            'name': 'Ana Torres', 'email': 'ana@example.com', 'password': PASSWORD})))
        self.assertEqual(register.status_code, 303)
        login = asyncio.run(self.endpoint('/login', 'POST')(self.request('/login', {
            'email': 'ana@example.com', 'password': PASSWORD}, https=https)))
        self.assertEqual(login.status_code, 303)
        self.assertIn('HttpOnly', login.headers['set-cookie'])
        self.assertIn('SameSite=lax', login.headers['set-cookie'])
        return login

    def test_public_health_and_private_gradio_routes(self):
        health = self.endpoint('/healthz', 'GET')()
        self.assertEqual(health['estado'], 'activo')
        mount = next(r for r in self.app.routes if r.__class__.__name__ == 'Mount')
        self.assertIsNone(mount.app.auth_dependency(self.request('/config')))
        login = self.register_and_login()
        token = login.headers['set-cookie'].split(f'{SESSION_COOKIE}=', 1)[1].split(';', 1)[0]
        self.assertIsNotNone(mount.app.auth_dependency(self.request('/config', cookie=token)))

    def test_registration_duplicate_login_logout_and_secure_cookie(self):
        self.register_and_login()
        duplicate = asyncio.run(self.endpoint('/register', 'POST')(self.request('/register', {
            'name': 'Ana Torres', 'email': 'ANA@example.com', 'password': PASSWORD})))
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn('Este correo ya tiene una cuenta.', duplicate.body.decode())
        active = self.auth.connect().sesiones.find_one({'revocada_en': None})
        token_hash = active['token_hash']
        # Recuperamos el token desde una nueva respuesta de acceso y revocamos ese valor.
        login = asyncio.run(self.endpoint('/login', 'POST')(self.request('/login', {
            'email': 'ana@example.com', 'password': PASSWORD})))
        token = login.headers['set-cookie'].split(f'{SESSION_COOKIE}=', 1)[1].split(';', 1)[0]
        logout = self.endpoint('/logout', 'POST')(self.request('/logout', cookie=token))
        self.assertEqual(logout.status_code, 303)
        self.assertIn('Max-Age=0', logout.headers['set-cookie'])
        self.assertIsNone(self.auth.resolve_session(token))
        self.assertIsNotNone(token_hash)

        secure = asyncio.run(self.endpoint('/login', 'POST')(self.request('/login', {
            'email': 'ana@example.com', 'password': PASSWORD}, https=True)))
        self.assertIn('Secure', secure.headers['set-cookie'])

    def test_camera_and_prediction_operations_require_authentication(self):
        # La misma puerta ASGI cubre cola/callback (foto, cámara, guardado e historial).
        stack = self.app.build_middleware_stack()
        for path in ('/gradio_api/queue/join', '/gradio_api/call/analizar',
                     '/gradio_api/call/fotograma', '/gradio_api/call/guardar_camara',
                     '/gradio_api/call/historial'):
            with self.subTest(path=path):
                messages = []
                request = self.request(path, {'event': 'unauthorized'})
                async def send(message, target=messages):
                    target.append(message)
                asyncio.run(stack(request.scope, request.receive, send))
                start = next(m for m in messages if m['type'] == 'http.response.start')
                self.assertEqual(start['status'], 401)


class ProtectedArtifactsTests(unittest.TestCase):
    def test_four_protected_files_keep_their_verified_digests(self):
        root = Path(__file__).resolve().parents[1]
        expected = {
            'models/best.onnx': 'b90eb5240038be75cea6b1477ef23665882abad69c126c7257a5578722812eef',
            'models/best.json': 'b24374fea80eb90015ae53ceca2673188104fc46b1acd506911c1f7273d5b178',
            'entrega/original/train100/weights/best.pt': '57b2194e8cfb26de44eb93960193392965e4c46be3c75f8f22c81b5a37b7ed32',
            'entrega/original/train100/weights/last.pt': '005ecb8bd05c6f2bfba95d3deccdc2f9c112840fea398aae07807d15c8e8d72f',
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main(verbosity=2)
