"""Hotspot shapes shared by the mouse skins."""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QPolygonF, QTransform


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
