"""Consultar checkpoints persistentes sin cargar PyTorch ni consumir GPU."""
import json
import os
import sys
sys.path.insert(0, '/content')
from persistencia_colab import STORE, require_drive, latest_snapshot

require_drive()
digest = os.environ['ECOGUARD_DATASET_SHA256']
run = STORE / 'runs' / ('train100-' + digest)
latest = latest_snapshot(run, digest)
print('=== RECUPERACIÓN ECOGUARD ===', flush=True)
if latest:
    path, metadata = latest
    print('CHECKPOINT VÁLIDO:', path, flush=True)
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)
else:
    print('No existe checkpoint persistente comprometido.', flush=True)
