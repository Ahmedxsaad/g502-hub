"""Label HID key usages the way the user's keyboard layout prints them.

The mouse stores physical key positions (HID usages). On an AZERTY layout the
usage US keyboards call "w" types "z", so labels go through libxkbcommon.
"""

import ctypes
import ctypes.util
import re
import subprocess

from . import keys

# Keys whose label doesn't come from the layout
SPECIAL_LABELS = {
    "enter": "Enter", "esc": "Esc", "backspace": "Backspace", "tab": "Tab",
    "space": "Space", "capslock": "Caps Lock", "printscreen": "Print Screen",
    "scrolllock": "Scroll Lock", "pause": "Pause", "insert": "Insert",
    "home": "Home", "pageup": "Page Up", "delete": "Delete", "end": "End",
    "pagedown": "Page Down", "right": "→", "left": "←", "down": "↓", "up": "↑",
    "numlock": "Num Lock", "kpenter": "Num Enter", "menu": "Menu",
}
MODIFIER_LABELS = {0x01: "Ctrl", 0x02: "Shift", 0x04: "Alt", 0x08: "Meta",
                   0x10: "Right Ctrl", 0x20: "Right Shift", 0x40: "AltGr", 0x80: "Right Meta"}


class _XkbRuleNames(ctypes.Structure):
    _fields_ = [(f, ctypes.c_char_p) for f in ("rules", "model", "layout", "variant", "options")]


def current_layout():
    """(layout, variant) of the active KDE layout, else the system X11 layout."""
    try:
        out = subprocess.run(["qdbus6", "--literal", "org.kde.keyboard", "/Layouts",
                              "org.kde.KeyboardLayouts.getLayoutsList"],
                             capture_output=True, text=True, timeout=2).stdout
        idx = int(subprocess.run(["qdbus6", "org.kde.keyboard", "/Layouts",
                                  "org.kde.KeyboardLayouts.getLayout"],
                                 capture_output=True, text=True, timeout=2).stdout or 0)
        layouts = re.findall(r'\(sss\) "([^"]*)", "([^"]*)"', out)
        if layouts:
            return layouts[min(idx, len(layouts) - 1)]
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        out = subprocess.run(["localectl", "status"], capture_output=True, text=True, timeout=2).stdout
        layout = re.search(r"X11 Layout: (\S+)", out)
        variant = re.search(r"X11 Variant: (\S+)", out)
        if layout:
            return layout.group(1).split(",")[0], variant.group(1).split(",")[0] if variant else ""
    except (OSError, subprocess.SubprocessError):
        pass
    return "us", ""


class KeyLabels:
    def __init__(self, layout=None):
        self.layout, self.variant = layout or current_layout()
        self._state = None
        self._lib = None
        self._keymap = None
        self._typing = None
        try:
            self._open_xkb()
        except (OSError, AttributeError):
            self._state = None  # fall back to US names

    def _open_xkb(self):
        lib = ctypes.CDLL(ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0")
        lib.xkb_context_new.restype = ctypes.c_void_p
        lib.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        lib.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(_XkbRuleNames), ctypes.c_int]
        lib.xkb_state_new.restype = ctypes.c_void_p
        lib.xkb_state_new.argtypes = [ctypes.c_void_p]
        lib.xkb_state_key_get_utf8.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        ctx = lib.xkb_context_new(0)
        names = _XkbRuleNames(None, None, self.layout.encode(), self.variant.encode() or None, None)
        keymap = lib.xkb_keymap_new_from_names(ctx, ctypes.byref(names), 0)
        if not keymap:
            raise OSError("xkb keymap not available")
        self._lib, self._state, self._keymap = lib, lib.xkb_state_new(keymap), keymap

    def key(self, usage):
        name = keys.key_name(usage)
        if name in SPECIAL_LABELS:
            return SPECIAL_LABELS[name]
        if name.startswith("kp") and name[2:].isdigit():
            return f"Num {name[2:]}"
        if re.fullmatch(r"f\d+", name):
            return name.upper()
        code = keys.HID_TO_EVDEV.get(usage)
        if self._state and code is not None:
            buf = ctypes.create_string_buffer(16)
            self._lib.xkb_state_key_get_utf8(self._state, code + 8, buf, 16)
            text = buf.value.decode(errors="replace")
            if text.strip():
                return text.upper()
        return name.upper() if len(name) == 1 else name

    def usage_for(self, char):
        """The HID usage that types `char` (unshifted) on this layout, e.g. 'z' -> 0x1A on AZERTY."""
        char = char.upper()
        for usage in keys.HID_TO_EVDEV:
            if self.key(usage) == char:
                return usage
        return keys.KEYS.get(char.lower())

    def typing(self, char):
        """(HID modifiers, usage) that type `char` on this layout, or None.

        E.g. on AZERTY '1' -> (Shift, 0x1E), '@' -> (AltGr, 0x27). Used to play
        macros that type text.
        """
        if self._typing is None:
            self._typing = self._typing_table()
        return self._typing.get(char)

    def _typing_table(self):
        table = {"\n": (0, keys.KEYS["enter"]), "\t": (0, keys.KEYS["tab"]), " ": (0, keys.KEYS["space"])}
        shift, altgr = 0x02, 0x40
        if not self._state:  # US layout from the key names
            for name, usage in keys.KEYS.items():
                if len(name) == 1:
                    table.setdefault(name, (0, usage))
                    if name.isalpha():
                        table.setdefault(name.upper(), (shift, usage))
            return table
        lib = self._lib
        lib.xkb_keymap_mod_get_index.restype = ctypes.c_uint32
        lib.xkb_keymap_mod_get_index.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.xkb_state_update_mask.argtypes = [ctypes.c_void_p] + [ctypes.c_uint32] * 6
        lib.xkb_state_unref.argtypes = [ctypes.c_void_p]
        index = {name: lib.xkb_keymap_mod_get_index(self._keymap, name.encode()) for name in ("Shift", "Mod5")}
        levels = [(0, 0), (shift, 1 << index["Shift"])]
        if index["Mod5"] < 32:  # AltGr (ISO Level 3) lives on Mod5 in xkb layouts
            levels += [(altgr, 1 << index["Mod5"]), (shift | altgr, (1 << index["Shift"]) | (1 << index["Mod5"]))]
        buf = ctypes.create_string_buffer(16)
        for hid_mods, xkb_mods in levels:
            state = lib.xkb_state_new(self._keymap)
            lib.xkb_state_update_mask(state, xkb_mods, 0, 0, 0, 0, 0)
            for usage, code in keys.HID_TO_EVDEV.items():
                lib.xkb_state_key_get_utf8(state, code + 8, buf, 16)
                char = buf.value.decode(errors="ignore")
                if len(char) == 1 and char.isprintable():
                    table.setdefault(char, (hid_mods, usage))
            lib.xkb_state_unref(state)
        return table

    def combo(self, modifiers, usage):
        parts = [label for bit, label in MODIFIER_LABELS.items() if modifiers & bit]
        if usage:
            parts.append(self.key(usage))
        return " + ".join(parts) or "None"
