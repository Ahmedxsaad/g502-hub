"""MACROS page: make and edit macros. Assigning them to buttons happens on Assignments."""

import copy
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ... import keys, macros
from ...macros import Macro, Step
from .. import labels
from ..i18n import tr
from ..widgets import Card, ChoiceList, KeyCapture, Segmented, Switcher, heading, muted
from . import Page

MEDIA = ["play-pause", "next", "previous", "stop", "volume-up", "volume-down", "mute"]
BUTTON_NAMES = {0: "G1", 1: "G2", 2: "G3", 3: "G4", 4: "G5", 5: "G6", 6: "G7", 7: "G8", 8: "G9",
                9: "tilt right", 10: "tilt left"}


class Recorder(QPushButton):
    """Toggle on, then type: every key press and release is kept with its timing."""

    def __init__(self, on_done):
        super().__init__(tr("●  Record keys", "Macros"))
        self.setCheckable(True)
        self.on_done = on_done
        self.events = []
        self._mods = 0
        self.toggled.connect(self._toggled)

    def _toggled(self, on):
        self.setText(tr("■  Stop recording (Esc)", "Macros") if on else tr("●  Record keys", "Macros"))
        if on:
            self.events, self._mods = [], 0
            self.setFocus()
            self.grabKeyboard()
        else:
            self.releaseKeyboard()
            if self.events:
                self.on_done(macros.from_recording(self.events))

    def _record(self, e, down):
        if e.isAutoRepeat():
            return
        code = e.nativeScanCode() - 8
        if down and code == 1 and not self._mods:  # Esc stops
            self.setChecked(False)
            return
        if code in keys.EVDEV_TO_MODIFIER:
            bit = keys.EVDEV_TO_MODIFIER[code]
            self._mods = self._mods | bit if down else self._mods & ~bit
            self.events.append((time.monotonic(), 0, bit, down))
            return
        usage = keys.EVDEV_TO_HID.get(code)
        if usage:
            self.events.append((time.monotonic(), usage, 0, down))

    def keyPressEvent(self, e):
        if self.isChecked():
            self._record(e, True)
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if self.isChecked():
            self._record(e, False)
        else:
            super().keyReleaseEvent(e)


class MacroCard(Card):
    def __init__(self, page, macro):
        super().__init__()
        top = QHBoxLayout()
        name = QLabel(macro.name)
        name.setStyleSheet("font-weight: 600; font-size: 14px;")
        top.addWidget(name)
        top.addStretch()
        self.body.addLayout(top)
        self.body.addWidget(muted(macro.describe()))
        uses = page.engine.uses(macro.id)
        where_parts = []
        for slot, layer, b in uses:
            b_name = BUTTON_NAMES.get(b, b)
            gshift = " " + tr("with G-Shift", "Macros") if layer else ""
            where_parts.append(tr("{button}{gshift} on slot {slot}", "Macros").format(button=b_name, gshift=gshift, slot=slot))
        where = ", ".join(where_parts)
        uses_text = tr("On {where}", "Macros").format(where=where) if uses else tr("Not on any button yet: pick it under Assignments.", "Macros")
        self.body.addWidget(muted(uses_text, "Faint"))
        row = QHBoxLayout()
        edit = QPushButton(tr("Edit", "Macros"))
        edit.clicked.connect(lambda: page.edit(macro))
        row.addWidget(edit)
        row.addStretch()
        delete = QPushButton(tr("Delete", "Macros"))
        delete.setObjectName("Flat")
        delete.clicked.connect(lambda: page.engine.delete(macro.id))
        row.addWidget(delete)
        self.body.addLayout(row)


