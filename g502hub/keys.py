"""Names for HID keyboard usages, modifiers and consumer-control usages."""

MODIFIERS = {
    "ctrl": 0x01, "shift": 0x02, "alt": 0x04, "super": 0x08,
    "rctrl": 0x10, "rshift": 0x20, "altgr": 0x40, "rsuper": 0x80,
}
MODIFIER_ALIASES = {"control": "ctrl", "lctrl": "ctrl", "lshift": "shift", "lalt": "alt",
                    "meta": "super", "win": "super", "gui": "super", "lsuper": "super",
                    "ralt": "altgr"}

# HID Keyboard/Keypad page (0x07) usages
KEYS = {chr(ord("a") + i): 0x04 + i for i in range(26)}
KEYS.update({str(n): 0x1E + (n - 1) for n in range(1, 10)})
KEYS["0"] = 0x27
KEYS.update({
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "minus": 0x2D, "equal": 0x2E, "leftbrace": 0x2F, "rightbrace": 0x30,
    "backslash": 0x31, "semicolon": 0x33, "apostrophe": 0x34, "grave": 0x35,
    "comma": 0x36, "dot": 0x37, "slash": 0x38, "capslock": 0x39,
    "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48, "insert": 0x49,
    "home": 0x4A, "pageup": 0x4B, "delete": 0x4C, "end": 0x4D, "pagedown": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52, "numlock": 0x53,
    "kpslash": 0x54, "kpasterisk": 0x55, "kpminus": 0x56, "kpplus": 0x57,
    "kpenter": 0x58, "kpdot": 0x63, "102nd": 0x64, "menu": 0x65,
})
KEYS.update({f"f{n}": 0x3A + (n - 1) for n in range(1, 13)})
KEYS.update({f"f{n}": 0x68 + (n - 13) for n in range(13, 25)})
KEYS.update({f"kp{n}": 0x59 + (n - 1) for n in range(1, 10)})
KEYS["kp0"] = 0x62
KEY_ALIASES = {"return": "enter", "escape": "esc", "del": "delete", "ins": "insert",
               "pgup": "pageup", "pgdn": "pagedown", "-": "minus", "=": "equal",
               "[": "leftbrace", "]": "rightbrace", "\\": "backslash", ";": "semicolon",
               "'": "apostrophe", "`": "grave", ",": "comma", ".": "dot", "/": "slash",
               "prtsc": "printscreen", "application": "menu"}

# HID Consumer page (0x0C) usages
CONSUMER = {
    "play-pause": 0x00CD, "next-track": 0x00B5, "prev-track": 0x00B6, "stop": 0x00B7,
    "mute": 0x00E2, "volume-up": 0x00E9, "volume-down": 0x00EA,
    "brightness-up": 0x006F, "brightness-down": 0x0070,
    "calculator": 0x0192, "file-browser": 0x0194, "mail": 0x018A,
    "browser-home": 0x0223, "browser-back": 0x0224, "browser-forward": 0x0225,
    "browser-refresh": 0x0227, "browser-search": 0x0221,
}

_KEY_NAMES = {v: k for k, v in KEYS.items()}
_CONSUMER_NAMES = {v: k for k, v in CONSUMER.items()}


def key_name(usage):
    return _KEY_NAMES.get(usage, f"key-0x{usage:02X}")


def modifier_names(mask):
    return [name for name, bit in MODIFIERS.items() if mask & bit]


def combo_name(modifiers, usage):
    parts = modifier_names(modifiers)
    if usage:
        parts.append(key_name(usage))
    return "+".join(parts) or "none"


def consumer_name(usage):
    return _CONSUMER_NAMES.get(usage, f"consumer-0x{usage:04X}")


def parse_combo(text):
    """Parse 'ctrl+shift+t' into (modifier mask, key usage)."""
    mods, usage = 0, 0
    for part in text.lower().split("+"):
        part = MODIFIER_ALIASES.get(part, part)
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
            continue
        part = KEY_ALIASES.get(part, part)
        if part not in KEYS:
            raise ValueError(f"unknown key '{part}'")
        if usage:
            raise ValueError(f"'{text}' has more than one non-modifier key")
        usage = KEYS[part]
    return mods, usage


def parse_consumer(text):
    if text not in CONSUMER:
        raise ValueError(f"unknown media key '{text}' (known: {', '.join(CONSUMER)})")
    return CONSUMER[text]
