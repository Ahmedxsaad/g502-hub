import ctypes
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from g502hub import lightsync_bridge as bridge
from g502hub.effects import lightsync as ls

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "bridge" / "logitechled"
PID = 4242


def approx(colors, expected):
    return all(abs(a - b) < 1e-6 for zone in expected for a, b in zip(colors[zone], expected[zone]))


def session(*packets, start=10.0):
    s = ls.Session()
    for i, p in enumerate(packets):
        s.handle(p, start + i * 0.001)
    return s


# ------------------------------------------------------------ protocol

def test_protocol_constants_match_the_dll():
    defines = dict(re.findall(r"#define LS_(\w+) (\d+)", (SOURCE / "protocol.h").read_text()))
    assert int(defines["PORT"]) == ls.PORT
    assert int(defines["VERSION"]) == ls.VERSION
    assert int(defines["NAME_MAX"]) == ls.NAME_MAX
    for name, value in defines.items():
        if name.startswith("OP_"):
            assert getattr(ls, name) == int(value), name
    assert {int(v) for k, v in defines.items() if k.startswith("OP_")} == set(ls.ARGS)


# ------------------------------------------------------------ session (SDK semantics)

def test_set_lights_both_zones():
    s = session(ls.pack(ls.OP_HELLO, PID, name=b"Uncharted"), ls.pack(ls.OP_SET, PID, 100, 50, 0))
    assert s.client == "Uncharted"
    assert approx(s.colors(10.5), {0: (1, 0.5, 0), 1: (1, 0.5, 0)})


def test_nothing_set_is_none():
    s = session(ls.pack(ls.OP_HELLO, PID, name=b"Game"))
    assert s.colors(10.5) is None
    assert ls.Session().colors(0) is None


def test_adopts_a_game_that_started_before_us():
    s = session(ls.pack(ls.OP_SET, PID, 0, 0, 100))
    assert s.pid == PID and s.client is None
    assert approx(s.colors(10.1), {0: (0, 0, 1)})


def test_percentages_are_clamped():
    s = session(ls.pack(ls.OP_SET, PID, 150, -5, 100))
    assert approx(s.colors(10.1), {0: (1, 0, 1)})


def test_flash_on_off_then_back_to_base():
    s = ls.Session()
    s.handle(ls.pack(ls.OP_SET, PID, 0, 0, 100), 9.0)
    s.handle(ls.pack(ls.OP_FLASH, PID, 100, 0, 0, 1000, 200), 10.0)
    assert approx(s.colors(10.05), {0: (1, 0, 0)})
    assert approx(s.colors(10.25), {0: (0, 0, 0)})
    assert approx(s.colors(10.45), {0: (1, 0, 0)})
    assert approx(s.colors(11.2), {0: (0, 0, 1), 1: (0, 0, 1)})


def test_infinite_flash_until_stopped():
    s = ls.Session()
    s.handle(ls.pack(ls.OP_SET, PID, 0, 100, 0), 9.0)
    s.handle(ls.pack(ls.OP_FLASH, PID, 100, 0, 0, 0, 100), 10.0)
    assert approx(s.colors(12.05), {0: (1, 0, 0)})
    s.handle(ls.pack(ls.OP_STOP, PID), 12.1)
    assert approx(s.colors(12.15), {0: (0, 1, 0)})


def test_pulse_fades_in_and_out():
    s = session(ls.pack(ls.OP_PULSE, PID, 100, 100, 100, 0, 1000))
    t0 = 10.0
    assert max(s.colors(t0)[0]) < 0.01
    assert approx(s.colors(t0 + 0.5), {0: (1, 1, 1)})
    assert abs(s.colors(t0 + 0.25)[0][0] - 0.5) < 0.01


def test_save_and_restore():
    s = ls.Session()
    s.handle(ls.pack(ls.OP_SET, PID, 0, 0, 100), 10.0)
    s.handle(ls.pack(ls.OP_SAVE, PID), 10.1)
    s.handle(ls.pack(ls.OP_SET, PID, 100, 0, 0), 10.2)
    assert approx(s.colors(10.3), {0: (1, 0, 0)})
    s.handle(ls.pack(ls.OP_RESTORE, PID), 10.4)
    assert approx(s.colors(10.5), {0: (0, 0, 1)})


