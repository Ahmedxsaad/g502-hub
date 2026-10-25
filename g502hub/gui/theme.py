"""G HUB-style dark theme: palette, fonts, stylesheet and painted icons."""

from math import cos, pi, sin
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap

ASSETS = Path(__file__).with_name("assets").as_posix()

BG = "#0e0f12"
PANEL = "#16181c"
RAISED = "#1e2126"
HOVER = "#262a30"
BORDER = "#2a2e35"
TEXT = "#e9eaec"
MUTED = "#8b9099"
FAINT = "#6b707a"
ACCENT = "#14b4ff"
ACCENT_DIM = "#0b5f87"
DANGER = "#ff5a5f"
OK = "#3ddc84"

FONT_FAMILY = "Inter"

STYLESHEET = f"""
* {{
    font-family: "{FONT_FAMILY}", "Noto Sans", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, #Root {{ background: {BG}; }}
#TopBar {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
#Rail {{ background: {BG}; border-right: 1px solid {BORDER}; }}
#SidePanel {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
#Card {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 6px; }}
#Card[active="true"] {{ border: 1px solid {ACCENT}; }}

QLabel#Title {{ font-size: 16px; font-weight: 600; }}
QLabel#Heading {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Faint {{ color: {FAINT}; font-size: 12px; }}
QLabel#LiveDpi {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: 13px; padding: 4px 12px;
    font-size: 11px; font-weight: 600; letter-spacing: 1px;
}}
QLabel#Status {{ color: {MUTED}; font-size: 12px; }}
QLabel#Status[kind="error"] {{ color: {DANGER}; }}
QLabel#Status[kind="ok"] {{ color: {OK}; }}

QPushButton {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {FAINT}; }}
QPushButton#Primary {{ background: {ACCENT}; border: none; color: #001018; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #45c4ff; }}
QPushButton#Danger {{ color: {DANGER}; }}
QPushButton#Flat {{ background: transparent; border: none; color: {MUTED}; padding: 4px 6px; }}
QPushButton#Flat:hover {{ color: {TEXT}; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

QPushButton#Segment {{
    background: transparent; border: none; border-bottom: 2px solid transparent;
    border-radius: 0; color: {MUTED}; font-size: 11px; font-weight: 600;
    letter-spacing: 1.2px; padding: 8px 10px;
}}
QPushButton#Segment:hover {{ color: {TEXT}; }}
QPushButton#Segment:checked {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

QPushButton#Choice {{
    background: {RAISED}; text-align: left; padding: 9px 12px; border-radius: 4px;
}}
QPushButton#Choice:checked {{ border: 1px solid {ACCENT}; background: #10293a; }}

QToolButton#RailButton {{
    background: transparent; border: none; border-left: 3px solid transparent;
    padding: 10px 0; color: {MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 1px;
}}
QToolButton#RailButton:hover {{ color: {TEXT}; }}
QToolButton#RailButton:checked {{ color: {TEXT}; border-left: 3px solid {ACCENT}; }}

QLineEdit, QSpinBox, QComboBox {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 8px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({ASSETS}/chevron-down.svg); width: 12px; height: 12px; }}
QComboBox#ProfileBox {{
    /* Qt drops a radius larger than half the height, so the height is fixed */
    background: transparent; border: 1px solid {BORDER}; border-radius: 17px; padding: 0 16px;
    min-height: 34px; max-height: 34px; font-size: 11px; font-weight: 600; letter-spacing: 1.2px;
}}
QComboBox#ProfileBox:hover {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {BORDER}; selection-background-color: {HOVER};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}

QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 4px; margin: 1px 0; }}
QListWidget::item:hover {{ background: {HOVER}; }}
QListWidget::item:selected {{ background: #10293a; color: {TEXT}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > #qt_scrollarea_viewport, QScrollArea > #qt_scrollarea_viewport > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1px solid {FAINT}; border-radius: 3px; background: {RAISED};
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT}; image: url({ASSETS}/check.svg);
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}

QMenu {{ background: {RAISED}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 3px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QMessageBox {{ background: {PANEL}; }}
"""


def palette():
    """Dark palette so unstyled surfaces (viewports, dialogs, menus) match the stylesheet."""
    pal = QPalette()
    R = QPalette.ColorRole
    for role, color in ((R.Window, PANEL), (R.WindowText, TEXT), (R.Base, RAISED), (R.AlternateBase, PANEL),
                        (R.Text, TEXT), (R.Button, RAISED), (R.ButtonText, TEXT), (R.BrightText, DANGER),
                        (R.Highlight, ACCENT_DIM), (R.HighlightedText, TEXT), (R.ToolTipBase, RAISED),
                        (R.ToolTipText, TEXT), (R.PlaceholderText, FAINT), (R.Link, ACCENT)):
        pal.setColor(role, QColor(color))
    for role in (R.WindowText, R.Text, R.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(FAINT))
    return pal


def font(size=13, weight=QFont.Weight.Normal):
    f = QFont(FONT_FAMILY)
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def _icon_path(name):
    """24x24 outline paths for the navigation rail."""
    p = QPainterPath()
    if name == "lighting":
        p.addEllipse(QPointF(12, 12), 4.5, 4.5)
        for i in range(8):
            a = i * pi / 4
            p.moveTo(12 + 7.5 * cos(a), 12 + 7.5 * sin(a))
            p.lineTo(12 + 10 * cos(a), 12 + 10 * sin(a))
    elif name == "assignments":
        p.addRoundedRect(QRectF(6, 2.5, 12, 19), 6, 6)
        p.moveTo(12, 2.5)
        p.lineTo(12, 10)
        p.moveTo(6, 10)
        p.lineTo(18, 10)
    elif name == "sensitivity":
        p.addEllipse(QPointF(12, 12), 8, 8)
        p.addEllipse(QPointF(12, 12), 2, 2)
        for a, b in (((12, 1), (12, 6)), ((12, 18), (12, 23)), ((1, 12), (6, 12)), ((18, 12), (23, 12))):
            p.moveTo(*a)
            p.lineTo(*b)
    elif name == "profiles":
        for y in (5, 12, 19):
            p.addRoundedRect(QRectF(3, y - 2.5, 18, 5), 1.5, 1.5)
    return p


def icon(name, color=MUTED, active=TEXT, size=24):
    result = QIcon()
    for mode, c in ((QIcon.Mode.Normal, color), (QIcon.Mode.Active, active), (QIcon.Mode.Selected, active)):
        for state, cc in ((QIcon.State.Off, c), (QIcon.State.On, active)):
            pix = QPixmap(size * 2, size * 2)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.scale(2 * size / 24, 2 * size / 24)
            painter.setPen(QPen(QColor(cc), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(_icon_path(name))
            painter.end()
            pix.setDevicePixelRatio(2)
            result.addPixmap(pix, mode, state)
    return result
