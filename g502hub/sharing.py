"""Profiles as files people can share: one onboard profile, byte-exact, plus a readable summary."""

import json

from . import __version__, onboard

FORMAT = "g502-hub-profile"
VERSION = 1
DEVICE = "046d:c08b"
SUFFIX = ".g502profile"


class ShareError(ValueError):
    pass


def export(profile):
    """A JSON text for one onboard profile."""
    data = profile.encode()
    summary = {
        "name": profile.name,
        "report_rate_hz": profile.report_rate_hz,
        "dpi": [dpi for _, dpi in profile.dpi_levels()],
        "default_dpi_level": next((n for n, (s, _) in enumerate(profile.dpi_levels(), 1)
                                   if s == profile.default_dpi_index), None),
        "lighting": [led.describe() for led in profile.leds],
        "buttons": [b.describe() for b in profile.buttons[:11]],
        "gshift": [b.describe() for b in profile.gshift[:11]],
    }
    return json.dumps({"format": FORMAT, "version": VERSION, "device": DEVICE,
                       "app": f"G502 Hub {__version__}", "summary": summary,
                       "sector": data.hex()}, indent=2) + "\n"


def load(text):
    """(Profile, notes) from an exported file. Notes explain anything that was changed."""
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise ShareError(f"not a profile file ({e})") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ShareError("not a G502 Hub profile file")
    if doc.get("version", 0) > VERSION:
        raise ShareError("made by a newer version of G502 Hub; update to import it")
    if doc.get("device") != DEVICE:
        raise ShareError(f"made for another device ({doc.get('device')}), not the G502 HERO")
    try:
        data = bytes.fromhex(doc["sector"])
    except (KeyError, TypeError, ValueError):
        raise ShareError("the profile data is missing or damaged") from None
    if len(data) != 255 or not onboard.crc_ok(data):
        raise ShareError("the profile data is damaged (checksum mismatch)")
    profile = onboard.Profile.decode(data)
    notes = []
    # Macros live in other memory sectors that aren't part of the file
    for layer, bindings in (("", profile.buttons), ("G-Shift ", profile.gshift)):
        for i, b in enumerate(bindings):
            if isinstance(b, onboard.Macro):
                bindings[i] = onboard.Disabled()
                notes.append(f"{layer}button {i + 1} had a macro, which can't be shared, so it's disabled")
    return profile, notes
