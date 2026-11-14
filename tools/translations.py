"""Translations of umcub-gui (Qt Linguist), run from the repository root with the program installed:

  python tools/translations.py update    # error_texts.py from the library, then the .ts files from the sources
  python tools/translations.py release   # the .qm files into umcub_gui/translations (the program loads them)

New language: copy umcub_gui_ru.ts to umcub_gui_<lang>.ts, set its language attribute, run update and translate it in
pyside6-linguist; then release. The packaged program also loads a .qm from "translations" next to it.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "umcub_gui"
TRANSLATIONS = PACKAGE / "translations"
ERROR_TEXTS = PACKAGE / "app" / "error_texts.py"


def _tool(name):
    return shutil.which(name) or str(Path(sys.executable).parent / name)


def sources():
    """The Python files with strings to translate."""
    return sorted(p for p in PACKAGE.rglob("*.py") if p.name != "selftest.py")


def has_words(template):
    """A message template with something to translate besides its {placeholders}."""
    return re.search(r"[A-Za-z]", re.sub(r"\{[^}]*\}", "", template)) is not None


def write_error_texts():
    """umcub_gui/app/error_texts.py: the library's message templates in QT_TRANSLATE_NOOP, so lupdate finds them."""
    import umcub
    texts = sorted({t for t in umcub.errors.MESSAGES.values() if has_words(t)})
    lines = ['"""The message templates of the umcub host library (umcub.errors.MESSAGES), for lupdate: the program',
             'translates a library error by its template (i18n.message). Written by tools/translations.py update;',
             'do not edit."""',
             "from PySide6.QtCore import QT_TRANSLATE_NOOP",
             "",
             "TEXTS = ("]
    lines += [f'    QT_TRANSLATE_NOOP("UmcubError", {t!r}),' for t in texts]
    lines += [")", ""]
    ERROR_TEXTS.write_text("\n".join(lines), encoding="utf-8")


def lupdate(ts):
    """Bring a .ts up to the sources: new strings unfinished, removed ones dropped; no source locations (line moves
    do not change the file)."""
    subprocess.run([_tool("pyside6-lupdate"), *map(str, sources()), "-no-obsolete", "-locations", "none",
                    "-ts", str(ts)], check=True, capture_output=True)


def update():
    write_error_texts()
    for ts in sorted(TRANSLATIONS.glob("*.ts")):
        lupdate(ts)


def release(out=TRANSLATIONS):
    for ts in sorted(TRANSLATIONS.glob("*.ts")):
        subprocess.run([_tool("pyside6-lrelease"), str(ts), "-qm", str(Path(out) / (ts.stem + ".qm"))], check=True,
                       capture_output=True)


if __name__ == "__main__":
    commands = {"update": update, "release": release}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
