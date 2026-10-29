"""Lighting controls and previews backed by the independent background service."""

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor

from .. import ipc, settings
from ..runtime.lighting import DEFAULTS, EFFECTS, EFFECT_NAMES


class LiveLighting(QObject):
    colors = Signal(object)
    status = Signal(str, str)
    runningChanged = Signal(bool)

    def __init__(self, state):
        super().__init__()
        self.state = state
        saved = settings.load().get('live', {})
        self.options = {k: {**v, **saved.get('options', {}).get(k, {})} for k, v in DEFAULTS.items()}
        self.selected = saved.get('effect', 'screen')
        self.effect = self.selected if saved.get('on') else None
        self.wanted_on = bool(saved.get('on'))
        self._colors = None
        self._status = None
        self._timer = QTimer(self, interval=100)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    @property
    def running(self):
        return self.effect is not None

    def _update(self, data):
        was_running = self.running
        self.effect = data['live_effect']
        self.selected = data['live_selected']
        if was_running != self.running:
            self.runningChanged.emit(self.running)
        colors = data['colors']
        if colors != self._colors:
            self._colors = colors
            self.colors.emit({z: QColor(*c) for z, c in colors.items()})
        if data['status'] != self._status:
            self._status = data['status']
            self.status.emit(*self._status)

    def _poll(self):
        try:
            self._update(ipc.request('snapshot', timeout=1))
        except (OSError, RuntimeError, ValueError) as error:
            self.status.emit('error', f'Background service unavailable: {error}')

    def _call(self, method, *args, **kwargs):
        try:
            self._update(ipc.request('lighting', method, args, kwargs))
        except (OSError, RuntimeError, ValueError) as error:
            self.status.emit('error', str(error))

    def start(self, effect=None):
        self._call('start', effect)

    def stop(self, remember=True):
        self._call('stop', remember=remember)

    def resume(self):
        self._poll()

    def select(self, effect):
        self._call('select', effect)

    def set_option(self, effect, key, value, save=True):
        self.options[effect][key] = value
        self._call('set_option', effect, key, value, save=save)

    def choose_another_screen(self):
        self._call('choose_another_screen')

    def set_override(self, spec):
        pass  # rules run in the service

    def shutdown(self):
        self._timer.stop()  # closing settings must not turn the mouse's effects off
