"""Game-driven lighting from Windows games under Wine/Proton.

Games that support Logitech LIGHTSYNC call Logitech's LED SDK (LogitechLed.dll,
normally provided by G HUB). bridge/logitechled is a stand-in DLL that sends
each call here as a UDP datagram; this module plays them back as mouse colors
the way the SDK would (static colors, flash, pulse, save/restore).

Routing, as in the SDK: calls made while the game targets RGB devices (the
default) light the mouse. Calls aimed only at keyboards (per-key target,
per-key bitmaps, other devices' zones) are kept as a fallback, so a game that
only ever lights keyboards still lights the mouse.

Zones: SDK mouse zone 0 -> the DPI lights, zone 1 -> the logo, the order the
mouse itself reports them in (G HUB's numbering for the G502 is unverified).
"""

import errno
import socket
import struct
import threading
import time
from math import cos, pi

# Mirrors bridge/logitechled/protocol.h (a test checks they match)
PORT = 41503
VERSION = 1
NAME_MAX = 64
OP_HELLO, OP_SHUTDOWN, OP_TARGET, OP_SET, OP_FLASH, OP_PULSE = 1, 2, 3, 4, 5, 6
OP_STOP, OP_SAVE, OP_RESTORE, OP_ZONE, OP_AMBIENT, OP_PING = 7, 8, 9, 10, 11, 12
ARGS = {OP_HELLO: 0, OP_SHUTDOWN: 0, OP_TARGET: 1, OP_SET: 3, OP_FLASH: 5, OP_PULSE: 5,
        OP_STOP: 0, OP_SAVE: 0, OP_RESTORE: 0, OP_ZONE: 5, OP_AMBIENT: 3, OP_PING: 0}
HEADER = struct.Struct("<2sBBI")  # magic, version, op, process id

# SDK constants
TARGET_RGB = 1 << 1
TARGET_ALL = 0b111
DEVICE_MOUSE = 3
MOUSE_ZONES = (0, 1)

TIMEOUT = 3.0  # seconds without any datagram (the DLL pings every second) before giving up on a game
MIN_INTERVAL = 0.02  # seconds; guards against interval 0

OFF = (0.0, 0.0, 0.0)


def pack(op, pid, *args, name=b""):
    """A datagram as the DLL sends it."""
    return HEADER.pack(b"LS", VERSION, op, pid & 0xFFFFFFFF) + struct.pack(f"<{len(args)}i", *args) + name


def _rgb(r, g, b):
    return tuple(min(max(c, 0), 100) / 100 for c in (r, g, b))


class _Channel:
    """The lighting one class of device would show: a base color, zone overrides, one effect."""

    def __init__(self):
        self.touched = False
        self.base = OFF
        self.zones = {}
        self.saved = None
        self.effect = None  # (kind, rgb, start, end or None, interval)

    def set(self, rgb):
        self.touched = True
        self.base, self.zones = rgb, {}

    def start_effect(self, kind, rgb, now, duration_ms, interval_ms):
        self.touched = True
        end = now + duration_ms / 1000 if duration_ms > 0 else None
        self.effect = (kind, rgb, now, end, max(interval_ms / 1000, MIN_INTERVAL))

    def color(self, zone, t):
        if self.effect is not None:
            kind, rgb, start, end, interval = self.effect
            if end is None or t < end:
                phase = (t - start) / interval
                if kind == OP_FLASH:  # on for one interval, off for the next
                    return rgb if int(phase) % 2 == 0 else OFF
                level = (1 - cos(2 * pi * phase)) / 2  # pulse: fade in and out once per interval
                return tuple(c * level for c in rgb)
        return self.zones.get(zone, self.base)


