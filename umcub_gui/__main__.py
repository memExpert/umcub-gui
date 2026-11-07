"""Entry point: python -m umcub_gui, or the umcub-gui command."""
import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("umcub-gui")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
