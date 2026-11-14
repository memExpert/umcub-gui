"""Main window: the device table (one row = one device, its own image), shared adapter / keys / upload options;
discover fills the table, Flash runs the checked rows (serial rows in turn, CAN / UDP in parallel), failed rows can
be retried; the last session comes back at start."""
import shutil
from dataclasses import replace

import umcub
from PySide6.QtWidgets import QFileDialog, QHeaderView, QLabel, QPushButton

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
    rows = [Row("/dev/ttyUSB1", 6, "", "lite", "/img/a.signed.bin", checked=True),
            Row("/dev/ttyUSB1", None, "ab" * 12, "smp", "/img/b.signed.bin", checked=False)]
    Settings(qsettings).save_session(Session(adapter="/dev/ttyUSB1", admin_key="/k/a.pem", slot="secondary",
                                             mark="test", reset=True, rows=rows))
    win = window(qtbot, qsettings, tmp_path)
    assert win.adapter.currentText() == "/dev/ttyUSB1" and win.admin_key.text() == "/k/a.pem"
    assert win.slot.currentData() == "secondary" and win.mark.currentData() == "test" and win.reset.isChecked()
    assert win.rows() == [replace(r, checked=False) for r in rows]     # nothing is flashed by accident


def test_discover_link_fills_the_table(qtbot, qsettings, tmp_path, fake_umcub):
    _, answers = fake_umcub
    answers["devices"] = [dict(addr=5, uid="00" * 12, board_type=0x46103001, **LINK),
                          dict(addr=0, uid="ab" * 12, board_type=0x46411001, **LINK)]
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("/dev/ttyUSB1")
    click(qtbot, win, win.discover_button)
    assert [(r.spec, r.node, r.uid, r.protocol) for r in win.rows()] == \
        [("/dev/ttyUSB1", 5, "00" * 12, "smp"), ("/dev/ttyUSB1", None, "ab" * 12, "smp")]  # UID shown for all
    assert not any(r.checked for r in win.rows())          # the user picks what to flash
    assert "0x46103001" in win.table.item(0, win.COL_BOARD).text()
    assert win.status(0) == "found: umcub 1.0.0, addressed" and win.status(1) == "found: umcub 1.0.0, addressed"
    win.set_image(0, "/img/x.signed.bin")
    click(qtbot, win, win.discover_button)                  # again: the known rows stay, with their images
    assert len(win.rows()) == 2 and win.rows()[0].image == "/img/x.signed.bin"


def test_discover_matches_known_rows(qtbot, qsettings, tmp_path, fake_umcub):
    """A saved row is matched by its node (its UID filled in), a row of the adapter that did not answer says so."""
    _, answers = fake_umcub
    answers["devices"] = [dict(addr=5, uid="00" * 12, board_type=0x46103001, **LINK)]
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", "/img/a.signed.bin"), Row("/dev/ttyUSB1", 9, "", "smp", ""),
                  Row("/dev/ttyUSB0", 2, "", "smp", "")])
    win.adapter.setEditText("/dev/ttyUSB1")
    click(qtbot, win, win.discover_button)
    assert [(r.node, r.uid, r.image) for r in win.rows()] == \
        [(5, "00" * 12, "/img/a.signed.bin"), (9, "", ""), (2, "", "")]
    assert win.status(0).startswith("found") and win.status(1) == "not found" and win.status(2) == ""


def test_discover_nothing_is_a_warning(qtbot, qsettings, tmp_path, fake_umcub):
    win = window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("/dev/ttyUSB1")
    click(qtbot, win, win.discover_button)
    assert win.result.text() == "No device answered on /dev/ttyUSB1" and "#1a7f37" not in win.result.styleSheet()


