"""Human-readable names for buttons, actions and effects."""

from PySide6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from .. import onboard

BUTTON_NAMES = [
    QT_TRANSLATE_NOOP("Labels", "G1 · Left click"),
    QT_TRANSLATE_NOOP("Labels", "G2 · Right click"),
    QT_TRANSLATE_NOOP("Labels", "G3 · Wheel click"),
    QT_TRANSLATE_NOOP("Labels", "G4 · Back"),
    QT_TRANSLATE_NOOP("Labels", "G5 · Forward"),
    QT_TRANSLATE_NOOP("Labels", "G6 · Sniper"),
    QT_TRANSLATE_NOOP("Labels", "G7 · Front left"),
    QT_TRANSLATE_NOOP("Labels", "G8 · Behind G7"),
    QT_TRANSLATE_NOOP("Labels", "G9 · Behind wheel"),
    QT_TRANSLATE_NOOP("Labels", "Wheel tilt right"),
    QT_TRANSLATE_NOOP("Labels", "Wheel tilt left"),
]

MOUSE_LABELS = {
    0x0001: QT_TRANSLATE_NOOP("Labels", "Left click"),
    0x0002: QT_TRANSLATE_NOOP("Labels", "Right click"),
    0x0004: QT_TRANSLATE_NOOP("Labels", "Middle click"),
    0x0008: QT_TRANSLATE_NOOP("Labels", "Back"),
    0x0010: QT_TRANSLATE_NOOP("Labels", "Forward"),
}

SPECIAL_LABELS = {
    "noop": QT_TRANSLATE_NOOP("Labels", "Nothing"),
    "tilt-left": QT_TRANSLATE_NOOP("Labels", "Scroll left"),
    "tilt-right": QT_TRANSLATE_NOOP("Labels", "Scroll right"),
    "dpi-up": QT_TRANSLATE_NOOP("Labels", "DPI up"),
    "dpi-down": QT_TRANSLATE_NOOP("Labels", "DPI down"),
    "dpi-cycle": QT_TRANSLATE_NOOP("Labels", "DPI cycle"),
    "dpi-default": QT_TRANSLATE_NOOP("Labels", "DPI default"),
    "dpi-shift": QT_TRANSLATE_NOOP("Labels", "DPI shift (sniper)"),
    "profile-next": QT_TRANSLATE_NOOP("Labels", "Next profile"),
    "profile-prev": QT_TRANSLATE_NOOP("Labels", "Previous profile"),
    "profile-cycle": QT_TRANSLATE_NOOP("Labels", "Cycle profiles"),
    "gshift": QT_TRANSLATE_NOOP("Labels", "G-Shift"),
    "scroll-up": QT_TRANSLATE_NOOP("Labels", "Scroll up"),
    "scroll-down": QT_TRANSLATE_NOOP("Labels", "Scroll down"),
    "battery": QT_TRANSLATE_NOOP("Labels", "Battery status"),
    "mode-switch": QT_TRANSLATE_NOOP("Labels", "Mode switch"),
    "host": QT_TRANSLATE_NOOP("Labels", "Host button"),
}

CONSUMER_LABELS = {
    "play-pause": QT_TRANSLATE_NOOP("Labels", "Play / Pause"),
    "next-track": QT_TRANSLATE_NOOP("Labels", "Next track"),
    "prev-track": QT_TRANSLATE_NOOP("Labels", "Previous track"),
    "stop": QT_TRANSLATE_NOOP("Labels", "Stop"),
    "mute": QT_TRANSLATE_NOOP("Labels", "Mute"),
    "volume-up": QT_TRANSLATE_NOOP("Labels", "Volume up"),
    "volume-down": QT_TRANSLATE_NOOP("Labels", "Volume down"),
    "brightness-up": QT_TRANSLATE_NOOP("Labels", "Brightness up"),
    "brightness-down": QT_TRANSLATE_NOOP("Labels", "Brightness down"),
    "calculator": QT_TRANSLATE_NOOP("Labels", "Calculator"),
    "file-browser": QT_TRANSLATE_NOOP("Labels", "File manager"),
    "mail": QT_TRANSLATE_NOOP("Labels", "Mail"),
    "browser-home": QT_TRANSLATE_NOOP("Labels", "Browser home"),
    "browser-back": QT_TRANSLATE_NOOP("Labels", "Browser back"),
    "browser-forward": QT_TRANSLATE_NOOP("Labels", "Browser forward"),
    "browser-refresh": QT_TRANSLATE_NOOP("Labels", "Browser refresh"),
    "browser-search": QT_TRANSLATE_NOOP("Labels", "Search"),
}

EFFECT_LABELS = {
    0x00: QT_TRANSLATE_NOOP("Labels", "Off"),
    0x01: QT_TRANSLATE_NOOP("Labels", "Fixed"),
    0x0A: QT_TRANSLATE_NOOP("Labels", "Breathing"),
    0x03: QT_TRANSLATE_NOOP("Labels", "Color cycle"),
}


def button_name(idx):
    if 0 <= idx < len(BUTTON_NAMES):
        return QCoreApplication.translate("Labels", BUTTON_NAMES[idx])
    return f"G{idx + 1}"


def effect_label(code):
    lbl = EFFECT_LABELS.get(code)
    return QCoreApplication.translate("Labels", lbl) if lbl else None


def binding(b, keylabels):
    if isinstance(b, onboard.MouseButton):
        lbl = MOUSE_LABELS.get(b.mask)
        return QCoreApplication.translate("Labels", lbl) if lbl else b.describe().replace("button", "Button ")
    if isinstance(b, onboard.Key):
        return keylabels.combo(b.modifiers, b.usage)
    if isinstance(b, onboard.Consumer):
        name = b.describe().removeprefix("media ")
        lbl = CONSUMER_LABELS.get(name)
        return QCoreApplication.translate("Labels", lbl) if lbl else name
    if isinstance(b, onboard.Special):
        name = onboard.SPECIAL.get(b.function, "")
        if name == "profile-select":
            return QCoreApplication.translate("Labels", "Switch to profile {slot}").format(slot=b.arg)
        lbl = SPECIAL_LABELS.get(name)
        return QCoreApplication.translate("Labels", lbl) if lbl else b.describe()
    if isinstance(b, onboard.Macro):
        return QCoreApplication.translate("Labels", "Macro")
    if isinstance(b, onboard.Disabled):
        return QCoreApplication.translate("Labels", "Disabled")
    if isinstance(b, onboard.Unassigned):
        return QCoreApplication.translate("Labels", "Not set")
    return b.describe()
