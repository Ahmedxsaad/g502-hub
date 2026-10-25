"""Small reusable widgets: segmented tabs, color picker, slider rows, key capture."""

from math import atan2, cos, hypot, pi, sin

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QConicalGradient, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from .. import keys, settings
from . import theme


def heading(text):
    label = QLabel(text.upper())
    label.setObjectName("Heading")
    return label


def muted(text, name="Muted"):
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(8)


class LedSwatch(QWidget):
    """A small dot showing an LedEffect: its color, a rainbow for color cycle, a ring when off."""

    def __init__(self, size=14, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.effect = None

    def set_effect(self, effect):
        self.effect = effect
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        e = self.effect
        if e is None or e.effect == 0x00:
            p.setPen(QPen(QColor(theme.FAINT), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
        elif e.effect == 0x03:
            g = QConicalGradient(r.center(), 90)
            for i in range(7):
                g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 0.85, 1))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(*e.color))
        p.drawEllipse(r)


class Switcher(QWidget):
    """Shows one of its pages at a time and takes that page's size (unlike QStackedWidget)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self.pages = []
        self._current = 0

    def addWidget(self, page):
        self.pages.append(page)
        self._col.addWidget(page)
        page.setVisible(len(self.pages) - 1 == self._current)

    def setCurrentIndex(self, i):
        self._current = i
        for n, page in enumerate(self.pages):
            page.setVisible(n == i)

    def currentIndex(self):
        return self._current


class Segmented(QWidget):
    """A row of exclusive tab-like buttons."""

    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, text in enumerate(labels):
            b = QPushButton(text.upper())
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b, i)
            row.addWidget(b)
        row.addStretch()
        self.group.button(0).setChecked(True)
        self.group.idClicked.connect(self.changed)

    def index(self):
        return self.group.checkedId()

    def set_index(self, i):
        self.group.button(i).setChecked(True)


class ChoiceList(QWidget):
    """Exclusive list of large buttons (effect types, actions...)."""

    changed = Signal(object)

    def __init__(self, choices, columns=1, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.group = QButtonGroup(self)
        self.values = []
        for i, (value, label) in enumerate(choices):
            b = QPushButton(label)
            b.setObjectName("Choice")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b, i)
            self.values.append(value)
            grid.addWidget(b, i // columns, i % columns)
        self.group.idClicked.connect(lambda i: self.changed.emit(self.values[i]))

    def set_value(self, value):
        if value in self.values:
            self.group.button(self.values.index(value)).setChecked(True)
        else:
            checked = self.group.checkedButton()
            if checked:
                self.group.setExclusive(False)
                checked.setChecked(False)
                self.group.setExclusive(True)


class SliderRow(QWidget):
    """Label, value text and a slider. `moved` fires while dragging, `committed` on release."""

    moved = Signal(int)
    committed = Signal(int)

    def __init__(self, label, lo, hi, fmt="{}", step=1, parent=None):
        super().__init__(parent)
        self.fmt = fmt if callable(fmt) else fmt.format  # "{} %" or a function of the value
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(heading(label))
        top.addStretch()
        self.value_label = QLabel()
        self.value_label.setObjectName("Muted")
        top.addWidget(self.value_label)
        col.addLayout(top)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setSingleStep(step)
        self.slider.setPageStep(step * 10)
        col.addWidget(self.slider)
        self.slider.valueChanged.connect(self._changed)
        self.slider.sliderReleased.connect(lambda: self.committed.emit(self.slider.value()))

    def _changed(self, v):
        self.value_label.setText(self.fmt(v))
        self.moved.emit(v)
        if not self.slider.isSliderDown():
            self.committed.emit(v)  # keyboard or click on the groove

    def set_value(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.value_label.setText(self.fmt(v))


class _HueSatWheel(QWidget):
    """Hue around, saturation outwards, like G HUB's color wheel."""

    picked = Signal(float, float, bool)  # hue, saturation, final

    def __init__(self, size=220):
        super().__init__()
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.hue, self.sat, self.val = 0.0, 1.0, 1.0
        self._image = self._render(size)

    @staticmethod
    def _render(size, dpr=2):
        n = size * dpr
        y, x = np.mgrid[0:n, 0:n].astype(np.float32)
        c = (n - 1) / 2
        dx, dy = (x - c) / c, (c - y) / c
        r = np.hypot(dx, dy)
        hue6 = (np.arctan2(dy, dx) / (2 * np.pi) % 1.0) * 6
        # HSV -> RGB at full value: f(n) = 1 - S * clamp(min(k, 4 - k), 0, 1), k = (n + H/60) mod 6
        k = (np.array([5, 3, 1], np.float32) + hue6[..., None]) % 6
        rgb = 1 - np.clip(r, 0, 1)[..., None] * np.clip(np.minimum(k, 4 - k), 0, 1)
        alpha = np.clip((1 - r) * c + 0.5, 0, 1)[..., None]  # antialiased rim
        bgra = np.concatenate([rgb[..., ::-1] * alpha, alpha], -1)  # premultiplied, memory order
        data = (bgra * 255 + 0.5).astype(np.uint8).tobytes()
        image = QImage(data, n, n, n * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        image.setDevicePixelRatio(dpr)
        return image

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawImage(0, 0, self._image)
        if self.val < 1:  # show the chosen brightness over the whole wheel
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, int((1 - self.val) * 255)))
            p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        c = self.width() / 2
        a = self.hue * 2 * pi
        pos = QPointF(c + cos(a) * self.sat * (c - 1), c - sin(a) * self.sat * (c - 1))
        p.setPen(QPen(QColor(0, 0, 0, 120), 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pos, 9, 9)
        p.setPen(QPen(QColor("white"), 2.5))
        p.setBrush(QColor.fromHsvF(self.hue, self.sat, self.val))
        p.drawEllipse(pos, 9, 9)

    def _pick(self, pos, final):
        c = self.width() / 2
        dx, dy = (pos.x() - c) / c, (c - pos.y()) / c
        self.hue = (atan2(dy, dx) / (2 * pi)) % 1.0
        self.sat = min(hypot(dx, dy), 1.0)
        self.update()
        self.picked.emit(self.hue, self.sat, final)

    def mousePressEvent(self, e):
        self._pick(e.position(), False)

    def mouseMoveEvent(self, e):
        self._pick(e.position(), False)

    def mouseReleaseEvent(self, e):
        self._pick(e.position(), True)


class _ValueBar(QWidget):
    """Brightness of the chosen hue, black to full."""

    picked = Signal(float, bool)

    def __init__(self):
        super().__init__()
        self.hue, self.sat, self.val = 0.0, 1.0, 1.0
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(9, 4, -9, -4)
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, QColor("black"))
        g.setColorAt(1, QColor.fromHsvF(self.hue, self.sat, 1))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, 5, 5)
        x = r.left() + self.val * r.width()
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(QColor.fromHsvF(self.hue, self.sat, self.val))
        p.drawEllipse(QPointF(x, self.height() / 2), 7, 7)

    def _pick(self, pos, final):
        r = QRectF(self.rect()).adjusted(9, 4, -9, -4)
        self.val = min(max((pos.x() - r.left()) / max(r.width(), 1), 0), 1)
        self.update()
        self.picked.emit(self.val, final)

    def mousePressEvent(self, e):
        self._pick(e.position(), False)

    def mouseMoveEvent(self, e):
        self._pick(e.position(), False)

    def mouseReleaseEvent(self, e):
        self._pick(e.position(), True)