def test_connect_status(qtbot, qsettings, tmp_path, fake_umcub):
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "00" * 12, "smp", "", checked=True)])
    click(qtbot, win, win.connect_button)
    assert win.status(0) == "connected: umcub 1.0.0, addressed"


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
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image), checked=True),
                  Row("/dev/ttyUSB1", 6, "", "smp", str(other), checked=True),
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
    win.set_rows([Row("/dev/ttyUSB1", n, "", "smp", str(signed_image), checked=True) for n in (5, 6, 7)])
    click(qtbot, win, win.flash_button)
    assert "invalid" in win.status(1) and "1 failed" in win.result.text() and win.retry_button.isEnabled()
    assert "node 6: the device reports the uploaded image invalid" in win.log.toPlainText()    # each device's error
    assert win.table.item(1, win.COL_STATUS).toolTip() == win.status(1)     # the whole text when the cell cuts it
    answers["fail_nodes"] = set()
    calls.clear()
    click(qtbot, win, win.retry_button)
    assert [c[2] for c in calls if c[0] == "connect"] == [6] and "valid" in win.status(1)
    assert not win.retry_button.isEnabled()


def test_row_without_image(qtbot, qsettings, tmp_path, fake_umcub):
    calls, _ = fake_umcub
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", "", checked=True)])
    click(qtbot, win, win.flash_button)
    assert not [c for c in calls if c[0] == "flash"] and win.status(0)


def test_connect_current_row(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, _ = fake_umcub
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image), checked=True)])
    win.table.selectRow(0)
    assert "1.2.3" in win.image_info.text() and "0x46103001" in win.image_info.text()
    click(qtbot, win, win.connect_button)
    assert [c[:3] for c in calls if c[0] == "connect"] == [("connect", "/dev/ttyUSB1", 5)]
    assert "0x46103001" in win.device_info.text()


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
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image), checked=True)])
    with qtbot.waitSignal(win.job_finished, timeout=10000):
        win.flash_button.click()
        busy = [b.isEnabled() for b in (win.add_button, win.remove_button, win.image_widget(0))]
        editable = win.table.editTriggers() != win.table.EditTrigger.NoEditTriggers
    assert busy == [False, False, False] and not editable
    assert win.add_button.isEnabled() and win.table.editTriggers() != win.table.EditTrigger.NoEditTriggers


def test_removing_rows_forgets_failed(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    _, answers = fake_umcub
    answers["fail_nodes"] = {5}
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", str(signed_image), checked=True)])
    click(qtbot, win, win.flash_button)
    assert win.retry_button.isEnabled()
    win.table.selectRow(0)
    win.remove_button.click()
    assert not win.retry_button.isEnabled()


def test_nothing_checked(qtbot, qsettings, tmp_path, fake_umcub):
    calls, _ = fake_umcub
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", "")])
    win.flash_button.click()
    assert not calls and "no device checked" in win.result.text().lower() and win.flash_button.isEnabled()


def test_image_column_resizable(qtbot, qsettings, tmp_path):
    win = window(qtbot, qsettings, tmp_path)
    header = win.table.horizontalHeader()
    assert header.sectionResizeMode(win.COL_IMAGE) == QHeaderView.ResizeMode.Interactive    # not Stretch
    assert header.stretchLastSection() and header.sectionSize(win.COL_IMAGE) == 220


def test_image_chosen_in_its_row(qtbot, qsettings, tmp_path, monkeypatch):
    """No image: a Choose... button fills the cell; with one: its file name and a small ... button at the right."""
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", ""), Row("/dev/ttyUSB1", 6, "", "smp", "")])
    cell = win.image_widget(1)
    buttons = cell.findChildren(QPushButton)
    assert len(buttons) == 1 and "Choose" in buttons[0].text() and not cell.findChildren(QLabel)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("/img/app.signed.bin", ""))
    buttons[0].click()
    assert [r.image for r in win.rows()] == ["", "/img/app.signed.bin"]     # only that row
    cell = win.image_widget(1)
    assert cell.findChildren(QLabel)[0].text() == "app.signed.bin"
    assert win.table.item(1, win.COL_IMAGE).text() == ""        # nothing drawn under the cell's widget
    assert [b.text() for b in cell.findChildren(QPushButton)] == ["..."]
    win.table.selectRow(0)
    win.remove_button.click()                                               # rows move: the button follows its row
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("/img/new.signed.bin", ""))
    win.image_widget(0).findChildren(QPushButton)[0].click()
    assert [r.image for r in win.rows()] == ["/img/new.signed.bin"]


