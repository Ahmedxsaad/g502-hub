"""The update check: versions, how a copy updates, the checker and what Settings shows. No network."""

import io
import json
import subprocess
import time
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from g502hub import about, settings
from g502hub.gui import updates
from g502hub.gui.app import MainWindow
from g502hub.gui.pages.settings import SettingsPage
from g502hub.gui.updates import Release, Updates

REAL_FETCH = updates.fetch_latest  # the tests replace it, so nothing reaches the network


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings, "PATH", tmp_path / "settings.json")
    monkeypatch.setattr(updates, "fetch_latest", MagicMock(side_effect=AssertionError("no network in tests")))


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_versions_compare_as_numbers():
    assert updates.parse_version("v0.3.0") == (0, 3, 0)
    assert updates.is_newer("0.10.0", "0.9.9")
    assert updates.is_newer("v1.0.0", "0.3.0")
    assert not updates.is_newer("0.3.0", "0.3.0")
    assert not updates.is_newer("0.2.9", "0.3.0")
    assert not updates.is_newer("garbage", "0.3.0")


def test_fetch_latest_reads_the_release(monkeypatch):
    reply = {"tag_name": "v0.4.0", "html_url": "https://github.com/x/releases/tag/v0.4.0"}
    seen = {}

    def urlopen(req, timeout):
        seen["url"], seen["agent"] = req.full_url, req.get_header("User-agent")
        return io.BytesIO(json.dumps(reply).encode())
    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    assert REAL_FETCH() == Release("0.4.0", reply["html_url"])
    assert seen["url"].endswith(f"/repos/{about.GITHUB}/g502-hub/releases/latest")
    assert seen["agent"] == f"g502-hub/{about.VERSION}"


def test_install_kind(monkeypatch, tmp_path):
    script = tmp_path / "data" / "g502-hub" / "app"
    monkeypatch.setattr(updates, "SCRIPT_APP", script)
    package = tmp_path / "site-packages"
    package.mkdir()
    assert updates.install_kind(package) == "package"
    for root in (script, tmp_path / "checkout"):
        (root / ".git").mkdir(parents=True)
        (root / "pyproject.toml").touch()
    assert updates.install_kind(script) == "script"
    assert updates.install_kind(tmp_path / "checkout") == "source"


def test_updating_a_script_copy_pulls_and_rewrites_the_menu_entry(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(updates.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    updates.update_script_copy(tmp_path)
    assert ran == [["git", "-C", str(tmp_path), "pull", "--ff-only", "--quiet"],
                   ["sh", str(tmp_path / "tools" / "install-desktop.sh")]]


def test_check_finds_a_newer_release():
    updates.fetch_latest.side_effect = None
    updates.fetch_latest.return_value = Release("99.0.0", "https://example.invalid/release")
    u = Updates()
    u.check()
    wait_for(lambda: not u.checking)
    assert u.available and u.latest.version == "99.0.0" and u.error is None
    assert time.time() - settings.load()["update_checked_at"] < 5


def test_check_reports_why_it_failed():
    updates.fetch_latest.side_effect = urllib.error.URLError("no connection")
    u = Updates()
    u.check()
    wait_for(lambda: not u.checking)
    assert not u.available and u.error == "no connection"
    assert "update_checked_at" not in settings.load()  # try again next time


def test_daily_check_respects_the_setting_and_the_last_check():
    u = Updates()
    u.check = MagicMock()
    u.check_if_due()
    assert u.check.call_count == 1  # never checked
    settings.update(update_checked_at=time.time() - 3600)
    u.check_if_due()
    assert u.check.call_count == 1  # checked an hour ago
    settings.update(update_checked_at=time.time() - 2 * updates.DAY)
    u.check_if_due()
    assert u.check.call_count == 2
    settings.update(update_check=False)
    u.check_if_due()
    assert u.check.call_count == 2


def test_install_only_for_script_copies(monkeypatch):
    copy = MagicMock()
    monkeypatch.setattr(updates, "update_script_copy", copy)
    u = Updates()
    u.kind = "package"
    u.install()
    assert not copy.called
    u.kind = "script"
    results = []
    u.updated.connect(results.append)
    u.install()
    wait_for(lambda: not u.updating)
    assert copy.called and u.installed and results == [None]
    copy.side_effect = subprocess.CalledProcessError(1, "git", stderr="fatal: not possible to fast-forward\n")
    u.installed = False
    u.install()
    wait_for(lambda: not u.updating)
    assert not u.installed and results[-1] == "fatal: not possible to fast-forward"


def page_with(kind, latest=None, installed=False):
    u = Updates()
    u.kind, u.latest, u.installed = kind, latest, installed
    page = SettingsPage(MagicMock(), MagicMock(), MagicMock(), u)
    page._show_updates()
    return page


def test_settings_shows_what_to_do():
    newer = Release("99.0.0", "https://example.invalid/release")
    page = page_with("script")
    assert page.update_btn.text() == "Check now" and page.notes_btn.isHidden()
    page = page_with("script", newer)
    assert page.update_btn.text() == "Update now" and not page.notes_btn.isHidden()
    page = page_with("package", newer)
    assert page.update_btn.text() == "Check now" and "yay -Syu" in page.update_status.text()
    page = page_with("source", newer)
    assert "git pull" in page.update_status.text()
    page = page_with("script", Release(about.VERSION, "https://example.invalid/release"))
    assert "is the latest version" in page.update_status.text() and page.notes_btn.isHidden()
    page = page_with("script", newer, installed=True)
    assert page.update_btn.text() == "Restart now"


def test_a_new_version_is_announced_once():
    u = Updates()
    u.latest = Release("99.0.0", "https://example.invalid/release")
    window = SimpleNamespace(updates=u, tray=MagicMock(), _status=MagicMock(), tr=lambda text: text)
    MainWindow._update_found(window)
    MainWindow._update_found(window)
    assert window.tray.showMessage.call_count == 1
    assert "99.0.0" in window._status.call_args.args[1]
