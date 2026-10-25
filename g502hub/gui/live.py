"""Live lighting: effects computed by the app and streamed to the mouse.

The mouse stays in onboard mode; colors go to its LEDs' RAM only, so turning
an effect off (or quitting) brings the saved lighting straight back.
"""

import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor

from .. import lightfx, settings
from ..onboard import LedEffect

FPS = 30
KEEPALIVE_S = 1.0  # resend even unchanged colors, e.g. after G9 loads another profile
FAST_POLL_MS = 120

EFFECTS = [("screen", "Screen sampler"), ("audio", "Audio visualizer"),
           ("wave", "Color wave"), ("dpi", "DPI colors")]
EFFECT_NAMES = dict(EFFECTS)

DEFAULTS = {
    "screen": {"dpi_area": "screen", "logo_area": "center", "vivid": True,
               "saturation": 1.3, "brightness": 1.0, "smoothing": 0.6},
    "audio": {"style": "pulse", "color": "#14b4ff", "sensitivity": 1.0, "brightness": 1.0},
    "wave": {"period": 6.0, "saturation": 1.0, "brightness": 1.0, "reverse": False},
    "dpi": {"colors": ["#ff2a2a", "#ffd400", "#3ddc84", "#14b4ff", "#a040ff"]},
}


class LiveLighting(QObject):
    colors = Signal(object)     # {zone: QColor} while running, {} when stopped
    status = Signal(str, str)   # kind (busy, ok, error, info), text
    runningChanged = Signal(bool)

    def __init__(self, state):
        super().__init__()
        self.state = state
        saved = settings.load().get("live", {})
        self.options = {k: {**v, **saved.get("options", {}).get(k, {})} for k, v in DEFAULTS.items()}
        self.selected = saved.get("effect", "screen") if saved.get("effect") in DEFAULTS else "screen"
        self.wanted_on = bool(saved.get("on"))
        self.effect = None
        self.screen = self.audio = None
        self._current = {}
        self._sent = {}
        self._sent_at = 0.0
        self._rainbow = lightfx.BeatRainbow()
        self._t0 = time.monotonic()
        self._screen_state = None
        self._timer = QTimer(self, interval=1000 // FPS)
        self._timer.timeout.connect(self._tick)

    @property
    def running(self):
        return self.effect is not None

    # ------------------------------------------------------------ control

    def start(self, effect=None):
        effect = effect or self.selected
        self.selected, self.effect = effect, effect
        self._current, self._sent = {}, {}
        self._sync_sources()
        self.state.set_poll_ms(FAST_POLL_MS if effect == "dpi" else 500)
        self._timer.start()
        self._save(on=True)
        self.runningChanged.emit(True)
        if effect != "screen":
            self.status.emit("ok", f"{EFFECT_NAMES[effect]} is on")

    def stop(self, remember=True):
        was_running = self.running
        self._timer.stop()
        self.effect = None
        self._sync_sources()
        self.state.set_poll_ms(500)
        self.colors.emit({})
        if was_running:
            self._restore_saved_lighting()
            self.runningChanged.emit(False)
            self.status.emit("info", "Live lighting off: back to the lighting saved on the mouse")
        if remember:
            self._save(on=False)

    def resume(self):
        """Turn the last live effect back on if it was on when the app closed."""
        if self.wanted_on and not self.running:
            self.start(self.selected)

    def select(self, effect):
        self.selected = effect
        if self.running:
            self.start(effect)
        else:
            self._save(on=False)

    def set_option(self, effect, key, value, save=True):
        self.options[effect][key] = value
        if save:
            self._save(on=self.running)

    def choose_another_screen(self):
        settings.update(screen_token=None)
        if self.effect == "screen":
            self.start("screen")

    def _save(self, on):
        self.wanted_on = on
        settings.update(live={"effect": self.selected, "on": on, "options": self.options})

    def _restore_saved_lighting(self):
        profile = self.state.profile()
        if profile is not None and self.state.connected:
            for zone, effect in enumerate(profile.leds):
                self.state.preview_led(zone, effect)

    # ------------------------------------------------------------ sources

    def _sync_sources(self):
        want_screen, want_audio = self.effect == "screen", self.effect == "audio"
        if self.screen is not None and not want_screen:
            self.screen.stop()
            self.screen = None
        if self.audio is not None and not want_audio:
            self.audio.stop()
            self.audio = None
        if want_screen and self.screen is None:
            from ..effects.screen import ScreenCapture
            self.screen = ScreenCapture(restore_token=settings.load().get("screen_token"), fps=FPS)
            self._screen_state = None
            self.screen.start()
            self.status.emit("busy", "Starting screen capture… pick a screen if asked")
        if want_audio and self.audio is None:
            from ..effects.audio import AudioMonitor
            self.audio = AudioMonitor()
            self.audio.start()

    def _check_screen(self):
        state = self.screen.state
        if state == self._screen_state:
            return state == "running"
        self._screen_state = state
        if state == "running":
            if self.screen.restore_token:
                settings.update(screen_token=self.screen.restore_token)
            size = self.screen.source_size
            self.status.emit("ok", "Screen sampler is on" + (f" ({size[0]}×{size[1]})" if size else ""))
        elif state == "cancelled":
            self.stop()
            self.status.emit("error", "Screen sharing was cancelled, so the screen sampler is off")
        elif state == "error":
            error = self.screen.error
            self.stop()
            self.status.emit("error", f"Screen capture failed: {error}")
        return state == "running"

    # ------------------------------------------------------------ frames

    def _targets(self, t):
        """{zone: rgb} for this frame, or None to keep the current colors."""
        o = self.options[self.effect]
        if self.effect == "screen":
            if not self._check_screen() or (frame := self.screen.frame()) is None:
                return None
            out = {}
            for zone, area in ((0, o["dpi_area"]), (1, o["logo_area"])):
                rgb = lightfx.sample(frame, area, o["vivid"])
                out[zone] = lightfx.adjust(rgb, o["saturation"], o["brightness"])
            return out
        if self.effect == "audio":
            if self.audio.state == "error":
                error = self.audio.error
                self.stop()
                self.status.emit("error", f"Couldn't capture sound: {error}")
                return None
            levels = self.audio.levels()
            sensitivity = o["sensitivity"]
            if o["style"] == "spectrum":
                out = lightfx.audio_spectrum(levels, sensitivity)
            elif o["style"] == "rainbow":
                out = self._rainbow(levels, sensitivity)
            else:
                out = lightfx.audio_pulse(levels, lightfx.hex_to_rgb(o["color"]), sensitivity)
            return {z: lightfx.scale(rgb, o["brightness"]) for z, rgb in out.items()}
        if self.effect == "wave":
            return {z: lightfx.wave(t, o["period"], z, o["saturation"], o["brightness"], o["reverse"])
                    for z in (0, 1)}
        if self.effect == "dpi":
            profile = self.state.profile()
            levels = [s for s, _ in profile.dpi_levels()] if profile else []
            if self.state.dpi_index not in levels:
                return None
            rgb = lightfx.hex_to_rgb(o["colors"][levels.index(self.state.dpi_index)])
            return {0: rgb, 1: rgb}
        return None

    def _tick(self):
        if not self.running:
            return
        now = time.monotonic()
        targets = self._targets(now - self._t0)
        if not self.running or targets is None:
            return
        response = 1.0
        if self.effect == "screen":
            response = 1.0 - 0.93 * self.options["screen"]["smoothing"]
        for zone, rgb in targets.items():
            self._current[zone] = lightfx.smooth(self._current.get(zone), rgb, response)
        rgb8 = {z: lightfx.to_rgb8(c) for z, c in self._current.items()}
        self.colors.emit({z: QColor(*c) for z, c in rgb8.items()})
        stale = now - self._sent_at > KEEPALIVE_S
        changed = {z: c for z, c in rgb8.items()
                   if stale or max(abs(a - b) for a, b in zip(c, self._sent.get(z, (999, 999, 999)))) > 1}
        if changed and self.state.connected and not self.state.bridge.pending:
            self._sent.update(changed)
            self._sent_at = now

            def job(dev):
                for zone, c in changed.items():
                    dev.set_led(zone, LedEffect.fixed(c))
            self.state.bridge.call(job)
