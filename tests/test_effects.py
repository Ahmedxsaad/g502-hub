"""Live-effect inputs: audio analysis, screen frame plumbing and the portal handshake (with a fake portal)."""

import asyncio
import os
import shutil
import subprocess
import threading
import time

import numpy as np
import pytest

from g502hub.effects.audio import Analyzer
from g502hub.effects.screen import (FramePump, ScreenCapture, pipeline_description, request_path,
                                    rgb_from_buffer, session_path)

RATE = 44100


def tone(freq, seconds=1.0, amp=0.3):
    t = np.arange(int(RATE * seconds)) / RATE
    return amp * np.sin(2 * np.pi * freq * t)


# ---------------------------------------------------------------- audio

def test_bass_tone():
    lv = Analyzer(RATE).feed(tone(60))
    assert lv.bass > 0.9 and lv.treble < 0.05 and lv.level > 0.9
    assert lv.centroid < 0.2


def test_mid_and_treble_tones():
    mid = Analyzer(RATE).feed(tone(1000))
    assert mid.mid > 0.9 and mid.bass < 0.05 and mid.treble < 0.05
    treble = Analyzer(RATE).feed(tone(5000))
    assert treble.treble > 0.9 and treble.bass < 0.05 and treble.mid < 0.05
    assert treble.centroid > mid.centroid > 0.3


def test_int16_input_matches_float():
    a = Analyzer(RATE).feed((tone(1000) * 32767).astype(np.int16))
    b = Analyzer(RATE).feed(tone(1000))
    assert a.mid == pytest.approx(b.mid, abs=0.01)


def test_silence_and_hiss_read_zero():
    assert Analyzer(RATE).feed(np.zeros(RATE)).level == 0
    hiss = np.random.default_rng(0).normal(0, 33, RATE).astype(np.int16)  # ~-60 dBFS
    lv = Analyzer(RATE).feed(hiss)
    assert lv.level == 0 and lv.bass == 0 and lv.treble == 0


def test_quiet_music_is_auto_gained():
    lv = Analyzer(RATE).feed(0.03 * (np.sin(2 * np.pi * 80 * np.arange(RATE) / RATE)))
    assert lv.bass > 0.9


def test_not_enough_samples_gives_none():
    assert Analyzer(RATE).feed(np.zeros(500)) is None


def test_kick_train_beats():
    sig = np.random.default_rng(1).normal(0, 0.002, RATE * 4)
    starts = [k * 0.5 for k in range(8)]
    for s in starts:
        i, n = int(s * RATE), int(0.12 * RATE)
        t = np.arange(n) / RATE
        sig[i:i + n] += 0.8 * np.sin(2 * np.pi * 60 * t) * np.exp(-t * 30)
    a = Analyzer(RATE)
    beats = []
    for i in range(0, len(sig), 512):
        lv = a.feed(sig[i:i + 512])
        if lv and lv.beat:
            beats.append(i / RATE)
    # The first kick has no history to compare with; every later one is found once
    assert len(beats) == 7
    for b, s in zip(beats, starts[1:]):
        assert abs(b - s) < 0.05


def test_beat_survives_a_multi_window_feed():
    a = Analyzer(RATE)
    a.feed(np.random.default_rng(2).normal(0, 0.002, RATE))
    t = np.arange(int(0.1 * RATE)) / RATE
    kick = 0.8 * np.sin(2 * np.pi * 60 * t) * np.exp(-t * 30)
    lv = a.feed(np.concatenate([kick, np.zeros(4096)]))  # several windows in one call
    assert lv.beat


# ---------------------------------------------------------------- screen helpers

def test_request_and_session_paths():
    assert request_path(":1.42", "tok") == "/org/freedesktop/portal/desktop/request/1_42/tok"
    assert session_path(":1.7", "s") == "/org/freedesktop/portal/desktop/session/1_7/s"


def test_rgb_from_buffer_with_rowstride():
    w, h, stride = 3, 2, 12  # 9 bytes of pixels + 3 padding per row
    data = bytearray(stride * h)
    for y in range(h):
        for x in range(w):
            data[y * stride + x * 3:y * stride + x * 3 + 3] = bytes([x * 10, y * 10, 99])
        data[y * stride + 9:y * stride + 12] = b"\xee\xee\xee"
    img = rgb_from_buffer(bytes(data), w, h, stride)
    assert img.shape == (2, 3, 3) and img.dtype == np.uint8
    assert img[1, 2].tolist() == [20, 10, 99]
    assert 0xEE not in img


def _gst_available():
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        return all(Gst.ElementFactory.find(e) for e in ("videotestsrc", "videoscale", "videoconvert", "appsink"))
    except (ImportError, ValueError):
        return False


