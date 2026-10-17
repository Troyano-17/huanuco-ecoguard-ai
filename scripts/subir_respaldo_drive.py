"""Alternativa WSL: Drive API resumable PATCH sobre un file ID existente.

No usa colab upload ni procesa imágenes. ADC OAuth de usuario con scope Drive.
El URI de reanudación es privado y se conserva únicamente en .runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

TIMEOUT = 180
CHUNK = 1024 * 1024  # Múltiplo de los 256 KiB exigidos por Drive.
TRANSIENT = (408, 429, 500, 502, 503, 504)
API = 'https://www.googleapis.com/drive/v3/files/'


def digest_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_retry(operation, sleep=time.sleep):
    import requests
    for attempt in range(4):
        try:
            response = operation()
            if response.status_code not in TRANSIENT:
                return response
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pass
        if attempt == 3:
            raise RuntimeError('Drive API inaccesible tras cuatro intentos; progreso conservado')
        sleep(2 ** attempt)


def response_offset(response, total):
    if response.status_code in (200, 201):
        return total
    if response.status_code == 308:
        value = response.headers.get('Range', '')
        if not value:
            return 0
        match = re.fullmatch(r'bytes=0-(\d+)', value)
        if not match or int(match[1]) >= total:
            raise RuntimeError('Rango de reanudación inválido')
        return int(match[1]) + 1
    if response.status_code in (404, 410):
        raise RuntimeError('Sesión resumable expirada; consulta el file ID antes de iniciar otra sesión')
    raise RuntimeError(f'Drive API HTTP {response.status_code}; no reintentar automáticamente')


def save_private(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def upload(session, path, file_id, cache):
    import requests
    total, digest = path.stat().st_size, digest_file(path)
    url = API + file_id
    metadata = read_retry(lambda: session.get(url, params={'fields': 'id,name,size,sha256Checksum'}, timeout=TIMEOUT))
    if metadata.status_code != 200:
        raise RuntimeError(f'No se puede consultar file ID: HTTP {metadata.status_code}')
    existing = metadata.json()
    if existing.get('sha256Checksum') == digest and int(existing.get('size', -1)) == total:
        print('DRIVE API: archivo ya íntegro; SHA256:', digest, flush=True)
        return
    saved = json.loads(cache.read_text()) if cache.exists() else None
    if saved and (saved['file_id'] != file_id or saved['sha256'] != digest or saved['size'] != total):
        raise RuntimeError('La sesión guardada corresponde a otro archivo/dataset; no reutilizar')
    if saved:
        uri = saved['uri']
    else:
        # PATCH del mismo file ID: no crea archivos duplicados. No reenviar datos
        # si no se recibió/persistió el URI de esta sesión.
        response = read_retry(lambda: session.patch(
            'https://www.googleapis.com/upload/drive/v3/files/' + file_id,
            params={'uploadType': 'resumable'}, json={'name': 'ecoguard-validacion.zip'},
            headers={'X-Upload-Content-Type': 'application/zip',
                     'X-Upload-Content-Length': str(total)}, timeout=TIMEOUT))
        if response.status_code not in (200, 201) or 'Location' not in response.headers:
            raise RuntimeError(f'No se obtuvo URI resumable: HTTP {response.status_code}')
        uri = response.headers['Location']
        save_private(cache, dict(uri=uri, file_id=file_id, sha256=digest, size=total))
    # Nunca enviar credenciales a un URI ajeno, incluso si la caché fue alterada.
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    if parsed.scheme != 'https' or parsed.hostname != 'www.googleapis.com':
        raise RuntimeError('URI resumable no pertenece a Google Drive')
    def probe():
        response = read_retry(lambda: session.put(uri, data=b'', headers={
            'Content-Length': '0', 'Content-Range': f'bytes */{total}'}, timeout=TIMEOUT))
        return response_offset(response, total)
    offset = probe()
    with path.open('rb') as stream:
        failures = 0
        while offset < total:
            stream.seek(offset)
            block = stream.read(min(CHUNK, total - offset))
            try:
                response = session.put(uri, data=block, headers={
                    'Content-Type': 'application/zip', 'Content-Length': str(len(block)),
                    'Content-Range': f'bytes {offset}-{offset+len(block)-1}/{total}'}, timeout=TIMEOUT)
                if response.status_code in TRANSIENT:
                    raise requests.exceptions.ConnectionError('HTTP transitorio')
                next_offset = response_offset(response, total)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                failures += 1
                if failures > 3:
                    raise RuntimeError('Transporte interrumpido; URI persistido. Retomar con el mismo comando') from None
                time.sleep(2 ** (failures - 1))
                # La respuesta pudo perderse después del commit: consultar primero.
                next_offset = probe()
            if next_offset < offset or next_offset > offset + len(block):
                raise RuntimeError('Progreso ambiguo: posible escritor concurrente; detener')
            if next_offset == offset and failures == 0:
                failures = 1
            elif next_offset > offset:
                failures = 0
            elif failures >= 3:
                raise RuntimeError('Drive no confirma progreso; sesión conservada')
            else:
                failures += 1
            offset = next_offset
            print(f'DRIVE API: {offset}/{total} bytes confirmados', flush=True)
    # Verificación independiente del contenido remoto, también si se perdió el ACK final.
    def verify():
        response = session.get(url, params={'alt': 'media'}, stream=True, timeout=TIMEOUT)
        if response.status_code != 200:
            response.close()
            raise RuntimeError(f'Verificación remota HTTP {response.status_code}')
        remote_hash = hashlib.sha256()
        with response:
            for chunk in response.iter_content(CHUNK):
                remote_hash.update(chunk)
        return remote_hash.hexdigest()
    remote_digest = None
    for attempt in range(4):
        try:
            remote_digest = verify()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == 3:
                raise RuntimeError('Subida completada; falta confirmar SHA256 remoto') from None
            time.sleep(2 ** attempt)
    if remote_digest != digest:
        raise RuntimeError('SHA256 del archivo remoto no coincide')
    cache.unlink(missing_ok=True)
    print('DRIVE API: subida y SHA256 remoto verificados:', digest, 'file ID:', file_id, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file-id', required=True, help='ID de archivo destino existente y reservado para este respaldo')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.file_id):
        raise RuntimeError('File ID inválido')
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive'])
    root = Path(__file__).resolve().parents[1]
    with AuthorizedSession(credentials, max_refresh_attempts=1, refresh_timeout=TIMEOUT) as session:
        upload(session, root / 'ecoguard-validacion.zip', args.file_id,
               root / '.runtime' / ('drive-resumable-' + args.file_id + '.json'))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No volcar excepciones HTTP con URI privado o credenciales.
        if isinstance(exc, RuntimeError):
            print('DRIVE API:', str(exc), file=sys.stderr)
        else:
            print('DRIVE API:', type(exc).__name__, 'consulta autenticación/red; progreso conservado', file=sys.stderr)
        sys.exit(1)
