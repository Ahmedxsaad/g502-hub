import os
import time

import pytest

from g502hub import keys, macro, macros
from g502hub.effects import macroplayer, spy
from g502hub.macros import Macro, MacroError, Step

US = {**{c: (0, keys.KEYS[c]) for c in "abcdefghijklmnopqrstuvwxyz0123456789"},
      **{c.upper(): (0x02, keys.KEYS[c]) for c in "abcdefghijklmnopqrstuvwxyz"},
      "!": (0x02, keys.KEYS["1"]), " ": (0, keys.KEYS["space"])}
# AZERTY: digits need Shift, 'a' is the US 'q' key, '@' is AltGr + the '0' key
AZERTY = {"a": (0, keys.KEYS["q"]), "A": (0x02, keys.KEYS["q"]), "1": (0x02, keys.KEYS["1"]),
          "&": (0, keys.KEYS["1"]), "@": (0x40, keys.KEYS["0"]), "z": (0, keys.KEYS["w"])}


def us(char):
    return US.get(char)


def azerty(char):
    return AZERTY.get(char)


def every_step():
    return [Step("key", {"combo": "ctrl+s"}), Step("key-down", {"combo": "shift"}),
            Step("key-up", {"combo": "shift"}), Step("text", {"text": "Hi!"}), Step("delay", {"ms": 250}),
            Step("click", {"button": "left"}), Step("button-down", {"button": "back"}),
            Step("button-up", {"button": "back"}), Step("scroll", {"amount": -3}),
            Step("hscroll", {"amount": 2}), Step("move", {"dx": 10, "dy": -5}),
            Step("media", {"key": "volume-up"})]


# ------------------------------------------------------------ model

def test_round_trip_and_load_skips_junk():
    m = Macro("Everything", every_step(), mode="toggle", gap_ms=15)
    assert Macro.from_dict(m.to_dict()) == m
    loaded = macros.load([m.to_dict(), {"name": "x", "steps": [{"kind": "laser"}]}, "junk",
                          {"name": "", "steps": []}, {"name": "y", "steps": [{"kind": "delay", "args": {"ms": -1}}]}])
    assert loaded == [m]


@pytest.mark.parametrize("step", [
    Step("key", {"combo": "ctrl+nope"}), Step("key", {"combo": ""}), Step("text", {"text": ""}),
    Step("delay", {"ms": "5"}), Step("click", {"button": "top"}), Step("scroll", {"amount": True}),
    Step("move", {"dx": 1}), Step("media", {"key": "laser"}), Step("teleport", {}),
])
def test_bad_steps_are_rejected(step):
    with pytest.raises(ValueError):
        step.validate()


def test_mouse_macros_only_play_once():
    with pytest.raises(ValueError):
        Macro("m", [], mode="while-held", target="mouse").validate()
    Macro("m", [], target="mouse").validate()


def test_descriptions():
    texts = [s.describe() for s in every_step()]
    assert texts == ["Press ctrl+s", "Hold shift", "Release shift", "Type “Hi!”", "Wait 250 ms",
                     "Left click", "Hold the back button", "Release the back button", "Scroll down 3",
                     "Scroll right 2", "Move the pointer 10, -5", "Volume up"]
    assert Step("key", {"combo": "ctrl+s"}).describe(lambda m, u: "Ctrl + S") == "Press Ctrl + S"
    assert Step("delay", {"ms": 1500}).describe() == "Wait 1.5 s"
    assert Macro("m", every_step()[:2], target="mouse").describe() == "2 steps · plays once · stored in the mouse"
    assert Macro("m", [], mode="while-held").describe() == "0 steps · repeats while held · run by the app"


def test_unknown_usages_round_trip():
    s = Step("key", {"combo": "ctrl+key-0x87"}).validate()
    assert macros.step_events(s, us) == [("key", 0x01, 0x87, True), ("key", 0x01, 0x87, False)]
    assert macros.parse_media("consumer-0x0183") == 0x0183


# ------------------------------------------------------------ expand

def test_expand_every_kind():
    events = macros.expand(Macro("m", every_step()), us)
    S, B = keys.KEYS["s"], 0x08
    assert events == [
        ("key", 0x01, S, True), ("key", 0x01, S, False),
        ("key", 0x02, 0, True), ("key", 0x02, 0, False),
        ("key", 0x02, keys.KEYS["h"], True), ("key", 0x02, keys.KEYS["h"], False),
        ("key", 0, keys.KEYS["i"], True), ("key", 0, keys.KEYS["i"], False),
        ("key", 0x02, keys.KEYS["1"], True), ("key", 0x02, keys.KEYS["1"], False),
        ("delay", 250),
        ("button", 0x01, True), ("button", 0x01, False), ("button", B, True), ("button", B, False),
        ("wheel", -3), ("hwheel", 2), ("move", 10, -5),
        ("consumer", 0x00E9, True), ("consumer", 0x00E9, False),
    ]


