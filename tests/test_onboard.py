"""Codec tests against a real dump of this G502 HERO (firmware U1 69.00)."""

import json
from pathlib import Path

import pytest

from g502hub import macro, onboard
from g502hub.device import parse_dpi_list
from g502hub.onboard import (Binding, Consumer, Directory, Key, LedEffect, MouseButton,
                             Profile, Special, Unassigned)

FIXTURE = json.loads((Path(__file__).parent / "fixtures/onboard-c08b.json").read_text())
SECTORS = {int(k, 16): bytes.fromhex(v) for k, v in FIXTURE["sectors"].items()}
USER_PROFILES = [1, 2, 3, 4, 5]
ROM_PROFILES = [0x0101, 0x0102, 0x0103, 0x0104, 0x0105]


def test_crc_check_value():
    assert onboard.crc16(b"123456789") == 0x29B1


@pytest.mark.parametrize("sector", [0] + USER_PROFILES)
def test_user_sectors_have_valid_crc(sector):
    assert onboard.crc_ok(SECTORS[sector])


@pytest.mark.parametrize("sector", USER_PROFILES)
def test_profile_round_trip_is_byte_exact(sector):
    assert Profile.decode(SECTORS[sector]).encode() == SECTORS[sector]


@pytest.mark.parametrize("sector", ROM_PROFILES)
def test_rom_profile_round_trip_except_crc(sector):
    # Factory sectors carry no CRC, so only the payload has to survive
    assert Profile.decode(SECTORS[sector]).encode()[:-2] == SECTORS[sector][:-2]


def test_decode_gshift_profile():
    p = Profile.decode(SECTORS[3])
    assert p.report_rate_hz == 500
    assert p.dpi_levels() == [(0, 2800)]
    assert p.buttons[0] == MouseButton(0x0001)
    assert p.buttons[5] == Special(0x0B)
    assert p.buttons[6].describe() == "key ctrl+c"
    assert p.buttons[7].describe() == "key ctrl+v"
    assert all(isinstance(b, Unassigned) for b in p.gshift)
    assert p.leds[0].describe() == "fixed #ffffff"
    assert p.leds[1].color == (0xCD, 0xAB, 0x8F)
    assert p.name == ""


def test_decode_active_profile():
    p = Profile.decode(SECTORS[2])
    assert [d for _, d in p.dpi_levels()] == [400, 800, 1600, 2400]
    assert p.default_dpi_index == 2
    assert p.leds[0] == LedEffect(0x0A, (0x00, 0xDC, 0xFF), 8000, 0)
    assert p.leds[0].brightness == 100
    assert [b.describe() for b in p.buttons[5:11]] == [
        "dpi-shift", "dpi-down", "dpi-up", "profile-cycle", "tilt-right", "tilt-left"]


def test_rom_profile_has_default_name():
    assert Profile.decode(SECTORS[0x0101]).name is None


def test_edit_touches_only_the_edited_field():
    original = SECTORS[3]
    p = Profile.decode(original)
    p.name = "Test"
    p.gshift[6] = Binding.parse("key:ctrl+x")
    data = p.encode()
    changed = {i for i in range(len(data)) if data[i] != original[i]}
    assert changed <= set(range(160, 208)) | set(range(120, 124)) | {253, 254}
    again = Profile.decode(data)
    assert again.name == "Test"
    assert again.gshift[6] == Key(0x01, 0x1B)
    assert onboard.crc_ok(data)


def test_long_name_is_truncated_to_24_units():
    p = Profile.decode(SECTORS[3])
    p.name = "x" * 40
    assert Profile.decode(p.encode()).name == "x" * 24


def test_led_effect_change_drops_stale_bytes():
    breathing = Profile.decode(SECTORS[2]).leds[0]
    cycle = LedEffect.cycle(5000, brightness=50)
    assert cycle.encode() == bytes([0x03, 0, 0, 0, 0, 0, 0x13, 0x88, 50, 0, 0])
    kept = LedEffect(0x0A, (1, 2, 3), 1000, 0, raw=breathing.raw)
    assert kept.encode()[6] == breathing.raw[6]  # waveform byte preserved


@pytest.mark.parametrize("text, raw", [
    ("left", "80010001"), ("back", "80010008"), ("forward", "80010010"),
    ("key:ctrl+shift+t", "80020317"), ("key:f13", "80020068"),
    ("media:volume-up", "800300e9"), ("dpi-shift", "9007ffff"), ("gshift", "900bffff"),
    ("profile-select:3", "900dff03"), ("disabled", "8000ffff"), ("unassigned", "ffffffff"),
])
def test_binding_parse_and_encode(text, raw):
    binding = Binding.parse(text)
    assert binding.encode().hex() == raw
    assert Binding.decode(bytes.fromhex(raw)) == binding


def test_unknown_binding_survives():
    raw = bytes.fromhex("a1b2c3d4")
    assert Binding.decode(raw).encode() == raw


def test_consumer_describe():
    assert Consumer(0x00CD).describe() == "media play-pause"


def test_directory_round_trip_and_disable():
    d = Directory.decode(SECTORS[0])
    assert [(e.sector, e.enabled) for e in d.entries] == [(i, True) for i in range(1, 6)]
    assert d.encode(255) == SECTORS[0]
    d.entries[3].enabled = False
    data = d.encode(255)
    assert {i for i in range(255) if data[i] != SECTORS[0][i]} == {14, 253, 254}


def test_directory_shrinks_cleanly():
    d = Directory.decode(SECTORS[0])
    d.entries.pop()
    data = d.encode(255)
    assert data[16:20] == b"\xff\xff\x00\x00"
    assert data[20:24] == b"\xff" * 4
    assert [e.sector for e in Directory.decode(data).entries] == [1, 2, 3, 4]


def test_blank_directory_means_rom():
    assert Directory.decode(b"\x00" * 255) is None
    assert Directory.decode(b"\xff" * 255) is None


def test_rom_directory_parses():
    d = Directory.decode(SECTORS[0x0100])
    assert [e.sector for e in d.entries] == ROM_PROFILES


def test_dpi_list_range():
    assert parse_dpi_list(bytes.fromhex("0064e0326400" + "00" * 9)) == (100, 25600, 50)


def test_macro_round_trip_across_a_jump():
    steps = [("key-down", 0x01, 0x06), ("delay", 50), ("key-up", 0x01, 0x06),
             ("wheel", -3), ("move", -10, 250), ("consumer-down", 0xCD)]
    first = macro.encode(steps[:3])[:-1] + macro.encode_step(("jump", 0, 7, 16))
    second = bytes(16) + macro.encode(steps[3:])
    pages = {6: first.ljust(255, b"\xff"), 7: second.ljust(255, b"\xff")}
    assert macro.decode(pages.__getitem__, 6, 0) == steps + [("end",)]


def test_macro_describe():
    assert macro.describe(("key-down", 0x01, 0x06)) == "key-down ctrl+c"
    assert macro.describe(("delay", 30)) == "delay 30 ms"
