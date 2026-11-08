"""Main window: the device table (one row = one device, its own image), shared adapter / keys / upload options;
discover fills the table, Flash runs the checked rows (serial rows in turn, CAN / UDP in parallel), failed rows can
be retried; the last session comes back at start."""
import shutil

import umcub

from umcub_gui.app.batch import Row
from umcub_gui.app.history import History
from umcub_gui.app.settings import Session, Settings
from umcub_gui.ui.main_window import MainWindow

LINK = {"board_rev": 1, "link": 1, "enc": False, "closed": False, "version": "1.0.0"}


def window(qtbot, qsettings, tmp_path):
    win = MainWindow(Settings(qsettings), History(tmp_path / "h.sqlite"))
    qtbot.addWidget(win)
    return win


def click(qtbot, win, button):
    with qtbot.waitSignal(win.job_finished, timeout=10000):
        button.click()


def test_title(qtbot, qsettings, tmp_path):
    assert "umcub" in window(qtbot, qsettings, tmp_path).windowTitle()


def test_last_session_restored(qtbot, qsettings, tmp_path):
    rows = [Row("/dev/ttyUSB1", 6, "", "lite", "/img/a.signed.bin"),
            Row("/dev/ttyUSB1", None, "ab" * 12, "smp", "/img/b.signed.bin", checked=False)]
    Settings(qsettings).save_session(Session(adapter="/dev/ttyUSB1", admin_key="/k/a.pem", slot="secondary",
                                             mark="test", reset=True, rows=rows))
    win = window(qtbot, qsettings, tmp_path)
    assert win.adapter.currentText() == "/dev/ttyUSB1" and win.admin_key.text() == "/k/a.pem"
    assert win.slot.currentData() == "secondary" and win.mark.currentData() == "test" and win.reset.isChecked()
    assert win.rows() == rows


def test_discover_link_fills_the_table(qtbot, qsettings, tmp_path, fake_umcub):
    _, answers = fake_umcub
    answers["devices"] = [dict(addr=5, uid="00" * 12, board_type=0x46103001, **LINK),
                          dict(addr=0, uid="ab" * 12, board_type=0x46411001, **LINK)]
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("/dev/ttyUSB1")
    click(qtbot, win, win.discover_button)
    assert [(r.spec, r.node, r.uid, r.protocol) for r in win.rows()] == \
        [("/dev/ttyUSB1", 5, "", "smp"), ("/dev/ttyUSB1", None, "ab" * 12, "smp")]     # unassigned: by UID
    assert "0x46103001" in win.table.item(0, win.COL_BOARD).text()
    win.set_image([0], "/img/x.signed.bin")
    click(qtbot, win, win.discover_button)                  # again: the known rows stay, with their images
    assert len(win.rows()) == 2 and win.rows()[0].image == "/img/x.signed.bin"


def test_discover_can(qtbot, qsettings, tmp_path, fake_umcub):
    _, answers = fake_umcub
    answers["devices"] = [{"addr": 0, "protocol": "smp"}, {"addr": 3, "protocol": "lite"}]
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("can:socketcan:can0")
    click(qtbot, win, win.discover_button)
    assert [(r.node, r.uid, r.protocol) for r in win.rows()] == [(0, "", "smp"), (3, "", "lite")]


def test_add_and_remove_rows(qtbot, qsettings, tmp_path):
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("192.168.1.50")
    win.add_button.click()
    assert win.rows() == [Row("192.168.1.50", None, "", "smp", "")]
    win.table.selectRow(0)
    win.remove_button.click()
    assert win.rows() == []


def test_flash_checked_rows(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, _ = fake_umcub
    other = tmp_path / "other.signed.bin"
    shutil.copy(signed_image, other)
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image)),
                  Row("/dev/ttyUSB1", 6, "", "smp", str(other)),
                  Row("/dev/ttyUSB1", 7, "", "smp", str(signed_image), checked=False)])
    win.reset.setChecked(True)
    click(qtbot, win, win.flash_button)
    assert sorted(c[2] for c in calls if c[0] == "connect") == [5, 6]
    assert ("flash", "1.2.3", "smp", None, False, False, True) in calls
    assert "valid" in win.status(0) and "valid" in win.status(1) and win.status(2) == ""
    assert "2 ok" in win.result.text()
    assert sorted(r.image_name for r in win.history.records()) == ["app.signed.bin", "other.signed.bin"]
    assert win.history_table.rowCount() == 2
    assert Settings(qsettings).session().rows == win.rows()      # saved for the next start


def test_failed_rows_retried(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, answers = fake_umcub
    answers["fail_nodes"] = {6}
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", n, "", "smp", str(signed_image)) for n in (5, 6, 7)])
    click(qtbot, win, win.flash_button)
    assert "invalid" in win.status(1) and "1 failed" in win.result.text() and win.retry_button.isEnabled()
    assert "node 6: the device reports the uploaded image invalid" in win.log.toPlainText()    # each device's error
    answers["fail_nodes"] = set()
    calls.clear()
    click(qtbot, win, win.retry_button)
    assert [c[2] for c in calls if c[0] == "connect"] == [6] and "valid" in win.status(1)
    assert not win.retry_button.isEnabled()


def test_row_without_image(qtbot, qsettings, tmp_path, fake_umcub):
    calls, _ = fake_umcub
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", "")])
    click(qtbot, win, win.flash_button)
    assert not [c for c in calls if c[0] == "flash"] and win.status(0)


def test_connect_current_row(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, _ = fake_umcub
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image))])
    win.table.selectRow(0)
    assert "1.2.3" in win.image_info.text() and "0x46103001" in win.image_info.text()
    click(qtbot, win, win.connect_button)
    assert calls[0][:3] == ("connect", "/dev/ttyUSB1", 5) and "0x46103001" in win.device_info.text()


def test_adapters_listed(qtbot, qsettings, tmp_path, fake_umcub):
    _, answers = fake_umcub
    answers["adapters"] = [umcub.Adapter("/dev/ttyUSB0", "serial", "ttyUSB0", "FT232R"),
                           umcub.Adapter("", "udp", "enp12s0", "no link (cable?)")]
    win = window(qtbot, qsettings, tmp_path)
    click(qtbot, win, win.refresh_button)
    specs = [win.adapter.itemData(i) for i in range(win.adapter.count())]
    assert "/dev/ttyUSB0" in specs
    assert any("FT232R" in win.adapter.itemText(i) for i in range(win.adapter.count()))


def test_table_locked_while_flashing(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    _, answers = fake_umcub
    answers["delay"] = 0.4
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image))])
    with qtbot.waitSignal(win.job_finished, timeout=10000):
        win.flash_button.click()
        busy = [b.isEnabled() for b in (win.add_button, win.remove_button, win.image_button)]
        editable = win.table.editTriggers() != win.table.EditTrigger.NoEditTriggers
    assert busy == [False, False, False] and not editable
    assert win.add_button.isEnabled() and win.table.editTriggers() != win.table.EditTrigger.NoEditTriggers


def test_removing_rows_forgets_failed(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    _, answers = fake_umcub
    answers["fail_nodes"] = {5}
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image))])
    click(qtbot, win, win.flash_button)
    assert win.retry_button.isEnabled()
    win.table.selectRow(0)
    win.remove_button.click()
    assert not win.retry_button.isEnabled()
