"""ABOUT page: who made it, links, license, credits, and system info for bug reports."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ... import about
from .. import system, theme
from ..widgets import heading, muted
from . import Page


def _label(text, name=None, size=None, weight=None, spacing=None, color=None):
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    style = []
    if size:
        style.append(f"font-size: {size}px;")
    if weight:
        style.append(f"font-weight: {weight};")
    if spacing:
        style.append(f"letter-spacing: {spacing}px;")
    if color:
        style.append(f"color: {color};")
    if style:
        label.setStyleSheet(" ".join(style))
    return label


class AboutPage(Page):
    title = "ABOUT"
    icon = "about"

    def __init__(self, *args):
        super().__init__(*args)
        self.center = QScrollArea()
        self.center.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(48, 56, 48, 40)
        col.setSpacing(10)
        col.addStretch(1)
        col.addWidget(_label(about.APP_NAME.upper(), size=34, weight=800, spacing=6))
        col.addWidget(_label(about.TAGLINE, "Muted", size=14))
        col.addSpacing(18)
        col.addWidget(_label("MADE BY", "Heading"))
        col.addWidget(_label(about.AUTHOR, size=22, weight=700, color=theme.ACCENT))
        col.addSpacing(14)

        links = QHBoxLayout()
        links.addStretch()
        for i, (label, url) in enumerate(about.links()):
            b = QPushButton(label)
            b.setObjectName("Primary" if i == 0 else "")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(url)
            b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            links.addWidget(b)
        links.addStretch()
        col.addLayout(links)
        col.addSpacing(18)

        col.addWidget(_label(f"Version {about.VERSION}   ·   Free software under the GNU GPL v3 or later",
                             "Muted"))
        col.addSpacing(24)
        col.addWidget(_label("BUILT ON THE WORK OF", "Heading"))
        credits = "   ·   ".join(f"<a style='color:{theme.MUTED}; text-decoration:none' href='{url}'>{name}</a>"
                                 for name, url in about.CREDITS)
        credit_label = _label(credits)
        credit_label.setTextFormat(Qt.TextFormat.RichText)
        credit_label.setOpenExternalLinks(True)
        col.addWidget(credit_label)
        col.addSpacing(24)
        col.addWidget(_label(about.DISCLAIMER, "Faint"))
        col.addStretch(2)
        self.center.setWidget(inner)

        title = QLabel("About")
        title.setObjectName("Title")
        self.layout.addWidget(title)
        self.layout.addWidget(heading("This computer"))
        self.info = muted("")
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout.addWidget(self.info)
        copy = QPushButton("Copy for a bug report")
        copy.clicked.connect(self._copy)
        self.layout.addWidget(copy)
        self.copied = muted("", "Faint")
        self.layout.addWidget(self.copied)
        self.layout.addStretch()

    def _lines(self):
        s = self.state
        lines = system.session_info()
        if s.connected:
            lines.append(f"{s.name}, firmware {', '.join(f for _, f in s.firmware)}")
            lines.append(f"Profile format {s.info.profile_format}, {s.info.sector_count} × {s.info.sector_size} B")
        else:
            lines.append("Mouse not connected")
        return lines

    def refresh(self):
        self.info.setText("\n".join(self._lines()))

    def _copy(self):
        QGuiApplication.clipboard().setText("\n".join(self._lines()))
        self.copied.setText("Copied. Paste it into your bug report.")
