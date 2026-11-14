"""Translations: Qt Linguist .ts sources compiled to .qm (tools/translations.py); the language of the system or the
one chosen in Settings; library errors translated by code with the English text as the fallback; a .qm in the
"translations" folder next to the program adds a language without a new build."""
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import umcub
from PySide6.QtCore import QCoreApplication, QLocale

from conftest import translations_tool
from umcub_gui.app import error_texts, i18n
from umcub_gui.app.settings import Settings
from umcub_gui.ui.settings_dialog import SettingsDialog

ROOT = Path(__file__).resolve().parent.parent
TS = ROOT / "umcub_gui" / "translations" / "umcub_gui_ru.ts"


@pytest.fixture
def english(qapp):
    """Whatever a test installs, the next one starts in English."""
    yield
    i18n.install(qapp, "en")


def test_ts_is_complete_and_current(tmp_path):
    """Every string of the sources is in the .ts and translated, none is left over (tools/translations.py update)."""
    ts = tmp_path / TS.name
    shutil.copy(TS, ts)
    translations_tool.lupdate(ts)
    assert ts.read_text(encoding="utf-8") == TS.read_text(encoding="utf-8"), "run: python tools/translations.py update"
    unfinished = [m.findtext("source") for m in ET.parse(TS).iter("message")
                  if m.find("translation").get("type") in ("unfinished", "vanished", "obsolete")]
    assert unfinished == []


def test_error_texts_follow_the_library():
    """The library's message templates with words to translate, as lupdate sees them (tools/translations.py update
    writes the module from umcub.errors.MESSAGES)."""
    wanted = {t for t in umcub.errors.MESSAGES.values() if translations_tool.has_words(t)}
    assert set(error_texts.TEXTS) == wanted


def test_library_errors_are_translated_by_code(qapp, english):
    assert i18n.install(qapp, "ru") == "ru"
    e = umcub.UmcubError(code="smp.upload_refused", reason="no space", rc=5)
    text = i18n.message(e)
    assert text != str(e) and "no space" in text and "rc 5" in text
    assert i18n.message(umcub.UmcubError("plain text")) == "plain text"     # no code: the text itself
    i18n.install(qapp, "en")
    assert i18n.message(e) == str(e)


def test_language_from_the_setting_or_the_system(qapp, english, monkeypatch):
    assert i18n.install(qapp, "ru") == "ru"
    assert QCoreApplication.translate("MainWindow", "Flash") != "Flash"
    assert i18n.install(qapp, "en") == "en"
    assert QCoreApplication.translate("MainWindow", "Flash") == "Flash"
    monkeypatch.setattr(i18n, "system_language", lambda: "ru")
    assert i18n.install(qapp, "") == "ru"
    monkeypatch.setattr(i18n, "system_language", lambda: "de")              # no German: English
    assert i18n.install(qapp, "") == "en"


def test_qt_dialog_buttons_follow_the_language(qapp, english):
    i18n.install(qapp, "ru")
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") != "Cancel"


def test_a_language_next_to_the_program(qapp, english, tmp_path, monkeypatch):
    """A .qm in "translations" next to the program: a new language, or a newer one of a built-in language."""
    (tmp_path / "translations").mkdir()
    shutil.copy(i18n.languages()["ru"], tmp_path / "translations" / "umcub_gui_de.qm")
    monkeypatch.setattr(i18n, "program_folder", lambda: tmp_path)
    assert {"ru", "de"} <= set(i18n.languages())
    assert i18n.install(qapp, "de") == "de"


def test_settings_dialog_offers_the_languages(qtbot, qsettings):
    s = Settings(qsettings)
    d = SettingsDialog(s)
    qtbot.addWidget(d)
    assert [d.language.itemData(i) for i in range(d.language.count())] == ["", "en", "ru"]
    assert d.language.itemText(2) == QLocale("ru").nativeLanguageName().capitalize()
    d.language.setCurrentIndex(d.language.findData("ru"))
    d.apply()
    assert s.language() == "ru"
    assert Settings(qsettings).language() == "ru"


def test_every_tr_has_its_text_in_the_call():
    """lupdate only sees literal texts: self.tr(h) over a list of names stays English in every language."""
    calls = [f"{p.name}:{n}: {line.strip()}" for p in translations_tool.sources()
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if re.search(r"\btr\((?![\"'])", line)]
    assert calls == []
