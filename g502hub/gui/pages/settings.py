"""SETTINGS page: startup, on-screen popups, mouse picture, device access, game integrations."""

import os

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ... import settings
from .. import photo, system
from ..widgets import heading, muted
from . import Page


class SettingsPage(Page):
    title = "SETTINGS"
    icon = "settings"
    mouse_mode = "plain"

    def __init__(self, *args):
        super().__init__(*args)
        title = QLabel("Settings")
        title.setObjectName("Title")
        self.layout.addWidget(title)

        self.layout.addWidget(heading("Startup"))
        self.autostart = QCheckBox("Start G502 Hub in the background when I log in")
        self.autostart.setChecked(system.autostart_enabled())
        self.autostart.toggled.connect(system.set_autostart)
        self.layout.addWidget(self.autostart)
        self.layout.addWidget(muted("Closing this window frees the settings interface. Macros, game rules, "
                                    "live lighting and the DPI popup continue in the background.", "Faint"))

        self.stop_background = QPushButton("Quit G502 Hub completely")
        self.stop_background.setToolTip("Stops background macros, game rules and live lighting too")
        self.layout.addWidget(self.stop_background)

        self.layout.addWidget(heading("On-screen popup"))
        self.osd = QCheckBox("Show DPI and profile changes on screen")
        self.osd.setChecked(settings.load().get("osd", True))
        self.osd.toggled.connect(lambda on: settings.update(osd=on))
        self.layout.addWidget(self.osd)

        self.layout.addWidget(heading("Mouse picture"))
        self.picture = muted("")
        self.layout.addWidget(self.picture)
        row = QHBoxLayout()
        self.picture_btn = QPushButton()
        self.picture_btn.clicked.connect(self._toggle_photo)
        row.addWidget(self.picture_btn)
        row.addStretch()
        self.layout.addLayout(row)
        self.view.photoChanged.connect(self.refresh)

        self.layout.addWidget(heading("Device access"))
        self.access = muted("")
        self.layout.addWidget(self.access)
        self.fix_btn = QPushButton("Allow access (asks for your password)")
        self.fix_btn.clicked.connect(self._fix_access)
        self.layout.addWidget(self.fix_btn)
        self._fix = system.PermissionFix()
        self._fix.finished.connect(self._fixed)

        self.layout.addWidget(heading("Game integrations"))
        self.layout.addWidget(muted("Used by rules with “Game-driven” lighting (Games & apps).", "Faint"))
        self.gsi_status = muted("")
        self.layout.addWidget(self.gsi_status)
        row = QHBoxLayout()
        self.gsi_btn = QPushButton()
        self.gsi_btn.clicked.connect(self._toggle_gsi)
        row.addWidget(self.gsi_btn)
        row.addStretch()
        self.layout.addLayout(row)
        self.gsi_note = muted("Restart the game after setting this up. Dota 2 also needs "
                              "-gamestateintegration in its Steam launch options.", "Faint")
        self.layout.addWidget(self.gsi_note)

        self.layout.addWidget(heading("LIGHTSYNC bridge for Proton games"))
        self.layout.addWidget(muted("Windows games with Logitech lighting (like Uncharted, The Last of "
                                    "Us or GTA V) can drive the mouse through Proton, like with G HUB on "
                                    "Windows. Turn it on per game; it adds a small LogitechLed.dll to that "
                                    "game's Proton prefix, nothing in the game itself.", "Faint"))
        self.bridge = QWidget()
        self.bridge_col = QVBoxLayout(self.bridge)
        self.bridge_col.setContentsMargins(0, 0, 0, 0)
        self.bridge_col.setSpacing(6)
        self.layout.addWidget(self.bridge)
        self.layout.addStretch()

    def refresh(self):
        ready = self.view.skin.ready
        self.picture.setText(
            "Logitech's product photo of the G502 HERO. It's their image, so G502 Hub doesn't include it: "
            "it was downloaded from logitechg.com the first time the app started, and is kept in "
            f"{photo.PHOTO_PATH.parent}." if ready else self.view.skin.message)
        self.picture_btn.setText("Downloading…" if self.view.fetcher.busy else "Download it again")
        self.picture_btn.setEnabled(not self.view.fetcher.busy)
        rule = system.udev_rule_status()
        if rule == "old" and os.access("/dev/uinput", os.W_OK):
            rule = "current"  # the old rule covers the mouse, and Steam's rule already opens uinput
        self.access.setText({
            "current": "Your user can configure the mouse without root.",
            "old": "The permission rule is from an older version. Update it so macros run by the app "
                   "can always type.",
            "missing": "The permission rule isn't installed, so the app can't open the mouse.",
        }[rule])
        self.fix_btn.setText("Update the rule (asks for your password)" if rule == "old" else
                             "Allow access (asks for your password)")
        self.fix_btn.setVisible(rule != "current")
        self._show_games()
        self._show_bridge()

    # ------------------------------------------------------------ game integrations

    def _show_games(self):
        from ...effects import gsi
        games = gsi.installed_games()
        done = gsi.configs_installed()
        names = {"cs2": "Counter-Strike 2", "dota2": "Dota 2"}
        if not games:
            self.gsi_status.setText("CS2 and Dota 2 live lighting: neither game is installed.")
            self.gsi_btn.hide()
            self.gsi_note.hide()
            return
        state = ", ".join(f"{names[g]} {'✓ set up' if done.get(g) else 'not set up'}" for g in games)
        self.gsi_status.setText(f"CS2 and Dota 2 live lighting: {state}.")
        any_done = any(done.get(g) for g in games)
        self.gsi_btn.setText("Remove CS2 / Dota 2 setup" if any_done else "Set up CS2 / Dota 2 lighting")
        self.gsi_btn.show()
        self.gsi_note.setVisible("dota2" in games or not any_done)

    def _toggle_gsi(self):
        from ...effects import gsi
        try:
            if any(gsi.configs_installed().values()):
                gsi.uninstall_configs()
            else:
                gsi.install_configs()
        except OSError as e:
            self.gsi_status.setText(f"Couldn't change the game config: {e}")
            return
        self._show_games()

    def _show_bridge(self):
        while self.bridge_col.count():
            item = self.bridge_col.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            from ... import lightsync_bridge as bridge
            prefixes = bridge.steam_prefixes()
        except Exception as e:  # not built yet, or an unreadable Steam folder
            self.bridge_col.addWidget(muted(f"Not available: {e}", "Faint"))
            return
        if not prefixes:
            self.bridge_col.addWidget(muted("No Proton games found yet. Run a Windows game through "
                                            "Steam once, then come back here.", "Faint"))
            return
        built = all((bridge.BIN_DIR / arch / bridge.DLL).exists() for arch in ("x64", "x86"))
        if not built:
            self.bridge_col.addWidget(muted("The bridge DLL isn't built in this copy yet: install lld "
                                            "(sudo pacman -S lld) and run bridge/logitechled/build.sh.",
                                            "Faint"))
        for appid, name, pfx in prefixes:
            row = QHBoxLayout()
            row.addWidget(QLabel(name), 1)
            on = bridge.is_installed(pfx)
            b = QPushButton("Turn off" if on else "Turn on")
            b.setObjectName("" if on else "Primary")
            b.clicked.connect(lambda _=False, p=pfx, n=name: self._toggle_bridge(p, n))
            b.setEnabled(built or on)
            row.addWidget(b)
            holder = QWidget()
            holder.setLayout(row)
            self.bridge_col.addWidget(holder)

    def _toggle_bridge(self, pfx, name):
        from ... import lightsync_bridge as bridge
        try:
            if bridge.is_installed(pfx):
                bridge.uninstall(pfx)
            else:
                bridge.install(pfx)
        except Exception as e:  # game running (prefix busy), missing DLLs, disk errors
            self.bridge_col.addWidget(muted(f"{name}: {e}", "Faint"))
            return
        self._show_bridge()

    def _toggle_photo(self):
        self.view.fetch_photo()
        self.refresh()

    def _fix_access(self):
        self.fix_btn.setEnabled(False)
        self._fix.start()

    def _fixed(self, ok, message):
        self.fix_btn.setEnabled(True)
        self.access.setText(message)
        if ok:
            self.fix_btn.hide()
            self.state.load()
