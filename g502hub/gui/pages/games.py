"""GAMES & APPS page: rules that change lighting or profile for a game, app, window or video."""

import copy
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QPushButton, QVBoxLayout, QWidget)

from ... import context, rules
from ...rules import LIGHTING, TRIGGERS, Rule
from .. import theme
from ..widgets import Card, ChoiceList, ColorPicker, SliderRow, Switcher, heading, muted
from . import Page


class RuleCard(Card):
    def __init__(self, page, rule, active, game_names):
        super().__init__()
        self.setProperty("active", "true" if active else "false")
        top = QHBoxLayout()
        name = QLabel(rule.name)
        name.setStyleSheet("font-weight: 600; font-size: 14px;")
        top.addWidget(name)
        if active:
            badge = QLabel("ACTIVE")
            badge.setStyleSheet(f"color: {theme.ACCENT}; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
            top.addWidget(badge)
        top.addStretch()
        on = QCheckBox()
        on.setToolTip("Turn this rule on or off")
        on.setChecked(rule.enabled)
        on.toggled.connect(lambda v: page.engine.update(replace(rule, enabled=v)))
        top.addWidget(on)
        self.body.addLayout(top)
        self.body.addWidget(muted(rule.describe_trigger(game_names)))
        action = QHBoxLayout()
        if rule.lighting in ("color", "breathing"):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {rule.color}; font-size: 15px;")
            action.addWidget(dot)
        action.addWidget(muted(rule.describe_action(), "Faint"), 1)
        self.body.addLayout(action)
        buttons = QHBoxLayout()
        edit = QPushButton("Edit")
        edit.clicked.connect(lambda: page.edit(rule))
        buttons.addWidget(edit)
        for text, step, tip in (("↑", -1, "Check this rule earlier"), ("↓", 1, "Check this rule later")):
            b = QPushButton(text)
            b.setObjectName("Flat")
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, s=step: page.engine.move(rule.id, s))
            buttons.addWidget(b)
        buttons.addStretch()
        delete = QPushButton("Delete")
        delete.setObjectName("Flat")
        delete.clicked.connect(lambda: page.engine.remove(rule.id))
        buttons.addWidget(delete)
        self.body.addLayout(buttons)


