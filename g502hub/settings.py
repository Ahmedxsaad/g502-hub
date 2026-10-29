"""Small persistent app settings in ~/.config/g502-hub/settings.json."""

import fcntl
import json
import os
from pathlib import Path

PATH = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "g502-hub" / "settings.json"


def load():
    try:
        data = json.loads(PATH.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update(**values):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    # The settings window and service may update different keys concurrently.
    with PATH.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load()
        data.update(values)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(PATH)
