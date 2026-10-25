"""An interactive top view of the G502 HERO.

Buttons are hit-testable regions keyed by onboard slot (0-10); the two LED
zones are "zone0" (DPI lights) and "zone1" (logo) and show live effects.
The mouse is Logitech's product photo (see photo.py), downloaded on first start.
"""

import time
from math import cos, hypot, pi

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient, QTransform
from PySide6.QtWidgets import QToolTip, QWidget

from . import theme
from .photo import PhotoFetcher, PhotoSkin, load_image

BADGES = {0: "G1", 1: "G2", 2: "G3", 3: "G4", 4: "G5", 5: "G6", 6: "G7", 7: "G8",
          8: "G9", 9: "›", 10: "‹"}


def effect_color(effect, t):
    """The color an LedEffect shows at time t (seconds), or None when off."""
    if effect is None or effect.effect == 0x00:
        return None
    scale = effect.brightness / 100
    if effect.effect == 0x01:
        return QColor(*effect.color)
    if effect.effect == 0x0A:
        phase = (1 - cos(2 * pi * t * 1000 / max(effect.period_ms, 100))) / 2
        r, g, b = effect.color
        return QColor(int(r * phase * scale), int(g * phase * scale), int(b * phase * scale))
    if effect.effect == 0x03:
        hue = (t * 1000 / max(effect.period_ms, 100)) % 1.0
        return QColor.fromHsvF(hue, 1, scale)
    return None