SWATCHES = ["#ff0000", "#ff6a00", "#ffd400", "#3ddc84", "#00ffd5", "#14b4ff",
            "#2f4bff", "#8000ff", "#ff2fd6", "#ffffff"]
MAX_SAVED = 10


class ColorPicker(QWidget):
    """Hue/saturation wheel, brightness bar, hex and RGB fields, presets and saved colors.

    `changed(QColor, final)` fires live while dragging (final=False) and once on release.
    """

    changed = Signal(QColor, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        self.wheel = _HueSatWheel()
        col.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        self.value = _ValueBar()
        col.addWidget(self.value)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.preview = QLabel()
        self.preview.setFixedSize(32, 32)
        row.addWidget(self.preview)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(84)
        self.hex.setToolTip("Hex color, e.g. #14b4ff")
        self.hex.editingFinished.connect(self._hex_entered)
        row.addWidget(self.hex)
        self.rgb = []
        for name in "RGB":
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setPrefix(f"{name}  ")
            spin.setKeyboardTracking(False)
            spin.setMinimumWidth(66)
            spin.valueChanged.connect(self._rgb_entered)
            self.rgb.append(spin)
            row.addWidget(spin)
        row.addStretch()
        col.addLayout(row)

        swatches = QHBoxLayout()
        swatches.setSpacing(6)
        for color in SWATCHES:
            swatches.addWidget(self._swatch(color))
        swatches.addStretch()
        col.addLayout(swatches)
        col.addWidget(heading("My colors"))
        self.saved_row = QHBoxLayout()
        self.saved_row.setSpacing(6)
        col.addLayout(self.saved_row)
        self.saved = [c for c in settings.load().get("colors", []) if QColor.isValidColorName(c)][:MAX_SAVED]
        self._show_saved()
        self.wheel.picked.connect(self._wheel_picked)
        self.value.picked.connect(self._value_picked)
        self.set_color(QColor(theme.ACCENT))

    def _swatch(self, color, removable=False):
        b = QPushButton()
        b.setFixedSize(24, 24)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton {{ background:{color}; border:1px solid {theme.BORDER}; border-radius:12px; padding:0; }}"
                        f"QPushButton:hover {{ border:2px solid {theme.TEXT}; }}")
        b.setToolTip(color + ("  ·  right-click to remove" if removable else ""))
        b.clicked.connect(lambda _=False: self.set_color(QColor(color), emit=True))
        if removable:
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _: self._remove_saved(color))
        return b

    def _show_saved(self):
        while self.saved_row.count():
            item = self.saved_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for color in self.saved:
            self.saved_row.addWidget(self._swatch(color, removable=True))
        if len(self.saved) < MAX_SAVED:
            add = QPushButton("+")
            add.setFixedSize(24, 24)
            add.setCursor(Qt.CursorShape.PointingHandCursor)
            add.setToolTip("Save the current color")
            add.setStyleSheet(f"QPushButton {{ background: transparent; border:1px dashed {theme.FAINT}; "
                              f"border-radius:12px; padding:0; color:{theme.MUTED}; font-size:15px; }}"
                              f"QPushButton:hover {{ border-color:{theme.ACCENT}; color:{theme.TEXT}; }}")
            add.clicked.connect(self._save_color)
            self.saved_row.addWidget(add)
        self.saved_row.addStretch()

    def _save_color(self):
        color = self.color().name()
        if color not in self.saved:
            self.saved.append(color)
            settings.update(colors=self.saved)
            self._show_saved()

    def _remove_saved(self, color):
        self.saved.remove(color)
        settings.update(colors=self.saved)
        self._show_saved()

    def color(self):
        return QColor.fromHsvF(self.wheel.hue, self.wheel.sat, self.value.val)

    def set_color(self, color, emit=False):
        h, s, v, _ = color.getHsvF()
        hue = max(h, 0.0)  # -1 for greys
        for w in (self.wheel, self.value):
            w.hue, w.sat, w.val = hue, s, v
            w.update()
        self._show(color)
        if emit:
            self.changed.emit(color, True)

    def _wheel_picked(self, hue, sat, final):
        self.value.hue, self.value.sat = hue, sat
        self.value.update()
        self._emit(final)

    def _value_picked(self, val, final):
        self.wheel.val = val
        self.wheel.update()
        self._emit(final)

    def _emit(self, final):
        color = self.color()
        self._show(color)
        self.changed.emit(color, final)

    def _show(self, color):
        self.preview.setStyleSheet(f"background:{color.name()}; border:1px solid {theme.BORDER}; border-radius:16px;")
        if not self.hex.hasFocus():
            self.hex.setText(color.name())
        for spin, v in zip(self.rgb, (color.red(), color.green(), color.blue())):
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)

    def _hex_entered(self):
        color = QColor(self.hex.text().strip())
        if color.isValid() and color != self.color():
            self.set_color(color, emit=True)

    def _rgb_entered(self):
        self.set_color(QColor(*(s.value() for s in self.rgb)), emit=True)


