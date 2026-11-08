"""Settings dialog: OK saves and loads; what failed to load keeps the dialog open with the error."""
import umcub

from umcub_gui.app.settings import Settings
from umcub_gui.ui.settings_dialog import SettingsDialog


def test_ok_saves_and_loads(qtbot, qsettings, tmp_path):
    (tmp_path / "a.json").write_text('{"0x46103001": "Blue Pill"}')
    s = Settings(qsettings)
    d = SettingsDialog(s)
    qtbot.addWidget(d)
    d.names.addItem(str(tmp_path / "a.json"))
    try:
        d.apply()
        assert d.result() == d.DialogCode.Accepted and s.board_name_files() == [str(tmp_path / "a.json")]
        assert umcub.board_label(0x46103001) == "0x46103001 (Blue Pill)"
    finally:
        umcub.load_board_names()


def test_error_keeps_it_open(qtbot, qsettings, tmp_path):
    (tmp_path / "bad.json").write_text("{")
    d = SettingsDialog(Settings(qsettings))
    qtbot.addWidget(d)
    d.names.addItem(str(tmp_path / "bad.json"))
    d.apply()
    assert d.result() != d.DialogCode.Accepted and "bad.json" in d.errors.text()