class MouseView(QWidget):
    clicked = Signal(object)
    photoChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(300, 400)
        self.skin = PhotoSkin(load_image())
        self.elements = self.skin.elements
        self.fetcher = PhotoFetcher(self)
        self.fetcher.done.connect(self._fetched)
        if not self.skin.ready:
            self.fetch_photo()
        self.mode = "plain"  # "assign", "light" or "plain"
        self.selected = set()
        self.hovered = None
        self.tooltips = {}
        self.badges = dict(BADGES)
        self.leds = {0: None, 1: None}
        self.live = {}  # zone -> QColor streamed by a live effect, overriding self.leds
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=33)
        self._timer.timeout.connect(self.update)

    # ------------------------------------------------------------ API

    def set_mode(self, mode):
        self.mode = mode
        self.hovered = None
        self.update()

    def set_selected(self, keys):
        self.selected = set(keys)
        self.update()

    def set_leds(self, effects):
        """effects: {zone: LedEffect}"""
        self.leds.update(effects)
        animated = any(e is not None and e.effect in (0x03, 0x0A) for e in self.leds.values())
        if animated and not self._timer.isActive():
            self._timer.start()
        elif not animated:
            self._timer.stop()
        self.update()

    def fetch_photo(self):
        """Download Logitech's photo (first start, or to replace a damaged copy)."""
        self.skin.message = "Getting the picture of your G502 HERO from logitechg.com…"
        self.update()
        self.fetcher.start()

    def _fetched(self, error):
        image = None if error else load_image()
        if image is None:
            self.skin.message = (f"Couldn't download the picture of the mouse ({error or 'damaged file'}). "
                                 "Click here to try again.")
        else:
            self.skin.set_image(image)
        self.update()
        self.photoChanged.emit()

    def set_live(self, colors):
        """colors: {zone: QColor} from a live effect; {} to show the saved effects again."""
        self.live = dict(colors)
        self.update()

    # ------------------------------------------------------------ geometry

    def _transform(self):
        canvas = self.skin.canvas
        scale = min(self.width() / canvas.width(), self.height() / canvas.height()) * 0.96
        dx = (self.width() - canvas.width() * scale) / 2 - canvas.left() * scale
        dy = (self.height() - canvas.height() * scale) / 2 - canvas.top() * scale
        return QTransform().translate(dx, dy).scale(scale, scale)

    def _hit(self, pos):
        inverse, _ = self._transform().inverted()
        p = inverse.map(QPointF(pos))
        for el in self.elements:
            if not self._interactive(el):
                continue
            on_badge = self.mode == "assign" and \
                hypot(p.x() - el.badge_at.x(), p.y() - el.badge_at.y()) <= self.skin.badge_radius
            if on_badge or el.path.contains(p):
                return el.key
        return None

    def _interactive(self, el):
        return (self.mode == "assign" and el.kind == "button") or \
               (self.mode == "light" and el.kind == "led")

    # ------------------------------------------------------------ events

    def mouseMoveEvent(self, e):
        key = self._hit(e.position())
        if key != self.hovered:
            self.hovered = key
            self.setCursor(Qt.CursorShape.PointingHandCursor if key is not None else Qt.CursorShape.ArrowCursor)
            self.update()
        if key is not None and key in self.tooltips:
            QToolTip.showText(e.globalPosition().toPoint(), self.tooltips[key], self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _):
        self.hovered = None
        self.update()

    def mousePressEvent(self, e):
        if not self.skin.ready and not self.fetcher.busy:
            self.fetch_photo()
        key = self._hit(e.position())
        if key is not None:
            self.clicked.emit(key)

    # ------------------------------------------------------------ painting

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setTransform(self._transform())
        t = time.monotonic() - self._t0
        colors = {z: self.live[z] if z in self.live else effect_color(e, t) for z, e in self.leds.items()}

        center, radius = self.skin.halo
        halo = QRadialGradient(center, radius)
        halo.setColorAt(0, QColor(24, 46, 64, 130))
        halo.setColorAt(0.6, QColor(14, 22, 30, 60))
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(self.skin.canvas, halo)

        self.skin.paint(p, colors, self)

        if self.mode == "assign":
            for el in self.elements:
                if el.kind == "button":
                    self._paint_badge(p, el)
        if self.mode == "light":
            for text, anchor, end, key in self.skin.callouts:
                self._paint_callout(p, text, anchor, end, key)

    def _state_colors(self, el):
        if el.key in self.selected and self._interactive(el):
            return QColor("#163246"), QPen(QColor(theme.ACCENT), 2)
        if el.key == self.hovered:
            return QColor("#26323f"), QPen(QColor("#4a6378"), 1.4)
        return None, None

    def _paint_badge(self, p, el):
        selected = el.key in self.selected
        hovered = el.key == self.hovered
        s = self.skin
        if el.anchor is not None:  # leader line from an off-body badge to its button
            p.setPen(QPen(QColor(theme.ACCENT if selected else "#5c6470"), 1.2 * s.pen_scale * 0.6))
            p.drawLine(el.badge_at, el.anchor)
            p.setBrush(QColor(theme.ACCENT if selected else "#8b9099"))
            p.drawEllipse(el.anchor, 2.2 * s.pen_scale * 0.7, 2.2 * s.pen_scale * 0.7)
        p.setPen(QPen(QColor(theme.ACCENT if selected else "#6b7380"), 1.2 * s.pen_scale * 0.6))
        p.setBrush(QColor(theme.ACCENT) if selected else QColor("#2d3a47") if hovered else QColor(20, 23, 27, 225))
        p.drawEllipse(el.badge_at, s.badge_radius, s.badge_radius)
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(s.badge_font[0] if len(self.badges[el.key]) > 1 else s.badge_font[1])
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor("#001018" if selected else theme.TEXT))
        r = s.badge_radius + 1
        p.drawText(QRectF(el.badge_at.x() - r, el.badge_at.y() - r, 2 * r, 2 * r),
                   Qt.AlignmentFlag.AlignCenter, self.badges[el.key])

    def _paint_callout(self, p, text, anchor, end, key):
        """A leader line from an LED zone out to `end`, labelled above its outer end."""
        s = self.skin.pen_scale
        color = QColor(theme.ACCENT if key in self.selected else theme.MUTED)
        p.setPen(QPen(color, 1 * s * 0.7))
        p.drawLine(anchor, end)
        p.setBrush(color)
        p.drawEllipse(anchor, 2 * s, 2 * s)
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(round(10 * s))
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2 * s)
        p.setFont(f)
        rect = QRectF(min(anchor.x(), end.x()), end.y() - 18 * s, abs(end.x() - anchor.x()), 14 * s)
        outward = Qt.AlignmentFlag.AlignRight if end.x() > anchor.x() else Qt.AlignmentFlag.AlignLeft
        p.drawText(rect, outward | Qt.AlignmentFlag.AlignVCenter, text)
