"""Settings: the last session's choices and the app settings come back at the next start."""
from PySide6.QtCore import QSettings

from umcub_gui.app.settings import Session, Settings


def test_defaults(qsettings):
    s = Settings(qsettings)
    assert s.session() == Session()
    assert Session().protocol == "smp" and Session().slot == "primary" and Session().mark == ""
    assert not Session().reset
    assert s.board_name_files() == [] and s.plugins_folder() == ""


def test_session_round_trip(qsettings):
    s = Settings(qsettings)
    want = Session(adapter="/dev/ttyUSB1", node=5, uid="", admin_key="/k/admin.pem", device_key="/k/dev.pem",
                   protocol="lite", image="/img/app.signed.bin", slot="secondary", mark="test", reset=True)
    s.save_session(want)
    qsettings.sync()
    again = Settings(QSettings(qsettings.fileName(), QSettings.Format.IniFormat))
    assert again.session() == want


def test_node_none_and_uid(qsettings):
    s = Settings(qsettings)
    s.save_session(Session(adapter="udp:192.168.1.50", node=None, uid="0123456789abcdef01234567"))
    got = s.session()
    assert got.node is None and got.uid == "0123456789abcdef01234567"


def test_names_and_plugins(qsettings):
    s = Settings(qsettings)
    s.set_board_name_files(["/a/boards.json", "/b/more.json"])
    s.set_plugins_folder("/plugins")
    assert s.board_name_files() == ["/a/boards.json", "/b/more.json"] and s.plugins_folder() == "/plugins"
    s.set_board_name_files([])
    assert s.board_name_files() == []
