"""Listens for Mouse Button Spy (HID++ 0x8110) events on a hidraw node of its own."""

import os
import select
import threading
from collections import deque

SIZES = {0x10: 7, 0x11: 20}  # HID++ short and long reports


def parse(data, feature_index, device_index=0xFF):
    """(button masks, leftover bytes) from HID++ reports.

    hidraw returns one report per read; a pipe may join or split them, so a
    partial report comes back as leftover for the next read.
    """
    masks = []
    while data:
        size = SIZES.get(data[0])
        if size is None:
            return masks, b""  # another collection's report on this interface
        if len(data) < size:
            return masks, data
        frame, data = data[:size], data[size:]
        # Event 0 from the spy feature, software id 0 (a notification, not a reply)
        if frame[1] == device_index and frame[2] == feature_index and frame[3] == 0x00:
            masks.append(int.from_bytes(frame[4:6], "big"))
    return masks, b""


class ButtonSpy:
    """Reads Mouse Button Spy (HID++ 0x8110) events on its own hidraw file descriptor.

    hidraw gives every open fd a copy of each input report, so this never takes
    replies away from the app's own requests. The app starts/stops the spy itself
    (device.G502.spy_start/spy_stop); this only listens.
    """

    def __init__(self, path, feature_index, device_index=0xFF, fd=None):
        self.path, self.feature_index, self.device_index = path, feature_index, device_index
        self.state = "idle"
        self.error = None
        self._fd, self._own_fd = fd, fd is None
        self._mask = 0
        self._changes = deque(maxlen=256)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        try:
            if self._fd is None:
                self._fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            self.state, self.error = "error", f"can't open {self.path}: {e}"
            return
        self._stop.clear()
        self.state = "running"
        self._thread = threading.Thread(target=self._read, daemon=True, name="button spy")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(1.0)
            self._thread = None
        if self._own_fd and self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self.state == "running":
            self.state = "idle"

    def changes(self):
        """(old_mask, new_mask) for every change since the last call."""
        with self._lock:
            out = list(self._changes)
            self._changes.clear()
        return out

    def _read(self):
        rest = b""
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._fd], [], [], 0.1)
                if not ready:
                    continue
                data = os.read(self._fd, 64)
            except BlockingIOError:
                continue
            except OSError as e:  # unplugged
                self.state, self.error = "error", str(e)
                return
            if not data:
                self.state, self.error = "error", "the device went away"
                return
            masks, rest = parse(rest + data, self.feature_index, self.device_index)
            for mask in masks:
                if mask != self._mask:
                    with self._lock:
                        self._changes.append((self._mask, mask))
                    self._mask = mask
