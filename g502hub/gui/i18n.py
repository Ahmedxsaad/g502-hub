"""Internationalization (i18n) support for G502 Hub."""

from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from .. import settings

TRANSLATIONS_DIR = Path(__file__).parent / "translations"

AVAILABLE_LANGUAGES = {
    "auto": "System Default / 跟随系统",
    "en_US": "English",
    "zh_CN": "简体中文",
}

_app_translator = None
_qt_translator = None


def detect_system_language():
    """Detect the most appropriate supported language code from system locale."""
    sys_name = QLocale.system().name()
    if sys_name.startswith("zh"):
        return "zh_CN"
    if sys_name.startswith("en"):
        return "en_US"
    for code in AVAILABLE_LANGUAGES:
        if code != "auto" and (sys_name == code or sys_name.startswith(code.split("_")[0])):
            return code
    return "en_US"


def get_current_language():
    """Get the currently configured language setting ("auto", "zh_CN", "en_US", etc.)."""
    return settings.load().get("language", "auto")


def reset_translation(app=None):
    """Remove installed translators."""
    global _app_translator, _qt_translator
    if app is None:
        app = QApplication.instance()
    if app:
        if _app_translator is not None:
            app.removeTranslator(_app_translator)
            _app_translator = None
        if _qt_translator is not None:
            app.removeTranslator(_qt_translator)
            _qt_translator = None


def setup_translation(app=None, lang_code=None):
    """Install QTranslator on the QApplication. Returns the active language code."""
    global _app_translator, _qt_translator

    if app is None:
        app = QApplication.instance()
    if app is None:
        return "en_US"

    reset_translation(app)

    if lang_code is None:
        lang_code = get_current_language()

    effective_code = detect_system_language() if lang_code == "auto" else lang_code

    if effective_code != "en_US":
        qm_path = TRANSLATIONS_DIR / f"{effective_code}.qm"
        if qm_path.exists():
            _app_translator = QTranslator(app)
            if _app_translator.load(str(qm_path)):
                app.installTranslator(_app_translator)

        for qt_tr_dir in [
            Path("/usr/share/qt6/translations"),
            Path("/usr/lib/qt6/translations"),
            Path("/usr/share/qt/translations"),
        ]:
            qt_qm = qt_tr_dir / f"qtbase_{effective_code}.qm"
            if qt_qm.exists():
                _qt_translator = QTranslator(app)
                if _qt_translator.load(str(qt_qm)):
                    app.installTranslator(_qt_translator)
                break

    return effective_code
