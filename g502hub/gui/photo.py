"""Logitech's product photo of the G502 HERO, with button and LED positions on it.

The photo isn't shipped (it's Logitech's); tools/fetch-photo.py downloads it.
Coordinates below are in the prepared photo's pixels (PHOTO_SIZE).
"""

import os
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QRadialGradient

from . import theme
from .shapes import Element, ellipse, polygon, rounded

PHOTO_PATH = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "g502-hub" / "g502-hero.png"
PHOTO_SIZE = (618, 1110)

# Lit areas in the photo: (bounding box, glow center, glow radius)
LED_AREAS = {
    0: (QRect(112, 529, 41, 116), QPointF(132, 586), 70),
    1: (QRect(202, 704, 98, 100), QPointF(251, 754), 120),
}


def elements():
    """Hotspots on the photo; side buttons hidden from above get a badge out to the left."""
    return [
        # Smaller elements first: hit-testing takes the first match
        Element(10, ellipse(276, 322, 17), (276, 322)),
        Element(9, ellipse(432, 322, 17), (432, 322)),
        Element(2, rounded(318, 236, 68, 166, 22), (352, 318)),
        Element(8, rounded(336, 520, 54, 58, 8), (363, 548)),
        Element(7, polygon([(108, 258), (162, 246), (165, 330), (102, 338)]), (136, 294)),
        Element(6, polygon([(100, 342), (165, 334), (163, 402), (94, 396)]), (132, 368)),
        Element(5, ellipse(90, 462, 20), (-70, 440), anchor=(90, 462)),
        Element(4, ellipse(50, 598, 22), (-70, 560), anchor=(50, 598)),
        Element(3, ellipse(42, 690, 22), (-70, 680), anchor=(42, 690)),
        Element("zone0", rounded(110, 527, 45, 120, 12), (132, 586), "led"),
        Element("zone1", ellipse(251, 754, 56), (251, 754), "led"),
        Element(0, polygon([(168, 163), (298, 88), (300, 505), (232, 540), (166, 520), (160, 400)]), (232, 300)),
        Element(1, polygon([(402, 88), (522, 150), (562, 250), (575, 400), (565, 515), (470, 560),
                          (402, 505)]), (482, 300)),
    ]


class PhotoSkin:
    canvas = QRectF(-190, -10, 990, 1130)
    halo = (QPointF(300, 560), 620)
    badge_radius = 17
    badge_font = (13, 19)  # label pixel size for 2-char and 1-char badges
    pen_scale = 2.4
    callouts = [("DPI LIGHTS", QPointF(110, 586), QPointF(-170, 586), "zone0"),
                ("LOGO", QPointF(308, 754), QPointF(780, 754), "zone1")]

    def __init__(self, image):
        self.elements = elements()
        self.base, self.masks = self._prepare(image.convertToFormat(QImage.Format.Format_ARGB32))

    @staticmethod
    def load():
        """The photo skin, or None when the photo hasn't been downloaded."""
        image = QImage(str(PHOTO_PATH))
        if image.isNull() or (image.width(), image.height()) != PHOTO_SIZE:
            return None
        return PhotoSkin(image)

    def _prepare(self, image):
        """Split the photo into an 'LEDs off' base and a light mask per zone."""
        w, h = image.width(), image.height()
        px = np.frombuffer(image.constBits(), np.uint8).reshape(h, image.bytesPerLine() // 4, 4)[:, :w]
        bgr = px[..., :3].astype(np.float32) / 255
        mx, mn = bgr.max(-1), bgr.min(-1)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        blue = bgr[..., 0] - np.maximum(bgr[..., 1], bgr[..., 2]) * 0.55
        strength = np.clip((sat - 0.18) / 0.35, 0, 1) * np.clip((mx - 0.08) / 0.3, 0, 1) * (blue > 0.05)
        base = px.copy()
        masks = {}
        for zone, (rect, _, _) in LED_AREAS.items():
            sl = (slice(rect.top(), rect.bottom() + 1), slice(rect.left(), rect.right() + 1))
            s = strength[sl]
            # LEDs off: dark smoked plastic, keeping a little of the photo's shading
            off = (mx[sl] * 0.28 + 0.05)[..., None] * np.array([1.0, 0.98, 0.94], np.float32)
            mixed = bgr[sl] * (1 - s[..., None]) + off * s[..., None]
            base[sl][..., :3] = (mixed * 255).astype(np.uint8)
            shade = 0.55 + 0.45 * mx[sl] / max(float(mx[sl].max()), 1e-6)
            alpha = (np.clip(s * shade, 0, 1) * 255).astype(np.uint8)
            mask = QImage(alpha.shape[1], alpha.shape[0], QImage.Format.Format_ARGB32_Premultiplied)
            mask.fill(Qt.GlobalColor.transparent)
            buf = np.frombuffer(mask.bits(), np.uint8).reshape(mask.height(), mask.bytesPerLine() // 4, 4)
            buf[:, :alpha.shape[1], 3] = alpha
            masks[zone] = mask
        out = QImage(base.tobytes(), w, h, w * 4, QImage.Format.Format_ARGB32).copy()
        return out, masks

    def paint(self, p, colors, view):
        p.drawImage(0, 0, self.base)
        for zone, color in colors.items():
            if color is not None and color.value() > 6:
                self._paint_light(p, zone, color)
        for el in self.elements:
            fill, pen = view._state_colors(el)
            if pen is None or el.kind == "led":
                continue
            c = QColor(theme.ACCENT)
            c.setAlpha(70 if el.key in view.selected else 40)
            p.setBrush(c)
            p.setPen(QPen(pen.color(), pen.widthF() * self.pen_scale * 0.6))
            p.drawPath(el.path)
        for el in self.elements:
            if el.kind == "led":
                _, pen = view._state_colors(el)
                if pen is not None:
                    p.setPen(QPen(pen.color(), pen.widthF() * self.pen_scale * 0.6))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawPath(el.path)

    def _paint_light(self, p, zone, color):
        rect, center, radius = LED_AREAS[zone]
        glow = QRadialGradient(center, radius)
        c = QColor(color)
        c.setAlpha(90)
        glow.setColorAt(0, c)
        c.setAlpha(28)
        glow.setColorAt(0.45, c)
        c.setAlpha(0)
        glow.setColorAt(1, c)
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(center, radius, radius)
        p.restore()
        lit = QImage(self.masks[zone].size(), QImage.Format.Format_ARGB32_Premultiplied)
        lit.fill(color)
        q = QPainter(lit)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        q.drawImage(0, 0, self.masks[zone])
        q.end()
        p.drawImage(rect.topLeft(), lit)

