"""HID++ 2.0 transport over Linux hidraw.

Framing, error frames and reply matching follow docs/protocol.md §1.
"""

import glob
import os
import select
import time
from collections import deque

SHORT, LONG = 0x10, 0x11
SIZES = {SHORT: 7, LONG: 20}
CORDED = 0xFF  # device index of a corded device
SW_ID = 0x06  # unused by kernel (1), OpenRGB (7), libratbag (8), Solaar (B), G HUB (D)

ERRORS = {
    0x01: "unknown", 0x02: "invalid argument", 0x03: "out of range",
    0x04: "hardware error", 0x05: "not allowed", 0x06: "invalid feature index",
    0x07: "invalid function", 0x08: "busy", 0x09: "unsupported",
}
ERR_INVALID_ARGUMENT = 0x02
ERR_HARDWARE = 0x04
ERR_BUSY = 0x08


class HidppError(Exception):
    def __init__(self, code, feature_index, function):
        self.code = code
        name = ERRORS.get(code, "?")
        super().__init__(f"HID++ error 0x{code:02X} ({name}) on feature index "
                         f"{feature_index} function {function}")


class Event:
    """An unsolicited report from the device (software id 0)."""

    def __init__(self, feature_index, event_id, params):
        self.feature_index = feature_index
        self.event_id = event_id
        self.params = params

    def __repr__(self):
        return f"Event(idx={self.feature_index}, id={self.event_id}, {self.params.hex(' ')})"


def find_hidraw(vid, pid):
    """Return the hidraw node of the interface that carries HID++ reports."""
    want = f"{vid:08X}:{pid:08X}"
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(f"{node}/device/uevent") as f:
                if want not in f.read().upper():
                    continue
            with open(f"{node}/device/report_descriptor", "rb") as f:
                desc = f.read()
        except OSError:
            continue
        # Vendor usage page 0xFF00 with report id 0x11 = HID++ long reports
        if b"\x06\x00\xff" in desc and b"\x85\x11" in desc:
            return "/dev/" + os.path.basename(node)
    return None


class Hidpp:
    def __init__(self, path, index=CORDED):
        self.path = path
        self.index = index
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.events = deque(maxlen=256)
        self._features = {0x0000: 0}

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def fileno(self):
        return self.fd

    def _read_report(self, timeout):
        ready, _, _ = select.select([self.fd], [], [], max(timeout, 0))
        if not ready:
            return None
        try:
            return os.read(self.fd, 64)
        except BlockingIOError:
            return None

    def _queue_if_event(self, data):
        # Events carry software id 0 in the low nibble of byte 3
        if data[2] not in (0xFF, 0x8F) and data[3] & 0x0F == 0:
            self.events.append(Event(data[2], data[3] >> 4, bytes(data[4:])))

    def request(self, feature_index, function, params=b"", timeout=1.0, retries=2):
        """Send a request and return the 16 parameter bytes of the reply."""
        params = bytes(params)
        report = SHORT if len(params) <= 3 else LONG
        func_sw = (function << 4) | SW_ID
        msg = bytes([report, self.index, feature_index, func_sw]) + params
        msg = msg.ljust(SIZES[report], b"\0")

        for attempt in range(retries + 1):
            os.write(self.fd, msg)
            deadline = time.monotonic() + timeout
            try:
                while (data := self._read_report(deadline - time.monotonic())) is not None:
                    if len(data) < 5 or data[0] not in SIZES or data[1] != self.index:
                        continue
                    if data[2] in (0xFF, 0x8F) and data[3] == feature_index and data[4] == func_sw:
                        raise HidppError(data[5], feature_index, function)
                    if data[2] == feature_index and data[3] == func_sw:
                        return bytes(data[4:]).ljust(16, b"\0")
                    self._queue_if_event(data)
            except HidppError as e:
                if e.code != ERR_BUSY or attempt == retries:
                    raise
            time.sleep(0.01)
        raise TimeoutError(f"no reply for feature index {feature_index} function {function}")

    def read_events(self, timeout=0.0):
        """Return queued events, waiting up to `timeout` seconds for the first one."""
        deadline = time.monotonic() + timeout
        while not self.events:
            data = self._read_report(deadline - time.monotonic())
            if data is None:
                break
            if len(data) >= 5 and data[0] in SIZES and data[1] == self.index:
                self._queue_if_event(data)
        out = list(self.events)
        self.events.clear()
        return out

    def feature_index(self, feature_id):
        """Resolve a feature id to its index on this device, or None."""
        if feature_id not in self._features:
            reply = self.request(0, 0, feature_id.to_bytes(2, "big"))
            self._features[feature_id] = reply[0] or None
        return self._features[feature_id]

    def protocol_version(self):
        reply = self.request(0, 1, [0, 0, 0x5A])
        return reply[0], reply[1]
