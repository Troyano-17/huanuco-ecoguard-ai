#!/usr/bin/env bash
# Reutilizar los 165 PNG respaldados; no volver a convertir ni subir el TAR original.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec /home/troyano/proyectos/gpu-t4/.venv/bin/python scripts/entrenar_165_wsl.py run "$@"