def test_expand_gap_between_steps():
    m = Macro("m", [Step("click", {"button": "left"}), Step("click", {"button": "right"})], gap_ms=40)
    assert macros.expand(m, us) == [("button", 1, True), ("button", 1, False), ("delay", 40),
                                    ("button", 2, True), ("button", 2, False)]


def test_text_follows_the_layout():
    m = Macro("m", [Step("text", {"text": "a1@z"})])
    q, one, zero, w = keys.KEYS["q"], keys.KEYS["1"], keys.KEYS["0"], keys.KEYS["w"]
    assert macros.expand(m, azerty) == [("key", 0, q, True), ("key", 0, q, False),
                                        ("key", 0x02, one, True), ("key", 0x02, one, False),
                                        ("key", 0x40, zero, True), ("key", 0x40, zero, False),
                                        ("key", 0, w, True), ("key", 0, w, False)]
    # Whitespace works even if the layout lookup doesn't know it
    assert macros.expand(Macro("m", [Step("text", {"text": "\n"})]), lambda c: None) == \
        [("key", 0, keys.KEYS["enter"], True), ("key", 0, keys.KEYS["enter"], False)]
    with pytest.raises(MacroError, match="can't be typed"):
        macros.expand(Macro("m", [Step("text", {"text": "é"})]), us)


# ------------------------------------------------------------ in the mouse

def test_to_onboard_is_byte_exact():
    m = Macro("m", [Step("key", {"combo": "ctrl+c"}), Step("delay", {"ms": 300}), Step("click", {"button": "back"}),
                    Step("scroll", {"amount": 2}), Step("media", {"key": "mute"}), Step("move", {"dx": -4, "dy": 9})],
              target="mouse")
    C = keys.KEYS["c"]
    want = macro.encode([("key-down", 0x01, C), ("key-up", 0x01, C), ("delay", 300),
                         ("button-down", 0x08), ("button-up", 0x08), ("wheel", 2),
                         ("consumer-down", 0x00E2), ("consumer-up", 0x00E2), ("move", -4, 9)])
    assert macros.to_onboard(m, us) == want
    assert want[-1] == 0xFF and macros.onboard_size(m, us) == len(want)


def test_onboard_splits_big_values():
    steps = macros.onboard_steps(Macro("m", [Step("delay", {"ms": 70000}), Step("scroll", {"amount": 300})],
                                       target="mouse"), us)
    assert steps == [("delay", 65535), ("delay", 4465), ("wheel", 127), ("wheel", 127), ("wheel", 46)]


def test_onboard_limits():
    long = Macro("m", [Step("text", {"text": "a" * 60})], target="mouse")  # 60 x 2 x 3 bytes
    with pytest.raises(MacroError, match="too long"):
        macros.to_onboard(long, us)
    with pytest.raises(MacroError, match="once"):
        macros.to_onboard(Macro("m", [], mode="toggle"), us)
    fits = Macro("m", [Step("text", {"text": "a" * 42})], target="mouse")  # 252 + END = 253
    assert len(macros.to_onboard(fits, us)) == macros.ONBOARD_CAPACITY


def test_from_onboard_ghub_style():
    two = keys.KEYS["2"]
    decoded = [("key-down", 0, two), ("delay", 300), ("key-up", 0, two), ("delay", 1000),
               ("key-down", 0x02, keys.KEYS["a"]), ("key-up", 0x02, keys.KEYS["a"]),
               ("button-down", 0x01), ("button-up", 0x01), ("consumer-down", 0x00CD), ("consumer-up", 0x00CD),
               ("key-down", 0, 0), ("wait-release",), ("end",)]
    m = macros.from_onboard(decoded)
    assert [(s.kind, s.args) for s in m.steps] == [
        ("key-down", {"combo": "2"}), ("delay", {"ms": 300}), ("key-up", {"combo": "2"}),
        ("delay", {"ms": 1000}), ("key", {"combo": "shift+a"}), ("click", {"button": "left"}),
        ("media", {"key": "play-pause"})]
    assert m.target == "mouse" and m.mode == "once"
    m.validate()


