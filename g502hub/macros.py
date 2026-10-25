"""Macros: sequences of key presses, typing, clicks, scrolling and delays.

A macro either runs in the app (played through a virtual input device, see
effects/macroplayer.py) or is stored in the mouse in onboard macro format 1
(see macro.py). Both play the same low-level events from `expand()`.

`typing(char) -> (modifiers, usage) | None` says which keys type a character
on the user's layout (keylabels.KeyLabels.typing).
"""

import uuid
from dataclasses import dataclass, field

from . import keys, macro
from .onboard import MOUSE_BUTTON_NAMES

KINDS = ("key", "key-down", "key-up", "text", "delay", "click", "button-down", "button-up",
         "scroll", "hscroll", "move", "media")
MODES = ("once", "while-held", "toggle")
TARGETS = ("app", "mouse")
BUTTONS = ("left", "right", "middle", "back", "forward")
ONBOARD_CAPACITY = 253   # bytes in one flash sector before its 2-byte CRC
MAX_DELAY_MS = 600_000
WHITESPACE = {" ": (0, keys.KEYS["space"]), "\n": (0, keys.KEYS["enter"]), "\t": (0, keys.KEYS["tab"])}

_MODE_TEXT = {"once": "plays once", "while-held": "repeats while held", "toggle": "toggles on and off"}
_TARGET_TEXT = {"app": "run by the app", "mouse": "stored in the mouse"}


class MacroError(ValueError):
    pass


def new_id():
    return uuid.uuid4().hex[:8]


def parse_combo(text):
    """keys.parse_combo, also accepting the "key-0x1D" names unknown usages get."""
    mods, usage = 0, 0
    rest = []
    for part in text.lower().split("+"):
        if part.startswith("key-0x"):
            if usage:
                raise ValueError(f"'{text}' has more than one non-modifier key")
            usage = int(part[6:], 16)
        else:
            rest.append(part)
    if rest:
        m, u = keys.parse_combo("+".join(rest))
        if u and usage:
            raise ValueError(f"'{text}' has more than one non-modifier key")
        mods, usage = m, usage or u
    return mods, usage


def parse_media(text):
    """keys.parse_consumer, also accepting "consumer-0x00CD"."""
    if text.startswith("consumer-0x"):
        return int(text[11:], 16)
    return keys.parse_consumer(text)


def _int(args, name, lo, hi):
    value = args.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ValueError(f"{name} must be a whole number from {lo} to {hi}")
    return value


