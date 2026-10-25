#!/usr/bin/env python3
"""Take the README / website screenshots in a demo setup.

    QT_QPA_PLATFORM=offscreen tools/screenshots.py

Needs the mouse plugged in (the pages show its real profiles), but never
changes it: LED writes are switched off and the rules use made-up activity.
Settings go to a throwaway folder. Every page is saved as the full window in
docs/screenshots/ (for the README). For the website, pages that show the mouse
are saved as just the rail and settings panel (website/screenshots/NAME-panel.webp),
shown there next to Logitech's photo loaded live from logitechg.com, and pages
without the mouse as the full window.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="g502hub-shots-")
os.environ.setdefault("QT_SCALE_FACTOR", "2")

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from g502hub import context, device, settings  # noqa: E402
from g502hub.rules import Rule  # noqa: E402

FULL = ROOT / "docs" / "screenshots"
SITE = ROOT / "website" / "screenshots"

device.G502.set_led = lambda self, *a, **k: None  # screenshots never touch the lights

DEMO = context.Context(
    app="firefox", title="lofi hip hop radio 📚 beats to relax/study to - YouTube — Mozilla Firefox", pid=None,
    game=None, media=(context.Media(player="plasma-browser-integration", identity="Firefox",
                                    title="lofi hip hop radio 📚 beats to relax/study to", artist="Lofi Girl",
                                    album="", url="https://www.youtube.com/watch?v=jfKfPfyJRdk",
                                    status="Playing"),))


IDLE = context.Context(app="firefox", title="Mozilla Firefox", pid=None, game=None, media=())
NOW = [IDLE]  # what the demo "is doing" for the current shot


class DemoWatcher:
    errors = {}

    def start(self):
        pass

    def stop(self):
        pass

    def current(self):
        return NOW[0]


context.ContextWatcher = DemoWatcher
settings.update(rules=[
    Rule("YouTube", "media", "youtube", lighting="color", color="#ff1e1e").to_dict(),
    Rule("Anime night", "media", "one piece", lighting="breathing", color="#ff8a00").to_dict(),
    Rule("Any Steam game", "game", "any", lighting="art", slot=1).to_dict(),
    Rule("Counter-Strike 2", "game", "730", lighting="game").to_dict(),
], live={"effect": "screen", "on": False}, colors=["#ff2d95", "#7c4dff", "#00e5ff"])

from g502hub.gui import theme  # noqa: E402
from g502hub.gui.app import MainWindow  # noqa: E402

app = QApplication(sys.argv[:1])
app.setStyle("Fusion")
app.setPalette(theme.palette())
app.setStyleSheet(theme.STYLESHEET)
w = MainWindow()
w.resize(1280, 800)
w.show()
FULL.mkdir(parents=True, exist_ok=True)
SITE.mkdir(parents=True, exist_ok=True)
NEON = {0: QColor("#ff2d95"), 1: QColor("#00e5ff")}


def shots():
    page = {type(p).__name__: i for i, p in enumerate(w.pages)}
    lp = w.pages[page["LightingPage"]]
    yield "lighting-live", lambda: (w.rail_group.button(page["LightingPage"]).click(), lp.mode.group.button(1).click(),
                                    lp.live_effects.set_value("screen"), lp._live_selected("screen"),
                                    w.view.set_live(NEON), lp.live_toggle.setText("Turn off"),
                                    lp.live_toggle.setObjectName(""), lp.live_toggle.style().polish(lp.live_toggle))
    yield "lighting", lambda: (lp.mode.group.button(0).click(), lp.stack.setCurrentIndex(0), w.view.set_live({}))
    yield "games", lambda: (NOW.__setitem__(0, DEMO), w.rail_group.button(page["GamesPage"]).click())
    yield "sensitivity", lambda: (NOW.__setitem__(0, IDLE), w.rail_group.button(page["SensitivityPage"]).click())
    yield "assignments", lambda: w.rail_group.button(page["AssignmentsPage"]).click()
    yield "profiles", lambda: w.rail_group.button(page["ProfilesPage"]).click()
    yield "about", lambda: w.rail_group.button(page["AboutPage"]).click()


def run(it=None, wait=0):
    if not (w.state.connected and w.state.profiles):
        if wait > 60:
            sys.exit("The mouse isn't connected; plug it in and try again.")
        QTimer.singleShot(250, lambda: run(it, wait + 1))
        return
    it = it or shots()
    try:
        name, action = next(it)
    except StopIteration:
        w.quit()
        return
    action()

    def save():
        image = w.grab().toImage()
        full = image.scaledToWidth(1920, Qt.TransformationMode.SmoothTransformation)
        full.save(str(FULL / f"{name}.webp"), "WEBP", 88)
        print(f"saved {FULL / name}.webp")
        if w.center.currentWidget() is w.view:
            # The rail and settings panel alone: the website puts Logitech's photo next to it, live
            ratio = image.devicePixelRatio()
            panel = w.side.geometry().right() + 1
            crop = image.copy(0, round(64 * ratio), round(panel * ratio), round((w.height() - 64) * ratio))
            crop.save(str(SITE / f"{name}-panel.webp"), "WEBP", 88)
            print(f"saved {SITE / name}-panel.webp")
        else:
            full.save(str(SITE / f"{name}.webp"), "WEBP", 88)
            print(f"saved {SITE / name}.webp")
        run(it)
    QTimer.singleShot(900, save)


QTimer.singleShot(300, run)
app.exec()
