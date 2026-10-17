import csv
import hashlib
import io
import re
import time
from pathlib import Path

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

BASE = Path("/content/ecoguard")
DESTINO = BASE / "pendientes_revision"
DESTINO.mkdir(parents=True, exist_ok=True)

API = "https://commons.wikimedia.org/w/api.php"

BUSQUEDAS = {
    "agua_contaminada": [
        "plastic waste in river",
        "polluted forest stream",
        "garbage in river water",
        "plastic pollution freshwater",
        "riverbank trash pollution",
    ],
    "suelo_contaminado": [
        "plastic litter forest floor",
        "garbage dumping countryside",
        "rural land pollution waste",
        "plastic waste in nature",
        "illegal dumping vegetation",
    ],
    "aire_contaminado": [
        "burning trash rural",
        "open burning solid waste",
        "garbage burning smoke",
        "waste burning countryside",
        "plastic waste burning smoke",
    ],
}

LICENCIAS = {
    "cc0", "cc by", "cc by-sa",
    "public domain", "public domain mark",
    "pdm", "pd"
}

sesion = requests.Session()
sesion.headers.update({
    "User-Agent": (
        "HuanucoEcoGuardAI/1.0 "
        "(academic image dataset; Wikimedia Commons research)"
    )
})

def limpiar_html(valor):
    return re.sub(r"<[^>]+>", "", str(valor or "")).strip()

def huella(imagen):
    """Hash perceptual sencillo para detectar imágenes parecidas."""
    gris = imagen.convert("L").resize((9, 8))
    pixels = list(gris.getdata())
    bits = 0

    for y in range(8):
        for x in range(8):
            izquierda = pixels[y * 9 + x]
            derecha = pixels[y * 9 + x + 1]
            bits = (bits << 1) | (izquierda > derecha)

    return bits

def duplicada(hash_nuevo, hashes):
    return any(
        (hash_nuevo ^ anterior).bit_count() <= 5
        for anterior in hashes
    )

registros = []
hashes = []
urls_vistas = set()

for clase, consultas in BUSQUEDAS.items():
    carpeta = DESTINO / clase
    carpeta.mkdir(exist_ok=True)

    aceptadas = 0

    for consulta in consultas:
        if aceptadas >= 35:
            break

        print(f"\n[{clase}] {consulta}", flush=True)

        parametros = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": consulta,
            "gsrnamespace": 6,
            "gsrlimit": 30,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 800,
        }

        try:
            respuesta = sesion.get(
                API, params=parametros, timeout=40
            )
            respuesta.raise_for_status()

            paginas = respuesta.json().get(
                "query", {}
            ).get("pages", {})

        except requests.RequestException as error:
            print("Error de búsqueda:", error)
            time.sleep(5)
            continue

        for pagina in paginas.values():
            if aceptadas >= 35:
                break

            info = pagina.get("imageinfo", [])
            if not info:
                continue

            imagen_info = info[0]
            url_original = imagen_info.get("url", "")

            if url_original in urls_vistas:
                continue

            urls_vistas.add(url_original)

            meta = imagen_info.get("extmetadata", {})
            licencia = limpiar_html(
                meta.get("LicenseShortName", {}).get("value")
            ).lower()

            licencia_normalizada = re.sub(
                r"[^a-z0-9]+", " ", licencia
            ).strip()

            if not any(
                licencia_normalizada == permitida
                or licencia_normalizada.startswith(permitida + " ")
                for permitida in LICENCIAS
            ):
                continue

            url = imagen_info.get("thumburl", url_original)

            try:
                descarga = sesion.get(url, timeout=30)
                descarga.raise_for_status()

                foto = Image.open(io.BytesIO(descarga.content))
                foto = ImageOps.exif_transpose(foto).convert("RGB")

                if min(foto.size) < 180:
                    continue

                hash_actual = huella(foto)

                if duplicada(hash_actual, hashes):
                    continue

                nombre = (
                    hashlib.sha256(
                        url_original.encode()
                    ).hexdigest()[:16] + ".jpg"
                )

                ruta = carpeta / nombre
                foto.save(ruta, "JPEG", quality=90)

                hashes.append(hash_actual)
                aceptadas += 1

                registros.append({
                    "clase_candidata": clase,
                    "archivo": str(ruta),
                    "titulo": pagina.get("title", ""),
                    "autor": limpiar_html(
                        meta.get("Artist", {}).get("value")
                    ),
                    "licencia": licencia,
                    "licencia_url": limpiar_html(
                        meta.get("LicenseUrl", {}).get("value")
                    ),
                    "fuente": imagen_info.get(
                        "descriptionurl", ""
                    ),
                    "url_original": url_original,
                    "estado": "pendiente_revision"
                })

            except (
                requests.RequestException,
                UnidentifiedImageError,
                OSError
            ):
                continue

        print("Descargadas en esta clase:", aceptadas)
        time.sleep(3)

archivo = BASE / "imagenes_pendientes.csv"

campos = [
    "clase_candidata", "archivo", "titulo",
    "autor", "licencia", "licencia_url",
    "fuente", "url_original", "estado"
]

with archivo.open(
    "w", newline="", encoding="utf-8"
) as f:
    escritor = csv.DictWriter(f, fieldnames=campos)
    escritor.writeheader()
    escritor.writerows(registros)

print("\n=== RESULTADOS ===")

for clase in BUSQUEDAS:
    cantidad = sum(
        r["clase_candidata"] == clase
        for r in registros
    )
    print(f"{clase}: {cantidad}")

print("Total descargadas:", len(registros))
print("Directorio:", DESTINO)
print("Metadatos:", archivo)
