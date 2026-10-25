"""LIGHTSYNC page: onboard lighting effects per zone, previewed live."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QLabel

from ...onboard import LedEffect
from .. import labels
from ..widgets import ChoiceList, ColorPicker, Segmented, SliderRow, heading, muted
from . import Page

EFFECTS = [(0x01, "Fixed"), (0x0A, "Breathing"), (0x03, "Color cycle"), (0x00, "Off")]


class LightingPage(Page):
    title = "LIGHTSYNC"
    icon = "lighting"
    mouse_mode = "light"

    def __init__(self, *args):
        super().__init__(*args)
        self.zone = 0
        title = QLabel("Lighting")
        title.setObjectName("Title")
        self.layout.addWidget(title)
        self.layout.addWidget(muted("Saved on the mouse, so it works without this app running.", "Faint"))

        self.zones = Segmented(["DPI lights", "Logo"])
        self.zones.changed.connect(self._zone_clicked)
        self.layout.addWidget(self.zones)
        self.sync = QCheckBox("Same effect on both zones")
        self.sync.toggled.connect(self._sync_toggled)
        self.layout.addWidget(self.sync)

        self.layout.addWidget(heading("Effect"))
        self.effects = ChoiceList(EFFECTS, columns=2)
        self.effects.changed.connect(lambda _: self._apply(final=True))
        self.layout.addWidget(self.effects)

        self.color_heading = heading("Color")
        self.layout.addWidget(self.color_heading)
        self.picker = ColorPicker()
        self.picker.changed.connect(lambda _, final: self._apply(final))
        self.layout.addWidget(self.picker)

        self.rate = SliderRow("Rate", 1000, 20000, "{:,} ms", step=100)
        self.rate.moved.connect(lambda _: self._apply(final=False))
        self.rate.committed.connect(lambda _: self._apply(final=True))
        self.layout.addWidget(self.rate)
        self.brightness = SliderRow("Brightness", 1, 100, "{} %")
        self.brightness.moved.connect(lambda _: self._apply(final=False))
        self.brightness.committed.connect(lambda _: self._apply(final=True))
        self.layout.addWidget(self.brightness)
        self.layout.addStretch()

    def _targets(self):
        return [0, 1] if self.sync.isChecked() else [self.zone]

    def _zone_clicked(self, zone):
        self.zone = zone
        self.refresh()

    def on_view_click(self, key):
        self.zone = 0 if key == "zone0" else 1
        self.zones.set_index(self.zone)
        self.refresh()

    def _sync_toggled(self, on):
        if on:
            self._apply(final=True)  # copy the shown effect to the other zone
        else:
            self.refresh()

    def _effect(self):
        effect = self.effects.values[self.effects.group.checkedId()] if self.effects.group.checkedButton() else 0x01
        c = self.picker.color()
        rgb = (c.red(), c.green(), c.blue())
        if effect == 0x01:
            return LedEffect.fixed(rgb)
        if effect == 0x0A:
            return LedEffect.breathing(rgb, self.rate.slider.value(), self.brightness.slider.value())
        if effect == 0x03:
            return LedEffect.cycle(self.rate.slider.value(), self.brightness.slider.value())
        return LedEffect.off()

    def _apply(self, final):
        profile = self.state.profile()
        if profile is None:
            return
        effect = self._effect()
        self._show_controls(effect.effect)
        zones = self._targets()
        self.view.set_leds({z: effect for z in zones})
        for z in zones:
            self.state.preview_led(z, effect)
        if final:
            def change(p):
                for z in zones:
                    # Keep the stored bytes when the effect didn't actually change
                    if p.leds[z] != effect:
                        p.leds[z] = effect
                        p.alt_leds[z] = effect
            # The preview already shows it; no profile reload needed
            self.state.edit(change, reload=False)

    def _show_controls(self, effect):
        has_color = effect in (0x01, 0x0A)
        self.color_heading.setVisible(has_color)
        self.picker.setVisible(has_color)
        self.rate.setVisible(effect in (0x0A, 0x03))
        self.brightness.setVisible(effect in (0x0A, 0x03))

    def reset(self):
        profile = self.state.profile()
        if profile is not None:
            self.sync.blockSignals(True)
            self.sync.setChecked(profile.leds[0] == profile.leds[1])
            self.sync.blockSignals(False)
        self.refresh()

    def refresh(self):
        profile = self.state.profile()
        if profile is None:
            return
        self.view.set_leds({0: profile.leds[0], 1: profile.leds[1]})
        self.view.set_selected(["zone0", "zone1"] if self.sync.isChecked() else [f"zone{self.zone}"])
        led = profile.leds[self.zone]
        known = led.effect in labels.EFFECT_LABELS
        self.effects.set_value(led.effect if known else None)
        if led.effect in (0x01, 0x0A):
            self.picker.set_color(QColor(*led.color))
        if led.effect in (0x0A, 0x03):
            self.rate.set_value(led.period_ms)
            self.brightness.set_value(led.brightness)
        else:
            self.rate.set_value(8000)
            self.brightness.set_value(100)
        self._show_controls(led.effect)
