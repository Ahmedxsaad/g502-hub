"""Macros: the user's list, which buttons play them, and playing the app ones.

A macro stored in the mouse is a binding the firmware plays by itself. A
macro run by the app leaves its button disabled in the mouse; Mouse Button
Spy reports the press and the app plays the macro through a virtual input
device, so it can do anything the keyboard and mouse can.
"""

from PySide6.QtCore import QObject, Qt, Signal, Slot

from .. import macros, onboard, settings
from ..onboard import SPECIAL_CODES, Special

SPY_FEATURE = 0x8110


def _key(slot, layer, button):
    return f"{slot}:{layer}:{button}"


class MacroEngine(QObject):
    changed = Signal()
    _buttons_changed = Signal()

    def __init__(self, state, keylabels):
        super().__init__()
        self.state = state
        self.keylabels = keylabels
        saved = settings.load()
        self.macros = macros.load(saved.get("macros"))
        self.app_buttons = dict(saved.get("app_macros", {}))  # "slot:layer:button" -> macro id
        self.spy = self.player = None
        self.error = None
        self._mask = 0
        self._starting = False
        self._buttons_changed.connect(self._tick, Qt.ConnectionType.QueuedConnection)
        state.connectedChanged.connect(lambda _: self.sync(restart=True))

    # ------------------------------------------------------------ the list

    def get(self, macro_id):
        return next((m for m in self.macros if m.id == macro_id), None)

    def save(self, macro):
        """Add or update a macro; one stored in the mouse is rewritten where it lives."""
        self.macros = [macro if m.id == macro.id else m for m in self.macros]
        if not any(m.id == macro.id for m in self.macros):
            self.macros.append(macro)
        self._persist()
        if macro.target == "mouse" and self.onboard_uses(macro.id):
            self.write_to_mouse(macro)
        if macro.target == "app" and self.onboard_uses(macro.id):
            self._move_to_app(macro)
        if macro.target == "mouse" and self.app_uses(macro.id):
            self._move_to_mouse(macro)

    def delete(self, macro_id):
        for slot, layer, button in self.onboard_uses(macro_id):
            self._set_binding(slot, layer, button, onboard.Disabled())
        self.app_buttons = {k: v for k, v in self.app_buttons.items() if v != macro_id}
        self.macros = [m for m in self.macros if m.id != macro_id]
        self._persist()
        self.state.free_macro_pages()
        self.sync()

    def _persist(self):
        settings.update(macros=[m.to_dict() for m in self.macros], app_macros=self.app_buttons)
        self.changed.emit()

    # ------------------------------------------------------------ where they're used

    def onboard_sector(self, macro_id):
        sector = settings.load().get("macro_pages", {}).get(macro_id)
        return int(sector) if sector is not None else None

    def onboard_uses(self, macro_id):
        sector = self.onboard_sector(macro_id)
        return self.state.macro_references(sector) if sector is not None else []

    def app_uses(self, macro_id):
        out = []
        for key, mid in self.app_buttons.items():
            if mid == macro_id:
                slot, layer, button = (int(x) for x in key.split(":"))
                out.append((slot, layer, button))
        return out

    def uses(self, macro_id):
        return sorted(self.onboard_uses(macro_id) + self.app_uses(macro_id))

    def macro_on(self, slot, layer, button, binding):
        """The macro a button plays, if any (stored in the mouse or run by the app)."""
        mid = self.app_buttons.get(_key(slot, layer, button))
        if mid:
            return self.get(mid)
        if isinstance(binding, onboard.Macro):
            owned = settings.load().get("macro_pages", {})
            mid = next((m for m, n in owned.items() if int(n) == binding.page), None)
            return self.get(mid) if mid else None
        return None

    # ------------------------------------------------------------ assigning

    def _set_binding(self, slot, layer, button, binding):
        self.state.edit(lambda p: (p.gshift if layer else p.buttons).__setitem__(button, binding), slot=slot)

    def assign(self, slot, layer, button, macro_id, done=None):
        """Make a button play a macro. done(error) when it's in place."""
        macro = self.get(macro_id)
        self.unassign_app(slot, layer, button)
        if macro.target == "app":
            self.app_buttons[_key(slot, layer, button)] = macro_id
            self._persist()
            self._set_binding(slot, layer, button, onboard.Disabled())
            self.sync()
            if done:
                done(None)
            return
        try:
            data = macros.to_onboard(macro, self.keylabels.typing)
        except macros.MacroError as e:
            if done:
                done(e)
            return

        def stored(sector, error):
            if not error:
                self._set_binding(slot, layer, button, onboard.Macro(page=sector, offset=0))
                self.state.free_macro_pages(keep={macro_id})
            if done:
                done(error)
        self.state.store_macro(macro_id, data, stored)

    def unassign_app(self, slot, layer, button):
        """Forget an app macro on a button (it's getting another assignment)."""
        if self.app_buttons.pop(_key(slot, layer, button), None):
            self._persist()
            self.sync()

    def write_to_mouse(self, macro, done=None):
        try:
            data = macros.to_onboard(macro, self.keylabels.typing)
        except macros.MacroError as e:
            self.state.status.emit("error", f"Couldn't save “{macro.name}” on the mouse: {e}")
            return
        self.state.store_macro(macro.id, data, lambda _, e: done and done(e))

    def _move_to_app(self, macro):
        for slot, layer, button in self.onboard_uses(macro.id):
            self.assign(slot, layer, button, macro.id)
        self.state.free_macro_pages()

    def _move_to_mouse(self, macro):
        for slot, layer, button in self.app_uses(macro.id):
            self.assign(slot, layer, button, macro.id)

    # ------------------------------------------------------------ playing app macros

    def sync(self, restart=False):
        """Run the button spy and the player only while some button uses an app macro."""
        want = bool(self.app_buttons) and self.state.connected
        if restart or not want:
            self._stop()
        if want and self.spy is None and not self._starting:
            self._start()

    def _start(self):
        from ..effects.macroplayer import MacroPlayer
        from ..effects.spy import ButtonSpy
        self._starting = True
        if self.player is None:
            self.player = MacroPlayer()

        def job(dev):
            dev.spy_start()
            return dev.path, dev.hidpp.feature_index(SPY_FEATURE)

        def started(result, error):
            self._starting = False
            if error or not result[1]:
                self.error = f"Can't watch the buttons: {error or 'Mouse Button Spy missing'}"
                self.state.status.emit("error", self.error)
                return
            self.error = None
            self.spy = ButtonSpy(*result, on_change=self._buttons_changed.emit)
            self.spy.start()
            self._mask = 0
        self.state.bridge.call(job, started)

    def _stop(self):
        if self.spy is not None:
            self.spy.stop()
            self.spy = None
            if self.state.connected:
                self.state.bridge.call(lambda dev: dev.spy_stop())
        if self.player is not None:
            self.player.stop_all()

    def shutdown(self):
        self._stop()
        if self.player is not None:
            self.player.close()
            self.player = None

    def _gshift_held(self, mask):
        profile = self.state.profile()
        if profile is None:
            return False
        return any(mask & (1 << i) for i, b in enumerate(profile.buttons[:16])
                   if isinstance(b, Special) and b.function == SPECIAL_CODES["gshift"])

    @Slot()
    def _tick(self):
        if self.spy is None:
            return
        slot = self.state.active_slot
        for old, new in self.spy.changes():
            layer = 1 if self._gshift_held(new | old) else 0
            for button in range(16):
                bit = 1 << button
                if (old ^ new) & bit == 0:
                    continue
                key = (slot, layer, button)
                if not new & bit:  # released: stop whatever this button started, on either layer
                    self.player.release(key)
                    self.player.release((slot, 1 - layer, button))
                    continue
                mid = self.app_buttons.get(_key(*key))
                macro = self.get(mid) if mid else None
                if macro is not None:
                    try:
                        events = macros.expand(macro, self.keylabels.typing)
                    except macros.MacroError as e:
                        self.state.status.emit("error", f"“{macro.name}”: {e}")
                        continue
                    self.player.press(key, events, macro.mode)
