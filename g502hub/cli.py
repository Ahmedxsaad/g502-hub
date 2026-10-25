"""g502hub: configure a Logitech G502 HERO from the command line."""

import argparse
import sys
import time

from . import backup, keys, onboard
from .device import MODE_HOST, MODE_ONBOARD, ROM, DeviceNotFound, G502
from .hidpp import HidppError

# Physical buttons in onboard slot / spy bit order (docs/protocol.md §3.7)
BUTTONS = [
    ("g1", "G1 left click"), ("g2", "G2 right click"), ("g3", "G3 middle click"),
    ("g4", "G4 back"), ("g5", "G5 forward"), ("g6", "G6 sniper"),
    ("g7", "G7 front of left"), ("g8", "G8 behind G7"), ("g9", "G9 behind wheel"),
    ("tilt-right", "wheel tilt right"), ("tilt-left", "wheel tilt left"),
]
BUTTON_ALIASES = {"left": "g1", "right": "g2", "middle": "g3", "back": "g4",
                  "forward": "g5", "sniper": "g6"}
FEATURE_NAMES = {
    0x0000: "Root", 0x0001: "FeatureSet", 0x0003: "DeviceFwVersion",
    0x0005: "DeviceName", 0x00C2: "DfuControlSigned", 0x1300: "LedControl",
    0x1802: "DeviceReset", 0x1806: "ConfigurableDeviceProperties",
    0x1E00: "EnableHiddenFeatures", 0x2201: "AdjustableDpi",
    0x8060: "AdjustableReportRate", 0x8070: "ColorLedEffects",
    0x8100: "OnboardProfiles", 0x8110: "MouseButtonSpy",
}


def button_slot(name):
    name = BUTTON_ALIASES.get(name.lower(), name.lower())
    for i, (key, _) in enumerate(BUTTONS):
        if key == name:
            return i
    raise ValueError(f"unknown button '{name}' (use g1-g9, tilt-left, tilt-right)")


def parse_color(text):
    text = text.lstrip("#")
    if len(text) != 6:
        raise ValueError("colors are RRGGBB hex, e.g. ff8800")
    return tuple(bytes.fromhex(text))


def slot_sector(dev, slot):
    entries = dev.read_directory().entries
    if not 1 <= slot <= len(entries):
        raise ValueError(f"slot must be 1-{len(entries)}")
    return entries[slot - 1].sector


def zone_label(dev, zone):
    return f"{dev.led_zones()[zone].name} (zone {zone})"


class Session:
    """Wraps a device and makes one automatic backup before the first write."""

    def __init__(self, dev):
        self.dev = dev
        self.backed_up = False

    def ensure_backup(self):
        if not self.backed_up:
            path = backup.save(backup.dump(self.dev))
            print(f"backup saved to {path}")
            self.backed_up = True

    def edit_profile(self, slot, change):
        dev = self.dev
        sector = slot_sector(dev, slot)
        profile = dev.read_profile(sector)
        change(profile)
        data = profile.encode()
        if data == dev.read_sector(sector):
            print("no change")
            return
        self.ensure_backup()
        dev.write_sector(sector, data)
        print(f"slot {slot} written and verified")
        if dev.get_mode() == MODE_ONBOARD and dev.get_current_profile() == sector:
            dev.reload_current_profile()  # so the change applies now


# ------------------------------------------------------------ commands

