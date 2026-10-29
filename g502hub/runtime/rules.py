"""Runs the rules: watches what's happening and applies the first matching rule."""

from PySide6.QtCore import QObject, QTimer, Signal

from .. import rules, settings
from ..rules import Rule

TICK_MS = 300


class RulesEngine(QObject):
    changed = Signal()  # the context, the rules or the matching rule changed

    def __init__(self, state, live):
        super().__init__()
        self.state = state
        self.live = live
        self.rules = rules.load(settings.load().get("rules"))
        self.watcher = None
        self.context = None
        self.active = None       # the matching Rule
        self.error = None
        self.seen_apps = []    # recently active window classes, newest first
        self.seen_media = []   # recently playing media titles, newest first
        self._slot_before = None  # where to go back to when a rule that switched slots ends
        self._timer = QTimer(self, interval=TICK_MS)
        self._timer.timeout.connect(self._tick)

    def start(self):
        try:
            from ..context import ContextWatcher
        except ImportError as e:
            self.error = f"Can't watch apps and games: {e}"
            return
        self.watcher = ContextWatcher()
        self.watcher.start()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        if self.watcher is not None:
            self.watcher.stop()

    # ------------------------------------------------------------ editing

    def save(self):
        settings.update(rules=[r.to_dict() for r in self.rules])
        self.changed.emit()

    def add(self, rule):
        self.rules.append(rule)
        self.save()

    def update(self, rule):
        self.rules = [rule if r.id == rule.id else r for r in self.rules]
        self.save()

    def remove(self, rule_id):
        self.rules = [r for r in self.rules if r.id != rule_id]
        self.save()

    def move(self, rule_id, step):
        i = next(n for n, r in enumerate(self.rules) if r.id == rule_id)
        j = min(max(i + step, 0), len(self.rules) - 1)
        self.rules.insert(j, self.rules.pop(i))
        self.save()

    # ------------------------------------------------------------ running

    def _tick(self):
        ctx = self.watcher.current()
        if ctx != self.context:
            self.context = ctx
            self._remember(self.seen_apps, ctx.app)
            for m in ctx.media:
                if m.status == "Playing":
                    self._remember(self.seen_media, m.title)
            self.changed.emit()
        rule = rules.first_match(self.rules, ctx)
        if (rule.to_dict() if rule else None) != (self.active.to_dict() if self.active else None):
            self._switch(rule)
        # Recomputed every tick, so e.g. "any game" follows the game that's running
        self.live.set_override(None if rule is None or not rule.lighting else {
            "lighting": rule.lighting, "color": rule.color, "period_ms": rule.period_ms,
            "game": ctx.game, "name": rule.name})

    @staticmethod
    def _remember(seen, value, keep=12):
        if value:
            if value in seen:
                seen.remove(value)
            seen.insert(0, value)
            del seen[keep:]

    def _switch(self, rule):
        before, self.active = self.active, rule
        s = self.state
        if rule and rule.slot and s.connected:
            if self._slot_before is None:
                self._slot_before = s.active_slot
            if s.active_slot != rule.slot:
                s.activate(rule.slot)
        elif self._slot_before is not None:
            # Go back, unless the user moved to another slot meanwhile
            if s.connected and before is not None and s.active_slot == before.slot:
                s.activate(self._slot_before)
            self._slot_before = None
        if rule:
            s.status.emit("ok", f"Rule “{rule.name}”: {rule.describe_action()}")
        elif before:
            s.status.emit("info", f"Rule “{before.name}” ended")
        self.changed.emit()