def test_onboard_round_trip_through_the_decoder():
    m = Macro("m", [Step("key", {"combo": "alt+tab"}), Step("delay", {"ms": 80}), Step("hscroll", {"amount": -1})],
              target="mouse")
    sector = macros.to_onboard(m, us).ljust(255, b"\xff")
    back = macros.from_onboard(macro.decode(lambda page: sector, 7, 0))
    assert [(s.kind, s.args) for s in back.steps] == [(s.kind, s.args) for s in m.steps]


# ------------------------------------------------------------ recording

def test_from_recording():
    A, B = keys.KEYS["a"], keys.KEYS["b"]
    events = [(0.0, A, 0, True), (0.01, A, 0, False),      # a quick tap
              (0.5, 0, 0x01, True),                        # Ctrl held...
              (0.6, B, 0x01, True), (0.61, B, 0x01, False),  # ...while tapping b
              (0.7, 0, 0x01, False),
              (0.705, A, 0, True), (2.0, A, 0, False)]     # a held down for a while
    steps = macros.from_recording(events)
    assert [(s.kind, s.args) for s in steps] == [
        ("key", {"combo": "a"}), ("delay", {"ms": 490}), ("key-down", {"combo": "ctrl"}),
        ("delay", {"ms": 100}), ("key", {"combo": "b"}), ("delay", {"ms": 90}),
        ("key-up", {"combo": "ctrl"}), ("key-down", {"combo": "a"}), ("delay", {"ms": 1295}),
        ("key-up", {"combo": "a"})]
    # A modifier on its own, tapped, and keys with the held modifiers folded in
    assert [(s.kind, s.args) for s in macros.from_recording([(0, 0, 0x02, True), (0.01, 0, 0x02, False)])] == \
        [("key", {"combo": "shift"})]
    assert [(s.kind, s.args) for s in macros.from_recording([(0, A, 0x05, True), (0.01, A, 0x05, False)])] == \
        [("key", {"combo": "ctrl+alt+a"})]
    for s in steps:
        s.validate()


# ------------------------------------------------------------ the player (fake device only)

class FakeDevice:
    def __init__(self):
        self.log = []

    def write(self, type_, code, value):
        self.log.append((time.monotonic(), type_, code, value))

    def syn(self):
        pass

    def close(self):
        self.closed = True

    def keys(self):
        return [(code, value) for _, type_, code, value in self.log if type_ == macroplayer.EV_KEY]


def wait_idle(player, timeout=3.0):
    deadline = time.monotonic() + timeout
    while player.running() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not player.running()


def test_once_plays_in_order_and_ignores_repeat_presses():
    dev = FakeDevice()
    player = macroplayer.MacroPlayer(dev)
    S = keys.HID_TO_EVDEV[keys.KEYS["s"]]
    events = [("key", 0x01, keys.KEYS["s"], True), ("key", 0x01, keys.KEYS["s"], False), ("delay", 120),
              ("button", 0x01, True), ("button", 0x01, False), ("wheel", 2), ("move", 3, -4),
              ("consumer", 0x00E9, True), ("consumer", 0x00E9, False)]
    start = time.monotonic()
    player.press("g4", events, "once")
    player.press("g4", events, "once")  # still playing: ignored
    wait_idle(player)
    assert dev.keys() == [(29, 1), (S, 1), (S, 0), (29, 0), (0x110, 1), (0x110, 0), (115, 1), (115, 0)]
    rel = [(code, value) for _, t, code, value in dev.log if t == macroplayer.EV_REL]
    assert rel == [(macroplayer.REL_WHEEL, 2), (macroplayer.REL_X, 3), (macroplayer.REL_Y, -4)]
    button_at = next(t for t, _, code, v in dev.log if code == 0x110 and v == 1)
    assert button_at - start >= 0.12  # the delay was honoured


def test_while_held_loops_until_release_and_releases_what_it_holds():
    dev = FakeDevice()
    player = macroplayer.MacroPlayer(dev)
    A = keys.HID_TO_EVDEV[keys.KEYS["a"]]
    player.press(5, [("key", 0x02, keys.KEYS["a"], True), ("delay", 30)], "while-held")
    time.sleep(0.15)
    assert 5 in player.running()
    player.release(5)
    wait_idle(player)
    # Held keys counted once (no repeat presses of an already-held key), then released at the end
    assert dev.keys() == [(42, 1), (A, 1), (A, 0), (42, 0)]


def test_toggle_second_press_stops():
    dev = FakeDevice()
    player = macroplayer.MacroPlayer(dev)
    player.press("t", [("wheel", 1), ("delay", 20)], "toggle")
    time.sleep(0.12)
    player.release("t")  # releasing doesn't stop a toggle
    assert "t" in player.running()
    player.press("t", [], "toggle")
    wait_idle(player)
    loops = sum(1 for _, t, *_ in dev.log if t == macroplayer.EV_REL)
    assert loops >= 3


