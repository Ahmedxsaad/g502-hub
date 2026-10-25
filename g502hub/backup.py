"""Full dumps of the mouse's onboard memory, and restoring them."""

import json
import time
from pathlib import Path

from . import onboard
from .device import ROM

BACKUP_DIR = Path.home() / ".local/share/g502-hub/backups"


def dump(dev):
    info = dev.onboard_info()
    sectors = {}
    for sector in list(range(info.sector_count)) + list(range(ROM, ROM + info.rom_profile_count + 1)):
        sectors[f"0x{sector:04X}"] = dev.read_sector(sector).hex()
    return {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "name": dev.name(),
        "firmware": [fw for _, fw in dev.firmware()],
        "mode": dev.get_mode(),
        "current_profile": dev.get_current_profile(),
        "sector_size": info.sector_size,
        "sectors": sectors,
    }


def save(data, path=None):
    if path is None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path = BACKUP_DIR / f"onboard-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path = Path(path)
    path.write_text(json.dumps(data, indent=1))
    return path


def load(path):
    data = json.loads(Path(path).read_text())
    data["sectors"] = {int(k, 16): bytes.fromhex(v) for k, v in data["sectors"].items()}
    return data


def restore(dev, data, log=print):
    """Write back every user sector that differs from the backup. Directory last."""
    info = dev.onboard_info()
    if data["sector_size"] != info.sector_size:
        raise ValueError("backup was made from a mouse with a different sector size")
    user = sorted(s for s in data["sectors"] if s < info.sector_count)
    written = []
    for sector in [s for s in user if s != 0] + [0]:
        want = data["sectors"][sector]
        if dev.read_sector(sector) == want:
            continue
        # Erased sectors in the backup have no valid CRC; restore them as they were
        dev.write_sector(sector, want, allow_bad_crc=not onboard.crc_ok(want))
        written.append(sector)
        log(f"restored sector 0x{sector:04X}")
    if written and data.get("current_profile"):
        dev.set_current_profile(data["current_profile"])
    return written
