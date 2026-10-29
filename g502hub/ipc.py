"""Private, versioned JSON protocol between the settings window and service.

No executable Python, pickle, arbitrary imports, or arbitrary device methods are
accepted. Only the current user's processes can access the runtime directory.
"""

import dataclasses
import json
import os
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

from . import context, device, onboard

VERSION = 1
MAX_MESSAGE = 1024 * 1024
DEVICE_METHODS = frozenset('''name firmware onboard_info get_mode set_mode
get_current_profile set_current_profile reload_current_profile get_current_dpi_index
set_current_dpi_index read_sector write_sector read_directory read_profile write_profile
dpi_range get_dpi set_dpi report_intervals get_report_interval set_report_interval
led_zones set_led set_led_software_control features'''.split())
TYPES = {c.__name__: c for module in (device, onboard, context)
         for c in vars(module).values() if isinstance(c, type) and dataclasses.is_dataclass(c)}


def runtime_dir():
    root = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/tmp/g502hub-{os.getuid()}') / 'g502-hub'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError(f'Unsafe service directory: {root}')
    return root


def socket_path():
    return str(runtime_dir() / 'service.sock')


def encode(value):
    if dataclasses.is_dataclass(value):
        return {'type': type(value).__name__, 'fields': {f.name: encode(getattr(value, f.name))
                for f in dataclasses.fields(value)}}
    if isinstance(value, bytes):
        return {'bytes': value.hex()}
    if isinstance(value, tuple):
        return {'tuple': [encode(v) for v in value]}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {'dict': [[encode(k), encode(v)] for k, v in value.items()]}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f'Unsupported IPC value: {type(value).__name__}')


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {'bytes'}:
        return bytes.fromhex(value['bytes'])
    if set(value) == {'tuple'}:
        return tuple(decode(v) for v in value['tuple'])
    if set(value) == {'dict'}:
        return {decode(k): decode(v) for k, v in value['dict']}
    if set(value) == {'type', 'fields'} and value['type'] in TYPES:
        return TYPES[value['type']](**{k: decode(v) for k, v in value['fields'].items()})
    raise ValueError('Unknown IPC value')


def request(command, *args, timeout=20, **kwargs):
    data = json.dumps({'version': VERSION, 'command': command,
                       'args': encode(args), 'kwargs': encode(kwargs)}).encode() + b'\n'
    if len(data) > MAX_MESSAGE:
        raise ValueError('Service request too large')
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(timeout)
        sock.connect(socket_path())
        sock.sendall(data)
        reply = bytearray()
        while b'\n' not in reply:
            chunk = sock.recv(65536)
            if not chunk:
                raise ConnectionError('Service closed without a reply')
            reply.extend(chunk)
            if len(reply) > MAX_MESSAGE:
                raise ValueError('Service response too large')
    result = json.loads(bytes(reply).split(b'\n', 1)[0])
    if 'error' in result:
        cls = {'DeviceNotFound': device.DeviceNotFound, 'NoPermission': device.NoPermission}.get(
            result.get('error_type'), RuntimeError)
        raise cls(result['error'])
    return decode(result['result'])


def ensure_service(timeout=15):
    try:
        request('ping', timeout=0.5)
        return
    except (OSError, ConnectionError):
        pass
    root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env['PYTHONPATH'] = str(root) + os.pathsep + env.get('PYTHONPATH', '')
    log = runtime_dir() / 'service.log'
    with log.open('ab') as output:
        proc = subprocess.Popen([sys.executable, '-m', 'g502hub.daemon'], env=env,
                                stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                start_new_session=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            request('ping', timeout=0.5)
            return
        except (OSError, ConnectionError):
            if proc.poll() not in (None, 0):
                raise RuntimeError(f'G502 Hub service failed; see {log}')
            time.sleep(0.05)
    raise TimeoutError(f'G502 Hub service did not start; see {log}')


class RemoteDevice:
    """The GUI's existing ordered worker talks to the service, never to hidraw."""

    def __init__(self):
        ensure_service()

    def close(self):
        pass

    def __getattr__(self, method):
        if method not in DEVICE_METHODS:
            raise AttributeError(method)
        return lambda *args, **kwargs: request('device', method, args, kwargs)
