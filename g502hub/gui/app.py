"""Main window: top bar, navigation rail, mouse view and page panels."""

import os
import subprocess
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QHBoxLayout, QLabel,
                               QMainWindow, QMenu, QPushButton, QStackedWidget, QSystemTrayIcon,
                               QToolButton, QVBoxLayout, QWidget)

from .. import settings
from ..keylabels import KeyLabels
from . import system, theme
from .i18n import setup_translation
from .live import LiveLighting, effect_name
from .macro_engine import MacroEngine
from .mouse_view import MouseView
from .pages.about import AboutPage
from .pages.assignments import AssignmentsPage
from .pages.games import GamesPage
from .pages.lighting import LightingPage
from .pages.macros import MacrosPage
from .pages.profiles import ProfilesPage
from .pages.sensitivity import SensitivityPage
from .pages.settings import SettingsPage
from .rules_engine import RulesEngine
from .state import MouseState


class Placeholder(QWidget):
    def __init__(self):
        super().__init__()
        col = QVBoxLayout(self)
        col.addStretch()
        self.title = QLabel(self.tr("Connect your G502 HERO"))
        self.title.setObjectName("Title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.detail = QLabel(self.tr("Looking for the mouse…"))
        self.detail.setObjectName("Muted")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        col.addWidget(self.detail)
        col.addSpacing(12)
        self.fix = QPushButton(self.tr("Allow access (asks for your password)"))
        self.fix.setObjectName("Primary")
        self.fix.hide()
        col.addWidget(self.fix, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G502 Hub")
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self.state = MouseState()
        self.live = LiveLighting(self.state)
        self.rules = RulesEngine(self.state, self.live)
        self.keylabels = KeyLabels()
        self.macros = MacroEngine(self.state, self.keylabels)
        self.view = MouseView()
        self._shown_slot = None
        self._resumed = False

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._top_bar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        col.addLayout(body, 1)

        args = (self.state, self.view, self.keylabels)
        self.pages = [LightingPage(*args, self.live), AssignmentsPage(*args, self.macros), SensitivityPage(*args),
                      ProfilesPage(*args), MacrosPage(*args, self.macros), GamesPage(*args, self.rules),
                      SettingsPage(*args), AboutPage(*args)]
        bottom = {SettingsPage, AboutPage}  # pinned to the bottom of the rail, like G HUB's gear

        rail = QWidget()
        rail.setObjectName("Rail")
        rail.setFixedWidth(92)
        rail_col = QVBoxLayout(rail)
        rail_col.setContentsMargins(0, 16, 0, 16)
        rail_col.setSpacing(4)
        self.rail_group = QButtonGroup(self)
        bottom_buttons = []
        for i, page in enumerate(self.pages):
            b = QToolButton()
            b.setObjectName("RailButton")
            b.setText(page.title.replace("&", "&&"))  # a lone & would mark a shortcut key
            b.setIcon(theme.icon(page.icon))
            b.setIconSize(QSize(24, 24))
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFixedWidth(92)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.rail_group.addButton(b, i)
            if type(page) in bottom:
                bottom_buttons.append(b)
            else:
                rail_col.addWidget(b)
        rail_col.addStretch()
        for b in bottom_buttons:
            rail_col.addWidget(b)
        body.addWidget(rail)

        # G HUB layout: section rail, then the settings panel, then the device
        self.side = QStackedWidget()
        self.side.setObjectName("SidePanel")
        self.side.setFixedWidth(410)
        for page in self.pages:
            self.side.addWidget(page.panel)
        body.addWidget(self.side)

        self.placeholder = Placeholder()
        self.center = QStackedWidget()
        self.center.setObjectName("Stage")
        self.center.addWidget(self.placeholder)
        self.center.addWidget(self.view)
        for page in self.pages:
            if page.center is not None:
                self.center.addWidget(page.center)
        body.addWidget(self.center, 1)

        self.rail_group.idClicked.connect(self.show_page)
        self.view.clicked.connect(lambda key: self.page.on_view_click(key))
        self.state.loaded.connect(self._loaded)
        self.state.activeChanged.connect(self._active_changed)
        self.state.profileEdited.connect(self._profile_edited)
        self.state.status.connect(self._status)
        self.state.connectedChanged.connect(self._connected)
        self.live.colors.connect(self.view.set_live)
        self.live.status.connect(self._status)
        self.live.runningChanged.connect(self._live_changed)
        self.tray = self._make_tray()
        self.rules.start()
        self.placeholder.fix.clicked.connect(self._fix_permissions)
        macros_page = next(i for i, p in enumerate(self.pages) if isinstance(p, MacrosPage))
        self.pages[1].open_macros = lambda: self.rail_group.button(macros_page).click()
        next(p for p in self.pages if isinstance(p, SettingsPage)).restart_app = self.restart
        self.restarting = False
        self.rail_group.button(0).setChecked(True)
        self.show_page(0)
        self._connected(False)
        self.state.start()
        self._warn_ratbagd()

    def _top_bar(self):
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(64)
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 0, 24, 0)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel("G502 HERO")
        name.setFont(theme.font(15, QFont.Weight.Bold))
        titles.addWidget(name)
        self.subtitle = QLabel(self.tr("ONBOARD MEMORY"))
        self.subtitle.setObjectName("Heading")
        titles.addWidget(self.subtitle)
        row.addLayout(titles, 1)
        self.profile_box = QComboBox()
        self.profile_box.setObjectName("ProfileBox")
        self.profile_box.setMinimumWidth(280)
        self.profile_box.setToolTip(self.tr("Active onboard profile"))
        self.profile_box.activated.connect(lambda i: self.state.activate(i + 1))
        row.addWidget(self.profile_box)
        right = QHBoxLayout()
        right.setSpacing(14)
        right.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("Status")
        right.addWidget(self.status_label)
        self.live_dpi = QLabel()
        self.live_dpi.setObjectName("LiveDpi")
        self.live_dpi.setToolTip(self.tr("Current DPI on the mouse"))
        self.live_dpi.setFixedHeight(28)
        self.live_dpi.hide()
        right.addWidget(self.live_dpi, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(right, 1)
        return bar

    @property
    def page(self):
        return self.pages[self.side.currentIndex()]

    def show_page(self, i):
        self.side.setCurrentIndex(i)
        self._sync_center()
        if self.state.connected:
            self.page.activate()

    def _sync_center(self):
        if not self.state.connected:
            self.center.setCurrentWidget(self.placeholder)
        else:
            self.center.setCurrentWidget(self.page.center or self.view)

    # ------------------------------------------------------------ state signals

    def _loaded(self):
        self._fill_profile_box()
        self._shown_slot = self.state.active_slot
        self._sync_center()
        self.page.activate()
        if not self._resumed:
            self._resumed = True
            self.live.resume()
            self.macros.sync()

    def _active_changed(self):
        self._show_osd()
        self._fill_profile_box()
        if self.state.active_slot != self._shown_slot:
            self._shown_slot = self.state.active_slot
            self.page.reset()
        else:
            self.page.refresh()

    def _profile_edited(self, slot):
        if slot == self.state.active_slot or isinstance(self.page, ProfilesPage):
            self.page.refresh()
        self._fill_profile_box()

    def _connected(self, connected):
        self.side.setEnabled(connected)
        self.profile_box.setEnabled(connected)
        self._sync_center()

    def _status(self, kind, text):
        self.status_label.setText(text)
        self.status_label.setProperty("kind", kind)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if not self.state.connected:
            self.placeholder.detail.setText(text)
            self.placeholder.fix.setVisible(self.state.no_permission)

    def _fill_profile_box(self):
        s = self.state
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        for n, profile in enumerate(s.profiles, 1):
            name = (profile.name or self.tr("Profile {n}").format(n=n)).upper()
            self.profile_box.addItem(self.tr("PROFILE {n}:  {name}").format(n=n, name=name))
        if s.active_slot:
            self.profile_box.setCurrentIndex(s.active_slot - 1)
        self.profile_box.blockSignals(False)
        if s.active_slot:
            self.subtitle.setText(self.tr("ONBOARD MEMORY  ·  SLOT {slot}").format(slot=s.active_slot))
        profile = s.profile()
        levels = [slot for slot, _ in profile.dpi_levels()] if profile else []
        if profile and s.dpi_index in levels:
            live_text = self.tr("{dpi} DPI   ·   LEVEL {level}/{total}").format(
                dpi=profile.dpi[s.dpi_index], level=levels.index(s.dpi_index) + 1, total=len(levels))
            self.live_dpi.setText(live_text)
        self.live_dpi.setVisible(bool(profile and s.dpi_index in levels))

    def _warn_ratbagd(self):
        try:
            running = subprocess.run(["pgrep", "-x", "ratbagd"], capture_output=True).returncode == 0
        except OSError:
            running = False
        if running:
            self._status("error", self.tr("ratbagd (Piper) is running and may overwrite your G-Shift layer. "
                                          "Close Piper / stop ratbagd."))

    def _show_osd(self):
        """Popup on DPI or profile changes, like G HUB's."""
        s = self.state
        now = (s.active_slot, s.dpi_index)
        before, self._osd_seen = getattr(self, "_osd_seen", None), now
        if before is None or before == now or not settings.load().get("osd", True):
            return
        profile = s.profile()
        if now[0] != before[0]:
            name = profile.name if profile and profile.name else self.tr("Profile {slot}").format(slot=now[0])
            system.show_osd(self.tr("{name}  ·  slot {slot}").format(name=name, slot=now[0]))
        elif profile and now[1] is not None and now[1] < 5 and profile.dpi[now[1]]:
            system.show_osd(f"{profile.dpi[now[1]]} DPI")

    def _fix_permissions(self):
        self.placeholder.fix.setEnabled(False)
        self._permission_fix = system.PermissionFix(self)
        self._permission_fix.finished.connect(self._permissions_fixed)
        self._permission_fix.start()

    def _permissions_fixed(self, ok, message):
        self.placeholder.fix.setEnabled(True)
        self.placeholder.detail.setText(message)
        if ok:
            self.placeholder.fix.hide()
            self.state.load()

    # ------------------------------------------------------------ tray

    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(QIcon.fromTheme("input-mouse", theme.icon("assignments")), self)
        tray.setToolTip("G502 Hub")
        menu = QMenu(self)
        menu.addAction(self.tr("Open G502 Hub"), self._show_window)
        menu.addSeparator()
        self.tray_live = QAction(self.tr("Live lighting"), self, checkable=True)
        self.tray_live.toggled.connect(self._tray_live_toggled)
        menu.addAction(self.tray_live)
        menu.addSeparator()
        menu.addAction(self.tr("Quit"), self.quit)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self._show_window()
                               if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        return tray

    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _tray_live_toggled(self, on):
        if on and not self.live.running:
            self.live.start()
        elif not on and self.live.running:
            self.live.stop()

    def _live_changed(self, running):
        if self.tray is not None:
            self.tray_live.blockSignals(True)
            self.tray_live.setChecked(running)
            self.tray_live.blockSignals(False)
            self.tray_live.setText(self.tr("Live lighting: {effect}").format(effect=effect_name(self.live.selected)))
            self.tray.setToolTip(self.tr("G502 Hub · {effect} on").format(effect=effect_name(self.live.effect)) if running else "G502 Hub")

    def quit(self):
        self.rules.stop()
        self.macros.shutdown()
        self.live.shutdown()  # the saved lighting comes back; a live effect resumes next start
        self.state.shutdown()
        QApplication.quit()

    def restart(self):
        """Quit, and have main() start a new copy (to show another language)."""
        self.restarting = True
        self.quit()

    def closeEvent(self, e):
        prefs = settings.load()
        if self.tray is not None and prefs.get("close_to_tray", True):
            # Keep rules, app macros, live lighting and the DPI popup going from the tray
            e.ignore()
            self.hide()
            if not prefs.get("tray_hint_shown"):
                settings.update(tray_hint_shown=True)
                self.tray.showMessage("G502 Hub", self.tr("G502 Hub keeps running in the tray. Quit it from the "
                                                          "tray menu."), QSystemTrayIcon.MessageIcon.Information, 4000)
            return
        self.quit()
        super().closeEvent(e)


INSTANCE = f"g502-hub-{os.getuid()}"


def _hand_over(message):
    """If G502 Hub is already running, pass it the message and return True."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE)
    if not sock.waitForConnected(500):
        return False
    sock.write(message)
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def _listen(window):
    """Bring the window up when G502 Hub is started again (one copy talks to the mouse)."""
    QLocalServer.removeServer(INSTANCE)  # left behind by a crash
    server = QLocalServer(window)

    def connected():
        sock = server.nextPendingConnection()

        def read():
            if bytes(sock.readAll()).strip() == b"show":
                window._show_window()
        sock.readyRead.connect(read)
    server.newConnection.connect(connected)
    server.listen(INSTANCE)
    return server


def main():
    app = QApplication(sys.argv)
    tray_only = "--tray" in sys.argv[1:]
    if _hand_over(b"tray" if tray_only else b"show"):
        sys.exit(0)
    setup_translation(app)
    app.setApplicationName("G502 Hub")
    app.setDesktopFileName("g502-hub")
    app.setQuitOnLastWindowClosed(False)  # the tray keeps live effects running
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.STYLESHEET)
    window = MainWindow()
    window._instance_server = _listen(window)
    if not (tray_only and window.tray is not None):
        window.show()
    code = app.exec()
    if window.restarting:
        # Everything is shut down and the mouse released; replace this process with a new copy
        cmd = system.launch_command()
        os.execvp(cmd[0], cmd)
    sys.exit(code)
