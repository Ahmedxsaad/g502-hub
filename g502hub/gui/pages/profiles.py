"""PROFILES page: the 5 onboard slots, plus device info and backups."""

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QWidget)

from ... import backup
from .. import theme
from .. import labels
from ..widgets import Card, LedSwatch, heading, muted
from . import Page


class SlotCard(Card):
    def __init__(self, page, slot):
        super().__init__()
        self.page, self.slot = page, slot
        self.setMinimumWidth(250)
        top = QHBoxLayout()
        top.addWidget(heading(f"Slot {slot}"))
        top.addStretch()
        self.badge = QLabel("ACTIVE")
        self.badge.setStyleSheet(f"color: {theme.ACCENT}; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
        top.addWidget(self.badge)
        self.body.addLayout(top)
        self.name = QLineEdit()
        self.name.setPlaceholderText(f"Profile {slot}")
        self.name.setMaxLength(24)
        self.name.editingFinished.connect(self._renamed)
        self.body.addWidget(self.name)
        self.summary = QLabel()
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)
        lights = QHBoxLayout()
        lights.setSpacing(6)
        self.swatches, self.light_names = [], []
        for zone in ("DPI", "Logo"):
            swatch, name = LedSwatch(), QLabel()
            name.setObjectName("Muted")
            lights.addWidget(swatch)
            lights.addWidget(name)
            lights.addSpacing(10)
            self.swatches.append(swatch)
            self.light_names.append((zone, name))
        lights.addStretch()
        self.body.addLayout(lights)
        self.cycle = QCheckBox("Included when G9 cycles profiles")
        self.cycle.clicked.connect(lambda on: page.state.set_slot_enabled(slot, on))
        self.body.addWidget(self.cycle)
        row = QHBoxLayout()
        self.activate_btn = QPushButton("Activate")
        self.activate_btn.setObjectName("Primary")
        self.activate_btn.clicked.connect(lambda: page.state.activate(slot))
        row.addWidget(self.activate_btn)
        more = QPushButton("More  ▾")
        menu = QMenu(more)
        menu.addAction("Reset to factory profile", self._reset)
        copy = menu.addMenu("Copy this profile to")
        for other in range(1, 6):
            if other != slot:
                copy.addAction(f"Slot {other}", lambda o=other: self._copy(o))
        more.setMenu(menu)
        row.addWidget(more)
        row.addStretch()
        self.body.addLayout(row)

    def _renamed(self):
        text = self.name.text().strip() or None  # empty = the firmware's default name
        profile = self.page.state.profile(self.slot)
        if profile is not None and (profile.name or None) != text:
            self.page.state.edit(lambda p: setattr(p, "name", text), slot=self.slot, reload=False)

    def _reset(self):
        if QMessageBox.question(self, "Reset slot", f"Replace slot {self.slot} with its factory "
                                "profile? Your backup keeps the current one.") == QMessageBox.StandardButton.Yes:
            self.page.state.reset_slot(self.slot)

    def _copy(self, target):
        if QMessageBox.question(self, "Copy profile", f"Overwrite slot {target} with slot "
                                f"{self.slot}?") == QMessageBox.StandardButton.Yes:
            self.page.state.copy_slot(self.slot, target)

    def show_profile(self, profile, enabled, active):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.badge.setVisible(active)
        self.activate_btn.setVisible(not active)
        if not self.name.hasFocus():
            self.name.setText(profile.name or "")
        dpis = " / ".join(str(d) for _, d in profile.dpi_levels())
        self.summary.setText(f"{profile.report_rate_hz} Hz  ·  {dpis} DPI")
        for led, swatch, (zone, name) in zip(profile.leds, self.swatches, self.light_names):
            swatch.set_effect(led)
            name.setText(f"{zone}: {labels.EFFECT_LABELS.get(led.effect, 'custom').lower()}")
        self.cycle.setChecked(enabled)


class ProfilesPage(Page):
    title = "PROFILES"
    icon = "profiles"

    def __init__(self, *args):
        super().__init__(*args)
        self.center = QScrollArea()
        self.center.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(28, 24, 28, 24)
        grid.setSpacing(14)
        title = QLabel("Onboard memory")
        title.setObjectName("Title")
        grid.addWidget(title, 0, 0, 1, 2)
        grid.addWidget(muted("These 5 profiles live on the mouse and work on any computer. "
                             "G9 switches between the included ones.", "Faint"), 1, 0, 1, 2)
        self.cards = [SlotCard(self, n) for n in range(1, 6)]
        for i, card in enumerate(self.cards):
            grid.addWidget(card, 2 + i // 2, i % 2)
        grid.setRowStretch(5, 1)
        self.center.setWidget(inner)

        self.layout.addWidget(heading("Device"))
        self.device = QLabel()
        self.device.setObjectName("Muted")
        self.device.setWordWrap(True)
        self.layout.addWidget(self.device)
        self.layout.addWidget(heading("Backups"))
        self.layout.addWidget(muted("A full backup is taken automatically before the first change "
                                    "each session.", "Faint"))
        for text, slot in (("Back up now", self._backup), ("Restore a backup…", self._restore),
                           ("Open backups folder", self._open_folder)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            self.layout.addWidget(b)
        self.backup_result = muted("", "Faint")
        self.layout.addWidget(self.backup_result)
        self.layout.addStretch()

    def refresh(self):
        s = self.state
        if not s.connected:
            return
        fw = ", ".join(f for _, f in s.firmware)
        self.device.setText(f"{s.name}\nFirmware {fw}\nProfile format {s.info.profile_format}, "
                            f"{s.info.sector_count} × {s.info.sector_size} B onboard memory")
        for card, entry, profile in zip(self.cards, s.directory.entries, s.profiles):
            card.show_profile(profile, entry.enabled, card.slot == s.active_slot)

    def _backup(self):
        self.backup_result.setText("Backing up…")
        self.state.backup_now(lambda path, e: self.backup_result.setText(
            f"Failed: {e}" if e else f"Saved {path}"))

    def _restore(self):
        backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self.panel, "Restore backup", str(backup.BACKUP_DIR),
                                              "Backups (*.json)")
        if not path:
            return
        if QMessageBox.question(self.panel, "Restore backup",
                                "Write this backup to the mouse? A backup of the current state "
                                "is taken first.") != QMessageBox.StandardButton.Yes:
            return
        self.backup_result.setText("Restoring…")
        self.state.restore(path, lambda written, e: self.backup_result.setText(
            f"Failed: {e}" if e else f"Restored {len(written)} sector(s)" if written
            else "The mouse already matches that backup"))

    def _open_folder(self):
        backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(backup.BACKUP_DIR)))
