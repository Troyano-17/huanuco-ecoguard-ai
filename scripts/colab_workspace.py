"""Run installed Colab CLI with writable session cache and no debug credential logs.

Does not change HOME, installed packages, authentication files or remote sessions.
"""
import logging
import json
import shutil
import sys
from pathlib import Path

from colab_cli import cli
from colab_cli.common import state
from colab_cli.history import HistoryLogger


def main():
    cache = Path(__file__).resolve().parents[1] / ".runtime"
    cache.mkdir(mode=0o700, exist_ok=True)
    session_cache = cache / "sessions.json"
    original = Path.home() / ".config/colab-cli/sessions.json"
    # Una caché vacía o anterior a un cambio de máquina no debe ocultar la sesión WSL.
    refresh = not session_cache.exists()
    if original.exists() and session_cache.exists():
        primary = json.loads(original.read_text())
        cached = json.loads(session_cache.read_text())
        changed_machine = any(
            name not in cached or any(cached[name].get(key) != session.get(key)
                                      for key in ('url', 'endpoint'))
            for name, session in primary.items())
        refresh = (original.stat().st_mtime > session_cache.stat().st_mtime or
                   not cached or changed_machine)
    if original.exists() and refresh:
        shutil.copyfile(original, session_cache)
        session_cache.chmod(0o600)
    cli.setup_logging = lambda *_: logging.basicConfig(level=logging.ERROR)
    cli.auto_update.run_background_check = lambda: None
    state._history = HistoryLogger(str(cache / "history"))
    sys.argv[1:1] = ["--config", str(session_cache)]
    cli.main()


if __name__ == "__main__":
    main()
