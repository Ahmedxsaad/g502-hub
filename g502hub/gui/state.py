"""Device access off the UI thread, and the editable state of the mouse."""

import time

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QThread, QTimer, Signal, Slot

from .. import backup, onboard
from ..device import MODE_ONBOARD, ROM, DeviceNotFound, G502

SAVE_DELAY_MS = 700
POLL_MS = 500
RECONNECT_MS = 2000


class _Worker(QObject):
    finished = Signal(object, object, object)  # callback, result, error

    def __init__(self):
        super().__init__()
        self.dev = None

    @Slot(object, object)
    def run(self, fn, callback):
        result = error = None
        try:
            if self.dev is None:
                self.dev = G502()
            result = fn(self.dev)
        except (OSError, DeviceNotFound) as e:
            # Unplugged, or never there: reopen on the next call
            if self.dev is not None:
                self.dev.close()
            self.dev = None
            error = e
        except Exception as e:  # HID++ errors, bad values
            error = e
        self.finished.emit(callback, result, error)


class Bridge(QObject):
    """Runs callables against the G502 on one worker thread, in order."""

    _submit = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.pending = 0
        self._thread = QThread()
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self._submit.connect(self._worker.run)
        self._worker.finished.connect(self._finished)
        self._thread.start()

    def call(self, fn, done=None):
        """fn(dev) runs on the worker; done(result, error) runs on the UI thread."""
        self.pending += 1
        self._submit.emit(fn, done)

    @Slot(object, object, object)
    def _finished(self, callback, result, error):
        self.pending -= 1
        if callback:
            callback(result, error)

    def wait_idle(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while self.pending and time.monotonic() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)

    def stop(self):
        self._thread.quit()
        self._thread.wait(2000)


