"""Checking GitHub for a newer release, and updating copies made by the install script."""

import json
import os
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal

import g502hub

from .. import about, settings

LATEST_URL = f"https://api.github.com/repos/{about.GITHUB}/g502-hub/releases/latest"
DAY = 24 * 3600
ROOT = Path(g502hub.__file__).resolve().parent.parent
# Where the install script keeps the app: a git clone of main
SCRIPT_APP = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "g502-hub" / "app"


@dataclass
class Release:
    version: str
    url: str


def parse_version(text):
    """"v0.3.0" or "0.3.0" -> (0, 3, 0)"""
    return tuple(int(part) for part in text.strip().removeprefix("v").split("."))


def is_newer(version, than=about.VERSION):
    try:
        return parse_version(version) > parse_version(than)
    except ValueError:
        return False


def fetch_latest():
    req = urllib.request.Request(LATEST_URL, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": f"g502-hub/{about.VERSION}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return Release(data["tag_name"].removeprefix("v"), data["html_url"])


def install_kind(root=ROOT):
    """How this copy got here, which decides how it's updated: "script" (the install script's
    clone), "source" (another checkout) or "package" (pacman, the AUR, pip)."""
    if not (root / "pyproject.toml").exists():
        return "package"
    if (root / ".git").exists() and root == SCRIPT_APP.resolve():
        return "script"
    return "source"


def update_script_copy(root=SCRIPT_APP):
    """What running the install script again does for the app: pull, then rewrite the menu entry."""
    for cmd in (["git", "-C", str(root), "pull", "--ff-only", "--quiet"],
                ["sh", str(root / "tools" / "install-desktop.sh")]):
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)


def _reason(error):
    if isinstance(error, subprocess.CalledProcessError):
        return (error.stderr or "").strip() or str(error)
    return str(getattr(error, "reason", None) or error)  # URLError keeps the useful part in .reason


class Updates(QObject):
    """Checks for a newer release, and updates script installs, on background threads.

    `changed` fires on the UI thread whenever there's something new to show;
    `updated(error)` once an update has finished (error is None if it went through).
    """

    changed = Signal()
    updated = Signal(object)
    _checked = Signal(object, object)
    _installed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = ROOT
        self.kind = install_kind()
        self.latest = None  # the newest Release, once a check went through
        self.error = None  # why the last check failed
        self.update_error = None
        self.checking = self.updating = self.installed = False
        self._checked.connect(self._check_done, Qt.ConnectionType.QueuedConnection)
        self._installed.connect(self._install_done, Qt.ConnectionType.QueuedConnection)

    @property
    def available(self):
        return self.latest is not None and is_newer(self.latest.version)

    def check_if_due(self):
        prefs = settings.load()
        if prefs.get("update_check", True) and time.time() - prefs.get("update_checked_at", 0) >= DAY:
            self.check()

    def check(self):
        if self.checking:
            return
        self.checking = True
        self.changed.emit()

        def run():
            try:
                self._checked.emit(fetch_latest(), None)
            except Exception as e:  # offline, rate limited, an unexpected reply
                self._checked.emit(None, e)
        threading.Thread(target=run, daemon=True).start()

    def _check_done(self, release, error):
        self.checking = False
        self.error = _reason(error) if error else None
        if release is not None:
            self.latest = release
            settings.update(update_checked_at=time.time())
        self.changed.emit()

    def install(self):
        if self.updating or self.kind != "script":
            return
        self.updating, self.update_error = True, None
        self.changed.emit()

        def run():
            try:
                update_script_copy()
                self._installed.emit(None)
            except (OSError, subprocess.SubprocessError) as e:
                self._installed.emit(e)
        threading.Thread(target=run, daemon=True).start()

    def _install_done(self, error):
        self.updating = False
        self.installed = error is None
        self.update_error = _reason(error) if error else None
        self.changed.emit()
        self.updated.emit(self.update_error)