def test_empty_loop_does_not_spin():
    dev = FakeDevice()
    player = macroplayer.MacroPlayer(dev)
    player.press("x", [("wheel", 1)], "while-held")
    time.sleep(0.2)
    player.stop_all()
    wait_idle(player)
    assert len(dev.log) <= 25  # at most one round per 10 ms


def test_stop_all_cuts_long_delays_short():
    dev = FakeDevice()
    player = macroplayer.MacroPlayer(dev)
    player.press("x", [("button", 0x02, True), ("delay", 10_000), ("button", 0x02, False)], "once")
    time.sleep(0.05)
    t0 = time.monotonic()
    player.stop_all()
    assert time.monotonic() - t0 < 0.5
    assert dev.keys() == [(0x111, 1), (0x111, 0)]


def test_device_errors_are_reported_not_raised(monkeypatch):
    def refuse():
        raise PermissionError(13, "Permission denied", "/dev/uinput")
    monkeypatch.setattr(macroplayer, "_UInputBackend", refuse)
    player = macroplayer.MacroPlayer()
    player.press("x", [("wheel", 1)], "once")
    assert player.state == "error" and "/dev/uinput" in player.error
    assert player.running() == set()


def test_device_key_coverage():
    codes = set(macroplayer.device_keys())
    assert set(keys.HID_TO_EVDEV.values()) <= codes and set(keys.MODIFIER_EVDEV.values()) <= codes
    assert set(keys.CONSUMER.values()) == set(macroplayer.CONSUMER_EVDEV)
    ecodes = pytest.importorskip("evdev").ecodes
    names = {0x00CD: "KEY_PLAYPAUSE", 0x00B5: "KEY_NEXTSONG", 0x00B6: "KEY_PREVIOUSSONG", 0x00B7: "KEY_STOPCD",
             0x00E2: "KEY_MUTE", 0x00E9: "KEY_VOLUMEUP", 0x00EA: "KEY_VOLUMEDOWN", 0x006F: "KEY_BRIGHTNESSUP",
             0x0070: "KEY_BRIGHTNESSDOWN", 0x0192: "KEY_CALC", 0x0194: "KEY_FILE", 0x018A: "KEY_MAIL",
             0x0223: "KEY_HOMEPAGE", 0x0224: "KEY_BACK", 0x0225: "KEY_FORWARD", 0x0227: "KEY_REFRESH",
             0x0221: "KEY_SEARCH"}
    assert {u: getattr(ecodes, n) for u, n in names.items()} == macroplayer.CONSUMER_EVDEV
    assert [getattr(ecodes, n) for n in ("BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA")] == \
        list(macroplayer.BUTTON_EVDEV.values())


# ------------------------------------------------------------ button spy (a pipe stands in for hidraw)

def spy_event(mask, index=9):
    return bytes([0x10, 0xFF, index, 0x00]) + mask.to_bytes(2, "big") + b"\x00"


def test_spy_parse_ignores_replies_and_other_features():
    reply = bytes([0x10, 0xFF, 9, 0x16, 0, 1, 0])           # a reply to software id 6
    other = bytes([0x11, 0xFF, 4, 0x00]) + b"\x00" * 16     # another feature's event
    data = spy_event(0x0001) + reply + other + spy_event(0x0021)
    assert spy.parse(data, 9) == ([0x0001, 0x0021], b"")
    assert spy.parse(spy_event(1)[:4], 9) == ([], spy_event(1)[:4])
    assert spy.parse(b"\x01\x02\x03", 9) == ([], b"")


def test_spy_reports_changes_from_a_pipe():
    r, w = os.pipe()
    s = spy.ButtonSpy(None, 9, fd=r)
    s.start()
    try:
        os.write(w, spy_event(0x0010))
        os.write(w, spy_event(0x0010))           # no change: no entry
        whole = spy_event(0x0011) + spy_event(0)
        os.write(w, whole[:10])                  # split across reads
        time.sleep(0.05)
        os.write(w, whole[10:])
        deadline = time.monotonic() + 2
        got = []
        while len(got) < 3 and time.monotonic() < deadline:
            got += s.changes()
            time.sleep(0.02)
        assert got == [(0, 0x10), (0x10, 0x11), (0x11, 0)]
        assert s.state == "running"
    finally:
        s.stop()
        os.close(w)
        os.close(r)


def test_spy_open_error():
    s = spy.ButtonSpy("/nonexistent/hidraw99", 9)
    s.start()
    assert s.state == "error" and "hidraw99" in s.error
    s.stop()
