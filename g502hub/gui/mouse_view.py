"""A painted, interactive top view of the G502 HERO.

Buttons are hit-testable regions keyed by onboard slot (0-10); the two LED
zones are "zone0" (DPI lights) and "zone1" (logo) and show live effects.
"""

import time
from math import cos, pi

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient, QTransform)
from PySide6.QtWidgets import QToolTip, QWidget

from . import theme

CANVAS = QRectF(0, 0, 340, 480)

BODY = [(190, 22), (235, 26), (262, 70), (270, 140), (273, 220), (266, 280), (270, 340),
        (252, 410), (220, 440), (180, 446), (148, 436), (125, 420), (90, 395), (68, 360),
        (74, 330), (100, 318), (108, 290), (102, 250), (104, 200), (108, 150), (118, 80),
        (142, 28)]
LEFT_BUTTON = [(146, 32), (186, 25), (187, 176), (142, 182), (134, 130), (135, 70)]
RIGHT_BUTTON = [(194, 25), (234, 30), (258, 72), (265, 140), (256, 180), (194, 178)]

BADGES = {0: "G1", 1: "G2", 2: "G3", 3: "G4", 4: "G5", 5: "G6", 6: "G7", 7: "G8",
          8: "G9", 9: "›", 10: "‹"}


def smooth_path(points, closed=True, tension=0.5):
    """Catmull-Rom spline through the points, as cubic Beziers."""
    pts = [QPointF(*p) for p in points]
    n = len(pts)
    path = QPainterPath(pts[0])
    for i in range(n if closed else n - 1):
        p0, p1 = pts[(i - 1) % n], pts[i]
        p2, p3 = pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = p1 + (p2 - p0) * (tension / 3)
        c2 = p2 - (p3 - p1) * (tension / 3)
        path.cubicTo(c1, c2, p2)
    if closed:
        path.closeSubpath()
    return path


def pill(cx, cy, w, h, angle=0.0):
    path = QPainterPath()
    path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), min(w, h) / 2, min(w, h) / 2)
    return QTransform().translate(cx, cy).rotate(angle).map(path)


def _rect(x, y, w, h, r=2):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


class Element:
    def __init__(self, key, path, badge_at, kind="button"):
        self.key = key
        self.path = path
        self.badge_at = QPointF(*badge_at)
        self.kind = kind


