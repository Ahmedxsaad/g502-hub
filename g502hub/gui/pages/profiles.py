"""PROFILES page: the 5 onboard slots, plus device info and backups."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QWidget)

from ... import backup, sharing
from .. import labels, theme
from ..widgets import Card, LedSwatch, heading, muted
from . import Page


class SlotCard(Card):
    def __init__(self, page, slot):
        super().__init__()
        self.page, self.slot = page, slot
        self.setMinimumWidth(250)
        top = QHBoxLayout()
        top.addWidget(heading(self.tr("Slot {slot}").format(slot=slot)))
        top.addStretch()
        self.badge = QLabel(self.tr("ACTIVE"))
        self.badge.setStyleSheet(f"color: {theme.ACCENT}; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
        top.addWidget(self.badge)
        self.body.addLayout(top)
        self.name = QLineEdit()
        self.name.setPlaceholderText(self.tr("Profile {slot}").format(slot=slot))
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
        zone_labels = {"DPI": self.tr("DPI"), "Logo": self.tr("Logo")}
        for zone in ("DPI", "Logo"):
            swatch, name = LedSwatch(), QLabel()
            name.setObjectName("Muted")
            lights.addWidget(swatch)
            lights.addWidget(name)
            lights.addSpacing(10)
            self.swatches.append(swatch)
            self.light_names.append((zone_labels[zone], name))
        lights.addStretch()
        self.body.addLayout(lights)
        self.cycle = QCheckBox(self.tr("Included when G9 cycles profiles"))
        self.cycle.clicked.connect(lambda on: page.state.set_slot_enabled(slot, on))
        self.body.addWidget(self.cycle)
        row = QHBoxLayout()
        self.activate_btn = QPushButton(self.tr("Activate"))
        self.activate_btn.setObjectName("Primary")
        self.activate_btn.clicked.connect(lambda: page.state.activate(slot))
        row.addWidget(self.activate_btn)
        more = QPushButton(self.tr("More  ▾"))
        menu = QMenu(more)
        menu.addAction(self.tr("Export to a file…"), self._export)
        menu.addAction(self.tr("Import from a file…"), self._import)
        menu.addSeparator()
        menu.addAction(self.tr("Reset to factory profile"), self._reset)
        copy = menu.addMenu(self.tr("Copy this profile to"))
        for other in range(1, 6):
            if other != slot:
                copy.addAction(self.tr("Slot {other}").format(other=other), lambda o=other: self._copy(o))
        more.setMenu(menu)
        row.addWidget(more)
        row.addStretch()
        self.body.addLayout(row)

    def _renamed(self):
        text = self.name.text().strip() or None  # empty = the firmware's default name
        profile = self.page.state.profile(self.slot)
        if profile is not None and (profile.name or None) != text:
            self.page.state.edit(lambda p: setattr(p, "name", text), slot=self.slot, reload=False)

    def _export(self):
        profile = self.page.state.profile(self.slot)
        name = (profile.name or f"G502 profile {self.slot}").replace("/", "-")
        title = self.tr("Export profile")
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path.home() / f"{name}{sharing.SUFFIX}"),
                                              f"G502 Hub profiles (*{sharing.SUFFIX})")
        if not path:
            return
        if not path.endswith(sharing.SUFFIX):
            path += sharing.SUFFIX
        try:
            Path(path).write_text(sharing.export(profile))
        except OSError as e:
            QMessageBox.warning(self, title, self.tr("Couldn't save the file: {error}").format(error=e))
            return
        self.page.state.status.emit("ok", self.tr("Exported slot {slot} to {path}").format(slot=self.slot, path=path))

    def _import(self):
        title = self.tr("Import profile")
        path, _ = QFileDialog.getOpenFileName(self, title, str(Path.home()),
                                              f"G502 Hub profiles (*{sharing.SUFFIX});;All files (*)")
        if not path:
            return
        try:
            profile, notes = sharing.load(Path(path).read_text())
        except (OSError, UnicodeDecodeError, sharing.ShareError) as e:
            QMessageBox.warning(self, title, self.tr("Couldn't import {filename}: {error}").format(filename=Path(path).name, error=e))
            return
        name = profile.name or Path(path).stem
        text = self.tr("Replace slot {slot} with \"{name}\"? Your backup keeps the current one.").format(slot=self.slot, name=name)
        if notes:
            text += "\n\n" + "\n".join(f"• {n}" for n in notes)
        if QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes:
            self.page.state.replace_slot(self.slot, profile)

    def _reset(self):
        msg = self.tr("Replace slot {slot} with its factory profile? Your backup keeps the current one.").format(slot=self.slot)
        if QMessageBox.question(self, self.tr("Reset slot"), msg) == QMessageBox.StandardButton.Yes:
            self.page.state.reset_slot(self.slot)

    def _copy(self, target):
        msg = self.tr("Overwrite slot {target} with slot {slot}?").format(target=target, slot=self.slot)
        if QMessageBox.question(self, self.tr("Copy profile"), msg) == QMessageBox.StandardButton.Yes:
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
            eff = labels.effect_label(led.effect) or self.tr("custom")
            name.setText(f"{zone}: {eff.lower()}")
        self.cycle.setChecked(enabled)


class ProfilesPage(Page):
    icon = "profiles"

    @property
    def title(self):
        return self.tr("PROFILES")

    def __init__(self, *args):
        super().__init__(*args)
        self.center = QScrollArea()
        self.center.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(28, 24, 28, 24)
        grid.setSpacing(14)
        title = QLabel(self.tr("Onboard memory"))
        title.setObjectName("Title")
        grid.addWidget(title, 0, 0, 1, 2)
        grid.addWidget(muted(self.tr("These 5 profiles live on the mouse and work on any computer. "
                                     "G9 switches between the included ones."), "Faint"), 1, 0, 1, 2)
        self.cards = [SlotCard(self, n) for n in range(1, 6)]
        for i, card in enumerate(self.cards):
            grid.addWidget(card, 2 + i // 2, i % 2)
        grid.setRowStretch(5, 1)
        self.center.setWidget(inner)

        self.layout.addWidget(heading(self.tr("Device")))
        self.device = QLabel()
        self.device.setObjectName("Muted")
        self.device.setWordWrap(True)
        self.layout.addWidget(self.device)
        self.layout.addWidget(heading(self.tr("Backups")))
        self.layout.addWidget(muted(self.tr("A full backup is taken automatically before the first change "
                                            "each session."), "Faint"))
        buttons_info = [
            (self.tr("Back up now"), self._backup),
            (self.tr("Restore a backup…"), self._restore),
            (self.tr("Open backups folder"), self._open_folder),
        ]
        for text, slot in buttons_info:
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
        dev_text = self.tr("{name}\nFirmware {fw}\nProfile format {format}, {sectors} × {size} B onboard memory")
        self.device.setText(dev_text.format(name=s.name, fw=fw, format=s.info.profile_format,
                                            sectors=s.info.sector_count, size=s.info.sector_size))
        for card, entry, profile in zip(self.cards, s.directory.entries, s.profiles):
            card.show_profile(profile, entry.enabled, card.slot == s.active_slot)

    def _backup(self):
        self.backup_result.setText(self.tr("Backing up…"))
        self.state.backup_now(lambda path, e: self.backup_result.setText(
            self.tr("Failed: {error}").format(error=e) if e else self.tr("Saved {path}").format(path=path)))

    def _restore(self):
        backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        title = self.tr("Restore backup")
        path, _ = QFileDialog.getOpenFileName(self.panel, title, str(backup.BACKUP_DIR), "Backups (*.json)")
        if not path:
            return
        confirm_msg = self.tr("Write this backup to the mouse? A backup of the current state is taken first.")
        if QMessageBox.question(self.panel, title, confirm_msg) != QMessageBox.StandardButton.Yes:
            return
        self.backup_result.setText(self.tr("Restoring…"))
        def on_done(written, e):
            if e:
                self.backup_result.setText(self.tr("Failed: {error}").format(error=e))
            elif written:
                self.backup_result.setText(self.tr("Restored {count} sector(s)").format(count=len(written)))
            else:
                self.backup_result.setText(self.tr("The mouse already matches that backup"))
        self.state.restore(path, on_done)

    def _open_folder(self):
        backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(backup.BACKUP_DIR)))
