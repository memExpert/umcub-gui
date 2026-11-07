"""Main window (placeholder until the first screens exist)."""
from PySide6.QtWidgets import QLabel, QMainWindow

from .. import __version__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("umcub {0}").format(__version__))
        self.setCentralWidget(QLabel(self.tr("No screens yet: see docs/plan.md.")))
        self.resize(800, 500)