def _elements():
    wheel = QPainterPath()
    wheel.addRoundedRect(QRectF(181, 64, 18, 56), 8, 8)
    logo = QPainterPath()
    logo.addEllipse(QPointF(196, 330), 22, 22)
    dpi = QPainterPath()
    for y in (146, 158, 170):
        dpi.addPath(_rect(121, y, 6, 9, 3))
    return [
        # Smaller elements first: hit-testing takes the first match
        Element(9, _rect(201, 66, 9, 52, 3), (213, 54)),
        Element(10, _rect(170, 66, 9, 52, 3), (167, 54)),
        Element(2, wheel, (190, 92)),
        Element(8, pill(190, 141, 14, 22), (190, 141)),
        Element(6, pill(127, 76, 11, 32, -14), (127, 76)),
        Element(7, pill(122, 115, 11, 32, -6), (122, 115)),
        Element(4, pill(108, 206, 10, 32, -3), (108, 206)),
        Element(3, pill(106, 247, 10, 32, 2), (106, 247)),
        Element(5, pill(98, 297, 12, 24, 35), (98, 297)),
        Element("zone0", dpi, (124, 162), "led"),
        Element("zone1", logo, (196, 330), "led"),
        Element(0, smooth_path(LEFT_BUTTON, tension=0.35), (162, 125)),
        Element(1, smooth_path(RIGHT_BUTTON, tension=0.35), (226, 125)),
    ]


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(300, 400)
        self.body = smooth_path(BODY)
        self.elements = _elements()
        self.mode = "plain"  # "assign", "light" or "plain"
        self.selected = set()
        self.hovered = None
        self.tooltips = {}
        self.badges = dict(BADGES)
        self.leds = {0: None, 1: None}
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

    # ------------------------------------------------------------ geometry

    def _transform(self):
        scale = min(self.width() / CANVAS.width(), self.height() / CANVAS.height()) * 0.96
        dx = (self.width() - CANVAS.width() * scale) / 2
        dy = (self.height() - CANVAS.height() * scale) / 2
        return QTransform().translate(dx, dy).scale(scale, scale)

    def _hit(self, pos):
        inverse, ok = self._transform().inverted()
        p = inverse.map(QPointF(pos))
        for el in self.elements:
            if self._interactive(el) and el.path.contains(p):
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
        key = self._hit(e.position())
        if key is not None:
            self.clicked.emit(key)

    # ------------------------------------------------------------ painting

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setTransform(self._transform())
        t = time.monotonic() - self._t0
        colors = {z: effect_color(e, t) for z, e in self.leds.items()}

        halo = QRadialGradient(QPointF(190, 240), 230)
        halo.setColorAt(0, QColor(20, 40, 56, 120))
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(CANVAS, halo)

        body = QLinearGradient(QPointF(70, 0), QPointF(275, 0))
        body.setColorAt(0, QColor("#24272d"))
        body.setColorAt(0.55, QColor("#17191d"))
        body.setColorAt(1, QColor("#202329"))
        p.setPen(QPen(QColor("#3b4049"), 1.4))
        p.setBrush(body)
        p.drawPath(self.body)

        # Decorative seams of the palm shell
        p.setPen(QPen(QColor("#2c3037"), 1.2))
        p.drawPath(smooth_path([(142, 184), (150, 260), (160, 380)], closed=False))
        p.drawPath(smooth_path([(256, 182), (252, 260), (240, 380)], closed=False))

        for el in reversed(self.elements):
            self._paint_element(p, el, colors)

        if self.mode == "assign":
            for el in self.elements:
                if el.kind == "button":
                    self._paint_badge(p, el)
        if self.mode == "light":
            self._paint_callout(p, "DPI LIGHTS", QPointF(118, 162), QPointF(20, 162), "zone0")
            self._paint_callout(p, "LOGO", QPointF(220, 330), QPointF(320, 330), "zone1")

    def _state_colors(self, el):
        if el.key in self.selected and self._interactive(el):
            return QColor("#163246"), QPen(QColor(theme.ACCENT), 2)
        if el.key == self.hovered:
            return QColor("#26323f"), QPen(QColor("#4a6378"), 1.4)
        return None, None

    def _paint_element(self, p, el, colors):
        fill, pen = self._state_colors(el)
        if el.kind == "led":
            zone = 0 if el.key == "zone0" else 1
            self._paint_led(p, el, colors.get(zone), pen)
            return
        if el.key in (0, 1):
            base = QColor("#1d2025")
        elif el.key == 2:
            base = QColor("#2b2f36")
        elif el.key == 5:
            base = QColor("#8f2a26")
        else:
            base = QColor("#2a2e35")
        p.setBrush(fill or base)
        p.setPen(pen or QPen(QColor("#3a3f48"), 1.1))
        p.drawPath(el.path)
        if el.key == 2:  # wheel ridges
            p.setPen(QPen(QColor("#3f444d"), 1))
            for y in range(70, 116, 5):
                p.drawLine(QPointF(184, y), QPointF(196, y))
        if el.key in (9, 10):  # tilt chevrons
            x = 205.5 if el.key == 9 else 174.5
            d = 2 if el.key == 9 else -2
            p.setPen(QPen(QColor(theme.MUTED), 1.2))
            p.drawLine(QPointF(x - d, 88), QPointF(x + d, 92))
            p.drawLine(QPointF(x + d, 92), QPointF(x - d, 96))

    def _paint_led(self, p, el, color, pen):
        if color is not None and color.value() > 8:
            center = el.path.boundingRect().center()
            glow = QRadialGradient(center, 46 if el.key == "zone1" else 30)
            c = QColor(color)
            c.setAlpha(150)
            glow.setColorAt(0, c)
            c.setAlpha(0)
            glow.setColorAt(1, c)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(center, 46 if el.key == "zone1" else 30, 46 if el.key == "zone1" else 30)
        lit = color if color is not None else QColor("#2a2e35")
        if pen is not None:  # selection / hover ring around the whole zone
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = el.path.boundingRect().adjusted(-5, -5, 5, 5)
            if el.key == "zone1":
                p.drawEllipse(r)
            else:
                p.drawRoundedRect(r, 6, 6)
        if el.key == "zone1":
            p.setBrush(QColor("#1b1e23"))
            p.setPen(QPen(QColor("#3a3f48"), 1.2))
            p.drawPath(el.path)
            f = QFont(theme.FONT_FAMILY)
            f.setPixelSize(26)
            f.setWeight(QFont.Weight.Black)
            p.setFont(f)
            p.setPen(lit)
            p.drawText(el.path.boundingRect(), Qt.AlignmentFlag.AlignCenter, "G")
        else:
            p.setBrush(lit)
            p.setPen(QPen(QColor("#3a3f48"), 0.8))
            p.drawPath(el.path)

    def _paint_badge(self, p, el):
        selected = el.key in self.selected
        hovered = el.key == self.hovered
        p.setPen(QPen(QColor(theme.ACCENT if selected else "#5c6470"), 1.2))
        p.setBrush(QColor(theme.ACCENT if selected else ("#2d3a47" if hovered else "#14171b")))
        p.drawEllipse(el.badge_at, 10.5, 10.5)
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(8 if len(self.badges[el.key]) > 1 else 12)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor("#001018" if selected else theme.TEXT))
        p.drawText(QRectF(el.badge_at.x() - 11, el.badge_at.y() - 11, 22, 22),
                   Qt.AlignmentFlag.AlignCenter, self.badges[el.key])

    def _paint_callout(self, p, text, anchor, end, key):
        """A leader line from an LED zone out to `end`, labelled above its outer end."""
        color = QColor(theme.ACCENT if key in self.selected else theme.MUTED)
        p.setPen(QPen(color, 1))
        p.drawLine(anchor, end)
        p.setBrush(color)
        p.drawEllipse(anchor, 2, 2)
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(10)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        p.setFont(f)
        rect = QRectF(min(anchor.x(), end.x()), end.y() - 18, abs(end.x() - anchor.x()), 14)
        outward = Qt.AlignmentFlag.AlignRight if end.x() > anchor.x() else Qt.AlignmentFlag.AlignLeft
        p.drawText(rect, outward | Qt.AlignmentFlag.AlignVCenter, text)
