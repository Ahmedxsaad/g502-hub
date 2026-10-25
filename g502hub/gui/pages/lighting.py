"""LIGHTSYNC page: onboard lighting per zone, plus live effects streamed by the app."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget

from ... import lightfx
from ...onboard import LedEffect
from .. import labels
from ..live import EFFECTS as LIVE_EFFECTS
from ..widgets import ChoiceList, ColorPicker, Segmented, SliderRow, Switcher, heading, muted
from . import Page

EFFECTS = [(0x01, "Fixed"), (0x0A, "Breathing"), (0x03, "Color cycle"), (0x00, "Off")]
AREAS = list(lightfx.AREA_LABELS.items())


def _column():
    w = QWidget()
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(14)
    return w, col


class LightingPage(Page):
    title = "LIGHTSYNC"
    icon = "lighting"
    mouse_mode = "light"

    def __init__(self, state, view, keylabels, live):
        super().__init__(state, view, keylabels)
        self.live = live
        self.zone = 0
        title = QLabel("Lighting")
        title.setObjectName("Title")
        self.layout.addWidget(title)
        self.mode = Segmented(["On the mouse", "Live effects"])
        self.mode.changed.connect(self._mode_changed)
        self.layout.addWidget(self.mode)
        self.stack = Switcher()
        self.stack.addWidget(self._onboard_panel())
        self.stack.addWidget(self._live_panel())
        self.layout.addWidget(self.stack)
        self.layout.addStretch()
        live.runningChanged.connect(lambda _: self._show_live_state())
        live.status.connect(self._live_status)

    # ------------------------------------------------------------ onboard

    def _onboard_panel(self):
        w, col = _column()
        col.addWidget(muted("Saved on the mouse, so it works without this app and on any computer.", "Faint"))
        self.zones = Segmented(["DPI lights", "Logo"])
        self.zones.changed.connect(self._zone_clicked)
        col.addWidget(self.zones)
        self.sync = QCheckBox("Same effect on both zones")
        self.sync.toggled.connect(self._sync_toggled)
        col.addWidget(self.sync)
        self.live_banner = muted("", "Faint")
        col.addWidget(self.live_banner)

        col.addWidget(heading("Effect"))
        self.effects = ChoiceList(EFFECTS, columns=2)
        self.effects.changed.connect(lambda _: self._apply(final=True))
        col.addWidget(self.effects)

        self.color_heading = heading("Color")
        col.addWidget(self.color_heading)
        self.picker = ColorPicker()
        self.picker.changed.connect(lambda _, final: self._apply(final))
        col.addWidget(self.picker)

        self.rate = SliderRow("Rate", 1000, 20000, "{:,} ms", step=100)
        self.rate.moved.connect(lambda _: self._apply(final=False))
        self.rate.committed.connect(lambda _: self._apply(final=True))
        col.addWidget(self.rate)
        self.brightness = SliderRow("Brightness", 1, 100, "{} %")
        self.brightness.moved.connect(lambda _: self._apply(final=False))
        self.brightness.committed.connect(lambda _: self._apply(final=True))
        col.addWidget(self.brightness)
        return w

    def _targets(self):
        return [0, 1] if self.sync.isChecked() else [self.zone]

    def _zone_clicked(self, zone):
        self.zone = zone
        self.refresh()

    def on_view_click(self, key):
        self.mode.set_index(0)
        self.stack.setCurrentIndex(0)
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
        if self.live.running:
            self.live.stop()  # editing the saved lighting: show it, not the live effect
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

    # ------------------------------------------------------------ live

    def _live_panel(self):
        w, col = _column()
        col.addWidget(muted("Made by G502 Hub while it runs. It keeps running in the tray when you "
                            "close the window. Turn it off and the mouse goes back to its saved lighting.",
                            "Faint"))
        col.addWidget(heading("Effect"))
        self.live_effects = ChoiceList(LIVE_EFFECTS, columns=2)
        self.live_effects.changed.connect(self._live_selected)
        col.addWidget(self.live_effects)
        self.live_toggle = QPushButton()
        self.live_toggle.setObjectName("Primary")
        self.live_toggle.clicked.connect(self._live_toggled)
        col.addWidget(self.live_toggle)
        self.live_state = muted("", "Faint")
        col.addWidget(self.live_state)
        self.live_options = Switcher()
        for key, _ in LIVE_EFFECTS:
            self.live_options.addWidget(getattr(self, f"_{key}_options")())
        col.addWidget(self.live_options)
        return w

    def _slider(self, col, effect, key, label, lo, hi, fmt, factor=100, step=1):
        """A slider bound to a live option stored as value / factor."""
        row = SliderRow(label, lo, hi, fmt, step=step)
        row.set_value(round(self.live.options[effect][key] * factor))
        row.moved.connect(lambda v: self.live.set_option(effect, key, v / factor, save=False))
        row.committed.connect(lambda v: self.live.set_option(effect, key, v / factor))
        col.addWidget(row)
        return row

    def _choices(self, col, effect, key, title, choices, columns=2):
        col.addWidget(heading(title))
        lst = ChoiceList(choices, columns=columns)
        lst.set_value(self.live.options[effect][key])
        lst.changed.connect(lambda v: self.live.set_option(effect, key, v))
        col.addWidget(lst)
        return lst

    def _screen_options(self):
        w, col = _column()
        col.addWidget(muted("Follows what's on your screen: the film or video you're watching, "
                            "or the game you're playing.", "Faint"))
        self._choices(col, "screen", "dpi_area", "DPI lights follow", AREAS)
        self._choices(col, "screen", "logo_area", "Logo follows", AREAS)
        self._choices(col, "screen", "vivid", "Style", [(True, "Vivid"), (False, "Average")])
        self._slider(col, "screen", "saturation", "Saturation", 50, 200, "{} %")
        self._slider(col, "screen", "brightness", "Brightness", 10, 150, "{} %")
        self._slider(col, "screen", "smoothing", "Smoothing", 0, 100, "{} %")
        other = QPushButton("Choose another screen…")
        other.clicked.connect(self.live.choose_another_screen)
        col.addWidget(other)
        return w

    def _audio_options(self):
        w, col = _column()
        col.addWidget(muted("Reacts to the sound your computer is playing.", "Faint"))
        self._choices(col, "audio", "style", "Style",
                      [("pulse", "Pulse"), ("spectrum", "Spectrum"), ("rainbow", "Rainbow beats")])
        self._slider(col, "audio", "sensitivity", "Sensitivity", 50, 300, "{} %")
        self._slider(col, "audio", "brightness", "Brightness", 10, 100, "{} %")
        col.addWidget(heading("Pulse color"))
        picker = ColorPicker()
        picker.set_color(QColor(self.live.options["audio"]["color"]))
        picker.changed.connect(lambda c, final: self.live.set_option("audio", "color", c.name(), save=final))
        col.addWidget(picker)
        return w

    def _wave_options(self):
        w, col = _column()
        col.addWidget(muted("A rainbow that flows from the DPI lights to the logo.", "Faint"))
        self._slider(col, "wave", "period", "Cycle time", 10, 200, lambda v: f"{v / 10:.1f} s", factor=10)
        self._slider(col, "wave", "saturation", "Saturation", 0, 100, "{} %")
        self._slider(col, "wave", "brightness", "Brightness", 10, 100, "{} %")
        reverse = QCheckBox("Flow from the logo to the DPI lights")
        reverse.setChecked(self.live.options["wave"]["reverse"])
        reverse.toggled.connect(lambda on: self.live.set_option("wave", "reverse", on))
        col.addWidget(reverse)
        return w

    def _dpi_options(self):
        w, col = _column()
        col.addWidget(muted("Both zones light up in the color of the DPI level you're on, so you "
                            "can see it at a glance.", "Faint"))
        col.addWidget(heading("Color for DPI level"))
        self.dpi_level_tabs = Segmented([str(n) for n in range(1, 6)])
        col.addWidget(self.dpi_level_tabs)
        self.dpi_picker = ColorPicker()
        col.addWidget(self.dpi_picker)

        def show_level(i):
            self.dpi_picker.set_color(QColor(self.live.options["dpi"]["colors"][i]))

        def picked(color, final):
            colors = list(self.live.options["dpi"]["colors"])
            colors[self.dpi_level_tabs.index()] = color.name()
            self.live.set_option("dpi", "colors", colors, save=final)

        self.dpi_level_tabs.changed.connect(show_level)
        self.dpi_picker.changed.connect(picked)
        show_level(0)
        return w

    def _live_selected(self, effect):
        self.live_options.setCurrentIndex([k for k, _ in LIVE_EFFECTS].index(effect))
        self.live.select(effect)
        self._show_live_state()

    def _live_toggled(self):
        if self.live.running:
            self.live.stop()
        else:
            self.live.start(self.live.selected)
        self._show_live_state()

    def _live_status(self, kind, text):
        self.live_state.setText(text)

    def _show_live_state(self):
        running = self.live.running
        self.live_toggle.setText("Turn off" if running else "Turn on")
        self.live_toggle.setObjectName("" if running else "Primary")
        self.live_toggle.style().unpolish(self.live_toggle)
        self.live_toggle.style().polish(self.live_toggle)
        self.live_effects.set_value(self.live.selected)
        self.live_options.setCurrentIndex([k for k, _ in LIVE_EFFECTS].index(self.live.selected))
        name = dict(LIVE_EFFECTS)[self.live.effect] if running else None
        self.live_banner.setText(f"{name} (a live effect) is showing on the mouse right now. "
                                 "Changing anything here turns it off." if running else "")
        self.live_banner.setVisible(running)

    def _mode_changed(self, i):
        self.stack.setCurrentIndex(i)

    # ------------------------------------------------------------ refresh

    def reset(self):
        profile = self.state.profile()
        if profile is not None:
            self.sync.blockSignals(True)
            self.sync.setChecked(profile.leds[0] == profile.leds[1])
            self.sync.blockSignals(False)
        if self.live.running:
            self.mode.set_index(1)
            self.stack.setCurrentIndex(1)
        self.refresh()

    def refresh(self):
        self._show_live_state()
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