class MacrosPage(Page):
    icon = "macros"

    @property
    def title(self):
        return self.tr("MACROS")

    def __init__(self, state, view, keylabels, engine):
        super().__init__(state, view, keylabels)
        self.engine = engine
        self.editing = None
        self.pages = Switcher()
        self.pages.addWidget(self._list_page())
        self.pages.addWidget(self._editor_page())
        self.layout.addWidget(self.pages)
        self.layout.addStretch()
        engine.changed.connect(lambda: self.pages.currentIndex() == 0 and self._show_list())

    # ------------------------------------------------------------ list

    def _list_page(self):
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        title = QLabel(self.tr("Macros"))
        title.setObjectName("Title")
        col.addWidget(title)
        col.addWidget(muted(self.tr("Saved on the mouse, a macro plays on any computer: keys, media keys, clicks, "
                                    "scrolling and waits. Run by G502 Hub, it can also type text and repeat while "
                                    "you hold the button, but needs the app running."), "Faint"))
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(10)
        col.addLayout(self.list_col)
        new = QPushButton(self.tr("+  New macro"))
        new.setObjectName("Primary")
        new.clicked.connect(lambda: self.edit(Macro(self.tr("New macro"), []), new=True))
        col.addWidget(new)
        return w

    def _show_list(self):
        while self.list_col.count():
            item = self.list_col.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for macro in self.engine.macros:
            self.list_col.addWidget(MacroCard(self, macro))
        if not self.engine.macros:
            self.list_col.addWidget(muted(self.tr("No macros yet."), "Faint"))

    # ------------------------------------------------------------ editor

    def _editor_page(self):
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        self.editor_title = QLabel(self.tr("Macro"))
        self.editor_title.setObjectName("Title")
        col.addWidget(self.editor_title)
        col.addWidget(heading(self.tr("Name")))
        self.name = QLineEdit()
        self.name.setMaxLength(40)
        col.addWidget(self.name)
        col.addWidget(heading(self.tr("Runs")))
        targets = [("mouse", self.tr("Saved on the mouse")), ("app", self.tr("Run by G502 Hub"))]
        self.target = ChoiceList(targets, columns=2)
        self.target.changed.connect(lambda _: self._update())
        col.addWidget(self.target)
        col.addWidget(heading(self.tr("Plays")))
        modes = [
            ("once", self.tr("Once per press")),
            ("while-held", self.tr("Repeats while held")),
            ("toggle", self.tr("Press to start, again to stop")),
        ]
        self.mode = ChoiceList(modes, columns=1)
        self.mode.changed.connect(lambda _: self._update())
        col.addWidget(self.mode)

        col.addWidget(heading(self.tr("Steps")))
        self.steps = QListWidget()
        self.steps.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.steps.setMinimumHeight(160)
        col.addWidget(self.steps)
        row = QHBoxLayout()
        for text, fn in (("↑", lambda: self._move(-1)), ("↓", lambda: self._move(1)), (self.tr("Remove"), self._remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        col.addLayout(row)
        self.capacity = muted("", "Faint")
        col.addWidget(self.capacity)

        col.addWidget(heading(self.tr("Add a step")))
        self.add_tabs = Segmented([self.tr("Key"), self.tr("Text"), self.tr("Wait"), self.tr("Mouse"), self.tr("Media")])
        col.addWidget(self.add_tabs)
        adders = Switcher()
        self.add_tabs.changed.connect(adders.setCurrentIndex)
        col.addWidget(adders)

        key_page, kcol = self._column()
        capture = KeyCapture()
        capture.captured.connect(lambda mods, usage: self._add(Step("key", {"combo": keys.combo_name(mods, usage)})))
        kcol.addWidget(capture)
        self.recorder = Recorder(self._recorded)
        kcol.addWidget(self.recorder)
        kcol.addWidget(muted(self.tr("Recording keeps the waits between your key presses."), "Faint"))
        adders.addWidget(key_page)

        text_page, tcol = self._column()
        self.text = QLineEdit()
        self.text.setPlaceholderText(self.tr("Text to type, e.g. gg wp"))
        tcol.addWidget(self.text)
        add_text = QPushButton(self.tr("Add text"))
        add_text.clicked.connect(lambda: self.text.text() and self._add(Step("text", {"text": self.text.text()})))
        tcol.addWidget(add_text)
        adders.addWidget(text_page)

        wait_page, wcol = self._column()
        self.wait = QSpinBox()
        self.wait.setRange(1, 60000)
        self.wait.setValue(100)
        self.wait.setSuffix(" ms")
        wcol.addWidget(self.wait)
        add_wait = QPushButton(self.tr("Add wait"))
        add_wait.clicked.connect(lambda: self._add(Step("delay", {"ms": self.wait.value()})))
        wcol.addWidget(add_wait)
        adders.addWidget(wait_page)

        mouse_page, mcol = self._column()
        mouse_buttons = [
            ("left", self.tr("Left click")),
            ("right", self.tr("Right click")),
            ("middle", self.tr("Middle click")),
            ("back", self.tr("Back")),
            ("forward", self.tr("Forward")),
        ]
        clicks = ChoiceList(mouse_buttons, columns=2)
        clicks.changed.connect(lambda b: (self._add(Step("click", {"button": b})), clicks.set_value(None)))
        mcol.addWidget(clicks)
        scroll = QHBoxLayout()
        for text, amount in ((self.tr("Scroll up"), 1), (self.tr("Scroll down"), -1)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, a=amount: self._add(Step("scroll", {"amount": a})))
            scroll.addWidget(b)
        mcol.addLayout(scroll)
        adders.addWidget(mouse_page)

        media_page, ecol = self._column()
        media = ChoiceList([(m, labels.CONSUMER_LABELS.get(m, m)) for m in MEDIA if m in keys.CONSUMER], columns=2)
        media.changed.connect(lambda m: (self._add(Step("media", {"key": m})), media.set_value(None)))
        ecol.addWidget(media)
        adders.addWidget(media_page)

        row = QHBoxLayout()
        save = QPushButton(self.tr("Save macro"))
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        row.addWidget(save)
        cancel = QPushButton(self.tr("Cancel"))
        cancel.clicked.connect(self._close)
        row.addWidget(cancel)
        row.addStretch()
        col.addLayout(row)
        self.error = muted("", "Faint")
        col.addWidget(self.error)
        return w

    @staticmethod
    def _column():
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        return w, col

    def edit(self, macro, new=False):
        self.editing, self.editing_new = copy.deepcopy(macro), new
        self.editor_title.setText(self.tr("New macro") if new else self.tr("Edit macro"))
        self.name.setText(macro.name)
        self.target.set_value(macro.target)
        self.mode.set_value(macro.mode)
        self.error.setText("")
        self._show_steps()
        self._update()
        self.pages.setCurrentIndex(1)
        self.panel.verticalScrollBar().setValue(0)

    def _show_steps(self, select=None):
        self.steps.clear()
        for step in self.editing.steps:
            self.steps.addItem(step.describe(self.keylabels.combo))
        if select is not None and 0 <= select < self.steps.count():
            self.steps.setCurrentRow(select)
        self._update()

    def _add(self, step):
        at = self.steps.currentRow() + 1 if self.steps.currentRow() >= 0 else len(self.editing.steps)
        self.editing.steps.insert(at, step)
        self._show_steps(select=at)

    def _recorded(self, steps):
        for step in steps:
            self._add(step)

    def _move(self, d):
        i = self.steps.currentRow()
        j = i + d
        if 0 <= i < len(self.editing.steps) and 0 <= j < len(self.editing.steps):
            s = self.editing.steps
            s[i], s[j] = s[j], s[i]
            self._show_steps(select=j)

    def _remove(self):
        i = self.steps.currentRow()
        if 0 <= i < len(self.editing.steps):
            del self.editing.steps[i]
            self._show_steps(select=min(i, len(self.editing.steps) - 1))

    def _update(self):
        """Keep the choices consistent and show how much mouse memory the macro needs."""
        if self.editing is None:
            return
        on_mouse = self.target.value() == "mouse"
        for i, button in enumerate(self.mode.group.buttons()):
            button.setEnabled(not on_mouse or self.mode.values[i] == "once")
        if on_mouse and self.mode.value() != "once":
            self.mode.set_value("once")
        if not on_mouse:
            self.capacity.setText(self.tr("Runs from the app, so there's no size limit. Its button does nothing "
                                          "while G502 Hub isn't running."))
            return
        trial = Macro(self.name.text() or self.tr("Macro"), self.editing.steps, mode="once", target="mouse")
        try:
            size = macros.onboard_size(trial, self.keylabels.typing)
            self.capacity.setText(self.tr("Uses {size} of {capacity} bytes of mouse memory.").format(
                size=size, capacity=macros.ONBOARD_CAPACITY))
        except macros.MacroError as e:
            self.capacity.setText(self.tr("Can't be saved on the mouse: {error}. Choose “Run by G502 Hub” instead.").format(error=e))

    def _save(self):
        m = self.editing
        m.name = self.name.text().strip() or self.tr("Macro")
        m.target = self.target.value() or "app"
        m.mode = self.mode.value() or "once"
        if not m.steps:
            self.error.setText(self.tr("Add at least one step."))
            return
        if m.target == "mouse":
            try:
                macros.to_onboard(m, self.keylabels.typing)
            except macros.MacroError as e:
                self.error.setText(self.tr("Can't be saved on the mouse: {error}").format(error=e))
                return
        self.engine.save(m)
        self._close()

    def _close(self):
        if self.recorder.isChecked():
            self.recorder.setChecked(False)
        self.editing = None
        self.pages.setCurrentIndex(0)
        self._show_list()

    def refresh(self):
        if self.pages.currentIndex() == 0:
            self._show_list()
