"""Main window: top bar, navigation rail, mouse view and page panels."""

import subprocess
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QHBoxLayout, QLabel,
                               QMainWindow, QMenu, QStackedWidget, QSystemTrayIcon, QToolButton,
                               QVBoxLayout, QWidget)

from ..keylabels import KeyLabels
from . import theme
from .live import EFFECT_NAMES, LiveLighting
from .mouse_view import MouseView
from .pages.assignments import AssignmentsPage
from .pages.lighting import LightingPage
from .pages.profiles import ProfilesPage
from .pages.sensitivity import SensitivityPage
from .state import MouseState


class Placeholder(QWidget):
    def __init__(self):
        super().__init__()
        col = QVBoxLayout(self)
        col.addStretch()
        self.title = QLabel("Connect your G502 HERO")
        self.title.setObjectName("Title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.detail = QLabel("Looking for the mouse…")
        self.detail.setObjectName("Muted")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        col.addWidget(self.detail)
        col.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G502 Hub")
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self.state = MouseState()
        self.live = LiveLighting(self.state)
        self.keylabels = KeyLabels()
        self.view = MouseView()
        self._shown_slot = None
        self._resumed = False
        self._told_about_tray = False

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
        self.pages = [LightingPage(*args, self.live), AssignmentsPage(*args), SensitivityPage(*args),
                      ProfilesPage(*args)]

        rail = QWidget()
        rail.setObjectName("Rail")
        rail.setFixedWidth(92)
        rail_col = QVBoxLayout(rail)
        rail_col.setContentsMargins(0, 16, 0, 16)
        rail_col.setSpacing(4)
        self.rail_group = QButtonGroup(self)
        for i, page in enumerate(self.pages):
            b = QToolButton()
            b.setObjectName("RailButton")
            b.setText(page.title)
            b.setIcon(theme.icon(page.icon))
            b.setIconSize(QSize(24, 24))
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFixedWidth(92)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.rail_group.addButton(b, i)
            rail_col.addWidget(b)
        rail_col.addStretch()
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
        self.subtitle = QLabel("ONBOARD MEMORY")
        self.subtitle.setObjectName("Heading")
        titles.addWidget(self.subtitle)
        row.addLayout(titles, 1)
        self.profile_box = QComboBox()
        self.profile_box.setObjectName("ProfileBox")
        self.profile_box.setMinimumWidth(280)
        self.profile_box.setToolTip("Active onboard profile")
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
        self.live_dpi.setToolTip("Current DPI on the mouse")
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

    def _active_changed(self):
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

    def _fill_profile_box(self):
        s = self.state
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        for n, profile in enumerate(s.profiles, 1):
            self.profile_box.addItem(f"PROFILE {n}:  {(profile.name or f'Profile {n}').upper()}")
        if s.active_slot:
            self.profile_box.setCurrentIndex(s.active_slot - 1)
        self.profile_box.blockSignals(False)
        if s.active_slot:
            self.subtitle.setText(f"ONBOARD MEMORY  ·  SLOT {s.active_slot}")
        profile = s.profile()
        levels = [slot for slot, _ in profile.dpi_levels()] if profile else []
        if profile and s.dpi_index in levels:
            self.live_dpi.setText(f"{profile.dpi[s.dpi_index]} DPI   ·   LEVEL {levels.index(s.dpi_index) + 1}/{len(levels)}")
        self.live_dpi.setVisible(bool(profile and s.dpi_index in levels))

    def _warn_ratbagd(self):
        try:
            running = subprocess.run(["pgrep", "-x", "ratbagd"], capture_output=True).returncode == 0
        except OSError:
            running = False
        if running:
            self._status("error", "ratbagd (Piper) is running and may overwrite your G-Shift layer. "
                                  "Close Piper / stop ratbagd.")

    # ------------------------------------------------------------ tray

    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(QIcon.fromTheme("input-mouse", theme.icon("assignments")), self)
        tray.setToolTip("G502 Hub")
        menu = QMenu(self)
        menu.addAction("Open G502 Hub", self._show_window)
        menu.addSeparator()
        self.tray_live = QAction("Live lighting", self, checkable=True)
        self.tray_live.toggled.connect(self._tray_live_toggled)
        menu.addAction(self.tray_live)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
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
            self.tray_live.setText(f"Live lighting: {EFFECT_NAMES[self.live.selected]}")
            self.tray.setToolTip(f"G502 Hub · {EFFECT_NAMES[self.live.effect]} on" if running else "G502 Hub")

    def quit(self):
        self.live.stop(remember=False)  # the saved lighting comes back; resumes next start
        self.state.shutdown()
        QApplication.quit()

    def closeEvent(self, e):
        if self.live.running and self.tray is not None:
            # Keep the live effect going from the tray
            e.ignore()
            self.hide()
            if not self._told_about_tray:
                self._told_about_tray = True
                self.tray.showMessage("G502 Hub", f"{EFFECT_NAMES[self.live.effect]} keeps running in the "
                                      "tray. Quit from the tray menu to stop it.", QSystemTrayIcon.MessageIcon.Information, 4000)
            return
        self.quit()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("G502 Hub")
    app.setDesktopFileName("g502-hub")
    app.setQuitOnLastWindowClosed(False)  # the tray keeps live effects running
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
