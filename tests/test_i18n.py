"""Tests for internationalization (i18n) and translations."""

from unittest.mock import MagicMock
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtWidgets import QApplication

from g502hub.gui import labels
from g502hub.gui.i18n import AVAILABLE_LANGUAGES, setup_translation, tr
from g502hub.gui.pages.about import AboutPage
from g502hub.gui.pages.assignments import AssignmentsPage
from g502hub.gui.pages.games import GamesPage
from g502hub.gui.pages.lighting import LightingPage
from g502hub.gui.pages.macros import MacrosPage
from g502hub.gui.pages.profiles import ProfilesPage
from g502hub.gui.pages.sensitivity import SensitivityPage
from g502hub.gui.pages.settings import SettingsPage


class DummyView(QObject):
    photoChanged = Signal()

    def __init__(self):
        super().__init__()
        self.skin = MagicMock(ready=True)
        self.fetcher = MagicMock(busy=False)


def test_available_languages():
    assert "auto" in AVAILABLE_LANGUAGES
    assert "zh_CN" in AVAILABLE_LANGUAGES
    assert "en_US" in AVAILABLE_LANGUAGES


def test_chinese_translation_loading():
    app = QApplication.instance() or QApplication([])

    # Setup translation for zh_CN
    effective = setup_translation(app, "zh_CN")
    assert effective == "zh_CN"

    # Test global/label translations
    assert tr("Connect your G502 HERO", "Placeholder") == "请连接你的 G502 HERO 鼠标"
    assert tr("Looking for the mouse…", "Placeholder") == "正在寻找鼠标设备…"
    assert tr("Macro", "Labels") == "宏"
    assert tr("Disabled", "Labels") == "已禁用"

    # Test dynamic labels
    assert labels.BUTTON_NAMES[0] == "G1 · 左键单击"
    assert labels.MOUSE_LABELS.get(0x0001) == "左键单击"
    assert labels.EFFECT_LABELS.get(0x01) == "常亮"

    # Test QObject / Page classes
    view = DummyView()
    args = (MagicMock(), view, MagicMock())

    about = AboutPage(*args)
    assert about.title == "关于"

    settings_page = SettingsPage(*args)
    assert settings_page.title == "系统设置"

    assign_page = AssignmentsPage(*args, MagicMock())
    assert assign_page.title == "按键分配"

    from g502hub.gui.live import DEFAULTS
    import copy
    live_mock = MagicMock()
    live_mock.options = copy.deepcopy(DEFAULTS)
    light_page = LightingPage(*args, live_mock)
    assert light_page.title == "LIGHTSYNC 灯效"

    sens_page = SensitivityPage(*args)
    assert sens_page.title == "灵敏度 (DPI)"

    prof_page = ProfilesPage(*args)
    assert prof_page.title == "板载配置"

    macro_page = MacrosPage(*args, MagicMock())
    assert macro_page.title == "宏管理"

    games_page = GamesPage(*args, MagicMock())
    assert games_page.title == "游戏与应用"


def test_english_fallback():
    app = QApplication.instance() or QApplication([])

    effective = setup_translation(app, "en_US")
    assert effective == "en_US"

    assert tr("Connect your G502 HERO", "Placeholder") == "Connect your G502 HERO"
    assert labels.BUTTON_NAMES[0] == "G1 · Left click"
    assert labels.MOUSE_LABELS.get(0x0001) == "Left click"

    view = DummyView()
    args = (MagicMock(), view, MagicMock())
    about = AboutPage(*args)
    assert about.title == "ABOUT"