class Session:
    """The SDK state of the game currently driving the lights, fed with datagrams."""

    def __init__(self):
        self.pid = None
        self.client = None
        self.closed = False
        self.last = None
        self._reset()

    def _reset(self):
        self.target = TARGET_ALL
        self.mouse = _Channel()
        self.fallback = _Channel()

    def handle(self, data, now):
        """Apply one datagram received at `now`. Malformed or foreign datagrams are ignored."""
        if len(data) < HEADER.size:
            return
        magic, version, op, pid = HEADER.unpack_from(data)
        if magic != b"LS" or version != VERSION or op not in ARGS:
            return
        count = ARGS[op]
        if len(data) < HEADER.size + 4 * count:
            return
        args = struct.unpack_from(f"<{count}i", data, HEADER.size)
        if op == OP_HELLO:
            # The SDK hands control to whichever program initialised last
            self.pid, self.closed, self.last = pid, False, now
            self.client = data[HEADER.size:HEADER.size + NAME_MAX].decode("utf-8", "replace") or None
            self._reset()
            return
        if self.pid is None or (self.closed and op != OP_SHUTDOWN):
            # A game that initialised before we were listening
            self.pid, self.client, self.closed = pid, None, False
            self._reset()
        if pid != self.pid:
            return
        self.last = now
        if op == OP_SHUTDOWN:
            self.closed = True
            return
        channel = self.mouse if self.target & TARGET_RGB else self.fallback
        if op == OP_TARGET:
            self.target = args[0]
        elif op == OP_SET:
            channel.set(_rgb(*args))
        elif op in (OP_FLASH, OP_PULSE):
            channel.start_effect(op, _rgb(*args[:3]), now, args[3], args[4])
        elif op == OP_STOP:
            channel.effect = None
        elif op == OP_SAVE:
            channel.saved = (channel.base, dict(channel.zones))
        elif op == OP_RESTORE and channel.saved is not None:
            channel.base, channel.zones = channel.saved[0], dict(channel.saved[1])
            channel.effect = None
        elif op == OP_ZONE:
            device, zone, rgb = args[0], args[1], _rgb(*args[2:])
            if device == DEVICE_MOUSE:
                if zone in MOUSE_ZONES:
                    self.mouse.touched = True
                    self.mouse.zones[zone] = rgb
            else:
                self.fallback.set(rgb)
        elif op == OP_AMBIENT:
            self.fallback.set(_rgb(*args))

    def colors(self, t):
        """{zone: (r, g, b)} in 0..1 at time t, or None when no game is driving the lights."""
        if self.pid is None or self.closed or self.last is None or t - self.last > TIMEOUT:
            return None
        channel = self.mouse if self.mouse.touched else self.fallback if self.fallback.touched else None
        if channel is None:
            return None
        return {zone: channel.color(zone, t) for zone in MOUSE_ZONES}


class LightsyncReceiver:
    """Listens on 127.0.0.1 for the bridge DLL. Safe to poll from any thread.

    `colors(t)` takes t from the same clock (time.monotonic by default).
    """

    def __init__(self, port=PORT, clock=time.monotonic):
        self.port, self.clock = port, clock
        self.state = "idle"
        self.error = None
        self._lock = threading.Lock()
        self._session = Session()
        self._sock = None
        self._thread = None
        self._stopping = False

    @property
    def client(self):
        with self._lock:
            return self._session.client if self._session.pid is not None else None

    def start(self):
        with self._lock:
            if self.state == "running":
                return
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("127.0.0.1", self.port))
                sock.settimeout(0.2)
            except OSError as e:
                self.state = "error"
                self.error = (f"Port {self.port} is already in use (is G502 Hub running twice?)"
                              if e.errno == errno.EADDRINUSE else f"Could not listen for games: {e}")
                return
            self._sock, self.port = sock, sock.getsockname()[1]
            self._session = Session()
            self._stopping = False
            self.state, self.error = "running", None
            self._thread = threading.Thread(target=self._read, args=(sock,), daemon=True,
                                            name="g502hub-lightsync")
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stopping = True
            sock, thread = self._sock, self._thread
            self._sock = self._thread = None
            if self.state == "running":
                self.state = "idle"
            self._session = Session()
        if thread is not None:
            thread.join(timeout=1)
        if sock is not None:
            sock.close()

    def colors(self, t=None):
        with self._lock:
            return self._session.colors(self.clock() if t is None else t)

    def _read(self, sock):
        while not self._stopping:
            try:
                data, _ = sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError as e:
                with self._lock:
                    if not self._stopping:
                        self.state, self.error = "error", f"Stopped listening for games: {e}"
                return
            with self._lock:
                self._session.handle(data, self.clock())