def connected_window(qtbot, qsettings, tmp_path, signed_image):
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", str(signed_image), checked=True),
                  Row("/dev/ttyUSB0", 6, "", "lite", str(signed_image), checked=True),
                  Row("/dev/ttyUSB0", 7, "", "smp", "")])
    click(qtbot, win, win.connect_button)
    return win


def test_connect_keeps_the_checked_rows_open(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, _ = fake_umcub
    win = connected_window(qtbot, qsettings, tmp_path, signed_image)
    assert [c[:3] for c in calls if c[0] in ("open", "connect")] == \
        [("open", "/dev/ttyUSB0"), ("connect", "/dev/ttyUSB0", 5), ("connect", "/dev/ttyUSB0", 6)]
    assert win.connect_button.text() == "Disconnect"
    assert win.status(0).startswith("connected") and win.status(1).startswith("connected") and win.status(2) == ""
    calls.clear()
    click(qtbot, win, win.flash_button)                     # over the open connections: no new connect
    assert not [c for c in calls if c[0] in ("open", "connect", "close")]
    assert [c[0] for c in calls].count("flash") == 2 and "valid" in win.status(0)
    calls.clear()
    win.connect_button.click()                              # Disconnect
    assert sorted(c[:3] for c in calls) == [("close", "/dev/ttyUSB0", 5), ("close", "/dev/ttyUSB0", 6),
                                            ("close conn", "/dev/ttyUSB0")]
    assert win.connect_button.text() == "Connect" and win.status(0) == "disconnected"


def test_keepalive_marks_lost_devices(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, answers = fake_umcub
    win = connected_window(qtbot, qsettings, tmp_path, signed_image)
    answers["lost_nodes"] = {6}
    with qtbot.waitSignal(win.job_finished, timeout=5000):
        win.keepalive()
    assert ("ping", "/dev/ttyUSB0", 5, "smp") in calls and ("ping", "/dev/ttyUSB0", 6, "lite") in calls
    assert win.status(1) == "connection lost" and win.status(0).startswith("connected")
    assert win.connect_button.text() == "Disconnect"        # node 5 is still connected


def test_keepalive_interval_from_settings(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    Settings(qsettings).set_keepalive_s(7)
    win = connected_window(qtbot, qsettings, tmp_path, signed_image)
    assert win.keepalive_timer.isActive() and win.keepalive_timer.interval() == 7000
    win.connect_button.click()
    assert not win.keepalive_timer.isActive()


def test_discover_over_the_open_port(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    calls, _ = fake_umcub
    win = connected_window(qtbot, qsettings, tmp_path, signed_image)
    win.adapter.setEditText("/dev/ttyUSB0")
    calls.clear()
    click(qtbot, win, win.discover_button)
    assert calls == [("discover", "/dev/ttyUSB0", "shared")]


def test_connect_failure_per_row(qtbot, qsettings, tmp_path, fake_umcub, signed_image):
    _, answers = fake_umcub
    answers["connect"] = umcub.LinkError(code="link.no_hello")
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 9, "", "smp", "", checked=True)])
    click(qtbot, win, win.connect_button)
    assert "no answer" in win.status(0).lower() and win.connect_button.text() == "Connect"


def service_window(qtbot, qsettings, tmp_path):
    Settings(qsettings).set_role("service")
    return window(qtbot, qsettings, tmp_path)


def test_slot_panel_lists_the_selected_device(qtbot, qsettings, tmp_path, fake_umcub):
    win = service_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", "")])
    win.table.selectRow(0)
    click(qtbot, win, win.slots_refresh_button)
    assert win.slot_table.rowCount() == 2
    assert win.slot_table.item(0, 2).text() == "1.0.0" and "active" in win.slot_table.item(0, 4).text()
    assert win.slot_table.item(1, 3).text().startswith("2222")


def test_slot_action_on_checked_rows(qtbot, qsettings, tmp_path, fake_umcub):
    calls, answers = fake_umcub
    answers["verify"] = {6: False}
    win = service_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", "", checked=True),
                  Row("/dev/ttyUSB0", 6, "", "smp", "", checked=True),
                  Row("/dev/ttyUSB0", 7, "", "smp", "")])
    win.table.selectRow(0)
    click(qtbot, win, win.slots_refresh_button)
    win.slot_table.selectRow(1)                                     # the secondary slot
    click(qtbot, win, win.verify_button)
    assert [c for c in calls if c[0] == "verify"] == [("verify", 5, 0, 1), ("verify", 6, 0, 1)]
    assert win.status(0) == "slot 0/1: valid" and win.status(1).startswith("slot 0/1: invalid") and win.status(2) == ""