needs_gst = pytest.mark.skipif(not _gst_available(), reason="GStreamer not available")
TEST_SOURCE = "videotestsrc pattern=smpte is-live=true ! video/x-raw,width=1280,height=720"
SMPTE = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255)]


def _wait(pred, timeout=3.0):
    t0 = time.monotonic()
    while not pred() and time.monotonic() - t0 < timeout:
        time.sleep(0.02)
    return pred()


@needs_gst
@pytest.mark.parametrize("size", [(64, 36), (63, 35)])
def test_frame_pump_delivers_scaled_rgb(size):
    pump = FramePump(pipeline_description(TEST_SOURCE, size, 30))
    pump.start()
    try:
        assert _wait(lambda: pump.frame() is not None)
        f = pump.frame()
    finally:
        pump.stop()
    assert f.shape == (size[1], size[0], 3) and f.dtype == np.uint8
    w = f.shape[1]
    bars = [tuple(int(v) for v in f[2, int((i + 0.5) * w / 7)]) for i in range(7)]
    for got, want in zip(bars, SMPTE):
        assert all(abs(g - c) < 40 for g, c in zip(got, want)), (got, want)


@needs_gst
def test_frame_pump_reports_end_of_stream():
    errors = []
    pump = FramePump(pipeline_description("videotestsrc num-buffers=3 is-live=true", (16, 9), 30),
                     on_error=errors.append)
    pump.start()
    try:
        assert _wait(lambda: errors)
    finally:
        pump.stop()
    assert "ended" in errors[0]


# ---------------------------------------------------------------- portal handshake, against a fake portal

FAKE_PORTAL = '''
import asyncio, os, sys
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method, dbus_property, signal
from dbus_fast import PropertyAccess, Variant

MODE = sys.argv[1]
calls = []

class Request(ServiceInterface):
    def __init__(self):
        super().__init__("org.freedesktop.portal.Request")
    @signal()
    def Response(self) -> "ua{sv}":
        return [self.code, self.results]
    @method()
    def Close(self):
        print("REQUEST_CLOSED", flush=True)

class Session(ServiceInterface):
    def __init__(self):
        super().__init__("org.freedesktop.portal.Session")
    @method()
    def Close(self):
        print("SESSION_CLOSED", flush=True)
    @signal()
    def Closed(self) -> "a{sv}":
        return {}

class ScreenCast(ServiceInterface):
    def __init__(self, bus):
        super().__init__("org.freedesktop.portal.ScreenCast")
        self.bus = bus
    def _respond(self, sender, token, code, results, delay=0.02):
        path = f"/org/freedesktop/portal/desktop/request/{sender.lstrip(':').replace('.', '_')}/{token}"
        req = Request()
        req.code, req.results = code, results
        self.bus.export(path, req)
        if code is not None:
            asyncio.get_running_loop().call_later(delay, req.Response)
        return path
    @dbus_property(access=PropertyAccess.READ)
    def version(self) -> "u":
        return 5
    @dbus_property(access=PropertyAccess.READ)
    def AvailableCursorModes(self) -> "u":
        return 7
    @method()
    def CreateSession(self, options: "a{sv}") -> "o":
        print("CreateSession", sorted(options), flush=True)
        st = options["session_handle_token"].value
        sender = self.sender
        spath = f"/org/freedesktop/portal/desktop/session/{sender.lstrip(':').replace('.', '_')}/{st}"
        self.bus.export(spath, Session())
        return self._respond(sender, options["handle_token"].value, 0, {"session_handle": Variant("s", spath)})
    @method()
    def SelectSources(self, session: "o", options: "a{sv}") -> "o":
        print("SelectSources", {k: v.value for k, v in options.items() if k != "handle_token"}, flush=True)
        return self._respond(self.sender, options["handle_token"].value, 0, {})
    @method()
    def Start(self, session: "o", parent: "s", options: "a{sv}") -> "o":
        print("Start", flush=True)
        if MODE == "cancel":
            return self._respond(self.sender, options["handle_token"].value, 1, {})
        if MODE == "hang":
            return self._respond(self.sender, options["handle_token"].value, None, {})
        streams = [[42, {"size": Variant("(ii)", [1920, 1080]), "source_type": Variant("u", 1)}]]
        return self._respond(self.sender, options["handle_token"].value, 0,
                             {"streams": Variant("a(ua{sv})", streams), "restore_token": Variant("s", "token-2")})
    @method()
    def OpenPipeWireRemote(self, session: "o", options: "a{sv}") -> "h":
        print("OpenPipeWireRemote", flush=True)
        return os.open("/dev/null", os.O_RDONLY)

async def main():
    bus = await MessageBus(sys.argv[2], negotiate_unix_fd=True).connect()
    sc = ScreenCast(bus)
    # dbus-fast doesn't hand the caller's name to methods; track it via a message handler
    def remember(msg):
        if msg.member in ("CreateSession", "SelectSources", "Start"):
            sc.sender = msg.sender
    bus.add_message_handler(remember)
    bus.export("/org/freedesktop/portal/desktop", sc)
    await bus.request_name("org.freedesktop.portal.Desktop")
    print("READY", flush=True)
    await asyncio.get_running_loop().create_future()

asyncio.run(main())
'''


