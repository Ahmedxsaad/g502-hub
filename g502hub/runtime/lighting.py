"""Live lighting: effects computed by the app and streamed to the mouse.

The mouse stays in onboard mode; colors go to its LEDs' RAM only, so turning
an effect off (or quitting) brings the saved lighting straight back.

What shows, highest first: a rule's lighting (set_override), the live effect
the user turned on, the lighting saved on the mouse.
"""

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from .. import settings
from ..onboard import LedEffect
from .state import POLL_MS

FPS = 30
KEEPALIVE_S = 1.0  # resend even unchanged colors, e.g. after G9 loads another profile
FAST_POLL_MS = 120

EFFECTS = [("screen", "Screen sampler"), ("audio", "Audio visualizer"),
           ("wave", "Color wave"), ("dpi", "DPI colors")]
EFFECT_NAMES = dict(EFFECTS)
GSI_GAMES = {730: "cs2", 570: "dota2"}

DEFAULTS = {
    "screen": {"dpi_area": "screen", "logo_area": "center", "vivid": True,
               "saturation": 1.3, "brightness": 1.0, "smoothing": 0.6},
    "audio": {"style": "pulse", "color": "#14b4ff", "sensitivity": 1.0, "brightness": 1.0},
    "wave": {"period": 6.0, "saturation": 1.0, "brightness": 1.0, "reverse": False},
    "dpi": {"colors": ["#ff2a2a", "#ffd400", "#3ddc84", "#14b4ff", "#a040ff"]},
}


def art_palette(path):
    """Two lighting colors from a cover image: {logo: main color, DPI lights: second color}."""
    import numpy as np
    from PySide6.QtGui import QImage
    from .. import lightfx

    image = QImage(path)
    if image.isNull():
        return None
    image = image.scaled(96, 54, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB888)
    rows = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    frame = rows[:, :image.width() * 3].reshape(image.height(), image.width(), 3)
    main, second = lightfx.palette(frame, 2)
    return {1: main, 0: second}


