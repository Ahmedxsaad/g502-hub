"""SETTINGS page: startup, on-screen popups, mouse picture, device access, game integrations."""

import os

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ... import settings
from .. import photo, system
from ..i18n import AVAILABLE_LANGUAGES, get_current_language
from ..widgets import heading, muted
from . import Page


class SettingsPage(Page):
    icon = "settings"
    mouse_mode = "plain"

    @property
    def title(self):
        return self.tr("SETTINGS")

    def __init__(self, *args):
        super().__init__(*args)
        title = QLabel(self.tr("Settings"))
        title.setObjectName("Title")
        self.layout.addWidget(title)

        # Language selection
        self.layout.addWidget(heading(self.tr("Language")))
        self.lang_box = QComboBox()
        for code, label in AVAILABLE_LANGUAGES.items():
            self.lang_box.addItem(label, code)
        cur_lang = get_current_language()
        idx = self.lang_box.findData(cur_lang)
        if idx >= 0:
            self.lang_box.setCurrentIndex(idx)
        self.lang_box.currentIndexChanged.connect(self._lang_changed)
        self.layout.addWidget(self.lang_box)
        self.lang_hint = muted(self.tr("Restart required. Please quit G502 Hub from the tray menu and open it again to apply."), "Faint")
        self.layout.addWidget(self.lang_hint)

        self.layout.addWidget(heading(self.tr("Startup")))
        self.autostart = QCheckBox(self.tr("Start G502 Hub when I log in (in the tray)"))
        self.autostart.setChecked(system.autostart_enabled())
        self.autostart.toggled.connect(system.set_autostart)
        self.layout.addWidget(self.autostart)
        self.close_to_tray = QCheckBox(self.tr("Keep running in the tray when I close the window"))
        self.close_to_tray.setChecked(settings.load().get("close_to_tray", True))
        self.close_to_tray.toggled.connect(lambda on: settings.update(close_to_tray=on))
        self.layout.addWidget(self.close_to_tray)
        self.layout.addWidget(muted(self.tr("Game rules, macros run by the app, live lighting and the DPI popup only "
                                            "work while G502 Hub runs. Settings saved on the mouse work either way."),
                                    "Faint"))

        self.layout.addWidget(heading(self.tr("On-screen popup")))
        self.osd = QCheckBox(self.tr("Show DPI and profile changes on screen"))
        self.osd.setChecked(settings.load().get("osd", True))
        self.osd.toggled.connect(lambda on: settings.update(osd=on))
        self.layout.addWidget(self.osd)

        self.layout.addWidget(heading(self.tr("Mouse picture")))
        self.picture = muted("")
        self.layout.addWidget(self.picture)
        row = QHBoxLayout()
        self.picture_btn = QPushButton()
        self.picture_btn.clicked.connect(self._toggle_photo)
        row.addWidget(self.picture_btn)
        row.addStretch()
        self.layout.addLayout(row)
        self.view.photoChanged.connect(self.refresh)

        self.layout.addWidget(heading(self.tr("Device access")))
        self.access = muted("")
        self.layout.addWidget(self.access)
        self.fix_btn = QPushButton(self.tr("Allow access (asks for your password)"))
        self.fix_btn.clicked.connect(self._fix_access)
        self.layout.addWidget(self.fix_btn)
        self._fix = system.PermissionFix()
        self._fix.finished.connect(self._fixed)

        self.layout.addWidget(heading(self.tr("Game integrations")))
        self.layout.addWidget(muted(self.tr("Used by rules with “Game-driven” lighting (Games & apps)."), "Faint"))
        self.gsi_status = muted("")
        self.layout.addWidget(self.gsi_status)
        row = QHBoxLayout()
        self.gsi_btn = QPushButton()
        self.gsi_btn.clicked.connect(self._toggle_gsi)
        row.addWidget(self.gsi_btn)
        row.addStretch()
        self.layout.addLayout(row)
        self.gsi_note = muted(self.tr("Restart the game after setting this up. Dota 2 also needs "
                                      "-gamestateintegration in its Steam launch options."), "Faint")
        self.layout.addWidget(self.gsi_note)

        self.layout.addWidget(heading(self.tr("LIGHTSYNC bridge for Proton games")))
        self.layout.addWidget(muted(self.tr("Windows games with Logitech lighting (like Uncharted, The Last of "
                                            "Us or GTA V) can drive the mouse through Proton, like with G HUB on "
                                            "Windows. Turn it on per game; it adds a small LogitechLed.dll to that "
                                            "game's Proton prefix, nothing in the game itself."), "Faint"))
        self.bridge = QWidget()
        self.bridge_col = QVBoxLayout(self.bridge)
        self.bridge_col.setContentsMargins(0, 0, 0, 0)
        self.bridge_col.setSpacing(6)
        self.layout.addWidget(self.bridge)
        self.layout.addStretch()

    def _lang_changed(self, idx):
        code = self.lang_box.itemData(idx)
        if code != get_current_language():
            settings.update(language=code)

    def refresh(self):
        ready = self.view.skin.ready
        photo_desc = self.tr("Logitech's product photo of the G502 HERO. It's their image, so G502 Hub doesn't include it: "
                             "it was downloaded from logitechg.com the first time the app started, and is kept in {path}.")
        self.picture.setText(photo_desc.format(path=photo.PHOTO_PATH.parent) if ready else self.view.skin.message)
        self.picture_btn.setText(self.tr("Downloading…") if self.view.fetcher.busy else self.tr("Download it again"))
        self.picture_btn.setEnabled(not self.view.fetcher.busy)
        rule = system.udev_rule_status()
        if rule == "old" and os.access("/dev/uinput", os.W_OK):
            rule = "current"  # the old rule covers the mouse, and Steam's rule already opens uinput
        self.access.setText({
            "current": self.tr("Your user can configure the mouse without root."),
            "old": self.tr("The permission rule is from an older version. Update it so macros run by the app "
                           "can always type."),
            "missing": self.tr("The permission rule isn't installed, so the app can't open the mouse."),
        }[rule])
        self.fix_btn.setText(self.tr("Update the rule (asks for your password)") if rule == "old" else
                             self.tr("Allow access (asks for your password)"))
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
            self.gsi_status.setText(self.tr("CS2 and Dota 2 live lighting: neither game is installed."))
            self.gsi_btn.hide()
            self.gsi_note.hide()
            return
        parts = []
        for g in games:
            status = self.tr("✓ set up") if done.get(g) else self.tr("not set up")
            parts.append(f"{names[g]} {status}")
        state = ", ".join(parts)
        self.gsi_status.setText(self.tr("CS2 and Dota 2 live lighting: {state}.").format(state=state))
        any_done = any(done.get(g) for g in games)
        self.gsi_btn.setText(self.tr("Remove CS2 / Dota 2 setup") if any_done else self.tr("Set up CS2 / Dota 2 lighting"))
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
            self.gsi_status.setText(self.tr("Couldn't change the game config: {error}").format(error=e))
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
            self.bridge_col.addWidget(muted(self.tr("Not available: {error}").format(error=e), "Faint"))
            return
        if not prefixes:
            self.bridge_col.addWidget(muted(self.tr("No Proton games found yet. Run a Windows game through "
                                                    "Steam once, then come back here."), "Faint"))
            return
        built = all((bridge.BIN_DIR / arch / bridge.DLL).exists() for arch in ("x64", "x86"))
        if not built:
            self.bridge_col.addWidget(muted(self.tr("The bridge DLL isn't built in this copy yet: install lld "
                                                    "(sudo pacman -S lld) and run bridge/logitechled/build.sh."),
                                            "Faint"))
        for appid, name, pfx in prefixes:
            row = QHBoxLayout()
            row.addWidget(QLabel(name), 1)
            on = bridge.is_installed(pfx)
            b = QPushButton(self.tr("Turn off") if on else self.tr("Turn on"))
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
