"""SENSITIVITY page: DPI levels, default and sniper level, report rate."""

from math import log

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from ...onboard import SPECIAL_CODES, Special
from .. import theme
from ..widgets import ChoiceList, heading, muted
from . import Page

TICKS = [100, 400, 800, 1600, 3200, 6400, 12800, 25600]
SNIPER_RED = "#ff5a5f"


class DpiTrack(QWidget):
    """Log-scale track with one draggable marker per DPI level."""

    dragging = Signal(int, int)  # level slot, dpi
    committed = Signal(int, int)
    add = Signal(int)  # dpi

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(96)
        self.lo, self.hi, self.step = 100, 25600, 50
        self.levels = []  # [(slot, dpi)]
        self.default = self.shift = self.active = None
        self._drag = None
        self.setToolTip(self.tr("Drag a level to change it. Click the track to add a level there."))

    def _x(self, dpi):
        r = self._track()
        return r.left() + r.width() * log(dpi / self.lo) / log(self.hi / self.lo)

    def _dpi(self, x):
        r = self._track()
        frac = min(max((x - r.left()) / r.width(), 0), 1)
        dpi = self.lo * (self.hi / self.lo) ** frac
        return int(min(max(round(dpi / self.step) * self.step, self.lo), self.hi))

    def _track(self):
        return QRectF(14, 40, self.width() - 28, 4)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._track()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(r, 2, 2)
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(10)
        p.setFont(f)
        for t in TICKS:
            x = self._x(t)
            p.setPen(QPen(QColor(theme.FAINT), 1))
            p.drawLine(QPointF(x, r.bottom() + 4), QPointF(x, r.bottom() + 8))
            label = f"{t // 1000}k" if t >= 10000 else str(t)
            p.drawText(QRectF(x - 20, r.bottom() + 10, 40, 14), Qt.AlignmentFlag.AlignCenter, label)
        f.setPixelSize(10)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        for n, (slot, dpi) in enumerate(self.levels):
            c = QPointF(self._x(dpi), r.center().y())
            if slot == self.shift:
                p.setPen(QPen(QColor(SNIPER_RED), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, 13, 13)
            is_default = slot == self.default
            p.setPen(QPen(QColor(theme.ACCENT if is_default else "#5c6470"), 1.4))
            p.setBrush(QColor(theme.ACCENT if is_default else theme.RAISED))
            p.drawEllipse(c, 9, 9)
            p.setPen(QColor("#001018" if is_default else theme.TEXT))
            p.drawText(QRectF(c.x() - 9, c.y() - 9, 18, 18), Qt.AlignmentFlag.AlignCenter, str(n + 1))
            if slot == self.active:
                p.setPen(QColor(theme.ACCENT))
                p.drawText(QRectF(c.x() - 30, c.y() - 34, 60, 14), Qt.AlignmentFlag.AlignCenter, f"{dpi}")
                p.drawText(QRectF(c.x() - 30, c.y() - 24, 60, 12), Qt.AlignmentFlag.AlignCenter, "▼")

    def mousePressEvent(self, e):
        x = e.position().x()
        near = [(abs(self._x(dpi) - x), slot) for slot, dpi in self.levels]
        if near and min(near)[0] < 14:
            self._drag = min(near)[1]
        elif len(self.levels) < 5 and abs(e.position().y() - self._track().center().y()) < 16:
            self.add.emit(self._dpi(x))

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            dpi = self._dpi(e.position().x())
            self.levels = [(s, dpi if s == self._drag else d) for s, d in self.levels]
            self.update()
            self.dragging.emit(self._drag, dpi)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            slot, self._drag = self._drag, None
            self.committed.emit(slot, dict(self.levels)[slot])


class LevelRow(QWidget):
    changed = Signal(int, int)
    make_default = Signal(int)
    make_shift = Signal(int)
    remove = Signal(int)

    def __init__(self):
        super().__init__()
        self.slot = 0
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.name = QLabel()
        self.name.setFixedWidth(52)
        row.addWidget(self.name)
        self.spin = QSpinBox()
        self.spin.setKeyboardTracking(False)
        self.spin.setSuffix(" DPI")
        self.spin.setMinimumWidth(110)
        self.spin.valueChanged.connect(lambda v: self.changed.emit(self.slot, v))
        row.addWidget(self.spin)
        self.default_btn = QPushButton(self.tr("Default"))
        self.default_btn.setCheckable(True)
        self.default_btn.clicked.connect(lambda: self.make_default.emit(self.slot))
        row.addWidget(self.default_btn)
        self.shift_btn = QPushButton(self.tr("Sniper"))
        self.shift_btn.setCheckable(True)
        self.shift_btn.clicked.connect(lambda: self.make_shift.emit(self.slot))
        row.addWidget(self.shift_btn)
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setObjectName("Flat")
        self.remove_btn.setToolTip(self.tr("Remove this level"))
        self.remove_btn.clicked.connect(lambda: self.remove.emit(self.slot))
        row.addWidget(self.remove_btn)

    def show_level(self, n, slot, dpi, rng, is_default, is_shift, active, removable):
        self.slot = slot
        self.name.setText(self.tr("Level {n}").format(n=n))
        self.name.setStyleSheet(f"color: {theme.ACCENT if active else theme.TEXT}; font-weight: {600 if active else 400};")
        self.spin.blockSignals(True)
        self.spin.setRange(rng[0], rng[1])
        self.spin.setSingleStep(rng[2])
        self.spin.setValue(dpi)
        self.spin.blockSignals(False)
        self.default_btn.setChecked(is_default)
        self.default_btn.setStyleSheet(f"color: {theme.ACCENT};" if is_default else "")
        self.shift_btn.setChecked(is_shift)
        self.shift_btn.setStyleSheet(f"color: {SNIPER_RED};" if is_shift else "")
        self.remove_btn.setEnabled(removable)


class SensitivityPage(Page):
    icon = "sensitivity"
    mouse_mode = "plain"

    @property
    def title(self):
        return self.tr("SENSITIVITY")

    def __init__(self, *args):
        super().__init__(*args)
        title = QLabel(self.tr("Sensitivity"))
        title.setObjectName("Title")
        self.layout.addWidget(title)
        self.layout.addWidget(muted(self.tr("Up to 5 DPI levels. G7/G8 step through them by default; "
                                            "the sniper level applies while DPI shift is held."), "Faint"))
        self.track = DpiTrack()
        self.track.dragging.connect(self._dragging)
        self.track.committed.connect(self._set_dpi)
        self.track.add.connect(self._add_at)
        self.layout.addWidget(self.track)

        self.layout.addWidget(heading(self.tr("DPI levels")))
        self.rows = []
        for _ in range(5):
            row = LevelRow()
            row.changed.connect(self._set_dpi)
            row.make_default.connect(lambda s: self.state.edit(lambda p: setattr(p, "default_dpi_index", s)))
            row.make_shift.connect(lambda s: self.state.edit(lambda p: setattr(p, "shift_dpi_index", s)))
            row.remove.connect(self._remove)
            self.rows.append(row)
            self.layout.addWidget(row)
        self.add_btn = QPushButton(self.tr("+  Add level"))
        self.add_btn.clicked.connect(self._add)
        self.layout.addWidget(self.add_btn)
        self.shift_hint = muted("", "Faint")
        self.layout.addWidget(self.shift_hint)

        self.layout.addWidget(heading(self.tr("Report rate")))
        self.rate = ChoiceList([(ms, f"{1000 // ms} Hz") for ms in (8, 4, 2, 1)], columns=4)
        self.rate.changed.connect(lambda ms: self.state.edit(lambda p: setattr(p, "report_interval_ms", ms)))
        self.layout.addWidget(self.rate)
        self.layout.addWidget(muted(self.tr("1000 Hz is the most responsive. Lower rates use slightly less CPU."), "Faint"))
        self.layout.addStretch()

    def _dragging(self, slot, dpi):
        if slot == self.state.dpi_index:
            self.state.preview_dpi(dpi)

    def _set_dpi(self, slot, dpi):
        self.state.edit(lambda p: p.dpi.__setitem__(slot, dpi))

    def _relevel(self, values):
        """Store levels contiguously, keeping default, sniper and the active level on the same DPI."""
        profile = self.state.profile()
        remap = {s: i for i, (s, _) in enumerate(values)}
        default = remap.get(profile.default_dpi_index, 0)
        shift = remap.get(profile.shift_dpi_index, 0)

        def change(p):
            p.dpi = [d for _, d in values] + [0] * (5 - len(values))
            p.default_dpi_index, p.shift_dpi_index = default, shift
        self.state.edit(change, dpi_index=remap.get(self.state.dpi_index, default))

    def _remove(self, slot):
        self._relevel([(s, d) for s, d in self.state.profile().dpi_levels() if s != slot])

    def _add(self):
        lo, hi, step = self.state.dpi_range
        levels = self.state.profile().dpi_levels()
        last = levels[-1][1] if levels else 800
        self._relevel(levels + [(10, min(hi, max(lo, round(last * 2 / step) * step)))])

    def _add_at(self, dpi):
        levels = self.state.profile().dpi_levels()
        at = next((i for i, (_, d) in enumerate(levels) if d > dpi), len(levels))
        self._relevel(levels[:at] + [(10, dpi)] + levels[at:])

    def refresh(self):
        profile = self.state.profile()
        if profile is None:
            return
        levels = profile.dpi_levels()
        lo, hi, step = self.state.dpi_range
        t = self.track
        t.lo, t.hi, t.step = lo, hi, step
        t.levels = levels
        t.default, t.shift, t.active = profile.default_dpi_index, profile.shift_dpi_index, self.state.dpi_index
        t.update()
        for i, row in enumerate(self.rows):
            if i < len(levels):
                slot, dpi = levels[i]
                row.show_level(i + 1, slot, dpi, (lo, hi, step), slot == profile.default_dpi_index,
                               slot == profile.shift_dpi_index, slot == self.state.dpi_index, len(levels) > 1)
                row.show()
            else:
                row.hide()
        self.add_btn.setEnabled(len(levels) < 5)
        self.rate.set_value(profile.report_interval_ms)
        has_shift = any(isinstance(b, Special) and b.function == SPECIAL_CODES["dpi-shift"]
                        for b in profile.buttons)
        self.shift_hint.setText("" if has_shift else
                                self.tr("No button is set to DPI shift in this profile, so the sniper "
                                        "level isn't used. Assign DPI shift to G6 under Assignments."))
        self.shift_hint.setVisible(not has_shift)
