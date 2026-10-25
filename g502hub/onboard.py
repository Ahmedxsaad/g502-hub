"""Onboard memory formats of the G502 HERO (0x8100 profile format 2).

Layouts follow docs/protocol.md §3. Every decoder keeps the bytes it read and
every encoder writes its fields on top of them, so bytes we don't understand
survive a read-modify-write untouched.
"""

from dataclasses import dataclass, field

from . import keys

BUTTON_SLOTS = 16
LED_BLOCK = 11
NAME_UNITS = 24  # UTF-16 code units


def crc16(data, crc=0xFFFF):
    """CRC-16/CCITT-FALSE, as used by Logitech onboard memory."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc


def crc_ok(sector):
    return crc16(sector[:-2]) == int.from_bytes(sector[-2:], "big")


def seal(sector):
    """Return the sector with a fresh big-endian CRC in its last two bytes."""
    sector = bytearray(sector)
    sector[-2:] = crc16(sector[:-2]).to_bytes(2, "big")
    return bytes(sector)


# ---------------------------------------------------------------- bindings

SPECIAL = {
    0x00: "noop", 0x01: "tilt-left", 0x02: "tilt-right", 0x03: "dpi-up",
    0x04: "dpi-down", 0x05: "dpi-cycle", 0x06: "dpi-default", 0x07: "dpi-shift",
    0x08: "profile-next", 0x09: "profile-prev", 0x0A: "profile-cycle",
    0x0B: "gshift", 0x0C: "battery", 0x0D: "profile-select", 0x0E: "mode-switch",
    0x0F: "host", 0x10: "scroll-down", 0x11: "scroll-up",
}
SPECIAL_CODES = {name: code for code, name in SPECIAL.items()}

MOUSE_BUTTON_NAMES = ["left", "right", "middle", "back", "forward"] + \
    [f"button{n}" for n in range(6, 17)]


@dataclass(frozen=True)
class Binding:
    raw: bytes = field(default=b"", compare=False, repr=False, kw_only=True)

    @staticmethod
    def decode(raw):
        raw = bytes(raw)
        b0, b1 = raw[0], raw[1]
        if raw == b"\xff\xff\xff\xff":
            return Unassigned(raw=raw)
        if b0 == 0x80:
            if b1 == 0x00:
                return Disabled(tail=raw[2:], raw=raw)
            if b1 == 0x01:
                return MouseButton(int.from_bytes(raw[2:], "big"), raw=raw)
            if b1 == 0x02:
                return Key(raw[2], raw[3], raw=raw)
            if b1 == 0x03:
                return Consumer(int.from_bytes(raw[2:], "big"), raw=raw)
        elif b0 == 0x90:
            return Special(b1, arg=raw[3], reserved=raw[2], raw=raw)
        elif b0 < 0x80:
            return Macro(raw[1], int.from_bytes(raw[2:], "big"), head=b0, raw=raw)
        return UnknownBinding(raw=raw)

    @staticmethod
    def parse(text):
        """Parse CLI syntax: left, key:ctrl+c, media:volume-up, dpi-up, profile-select:3 ..."""
        text = text.strip().lower()
        kind, _, arg = text.partition(":")
        if kind == "key":
            return Key(*keys.parse_combo(arg))
        if kind == "media":
            return Consumer(keys.parse_consumer(arg))
        if kind == "profile-select":
            return Special(SPECIAL_CODES["profile-select"], arg=int(arg))
        if text in MOUSE_BUTTON_NAMES:
            return MouseButton(1 << MOUSE_BUTTON_NAMES.index(text))
        if text == "disabled":
            return Disabled()
        if text == "unassigned":
            return Unassigned()
        if text in SPECIAL_CODES:
            return Special(SPECIAL_CODES[text])
        raise ValueError(f"unknown action '{text}'")


@dataclass(frozen=True)
class MouseButton(Binding):
    mask: int

    def encode(self):
        return b"\x80\x01" + self.mask.to_bytes(2, "big")

    def describe(self):
        names = [MOUSE_BUTTON_NAMES[i] for i in range(16) if self.mask & (1 << i)]
        return "+".join(names) or "no button"


@dataclass(frozen=True)
class Key(Binding):
    modifiers: int
    usage: int

    def encode(self):
        return bytes([0x80, 0x02, self.modifiers, self.usage])

    def describe(self):
        return "key " + keys.combo_name(self.modifiers, self.usage)


@dataclass(frozen=True)
class Consumer(Binding):
    usage: int

    def encode(self):
        return b"\x80\x03" + self.usage.to_bytes(2, "big")

    def describe(self):
        return "media " + keys.consumer_name(self.usage)


@dataclass(frozen=True)
class Special(Binding):
    function: int
    arg: int = 0xFF
    reserved: int = 0xFF

    def encode(self):
        return bytes([0x90, self.function, self.reserved, self.arg])

    def describe(self):
        name = SPECIAL.get(self.function, f"special-0x{self.function:02X}")
        return f"{name}:{self.arg}" if self.function == 0x0D else name


@dataclass(frozen=True)
class Macro(Binding):
    page: int
    offset: int
    head: int = 0x00  # memory type (0 = flash); Solaar reads the high nibble as behaviour

    def encode(self):
        return bytes([self.head, self.page]) + self.offset.to_bytes(2, "big")

    def describe(self):
        return f"macro @ sector {self.page} offset {self.offset}"


@dataclass(frozen=True)
class Disabled(Binding):
    tail: bytes = b"\xff\xff"

    def encode(self):
        return b"\x80\x00" + self.tail

    def describe(self):
        return "disabled"


@dataclass(frozen=True)
class Unassigned(Binding):
    def encode(self):
        return b"\xff\xff\xff\xff"

    def describe(self):
        return "unassigned"


@dataclass(frozen=True)
class UnknownBinding(Binding):
    def encode(self):
        return self.raw

    def describe(self):
        return "raw " + self.raw.hex(" ")


# ---------------------------------------------------------------- lighting

LED_EFFECTS = {0x00: "off", 0x01: "fixed", 0x03: "cycle", 0x0A: "breathing"}
LED_EFFECT_CODES = {name: code for code, name in LED_EFFECTS.items()}


@dataclass(frozen=True)
class LedEffect:
    """One 11-byte LED block. `intensity` is the raw byte: 0 means 100 %."""

    effect: int
    color: tuple = (0, 0, 0)
    period_ms: int = 0
    intensity: int = 0
    raw: bytes = field(default=b"", compare=False, repr=False)

    @classmethod
    def decode(cls, raw):
        raw = bytes(raw)
        effect = raw[0]
        if effect == 0x01:
            return cls(effect, tuple(raw[1:4]), raw=raw)
        if effect == 0x0A:
            return cls(effect, tuple(raw[1:4]), int.from_bytes(raw[4:6], "big"), raw[7], raw=raw)
        if effect == 0x03:
            return cls(effect, period_ms=int.from_bytes(raw[6:8], "big"), intensity=raw[8], raw=raw)
        return cls(effect, raw=raw)

    @classmethod
    def off(cls):
        return cls(0x00)

    @classmethod
    def fixed(cls, color):
        return cls(0x01, tuple(color))

    @classmethod
    def breathing(cls, color, period_ms=8000, brightness=100):
        return cls(0x0A, tuple(color), period_ms, _intensity(brightness))

    @classmethod
    def cycle(cls, period_ms=8000, brightness=100):
        return cls(0x03, period_ms=period_ms, intensity=_intensity(brightness))

    def encode(self):
        # Keep unknown bytes only while the effect type is unchanged
        same = len(self.raw) == LED_BLOCK and self.raw[0] == self.effect
        out = bytearray(self.raw if same else bytes(LED_BLOCK))
        out[0] = self.effect
        if self.effect == 0x01:
            out[1:4] = bytes(self.color)
        elif self.effect == 0x0A:
            out[1:4] = bytes(self.color)
            out[4:6] = self.period_ms.to_bytes(2, "big")
            out[7] = self.intensity
        elif self.effect == 0x03:
            out[6:8] = self.period_ms.to_bytes(2, "big")
            out[8] = self.intensity
        return bytes(out)

    @property
    def brightness(self):
        return self.intensity or 100

    def describe(self):
        name = LED_EFFECTS.get(self.effect, f"effect-0x{self.effect:02X}")
        rgb = "#" + bytes(self.color).hex()
        if self.effect == 0x01:
            return f"{name} {rgb}"
        if self.effect == 0x0A:
            return f"{name} {rgb} {self.period_ms} ms {self.brightness}%"
        if self.effect == 0x03:
            return f"{name} {self.period_ms} ms {self.brightness}%"
        return name


def _intensity(brightness):
    if not 1 <= brightness <= 100:
        raise ValueError("brightness must be 1-100")
    return 0 if brightness == 100 else brightness


# ---------------------------------------------------------------- profiles

@dataclass
class Profile:
    report_interval_ms: int
    default_dpi_index: int
    shift_dpi_index: int
    dpi: list
    color: tuple
    angle_snapping: int
    buttons: list
    gshift: list
    name: str | None  # None = the firmware's default name (all 0xFF)
    leds: list
    alt_leds: list
    raw: bytes = field(repr=False)

    @classmethod
    def decode(cls, data):
        data = bytes(data)
        binding = lambda off: Binding.decode(data[off:off + 4])
        led = lambda off: LedEffect.decode(data[off:off + LED_BLOCK])
        return cls(
            report_interval_ms=data[0],
            default_dpi_index=data[1],
            shift_dpi_index=data[2],
            dpi=[int.from_bytes(data[3 + 2 * i:5 + 2 * i], "little") for i in range(5)],
            color=tuple(data[13:16]),
            angle_snapping=data[17],
            buttons=[binding(32 + 4 * i) for i in range(BUTTON_SLOTS)],
            gshift=[binding(96 + 4 * i) for i in range(BUTTON_SLOTS)],
            name=_decode_name(data[160:208]),
            leds=[led(208), led(219)],
            alt_leds=[led(230), led(241)],
            raw=data,
        )

    def encode(self):
        out = bytearray(self.raw)
        out[0] = self.report_interval_ms
        out[1] = self.default_dpi_index
        out[2] = self.shift_dpi_index
        for i, dpi in enumerate(self.dpi):
            out[3 + 2 * i:5 + 2 * i] = dpi.to_bytes(2, "little")
        out[13:16] = bytes(self.color)
        out[17] = self.angle_snapping
        for i, b in enumerate(self.buttons):
            out[32 + 4 * i:36 + 4 * i] = b.encode()
        for i, b in enumerate(self.gshift):
            out[96 + 4 * i:100 + 4 * i] = b.encode()
        out[160:208] = _encode_name(self.name)
        for off, led in zip((208, 219, 230, 241), self.leds + self.alt_leds):
            out[off:off + LED_BLOCK] = led.encode()
        return seal(out)

    @property
    def report_rate_hz(self):
        return 1000 // self.report_interval_ms if self.report_interval_ms else 0

    def dpi_levels(self):
        """(slot, dpi) for every enabled DPI slot."""
        return [(i, d) for i, d in enumerate(self.dpi) if d not in (0, 0xFFFF)]


def _decode_name(raw):
    if all(b == 0xFF for b in raw):
        return None
    return raw.decode("utf-16-le", errors="replace").split("\0")[0]


def _encode_name(name):
    if name is None:
        return b"\xff" * (2 * NAME_UNITS)
    data = name.encode("utf-16-le")
    while len(data) > 2 * NAME_UNITS:
        name = name[:-1]
        data = name.encode("utf-16-le")
    return data.ljust(2 * NAME_UNITS, b"\0")


# ---------------------------------------------------------------- directory

@dataclass
class DirEntry:
    sector: int
    enabled: bool
    flag: int = 0x00  # reserved byte; 0x00 in libratbag/Solaar-written dirs, 0xFF in ROM

    def encode(self):
        return self.sector.to_bytes(2, "big") + bytes([int(self.enabled), self.flag])


@dataclass
class Directory:
    entries: list
    terminator: bytes = b"\xff\xff\x00\x00"
    raw: bytes = field(default=b"", repr=False)

    @classmethod
    def decode(cls, data):
        """Return the directory, or None when the sector was never written."""
        data = bytes(data)
        if all(b == 0 for b in data[:-2]) or all(b == 0xFF for b in data[:-2]):
            return None
        entries = []
        for off in range(0, len(data) - 6, 4):
            sector = int.from_bytes(data[off:off + 2], "big")
            if sector == 0xFFFF:
                return cls(entries, data[off:off + 4], data)
            entries.append(DirEntry(sector, bool(data[off + 2]), data[off + 3]))
        raise ValueError("profile directory has no terminator")

    def encode(self, size):
        out = bytearray(self.raw or b"\xff" * size)
        old_end = 4 * (len(Directory.decode(out).entries) + 1) if self.raw else 0
        block = b"".join(e.encode() for e in self.entries) + self.terminator
        out[:len(block)] = block
        if len(block) < old_end:
            out[len(block):old_end] = b"\xff" * (old_end - len(block))
        return seal(out)
