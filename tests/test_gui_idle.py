"""Background work must sleep without losing input or visible animations."""

import os
import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from g502hub import macros
from g502hub.effects import macroplayer, spy
from g502hub.runtime import macros as macro_engine
from g502hub.gui import mouse_view
from g502hub.onboard import LedEffect


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert predicate()


@pytest.mark.parametrize("mode", ["once", "while-held", "toggle"])
def test_button_events_reach_macro_player_on_gui_thread(app, monkeypatch, mode):
    """A press and release arriving together survive the reader/Qt handoff."""
    monkeypatch.setattr(macro_engine.settings, "load", lambda: {})
    calls = []

    class State(QObject):
        connectedChanged = Signal(bool)
        active_slot = 1
        profile = lambda self: None

    class Player:
        def press(self, *args):
            calls.append(("press", args, QThread.currentThread()))

        def release(self, *args):
            calls.append(("release", args, QThread.currentThread()))

        def stop_all(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(macroplayer, "MacroPlayer", Player)
    monkeypatch.setattr(macros, "expand", lambda macro, typing: ["events"])
    r, w = os.pipe()
    real_spy = spy.ButtonSpy
    monkeypatch.setattr(spy, "ButtonSpy", lambda *args, **kw: real_spy(*args, fd=r, **kw))
    state = State()
    state.bridge = SimpleNamespace(call=lambda job, done=None: done((None, 9), None) if done else None)
    state.connected = False
    engine = macro_engine.MacroEngine(state, SimpleNamespace(typing=None))
    engine.macros = [SimpleNamespace(id="test", mode=mode)]
    engine.app_buttons = {"1:0:0": "test"}
    try:
        engine._start()
        # Idle must not dispatch repeated button checks.
        notifications = []
        engine._buttons_changed.connect(lambda: notifications.append(True))
        app.processEvents()
        assert calls == [] and notifications == []
        frame = lambda mask: bytes([0x10, 0xFF, 9, 0]) + mask.to_bytes(2, "big") + b"\0"
        os.write(w, frame(1) + frame(1) + frame(0))
        wait_for(app, lambda: len(calls) == 3)
        assert [(name, args) for name, args, _ in calls] == [
            ("press", ((1, 0, 0), ["events"], mode)),
            ("release", ((1, 0, 0),)),
            ("release", ((1, 1, 0),)),
        ]
        assert all(thread == app.thread() for _, _, thread in calls)
        engine._stop()
        engine._buttons_changed.emit()  # late notification after disconnect
        app.processEvents()
        assert len(calls) == 3
    finally:
        engine.shutdown()
        os.close(r)
        os.close(w)


def test_spy_notifies_only_on_changes():
    r, w = os.pipe()
    notified = threading.Event()
    observed = []
    reader = spy.ButtonSpy(None, 9, fd=r, on_change=lambda: (observed.extend(reader.changes()), notified.set()))
    reader.start()
    frame = lambda mask: bytes([0x10, 0xFF, 9, 0]) + mask.to_bytes(2, "big") + b"\0"
    try:
        os.write(w, frame(1))
        assert notified.wait(2)
        assert observed == [(0, 1)]
        notified.clear()
        os.write(w, frame(1))
        assert not notified.wait(0.1)
        os.write(w, frame(0))
        assert notified.wait(2)
        assert observed == [(0, 1), (1, 0)]
    finally:
        reader.stop()
        os.close(r)
        os.close(w)


def test_preview_animation_follows_visibility_and_live_overrides(app, monkeypatch):
    monkeypatch.setattr(mouse_view, "load_image", lambda: QImage(618, 1110, QImage.Format.Format_ARGB32))
    parent = QWidget()
    view = mouse_view.MouseView(parent)
    try:
        view.set_leds({0: LedEffect(effect=0x03)})
        assert not view._timer.isActive()
        parent.show()
        app.processEvents()
        assert view._timer.isActive()
        parent.hide()  # exactly what closing to the tray does
        assert not view._timer.isActive()
        view.set_leds({0: LedEffect(effect=0x0A)})
        assert not view._timer.isActive()
        parent.show()
        assert view._timer.isActive()
        view.set_live({0: QColor("red")})
        assert not view._timer.isActive()
        view.set_live({})
        assert view._timer.isActive()
        view.set_leds({0: LedEffect(effect=0x01)})
        assert not view._timer.isActive()
    finally:
        parent.close()
