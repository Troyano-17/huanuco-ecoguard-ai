from pathlib import Path

base = Path("/content/ecoguard/pendientes_revision")

print("=== ESTADO DEL DATASET ===")

total = 0

for clase in [
    "agua_contaminada",
    "suelo_contaminado",
    "aire_contaminado"
]:
    carpeta = base / clase

    cantidad = len(list(carpeta.glob("*.jpg"))) if carpeta.exists() else 0

    print(f"{clase}: {cantidad}")
    total += cantidad

print("TOTAL:", total)
