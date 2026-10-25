from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from g502hub.gui import system  # noqa: E402


def test_embedded_udev_rule_matches_the_repository_file():
    assert system.UDEV_RULE == (Path(__file__).parent.parent / "udev/70-g502-hub.rules").read_text()


def test_autostart_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "AUTOSTART", tmp_path / "autostart" / "g502-hub.desktop")
    system.set_autostart(True)
    text = system.AUTOSTART.read_text()
    assert "Exec=" in text and "--tray" in text and "g502hub.gui" in text
    system.set_autostart(False)
    assert not system.autostart_enabled()
