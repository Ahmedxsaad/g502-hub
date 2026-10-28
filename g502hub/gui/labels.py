"""Human-readable names for buttons, actions and effects."""

from .. import onboard
from .i18n import tr


class _TrList:
    def __init__(self, items, context="Labels"):
        self._items = items
        self.context = context

    def __getitem__(self, idx):
        return tr(self._items[idx], self.context)

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        for item in self._items:
            yield tr(item, self.context)


class _TrDict:
    def __init__(self, mapping, context="Labels"):
        self._mapping = mapping
        self.context = context

    def get(self, key, default=None):
        if key in self._mapping:
            return tr(self._mapping[key], self.context)
        return default

    def __getitem__(self, key):
        return tr(self._mapping[key], self.context)

    def __contains__(self, key):
        return key in self._mapping

    def __iter__(self):
        return iter(self._mapping)

    def items(self):
        for k, v in self._mapping.items():
            yield k, tr(v, self.context)


BUTTON_NAMES = _TrList([
    tr("G1 · Left click", "Buttons"),
    tr("G2 · Right click", "Buttons"),
    tr("G3 · Wheel click", "Buttons"),
    tr("G4 · Back", "Buttons"),
    tr("G5 · Forward", "Buttons"),
    tr("G6 · Sniper", "Buttons"),
    tr("G7 · Front left", "Buttons"),
    tr("G8 · Behind G7", "Buttons"),
    tr("G9 · Behind wheel", "Buttons"),
    tr("Wheel tilt right", "Buttons"),
    tr("Wheel tilt left", "Buttons"),
], "Buttons")

MOUSE_LABELS = _TrDict({
    0x0001: tr("Left click", "MouseLabels"),
    0x0002: tr("Right click", "MouseLabels"),
    0x0004: tr("Middle click", "MouseLabels"),
    0x0008: tr("Back", "MouseLabels"),
    0x0010: tr("Forward", "MouseLabels"),
}, "MouseLabels")

SPECIAL_LABELS = _TrDict({
    "noop": tr("Nothing", "SpecialLabels"),
    "tilt-left": tr("Scroll left", "SpecialLabels"),
    "tilt-right": tr("Scroll right", "SpecialLabels"),
    "dpi-up": tr("DPI up", "SpecialLabels"),
    "dpi-down": tr("DPI down", "SpecialLabels"),
    "dpi-cycle": tr("DPI cycle", "SpecialLabels"),
    "dpi-default": tr("DPI default", "SpecialLabels"),
    "dpi-shift": tr("DPI shift (sniper)", "SpecialLabels"),
    "profile-next": tr("Next profile", "SpecialLabels"),
    "profile-prev": tr("Previous profile", "SpecialLabels"),
    "profile-cycle": tr("Cycle profiles", "SpecialLabels"),
    "gshift": tr("G-Shift", "SpecialLabels"),
    "scroll-up": tr("Scroll up", "SpecialLabels"),
    "scroll-down": tr("Scroll down", "SpecialLabels"),
    "battery": tr("Battery status", "SpecialLabels"),
    "mode-switch": tr("Mode switch", "SpecialLabels"),
    "host": tr("Host button", "SpecialLabels"),
}, "SpecialLabels")

CONSUMER_LABELS = _TrDict({
    "play-pause": tr("Play / Pause", "ConsumerLabels"),
    "next-track": tr("Next track", "ConsumerLabels"),
    "prev-track": tr("Previous track", "ConsumerLabels"),
    "stop": tr("Stop", "ConsumerLabels"),
    "mute": tr("Mute", "ConsumerLabels"),
    "volume-up": tr("Volume up", "ConsumerLabels"),
    "volume-down": tr("Volume down", "ConsumerLabels"),
    "brightness-up": tr("Brightness up", "ConsumerLabels"),
    "brightness-down": tr("Brightness down", "ConsumerLabels"),
    "calculator": tr("Calculator", "ConsumerLabels"),
    "file-browser": tr("File manager", "ConsumerLabels"),
    "mail": tr("Mail", "ConsumerLabels"),
    "browser-home": tr("Browser home", "ConsumerLabels"),
    "browser-back": tr("Browser back", "ConsumerLabels"),
    "browser-forward": tr("Browser forward", "ConsumerLabels"),
    "browser-refresh": tr("Browser refresh", "ConsumerLabels"),
    "browser-search": tr("Search", "ConsumerLabels"),
}, "ConsumerLabels")

EFFECT_LABELS = _TrDict({
    0x00: tr("Off", "EffectLabels"),
    0x01: tr("Fixed", "EffectLabels"),
    0x0A: tr("Breathing", "EffectLabels"),
    0x03: tr("Color cycle", "EffectLabels"),
}, "EffectLabels")


def binding(b, keylabels):
    if isinstance(b, onboard.MouseButton):
        return MOUSE_LABELS.get(b.mask) or b.describe().replace("button", tr("Button ", "Labels"))
    if isinstance(b, onboard.Key):
        return keylabels.combo(b.modifiers, b.usage)
    if isinstance(b, onboard.Consumer):
        name = b.describe().removeprefix("media ")
        return CONSUMER_LABELS.get(name, name)
    if isinstance(b, onboard.Special):
        name = onboard.SPECIAL.get(b.function, "")
        if name == "profile-select":
            return tr("Switch to profile {slot}", "Labels").format(slot=b.arg)
        return SPECIAL_LABELS.get(name, b.describe())
    if isinstance(b, onboard.Macro):
        return tr("Macro", "Labels")
    if isinstance(b, onboard.Disabled):
        return tr("Disabled", "Labels")
    if isinstance(b, onboard.Unassigned):
        return tr("Not set", "Labels")
    return b.describe()
