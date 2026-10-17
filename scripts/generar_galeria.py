import csv
import html
from pathlib import Path

BASE = Path("/content/ecoguard")
ORIGEN = BASE / "candidatas.csv"
DESTINO = BASE / "galeria.html"

NOMBRES = {
    "agua_contaminada": "Contaminación del agua",
    "suelo_contaminado": "Contaminación del suelo",
    "aire_contaminado": "Contaminación del aire",
}

with ORIGEN.open(encoding="utf-8") as f:
    fotos = list(csv.DictReader(f))

partes = ["""
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HUÁNUCO ECOGUARD AI - Galería</title>
<style>
body {
  font-family: Arial, sans-serif;
  background: #f3f6f4;
  color: #1b3028;
  margin: 0;
  padding: 24px;
}
h1 { text-align: center; }
h2 { margin-top: 36px; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 16px;
}
.card {
  background: white;
  border: 1px solid #ddd;
  border-radius: 10px;
  overflow: hidden;
}
.card img {
  width: 100%;
  height: 170px;
  object-fit: cover;
  background: #eee;
}
.info { padding: 12px; }
.info p { font-size: 13px; overflow-wrap: anywhere; }
a { color: #126448; }
</style>
</head>
<body>
<h1>HUÁNUCO ECOGUARD AI</h1>
<p style="text-align:center">
Galería de fotografías candidatas para el entrenamiento
</p>
"""]

for clase, nombre in NOMBRES.items():
    seleccionadas = [
        x for x in fotos
        if x["clase_candidata"] == clase
    ]

    partes.append(
        f"<h2>{html.escape(nombre)} "
        f"({len(seleccionadas)})</h2>"
        '<div class="grid">'
    )

    for i, foto in enumerate(seleccionadas, 1):
        titulo = html.escape(foto.get("titulo", "") or "")
        miniatura = html.escape(
            foto.get("miniatura", "") or foto.get("url", ""),
            quote=True
        )
        fuente = html.escape(
            foto.get("fuente", "") or "",
            quote=True
        )
        licencia = html.escape(
            foto.get("licencia", "") or "Sin especificar"
        )

        partes.append(f"""
        <div class="card">
          <img src="{miniatura}" alt="{titulo}" loading="lazy">
          <div class="info">
            <strong>{i}. {titulo}</strong>
            <p>Licencia: {licencia}</p>
            <a href="{fuente}" target="_blank"
               rel="noopener noreferrer">Ver fuente original</a>
          </div>
        </div>
        """)

    partes.append("</div>")

partes.append("</body></html>")

DESTINO.write_text(
    "\n".join(partes),
    encoding="utf-8"
)

print("Galería generada:", DESTINO)
print("Total de fotografías:", len(fotos))
