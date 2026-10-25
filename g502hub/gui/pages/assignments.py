"""ASSIGNMENTS page: what each button does, on the primary and G-Shift layers."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ... import keys
from ...onboard import SPECIAL_CODES, Consumer, Disabled, Key, MouseButton, Special, Unassigned
from .. import labels
from ..widgets import Card, ChoiceList, KeyCapture, Segmented, heading, muted
from . import Page

LEFT_CLICK = MouseButton(0x0001)

COMMAND_GROUPS = [
    ("Mouse", [(MouseButton(0x0001), "Left click"), (MouseButton(0x0002), "Right click"),
               (MouseButton(0x0004), "Middle click"), (MouseButton(0x0008), "Back"),
               (MouseButton(0x0010), "Forward")]),
    ("Scroll", [(Special(SPECIAL_CODES["tilt-left"]), "Scroll left"),
                (Special(SPECIAL_CODES["tilt-right"]), "Scroll right"),
                (Special(SPECIAL_CODES["scroll-up"]), "Scroll up"),
                (Special(SPECIAL_CODES["scroll-down"]), "Scroll down")]),
    ("Sensitivity", [(Special(SPECIAL_CODES["dpi-up"]), "DPI up"),
                     (Special(SPECIAL_CODES["dpi-down"]), "DPI down"),
                     (Special(SPECIAL_CODES["dpi-cycle"]), "DPI cycle"),
                     (Special(SPECIAL_CODES["dpi-default"]), "DPI default"),
                     (Special(SPECIAL_CODES["dpi-shift"]), "DPI shift (sniper)")]),
    ("Profiles", [(Special(SPECIAL_CODES["profile-next"]), "Next profile"),
                  (Special(SPECIAL_CODES["profile-prev"]), "Previous profile"),
                  (Special(SPECIAL_CODES["profile-cycle"]), "Cycle profiles")]),
    ("Layers", [(Special(SPECIAL_CODES["gshift"]), "G-Shift (hold)")]),
]

MEDIA = ["play-pause", "next-track", "prev-track", "stop", "mute", "volume-up", "volume-down",
         "browser-back", "browser-forward", "browser-refresh", "browser-home", "browser-search",
         "file-browser", "calculator", "mail", "brightness-up", "brightness-down"]

# (label, modifiers, character typed on the user's layout, or a key name)
SHORTCUTS = [
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
    title = "ASSIGNMENTS"
    icon = "assignments"
    mouse_mode = "assign"

    def __init__(self, *args):
        super().__init__(*args)
        self.slot = 5  # G6
        self.layer = 0
        title = QLabel("Assignments")
        title.setObjectName("Title")
        self.layout.addWidget(title)
        self.layer_tabs = Segmented(["Primary", "G-Shift"])
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
        self.default_btn = QPushButton("Restore default")
        self.default_btn.clicked.connect(self._restore_default)
        row.addWidget(self.default_btn)
        self.disable_btn = QPushButton("Disable")
        self.disable_btn.clicked.connect(lambda: self._assign(self._off_binding()))
        row.addWidget(self.disable_btn)
        row.addStretch()
        current.body.addLayout(row)
        self.layout.addWidget(current)

        self.categories = Segmented(["Commands", "Keys", "Media"])
        self.layout.addWidget(self.categories)
        self.stack = QStackedWidget()
        self.categories.changed.connect(self.stack.setCurrentIndex)
        self.layout.addWidget(self.stack)

        self.choice_lists = []
        commands = QWidget()
        col = QVBoxLayout(commands)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(10)
        for name, choices in COMMAND_GROUPS:
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
        col.addWidget(heading("Press a key or combination"))
        self.capture = KeyCapture()
        self.capture.captured.connect(lambda mods, usage: self._assign(Key(mods, usage)))
        col.addWidget(self.capture)
        col.addWidget(heading("Common shortcuts"))
        shortcuts = []
        for label, mods, char in SHORTCUTS:
            usage = keys.KEYS[char[1:]] if char.startswith("@") else self.keylabels.usage_for(char)
            binding = Key(mods, usage)
            shortcuts.append((binding, f"{label}   ·   {self.keylabels.combo(mods, usage)}"))
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
                answer = QMessageBox.question(
                    self.panel, "Remove left click?",
                    "No other button is set to Left click. Without one you can only click "
                    "with the keyboard or touchpad until you change it back.\n\nContinue?")
                if answer != QMessageBox.StandardButton.Yes:
                    self.refresh()
                    return
        slot, layer = self.slot, self.layer
        self.state.edit(lambda p: (p.gshift if layer else p.buttons).__setitem__(slot, binding))

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
        self.button_name.setText(labels.BUTTON_NAMES[self.slot])
        self.current.setText(("G-Shift layer: " if self.layer else "") + labels.binding(current, self.keylabels))
        for lst in self.choice_lists:
            match = next((v for v in lst.values if same_action(v, current)), None)
            lst.set_value(match)
        has_shift = any(isinstance(b, Special) and b.function == SPECIAL_CODES["gshift"] for b in profile.buttons)
        if self.layer and not has_shift:
            self.gshift_hint.setText("No button is set to G-Shift on the primary layer yet. "
                                     "Set one (G6 works well) to use this layer.")
        elif self.layer:
            self.gshift_hint.setText("While the G-Shift button is held, buttons do this instead.")
        else:
            self.gshift_hint.setText("")
        self.gshift_hint.setVisible(bool(self.gshift_hint.text()))
