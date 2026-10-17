"""Solo Colab: validar el paquete existente y preparar revisión; nunca entrenar."""
import collections
import csv
import hashlib
import html
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tarfile


def main():
    if not Path('/content').is_dir() or importlib.util.find_spec('google.colab') is None:
        raise RuntimeError('Este programa solo puede ejecutarse dentro de Google Colab.')
    from PIL import Image, ImageOps
    import torch

    if not torch.cuda.is_available() or 'T4' not in torch.cuda.get_device_name(0):
        raise RuntimeError('Se requiere la sesión existente con GPU T4. No se crea otra sesión.')
    run_id = os.environ['ECOGUARD_RUN_ID']
    if not run_id.replace('-', '').isalnum():
        raise ValueError('Identificador de ejecución inválido')
    package = Path('/content/imagenes-165-candidatas.tar')
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    if digest != os.environ['ECOGUARD_PACKAGE_SHA256']:
        raise RuntimeError('SHA256 del paquete transferido incorrecto')
    root = Path('/content') / f'ecoguard-validacion-{run_id}'
    root.mkdir(exist_ok=False)
    originals = root / 'originales'
    originals.mkdir()
    review = root / 'revision'
    review.mkdir()
    mapping = {'RIOS CONTAMINADOS': 'agua_contaminada',
               'SUELOS CONTAMINADOS': 'suelo_contaminado',
               'INCENDIOS': 'aire_contaminado'}
    print('GPU:', torch.cuda.get_device_name(0), flush=True)
    print('Paquete SHA256:', digest, flush=True)
    print('Validación y conversión ejecutadas exclusivamente en Colab.', flush=True)
    with tarfile.open(package) as archive:
        members = archive.getmembers()
        files = [m for m in members if m.isfile()]
        if len(files) != 165:
            raise RuntimeError(f'Se esperaban 165 archivos, encontrados {len(files)}')
        for m in members:
            parts = Path(m.name).parts
            if (not m.isfile() or len(parts) != 3 or parts[0] != 'imagenes'
                    or parts[1] not in mapping or '..' in parts or Path(m.name).is_absolute()):
                raise RuntimeError(f'Entrada de paquete inesperada: {m.name}')
        if len({m.name for m in files}) != 165:
            raise RuntimeError('Rutas repetidas dentro del paquete')
        archive.extractall(originals, filter='data')

    rows, byte_seen, pixel_seen, perceptual = [], {}, {}, []
    for index, path in enumerate(sorted(originals.rglob('*'))):
        if not path.is_file():
            continue
        ident = f'ECO-{len(rows) + 1:03d}'
        row = dict(id=ident, original=str(path.relative_to(root)),
                   clase_propuesta=mapping[path.parent.name], estado_tecnico='',
                   formato='', ancho='', alto='', sha256='', pixel_sha256='',
                   duplicado_bytes_de='', duplicado_visual_de='', convertido='',
                   error='', tipo_error='', revision_semantica='pendiente', revisor='', evidencia='',
                   grupo_escena='', licencia='pendiente')
        payload = path.read_bytes()
        row['sha256'] = hashlib.sha256(payload).hexdigest()
        row['duplicado_bytes_de'] = byte_seen.get(row['sha256'], '')
        byte_seen.setdefault(row['sha256'], ident)
        try:
            with Image.open(io.BytesIO(payload)) as im:
                row['formato'] = im.format
                im.verify()
            with Image.open(io.BytesIO(payload)) as im:
                im.load()
                if getattr(im, 'n_frames', 1) != 1:
                    raise ValueError('Imagen multiframe: requiere revisión especial')
                rgb = ImageOps.exif_transpose(im).convert('RGB')
                row['ancho'], row['alto'] = rgb.size
                row['pixel_sha256'] = hashlib.sha256(
                    str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                row['duplicado_visual_de'] = pixel_seen.get(row['pixel_sha256'], '')
                pixel_seen.setdefault(row['pixel_sha256'], ident)
                small = list(rgb.convert('L').resize((9, 8)).getdata())
                dhash = sum((small[y*9+x] > small[y*9+x+1]) << (y*8+x)
                            for y in range(8) for x in range(8))
                perceptual.append((ident, dhash))
                target = review / row['clase_propuesta'] / f'{ident}.png'
                target.parent.mkdir(exist_ok=True)
                rgb.save(target, format='PNG')
                with Image.open(target) as check:
                    check.load()
                    if check.size != rgb.size or check.tobytes() != rgb.tobytes():
                        raise ValueError('La conversión PNG no coincide con los píxeles RGB')
                row['convertido'] = str(target.relative_to(root))
                row['estado_tecnico'] = 'valida'
        except Exception as exc:
            row['estado_tecnico'] = 'error'
            row['error'] = f'{type(exc).__name__}: {exc}'
            if path.suffix.lower() not in Image.registered_extensions():
                row['tipo_error'] = 'formato_o_codec_no_disponible'
            elif 'multiframe' in str(exc) or 'conversión PNG' in str(exc):
                row['tipo_error'] = 'requiere_revision_tecnica'
            else:
                row['tipo_error'] = 'corrupta_o_no_decodificable'
        rows.append(row)
        print(f"{ident} | {row['clase_propuesta']} | {row['estado_tecnico']} | "
              f"duplicado_bytes={row['duplicado_bytes_de'] or '-'} | "
              f"duplicado_visual={row['duplicado_visual_de'] or '-'} | "
              f"{row['original']} | {row['error']}", flush=True)

    pairs = [dict(a=a, b=b, distancia=(ha ^ hb).bit_count())
             for i, (a, ha) in enumerate(perceptual) for b, hb in perceptual[i+1:]
             if (ha ^ hb).bit_count() <= 6]
    with (root / 'manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    valid = [r for r in rows if r['estado_tecnico'] == 'valida']
    summary = dict(paquete_sha256=digest, total=len(rows), validas=len(valid),
                   errores=len(rows)-len(valid),
                   errores_por_tipo=dict(collections.Counter(r['tipo_error'] for r in rows
                                                             if r['tipo_error'])),
                   duplicados_bytes=sum(bool(r['duplicado_bytes_de']) for r in rows),
                   duplicados_pixeles=sum(bool(r['duplicado_visual_de']) for r in valid),
                   validas_unicas_pixeles=len({r['pixel_sha256'] for r in valid}),
                   pares_similares_pendientes=len(pairs), clases={}, entrenamiento='NO INICIADO')
    for cls in mapping.values():
        group = [r for r in rows if r['clase_propuesta'] == cls]
        good = [r for r in group if r['estado_tecnico'] == 'valida']
        summary['clases'][cls] = dict(candidatas=len(group), validas=len(good),
            errores=len(group)-len(good),
            duplicados_pixeles=sum(bool(r['duplicado_visual_de']) for r in good),
            revision_semantica='pendiente')
    (root / 'resultados.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (root / 'pares_similares.json').write_text(json.dumps(pairs, indent=2))
    rules = ('Agua: residuos visibles en ríos/quebradas. Suelo: residuos sobre suelo '
             'o vegetación. Aire: humo de quema de residuos; la carpeta INCENDIOS es '
             'solo una propuesta y requiere revisar incendios forestales y escenas ambiguas. '
             'La validez técnica no aprueba la clase ni los derechos de uso. '
             'Errores de decodificación pueden indicar corrupción o un códec no disponible.')
    cards = ['<!doctype html><meta charset="utf-8"><title>Revisión ECOGUARD</title>',
             '<style>img{max-width:320px;max-height:240px}article{display:inline-block;'
             'vertical-align:top;width:340px;margin:8px;overflow-wrap:anywhere}</style>',
             '<h1>Revisión pendiente de las tres clases</h1><p>' + html.escape(rules) + '</p>']
    for cls in mapping.values():
        cards.append('<h2>' + cls + '</h2>')
        for r in rows:
            if r['clase_propuesta'] != cls:
                continue
            cards.append('<article><h3>' + r['id'] + '</h3><p>' +
                         html.escape(json.dumps(r, ensure_ascii=False)) + '</p>')
            if r['convertido']:
                cards.append('<a href="' + html.escape(r['original'], quote=True) +
                             '"><img loading="lazy" src="' +
                             html.escape(r['convertido'], quote=True) + '"></a>')
            cards.append('</article>')
    cards.append('<h2>Pares similares: revisar manualmente</h2><pre>' +
                 html.escape(json.dumps(pairs, indent=2)) + '</pre>')
    (root / 'revision.html').write_text('\n'.join(cards), encoding='utf-8')
    # Comprobar que los originales extraídos siguen idénticos al paquete.
    with tarfile.open(package) as archive:
        for m in archive.getmembers():
            if hashlib.sha256(archive.extractfile(m).read()).digest() != hashlib.sha256(
                    (originals / m.name).read_bytes()).digest():
                raise RuntimeError('Un original cambió durante el proceso')
    print('\n=== RESULTADOS VERIFICABLES ===', flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(rules, flush=True)
    print('=== PARES SIMILARES (alertas, no duplicados confirmados) ===', flush=True)
    print(json.dumps(pairs, indent=2), flush=True)
    backup = Path(shutil.make_archive(str(root), 'zip', root))
    print('Respaldo remoto:', backup, flush=True)
    print('Respaldo SHA256:', hashlib.sha256(backup.read_bytes()).hexdigest(), flush=True)
    print('ENTRENAMIENTO BLOQUEADO: falta revisión y aprobación expresa de 100 épocas.', flush=True)
    print('ECOGUARD_VALIDACION_COMPLETA', flush=True)


if __name__ == '__main__':
    main()