@dataclass
class Step:
    kind: str
    args: dict = field(default_factory=dict)

    def validate(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown step {self.kind!r}")
        if not isinstance(self.args, dict):
            raise ValueError("step arguments must be a dict")
        a = self.args
        if self.kind in ("key", "key-down", "key-up"):
            if not isinstance(a.get("combo"), str):
                raise ValueError("a key step needs a combo")
            mods, usage = parse_combo(a["combo"])
            if not mods and not usage:
                raise ValueError("a key step needs a key")
        elif self.kind == "text":
            if not isinstance(a.get("text"), str) or not a["text"]:
                raise ValueError("a text step needs some text")
        elif self.kind == "delay":
            _int(a, "ms", 0, MAX_DELAY_MS)
        elif self.kind in ("click", "button-down", "button-up"):
            if a.get("button") not in BUTTONS:
                raise ValueError(f"button must be one of {', '.join(BUTTONS)}")
        elif self.kind in ("scroll", "hscroll"):
            _int(a, "amount", -1000, 1000)
        elif self.kind == "move":
            _int(a, "dx", -32768, 32767)
            _int(a, "dy", -32768, 32767)
        elif self.kind == "media":
            if not isinstance(a.get("key"), str):
                raise ValueError("a media step needs a key")
            parse_media(a["key"])
        return self

    def describe(self, key_name=None):
        a = self.args
        if self.kind in ("key", "key-down", "key-up"):
            mods, usage = parse_combo(a["combo"])
            label = key_name(mods, usage) if key_name else keys.combo_name(mods, usage)
            verb = {"key": "Press", "key-down": "Hold", "key-up": "Release"}[self.kind]
            return f"{verb} {label}"
        if self.kind == "text":
            return f"Type “{a['text']}”"
        if self.kind == "delay":
            ms = a["ms"]
            return f"Wait {ms / 1000:g} s" if ms >= 1000 else f"Wait {ms} ms"
        if self.kind == "click":
            return f"{a['button'].capitalize()} click"
        if self.kind == "button-down":
            return f"Hold the {a['button']} button"
        if self.kind == "button-up":
            return f"Release the {a['button']} button"
        if self.kind in ("scroll", "hscroll"):
            n = a["amount"]
            if self.kind == "scroll":
                way = "up" if n >= 0 else "down"
            else:
                way = "right" if n >= 0 else "left"
            return f"Scroll {way} {abs(n)}"
        if self.kind == "move":
            return f"Move the pointer {a['dx']}, {a['dy']}"
        return keys.consumer_name(parse_media(a["key"])).replace("-", " ").capitalize()


@dataclass
class Macro:
    name: str
    steps: list = field(default_factory=list)
    mode: str = "once"
    target: str = "app"
    gap_ms: int = 0
    id: str = field(default_factory=new_id)

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("a macro needs a name")
        if self.mode not in MODES:
            raise ValueError(f"unknown mode {self.mode!r}")
        if self.target not in TARGETS:
            raise ValueError(f"unknown target {self.target!r}")
        if self.target == "mouse" and self.mode != "once":
            raise ValueError("macros stored in the mouse can only play once")
        if not isinstance(self.gap_ms, int) or not 0 <= self.gap_ms <= 10_000:
            raise ValueError("the gap between steps must be 0 to 10000 ms")
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("a macro needs an id")
        for step in self.steps:
            step.validate()
        return self

    def to_dict(self):
        return {"id": self.id, "name": self.name, "mode": self.mode, "target": self.target,
                "gap_ms": self.gap_ms, "steps": [{"kind": s.kind, "args": dict(s.args)} for s in self.steps]}

    @staticmethod
    def from_dict(d):
        if not isinstance(d, dict) or not isinstance(d.get("steps", []), list):
            raise ValueError("not a macro")
        steps = []
        for s in d.get("steps", []):
            if not isinstance(s, dict):
                raise ValueError("not a macro step")
            steps.append(Step(s.get("kind"), dict(s.get("args") or {})))
        m = Macro(name=d.get("name"), steps=steps, mode=d.get("mode", "once"),
                  target=d.get("target", "app"), gap_ms=d.get("gap_ms", 0), id=d.get("id") or new_id())
        return m.validate()

    def describe(self):
        n = len(self.steps)
        return f"{n} step{'s' if n != 1 else ''} · {_MODE_TEXT[self.mode]} · {_TARGET_TEXT[self.target]}"


def load(items):
    """Macros from settings, skipping any that are malformed."""
    out = []
    for d in items or []:
        try:
            out.append(Macro.from_dict(d))
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
    return out


# ------------------------------------------------------------ low-level events

def _button_mask(name):
    return 1 << MOUSE_BUTTON_NAMES.index(name)


def _type(text, typing):
    out = []
    for char in text:
        found = typing(char) if typing else None
        if found is None:
            found = WHITESPACE.get(char)
        if found is None:
            raise MacroError(f"“{char}” can't be typed with your keyboard layout")
        mods, usage = found
        out += [("key", mods, usage, True), ("key", mods, usage, False)]
    return out


def step_events(step, typing):
    """The low-level events of one step."""
    a = step.args
    if step.kind in ("key", "key-down", "key-up"):
        mods, usage = parse_combo(a["combo"])
        if step.kind == "key":
            return [("key", mods, usage, True), ("key", mods, usage, False)]
        return [("key", mods, usage, step.kind == "key-down")]
    if step.kind == "text":
        return _type(a["text"], typing)
    if step.kind == "delay":
        return [("delay", a["ms"])] if a["ms"] else []
    if step.kind in ("click", "button-down", "button-up"):
        mask = _button_mask(a["button"])
        if step.kind == "click":
            return [("button", mask, True), ("button", mask, False)]
        return [("button", mask, step.kind == "button-down")]
    if step.kind == "scroll":
        return [("wheel", a["amount"])] if a["amount"] else []
    if step.kind == "hscroll":
        return [("hwheel", a["amount"])] if a["amount"] else []
    if step.kind == "move":
        return [("move", a["dx"], a["dy"])] if a["dx"] or a["dy"] else []
    usage = parse_media(a["key"])
    return [("consumer", usage, True), ("consumer", usage, False)]


def expand(macro_, typing):
    """Low-level events, in order:

    ("key", mods, usage, down) ("button", mask, down) ("wheel", n) ("hwheel", n)
    ("move", dx, dy) ("consumer", usage, down) ("delay", ms)
    """
    out = []
    for n, step in enumerate(macro_.steps):
        if n and macro_.gap_ms:
            out.append(("delay", macro_.gap_ms))
        out += step_events(step, typing)
    return out


# ------------------------------------------------------------ in the mouse

def _chunks(value, limit):
    """Split a signed amount into pieces the firmware's field can hold."""
    out = []
    while value:
        piece = max(-limit, min(limit, value))
        out.append(piece)
        value -= piece
    return out


def onboard_steps(macro_, typing):
    """The macro as macro.py steps (without END)."""
    if macro_.mode != "once":
        raise MacroError("a macro stored in the mouse can only play once per press")
    steps = []
    for ev in expand(macro_, typing):
        kind = ev[0]
        if kind == "key":
            steps.append(("key-down" if ev[3] else "key-up", ev[1], ev[2]))
        elif kind == "button":
            steps.append(("button-down" if ev[2] else "button-up", ev[1]))
        elif kind == "consumer":
            steps.append(("consumer-down" if ev[2] else "consumer-up", ev[1]))
        elif kind == "delay":
            ms = ev[1]
            while ms > 0:
                steps.append(("delay", min(ms, 0xFFFF)))
                ms -= 0xFFFF
        elif kind in ("wheel", "hwheel"):
            steps += [(kind, n) for n in _chunks(ev[1], 127)]
        elif kind == "move":
            dx, dy = ev[1], ev[2]
            while dx or dy:
                sx, sy = max(-32767, min(32767, dx)), max(-32767, min(32767, dy))
                steps.append(("move", sx, sy))
                dx, dy = dx - sx, dy - sy
    return steps


def to_onboard(macro_, typing):
    """Macro format 1 bytes ending with END, for one flash sector."""
    data = macro.encode(onboard_steps(macro_, typing))
    if len(data) > ONBOARD_CAPACITY:
        raise MacroError(f"too long for the mouse: {len(data)} bytes, {ONBOARD_CAPACITY} fit")
    return data


def onboard_size(macro_, typing):
    return len(macro.encode(onboard_steps(macro_, typing)))


def from_onboard(steps, name="Macro from the mouse"):
    """A Macro from macro.decode() output (e.g. one G HUB left on the mouse). Best effort."""
    steps = [s for s in steps if s[0] not in ("noop", "end", "wait-release",
                                               "repeat-while-pressed", "repeat-forever")]
    out = []
    i = 0
    while i < len(steps):
        s = steps[i]
        nxt = steps[i + 1] if i + 1 < len(steps) else None
        kind = s[0]
        if kind in ("key-down", "key-up") and not (s[1] or s[2]):
            pass  # an empty key report: nothing to press
        elif kind in ("key-down", "key-up"):
            combo = keys.combo_name(s[1], s[2])
            if kind == "key-down" and nxt and nxt[0] == "key-up" and nxt[1:] == s[1:]:
                out.append(Step("key", {"combo": combo}))
                i += 1
            else:
                out.append(Step(kind, {"combo": combo}))
        elif kind == "delay":
            out.append(Step("delay", {"ms": s[1]}))
        elif kind in ("button-down", "button-up"):
            names = [n for b, n in enumerate(BUTTONS) if s[1] & (1 << b)]
            tap = kind == "button-down" and nxt and nxt[0] == "button-up" and nxt[1] == s[1]
            for n in names:
                out.append(Step("click" if tap else kind, {"button": n}))
            if tap:
                i += 1
        elif kind in ("wheel", "hwheel"):
            out.append(Step("scroll" if kind == "wheel" else "hscroll", {"amount": s[1]}))
        elif kind == "move":
            out.append(Step("move", {"dx": s[1], "dy": s[2]}))
        elif kind == "consumer-down":
            out.append(Step("media", {"key": keys.consumer_name(s[1])}))
            if nxt and nxt[0] == "consumer-up" and nxt[1] == s[1]:
                i += 1
        # a lone consumer-up has no step of its own
        i += 1
    return Macro(name=name, steps=out, mode="once", target="mouse")


def from_recording(events, min_delay_ms=20, tap_ms=200):
    """Steps from keys recorded in the editor.

    `events` are (seconds, hid_usage, mods, down). A modifier key on its own is
    usage 0 with its modifier bit in `mods`; for other keys `mods` is what was
    held. A press released within `tap_ms`, before anything else happened,
    becomes one "key" step; longer holds keep their down, delay and up.
    """
    events = sorted(events, key=lambda e: e[0])
    held = 0  # modifiers recorded as their own steps
    steps, last_t = [], None
    i = 0
    while i < len(events):
        t, usage, mods, down = events[i]
        if last_t is not None:
            gap = round((t - last_t) * 1000)
            if gap >= min_delay_ms:
                steps.append(Step("delay", {"ms": min(gap, MAX_DELAY_MS)}))
        if usage == 0:
            combo = keys.combo_name(mods, 0)
            held = held | mods if down else held & ~mods
        else:
            combo = keys.combo_name(mods & ~held, usage)
        nxt = events[i + 1] if i + 1 < len(events) else None
        tap = nxt and not nxt[3] and nxt[1] == usage and (usage or nxt[2] == mods) and \
            (nxt[0] - t) * 1000 < tap_ms
        if down and tap:
            steps.append(Step("key", {"combo": combo}))
            if usage == 0:
                held &= ~mods
            last_t = nxt[0]
            i += 2
            continue
        steps.append(Step("key-down" if down else "key-up", {"combo": combo}))
        last_t = t
        i += 1
    return steps
