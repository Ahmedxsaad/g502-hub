"""ASSIGNMENTS page: what each button does, on the primary and G-Shift layers."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ... import keys
from ...onboard import SPECIAL_CODES, Consumer, Disabled, Key, MouseButton, Special, Unassigned
from .. import labels
from ..i18n import tr
from ..widgets import Card, ChoiceList, KeyCapture, Segmented, heading, muted
from . import Page

LEFT_CLICK = MouseButton(0x0001)

MEDIA = ["play-pause", "next-track", "prev-track", "stop", "mute", "volume-up", "volume-down",
         "browser-back", "browser-forward", "browser-refresh", "browser-home", "browser-search",
         "file-browser", "calculator", "mail", "brightness-up", "brightness-down"]

# (label, modifiers, character typed on the user's layout, or a key name)
RAW_SHORTCUTS = [
    ("Copy", 0x01, "c"), ("Paste", 0x01, "v"), ("Cut", 0x01, "x"), ("Undo", 0x01, "z"),
    ("Redo", 0x03, "z"), ("Select all", 0x01, "a"), ("Save", 0x01, "s"), ("Find", 0x01, "f"),
    ("New tab", 0x01, "t"), ("Close tab", 0x01, "w"), ("Reopen tab", 0x03, "t"),
    ("Next tab", 0x01, "@tab"), ("Previous tab", 0x03, "@tab"), ("Switch window", 0x04, "@tab"),
    ("Show desktop", 0x08, "d"), ("Lock screen", 0x08, "l"), ("Screenshot", 0x00, "@printscreen"),
    ("Escape", 0x00, "@esc"), ("Enter", 0x00, "@enter"), ("Delete", 0x00, "@delete"),
]


def same_action(a, b):
    """Compare bindings by what they do, ignoring the stored filler bytes."""
    return type(a) is type(b) and a.encode()[:2] == b.encode()[:2] and (
        not isinstance(a, (MouseButton, Key, Consumer)) or a.encode() == b.encode())


class AssignmentsPage(Page):
    icon = "assignments"
    mouse_mode = "assign"

    @property
    def title(self):
        return self.tr("ASSIGNMENTS")

    def __init__(self, state, view, keylabels, engine):
        super().__init__(state, view, keylabels)
        self.engine = engine
        self.open_macros = None  # set by the window: show the Macros page
        self.slot = 5  # G6
        self.layer = 0
        title = QLabel(self.tr("Assignments"))
        title.setObjectName("Title")
        self.layout.addWidget(title)
        self.layer_tabs = Segmented([self.tr("Primary"), self.tr("G-Shift")])
        self.layer_tabs.changed.connect(self._layer_changed)
        self.layout.addWidget(self.layer_tabs)
        self.gshift_hint = muted("", "Faint")
        self.layout.addWidget(self.gshift_hint)

        current = Card()
        self.button_name = QLabel()
        self.button_name.setObjectName("Title")
        current.body.addWidget(self.button_name)
        self.current = QLabel()
        self.current.setObjectName("Muted")
        current.body.addWidget(self.current)
        row = QHBoxLayout()
        self.default_btn = QPushButton(self.tr("Restore default"))
        self.default_btn.clicked.connect(self._restore_default)
        row.addWidget(self.default_btn)
        self.disable_btn = QPushButton(self.tr("Disable"))
        self.disable_btn.clicked.connect(lambda: self._assign(self._off_binding()))
        row.addWidget(self.disable_btn)
        row.addStretch()
        current.body.addLayout(row)
        self.layout.addWidget(current)

        self.categories = Segmented([self.tr("Commands"), self.tr("Keys"), self.tr("Media"), self.tr("Macros")])
        self.layout.addWidget(self.categories)
        self.stack = QStackedWidget()
        self.categories.changed.connect(self.stack.setCurrentIndex)
        self.layout.addWidget(self.stack)

        command_groups = [
            (self.tr("Mouse"), [
                (MouseButton(0x0001), self.tr("Left click")),
                (MouseButton(0x0002), self.tr("Right click")),
                (MouseButton(0x0004), self.tr("Middle click")),
                (MouseButton(0x0008), self.tr("Back")),
                (MouseButton(0x0010), self.tr("Forward")),
            ]),
            (self.tr("Scroll"), [
                (Special(SPECIAL_CODES["tilt-left"]), self.tr("Scroll left")),
                (Special(SPECIAL_CODES["tilt-right"]), self.tr("Scroll right")),
                (Special(SPECIAL_CODES["scroll-up"]), self.tr("Scroll up")),
                (Special(SPECIAL_CODES["scroll-down"]), self.tr("Scroll down")),
            ]),
            (self.tr("Sensitivity"), [
                (Special(SPECIAL_CODES["dpi-up"]), self.tr("DPI up")),
                (Special(SPECIAL_CODES["dpi-down"]), self.tr("DPI down")),
                (Special(SPECIAL_CODES["dpi-cycle"]), self.tr("DPI cycle")),
                (Special(SPECIAL_CODES["dpi-default"]), self.tr("DPI default")),
                (Special(SPECIAL_CODES["dpi-shift"]), self.tr("DPI shift (sniper)")),
            ]),
            (self.tr("Profiles"), [
                (Special(SPECIAL_CODES["profile-next"]), self.tr("Next profile")),
                (Special(SPECIAL_CODES["profile-prev"]), self.tr("Previous profile")),
                (Special(SPECIAL_CODES["profile-cycle"]), self.tr("Cycle profiles")),
            ]),
            (self.tr("Layers"), [
                (Special(SPECIAL_CODES["gshift"]), self.tr("G-Shift (hold)")),
            ]),
        ]

        self.choice_lists = []
        commands = QWidget()
        col = QVBoxLayout(commands)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(10)
        for name, choices in command_groups:
            col.addWidget(heading(name))
            lst = ChoiceList(choices, columns=2)
            lst.changed.connect(self._assign)
            self.choice_lists.append(lst)
            col.addWidget(lst)
        col.addStretch()
        self.stack.addWidget(commands)

        keys_page = QWidget()
        col = QVBoxLayout(keys_page)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(10)
        col.addWidget(heading(self.tr("Press a key or combination")))
        self.capture = KeyCapture()
        self.capture.captured.connect(lambda mods, usage: self._assign(Key(mods, usage)))
        col.addWidget(self.capture)
        col.addWidget(heading(self.tr("Common shortcuts")))
        shortcuts = []
        for raw_label, mods, char in RAW_SHORTCUTS:
            usage = keys.KEYS[char[1:]] if char.startswith("@") else self.keylabels.usage_for(char)
            binding = Key(mods, usage)
            lbl = self.tr(raw_label)
            shortcuts.append((binding, f"{lbl}   ·   {self.keylabels.combo(mods, usage)}"))
        lst = ChoiceList(shortcuts, columns=1)
        lst.changed.connect(self._assign)
        self.choice_lists.append(lst)
        col.addWidget(lst)
        col.addStretch()
        self.stack.addWidget(keys_page)

        media = QWidget()
        col = QVBoxLayout(media)
        col.setContentsMargins(0, 4, 0, 0)
        lst = ChoiceList([(Consumer(keys.CONSUMER[m]), labels.CONSUMER_LABELS[m]) for m in MEDIA], columns=2)
        lst.changed.connect(self._assign)
        self.choice_lists.append(lst)
        col.addWidget(lst)
        col.addStretch()
        self.stack.addWidget(media)

        macro_page = QWidget()
        col = QVBoxLayout(macro_page)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(10)
        self.macro_hint = muted("", "Faint")
        col.addWidget(self.macro_hint)
        self.macro_holder = QVBoxLayout()
        col.addLayout(self.macro_holder)
        self.macro_list = None
        make = QPushButton(self.tr("Make a macro…"))
        make.clicked.connect(lambda: self.open_macros and self.open_macros())
        col.addWidget(make)
        col.addStretch()
        self.stack.addWidget(macro_page)
        engine.changed.connect(self.refresh)
        self.layout.addStretch()

    def _bindings(self, profile):
        return profile.gshift if self.layer else profile.buttons

    def _off_binding(self):
        return Unassigned() if self.layer else Disabled()

    def _layer_changed(self, layer):
        self.layer = layer
        self.refresh()

    def on_view_click(self, key):
        self.slot = key
        self.refresh()

    def _assign(self, binding):
        profile = self.state.profile()
        if profile is None:
            return
        if self.layer == 0 and self.slot == 0 and not same_action(binding, LEFT_CLICK):
            others = [b for i, b in enumerate(profile.buttons) if i != 0 and same_action(b, LEFT_CLICK)]
            if not others:
                title = self.tr("Remove left click?")
                msg = self.tr("No other button is set to Left click. Without one you can only click "
                              "with the keyboard or touchpad until you change it back.\n\nContinue?")
                answer = QMessageBox.question(self.panel, title, msg)
                if answer != QMessageBox.StandardButton.Yes:
                    self.refresh()
                    return
        slot, layer = self.slot, self.layer
        self.engine.unassign_app(self.state.active_slot, layer, slot)
        self.state.edit(lambda p: (p.gshift if layer else p.buttons).__setitem__(slot, binding))
        self.state.free_macro_pages()  # if this button played a macro stored in the mouse

    def _assign_macro(self, macro_id):
        def done(error):
            if error:
                err_text = self.tr("Couldn't put the macro on {button}: {error}").format(button=labels.BUTTON_NAMES[self.slot], error=error)
                self.state.status.emit("error", err_text)
            self.refresh()
        self.engine.assign(self.state.active_slot, self.layer, self.slot, macro_id, done)

    def _show_macros(self, current):
        if self.macro_list is not None:
            self.macro_list.deleteLater()
        where = {"mouse": self.tr("saved on the mouse"), "app": self.tr("run by the app")}
        choices = [(m.id, f"{m.name}   ·   {where.get(m.target, m.target)}") for m in self.engine.macros]
        self.macro_list = ChoiceList(choices, columns=1)
        self.macro_list.changed.connect(self._assign_macro)
        self.macro_list.set_value(current.id if current else None)
        self.macro_holder.addWidget(self.macro_list)
        self.macro_hint.setText(self.tr("Pick a macro for this button.") if choices else
                                self.tr("You don't have any macros yet."))

    def _restore_default(self):
        if self.layer:
            self._assign(Unassigned())
            return
        slot = self.state.active_slot
        factory = self.state.factory[(slot - 1) % len(self.state.factory)]
        self._assign(factory.buttons[self.slot])

    def refresh(self):
        profile = self.state.profile()
        if profile is None:
            return
        bindings = self._bindings(profile)
        self.view.tooltips = {i: f"{labels.BUTTON_NAMES[i]}\n{labels.binding(bindings[i], self.keylabels)}"
                              for i in range(len(labels.BUTTON_NAMES))}
        self.view.set_selected([self.slot])
        current = bindings[self.slot]
        macro = self.engine.macro_on(self.state.active_slot, self.layer, self.slot, current)
        self.button_name.setText(labels.BUTTON_NAMES[self.slot])
        where_text = self.tr("saved on the mouse") if (macro and macro.target == "mouse") else self.tr("run by the app")
        text = (f"Macro “{macro.name}”, {where_text}"
                if macro else labels.binding(current, self.keylabels))
        prefix = self.tr("G-Shift layer: ") if self.layer else ""
        self.current.setText(prefix + text)
        self._show_macros(macro)
        for lst in self.choice_lists:
            match = next((v for v in lst.values if same_action(v, current)), None)
            lst.set_value(match)
        has_shift = any(isinstance(b, Special) and b.function == SPECIAL_CODES["gshift"] for b in profile.buttons)
        if self.layer and not has_shift:
            self.gshift_hint.setText(self.tr("No button is set to G-Shift on the primary layer yet. "
                                             "Set one (G6 works well) to use this layer."))
        elif self.layer:
            self.gshift_hint.setText(self.tr("While the G-Shift button is held, buttons do this instead."))
        else:
            self.gshift_hint.setText("")
        self.gshift_hint.setVisible(bool(self.gshift_hint.text()))
