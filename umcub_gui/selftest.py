"""--self-test: the packaged program (PyInstaller) checks what a build can leave out - modules imported by name or
only when a device is used, python-can's interfaces, the Qt platform and the window - and lists what failed. CI runs
it on every build; the development tree passes it too (tests/test_selftest.py)."""
import importlib
import logging
import tempfile
import warnings
from pathlib import Path

# Imported when a device is used, not at start: a build without them starts and fails at the first device.
LAZY_MODULES = ("smpclient", "isotp", "serial.tools.list_ports", "psutil",
                "cryptography.hazmat.primitives.asymmetric.ec")


def missing_can_interfaces():
    """python-can's interface modules (can:<interface>:<channel>) the program lacks. They are imported by name; one
    whose vendor package or driver is missing (kvaser, ixxat, ...) fails only when used and is no failure here."""
    from can.interfaces import BACKENDS
    log = logging.getLogger("can")
    level = log.level
    log.setLevel(logging.CRITICAL)              # each interface without its driver logs a warning on import
    missing = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")     # and some warn about their ctypes structures
            for name, (module, _) in sorted(BACKENDS.items()):
                try:
                    importlib.import_module(module)
                except ModuleNotFoundError as e:
                    if e.name and (e.name == "can" or e.name.startswith("can.")):
                        missing.append(name)
                except Exception:               # e.g. a Windows-only interface on Linux: present, not usable here
                    pass
    finally:
        log.setLevel(level)
    return missing


def _can():
    import can
    missing = missing_can_interfaces()
    if missing:
        raise RuntimeError(f"interfaces missing: {', '.join(missing)}")
    with can.Bus(interface="virtual", channel="selftest"):
        pass


def _adapters():
    import umcub
    errors = []                                 # a source that fails is skipped, its error only lands here
    umcub.adapters(errors=errors)
    if errors:
        raise RuntimeError("; ".join(errors))


_qapp = None


def _app():
    """The one QApplication of the steps (kept: an unreferenced QApplication is deleted at once)."""
    global _qapp
    from PySide6.QtWidgets import QApplication
    _qapp = QApplication.instance() or QApplication([])
    return _qapp


def _window():
    from PySide6.QtCore import QSettings

    from .app.history import History
    from .app.settings import Settings
    from .ui.main_window import MainWindow
    _app()
    with tempfile.TemporaryDirectory() as d:
        history = History(Path(d) / "h.sqlite")
        MainWindow(Settings(QSettings(str(Path(d) / "s.ini"), QSettings.Format.IniFormat)), history).close()
        history.db.close()


def _translations():
    """Every built-in language loads with Qt's own translations (dialog buttons); a build without them fails."""
    from PySide6.QtCore import QCoreApplication

    from .app import i18n
    langs = i18n.languages()
    if not langs:
        raise RuntimeError("no translations (tools/translations.py release before the build)")
    app = _app()
    try:
        for lang in langs:
            if i18n.install(app, lang) != lang or QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancel":
                raise RuntimeError(f"{lang} does not load (or Qt's own translation is missing)")
    finally:
        i18n.install(app, "en")


def run():
    """The failures, as lines; [] when the program has everything."""
    failures = []
    for m in LAZY_MODULES:
        try:
            importlib.import_module(m)
        except Exception as e:
            failures.append(f"module {m}: {type(e).__name__}: {e}")
    for name, step in (("CAN", _can), ("umcub.adapters()", _adapters), ("window", _window),
                       ("translations", _translations)):
        try:
            step()
        except Exception as e:
            failures.append(f"{name}: {type(e).__name__}: {e}")
    return failures