# No <servicedir>: nothing may be auto-started, or a call to the portal name would launch the real portal
BUS_CONFIG = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:dir={dir}</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""


@pytest.fixture
def private_bus(tmp_path):
    if not shutil.which("dbus-daemon"):
        pytest.skip("dbus-daemon not available")
    config = tmp_path / "bus.conf"
    config.write_text(BUS_CONFIG.format(dir=tmp_path))
    daemon = subprocess.Popen(["dbus-daemon", f"--config-file={config}", "--nofork", "--print-address=1"],
                              stdout=subprocess.PIPE, text=True)
    address = daemon.stdout.readline().strip()
    yield address
    daemon.terminate()
    daemon.wait(timeout=5)


def fake_portal(address, mode, tmp_path):
    script = tmp_path / "fake_portal.py"
    script.write_text(FAKE_PORTAL)
    proc = subprocess.Popen(["python3", str(script), mode, address], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "READY"
    lines = []
    threading.Thread(target=lambda: [lines.append(l.strip()) for l in proc.stdout], daemon=True).start()
    return proc, lines


@pytest.fixture
def capture_hooks(private_bus):
    ScreenCapture._bus_address = private_bus
    ScreenCapture._pipeline_source = TEST_SOURCE
    yield private_bus
    ScreenCapture._bus_address = None
    ScreenCapture._pipeline_source = None


@needs_gst
def test_portal_flow_success(capture_hooks, tmp_path):
    proc, log = fake_portal(capture_hooks, "ok", tmp_path)
    try:
        cap = ScreenCapture(restore_token="token-1", size=(32, 18))
        cap.start()
        assert _wait(lambda: cap.state == "running"), (cap.state, cap.error)
        assert _wait(lambda: cap.frame() is not None)
        assert cap.frame().shape == (18, 32, 3)
        assert cap.restore_token == "token-2"
        assert cap.source_size == (1920, 1080)
        select = next(l for l in log if l.startswith("SelectSources"))
        assert "'persist_mode': 2" in select and "'restore_token': 'token-1'" in select
        assert "'cursor_mode': 1" in select and "'types': 1" in select
        cap.stop()
        assert cap.state == "idle" and cap.frame() is None
        assert _wait(lambda: "SESSION_CLOSED" in log)
    finally:
        proc.terminate()


@needs_gst
def test_portal_flow_cancelled(capture_hooks, tmp_path):
    proc, log = fake_portal(capture_hooks, "cancel", tmp_path)
    try:
        cap = ScreenCapture()
        cap.start()
        assert _wait(lambda: cap.state == "cancelled"), (cap.state, cap.error)
        assert cap.frame() is None
        assert _wait(lambda: "SESSION_CLOSED" in log)
    finally:
        proc.terminate()


@needs_gst
def test_stop_while_dialog_is_open(capture_hooks, tmp_path):
    proc, log = fake_portal(capture_hooks, "hang", tmp_path)
    try:
        cap = ScreenCapture()
        cap.start()
        assert _wait(lambda: "Start" in log)
        time.sleep(0.1)
        t0 = time.monotonic()
        cap.stop()
        assert time.monotonic() - t0 < 2.5
        assert cap.state == "idle"
        assert _wait(lambda: "REQUEST_CLOSED" in log and "SESSION_CLOSED" in log), log
    finally:
        proc.terminate()


def test_no_portal_gives_error(private_bus):
    ScreenCapture._bus_address = private_bus
    try:
        cap = ScreenCapture()
        cap.start()
        assert _wait(lambda: cap.state == "error")
        assert cap.error
    finally:
        ScreenCapture._bus_address = None


def test_stop_right_after_start_never_reaches_the_portal(capture_hooks, tmp_path):
    proc, log = fake_portal(capture_hooks, "ok", tmp_path)
    try:
        for _ in range(20):
            cap = ScreenCapture()
            cap.start()
            cap.stop()
            assert cap.state == "idle"
        time.sleep(0.3)
        assert "Start" not in log or "SESSION_CLOSED" in log
    finally:
        proc.terminate()
