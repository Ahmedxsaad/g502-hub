"""Rule editing and a remote view of the background service's context."""

from .. import ipc, rules
from ..runtime.rules import RulesEngine as _RulesEngine


class RulesEngine(_RulesEngine):
    def start(self):
        self._timer.start()

    def _tick(self):
        try:
            snapshot = ipc.request('snapshot', timeout=1)
        except (OSError, RuntimeError, ValueError) as error:
            self.error = str(error)
            return
        active = snapshot['active_rule']
        context = snapshot['context']
        changed = context != self.context or active != (self.active.to_dict() if self.active else None)
        self.context = context
        self.active = rules.Rule.from_dict(active) if active else None
        self.seen_apps = snapshot['seen_apps']
        self.seen_media = snapshot['seen_media']
        self.error = snapshot['rules_error']
        if changed:
            self.changed.emit()