def test_mouse_zones_and_set_clears_them():
    s = ls.Session()
    s.handle(ls.pack(ls.OP_SET, PID, 0, 0, 100), 10.0)
    s.handle(ls.pack(ls.OP_ZONE, PID, ls.DEVICE_MOUSE, 1, 100, 0, 0), 10.1)
    s.handle(ls.pack(ls.OP_ZONE, PID, ls.DEVICE_MOUSE, 7, 0, 100, 0), 10.1)  # no such zone
    assert approx(s.colors(10.2), {0: (0, 0, 1), 1: (1, 0, 0)})
    s.handle(ls.pack(ls.OP_SET, PID, 0, 100, 0), 10.3)
    assert approx(s.colors(10.4), {0: (0, 1, 0), 1: (0, 1, 0)})


def test_keyboard_only_games_fall_back_to_ambient():
    s = ls.Session()
    s.handle(ls.pack(ls.OP_TARGET, PID, 1 << 2), 10.0)  # per-key RGB only
    s.handle(ls.pack(ls.OP_SET, PID, 0, 100, 0), 10.1)
    assert approx(s.colors(10.2), {0: (0, 1, 0)})
    s.handle(ls.pack(ls.OP_AMBIENT, PID, 100, 0, 100), 10.3)
    assert approx(s.colors(10.4), {0: (1, 0, 1)})
    # Once the game lights RGB devices, that's what the mouse shows
    s.handle(ls.pack(ls.OP_TARGET, PID, ls.TARGET_ALL), 10.5)
    s.handle(ls.pack(ls.OP_SET, PID, 100, 0, 0), 10.6)
    s.handle(ls.pack(ls.OP_AMBIENT, PID, 0, 0, 100), 10.7)
    assert approx(s.colors(10.8), {0: (1, 0, 0)})


def test_other_devices_zones_are_fallback():
    s = session(ls.pack(ls.OP_ZONE, PID, 0, 2, 0, 100, 100))  # a keyboard zone
    assert approx(s.colors(10.1), {0: (0, 1, 1)})


def test_times_out_without_pings_and_pings_keep_it():
    s = ls.Session()
    s.handle(ls.pack(ls.OP_SET, PID, 100, 0, 0), 10.0)
    assert s.colors(12.9) is not None
    assert s.colors(13.5) is None
    s.handle(ls.pack(ls.OP_PING, PID), 13.6)
    assert approx(s.colors(16.0), {0: (1, 0, 0)})


def test_shutdown_hands_back():
    s = session(ls.pack(ls.OP_SET, PID, 100, 0, 0), ls.pack(ls.OP_SHUTDOWN, PID))
    assert s.colors(10.1) is None


def test_latest_hello_takes_over_and_others_are_ignored():
    s = ls.Session()
    s.handle(ls.pack(ls.OP_HELLO, PID, name=b"First"), 10.0)
    s.handle(ls.pack(ls.OP_SET, PID, 100, 0, 0), 10.1)
    s.handle(ls.pack(ls.OP_SET, 777, 0, 100, 0), 10.2)  # not initialised: ignored
    assert approx(s.colors(10.3), {0: (1, 0, 0)})
    s.handle(ls.pack(ls.OP_HELLO, 777, name=b"Second"), 10.4)
    s.handle(ls.pack(ls.OP_SET, 777, 0, 0, 100), 10.5)
    s.handle(ls.pack(ls.OP_SET, PID, 100, 100, 100), 10.6)
    assert s.client == "Second"
    assert approx(s.colors(10.7), {0: (0, 0, 1)})


def test_garbage_is_ignored():
    s = ls.Session()
    for data in (b"", b"LS", b"XX\x01\x04" + bytes(8), ls.pack(ls.OP_SET, PID, 1)[:12],
                 b"LS\x02\x04" + bytes(16), b"LS\x01\x63" + bytes(16)):
        s.handle(data, 10.0)
    assert s.pid is None and s.colors(10.0) is None


# ------------------------------------------------------------ receiver over real UDP

def _send(port, *packets):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for p in packets:
            sock.sendto(p, ("127.0.0.1", port))