class GamesPage(Page):
    title = "GAMES & APPS"
    icon = "games"

    def __init__(self, state, view, keylabels, engine):
        super().__init__(state, view, keylabels)
        self.engine = engine
        self.editing = None
        self.pages = Switcher()
        self.pages.addWidget(self._list_page())
        self.pages.addWidget(self._editor_page())
        self.layout.addWidget(self.pages)
        self.layout.addStretch()
        engine.changed.connect(self._engine_changed)

    # ------------------------------------------------------------ list

    def _list_page(self):
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        title = QLabel("Games & apps")
        title.setObjectName("Title")
        col.addWidget(title)
        col.addWidget(muted("Make the mouse react to what you're doing: a game, an app, a YouTube "
                            "video or an anime. The first rule that matches wins; when none does, "
                            "your normal lighting and profile come back.", "Faint"))
        now = Card()
        now.body.addWidget(heading("Right now"))
        self.now = muted("")
        self.now.setTextFormat(Qt.TextFormat.PlainText)
        now.body.addWidget(self.now)
        col.addWidget(now)
        col.addWidget(heading("Rules"))
        self.rule_list = QVBoxLayout()
        self.rule_list.setSpacing(10)
        col.addLayout(self.rule_list)
        self.add_btn = QPushButton("+  Add rule")
        self.add_btn.setObjectName("Primary")
        self.add_menu = QMenu(self.add_btn)
        self.add_menu.aboutToShow.connect(self._fill_add_menu)
        self.add_btn.setMenu(self.add_menu)
        col.addWidget(self.add_btn)
        return w

    def _game_names(self):
        names = {str(appid): name for appid, name in context.installed_games()}
        ctx = self.engine.context
        if ctx and ctx.game:
            names[str(ctx.game.appid)] = ctx.game.name
        return names

    def _fill_add_menu(self):
        m = self.add_menu
        m.clear()
        ctx = self.engine.context
        now = []
        if ctx and ctx.game:
            now.append((f"While {ctx.game.name} is running",
                        Rule(ctx.game.name, "game", str(ctx.game.appid), lighting="art")))
        for title in self.engine.seen_media[:5]:
            short = title if len(title) <= 40 else title[:39] + "…"
            now.append((f"While “{short}” plays", Rule(short, "media", title, lighting="color")))
        for app in self.engine.seen_apps[:5]:
            now.append((f"While {app} is in front", Rule(app, "app", app, lighting="color")))
        if now:
            sub = m.addMenu("For something you did recently")
            for text, rule in now:
                sub.addAction(text, lambda r=rule: self.edit(r, new=True))
        m.addSection("Ready-made")
        for template in rules.TEMPLATES:
            m.addAction(f"{template.name}  ·  {template.describe_action()}",
                        lambda t=template: self.edit(replace(t, id=rules.new_id()), new=True))
        m.addSeparator()
        m.addAction("Blank rule", lambda: self.edit(Rule("New rule", "media", ""), new=True))

    def _show_rules(self):
        while self.rule_list.count():
            item = self.rule_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        names = self._game_names()
        active = self.engine.active.id if self.engine.active else None
        for rule in self.engine.rules:
            self.rule_list.addWidget(RuleCard(self, rule, rule.id == active, names))
        if not self.engine.rules:
            self.rule_list.addWidget(muted("No rules yet. Try YouTube from the ready-made ones.", "Faint"))

    def _show_now(self):
        e = self.engine
        if e.error or e.watcher is None:
            self.now.setText(e.error or "Not watching yet.")
            return
        ctx = e.context
        lines = []
        if ctx is None:
            lines.append("Looking…")
        else:
            if ctx.game:
                lines.append(f"Game: {ctx.game.name}")
            if ctx.app:
                title = ctx.title if len(ctx.title) <= 60 else ctx.title[:59] + "…"
                lines.append(f"In front: {ctx.app}" + (f" — {title}" if title else ""))
            for m in [m for m in ctx.media if m.status == "Playing"][:2]:
                lines.append(f"Playing: {m.title or '(untitled)'} · {m.identity or m.player}")
        lines.append(f"Rule: {e.active.name}" if e.active else "No rule matches")
        for source, problem in (e.watcher.errors or {}).items():
            lines.append(f"({source}: {problem})")
        self.now.setText("\n".join(lines))

    def _engine_changed(self):
        self._show_now()
        if self.pages.currentIndex() == 0:
            self._show_rules()

    # ------------------------------------------------------------ editor

    def _editor_page(self):
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        self.editor_title = QLabel("Rule")
        self.editor_title.setObjectName("Title")
        col.addWidget(self.editor_title)
        col.addWidget(heading("Name"))
        self.name = QLineEdit()
        self.name.setMaxLength(40)
        col.addWidget(self.name)

        col.addWidget(heading("When"))
        self.trigger = ChoiceList(list(TRIGGERS.items()), columns=2)
        self.trigger.changed.connect(lambda _: self._show_value_inputs())
        col.addWidget(self.trigger)
        self.game_box = QComboBox()
        col.addWidget(self.game_box)
        self.value = QLineEdit()
        col.addWidget(self.value)
        self.recent = QComboBox()
        self.recent.activated.connect(lambda i: self.value.setText(self.recent.itemData(i) or self.value.text()))
        col.addWidget(self.recent)
        self.value_hint = muted("", "Faint")
        col.addWidget(self.value_hint)

        col.addWidget(heading("Lighting"))
        self.lighting = ChoiceList([(None, "Don't change")] + list(LIGHTING.items()), columns=2)
        self.lighting.changed.connect(lambda _: self._show_lighting_inputs())
        col.addWidget(self.lighting)
        self.color = ColorPicker()
        col.addWidget(self.color)
        self.period = SliderRow("Breathing speed", 1000, 12000, "{:,} ms", step=100)
        col.addWidget(self.period)
        self.lighting_hint = muted("", "Faint")
        col.addWidget(self.lighting_hint)

        col.addWidget(heading("Profile slot"))
        col.addWidget(muted("Switch to an onboard profile (its DPI levels, buttons and report rate) "
                            "while the rule matches.", "Faint"))
        self.slot = ChoiceList([(None, "Don't change")] + [(n, f"Slot {n}") for n in range(1, 6)], columns=3)
        col.addWidget(self.slot)

        row = QHBoxLayout()
        save = QPushButton("Save rule")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        row.addWidget(save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._close_editor)
        row.addWidget(cancel)
        row.addStretch()
        col.addLayout(row)
        return w

    def edit(self, rule, new=False):
        self.editing, self.editing_new = copy.deepcopy(rule), new
        r = self.editing
        self.editor_title.setText("New rule" if new else "Edit rule")
        self.name.setText(r.name)
        self.trigger.set_value(r.trigger)
        self.game_box.clear()
        self.game_box.addItem("Any game", rules.ANY_GAME)
        for appid, name in context.installed_games():
            self.game_box.addItem(name, str(appid))
        if r.trigger == "game" and self.game_box.findData(r.value) < 0:
            self.game_box.addItem(self._game_names().get(r.value, f"Steam app {r.value}"), r.value)
        self.game_box.setCurrentIndex(max(self.game_box.findData(r.value), 0))
        self.value.setText("" if r.trigger == "game" else r.value)
        self.lighting.set_value(r.lighting)
        self.color.set_color(QColor(r.color))
        self.period.set_value(r.period_ms)
        self.slot.set_value(r.slot)
        self._show_value_inputs()
        self._show_lighting_inputs()
        self.pages.setCurrentIndex(1)
        self.panel.verticalScrollBar().setValue(0)

    def _show_value_inputs(self):
        trigger = self.trigger.value()
        self.game_box.setVisible(trigger == "game")
        self.value.setVisible(trigger != "game")
        self.recent.clear()
        if trigger == "app":
            self.value.setPlaceholderText("Window class, e.g. firefox, mpv, org.kde.dolphin")
            seen = self.engine.seen_apps
            self.value_hint.setText("Matches the app exactly.")
        elif trigger == "title":
            self.value.setPlaceholderText("Text in the window title, e.g. YouTube")
            seen = []
            self.value_hint.setText("Matches any window title containing this text, upper or lower case.")
        elif trigger == "media":
            self.value.setPlaceholderText("Text in the title, artist or page, e.g. youtube or One Piece")
            seen = self.engine.seen_media
            self.value_hint.setText("Matches while something is playing (browsers, mpv, VLC, Spotify, "
                                    "anime apps…) and its title, artist or web address contains this text.")
        else:
            seen = []
            self.value_hint.setText("Steam and Proton games are found automatically, "
                                    "including non-Steam games added to Steam.")
        if seen:
            self.recent.addItem("Recently seen…", None)
            for v in seen:
                self.recent.addItem(v if len(v) <= 50 else v[:49] + "…", v)
        self.recent.setVisible(bool(seen))

    def _show_lighting_inputs(self):
        kind = self.lighting.value()
        self.color.setVisible(kind in ("color", "breathing"))
        self.period.setVisible(kind == "breathing")
        hints = {
            "art": "Takes two colors from the game's cover art in your Steam library.",
            "game": "Lets the game drive the lights: live events in CS2 and Dota 2, and Proton games "
                    "with Logitech lighting once the LIGHTSYNC bridge is on (Settings). Other games "
                    "get their cover art colors.",
            "screen": "Uses your Screen sampler settings from Lightsync.",
            "audio": "Uses your Audio visualizer settings from Lightsync.",
            "wave": "Uses your Color wave settings from Lightsync.",
            "dpi": "Uses your DPI colors from Lightsync.",
        }
        self.lighting_hint.setText(hints.get(kind, ""))
        self.lighting_hint.setVisible(kind in hints)

    def _save(self):
        r = self.editing
        r.name = self.name.text().strip() or "Rule"
        r.trigger = self.trigger.value() or "media"
        r.value = self.game_box.currentData() if r.trigger == "game" else self.value.text().strip()
        r.lighting = self.lighting.value()
        r.color = self.color.color().name()
        r.period_ms = self.period.slider.value()
        r.slot = self.slot.value()
        if not r.value:
            self.value_hint.setText("Type what to look for first.")
            return
        if self.editing_new:
            self.engine.add(r)
        else:
            self.engine.update(r)
        self._close_editor()

    def _close_editor(self):
        self.editing = None
        self.pages.setCurrentIndex(0)
        self._show_rules()

    # ------------------------------------------------------------ page

    def refresh(self):
        self.slot_names()
        self._show_now()
        if self.pages.currentIndex() == 0:
            self._show_rules()

    def slot_names(self):
        for n, button in enumerate(self.slot.group.buttons()):
            value = self.slot.values[n]
            if value:
                profile = self.state.profile(value) if self.state.profiles else None
                button.setText(f"Slot {value}" + (f" · {profile.name}" if profile and profile.name else ""))
