from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

BASE = Path("/content/ecoguard/pendientes_revision")
SALIDA = Path("/content/ecoguard/revision")
SALIDA.mkdir(parents=True, exist_ok=True)

CLASES = [
    "agua_contaminada",
    "suelo_contaminado",
    "aire_contaminado"
]

COLUMNAS = 5
ANCHO = 220
ALTO = 190

for clase in CLASES:
    carpeta = BASE / clase

    archivos = sorted(
        p for p in carpeta.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png")
    )

    filas = (len(archivos) + COLUMNAS - 1) // COLUMNAS

    lamina = Image.new(
        "RGB",
        (COLUMNAS * ANCHO, filas * ALTO + 50),
        "white"
    )

    dibujo = ImageDraw.Draw(lamina)
    dibujo.text((15, 15), clase, fill="black")

    for indice, archivo in enumerate(archivos):
        columna = indice % COLUMNAS
        fila = indice // COLUMNAS

        x = columna * ANCHO
        y = fila * ALTO + 50

        with Image.open(archivo) as original:
            imagen = ImageOps.fit(
                original.convert("RGB"),
                (ANCHO - 10, ALTO - 35)
            )

        lamina.paste(imagen, (x + 5, y + 5))

        dibujo.text(
            (x + 10, y + ALTO - 25),
            f"Imagen {indice + 1:02d}",
            fill="black"
        )

    destino = SALIDA / f"{clase}.jpg"
    lamina.save(destino, quality=90)

    print(f"{clase}: {len(archivos)} imágenes")
    print("Lámina:", destino)

print("\nRevisión visual preparada.")
