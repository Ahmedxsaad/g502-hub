"""Headless per-user service. Owns the mouse, macros, rules and live effects.

Run `python3 -m g502hub.daemon`; no QApplication, widgets, tray or window is
constructed. The GUI connects to this service and can exit independently.
"""

import fcntl
import json
import os
import signal
import sys

from PySide6.QtCore import QCoreApplication, QObject, QTimer
from PySide6.QtNetwork import QLocalServer

from . import ipc, settings, rules
from .keylabels import KeyLabels
from .runtime.state import MouseState
from .runtime.macros import MacroEngine
from .runtime.rules import RulesEngine
from .runtime.lighting import LiveLighting


class Service(QObject):
    def __init__(self):
        super().__init__()
        self.state = MouseState()
        self.live = LiveLighting(self.state)
        self.macros = MacroEngine(self.state, KeyLabels())
        self.rules = RulesEngine(self.state, self.live)
        self.colors = {}
        self.last_status = ('info', 'Starting service')
        self.live.colors.connect(lambda rgb: setattr(self, 'colors', rgb))
        self.state.status.connect(self._status)
        self.live.status.connect(self._status)
        self.state.loaded.connect(self._loaded)
        self.state.activeChanged.connect(self._dpi_changed)
        self._saved = settings.load()
        self._watch = QTimer(self, interval=1000)
        self._watch.timeout.connect(self.reload_settings)
        self._refresh = QTimer(self, singleShot=True, interval=100)
        self._refresh.timeout.connect(self.state.load)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept)
        self._clients = set()
        if not self.server.listen(ipc.socket_path()):
            raise RuntimeError(self.server.errorString())
        self.rules.start()
        self.state.start()
        self._watch.start()

    def _status(self, kind, text):
        self.last_status = (kind, text)

    def _loaded(self):
        self.macros.sync()
        self.live.resume()

    def _dpi_changed(self):
        # Plasma's D-Bus OSD needs QtDBus, but no graphical application.
        state = self.state
        now = (state.active_slot, state.dpi_index)
        before, self._osd_seen = getattr(self, '_osd_seen', None), now
        if before is None or before == now or not settings.load().get('osd', True):
            return
        profile = state.profile()
        from .gui.system import show_osd
        if now[0] != before[0]:
            name = profile.name if profile and profile.name else f'Profile {now[0]}'
            show_osd(f'{name}  ·  slot {now[0]}')
        elif profile and now[1] is not None and 0 <= now[1] < len(profile.dpi) and profile.dpi[now[1]]:
            show_osd(f'{profile.dpi[now[1]]} DPI')

    def reload_settings(self):
        saved = settings.load()
        if saved == self._saved:
            return
        before, self._saved = self._saved, saved
        if any(saved.get(k) != before.get(k) for k in ('macros', 'app_macros')):
            from . import macros
            self.macros.macros = macros.load(saved.get('macros'))
            self.macros.app_buttons = dict(saved.get('app_macros', {}))
            self.macros.sync()
        if saved.get('rules') != before.get('rules'):
            self.rules.rules = rules.load(saved.get('rules'))
        if saved.get('live') != before.get('live'):
            live = saved.get('live', {})
            from .runtime.lighting import DEFAULTS
            self.live.options = {k: {**v, **live.get('options', {}).get(k, {})} for k, v in DEFAULTS.items()}
            self.live.selected = live.get('effect', self.live.selected)
            if live.get('on'):
                self.live.start(self.live.selected)
            else:
                self.live.stop(remember=False)

    def snapshot(self):
        return {'colors': self.colors, 'live_effect': self.live.effect,
                'live_selected': self.live.selected, 'status': self.last_status,
                'context': self.rules.context, 'active_rule': self.rules.active.to_dict() if self.rules.active else None,
                'seen_apps': self.rules.seen_apps, 'seen_media': self.rules.seen_media,
                'rules_error': self.rules.error, 'connected': self.state.connected,
                'pid': os.getpid()}

    def _accept(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client._buffer = bytearray()
            client._submitted = False
            self._clients.add(client)
            timer = QTimer(client, singleShot=True, interval=30000)
            timer.timeout.connect(lambda c=client: c.abort())
            timer.start()
            client.readyRead.connect(lambda c=client: self._read(c))
            client.disconnected.connect(lambda c=client: self._discard(c))
            self._read(client)

    def _discard(self, client):
        self._clients.discard(client)
        client.deleteLater()

    def _reply(self, client, result=None, error=None):
        if client not in self._clients:
            return
        try:
            response = {'result': ipc.encode(result)} if error is None else {
                'error': str(error), 'error_type': type(error).__name__}
            client.write(json.dumps(response).encode() + b'\n')
            client.disconnectFromServer()
        except (RuntimeError, TypeError, ValueError):
            client.abort()

    def _read(self, client):
        if client._submitted:
            return
        client._buffer.extend(bytes(client.readAll()))
        if len(client._buffer) > ipc.MAX_MESSAGE:
            client.abort()
            return
        if b'\n' not in client._buffer:
            return
        client._submitted = True
        try:
            message = json.loads(bytes(client._buffer).split(b'\n', 1)[0])
            if message['version'] != ipc.VERSION:
                raise ValueError('Incompatible G502 Hub service version')
            command = message['command']
            args, kwargs = ipc.decode(message['args']), ipc.decode(message['kwargs'])
            if command == 'ping':
                self._reply(client, {'version': ipc.VERSION, 'pid': os.getpid()})
            elif command == 'snapshot':
                self._reply(client, self.snapshot())
            elif command == 'reload':
                self.reload_settings()
                self._reply(client)
            elif command == 'device':
                method, call_args, call_kwargs = args
                if method not in ipc.DEVICE_METHODS:
                    raise ValueError('Device method is not allowed')
                def done(result, error):
                    self._reply(client, result, error)
                    if not error and method in ('write_sector', 'write_profile', 'set_mode',
                                                 'set_current_profile', 'reload_current_profile'):
                        self._refresh.start()
                self.state.bridge.call(lambda dev: getattr(dev, method)(*call_args, **call_kwargs), done)
            elif command == 'lighting':
                method, call_args, call_kwargs = args
                if method not in ('start', 'stop', 'select', 'set_option', 'choose_another_screen'):
                    raise ValueError('Lighting method is not allowed')
                getattr(self.live, method)(*call_args, **call_kwargs)
                self._saved = settings.load()
                self._reply(client, self.snapshot())
            elif command == 'stop':
                self._reply(client)
                QTimer.singleShot(100, QCoreApplication.quit)
            else:
                raise ValueError('Unknown service command')
        except Exception as error:
            self._reply(client, error=error)

    def shutdown(self):
        self._watch.stop()
        self._refresh.stop()
        self.server.close()
        self.rules.stop()
        self.macros.shutdown()
        self.live.shutdown()
        self.state.shutdown()
        for client in list(self._clients):
            client.abort()


def main():
    if "--stop" in sys.argv[1:]:
        ipc.request('stop')
        return
    if "--status" in sys.argv[1:]:
        print(json.dumps(ipc.request('ping')))
        return
    app = QCoreApplication(sys.argv)
    app.setApplicationName('g502-hub-service')
    lock = open(ipc.runtime_dir() / 'service.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # another launch already owns the socket and mouse
    QLocalServer.removeServer(ipc.socket_path())
    service = Service()
    app.aboutToQuit.connect(service.shutdown)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Gives Python an opportunity to dispatch Unix signals during Qt's loop.
    signals = QTimer(interval=1000)
    signals.timeout.connect(lambda: None)
    signals.start()
    app.exec()
    lock.close()


if __name__ == '__main__':
    main()
