import csv
import time
import requests
from pathlib import Path

DESTINO = Path("/content/ecoguard")
DESTINO.mkdir(parents=True, exist_ok=True)

API = "https://commons.wikimedia.org/w/api.php"

BUSQUEDAS = {
    "agua_contaminada": [
        "river pollution plastic",
        "stream water garbage"
    ],
    "suelo_contaminado": [
        "forest litter garbage",
        "illegal waste dumping"
    ],
    "aire_contaminado": [
        "burning garbage smoke",
        "open waste burning"
    ]
}

sesion = requests.Session()
sesion.headers.update({
    "User-Agent": "HuanucoEcoGuardAI/1.0 (academic image research; contact: https://commons.wikimedia.org)"
})

registros = []
vistos = set()

for clase, consultas in BUSQUEDAS.items():
    for consulta in consultas:
        print(f"Buscando {clase}: {consulta}", flush=True)

        parametros = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": consulta,
            "gsrnamespace": 6,
            "gsrlimit": 20,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 320
        }

        try:
            respuesta = sesion.get(
                API,
                params=parametros,
                timeout=40
            )

            print("HTTP:", respuesta.status_code)

            if respuesta.status_code in (401, 403, 429):
                print("Acceso restringido. Deteniendo búsquedas.")
                print(respuesta.text[:300])
                raise SystemExit(1)

            respuesta.raise_for_status()

            datos = respuesta.json()
            paginas = datos.get("query", {}).get("pages", {})

            for pagina in paginas.values():
                info = pagina.get("imageinfo", [])

                if not info:
                    continue

                imagen = info[0]
                url = imagen.get("url", "")

                if not url.lower().split("?")[0].endswith(
                    (".jpg", ".jpeg", ".png", ".webp")
                ):
                    continue

                if url in vistos:
                    continue

                vistos.add(url)
                meta = imagen.get("extmetadata", {})

                registros.append({
                    "clase_candidata": clase,
                    "titulo": pagina.get("title", ""),
                    "url": url,
                    "miniatura": imagen.get("thumburl", ""),
                    "autor": meta.get("Artist", {}).get("value", ""),
                    "licencia": meta.get("LicenseShortName", {}).get("value", ""),
                    "licencia_url": meta.get("LicenseUrl", {}).get("value", ""),
                    "fuente": imagen.get("descriptionurl", "")
                })

            print(f"Total acumulado: {len(registros)}")

        except requests.RequestException as error:
            print("Error:", error)

        time.sleep(3)

archivo = DESTINO / "candidatas.csv"

with archivo.open("w", newline="", encoding="utf-8") as f:
    campos = [
        "clase_candidata", "titulo", "url",
        "miniatura", "autor", "licencia",
        "licencia_url", "fuente"
    ]

    escritor = csv.DictWriter(f, fieldnames=campos)
    escritor.writeheader()
    escritor.writerows(registros)

print("\n=== RESULTADOS ===")
print("Total de candidatas:", len(registros))

for clase in BUSQUEDAS:
    cantidad = sum(
        r["clase_candidata"] == clase
        for r in registros
    )
    print(f"{clase}: {cantidad}")

print("Guardado en:", archivo)
