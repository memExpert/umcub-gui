"""Entry point: python -m umcub_gui, or the umcub-gui command."""
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from .app.extensions import load_extensions
from .app.history import History
from .app.settings import Settings
from .ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("umcub")
    app.setApplicationName("umcub-gui")
    settings = Settings()
    data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    win = MainWindow(settings, History(data / "history.sqlite"))
    win.show()
    for e in load_extensions(settings):         # board names, plugins: what failed shows in the result line and log
        win.show_result(False, e)
    win.refresh()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
