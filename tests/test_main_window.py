"""Main window: one form; the last session comes back, flash / discover run as jobs, results in the result line,
the log and the history tab."""
import umcub

from umcub_gui.app.history import History
from umcub_gui.app.settings import Session, Settings
from umcub_gui.ui.main_window import MainWindow


def window(qtbot, qsettings, tmp_path):
    win = MainWindow(Settings(qsettings), History(tmp_path / "h.sqlite"))
    qtbot.addWidget(win)
    return win


def test_title(qtbot, qsettings, tmp_path):
    assert "umcub" in window(qtbot, qsettings, tmp_path).windowTitle()


def test_last_session_restored(qtbot, qsettings, tmp_path):
    Settings(qsettings).save_session(Session(adapter="/dev/ttyUSB1", node=6, admin_key="/k/a.pem", protocol="lite",
                                             image="/img/app.signed.bin", slot="secondary", mark="test", reset=True))
    win = window(qtbot, qsettings, tmp_path)
    assert win.adapter.currentText() == "/dev/ttyUSB1" and win.node.text() == "6"
    assert win.admin_key.text() == "/k/a.pem" and win.protocol_lite.isChecked()
    assert win.image.text() == "/img/app.signed.bin" and win.slot.currentData() == "secondary"
    assert win.mark.currentData() == "test" and win.reset.isChecked()


def test_flash_ok(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, _ = fake_umcub
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("/dev/ttyUSB1")
    win.node.setText("5")
    win.image.setText(str(signed_image))
    win.reset.setChecked(True)
    with qtbot.waitSignal(win.job_finished, timeout=5000):
        win.flash_button.click()
    assert ("flash", "1.2.3", "smp", None, False, False, True) in calls
    assert "valid" in win.result.text()
    assert win.progress.value() == win.progress.maximum()
    assert win.history_table.rowCount() == 1
    assert Settings(qsettings).session().node == 5          # the choices are saved for the next start


def test_flash_error(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    _, answers = fake_umcub
    answers["flash"] = umcub.UmcubError(code="flash.invalid")
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("/dev/ttyUSB1")
    win.image.setText(str(signed_image))
    with qtbot.waitSignal(win.job_finished, timeout=5000):
        win.flash_button.click()
    assert "invalid" in win.result.text() and "invalid" in win.log.toPlainText()
    assert win.history_table.rowCount() == 1


def test_image_info(qtbot, qsettings, tmp_path, signed_image):
    win = window(qtbot, qsettings, tmp_path)
    win.image.setText(str(signed_image))
    assert "1.2.3" in win.image_info.text() and "0x46103001" in win.image_info.text()
    win.image.setText(str(tmp_path / "missing.bin"))
    assert "1.2.3" not in win.image_info.text()


def test_discover_fills_the_list(qtbot, qsettings, tmp_path, fake_umcub):
    _, answers = fake_umcub
    answers["devices"] = [{"addr": 5, "uid": "00" * 12, "board_type": 0x46103001, "board_rev": 1, "link": 1,
                           "enc": False, "closed": False, "version": "1.0.0"},
                          {"addr": 0, "uid": "ab" * 12, "board_type": 0x46411001, "board_rev": 1, "link": 1,
                           "enc": False, "closed": False, "version": "1.0.0"}]
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("/dev/ttyUSB1")
    with qtbot.waitSignal(win.job_finished, timeout=5000):
        win.discover_button.click()
    assert win.devices.count() == 2
    win.devices.setCurrentIndex(1)                          # unassigned: selected by UID
    assert win.node.text() == "" and win.uid.text() == "ab" * 12
    win.devices.setCurrentIndex(0)
    assert win.node.text() == "5" and win.uid.text() == ""


def test_adapters_listed(qtbot, qsettings, tmp_path, fake_umcub):
    _, answers = fake_umcub
    answers["adapters"] = [umcub.Adapter("/dev/ttyUSB0", "serial", "ttyUSB0", "FT232R"),
                           umcub.Adapter("", "udp", "enp12s0", "no link (cable?)")]
    win = window(qtbot, qsettings, tmp_path)
    with qtbot.waitSignal(win.job_finished, timeout=5000):
        win.refresh_button.click()
    specs = [win.adapter.itemData(i) for i in range(win.adapter.count())]
    assert "/dev/ttyUSB0" in specs
    assert any("FT232R" in win.adapter.itemText(i) for i in range(win.adapter.count()))
