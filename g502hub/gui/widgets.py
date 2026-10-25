"""Small reusable widgets: segmented tabs, color picker, slider rows, key capture."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QConicalGradient, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget)

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
        self.fmt = fmt
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
        self.value_label.setText(self.fmt.format(v))
        self.moved.emit(v)
        if not self.slider.isSliderDown():
            self.committed.emit(v)  # keyboard or click on the groove

    def set_value(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.value_label.setText(self.fmt.format(v))


class _SatValSquare(QWidget):
    picked = Signal(float, float, bool)  # saturation, value, final

    def __init__(self):
        super().__init__()
        self.hue, self.sat, self.val = 0.0, 1.0, 1.0
        self.setMinimumHeight(150)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 4, 4)
        p.setClipPath(path)
        horizontal = QLinearGradient(r.topLeft(), r.topRight())
        horizontal.setColorAt(0, QColor("white"))
        horizontal.setColorAt(1, QColor.fromHsvF(self.hue, 1, 1))
        p.fillRect(r, horizontal)
        vertical = QLinearGradient(r.topLeft(), r.bottomLeft())
        vertical.setColorAt(0, QColor(0, 0, 0, 0))
        vertical.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(r, vertical)
        p.setClipping(False)
        x = r.left() + self.sat * r.width()
        y = r.top() + (1 - self.val) * r.height()
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y), 6, 6)

    def _pick(self, pos, final):
        self.sat = min(max(pos.x() / max(self.width(), 1), 0), 1)
        self.val = 1 - min(max(pos.y() / max(self.height(), 1), 0), 1)
        self.update()
        self.picked.emit(self.sat, self.val, final)

    def mousePressEvent(self, e):
        self._pick(e.position(), False)

    def mouseMoveEvent(self, e):
        self._pick(e.position(), False)

    def mouseReleaseEvent(self, e):
        self._pick(e.position(), True)


class _HueBar(QWidget):
    picked = Signal(float, bool)

    def __init__(self):
        super().__init__()
        self.hue = 0.0
        self.setFixedHeight(14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        g = QLinearGradient(r.topLeft(), r.topRight())
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1, 1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 5, 5)
        x = r.left() + self.hue * r.width()
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(QColor.fromHsvF(self.hue, 1, 1))
        p.drawEllipse(QPointF(x, self.height() / 2), 6, 6)

    def _pick(self, pos, final):
        self.hue = min(max(pos.x() / max(self.width(), 1), 0), 0.999)
        self.update()
        self.picked.emit(self.hue, final)

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
    """Saturation/value square, hue bar, hex field and swatches.

    `changed(QColor, final)` fires live while dragging (final=False) and once on release.
    """

    changed = Signal(QColor, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        self.square = _SatValSquare()
        self.hue = _HueBar()
        col.addWidget(self.square)
        col.addWidget(self.hue)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.preview = QLabel()
        self.preview.setFixedSize(30, 30)
        row.addWidget(self.preview)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(90)
        self.hex.editingFinished.connect(self._hex_entered)
        row.addWidget(self.hex)
        self.save_btn = QPushButton("+  Save color")
        self.save_btn.setObjectName("Flat")
        self.save_btn.setToolTip("Add this color to My colors")
        self.save_btn.clicked.connect(self._save_color)
        row.addWidget(self.save_btn)
        row.addStretch()
        col.addLayout(row)
        swatches = QHBoxLayout()
        swatches.setSpacing(6)
        for color in SWATCHES:
            swatches.addWidget(self._swatch(color))
        swatches.addStretch()
        col.addLayout(swatches)
        self.saved_heading = QLabel("MY COLORS")
        self.saved_heading.setObjectName("Heading")
        col.addWidget(self.saved_heading)
        self.saved_row = QHBoxLayout()
        self.saved_row.setSpacing(6)
        col.addLayout(self.saved_row)
        self.saved = [c for c in settings.load().get("colors", []) if QColor.isValidColorName(c)][:MAX_SAVED]
        self._show_saved()
        self.square.picked.connect(lambda s, v, final: self._emit(final))
        self.hue.picked.connect(self._hue_picked)
        self.set_color(QColor(theme.ACCENT))

    def _swatch(self, color, removable=False):
        b = QPushButton()
        b.setFixedSize(22, 22)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"background:{color}; border:1px solid {theme.BORDER}; border-radius:11px; padding:0;")
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
        self.saved_row.addStretch()
        self.saved_heading.setVisible(bool(self.saved))
        self.save_btn.setEnabled(len(self.saved) < MAX_SAVED)

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
        return QColor.fromHsvF(self.hue.hue, self.square.sat, self.square.val)

    def set_color(self, color, emit=False):
        h, s, v, _ = color.getHsvF()
        self.hue.hue = max(h, 0.0)
        self.square.hue, self.square.sat, self.square.val = self.hue.hue, s, v
        self.hue.update()
        self.square.update()
        self._show(color)
        if emit:
            self.changed.emit(color, True)

    def _hue_picked(self, hue, final):
        self.square.hue = hue
        self.square.update()
        self._emit(final)

    def _emit(self, final):
        color = self.color()
        self._show(color)
        self.changed.emit(color, final)

    def _show(self, color):
        self.preview.setStyleSheet(f"background:{color.name()}; border:1px solid {theme.BORDER}; border-radius:4px;")
        if not self.hex.hasFocus():
            self.hex.setText(color.name())

    def _hex_entered(self):
        color = QColor(self.hex.text().strip())
        if color.isValid():
            self.set_color(color, emit=True)


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
