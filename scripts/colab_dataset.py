"""Execute using colab exec -f; this script collects/reviews on CPU, never trains."""
import importlib.util
import os
import runpy
import sys
from pathlib import Path

missing = [p for p in ("PIL", "requests") if importlib.util.find_spec(p) is None]
if missing:
    raise RuntimeError(f"Faltan paquetes en Colab: {missing}; inspeccionar antes de instalar")

root = Path(os.environ.get("ECOGUARD_ROOT", "/content/ecoguard_v2"))
command = os.environ.get("ECOGUARD_COMMAND", "audit")
if command not in {"collect", "audit", "catalog-taco"}:
    raise ValueError("Este lanzador solo permite recopilación/auditoría; build requiere aprobación")
sys.argv = ["ecoguard_data.py", "--root", str(root), command]
if command == "collect":
    sys.argv += ["--source", os.environ.get("ECOGUARD_SOURCE", "commons"), "--limit", "80"]
runpy.run_path("/content/ecoguard_data.py", run_name="__main__")
