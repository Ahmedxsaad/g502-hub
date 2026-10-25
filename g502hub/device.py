"""The G502 HERO's HID++ features: onboard profiles, DPI, report rate, LEDs, button spy.

Function numbers and payloads come from docs/protocol.md.
"""

from dataclasses import dataclass

from . import onboard
from .hidpp import ERR_HARDWARE, Hidpp, HidppError, find_hidraw

VID, PID = 0x046D, 0xC08B

ROOT, FEATURE_SET, FW_VERSION, DEVICE_NAME = 0x0000, 0x0001, 0x0003, 0x0005
ADJUSTABLE_DPI, REPORT_RATE = 0x2201, 0x8060
COLOR_LED_EFFECTS, ONBOARD_PROFILES, BUTTON_SPY = 0x8070, 0x8100, 0x8110

MODE_ONBOARD, MODE_HOST = 1, 2
ROM = 0x0100  # memory type 1 = read-only factory profiles


class DeviceNotFound(Exception):
    pass


def parse_dpi_list(payload):
    """(min, max, step) from a 0x2201 DPI list: BE16 values where 0xE000|step
    marks a range between its neighbours, terminated by 0."""
    values = [int.from_bytes(payload[i:i + 2], "big") for i in range(0, len(payload) - 1, 2)]
    values = values[:values.index(0)] if 0 in values else values
    steps = [v & 0x1FFF for v in values if v >> 13 == 0b111]
    plain = [v for v in values if v >> 13 != 0b111]
    return min(plain), max(plain), (steps[0] if steps else 1)


@dataclass
class OnboardInfo:
    memory_model: int
    profile_format: int
    macro_format: int
    profile_count: int
    rom_profile_count: int
    button_count: int
    sector_count: int
    sector_size: int
    mechanical_layout: int
    various_info: int

    @property
    def has_gshift(self):
        return self.mechanical_layout & 0x03 == 2

    @property
    def has_dpi_shift(self):
        return (self.mechanical_layout & 0x0C) >> 2 == 2


@dataclass
class LedZone:
    index: int
    location: int
    effects: dict  # effect id -> effect index in this zone

    @property
    def name(self):
        return {1: "primary", 2: "logo"}.get(self.location, f"location-{self.location}")