def _wait(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_receiver_over_udp():
    rx = ls.LightsyncReceiver(port=0)
    rx.start()
    try:
        assert rx.state == "running" and rx.port
        assert rx.colors() is None
        _send(rx.port, ls.pack(ls.OP_HELLO, PID, name=b"The Last of Us\xe2\x84\xa2"),
              ls.pack(ls.OP_SET, PID, 0, 100, 0))
        assert _wait(lambda: rx.colors() is not None)
        assert rx.client == "The Last of Us™"
        assert approx(rx.colors(), {0: (0, 1, 0), 1: (0, 1, 0)})
        _send(rx.port, ls.pack(ls.OP_SHUTDOWN, PID))
        assert _wait(lambda: rx.colors() is None)
    finally:
        rx.stop()
    assert rx.state == "idle" and rx.colors() is None and rx.client is None


def test_receiver_port_in_use():
    first = ls.LightsyncReceiver(port=0)
    first.start()
    try:
        second = ls.LightsyncReceiver(port=first.port)
        second.start()
        assert second.state == "error" and "in use" in second.error
    finally:
        first.stop()


# ------------------------------------------------------------ the DLL's C code, built natively

STUBS = r"""
#include <string.h>
static unsigned char packets[64][128];
static int sizes[64], count;
unsigned int GetCurrentProcessId(void) { return 4242; }
void Sleep(unsigned int ms) { (void)ms; }
void *CreateThread(void *a, unsigned long s, void *f, void *p, unsigned int fl, unsigned int *id)
{ (void)a; (void)s; (void)f; (void)p; (void)fl; (void)id; return 0; }
int CloseHandle(void *h) { (void)h; return 1; }
int GetModuleHandleExW(unsigned int f, const void *n, void **m) { (void)f; (void)n; *m = 0; return 1; }
void FreeLibraryAndExitThread(void *m, unsigned int c) { (void)m; (void)c; for (;;) {} }
int WSAStartup(unsigned short v, void *d) { (void)v; (void)d; return 0; }
unsigned long socket(int a, int t, int p) { (void)a; (void)t; (void)p; return 3; }
int sendto(unsigned long s, const char *buf, int len, int flags, const void *to, int tolen)
{
    const unsigned char *addr = to;
    (void)s; (void)flags;
    if (tolen != 16 || addr[0] != 2 || addr[2] != 0xa2 || addr[3] != 0x1f || addr[4] != 127) return -1;
    if (count < 64 && len <= 128) { memcpy(packets[count], buf, len); sizes[count++] = len; }
    return len;
}
int take(unsigned char *out) {
    int n;
    if (!count) return 0;
    n = sizes[0];
    memcpy(out, packets[0], n);
    memmove(packets, packets + 1, sizeof packets[0] * (size_t)(--count));
    memmove(sizes, sizes + 1, sizeof sizes[0] * (size_t)count);
    return n;
}
"""


@pytest.fixture(scope="module")
def dll(tmp_path_factory):
    cc = shutil.which("clang") or shutil.which("cc")
    if cc is None:
        pytest.skip("no C compiler")
    work = tmp_path_factory.mktemp("logitechled")
    (work / "stubs.c").write_text(STUBS)
    lib = work / "liblogitechled.so"
    # -Bsymbolic: the DLL code must call these stubs, not libc's real socket()/sendto()
    subprocess.run([cc, "-shared", "-fPIC", "-O1", "-w", "-fno-builtin", "-Wl,-Bsymbolic",
                    str(SOURCE / "logitechled.c"), str(work / "stubs.c"), "-o", str(lib)], check=True)
    return ctypes.CDLL(str(lib))


def _calls(dll):
    out = []
    buf = ctypes.create_string_buffer(128)
    while n := dll.take(buf):
        out.append(buf.raw[:n])
    return out


def _call(dll, name, *args):
    fn = getattr(dll, name)
    fn.restype = ctypes.c_bool
    assert fn(*args) is True
    return _calls(dll)


def test_dll_sends_what_the_receiver_expects(dll):
    assert _call(dll, "LogiLedInitWithName", b"Uncharted") == [ls.pack(ls.OP_HELLO, PID, name=b"Uncharted")]
    assert _call(dll, "LogiLedInit") == [ls.pack(ls.OP_HELLO, PID)]
    assert _call(dll, "LogiLedSetTargetDevice", 6) == [ls.pack(ls.OP_TARGET, PID, 6)]
    assert _call(dll, "LogiLedSetLighting", 100, 50, 0) == [ls.pack(ls.OP_SET, PID, 100, 50, 0)]
    assert _call(dll, "LogiLedFlashLighting", 1, 2, 3, 4000, 250) == [ls.pack(ls.OP_FLASH, PID, 1, 2, 3, 4000, 250)]
    assert _call(dll, "LogiLedPulseLighting", 4, 5, 6, 0, 800) == [ls.pack(ls.OP_PULSE, PID, 4, 5, 6, 0, 800)]
    assert _call(dll, "LogiLedStopEffects") == [ls.pack(ls.OP_STOP, PID)]
    assert _call(dll, "LogiLedSaveCurrentLighting") == [ls.pack(ls.OP_SAVE, PID)]
    assert _call(dll, "LogiLedRestoreLighting") == [ls.pack(ls.OP_RESTORE, PID)]
    assert _call(dll, "LogiLedSetLightingForTargetZone", 3, 1, 9, 8, 7) == \
        [ls.pack(ls.OP_ZONE, PID, 3, 1, 9, 8, 7)]
    dll.LogiLedShutdown()
    assert _calls(dll) == [ls.pack(ls.OP_SHUTDOWN, PID)]


def test_dll_name_is_capped(dll):
    [packet] = _call(dll, "LogiLedInitWithName", b"x" * 200)
    assert packet == ls.pack(ls.OP_HELLO, PID, name=b"x" * ls.NAME_MAX)


def test_dll_bitmap_is_averaged(dll):
    keys = 21 * 6
    bitmap = bytearray(keys * 4)
    for i in range(keys // 2):  # half the keys red (BGRA), the rest off
        bitmap[4 * i:4 * i + 4] = bytes([0, 0, 255, 255])
    assert _call(dll, "LogiLedSetLightingFromBitmap", bytes(bitmap)) == [ls.pack(ls.OP_AMBIENT, PID, 100, 0, 0)]
    for i in range(keys // 2, keys):  # the other half green: an even mix
        bitmap[4 * i:4 * i + 4] = bytes([0, 255, 0, 255])
    assert _call(dll, "LogiLedSetLightingFromBitmap", bytes(bitmap)) == [ls.pack(ls.OP_AMBIENT, PID, 50, 50, 0)]
    assert _call(dll, "LogiLedSetLightingFromBitmap", bytes(keys * 4)) == [ls.pack(ls.OP_AMBIENT, PID, 0, 0, 0)]


def test_dll_per_key_and_config_calls_are_accepted_quietly(dll):
    for name, args in (("LogiLedSetLightingForKeyWithKeyName", (0x1E, 1, 2, 3)),
                       ("LogiLedSetLightingForKeyWithScanCode", (0x1E, 1, 2, 3)),
                       ("LogiLedSaveLightingForKey", (0x1E,)), ("LogiLedRestoreLightingForKey", (0x1E,)),
                       ("LogiLedStopEffectsOnKey", (0x1E,)), ("LogiLedFlashSingleKey", (0x1E, 1, 2, 3, 4, 5))):
        assert _call(dll, name, *args) == []
    value = ctypes.c_double(20.0)
    assert _call(dll, "LogiLedGetConfigOptionNumber", ctypes.c_wchar_p("health/low"), ctypes.byref(value)) == []
    assert value.value == 20.0  # the game's default stays
    old = ctypes.c_double(5.0)
    assert _call(dll, "LogiGetConfigOptionNumber", ctypes.c_wchar_p("x"), ctypes.byref(old), 1) == []
    major, minor, build = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    _call(dll, "LogiLedGetSdkVersion", ctypes.byref(major), ctypes.byref(minor), ctypes.byref(build))
    assert major.value == 9


def test_dll_exports_every_function_in_the_def_file(dll):
    names = re.findall(r"^\s+(Logi\w+)", (SOURCE / "LogitechLed.def").read_text(), re.M)
    assert len(names) == 37
    for name in names:
        assert hasattr(dll, name), name


# ------------------------------------------------------------ prefix installer

REG = """WINE REGISTRY Version 2
;; All keys relative to REGISTRY\\\\Machine

#arch={arch}

[Software\\\\Classes\\\\*\\\\shellex\\\\ContextMenuHandlers] 1769531289
#time=1dc8fa9ec6ae52e

[Software\\\\Classes\\\\CLSID\\\\{{0000002F-0000-0000-C000-000000000046}}\\\\InprocServer32] 1769531287
#time=1dc8fa9eb414616
@="C:\\\\windows\\\\system32\\\\oleaut32.dll"
"ThreadingModel"="Both"

[System\\\\Select] 1769531290
#time=1dc8fa9ec700da6
"Current"=dword:00000001
"Default"=dword:00000001
"""


@pytest.fixture
def prefix(tmp_path, monkeypatch):
    bins = tmp_path / "bin"
    for arch in ("x64", "x86"):
        (bins / arch).mkdir(parents=True)
        (bins / arch / "LogitechLed.dll").write_bytes(b"MZ" + arch.encode())
    monkeypatch.setattr(bridge, "BIN_DIR", bins)
    monkeypatch.setattr(bridge, "prefix_in_use", lambda pfx: False)

    def make(arch="win64", extra=""):
        pfx = tmp_path / f"pfx-{arch}"
        (pfx / "drive_c").mkdir(parents=True)
        (pfx / "system.reg").write_bytes((REG.format(arch=arch) + extra).encode("latin-1"))
        return pfx
    return make


def test_install_uninstall_round_trip(prefix):
    pfx = prefix()
    original = (pfx / "system.reg").read_bytes()
    assert not bridge.is_installed(pfx)
    bridge.install(pfx)
    assert bridge.is_installed(pfx)
    text = (pfx / "system.reg").read_text()
    assert "[Software\\\\Classes\\\\CLSID\\\\{a6519e67-7632-4375-afdf-caa889744403}\\\\ServerBinary]" in text
    assert "[Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{a6519e67-7632-4375-afdf-caa889744403}\\\\ServerBinary]" in text
    assert '@="C:\\\\Program Files\\\\G502 Hub\\\\LogitechLed.dll"' in text
    assert '@="C:\\\\Program Files (x86)\\\\G502 Hub\\\\LogitechLed.dll"' in text
    assert text.startswith(original.decode())  # appended, the rest untouched
    assert (pfx / "drive_c/Program Files/G502 Hub/LogitechLed.dll").read_bytes() == b"MZx64"
    assert (pfx / "drive_c/Program Files (x86)/G502 Hub/LogitechLed.dll").read_bytes() == b"MZx86"
    assert (pfx / "system.reg.g502hub.bak").read_bytes() == original

    bridge.install(pfx)  # again: nothing changes
    assert (pfx / "system.reg").read_text() == text

    assert bridge.uninstall(pfx) is True
    assert (pfx / "system.reg").read_bytes() == original
    assert not (pfx / "drive_c/Program Files").exists()
    assert not (pfx / "drive_c/Program Files (x86)").exists()
    assert not (pfx / "system.reg.g502hub.bak").exists()
    assert not bridge.is_installed(pfx)
    assert bridge.uninstall(pfx) is False


def test_win32_prefix_gets_only_the_32_bit_dll(prefix):
    pfx = prefix("win32")
    original = (pfx / "system.reg").read_bytes()
    bridge.install(pfx)
    text = (pfx / "system.reg").read_text()
    assert "Wow6432Node" not in text
    assert (pfx / "drive_c/Program Files/G502 Hub/LogitechLed.dll").read_bytes() == b"MZx86"
    assert bridge.is_installed(pfx)
    bridge.uninstall(pfx)
    assert (pfx / "system.reg").read_bytes() == original


def test_someone_elses_server_binary_is_restored(prefix):
    theirs = ("\n[Software\\\\Classes\\\\CLSID\\\\{a6519e67-7632-4375-afdf-caa889744403}\\\\ServerBinary] 1769531000\n"
              "#time=1dc8fa9e0000000\n@=\"C:\\\\Program Files\\\\LGHUB\\\\sdk_legacy_led_x64.dll\"\n")
    pfx = prefix(extra=theirs)
    original = (pfx / "system.reg").read_bytes()
    bridge.install(pfx)
    assert "LGHUB" not in (pfx / "system.reg").read_text()
    assert bridge.is_installed(pfx)
    bridge.uninstall(pfx)
    assert (pfx / "system.reg").read_bytes() == original


def test_uninstall_after_wine_rewrote_the_file(prefix):
    pfx = prefix()
    bridge.install(pfx)
    text = (pfx / "system.reg").read_text()
    # Wine saves keys sorted, with its own timestamps: move our sections up front
    preamble, blocks = bridge._blocks(text)
    ours = [b for b in blocks if "a6519e67" in b]
    others = [b for b in blocks if "a6519e67" not in b]
    rewritten = preamble + "".join(b.rstrip("\n") + "\n\n" for b in ours + others).rstrip("\n") + "\n"
    (pfx / "system.reg").write_text(rewritten)
    assert bridge.is_installed(pfx)
    bridge.uninstall(pfx)
    after = (pfx / "system.reg").read_text()
    assert "a6519e67" not in after and "oleaut32" in after and '"Default"=dword:00000001' in after
    assert after.endswith('"Default"=dword:00000001\n')


def test_install_refuses_while_running(prefix, monkeypatch):
    pfx = prefix()
    monkeypatch.setattr(bridge, "prefix_in_use", lambda p: True)
    original = (pfx / "system.reg").read_bytes()
    with pytest.raises(bridge.PrefixInUse):
        bridge.install(pfx)
    assert (pfx / "system.reg").read_bytes() == original


def test_install_needs_the_built_dlls(prefix, tmp_path, monkeypatch):
    pfx = prefix()
    monkeypatch.setattr(bridge, "BIN_DIR", tmp_path / "missing")
    with pytest.raises(FileNotFoundError, match="build.sh"):
        bridge.install(pfx)
    assert not (pfx / "drive_c/Program Files").exists()


def test_prefix_in_use_sees_wine_processes(tmp_path):
    pfx = tmp_path / "pfx"
    pfx.mkdir()
    assert bridge.prefix_in_use(pfx) is False
    proc = subprocess.Popen(["sleep", "10"], env={**os.environ, "WINEPREFIX": str(pfx)})
    try:
        assert _wait(lambda: bridge.prefix_in_use(pfx))
    finally:
        proc.kill()
        proc.wait()
    compat = tmp_path / "compatdata" / "123"
    (compat / "pfx").mkdir(parents=True)
    proc = subprocess.Popen(["sleep", "10"], env={**os.environ, "STEAM_COMPAT_DATA_PATH": str(compat)})
    try:
        assert _wait(lambda: bridge.prefix_in_use(compat / "pfx"))
    finally:
        proc.kill()
        proc.wait()


def test_steam_prefixes(tmp_path):
    root = tmp_path / "Steam"
    other = tmp_path / "Games" / "SteamLibrary"
    for lib in (root, other):
        (lib / "steamapps" / "compatdata").mkdir(parents=True)
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{root}"\n\t}}\n'
        f'\t"1"\n\t{{\n\t\t"path"\t\t"{other}"\n\t}}\n}}\n')
    (other / "steamapps" / "appmanifest_1659420.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"1659420"\n\t"name"\t\t"UNCHARTED: Legacy of Thieves Collection"\n}\n')
    (root / "steamapps" / "appmanifest_291550.acf").write_text('"AppState"\n{\n\t"name"\t\t"Brawlhalla"\n}\n')
    (root / "steamapps" / "appmanifest_1493710.acf").write_text('"AppState"\n{\n\t"name"\t\t"Proton Experimental"\n}\n')
    for lib, appid in ((other, "1659420"), (root, "291550"), (root, "3100000000"), (root, "1493710")):
        pfx = lib / "steamapps" / "compatdata" / appid / "pfx"
        pfx.mkdir(parents=True)
        (pfx / "system.reg").write_text("WINE REGISTRY Version 2\n")
    (root / "steamapps" / "compatdata" / "0").mkdir()  # no prefix: skipped
    found = bridge.steam_prefixes(roots=[root, root])  # the same root twice is listed once
    assert [(appid, name) for appid, name, _ in found] == [
        (291550, "Brawlhalla"), (3100000000, "Non-Steam game 3100000000"),
        (1659420, "UNCHARTED: Legacy of Thieves Collection")]
    assert found[2][2] == other / "steamapps" / "compatdata" / "1659420" / "pfx"