def cmd_info(dev, args):
    print(f"{dev.name()}  ({dev.path})")
    for kind, fw in dev.firmware():
        print(f"  firmware {('main', 'bootloader', 'hardware')[kind] if kind < 3 else kind}: {fw}")
    info = dev.onboard_info()
    mode = {MODE_ONBOARD: "onboard", MODE_HOST: "host (software)"}.get(dev.get_mode(), "?")
    print(f"  mode: {mode}")
    if dev.get_mode() == MODE_ONBOARD:
        cur = dev.get_current_profile()
        print(f"  active profile: {'ROM ' if cur >= ROM else ''}slot {cur & 0xFF}, "
              f"DPI index {dev.get_current_dpi_index()}")
    print(f"  live DPI: {dev.get_dpi()}, report rate: {1000 // dev.get_report_interval()} Hz")
    lo, hi, step = dev.dpi_range()
    print(f"  DPI range: {lo}-{hi} step {step}; report rates: "
          f"{', '.join(str(1000 // ms) for ms in dev.report_intervals())} Hz")
    print(f"  onboard: {info.profile_count} profiles, {info.button_count} buttons, "
          f"{info.sector_count} sectors x {info.sector_size} B, profile format {info.profile_format}, "
          f"G-Shift {'yes' if info.has_gshift else 'no'}")
    zones = ", ".join(f"{z.name}: " + "/".join(onboard.LED_EFFECTS.get(e, hex(e)) for e in z.effects)
                      for z in dev.led_zones())
    print(f"  LED zones: {zones}")
    if args.features:
        print("\n  idx  id      ver  name")
        for idx, fid, flags, ver in dev.features():
            hidden = " [hidden]" if flags & 0x40 else ""
            print(f"  {idx:>3}  0x{fid:04X}  {ver:>3}  {FEATURE_NAMES.get(fid, '?')}{hidden}")


def cmd_profiles(dev, args):
    directory = dev.read_directory()
    current = dev.get_current_profile() if dev.get_mode() == MODE_ONBOARD else None
    print(f"{'':2}{'slot':<5}{'name':<14}{'rate':<9}{'DPI (* default, ^ shift)':<30}lighting")
    for n, entry in enumerate(directory.entries, 1):
        p = dev.read_profile(entry.sector)
        dpis = []
        for i, d in p.dpi_levels():
            mark = ("*" if i == p.default_dpi_index else "") + ("^" if i == p.shift_dpi_index else "")
            dpis.append(f"{d}{mark}")
        lights = " | ".join(led.describe() for led in p.leds)
        flag = ">" if entry.sector == current else " "
        state = "" if entry.enabled else " (disabled)"
        print(f"{flag} {n:<5}{(p.name or '-')[:13]:<14}{p.report_rate_hz:>4} Hz  "
              f"{' '.join(dpis):<30}{lights}{state}")


def cmd_show(dev, args):
    sector = slot_sector(dev, args.slot)
    p = dev.read_profile(sector)
    print(f"Slot {args.slot} (sector 0x{sector:04X}): {p.name or '(no name)'}")
    print(f"  report rate: {p.report_rate_hz} Hz")
    for i, d in enumerate(p.dpi):
        tags = [t for t, on in (("default", i == p.default_dpi_index), ("shift", i == p.shift_dpi_index)) if on]
        print(f"  DPI {i + 1}: {d if d not in (0, 0xFFFF) else 'off'} {' '.join(tags)}")
    print(f"  angle snapping: {'on' if p.angle_snapping == 1 else 'off'}")
    print(f"\n  {'button':<22}{'normal':<26}G-Shift layer")
    for i, (_, label) in enumerate(BUTTONS):
        print(f"  {label:<22}{p.buttons[i].describe():<26}{p.gshift[i].describe()}")
    print()
    for z, (led, alt) in enumerate(zip(p.leds, p.alt_leds)):
        extra = "" if alt.encode() == led.encode() else f"   (alt block: {alt.describe()})"
        print(f"  lighting {zone_label(dev, z)}: {led.describe()}{extra}")
    if args.raw:
        print()
        for off in range(0, len(p.raw), 16):
            print(f"  {off:3d}  {p.raw[off:off + 16].hex(' ')}")


def cmd_backup(dev, args):
    print(f"backup saved to {backup.save(backup.dump(dev), args.output)}")


def cmd_restore(dev, args):
    data = backup.load(args.file)
    print(f"backup from {data.get('created', '?')}, {len(data['sectors'])} sectors")
    if not args.yes:
        sys.exit("re-run with --yes to write it to the mouse")
    Session(dev).ensure_backup()
    written = backup.restore(dev, data)
    print(f"{len(written)} sector(s) restored" if written else "mouse already matches the backup")


