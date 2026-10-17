"""Candidate collection and fail-closed dataset preparation. CPU only.

Usage: python ecoguard_data.py --root /content/ecoguard_v2 collect
       python ecoguard_data.py --root /content/ecoguard_v2 audit
       python ecoguard_data.py --root /content/ecoguard_v2 build --approval approval.json
"""
import argparse
import csv
import hashlib
import html
import io
import json
import random
import re
import shutil
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

CLASSES = ("agua_contaminada", "suelo_contaminado", "aire_contaminado")
FIELDS = ("id", "archivo", "categoria", "fuente", "url", "autor", "licencia",
          "licencia_url", "procedencia", "ubicacion", "modificaciones", "sha256",
          "estado", "revisor", "fecha_revision", "evidencia", "grupo_escena")
QUERIES = {
    CLASSES[0]: ['"river" "plastic waste"', '"stream" "garbage"',
                 '"río" "basura" "Peru"', '"Huánuco" "contaminación"'],
    CLASSES[1]: ['"forest" "litter"', '"illegal dumping" "vegetation"',
                 '"basura" "campo"', '"Huánuco" "residuos"'],
    CLASSES[2]: ['"burning garbage"', '"burning waste" "smoke"',
                 '"quema de basura"', '"burning rubbish"'],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read_manifest(root):
    path = root / "manifest.csv"
    return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []


def write_manifest(root, rows):
    path = root / "manifest.csv"
    if path.exists():
        backup = root / "history" / f"manifest-{time.time_ns()}.csv"
        backup.parent.mkdir(exist_ok=True)
        shutil.copy2(path, backup)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def clean(text):
    return html.unescape(re.sub(r"<[^>]*>", "", str(text or ""))).strip()


def reusable_license(name, url):
    # Conservative allowlist; no substring matching of an arbitrary licence name.
    name = name.lower().strip()
    host = urlparse(url).hostname
    return ((bool(re.fullmatch(r"cc by(?:-sa)? [234]\.0", name))
             and host in {"creativecommons.org", "www.creativecommons.org"})
            or name in {"cc0", "cc0 1.0", "public domain", "public domain mark"})


def session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "HuanucoEcoGuardAI/2.0 (academic dataset curation)"
    return s


def fetch(s, url, *, params=None, max_bytes=40_000_000):
    if urlparse(url).scheme != "https":
        raise ValueError("Solo se permite HTTPS")
    with s.get(url, params=params, stream=True, timeout=(15, 60)) as r:
        r.raise_for_status()
        result = bytearray()
        for chunk in r.iter_content(65536):
            result.extend(chunk)
            if len(result) > max_bytes:
                raise ValueError("Archivo demasiado grande")
        return bytes(result)


def decode(data):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {"JPEG", "PNG"} or getattr(image, "n_frames", 1) != 1:
            raise ValueError("Se requiere fotografía JPG/PNG de un solo fotograma")
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if min(image.size) < 224:
            raise ValueError("Resolución inferior a 224 píxeles")
        return ImageOps.exif_transpose(image).convert("RGB")


def dhash(image):
    pixels = list(image.convert("L").resize((9, 8)).getdata())
    result = 0
    for y in range(8):
        for x in range(8):
            result = (result << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return result


def add_candidate(root, rows, s, record):
    if any(r["id"] == record["id"] for r in rows):
        return
    data = fetch(s, record["url"])
    image = decode(data)
    image.close()
    digest = hashlib.sha256(data).hexdigest()
    if any(r["sha256"] == digest for r in rows):
        return
    suffix = ".png" if data.startswith(b"\x89PNG") else ".jpg"
    relative = Path("candidates") / (record["id"] + suffix)
    (root / relative).write_bytes(data)
    record.update(archivo=relative.as_posix(), sha256=digest,
                  estado="pendiente", revisor="", fecha_revision="", evidencia="",
                  grupo_escena="", modificaciones="ninguna; archivo original")
    rows.append({field: record.get(field, "") for field in FIELDS})
    write_manifest(root, rows)


def collect_commons(root, rows, limit):
    s = session()
    snapshots = root / "sources"
    for category, queries in QUERIES.items():
        for query in queries:
            if sum(r["categoria"] == category for r in rows) >= limit:
                break
            params = dict(action="query", format="json", generator="search",
                          gsrsearch=query, gsrnamespace=6, gsrlimit=30,
                          prop="imageinfo", iiprop="url|extmetadata")
            raw = fetch(s, "https://commons.wikimedia.org/w/api.php", params=params)
            key = hashlib.sha256(query.encode()).hexdigest()[:12]
            snapshot = snapshots / f"commons-{key}.json"
            snapshot.write_bytes(raw)
            pages = json.loads(raw).get("query", {}).get("pages", {})
            for page in pages.values():
                if sum(r["categoria"] == category for r in rows) >= limit:
                    break
                infos = page.get("imageinfo", [])
                if not infos:
                    continue
                info = infos[0]
                meta = info.get("extmetadata", {})
                value = lambda key: clean(meta.get(key, {}).get("value", ""))
                name, license_url = value("LicenseShortName"), value("LicenseUrl")
                description = value("ImageDescription")
                if not reusable_license(name, license_url) or not value("Artist"):
                    continue
                if re.search(r"scan|book page|infographic|AI.generated|text page",
                             description + page["title"], re.I):
                    continue
                if Path(urlparse(info["url"]).path).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    continue
                record = dict(id=f"commons-{page['pageid']}", categoria=category,
                              fuente=info["descriptionurl"], url=info["url"],
                              autor=value("Artist"), licencia=name, licencia_url=license_url,
                              procedencia=snapshot.relative_to(root).as_posix(),
                              ubicacion="pendiente de verificar")
                try:
                    add_candidate(root, rows, s, record)
                except Exception as e:
                    log_error(root, record["id"], e)
                time.sleep(0.5)
            time.sleep(1)


def collect_floatwaste(root, rows, limit):
    s = session()
    repo = "OliviaWuYJ/sc-floatwaste"
    raw = fetch(s, f"https://huggingface.co/api/datasets/{repo}")
    info = json.loads(raw)
    revision = info["sha"]
    (root / "sources/floatwaste-api.json").write_bytes(raw)
    base = f"https://huggingface.co/datasets/{repo}/resolve/{revision}/"
    for filename in ("README.md", "LICENSE", "annotations/instances_train.json"):
        content = fetch(s, base + filename, max_bytes=80_000_000)
        (root / "sources" / ("floatwaste-" + Path(filename).name)).write_bytes(content)
    annotations = json.loads((root / "sources/floatwaste-instances_train.json").read_bytes())
    positives = {a["image_id"] for a in annotations["annotations"] if a.get("area", 0) > 0}
    images = [im for im in annotations["images"] if im["id"] in positives
              and "Indonesia/" in im["file_name"]]
    random.Random(42).shuffle(images)
    count = 0
    for im in images:
        if count >= limit:
            break
        filename = im["file_name"]
        record = dict(id=f"floatwaste-{im['id']}", categoria=CLASSES[0],
                      fuente=f"https://huggingface.co/datasets/{repo}/blob/{revision}/{quote(filename)}",
                      url=base + quote(filename), autor="Yujiao Wu et al. (ver ficha conservada)",
                      licencia="CC BY 4.0", licencia_url="https://creativecommons.org/licenses/by/4.0/",
                      procedencia="sources/floatwaste-README.md", ubicacion="Indonesia; según ficha")
        try:
            before = len(rows)
            add_candidate(root, rows, s, record)
            count += len(rows) - before
        except Exception as e:
            log_error(root, record["id"], e)
        time.sleep(0.3)


def taco_proposals(data):
    backgrounds = {b["id"]: b["name"].lower() for b in data["scene_categories"]}
    scene_names = defaultdict(set)
    for item in data["scene_annotations"]:
        scene_names[item["image_id"]].update(backgrounds.get(i, "") for i in item["background_ids"])
    proposal = {}
    for image_id, names in scene_names.items():
        if "water" in names:
            proposal[image_id] = CLASSES[0]
        elif "vegetation" in names:
            proposal[image_id] = CLASSES[1]
    records = []
    for im in data["images"]:
        if im["id"] in proposal:
            records.append(dict(id=f"taco-{im['id']}", categoria=proposal[im["id"]],
                                url=im.get("flickr_url", ""), archivo=im["file_name"],
                                licencia_original=im.get("license"),
                                estado="pendiente_autor_licencia_y_revision_visual"))
    return records


def catalog_taco(root):
    # Official COCO has incomplete image rights; never inherit the software MIT licence.
    s = session()
    raw = fetch(s, "https://raw.githubusercontent.com/pedropro/TACO/master/data/annotations.json",
                max_bytes=80_000_000)
    (root / "sources/taco-annotations.json").write_bytes(raw)
    records = taco_proposals(json.loads(raw))
    (root / "sources/taco-proposals.json").write_text(json.dumps(records, indent=2))
    print(f"TACO: {len(records)} propuestas; no se descargan fotos con derechos incompletos")


def log_error(root, item, error):
    with (root / "errors.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(time=now(), item=item, error=str(error)), ensure_ascii=False) + "\n")
    print(item, type(error).__name__, str(error), flush=True)


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Ruta fuera del proyecto de datos")
    return path


def inspect(root, rows):
    errors, images, hashes, pairs = [], {}, {}, []
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("IDs duplicados")
    for row in rows:
        try:
            path = safe_path(root, row["archivo"])
            if sha(path) != row["sha256"]:
                raise ValueError("Hash distinto del manifiesto")
            image = decode(path.read_bytes())
            hashes[row["id"]] = dhash(image)
            images[row["id"]] = image
        except Exception as e:
            errors.append(f"{row['id']}: {e}")
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            exact = a["sha256"] == b["sha256"]
            if a["id"] in hashes and b["id"] in hashes:
                distance = (hashes[a["id"]] ^ hashes[b["id"]]).bit_count()
                if exact or distance <= 6:
                    pairs.append(dict(a=a["id"], b=b["id"], exact=exact, distance=distance))
    return errors, images, pairs


def audit(root):
    from PIL import Image, ImageDraw, ImageOps
    rows = read_manifest(root)
    errors, images, pairs = inspect(root, rows)
    review = root / "review"
    review.mkdir(exist_ok=True)
    parts = ['<!doctype html><html lang="es"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>Revisión HUÁNUCO ECOGUARD AI</title>',
             '<style>body{font:16px system-ui;background:#edf5ef;margin:24px}',
             'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}',
             'article{background:white;padding:14px;border-radius:12px;overflow-wrap:anywhere}',
             'img{width:100%;height:240px;object-fit:contain}</style>',
             '<h1>HUÁNUCO ECOGUARD AI · revisión obligatoria</h1>',
             '<p>Propuestas pendientes. Ver original antes de aprobar. Editar manifest.csv según docs/REVISION.md.</p><main>']
    for category in CLASSES:
        selected = [r for r in rows if r["categoria"] == category and r["id"] in images]
        for page in range(0, len(selected), 20):
            subset = selected[page:page + 20]
            sheet = Image.new("RGB", (1200, 4 * 220), "white")
            draw = ImageDraw.Draw(sheet)
            for j, row in enumerate(subset):
                x, y = j % 5 * 240, j // 5 * 220
                thumb = ImageOps.contain(images[row["id"]], (230, 185))
                sheet.paste(thumb, (x, y))
                draw.text((x + 4, y + 190), row["id"], fill="black")
            sheet.save(review / f"{category}-{page // 20 + 1}.jpg")
    for row in rows:
        e = lambda field: html.escape(row[field], quote=True)
        parts.append(f'<article><h2>{e("id")}</h2><a href="../{e("archivo")}">'
                     f'<img src="../{e("archivo")}" loading="lazy"></a>'
                     f'<p>{e("categoria")} · {e("estado")}</p><p>{e("autor")} · {e("licencia")}</p>'
                     f'<a href="{e("fuente")}">Fuente y licencia</a></article>')
    parts.append("</main></html>")
    (review / "gallery.html").write_text("\n".join(parts), encoding="utf-8")
    report = dict(time=now(), total=len(rows), counts=dict(Counter(r["categoria"] for r in rows)),
                  states=dict(Counter(r["estado"] for r in rows)), errors=errors,
                  duplicate_pairs=pairs, manifest_sha256=sha(root / "manifest.csv") if rows else None)
    (review / "audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    for image in images.values():
        image.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def validate_reviews(rows):
    if not rows:
        raise ValueError("No hay fotografías validadas")
    for row in rows:
        if row["estado"] not in {"aprobada", "rechazada"}:
            raise ValueError(f"{row['id']}: revisión semántica pendiente")
        if not all(row.get(k, "").strip() for k in ("revisor", "fecha_revision", "evidencia")):
            raise ValueError(f"{row['id']}: falta evidencia de revisión")
        if row["estado"] == "aprobada":
            if row["categoria"] not in CLASSES:
                raise ValueError("Categoría fuera del alcance")
            for key in ("autor", "fuente", "procedencia", "grupo_escena", "ubicacion"):
                if not row.get(key, "").strip() or "pendiente" in row[key].lower():
                    raise ValueError(f"{row['id']}: falta {key}")
            if not reusable_license(row["licencia"], row["licencia_url"]):
                raise ValueError("Licencia no admitida o incompleta")


def assign_splits(rows, pairs, seed=42):
    # Connected components join review scene groups AND perceptual neighbours.
    parent = {r["id"]: r["id"] for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    groups = {}
    for row in rows:
        group = row["grupo_escena"]
        if group in groups:
            union(row["id"], groups[group])
        groups[group] = row["id"]
    for pair in pairs:
        if pair["a"] in parent and pair["b"] in parent:
            union(pair["a"], pair["b"])
    components = defaultdict(list)
    for row in rows:
        components[find(row["id"])].append(row)
    totals = Counter(r["categoria"] for r in rows)
    counts = {split: Counter() for split in ("train", "val", "test")}
    fractions = dict(train=0.7, val=0.15, test=0.15)
    ordered = list(components.values())
    random.Random(seed).shuffle(ordered)
    ordered.sort(key=len, reverse=True)
    assignments = {}
    for component in ordered:
        additions = Counter(r["categoria"] for r in component)

        def cost(split):
            return sum(((counts[s][c] + (additions[c] if s == split else 0)
                         - totals[c] * fractions[s]) / max(1, totals[c])) ** 2
                       for s in counts for c in CLASSES)

        chosen = min(counts, key=cost)
        counts[chosen].update(additions)
        for row in component:
            assignments[row["id"]] = chosen
    if any(counts[s][c] < 2 for s in counts for c in CLASSES):
        raise ValueError("No se pueden obtener tres particiones con >=2 fotos/clase sin separar escenas")
    # Fail rather than silently claiming balance with badly skewed scene groups.
    if any(max(counts[s].values()) > 1.5 * min(counts[s].values()) for s in counts):
        raise ValueError("Particiones desequilibradas: recopilar escenas independientes")
    return assignments


def build(root, approval_path):
    rows = read_manifest(root)
    validate_reviews(rows)
    approval = json.loads(Path(approval_path).read_text())
    digest = sha(root / "manifest.csv")
    if approval.get("manifest_sha256") != digest or approval.get("approved") is not True:
        raise ValueError("Falta aprobación del manifiesto exacto")
    if not approval.get("reviewer") or not approval.get("date"):
        raise ValueError("Falta revisor/fecha en aprobación")
    approved = [r for r in rows if r["estado"] == "aprobada"]
    counts = Counter(r["categoria"] for r in approved)
    if len(approved) < 50 or any(counts[c] < 16 for c in CLASSES):
        raise ValueError("Mínimo 50 originales; al menos 16 por clase")
    if max(counts.values()) - min(counts.values()) > 1:
        raise ValueError("Seleccionar cantidades equilibradas por clase (diferencia <=1)")
    errors, images, pairs = inspect(root, approved)
    for image in images.values():
        image.close()
    if errors:
        raise ValueError(str(errors))
    for row in approved:
        if not safe_path(root, row["procedencia"]).is_file():
            raise ValueError(f"{row['id']}: no existe respaldo de procedencia")
    if any(p["exact"] for p in pairs):
        raise ValueError("Rechazar duplicados exactos antes de construir")
    assignments = assign_splits(approved, pairs)
    destination = root / "dataset"
    if destination.exists():
        raise ValueError("Dataset ya existe; conservarlo y usar otra carpeta versionada")
    staging = root / f"dataset-staging-{time.time_ns()}"
    for split in ("train", "val", "test"):
        for category in CLASSES:
            (staging / split / category).mkdir(parents=True)
    inventory = []
    for row in approved:
        relative = Path(assignments[row["id"]]) / row["categoria"] / Path(row["archivo"]).name
        shutil.copy2(safe_path(root, row["archivo"]), staging / relative)
        inventory.append(dict(id=row["id"], path=relative.as_posix(), sha256=row["sha256"],
                              group=row["grupo_escena"]))
    (staging / "validation.json").write_text(json.dumps(dict(time=now(), seed=42,
        manifest_sha256=digest, approval=approval, files=inventory), indent=2))
    staging.rename(destination)
    print("Dataset construido:", destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/content/ecoguard_v2"))
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--source", choices=("commons", "floatwaste"), default="commons")
    collect.add_argument("--limit", type=int, default=80)
    sub.add_parser("audit")
    sub.add_parser("catalog-taco")
    builder = sub.add_parser("build")
    builder.add_argument("--approval", required=True, type=Path)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    (args.root / "candidates").mkdir(exist_ok=True)
    (args.root / "sources").mkdir(exist_ok=True)
    if args.command == "collect":
        rows = read_manifest(args.root)
        if not (args.root / "manifest.csv").exists():
            write_manifest(args.root, rows)
        fn = collect_commons if args.source == "commons" else collect_floatwaste
        try:
            fn(args.root, rows, args.limit)
        except Exception as e:
            log_error(args.root, "source-" + args.source, e)
            raise SystemExit(1) from None
    elif args.command == "audit":
        audit(args.root)
    elif args.command == "build":
        build(args.root, args.approval)
    elif args.command == "catalog-taco":
        catalog_taco(args.root)


if __name__ == "__main__":
    main()
