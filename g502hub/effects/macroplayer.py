"""Plays expanded macros (macros.expand) through a virtual input device.

The device is python-evdev's UInput on /dev/uinput, created on the first play.
Each playing macro has its own thread; stopping one releases whatever it holds.
"""

import threading
import time

from .. import keys

EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
REL_X, REL_Y, REL_HWHEEL, REL_WHEEL = 0x00, 0x01, 0x06, 0x08
# Mouse button bits (onboard.MOUSE_BUTTON_NAMES order) -> BTN_LEFT, RIGHT, MIDDLE, SIDE, EXTRA
BUTTON_EVDEV = {0x01: 0x110, 0x02: 0x111, 0x04: 0x112, 0x08: 0x113, 0x10: 0x114}
# Consumer usages (keys.CONSUMER) -> evdev key codes, as Linux's hid-input maps them
CONSUMER_EVDEV = {
    0x00CD: 164, 0x00B5: 163, 0x00B6: 165, 0x00B7: 166,   # play-pause, next, previous, stop
    0x00E2: 113, 0x00E9: 115, 0x00EA: 114,                 # mute, volume up, volume down
    0x006F: 225, 0x0070: 224,                              # brightness up, down
    0x0192: 140, 0x0194: 144, 0x018A: 155,                 # calculator, file browser, mail
    0x0223: 172, 0x0224: 158, 0x0225: 159, 0x0227: 173, 0x0221: 217,  # browser home/back/forward/refresh/search
}
PACE_S = 0.004       # after each press or release, so apps see every one
LOOP_FLOOR_S = 0.01  # a repeating macro takes at least this long per round
SLICE_S = 0.02


def device_keys():
    """Every key code the virtual device can press."""
    return sorted(set(keys.HID_TO_EVDEV.values()) | set(keys.MODIFIER_EVDEV.values()) |
                  set(CONSUMER_EVDEV.values()) | set(BUTTON_EVDEV.values()))


class _UInputBackend:
    def __init__(self):
        from evdev import UInput
        self.ui = UInput({EV_KEY: device_keys(), EV_REL: [REL_X, REL_Y, REL_HWHEEL, REL_WHEEL]},
                         name="G502 Hub macros")

    def write(self, type_, code, value):
        self.ui.write(type_, code, value)

    def syn(self):
        self.ui.syn()

    def close(self):
        self.ui.close()


class _Run(threading.Thread):
    def __init__(self, player, key, events, mode):
        super().__init__(daemon=True, name=f"macro {key!r}")
        self.player, self.key, self.events, self.mode = player, key, events, mode
        self.cancel = threading.Event()
        self.held = {}  # evdev key code -> presses not yet released by this macro

    def run(self):
        try:
            while not self.cancel.is_set():
                started = time.monotonic()
                for ev in self.events:
                    if self.cancel.is_set():
                        break
                    self._play(ev)
                if self.mode == "once":
                    break
                rest = LOOP_FLOOR_S - (time.monotonic() - started)
                if rest > 0:
                    self.cancel.wait(rest)
        except Exception as e:  # a closed device, an odd event
            self.player.error = str(e)
        finally:
            self._release_all()
            self.player._finished(self)

    def _key(self, code, down):
        count = self.held.get(code, 0)
        if down:
            self.held[code] = count + 1
            if count == 0:
                self.player._write([(EV_KEY, code, 1)])
        elif count:
            self.held[code] = count - 1
            if count == 1:
                del self.held[code]
                self.player._write([(EV_KEY, code, 0)])

    def _play(self, ev):
        kind = ev[0]
        if kind == "delay":
            self.cancel.wait(ev[1] / 1000)
            return
        if kind == "key":
            _, mods, usage, down = ev
            mod_codes = [code for bit, code in keys.MODIFIER_EVDEV.items() if mods & bit]
            code = keys.HID_TO_EVDEV.get(usage) if usage else None
            if down:
                for c in mod_codes:
                    self._key(c, True)
                if code is not None:
                    self._key(code, True)
            else:
                if code is not None:
                    self._key(code, False)
                for c in reversed(mod_codes):
                    self._key(c, False)
        elif kind == "button":
            for bit, code in BUTTON_EVDEV.items():
                if ev[1] & bit:
                    self._key(code, ev[2])
        elif kind == "consumer":
            code = CONSUMER_EVDEV.get(ev[1])
            if code is not None:
                self._key(code, ev[2])
        elif kind == "wheel":
            self.player._write([(EV_REL, REL_WHEEL, ev[1])])
        elif kind == "hwheel":
            self.player._write([(EV_REL, REL_HWHEEL, ev[1])])
        elif kind == "move":
            self.player._write([(EV_REL, REL_X, ev[1]), (EV_REL, REL_Y, ev[2])])
            return
        time.sleep(PACE_S)

    def _release_all(self):
        held, self.held = self.held, {}
        if held:
            try:
                self.player._write([(EV_KEY, code, 0) for code in reversed(list(held))])
            except Exception as e:
                self.player.error = str(e)


class MacroPlayer:
    """Plays expanded macros through a virtual input device (python-evdev UInput on /dev/uinput)."""

    def __init__(self, backend=None):
        self._backend = backend
        self.state = "ready" if backend is not None else "idle"
        self.error = None
        self._runs = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()

    def _device(self):
        if self._backend is None:
            try:
                self._backend = _UInputBackend()
                self.state = "ready"
            except Exception as e:  # no evdev, or /dev/uinput not writable
                self.state = "error"
                self.error = (f"/dev/uinput isn't writable ({e})" if isinstance(e, OSError)
                              else f"can't create the virtual input device ({e})")
                return None
        return self._backend

    def _write(self, events):
        with self._write_lock:
            for type_, code, value in events:
                self._backend.write(type_, code, value)
            self._backend.syn()

    def _finished(self, run):
        with self._lock:
            if self._runs.get(run.key) is run:
                del self._runs[run.key]

    def press(self, key, events, mode):
        """The button `key` went down."""
        try:
            with self._lock:
                run = self._runs.get(key)
                if run is not None and run.is_alive():
                    if mode == "toggle":
                        run.cancel.set()  # a second press stops it
                    return                # once: ignore presses while it plays
                if self._device() is None:
                    return
                run = _Run(self, key, list(events), mode if mode in ("once", "while-held", "toggle") else "once")
                self._runs[key] = run
                run.start()
        except Exception as e:
            self.error = str(e)

    def release(self, key):
        """The button `key` went up."""
        try:
            with self._lock:
                run = self._runs.get(key)
            if run is not None and run.mode == "while-held":
                run.cancel.set()
        except Exception as e:
            self.error = str(e)

    def stop_all(self, wait=1.0):
        try:
            with self._lock:
                runs = list(self._runs.values())
            for run in runs:
                run.cancel.set()
            deadline = time.monotonic() + wait
            for run in runs:
                run.join(max(0.0, deadline - time.monotonic()))
        except Exception as e:
            self.error = str(e)

    def close(self):
        self.stop_all()
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception:
                pass
            self._backend = None
            self.state = "idle"

    def running(self):
        with self._lock:
            return {k for k, r in self._runs.items() if r.is_alive()}
