"""Pages of the main window. Each owns a side panel and drives the mouse view."""

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


class Page:
    title = ""
    icon = ""
    mouse_mode = "plain"
    center = None  # a widget to show instead of the mouse view

    def __init__(self, state, view, keylabels):
        self.state = state
        self.view = view
        self.keylabels = keylabels
        self.panel = QScrollArea()
        self.panel.setWidgetResizable(True)
        self.panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self.layout = QVBoxLayout(inner)
        self.layout.setContentsMargins(22, 20, 22, 20)
        self.layout.setSpacing(16)
        self.panel.setWidget(inner)

    def tr(self, text, disambiguation=None, n=-1):
        return QCoreApplication.translate(type(self).__name__, text, disambiguation, n)

    def activate(self):
        self.view.set_mode(self.mouse_mode)
        self.reset()

    def reset(self):
        """A different profile is shown (load, switch): rebuild page state from it."""
        self.refresh()

    def refresh(self):
        """The shown profile was edited: update widgets from it."""

    def on_view_click(self, key):
        pass