class MouseState(QObject):
    """What the UI edits: the 5 onboard profiles, plus live device state."""

    connectedChanged = Signal(bool)
    loaded = Signal()
    profileEdited = Signal(int)  # slot
    activeChanged = Signal()
    status = Signal(str, str)  # kind (busy, ok, error, info), text

    def __init__(self):
        super().__init__()
        self.bridge = Bridge()
        self.connected = False
        self.name = ""
        self.firmware = []
        self.info = None
        self.zones = []
        self.dpi_range = (100, 25600, 50)
        self.intervals = [1, 2, 4, 8]
        self.directory = None
        self.profiles = []  # slot n is profiles[n - 1]
        self.factory = []
        self.active_slot = None
        self.dpi_index = None
        self._dirty = {}  # slot -> needs a firmware reload to apply
        self._dpi_target = None  # DPI index to land on after the next reload
        self._backed_up = False
        self._loading = False
        self._led_pending = {}

        self._save_timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.flush)
        self.poll_ms = POLL_MS
        self._poll_timer = QTimer(self, interval=POLL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._led_timer = QTimer(self, singleShot=True, interval=40)
        self._led_timer.timeout.connect(self._send_led_preview)

    # ------------------------------------------------------------ loading

    def start(self):
        self.load()
        self._poll_timer.start()

    def load(self):
        if self._loading:
            return
        self._loading = True

        def job(dev):
            if dev.get_mode() != MODE_ONBOARD:
                dev.set_mode(MODE_ONBOARD)
            directory = dev.read_directory()
            rom = onboard.Directory.decode(dev.read_sector(ROM))
            return {
                "name": dev.name(), "firmware": dev.firmware(), "info": dev.onboard_info(),
                "zones": dev.led_zones(), "dpi_range": dev.dpi_range(),
                "intervals": dev.report_intervals(), "directory": directory,
                "profiles": [dev.read_profile(e.sector) for e in directory.entries],
                "factory": [dev.read_profile(e.sector) for e in rom.entries],
                "active": dev.get_current_profile(), "dpi_index": dev.get_current_dpi_index(),
            }

        if not self.connected:
            self.status.emit("busy", "Looking for the G502 HERO…")
        self.bridge.call(job, self._loaded)

    def _loaded(self, data, error):
        self._loading = False
        if error:
            self._set_connected(False)
            if not isinstance(error, (OSError, DeviceNotFound)):
                self.status.emit("error", f"Could not read the mouse: {error}")
            else:
                self.status.emit("info", str(error) if isinstance(error, DeviceNotFound)
                                 else "Mouse disconnected")
            return
        for key in ("name", "firmware", "info", "zones", "dpi_range", "intervals",
                    "directory", "profiles", "factory", "dpi_index"):
            setattr(self, key, data[key])
        self.active_slot = self.slot_of(data["active"])
        self._dirty.clear()
        self._set_connected(True)
        self.loaded.emit()
        self.status.emit("ok", "Ready")

    def _set_connected(self, connected):
        if connected != self.connected:
            self.connected = connected
            self._poll_timer.setInterval(self.poll_ms if connected else RECONNECT_MS)
            self.connectedChanged.emit(connected)

    def set_poll_ms(self, ms):
        """How often to read the active profile and DPI level (faster for DPI-linked effects)."""
        self.poll_ms = ms
        if self.connected:
            self._poll_timer.setInterval(ms)

    def slot_of(self, sector):
        for n, entry in enumerate(self.directory.entries, 1):
            if entry.sector == sector:
                return n
        return None

    def sector_of(self, slot):
        return self.directory.entries[slot - 1].sector

    def _poll(self):
        if not self.connected:
            self.load()
            return
        if self.bridge.pending:
            return
        self.bridge.call(lambda dev: (dev.get_current_profile(), dev.get_current_dpi_index()),
                         self._polled)

    def _polled(self, result, error):
        if error:
            self._set_connected(False)
            self.status.emit("info", "Mouse disconnected")
            return
        slot, dpi_index = self.slot_of(result[0]), result[1]
        if (slot, dpi_index) != (self.active_slot, self.dpi_index):
            self.active_slot, self.dpi_index = slot, dpi_index
            self.activeChanged.emit()

    # ------------------------------------------------------------ editing

    def profile(self, slot=None):
        slot = slot or self.active_slot
        return self.profiles[slot - 1] if slot else None

    def edit(self, mutate, slot=None, reload=True, dpi_index=None):
        """Change a profile in memory and save it to the mouse shortly after.

        `dpi_index`: the DPI level the active profile should be on once reloaded,
        for edits that move levels around.
        """
        slot = slot or self.active_slot
        mutate(self.profiles[slot - 1])
        if dpi_index is not None and slot == self.active_slot:
            self.dpi_index = self._dpi_target = dpi_index
        self._dirty[slot] = self._dirty.get(slot, False) or reload
        self.profileEdited.emit(slot)
        self.status.emit("busy", "Unsaved changes…")
        self._save_timer.start()

    def flush(self):
        self._save_timer.stop()
        if not self._dirty or not self.connected:
            return
        jobs = []
        for slot, reload in sorted(self._dirty.items()):
            data = self.profiles[slot - 1].encode()
            self.profiles[slot - 1].raw = data
            jobs.append((self.sector_of(slot), data, reload))
        self._dirty.clear()
        need_backup = not self._backed_up
        dpi_target, self._dpi_target = self._dpi_target, None

        def job(dev):
            if need_backup:
                backup.save(backup.dump(dev))
            for sector, data, _ in jobs:
                dev.write_sector(sector, data)
            current = dev.get_current_profile()
            if any(sector == current and reload for sector, _, reload in jobs):
                dev.reload_current_profile(dpi_target)
            return len(jobs)

        def done(count, error):
            if error:
                self.status.emit("error", f"Saving failed: {error}")
                return
            self._backed_up = True
            self.status.emit("ok", "Saved to mouse")

        self.status.emit("busy", "Saving to mouse…")
        self.bridge.call(job, done)

    def activate(self, slot):
        self.flush()
        sector = self.sector_of(slot)

        def done(_, error):
            if error:
                self.status.emit("error", f"Could not switch profile: {error}")
                return
            self.active_slot, self.dpi_index = slot, self.profile(slot).default_dpi_index
            self.activeChanged.emit()

        self.bridge.call(lambda dev: dev.set_current_profile(sector), done)

    def set_slot_enabled(self, slot, enabled):
        self.directory.entries[slot - 1].enabled = enabled
        data = self.directory.encode(self.info.sector_size)
        self.directory.raw = data

        def job(dev):
            current = dev.get_current_profile()
            dev.write_sector(0, data)
            dev.set_current_profile(current)  # directory writes can shift it

        self.bridge.call(job, lambda _, e: self.status.emit(
            "error" if e else "ok", f"Saving failed: {e}" if e else "Saved to mouse"))

    def reset_slot(self, slot):
        """Replace a slot with its factory profile."""
        factory = self.factory[(slot - 1) % len(self.factory)]
        self.profiles[slot - 1] = onboard.Profile.decode(onboard.seal(factory.raw))
        self.edit(lambda p: None, slot)

    def copy_slot(self, source, target):
        copy = onboard.Profile.decode(self.profiles[source - 1].encode())
        self.profiles[target - 1] = copy
        self.edit(lambda p: None, target)

    # ------------------------------------------------------------ live previews

    def preview_led(self, zone, effect):
        """Show lighting on the mouse right away, throttled, without saving."""
        self._led_pending[zone] = effect
        if not self._led_timer.isActive():
            self._led_timer.start()

    def _send_led_preview(self):
        pending, self._led_pending = self._led_pending, {}

        def job(dev):
            for zone, effect in pending.items():
                dev.set_led(zone, effect, persistence=0)

        if self.connected:
            self.bridge.call(job)

    def preview_dpi(self, dpi):
        if self.connected:
            self.bridge.call(lambda dev: dev.set_dpi(dpi))

    # ------------------------------------------------------------ backups

    def backup_now(self, done):
        self.bridge.call(lambda dev: str(backup.save(backup.dump(dev))), done)

    def restore(self, path, done):
        def job(dev):
            backup.save(backup.dump(dev))
            return backup.restore(dev, backup.load(path), log=lambda _: None)

        def finished(result, error):
            done(result, error)
            if not error:
                self.load()

        self.flush()
        self.bridge.call(job, finished)

    def shutdown(self):
        self._poll_timer.stop()
        self.flush()
        self.bridge.wait_idle()
        self.bridge.stop()
