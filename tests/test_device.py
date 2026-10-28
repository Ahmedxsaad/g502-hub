"""G502 device logic against a fake mouse (no hardware)."""

from contextlib import nullcontext

import pytest

from g502hub.device import G502, MODE_HOST, MODE_ONBOARD
from g502hub.hidpp import HidppError
from g502hub.onboard import Directory, DirEntry


class FakeG502(G502):
    """Answers like the G502 HERO: disabled slots can't be selected."""

    def __init__(self, enabled):
        self.directory = Directory([DirEntry(n, on) for n, on in enumerate(enabled, 1)])
        self.current, self.dpi_index, self.calls = 2, 1, []

    def exclusive(self, timeout=10.0):
        return nullcontext()

    def read_directory(self):
        return self.directory

    def get_current_profile(self):
        return self.current

    def get_current_dpi_index(self):
        return self.dpi_index

    def set_current_profile(self, sector):
        if not self.directory.entries[sector - 1].enabled:
            raise HidppError(0x02, 12, 3)
        self.calls.append(("profile", sector))
        self.current = sector

    def set_mode(self, mode):
        self.calls.append(("mode", mode))

    def set_current_dpi_index(self, index):
        self.calls.append(("dpi", index))

    def read_profile(self, sector):
        return type("P", (), {"dpi_levels": lambda self: [(0, 800), (1, 1600)]})()


def test_reload_hops_through_an_enabled_slot():
    dev = FakeG502([False, True, False, True, True])
    dev.reload_current_profile()
    assert dev.calls == [("profile", 4), ("profile", 2), ("dpi", 1)]


@pytest.mark.parametrize("enabled", [[False, True, False, False, False], [True]])
def test_reload_with_no_other_enabled_slot_leaves_host_mode(enabled):
    dev = FakeG502(enabled)
    dev.current = 1 if len(enabled) == 1 else 2
    dev.reload_current_profile(dpi_index=0)
    assert dev.calls == [("mode", MODE_HOST), ("mode", MODE_ONBOARD), ("dpi", 0)]
