"""Entry point: python -m umcub_gui, or the umcub-gui command."""
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from .app import i18n
from .app.extensions import load_extensions
from .app.history import History
from .app.settings import Settings
from .ui.main_window import MainWindow


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--self-test"]:             # the packaged build checks itself (CI): --self-test [report file]
        from . import selftest
        failures = selftest.run()
        report = "\n".join(failures) if failures else "self-test: ok"
        if len(argv) > 1:                       # a windowed build (Windows) has no stdout
            Path(argv[1]).write_text(report + "\n")
        else:
            print(report, flush=True)
        return 1 if failures else 0
    app = QApplication(sys.argv)
    app.setOrganizationName("umcub")
    app.setApplicationName("umcub-gui")
    settings = Settings()
    i18n.install(app, settings.language())
    data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    win = MainWindow(settings, History(data / "history.sqlite"))
    win.show()
    for e in load_extensions(settings):         # board names, plugins: what failed shows in the result line and log
        win.show_result(False, e)
    win.refresh()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
