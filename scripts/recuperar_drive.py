"""Lectura de Drive mediante ADC previamente autorizado. No inicia sesiones ni entrena."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import uuid
from artefactos import DELIVERY_SHA256, DATASET_SHA256, RUN_NAME, sha256, extract_original

SCOPE = 'https://www.googleapis.com/auth/drive.readonly'
API = 'https://www.googleapis.com/drive/v3/files'


def children(session, parent, name=None):
    query = f"'{parent}' in parents and trashed = false"
    if name:
        query += " and name = '" + name.replace("'", "\\'") + "'"
    result, token = [], None
    while True:
        response = session.get(API, params={'q': query, 'fields': 'nextPageToken,files(id,name,mimeType,size)',
                               'pageToken': token, 'pageSize': 1000}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f'Drive HTTP {response.status_code}; revisar autorización de solo lectura.')
        value = response.json()
        result.extend(value.get('files', []))
        token = value.get('nextPageToken')
        if not token:
            return result


def unique(items, description):
    if len(items) != 1:
        raise RuntimeError(f'{description}: se encontraron {len(items)} coincidencias. No se selecciona un respaldo ambiguo.')
    return items[0]['id']


def download(session, item, folder):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (uuid.uuid4().hex + '-' + item['name'])
    if Path(item['name']).name != item['name']:
        raise RuntimeError('Nombre remoto inseguro.')
    response = session.get(API + '/' + item['id'], params={'alt': 'media'}, stream=True, timeout=60)
    with response:
        if response.status_code != 200:
            raise RuntimeError(f'Descarga HTTP {response.status_code}.')
        with target.open('xb') as stream:
            for block in response.iter_content(1024 * 1024):
                stream.write(block)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', help='ID de la carpeta persistente si hay varias HuanucoEcoGuard')
    parser.add_argument('--descargar', action='store_true', help='Descarga entrega.zip si existe; no escribe en Drive')
    parser.add_argument('--salida', type=Path, default=Path('recuperados'))
    args = parser.parse_args()
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    from google.auth.exceptions import DefaultCredentialsError
    try:
        credentials, _ = google.auth.default(scopes=[SCOPE])
    except DefaultCredentialsError:
        raise RuntimeError('No hay credenciales ADC de Drive. Abre drive.google.com con la cuenta del entrenamiento; '
                           'busca HuanucoEcoGuard/runs/' + RUN_NAME + '/entrega.zip y descárgalo. '
                           'Después: python3 ecoguard.py recuperar --archivo /ruta/entrega.zip') from None
    with AuthorizedSession(credentials) as session:
        run = args.run_id
        if run and not re.fullmatch(r'[A-Za-z0-9_-]+', run):
            raise RuntimeError('ID de carpeta inválido.')
        if not run:
            store = unique(children(session, 'root', 'HuanucoEcoGuard'), 'HuanucoEcoGuard')
            runs = unique(children(session, store, 'runs'), 'runs')
            run = unique(children(session, runs, RUN_NAME), RUN_NAME)
        entries = children(session, run)
        print(json.dumps({'archivos_run': entries}, ensure_ascii=False, indent=2))
        archives = [e for e in entries if e['name'] == 'entrega.zip']
        if archives:
            unique(archives, 'entrega.zip')
            print('entrega.zip existe en Drive; integridad pendiente de descarga.')
            if args.descargar:
                target = download(session, archives[0], args.salida)
                if sha256(target) != DELIVERY_SHA256:
                    raise RuntimeError('ZIP descargado diferente del original; conservado sin extraer.')
                print('ZIP original verificado:', target)
        else:
            print('No existe entrega.zip en la carpeta consultada. Inspección de checkpoints:')
            checkpoints = [e for e in entries if e['name'] == 'checkpoints']
            if not checkpoints:
                print('No se encontró carpeta checkpoints.')
            else:
                for generation in children(session, unique(checkpoints, 'checkpoints')):
                    if generation['mimeType'] == 'application/vnd.google-apps.folder':
                        print(json.dumps({'generacion': generation, 'archivos': children(session, generation['id'])}))
                print('Descarga las generaciones con COMMITTED.json desde Drive. Verifica sus SHA256 con '
                      'persistencia_colab.valid_snapshot antes de utilizarlas. No equivalen al ZIP final.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('RECUPERACIÓN:', str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__ + ': autorización/red no disponible', file=sys.stderr)
        sys.exit(1)
