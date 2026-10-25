from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from g502hub.gui import system  # noqa: E402


def test_embedded_udev_rule_matches_the_repository_file():
    assert system.UDEV_RULE == (Path(__file__).parent.parent / "udev/70-g502-hub.rules").read_text()


def test_udev_rule_status(tmp_path, monkeypatch):
    etc, lib = tmp_path / "etc.rules", tmp_path / "lib.rules"
    monkeypatch.setattr(system, "UDEV_RULE_PATH", str(etc))
    monkeypatch.setattr(system, "PACKAGED_RULE_PATH", str(lib))
    assert system.udev_rule_status() == "missing"
    etc.write_text("# an earlier version\n")
    assert system.udev_rule_status() == "old"
    lib.write_text(system.UDEV_RULE)
    assert system.udev_rule_status() == "current"


def test_autostart_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "AUTOSTART", tmp_path / "autostart" / "g502-hub.desktop")
    system.set_autostart(True)
    text = system.AUTOSTART.read_text()
    assert "Exec=" in text and "--tray" in text and "g502hub.gui" in text
    system.set_autostart(False)
    assert not system.autostart_enabled()
