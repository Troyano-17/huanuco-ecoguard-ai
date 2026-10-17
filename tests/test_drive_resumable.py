"""Drive API con servidor simulado; no autentica ni accede a la red."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import subir_respaldo_drive as drive


class Response:
    def __init__(self, status, headers=None, payload=None, content=b''):
        self.status_code, self.headers = status, headers or {}
        self.payload, self.content = payload, content
    def json(self):
        return self.payload
    def iter_content(self, size):
        yield self.content
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass


class DriveResumableTests(unittest.TestCase):
    def test_tls_lost_ack_resumes_at_server_offset_instead_of_resending(self):
        import requests
        content = b'0123456789'
        calls, probes = [], []
        class Session:
            def get(self, url, **kwargs):
                if kwargs['params'].get('alt') == 'media':
                    return Response(200, content=content)
                return Response(200, payload={'id': 'reserved-file', 'size': '0'})
            def put(self, url, **kwargs):
                header = kwargs['headers']['Content-Range']
                if header == 'bytes */10':
                    probes.append(header)
                    return Response(308, {'Range': 'bytes=0-3' if len(probes) == 1 else 'bytes=0-7'})
                calls.append(header)
                if header == 'bytes 4-7/10':
                    raise requests.exceptions.SSLError('lost ACK after commit')
                return Response(200)
            def patch(self, *_args, **_kwargs):
                raise AssertionError('Existing resumable session must be reused')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'archive.zip'
            path.write_bytes(content)
            cache = Path(temp) / 'private.json'
            drive.save_private(cache, dict(file_id='reserved-file', size=10,
                sha256=hashlib.sha256(content).hexdigest(),
                uri='https://www.googleapis.com/upload/drive/v3/files/reserved-file?upload_id=private'))
            with patch.object(drive, 'CHUNK', 4), patch('time.sleep'):
                drive.upload(Session(), path, 'reserved-file', cache)
            self.assertEqual(calls, ['bytes 4-7/10', 'bytes 8-9/10'])
            self.assertEqual(len(probes), 2)
            self.assertFalse(cache.exists())

    def test_range_and_expiration_fail_closed(self):
        self.assertEqual(drive.response_offset(Response(308), 100), 0)
        self.assertEqual(drive.response_offset(Response(308, {'Range': 'bytes=0-42'}), 100), 43)
        with self.assertRaisesRegex(RuntimeError, 'Rango'):
            drive.response_offset(Response(308, {'Range': 'bytes=0-100'}), 100)
        with self.assertRaisesRegex(RuntimeError, 'expirada'):
            drive.response_offset(Response(404), 100)

    def test_completed_file_is_not_uploaded_again(self):
        content = b'complete'
        class Session:
            def get(self, *_args, **_kwargs):
                return Response(200, payload=dict(size=len(content), sha256Checksum=hashlib.sha256(content).hexdigest()))
            def patch(self, *_args, **_kwargs):
                raise AssertionError('Completed file must not be uploaded')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'archive.zip'
            path.write_bytes(content)
            drive.upload(Session(), path, 'reserved', Path(temp) / 'cache.json')

    def test_no_progress_is_bounded(self):
        class Session:
            def get(self, *_args, **_kwargs):
                return Response(200, payload={'size': '0'})
            def patch(self, *_args, **_kwargs):
                return Response(200, headers={'Location': 'https://www.googleapis.com/upload/drive/v3/files?upload_id=private'})
            def put(self, *_args, **_kwargs):
                return Response(308)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'archive.zip'
            path.write_bytes(b'data')
            cache = Path(temp) / 'cache.json'
            with self.assertRaisesRegex(RuntimeError, 'no confirma progreso'):
                drive.upload(Session(), path, 'reserved', cache)
            self.assertTrue(cache.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
