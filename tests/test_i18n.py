"""Tests for internationalization (i18n) and translations."""

from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from g502hub import settings
from g502hub.gui import i18n, labels
from g502hub.gui.i18n import AVAILABLE_LANGUAGES, reset_translation, setup_translation
from g502hub.gui.pages import settings as settings_page
from g502hub.gui.pages.about import AboutPage
from g502hub.gui.pages.settings import SettingsPage
from g502hub.onboard import MouseButton


def test_available_languages():
    assert "auto" in AVAILABLE_LANGUAGES
    assert "zh_CN" in AVAILABLE_LANGUAGES
    assert "en_US" in AVAILABLE_LANGUAGES


def test_chinese_translation_loading():
    app = QApplication.instance() or QApplication([])
    try:
        effective = setup_translation(app, "zh_CN")
        assert effective == "zh_CN"

        # Test labels and bindings
        assert labels.button_name(0) == "G1 · 左键单击"
        assert labels.binding(MouseButton(0x0001), None) == "左键单击"
        assert labels.effect_label(0x01) == "常亮"

        # Test sample widget/page translation
        args = (MagicMock(), MagicMock(), MagicMock())
        about = AboutPage(*args)
        assert about.title == "关于"
        settings_page = SettingsPage(*args)
        assert settings_page.title == "系统设置"

        from g502hub.gui.app import Placeholder
        placeholder = Placeholder()
        assert placeholder.title.text() == "请连接你的 G502 HERO 鼠标"
        assert placeholder.detail.text() == "正在寻找鼠标设备…"
    finally:
        reset_translation(app)


def test_english_fallback():
    app = QApplication.instance() or QApplication([])
    try:
        effective = setup_translation(app, "en_US")
        assert effective == "en_US"

        assert labels.button_name(0) == "G1 · Left click"
        assert labels.binding(MouseButton(0x0001), None) == "Left click"
        assert labels.effect_label(0x01) == "Fixed"

        args = (MagicMock(), MagicMock(), MagicMock())
        about = AboutPage(*args)
        assert about.title == "ABOUT"

        from g502hub.gui.app import Placeholder
        placeholder = Placeholder()
        assert placeholder.title.text() == "Connect your G502 HERO"
        assert placeholder.detail.text() == "Looking for the mouse…"
    finally:
        reset_translation(app)


def test_picking_another_language_offers_a_restart(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings, "PATH", tmp_path / "settings.json")
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "en_US")
    box = MagicMock(StandardButton=settings_page.QMessageBox.StandardButton)
    monkeypatch.setattr(settings_page, "QMessageBox", box)
    page = SettingsPage(MagicMock(), MagicMock(), MagicMock())
    page.restart_app = MagicMock()

    def pick(code, answer=None):
        box.question.reset_mock()
        box.question.return_value = answer
        page.lang_box.setCurrentIndex(page.lang_box.findData(code))
        return box.question.called

    assert page.lang_hint.isHidden()
    assert not pick("en_US")  # what "System Default" already shows here
    assert page.lang_hint.isHidden()
    assert pick("zh_CN", box.StandardButton.No)
    assert not page.lang_hint.isHidden() and not page.restart_app.called
    assert not pick("auto")
    assert page.lang_hint.isHidden()
    assert pick("zh_CN", box.StandardButton.Yes)
    page.restart_app.assert_called_once()
    assert settings.load()["language"] == "zh_CN"
