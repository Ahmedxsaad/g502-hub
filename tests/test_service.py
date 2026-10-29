"""The real local protocol and process lifecycle, without touching USB hardware."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip('PySide6')
from g502hub import ipc, onboard
from g502hub.context import Context, Game, Media


def test_protocol_round_trips_domain_values():
    value = {1: (b'\0\xff', onboard.LedEffect.fixed((10, 20, 30))),
             'context': Context('app', 'title', 123, Game(10, 'game', 123, None),
                                (Media('p', 'id', 'title', '', '', '', 'Playing'),))}
    assert ipc.decode(json.loads(json.dumps(ipc.encode(value)))) == value
    with pytest.raises(ValueError):
        ipc.decode({'type': 'arbitrary.class', 'fields': {}})


FAKE_SERVICE = '''
import sys, time
from g502hub import daemon
from g502hub.device import DeviceNotFound
from g502hub.runtime.state import MouseState, Bridge
class Device:
    def close(self): pass
    def get_mode(self): raise DeviceNotFound('test mouse absent')
    def name(self): return 'test mouse'
    def set_led(self, zone, effect, persistence=0): return effect
    def features(self):
        return {m: m in sys.modules for m in ('PySide6.QtGui', 'PySide6.QtWidgets', 'numpy')}
    def get_dpi(self):
        time.sleep(0.1)
        return 800
    def write_sector(self, sector, data, allow_bad_crc=False):
        return (sector, data)
daemon.MouseState = lambda: MouseState(Bridge(device_factory=Device))
daemon.main()
'''


@pytest.fixture
def service(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    proc = subprocess.Popen([sys.executable, '-c', FAKE_SERVICE], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                ipc.request('ping', timeout=0.2)
                break
            except (OSError, ConnectionError):
                if proc.poll() is not None:
                    pytest.fail(proc.communicate()[1].decode())
                time.sleep(0.05)
        else:
            pytest.fail('service did not start')
        yield proc, env
    finally:
        if proc.poll() is None:
            ipc.request('stop')
        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 0, stderr.decode()
        assert b'Traceback' not in stderr, stderr.decode()


def test_real_service_rpc_and_single_instance(service):
    proc, env = service
    assert ipc.request('ping')['pid'] == proc.pid
    assert ipc.request('device', 'name', (), {}) == 'test mouse'
    effect = onboard.LedEffect.fixed((1, 2, 3))
    assert ipc.request('device', 'set_led', (0, effect), {}) == effect
    assert ipc.request('device', 'write_sector', (1, b'\0\xff'), {}) == (1, b'\0\xff')
    assert not any(ipc.request('device', 'features', (), {}).values())
    for method in ('__getattribute__', 'close', 'spy_start'):
        with pytest.raises(RuntimeError, match='not allowed'):
            ipc.request('device', method, (), {})
    with pytest.raises(RuntimeError, match='Incompatible'):
        # A different protocol version must never execute its command.
        with socket.socket(socket.AF_UNIX) as sock:
            sock.connect(ipc.socket_path())
            sock.sendall(b'{"version":999,"command":"stop"}\n')
            result = json.loads(sock.recv(10000))
            raise RuntimeError(result['error'])
    other = subprocess.run([sys.executable, '-c', FAKE_SERVICE], env=env, capture_output=True, timeout=10)
    assert other.returncode == 0, other.stderr
    assert ipc.request('ping')['pid'] == proc.pid
    # The UI can disappear before a pending worker call returns.
    with socket.socket(socket.AF_UNIX) as sock:
        sock.connect(ipc.socket_path())
        sock.sendall(json.dumps({'version':1, 'command':'device',
            'args':ipc.encode(('get_dpi', (), {})), 'kwargs':ipc.encode({})}).encode()+b'\n')
    time.sleep(0.2)
    assert ipc.request('ping')['pid'] == proc.pid


def test_graphical_process_exits_but_service_survives(service):
    proc, env = service
    ipc.request('lighting', 'start', ('wave',), {})
    script = '''
from PySide6.QtCore import QTimer
from g502hub.gui.app import MainWindow
from PySide6.QtWidgets import QApplication
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
window=MainWindow()
window.show()
QTimer.singleShot(400, window.close)
QTimer.singleShot(5000, lambda: app.exit(99))
app.exec()
'''
    ui = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, timeout=10)
    assert ui.returncode == 0, ui.stderr.decode()
    assert b'Traceback' not in ui.stderr, ui.stderr.decode()
    assert ipc.request('ping')['pid'] == proc.pid
    assert ipc.request('snapshot')['live_effect'] == 'wave'
    ipc.request('lighting', 'stop', (), {})
    # A legacy autostart entry must also return without constructing a UI.
    legacy = subprocess.run([sys.executable, '-m', 'g502hub.gui', '--tray'],
                            env=env, capture_output=True, timeout=10)
    assert legacy.returncode == 0, legacy.stderr.decode()
    assert ipc.request('ping')['pid'] == proc.pid


def test_private_runtime_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(tmp_path))
    path = tmp_path / 'g502-hub'
    path.mkdir(mode=0o755)
    with pytest.raises(PermissionError):
        ipc.runtime_dir()


def test_concurrent_settings_updates(tmp_path):
    script = '''
from pathlib import Path
import sys
from g502hub import settings
settings.PATH = Path(sys.argv[1])
settings.update(**{sys.argv[2]: True})
'''
    config = tmp_path / 'settings.json'
    processes = [subprocess.Popen([sys.executable, '-c', script, str(config), str(i)]) for i in range(8)]
    assert all(p.wait(timeout=10) == 0 for p in processes)
    assert json.loads(config.read_text()) == {str(i):True for i in range(8)}


def test_service_preserves_dpi_and_profile_osd(monkeypatch):
    from types import SimpleNamespace
    from g502hub import daemon
    from g502hub.gui import system
    messages = []
    monkeypatch.setattr(system, 'show_osd', messages.append)
    monkeypatch.setattr(daemon.settings, 'load', lambda: {})
    state = SimpleNamespace(active_slot=1, dpi_index=0,
                            profile=lambda: SimpleNamespace(name='Gaming', dpi=[400, 800]))
    service = SimpleNamespace(state=state)
    daemon.Service._dpi_changed(service)
    assert messages == []
    state.dpi_index = 1
    daemon.Service._dpi_changed(service)
    assert messages == ['800 DPI']
    state.active_slot = 2
    daemon.Service._dpi_changed(service)
    assert messages[-1] == 'Gaming  ·  slot 2'
    monkeypatch.setattr(daemon.settings, 'load', lambda: {'osd': False})
    state.dpi_index = 0
    daemon.Service._dpi_changed(service)
    assert len(messages) == 2
