"""Logitech's product photo of the G502 HERO, with button and LED positions on it.

The photo is Logitech's, so it isn't part of G502 Hub: each installation
downloads it once from logitechg.com on first start and keeps it in
~/.local/share/g502-hub. Coordinates below are in the prepared photo's pixels.
"""

import os
import threading
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QRadialGradient

from . import theme
from .i18n import tr
from .shapes import Element, ellipse, polygon, rounded

PHOTO_PATH = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "g502-hub" / "g502-hero.png"
PHOTO_SIZE = (618, 1110)
PHOTO_URL = ("https://resource.logitechg.com/f_png,q_auto/content/dam/gaming/en/non-braid/"
             "hyjal-g502-hero/2025/g502-hero-mouse-top-angle-gallery-1.png")
# The mouse inside Logitech's 2500x2160 picture, with a short stub of cable
PHOTO_CROP = (730, 130, 1030, 1850)


def download():
    """Fetch Logitech's photo, crop it to the mouse and save it to PHOTO_PATH. Raises on failure."""
    import urllib.request
    req = urllib.request.Request(PHOTO_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    image = QImage.fromData(data)
    if image.isNull() or (image.width(), image.height()) != (2500, 2160):
        raise ValueError(f"unexpected image ({image.width()}x{image.height()}); Logitech may have changed it")
    image = image.convertToFormat(QImage.Format.Format_ARGB32).copy(QRect(*PHOTO_CROP))
    image = image.scaled(*PHOTO_SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    PHOTO_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PHOTO_PATH.with_suffix(".part.png")
    if not image.save(str(tmp)):
        raise OSError(f"couldn't write {PHOTO_PATH}")
    tmp.replace(PHOTO_PATH)
    return PHOTO_PATH


def load_image():
    """The downloaded photo, or None if it isn't there (or is damaged)."""
    image = QImage(str(PHOTO_PATH))
    if image.isNull() or (image.width(), image.height()) != PHOTO_SIZE:
        return None
    return image


class PhotoFetcher(QObject):
    """Downloads the photo on a background thread; `done(error)` fires on the UI thread."""

    done = Signal(object)  # None on success, else the exception

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False

    def start(self):
        if self.busy:
            return
        self.busy = True

        def run():
            try:
                download()
                error = None
            except Exception as e:  # network, an unexpected image, disk
                error = e
            self.busy = False
            self.done.emit(error)
        threading.Thread(target=run, daemon=True).start()

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
        # Thumb side, seen edge-on from above: sniper tip, then forward (G5) and back (G4)
        Element(5, polygon([(82, 398), (95, 392), (101, 437), (86, 444)]), (-70, 400), anchor=(91, 418)),
        Element(4, polygon([(79, 446), (96, 436), (109, 600), (99, 613), (85, 603)]), (-70, 520), anchor=(93, 525)),
        Element(3, polygon([(100, 628), (114, 620), (140, 700), (151, 772), (141, 778), (124, 712)]),
                (-70, 690), anchor=(124, 695)),
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

    @property
    def callouts(self):
        return [
            (tr("DPI LIGHTS", "PhotoSkin"), QPointF(110, 586), QPointF(-170, 586), "zone0"),
            (tr("LOGO", "PhotoSkin"), QPointF(308, 754), QPointF(780, 754), "zone1"),
        ]

    def __init__(self, image=None):
        self.elements = elements()
        self.base = self.masks = None
        self.message = ""  # shown where the mouse goes until the photo is there
        if image is not None:
            self.set_image(image)

    @property
    def ready(self):
        return self.base is not None

    def set_image(self, image):
        self.base, self.masks = self._prepare(image.convertToFormat(QImage.Format.Format_ARGB32))

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
        if not self.ready:
            f = QFont(theme.FONT_FAMILY)
            f.setPixelSize(30)
            p.setFont(f)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, 380, *PHOTO_SIZE).adjusted(0, 0, 0, -760),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            return
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

