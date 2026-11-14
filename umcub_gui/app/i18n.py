"""Languages: umcub_gui_<lang>.qm built from the Qt Linguist sources (tools/translations.py release) into the package,
and from the "translations" folder next to the program (a language added without a new build; it wins over the built
one). English is the source language. Library errors are translated by their template (error_texts.py)."""
import os
import sys
from pathlib import Path

import umcub
from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

BUILTIN = Path(__file__).resolve().parent.parent / "translations"
_installed = []         # the translators in use: a QTranslator must outlive its installation


def program_folder():
    """The folder of the packaged program (the AppImage file's folder, not its mount point); None from source."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(os.environ["APPIMAGE"]).parent if "APPIMAGE" in os.environ else Path(sys.executable).parent


def languages():
    """{language: .qm file} of the program's translations; English, the source language, is not one."""
    found = {}
    beside = program_folder()
    for d in [BUILTIN] + ([beside / "translations"] if beside else []):
        if d.is_dir():
            for f in sorted(d.glob("umcub_gui_*.qm")):
                found[f.stem[len("umcub_gui_"):]] = f
    return found


def system_language():
    return QLocale.system().name().split("_")[0]


def install(app, setting):
    """Translate the program into `setting` ("" = the system's language, else English); the language used."""
    for t in _installed:
        app.removeTranslator(t)
    _installed.clear()
    lang = setting or system_language()
    qm = languages().get(lang)
    if qm is None:
        return "en"
    qt = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name, folder in ((str(qm), ""), (f"qtbase_{lang}", qt)):     # Qt's own: dialog buttons
        t = QTranslator()
        if t.load(name, folder):
            app.installTranslator(t)
            _installed.append(t)
    return lang


def message(e):
    """The text of a library error in the program's language: its code's template translated and filled with its
    params; the library's English text when the template is not translated or the error has no template."""
    template = umcub.errors.MESSAGES.get(e.code)
    if template is None:
        return str(e)
    try:
        return QCoreApplication.translate("UmcubError", template).format(**e.params)
    except (KeyError, IndexError, ValueError):     # a translation with a placeholder the template does not have
        return str(e)
