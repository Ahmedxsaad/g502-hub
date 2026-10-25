"""Hotspot shapes shared by the mouse skins."""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QPolygonF


class Element:
    """A clickable part of the mouse: an onboard button slot (0-10) or "zone0"/"zone1".

    `badge_at` is where its label goes; `anchor`, when set, is the point on the
    mouse a leader line runs to from a badge placed off the body.
    """

    def __init__(self, key, path, badge_at, kind="button", anchor=None):
        self.key = key
        self.path = path
        self.badge_at = QPointF(*badge_at)
        self.kind = kind
        self.anchor = QPointF(*anchor) if anchor else None


def rounded(x, y, w, h, r=2):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def ellipse(cx, cy, rx, ry=None):
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry or rx)
    return path


def polygon(points):
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(*p) for p in points]))
    path.closeSubpath()
    return path
