"""Macro editing for the GUI; playback belongs exclusively to the service."""

from .. import settings
from ..runtime.macros import MacroEngine as _MacroEngine


class MacroEngine(_MacroEngine):
    def sync(self, restart=False):
        # Assignment and onboard editing still use MouseState's remote bridge.
        # The service reloads settings and receives all button events.
        pass
