"""Settings: the last session's choices and the app settings come back at the next start."""
from PySide6.QtCore import QSettings

from umcub_gui.app.batch import Row
from umcub_gui.app.settings import Session, Settings


def test_defaults(qsettings):
    s = Settings(qsettings)
    assert s.session() == Session()
    assert Session().slot == "primary" and Session().mark == "" and not Session().reset and Session().rows == []
    assert s.board_name_files() == [] and s.plugins_folder() == ""


def test_session_round_trip(qsettings):
    s = Settings(qsettings)
    want = Session(adapter="/dev/ttyUSB1", admin_key="/k/admin.pem", device_key="/k/dev.pem", slot="secondary",
                   mark="test", reset=True,
                   rows=[Row("/dev/ttyUSB1", 5, "", "smp", "/img/a.signed.bin"),
                         Row("/dev/ttyUSB1", None, "ab" * 12, "lite", "/img/b.signed.bin", checked=False),
                         Row("can:socketcan:can0", 3, "", "smp", "")])
    s.save_session(want)
    qsettings.sync()
    again = Settings(QSettings(qsettings.fileName(), QSettings.Format.IniFormat))
    assert again.session() == want


def test_names_and_plugins(qsettings):
    s = Settings(qsettings)
    s.set_board_name_files(["/a/boards.json", "/b/more.json"])
    s.set_plugins_folder("/plugins")
    assert s.board_name_files() == ["/a/boards.json", "/b/more.json"] and s.plugins_folder() == "/plugins"
    s.set_board_name_files([])
    assert s.board_name_files() == []