def test_slot_action_without_checked_rows_uses_the_selected_one(qtbot, qsettings, tmp_path, fake_umcub):
    calls, _ = fake_umcub
    win = service_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", ""), Row("/dev/ttyUSB0", 6, "", "smp", "")])
    win.table.selectRow(1)
    click(qtbot, win, win.test_button)
    assert ("mark", 6, b"\x22" * 32, False) in calls and win.status(1) == "slot 0/1: marked for a test boot"


def test_read_slot_to_a_file(qtbot, qsettings, tmp_path, fake_umcub, monkeypatch):
    _, answers = fake_umcub
    out = tmp_path / "read.bin"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    win = service_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", "")])
    win.table.selectRow(0)
    click(qtbot, win, win.read_button)
    assert out.read_bytes() == answers["read"] and "300 byte(s)" in win.result.text()


def test_lite_row_has_no_slots(qtbot, qsettings, tmp_path, fake_umcub):
    win = service_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "lite", "")])
    win.table.selectRow(0)
    assert not win.slots_refresh_button.isEnabled() and "SMP" in win.slots_info.text()


def test_roles_show_what_a_role_needs(qtbot, qsettings, tmp_path):
    seen = {}
    for role in ("customer", "operator", "service", "developer"):
        Settings(qsettings).set_role(role)
        win = window(qtbot, qsettings, tmp_path)
        seen[role] = (not win.discover_button.isHidden(), win.tabs.isTabVisible(1), not win.slot_panel.isHidden())
    assert seen == {"customer": (False, False, False), "operator": (True, True, False),
                    "service": (True, True, True), "developer": (True, True, True)}


def test_slot_table_follows_the_selected_device(qtbot, qsettings, tmp_path, fake_umcub):
    win = service_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", ""), Row("/dev/ttyUSB0", 6, "", "smp", "")])
    win.table.selectRow(0)
    click(qtbot, win, win.slots_refresh_button)
    assert win.slot_table.rowCount() == 2
    win.table.selectRow(1)                          # another device: the slots shown were node 5's
    assert win.slot_table.rowCount() == 0


def test_lite_rows_in_a_slot_action_say_so(qtbot, qsettings, tmp_path, fake_umcub):
    calls, _ = fake_umcub
    win = service_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", "", checked=True),
                  Row("/dev/ttyUSB0", 6, "", "lite", "", checked=True)])
    win.table.selectRow(0)
    click(qtbot, win, win.verify_button)
    assert [c[1] for c in calls if c[0] == "verify"] == [5]
    assert win.status(0) == "slot 0/0: valid" and win.status(1) == "no slots with lite"
    assert "1 of 2" in win.result.text()


def developer_window(qtbot, qsettings, tmp_path):
    Settings(qsettings).set_role("developer")
    return window(qtbot, qsettings, tmp_path)


def hello(node, conn):
    from umcub import link
    return umcub.TapEvent(1.0, "tx", umcub.KIND_LINK, link.make_frame(link.T_HELLO, 0, node, 1, b""), conn)


def test_developer_tab_only_for_developers(qtbot, qsettings, tmp_path):
    assert not service_window(qtbot, qsettings, tmp_path).tabs.isTabVisible(2)
    assert developer_window(qtbot, qsettings, tmp_path).tabs.isTabVisible(2)


def test_exchange_log_shows_the_traffic(qtbot, qsettings, tmp_path, fake_umcub):
    win = developer_window(qtbot, qsettings, tmp_path)
    win.adapter.setEditText("/dev/ttyUSB0")
    click(qtbot, win, win.discover_button)                  # the fake library taps one HELLO
    win.exchange.flush()
    assert "HELLO" in win.exchange_view.toPlainText() and "/dev/ttyUSB0" in win.exchange_view.toPlainText()


