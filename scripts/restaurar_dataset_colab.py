"""Consulta del respaldo persistente; no procesa fotografías."""
import os
from pathlib import Path
import sys
sys.path.insert(0, '/content')
from persistencia_colab import STORE, require_drive, sha256

require_drive()
digest = os.environ['ECOGUARD_DATASET_SHA256']
archive = STORE / 'datasets' / digest / 'ecoguard-validacion.zip'
available = archive.is_file() and sha256(archive) == digest
print('ECOGUARD_DATASET=' + ('listo' if available else 'falta'), flush=True)
print('RESPALDO PERSISTENTE:', archive, 'SHA256 esperado:', digest, flush=True)
