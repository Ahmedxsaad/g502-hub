"""Human-readable names for buttons, actions and effects."""

from .. import onboard

BUTTON_NAMES = [
    "G1 · Left click", "G2 · Right click", "G3 · Wheel click", "G4 · Back", "G5 · Forward",
    "G6 · Sniper", "G7 · Front left", "G8 · Behind G7", "G9 · Behind wheel",
    "Wheel tilt right", "Wheel tilt left",
]

MOUSE_LABELS = {0x0001: "Left click", 0x0002: "Right click", 0x0004: "Middle click",
                0x0008: "Back", 0x0010: "Forward"}

SPECIAL_LABELS = {
    "noop": "Nothing", "tilt-left": "Scroll left", "tilt-right": "Scroll right",
    "dpi-up": "DPI up", "dpi-down": "DPI down", "dpi-cycle": "DPI cycle",
    "dpi-default": "DPI default", "dpi-shift": "DPI shift (sniper)",
    "profile-next": "Next profile", "profile-prev": "Previous profile",
    "profile-cycle": "Cycle profiles", "gshift": "G-Shift", "scroll-up": "Scroll up",
    "scroll-down": "Scroll down", "battery": "Battery status", "mode-switch": "Mode switch",
    "host": "Host button",
}

CONSUMER_LABELS = {
    "play-pause": "Play / Pause", "next-track": "Next track", "prev-track": "Previous track",
    "stop": "Stop", "mute": "Mute", "volume-up": "Volume up", "volume-down": "Volume down",
    "brightness-up": "Brightness up", "brightness-down": "Brightness down",
    "calculator": "Calculator", "file-browser": "File manager", "mail": "Mail",
    "browser-home": "Browser home", "browser-back": "Browser back",
    "browser-forward": "Browser forward", "browser-refresh": "Browser refresh",
    "browser-search": "Search",
}

EFFECT_LABELS = {0x00: "Off", 0x01: "Fixed", 0x0A: "Breathing", 0x03: "Color cycle"}


def binding(b, keylabels):
    if isinstance(b, onboard.MouseButton):
        return MOUSE_LABELS.get(b.mask) or b.describe().replace("button", "Button ")
    if isinstance(b, onboard.Key):
        return keylabels.combo(b.modifiers, b.usage)
    if isinstance(b, onboard.Consumer):
        name = b.describe().removeprefix("media ")
        return CONSUMER_LABELS.get(name, name)
    if isinstance(b, onboard.Special):
        name = onboard.SPECIAL.get(b.function, "")
        if name == "profile-select":
            return f"Switch to profile {b.arg}"
        return SPECIAL_LABELS.get(name, b.describe())
    if isinstance(b, onboard.Macro):
        return "Macro"
    if isinstance(b, onboard.Disabled):
        return "Disabled"
    if isinstance(b, onboard.Unassigned):
        return "Not set"
    return b.describe()