class KeyCapture(QPushButton):
    """Click, then press a key combination. Emits (modifier bits, HID usage).

    Uses scan codes, so the result is the physical key whatever the layout.
    """

    captured = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__("Click, then press a key combination", parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(44)
        self.toggled.connect(self._toggled)
        self._mods = 0
        self._held = set()

    def _toggled(self, on):
        self._mods, self._held = 0, set()
        self.setText("Press keys now… (Esc to cancel)" if on else "Click, then press a key combination")
        if on:
            self.setFocus()
            self.grabKeyboard()
        else:
            self.releaseKeyboard()

    def keyPressEvent(self, e):
        if not self.isChecked():
            return super().keyPressEvent(e)
        code = e.nativeScanCode() - 8
        if code == 1 and not self._mods:  # Esc alone cancels
            self.setChecked(False)
            return
        if code in keys.EVDEV_TO_MODIFIER:
            self._mods |= keys.EVDEV_TO_MODIFIER[code]
            self._held.add(code)
            return
        usage = keys.EVDEV_TO_HID.get(code)
        if usage:
            self.setChecked(False)
            self.captured.emit(self._mods, usage)

    def keyReleaseEvent(self, e):
        if not self.isChecked():
            return super().keyReleaseEvent(e)
        code = e.nativeScanCode() - 8
        self._held.discard(code)
        if code in keys.EVDEV_TO_MODIFIER and not self._held and self._mods:
            mods = self._mods  # modifier-only binding, e.g. a held Shift
            self.setChecked(False)
            self.captured.emit(mods, 0)