def cmd_activate(dev, args):
    dev.set_current_profile(slot_sector(dev, args.slot))
    print(f"slot {args.slot} active")


def cmd_set(dev, args):
    def change(p):
        if args.rate:
            if 1000 % args.rate or 1000 // args.rate not in dev.report_intervals():
                raise ValueError("rate must be 125, 250, 500 or 1000")
            p.report_interval_ms = 1000 // args.rate
        if args.dpi:
            lo, hi, step = dev.dpi_range()
            values = [int(v) for v in args.dpi.split(",")]
            if not 1 <= len(values) <= 5:
                raise ValueError("give 1 to 5 DPI values")
            for v in values:
                if not lo <= v <= hi or v % step:
                    raise ValueError(f"DPI {v} must be {lo}-{hi} in steps of {step}")
            p.dpi = values + [0] * (5 - len(values))
            p.default_dpi_index = min(p.default_dpi_index, len(values) - 1)
            p.shift_dpi_index = min(p.shift_dpi_index, len(values) - 1)
        for attr, value in (("default_dpi_index", args.default), ("shift_dpi_index", args.shift)):
            if value is not None:
                if not 1 <= value <= len(p.dpi_levels()):
                    raise ValueError("DPI level numbers start at 1 and must be enabled")
                setattr(p, attr, value - 1)
        if args.name is not None:
            p.name = args.name
        if args.default_name:
            p.name = None
        if args.angle_snapping:
            p.angle_snapping = 1 if args.angle_snapping == "on" else 0
    Session(dev).edit_profile(args.slot, change)


def cmd_bind(dev, args):
    slot = button_slot(args.button)
    action = onboard.Binding.parse(args.action)

    def change(p):
        (p.gshift if args.gshift else p.buttons)[slot] = action
    Session(dev).edit_profile(args.slot, change)


def make_led(args):
    if args.effect == "off":
        return onboard.LedEffect.off()
    if args.effect == "cycle":
        return onboard.LedEffect.cycle(args.period, args.brightness)
    if not args.color:
        raise ValueError(f"{args.effect} needs a color")
    if args.effect == "fixed":
        return onboard.LedEffect.fixed(parse_color(args.color))
    return onboard.LedEffect.breathing(parse_color(args.color), args.period, args.brightness)


def cmd_led(dev, args):
    led = make_led(args)
    zones = range(len(dev.led_zones())) if args.zone == "all" else [int(args.zone)]

    def change(p):
        for z in zones:
            p.leds[z] = led
            p.alt_leds[z] = led
    Session(dev).edit_profile(args.slot, change)


def cmd_enable(dev, args, enabled=True):
    directory = dev.read_directory()
    if not 1 <= args.slot <= len(directory.entries):
        raise ValueError(f"slot must be 1-{len(directory.entries)}")
    directory.entries[args.slot - 1].enabled = enabled
    data = directory.encode(dev.onboard_info().sector_size)
    if data == dev.read_sector(0):
        print("no change")
        return
    current = dev.get_current_profile()
    Session(dev).ensure_backup()
    dev.write_sector(0, data)
    dev.set_current_profile(current)  # directory writes can shift the current profile
    print(f"slot {args.slot} {'enabled' if enabled else 'disabled'}")


def cmd_live_led(dev, args):
    dev.set_led(int(args.zone), make_led(args), persistence=0)
    print("shown until the next profile change or replug (nothing saved)")


def cmd_mode(dev, args):
    if args.mode:
        dev.set_mode(MODE_ONBOARD if args.mode == "onboard" else MODE_HOST)
    print("onboard" if dev.get_mode() == MODE_ONBOARD else "host")