class LiveLighting(QObject):
    colors = Signal(object)     # {zone: RGB tuple}; no graphical toolkit required
    status = Signal(str, str)   # kind (busy, ok, error, info), text
    runningChanged = Signal(bool)

    def __init__(self, state):
        super().__init__()
        self.state = state
        saved = settings.load().get("live", {})
        self.options = {k: {**v, **saved.get("options", {}).get(k, {})} for k, v in DEFAULTS.items()}
        self.selected = saved.get("effect", "screen") if saved.get("effect") in DEFAULTS else "screen"
        self.wanted_on = bool(saved.get("on"))
        self.effect = None      # the user's live effect, when on
        self.override = None    # a rule's lighting: {"lighting", "color", "period_ms", "game", "name"}
        self.screen = self.audio = self.gsi = self.lightsync = None
        self._gsi_fx = {}
        self._art = {}
        self._shown = None
        self._current = {}
        self._sent = {}
        self._sent_at = 0.0
        self._rainbow = None
        self._t0 = time.monotonic()
        self._screen_state = None
        self._timer = QTimer(self, interval=1000 // FPS)
        self._timer.timeout.connect(self._tick)

    @property
    def running(self):
        """The user's own live effect is on."""
        return self.effect is not None

    @property
    def active(self):
        """What is showing now: a lighting kind, or None for the saved lighting."""
        return self.override["lighting"] if self.override else self.effect

    # ------------------------------------------------------------ control

    def start(self, effect=None):
        effect = effect or self.selected
        self.selected, self.effect = effect, effect
        self._save(on=True)
        self._refresh()
        self.runningChanged.emit(True)
        if effect != "screen":
            self.status.emit("ok", f"{EFFECT_NAMES[effect]} is on")

    def stop(self, remember=True):
        was_running = self.running
        self.effect = None
        self._refresh()
        if was_running:
            self.runningChanged.emit(False)
            if not self.override:
                self.status.emit("info", "Live lighting off: back to the lighting saved on the mouse")
        if remember:
            self._save(on=False)

    def set_override(self, spec):
        """Show a rule's lighting instead (None to end it)."""
        if spec == self.override:
            return
        self.override = spec
        self._refresh()

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
        if self.screen is not None:
            self.screen.stop()
            self.screen = None
            self._refresh()

    def shutdown(self):
        self.override = None
        self.stop(remember=False)
        for source in (self.gsi, self.lightsync):
            if source is not None:
                source.stop()

    def _save(self, on):
        self.wanted_on = on
        settings.update(live={"effect": self.selected, "on": on, "options": self.options})

    def _refresh(self):
        """Start or stop sources and the frame timer for whatever should show now."""
        kind = self.active
        if kind != self._shown:
            self._current, self._sent = {}, {}
        self._sync_sources(kind)
        self.state.set_poll_ms(FAST_POLL_MS if kind == "dpi" else POLL_MS)
        if kind:
            self._timer.start()
        else:
            self._timer.stop()
            self.colors.emit({})
            if self._shown:
                self._restore_saved_lighting()
        self._shown = kind

    def _restore_saved_lighting(self):
        profile = self.state.profile()
        if profile is not None and self.state.connected:
            for zone, effect in enumerate(profile.leds):
                self.state.preview_led(zone, effect)

    def _source_failed(self, text):
        """A capture source gave up: drop whatever was using it."""
        if self.override:
            self.override = None
            self._refresh()
        else:
            self.stop()
        self.status.emit("error", text)

    # ------------------------------------------------------------ sources

    def _sync_sources(self, kind):
        want = {"screen": kind == "screen", "audio": kind == "audio", "game": kind == "game"}
        if self.screen is not None and not want["screen"]:
            self.screen.stop()
            self.screen = None
        if self.audio is not None and not want["audio"]:
            self.audio.stop()
            self.audio = None
        if want["screen"] and self.screen is None:
            from ..effects.screen import ScreenCapture
            self.screen = ScreenCapture(restore_token=settings.load().get("screen_token"), fps=FPS)
            self._screen_state = None
            self.screen.start()
            self.status.emit("busy", "Starting screen capture… pick a screen if asked")
        if want["audio"] and self.audio is None:
            from ..effects.audio import AudioMonitor
            self.audio = AudioMonitor()
            self.audio.start()
        if want["game"]:  # both listeners are cheap; they stay up once a game rule has run
            if self.gsi is None:
                from ..effects.gsi import GameStateServer
                self.gsi = GameStateServer()
                self.gsi.start()
            if self.lightsync is None:
                try:
                    from ..effects.lightsync import LightsyncReceiver
                except ImportError:
                    self.lightsync = False
                else:
                    self.lightsync = LightsyncReceiver()
                    self.lightsync.start()

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
            self._source_failed("Screen sharing was cancelled, so the screen sampler is off")
        elif state == "error":
            self._source_failed(f"Screen capture failed: {self.screen.error}")
        return state == "running"

    # ------------------------------------------------------------ frames

    def _art_colors(self, game):
        path = game.art if game else None
        if path not in self._art:
            self._art[path] = art_palette(path) if path else None
        return self._art[path]

    def _game_colors(self, game, t):
        """Game-driven: CS2/Dota 2 game state, else the LIGHTSYNC bridge, else cover art."""
        name = GSI_GAMES.get(game.appid) if game else None
        if name and self.gsi is not None:
            state = self.gsi.latest()
            if state is not None and state.game == name:
                if name not in self._gsi_fx:
                    from ..effects import gsi
                    self._gsi_fx[name] = gsi.Cs2Lighting() if name == "cs2" else gsi.Dota2Lighting()
                try:
                    out = self._gsi_fx[name](state, t)
                except (TypeError, ValueError, KeyError, AttributeError):
                    out = None  # an odd payload; keep going with the fallbacks
                if out is not None:
                    return out
        if self.lightsync:
            out = self.lightsync.colors(t)
            if out is not None:
                return out
        return self._art_colors(game)

    def _targets(self, t):
        """{zone: rgb} for this frame, or None to keep the current colors."""
        from .. import lightfx

        kind = self.active
        if self.override:
            o = self.override
            if kind == "color":
                rgb = lightfx.hex_to_rgb(o["color"])
                return {0: rgb, 1: rgb}
            if kind == "breathing":
                rgb = lightfx.breathe(lightfx.hex_to_rgb(o["color"]), t, o["period_ms"] / 1000)
                return {0: rgb, 1: rgb}
            if kind == "art":
                return self._art_colors(o.get("game")) or {0: lightfx.hex_to_rgb(o["color"]),
                                                           1: lightfx.hex_to_rgb(o["color"])}
            if kind == "game":
                return self._game_colors(o.get("game"), t)
        o = self.options[kind]
        if kind == "screen":
            if not self._check_screen() or (frame := self.screen.frame()) is None:
                return None
            out = {}
            for zone, area in ((0, o["dpi_area"]), (1, o["logo_area"])):
                rgb = lightfx.sample(frame, area, o["vivid"])
                out[zone] = lightfx.adjust(rgb, o["saturation"], o["brightness"])
            return out
        if kind == "audio":
            if self.audio.state == "error":
                self._source_failed(f"Couldn't capture sound: {self.audio.error}")
                return None
            levels = self.audio.levels()
            sensitivity = o["sensitivity"]
            if o["style"] == "spectrum":
                out = lightfx.audio_spectrum(levels, sensitivity)
            elif o["style"] == "rainbow":
                if self._rainbow is None:
                    self._rainbow = lightfx.BeatRainbow()
                out = self._rainbow(levels, sensitivity)
            else:
                out = lightfx.audio_pulse(levels, lightfx.hex_to_rgb(o["color"]), sensitivity)
            return {z: lightfx.scale(rgb, o["brightness"]) for z, rgb in out.items()}
        if kind == "wave":
            return {z: lightfx.wave(t, o["period"], z, o["saturation"], o["brightness"], o["reverse"])
                    for z in (0, 1)}
        if kind == "dpi":
            profile = self.state.profile()
            levels = [s for s, _ in profile.dpi_levels()] if profile else []
            if self.state.dpi_index not in levels:
                return None
            rgb = lightfx.hex_to_rgb(o["colors"][levels.index(self.state.dpi_index)])
            return {0: rgb, 1: rgb}
        return None

    def _tick(self):
        from .. import lightfx

        kind = self.active
        if not kind:
            return
        now = time.monotonic()
        targets = self._targets(now - self._t0)
        if self.active != kind or targets is None:
            return
        response = 1.0
        if kind == "screen":
            response = 1.0 - 0.93 * self.options["screen"]["smoothing"]
        elif kind == "art":
            response = 0.08  # fade into a new game's colors
        for zone, rgb in targets.items():
            self._current[zone] = lightfx.smooth(self._current.get(zone), rgb, response)
        rgb8 = {z: lightfx.to_rgb8(c) for z, c in self._current.items()}
        self.colors.emit(rgb8)
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