def test_exchange_log_pause_clear_save(qtbot, qsettings, tmp_path, monkeypatch):
    win = developer_window(qtbot, qsettings, tmp_path)
    for ev in (hello(5, "/dev/ttyUSB0"), hello(6, "/dev/ttyUSB1"), hello(7, "/dev/ttyUSB0")):
        win.exchange(ev)
    win.exchange.flush()
    assert win.exchange_view.toPlainText().count("HELLO") == 3
    win.pause_button.setChecked(True)
    win.exchange(hello(5, "/dev/ttyUSB0"))
    win.exchange.flush()
    assert win.exchange_view.toPlainText().count("HELLO") == 3
    win.pause_button.setChecked(False)
    out = tmp_path / "log.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    win.save_log_button.click()
    saved = out.read_text(encoding="utf-8").splitlines()
    assert len(saved) == 4 and saved[0].endswith(hello(5, "/dev/ttyUSB0").payload.hex())   # all, the bytes whole
    win.clear_log_button.click()
    assert win.exchange_view.toPlainText() == "" and win.exchange.events() == []


def test_exchange_log_filter_matches_the_connection_name(qtbot, qsettings, tmp_path, fake_umcub):
    """The library names a UDP connection "ip:port", the row says "ip"; /dev/ttyUSB1 is not /dev/ttyUSB10."""
    win = developer_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB1", 5, "", "smp", "", True), Row("/dev/ttyUSB10", 5, "", "smp", "", True),
                  Row("192.168.1.50", 5, "", "smp", "", True)])
    click(qtbot, win, win.connect_button)                   # each connection taps one HELLO to node 5
    win.exchange(hello(6, "/dev/ttyUSB1"))                  # another node on the same port
    win.exchange.flush()
    assert win.exchange_view.toPlainText().count("HELLO") == 4
    win.table.selectRow(0)
    win.filter_check.setChecked(True)
    shown = win.exchange_view.toPlainText().splitlines()
    assert len(shown) == 1 and "/dev/ttyUSB1 " in shown[0] and "node 5" in shown[0]
    win.table.selectRow(2)                                  # another row: the log follows it
    shown = win.exchange_view.toPlainText().splitlines()
    assert len(shown) == 1 and "192.168.1.50:1337" in shown[0]
    win.table.selectRow(1)
    assert "/dev/ttyUSB10" in win.exchange_view.toPlainText()


def test_exchange_log_filter_on_can(qtbot, qsettings, tmp_path, fake_umcub):
    """Every node of a CAN channel has the same connection name and SMP packets carry no node: the node of the
    connection that saw the packet tells them apart."""
    win = developer_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("can:socketcan:can0", 1, "", "smp", "", True), Row("can:socketcan:can0", 2, "", "smp", "", True)])
    click(qtbot, win, win.connect_button)                   # one SMP echo per node
    win.exchange.flush()
    assert win.exchange_view.toPlainText().count("os/echo") == 2
    win.table.selectRow(1)
    win.filter_check.setChecked(True)
    assert win.exchange_view.toPlainText().count("os/echo") == 1


def test_console_sends_a_text_command(qtbot, qsettings, tmp_path, fake_umcub):
    calls, _ = fake_umcub
    win = developer_window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", "")])
    win.table.selectRow(0)
    win.console_input.setText("i")
    click(qtbot, win, win.send_button)
    assert ("text", "/dev/ttyUSB0", 5, "i") in calls
    assert "> i" in win.console_view.toPlainText() and "board 0x46103001" in win.console_view.toPlainText()
    assert win.console_input.text() == ""


def test_one_image_cell_per_row(qtbot, qsettings, tmp_path):
    """Filling a row makes its image cell once: a second one stayed over the first columns, untracked."""
    win = window(qtbot, qsettings, tmp_path)
    win.set_rows([Row("/dev/ttyUSB0", 5, "", "smp", "/img/a.signed.bin"), Row("/dev/ttyUSB0", 6, "", "lite", "")])
    win.add_row()
    buttons = win.table.viewport().findChildren(QPushButton)
    assert len(buttons) == 3
    assert all(any(b.parent() is win.image_widget(i) for i in range(3)) for b in buttons)