def cmd_spy(dev, args):
    print(f"press buttons for {args.seconds} s ...", flush=True)
    dev.spy_start()
    held, deadline = 0, time.monotonic() + args.seconds
    try:
        while (left := deadline - time.monotonic()) > 0:
            for mask in dev.spy_events(min(left, 0.25)):
                for i in range(16):
                    bit = 1 << i
                    if (mask ^ held) & bit:
                        label = BUTTONS[i][1] if i < len(BUTTONS) else f"bit {i}"
                        print(f"{time.strftime('%H:%M:%S')}  {'down' if mask & bit else 'up  '}  "
                              f"bit {i:<2} {label}", flush=True)
                held = mask
    finally:
        dev.spy_stop()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="g502hub", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="device, firmware and live settings")
    p.add_argument("--features", action="store_true", help="also list HID++ features")
    p.set_defaults(func=cmd_info)

    sub.add_parser("profiles", help="list onboard profiles").set_defaults(func=cmd_profiles)

    p = sub.add_parser("show", help="show one profile in detail")
    p.add_argument("slot", type=int)
    p.add_argument("--raw", action="store_true", help="also dump the raw sector")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("backup", help="save the whole onboard memory to a file")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="write a backup back to the mouse")
    p.add_argument("file")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("activate", help="switch to a profile slot")
    p.add_argument("slot", type=int)
    p.set_defaults(func=cmd_activate)

    p = sub.add_parser("set", help="change a profile's rate, DPI levels or name")
    p.add_argument("slot", type=int)
    p.add_argument("--rate", type=int, help="125, 250, 500 or 1000 Hz")
    p.add_argument("--dpi", help="comma-separated DPI levels, e.g. 800,1600,3200")
    p.add_argument("--default", type=int, help="DPI level used when the profile loads (1-5)")
    p.add_argument("--shift", type=int, help="DPI level used while sniper is held (1-5)")
    p.add_argument("--name")
    p.add_argument("--default-name", action="store_true")
    p.add_argument("--angle-snapping", choices=["on", "off"])
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("bind", help="assign an action to a button",
                       epilog="actions: left right middle back forward button6..16 | key:ctrl+c | "
                              "media:volume-up | " + " ".join(onboard.SPECIAL_CODES) +
                              " | profile-select:N | disabled | unassigned. Media keys: " +
                              " ".join(keys.CONSUMER))
    p.add_argument("slot", type=int)
    p.add_argument("button", help="g1-g9, tilt-left, tilt-right")
    p.add_argument("action")
    p.add_argument("--gshift", action="store_true", help="set the G-Shift layer instead")
    p.set_defaults(func=cmd_bind)

    for name, func, help_ in (("led", cmd_led, "set a profile's lighting"),
                              ("live-led", cmd_live_led, "show lighting now without saving")):
        p = sub.add_parser(name, help=help_)
        if name == "led":
            p.add_argument("slot", type=int)
        p.add_argument("zone", help="0, 1" + (" or all" if name == "led" else ""))
        p.add_argument("effect", choices=["off", "fixed", "breathing", "cycle"])
        p.add_argument("color", nargs="?", help="RRGGBB")
        p.add_argument("--period", type=int, default=8000, help="ms (breathing, cycle)")
        p.add_argument("--brightness", type=int, default=100, help="1-100")
        p.set_defaults(func=func)

    for name, enabled in (("enable", True), ("disable", False)):
        p = sub.add_parser(name, help=f"{name} a slot for profile cycling")
        p.add_argument("slot", type=int)
        p.set_defaults(func=lambda dev, a, e=enabled: cmd_enable(dev, a, e))

    p = sub.add_parser("mode", help="show or set onboard/host mode")
    p.add_argument("mode", nargs="?", choices=["onboard", "host"])
    p.set_defaults(func=cmd_mode)

    p = sub.add_parser("spy", help="print raw button presses")
    p.add_argument("--seconds", type=float, default=20)
    p.set_defaults(func=cmd_spy)

    args = ap.parse_args(argv)
    try:
        with G502() as dev:
            args.func(dev, args)
    except (DeviceNotFound, ValueError, IOError, HidppError, TimeoutError) as e:
        sys.exit(f"g502hub: {e}")


if __name__ == "__main__":
    main()
