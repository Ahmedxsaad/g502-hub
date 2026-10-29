"""Editable UI cache. All device operations go through the background service."""

from ..ipc import RemoteDevice
from ..runtime.state import Bridge, MouseState as _MouseState, POLL_MS, RECONNECT_MS, SAVE_DELAY_MS


class MouseState(_MouseState):
    def __init__(self):
        super().__init__(bridge=Bridge(device_factory=RemoteDevice))