class G502:
    def __init__(self, path=None):
        path = path or find_hidraw(VID, PID)
        if not path:
            raise DeviceNotFound("G502 HERO not found (is it plugged in?)")
        try:
            self.hidpp = Hidpp(path)
        except PermissionError:
            raise DeviceNotFound(f"no permission on {path}: install udev/70-g502-hub.rules") from None
        self.path = path
        self._onboard_info = None
        self._zones = None

    def close(self):
        self.hidpp.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _call(self, feature_id, function, params=b"", **kw):
        idx = self.hidpp.feature_index(feature_id)
        if idx is None:
            raise HidppError(0x09, feature_id, function)
        return self.hidpp.request(idx, function, params, **kw)

    # ------------------------------------------------------------ identity

    def features(self):
        """[(index, feature id, type flags, version)] for every feature."""
        count = self._call(FEATURE_SET, 0)[0]
        out = [(0, ROOT, 0, 0)]
        for i in range(1, count + 1):
            r = self._call(FEATURE_SET, 1, [i])
            out.append((i, int.from_bytes(r[0:2], "big"), r[2], r[3]))
        return out

    def name(self):
        length = self._call(DEVICE_NAME, 0)[0]
        name = b""
        while len(name) < length:
            name += self._call(DEVICE_NAME, 1, [len(name)])
        return name[:length].decode(errors="replace")

    def firmware(self):
        entities = []
        for e in range(self._call(FW_VERSION, 0)[0]):
            r = self._call(FW_VERSION, 1, [e])
            prefix = r[1:4].decode(errors="replace").strip("\0 ")
            entities.append((r[0] & 0x0F, f"{prefix} {r[4]:02X}.{r[5]:02X}.B{int.from_bytes(r[6:8], 'big'):04X}"))
        return entities

    # ------------------------------------------------------------ onboard profiles

    def onboard_info(self):
        if self._onboard_info is None:
            r = self._call(ONBOARD_PROFILES, 0)
            self._onboard_info = OnboardInfo(
                r[0], r[1], r[2], r[3], r[4], r[5], r[6],
                int.from_bytes(r[7:9], "big"), r[9], r[10])
        return self._onboard_info

    def get_mode(self):
        return self._call(ONBOARD_PROFILES, 2)[0]

    def set_mode(self, mode):
        if mode not in (MODE_ONBOARD, MODE_HOST):
            raise ValueError("mode must be 1 (onboard) or 2 (host)")
        self._call(ONBOARD_PROFILES, 1, [mode])

    def get_current_profile(self):
        """The active profile's sector, e.g. 0x0002 for user profile 2."""
        r = self._call(ONBOARD_PROFILES, 4)
        return r[0] << 8 | r[1]

    def set_current_profile(self, sector):
        self._call(ONBOARD_PROFILES, 3, sector.to_bytes(2, "big"))

    def reload_current_profile(self, dpi_index=None):
        """Make the firmware re-read the active profile after it was rewritten.

        Selecting the profile that is already active does nothing, so hop to
        another slot and straight back (factory profiles can't be selected).
        Afterwards go to DPI level `dpi_index`, or back to the one the user was on.
        """
        current = self.get_current_profile()
        if dpi_index is None:
            dpi_index = self.get_current_dpi_index()
        entries = self.read_directory().entries
        others = [e.sector for e in entries if e.sector != current and e.enabled] + \
                 [e.sector for e in entries if e.sector != current and not e.enabled]
        if not others:
            raise IOError("no other profile slot to reload through")
        self.set_current_profile(others[0])
        self.set_current_profile(current)
        # Loading resets to the default DPI level; keep the one the user was on
        if dpi_index < len(self.read_profile(current).dpi_levels()):
            self.set_current_dpi_index(dpi_index)

    def get_current_dpi_index(self):
        return self._call(ONBOARD_PROFILES, 11)[0]

    def set_current_dpi_index(self, index):
        if not 0 <= index <= 4:
            raise ValueError("DPI index must be 0-4")
        self._call(ONBOARD_PROFILES, 12, [index])

    def read_sector(self, sector):
        size = self.onboard_info().sector_size
        data = bytearray(size)
        for off in range(0, size, 16):
            start = min(off, size - 16)  # the firmware rejects offsets past size-16
            r = self._call(ONBOARD_PROFILES, 5, sector.to_bytes(2, "big") + start.to_bytes(2, "big"))
            data[start:start + 16] = r[:16]
        return bytes(data)

    def write_sector(self, sector, data, allow_bad_crc=False):
        """Write a full sector and verify it by reading it back.

        Refuses ROM and out-of-range sectors. A sector with a bad CRC (such as
        an erased one) is only written with allow_bad_crc: the firmware stores
        it, answers HARDWARE_ERROR and then ignores the sector.
        """
        info = self.onboard_info()
        if sector >= ROM or sector >= info.sector_count:
            raise ValueError(f"sector 0x{sector:04X} is not writable")
        if len(data) != info.sector_size:
            raise ValueError(f"sector data must be {info.sector_size} bytes")
        sealed = onboard.crc_ok(data)
        if not sealed and not allow_bad_crc:
            raise ValueError("refusing to write a sector with a bad CRC")
        self._call(ONBOARD_PROFILES, 6, sector.to_bytes(2, "big") + b"\0\0" +
                   len(data).to_bytes(2, "big"), retries=0)
        for off in range(0, len(data), 16):
            self._call(ONBOARD_PROFILES, 7, data[off:off + 16].ljust(16, b"\xff"), retries=0)
        try:
            self._call(ONBOARD_PROFILES, 8, retries=0)
        except HidppError as e:
            if e.code != ERR_HARDWARE:
                raise
            if sealed:
                raise IOError(f"mouse rejected the CRC of sector 0x{sector:04X}") from e
        if self.read_sector(sector) != bytes(data):
            raise IOError(f"read-back of sector 0x{sector:04X} does not match what was written")

    def read_directory(self):
        """The user profile directory, or the ROM one if the user one was never written."""
        user = onboard.Directory.decode(self.read_sector(0x0000))
        return user or onboard.Directory.decode(self.read_sector(ROM))

    def read_profile(self, sector):
        return onboard.Profile.decode(self.read_sector(sector))

    def write_profile(self, sector, profile):
        self.write_sector(sector, profile.encode())

    # ------------------------------------------------------------ DPI and report rate

    def dpi_range(self, sensor=0):
        """(min, max, step) from the sensor's DPI list."""
        return parse_dpi_list(self._call(ADJUSTABLE_DPI, 1, [sensor])[1:])

    def get_dpi(self, sensor=0):
        r = self._call(ADJUSTABLE_DPI, 2, [sensor])
        return int.from_bytes(r[1:3], "big")

    def set_dpi(self, dpi, sensor=0):
        """Temporary in onboard mode: the next profile or DPI change overrides it."""
        self._call(ADJUSTABLE_DPI, 3, bytes([sensor]) + dpi.to_bytes(2, "big"))

    def report_intervals(self):
        """Supported report intervals in ms."""
        mask = self._call(REPORT_RATE, 0)[0]
        return [n + 1 for n in range(8) if mask & (1 << n)]

    def get_report_interval(self):
        return self._call(REPORT_RATE, 1)[0]

    def set_report_interval(self, ms):
        self._call(REPORT_RATE, 2, [ms])

    # ------------------------------------------------------------ LEDs

    def led_zones(self):
        if self._zones is None:
            self._zones = []
            for z in range(self._call(COLOR_LED_EFFECTS, 0)[0]):
                zi = self._call(COLOR_LED_EFFECTS, 1, [z])
                effects = {}
                for e in range(zi[3]):
                    ei = self._call(COLOR_LED_EFFECTS, 2, [z, e])
                    effects[int.from_bytes(ei[2:4], "big")] = e
                self._zones.append(LedZone(z, int.from_bytes(zi[1:3], "big"), effects))
        return self._zones

    def set_led(self, zone, effect, persistence=0):
        """Show an LedEffect on a zone right now. persistence 0 = RAM only."""
        z = self.led_zones()[zone]
        if effect.effect not in z.effects:
            raise ValueError(f"zone {zone} has no effect 0x{effect.effect:02X}")
        params = effect.encode()[1:]
        if effect.effect == 0x01:
            params = params[:3] + b"\x02" + params[4:]  # no ramp, as G HUB does for live colors
        self._call(COLOR_LED_EFFECTS, 3, bytes([zone, z.effects[effect.effect]]) + params + bytes([persistence]))

    def set_led_software_control(self, on):
        self._call(COLOR_LED_EFFECTS, 8, [1, 1] if on else [0, 0])

    # ------------------------------------------------------------ button spy

    def spy_button_count(self):
        return self._call(BUTTON_SPY, 0)[0]

    def spy_start(self):
        self._call(BUTTON_SPY, 1)

    def spy_stop(self):
        self._call(BUTTON_SPY, 2)

    def spy_mapping(self):
        return list(self._call(BUTTON_SPY, 3)[:self.spy_button_count()])

    def spy_events(self, timeout):
        """Yield (mask) for each button-state report within `timeout` seconds."""
        idx = self.hidpp.feature_index(BUTTON_SPY)
        for ev in self.hidpp.read_events(timeout):
            if ev.feature_index == idx and ev.event_id == 0:
                yield int.from_bytes(ev.params[0:2], "big")
