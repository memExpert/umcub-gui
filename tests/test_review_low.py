"""LOW findings of the review: keys only for link rows (the host library refuses unused keys), old saved
sessions, self-test modules, history paging and history error texts in the current language, device logic in app/."""
import json

import umcub

from umcub_gui import selftest
from umcub_gui.app import i18n
from umcub_gui.app.devices import image_check, match_discovered
from umcub_gui.app.history import History, Record
from umcub_gui.app.jobs import Target, connect_target
from umcub_gui.app.settings import Settings


def test_keys_only_where_a_secure_session_can_follow(fake_umcub):
    calls, _ = fake_umcub
    for spec, node, uid, keys in (("can:socketcan:can0", 5, "", True),      # CAN node 5: SECURE over its IDs
                                  ("can:socketcan:can0", 0, "", False),     # CAN node 0: never SECURE
                                  ("plug:x", 5, "", False),                  # a plugin adapter selecting the node
                                  ("/dev/ttyUSB0", None, "", False),         # no node, no UID: no link session
                                  ("/dev/ttyUSB0", 5, "", True), ("/dev/ttyUSB0", None, "00" * 12, True)):
        connect_target(Target(spec, node, uid, "admin.pem", "device.pem"))
        assert calls[-1][4:6] == (("admin.pem", "device.pem") if keys else (None, None)), spec


def test_a_saved_session_of_another_version_still_loads(qsettings):
    qsettings.setValue("session/rows", json.dumps([
        {"spec": "/dev/ttyUSB0", "node": 5, "uid": "", "protocol": "smp", "image": "a.bin", "old_field": 1},
        {"spec": "/dev/ttyUSB1"}]))
    rows = Settings(qsettings).session().rows
    assert [(r.spec, r.node, r.protocol) for r in rows] == [("/dev/ttyUSB0", 5, "smp"), ("/dev/ttyUSB1", None, "smp")]
    qsettings.setValue("session/rows", "not json")
    assert Settings(qsettings).session().rows == []


def test_self_test_imports_what_the_library_loads_late():
    for m in ("umcub.smp", "cryptography.hazmat.primitives.ciphers", "cryptography.hazmat.primitives.serialization",
              "cryptography.hazmat.primitives.hashes"):
        assert m in selftest.LAZY_MODULES


def record(started, code="", params="", text=""):
    return Record(started, started + 1, "", None, "", 5, "/dev/ttyUSB0", "a.bin", "1.0.0", "", "error", None,
                  code, text, "1.2.1", params)


def test_history_pages_and_keeps_error_params(tmp_path):
    h = History(tmp_path / "h.sqlite")
    for k in range(5):
        h.add(record(float(k), "flash.invalid", json.dumps({}), "image rejected"))
    assert [r.started for r in h.records(limit=2)] == [4.0, 3.0]
    assert len(h.records()) == 5


def test_history_error_in_the_current_language(tmp_path):
    e = umcub.UmcubError(code="link.no_hello")
    r = record(1.0, e.code, json.dumps(e.params), "old text in another language")
    assert i18n.record_error(r) == i18n.message(e)
    plain = record(2.0, "error", "", "OSError: gone")         # not a library error: the stored text
    assert i18n.record_error(plain) == "OSError: gone"


def test_an_old_history_database_gets_the_new_column(tmp_path):
    import sqlite3
    path = tmp_path / "h.sqlite"
    db = sqlite3.connect(str(path))
    cols = [f for f in Record.__dataclass_fields__ if f != "error_params"]
    db.execute(f"CREATE TABLE flash ({', '.join(cols)})")
    db.execute(f"INSERT INTO flash VALUES ({', '.join('?' * len(cols))})",
               (1.0, 2.0, "", None, "", 5, "x", "a.bin", "1.0.0", "", "error", None, "error", "old", "1.1.0"))
    db.commit()
    db.close()
    h = History(path)
    assert [r.error_text for r in h.records()] == ["old"]


def test_discovered_devices_matched_to_rows():
    from umcub_gui.app.batch import Row
    rows = [Row("/dev/ttyUSB0", 5, "", "smp", "a.bin"), Row("/dev/ttyUSB0", None, "aa" * 12, "smp", ""),
            Row("/dev/ttyUSB1", 7, "", "smp", "")]
    devices = [{"addr": 5, "uid": "11" * 12, "board_type": 1, "version": "1.1.0", "link": 1},
               {"addr": 0, "uid": "aa" * 12, "board_type": 1, "version": "1.1.0", "link": 1},
               {"addr": 9, "uid": "bb" * 12, "board_type": 2, "version": "1.1.0", "link": 1}]
    found, missing = match_discovered("/dev/ttyUSB0", rows, devices)
    assert [(f.index, f.node, f.uid) for f in found] == [(0, 5, "11" * 12), (1, None, "aa" * 12), (None, 9, "bb" * 12)]
    assert missing == []
    found, missing = match_discovered("/dev/ttyUSB1", rows, [{"addr": 3, "protocol": "lite"}])    # CAN answer
    assert [(f.index, f.node, f.protocol) for f in found] == [(None, 3, "lite")] and missing == [2]
    secure = {"protocol": "link", "addr": 4, "uid": "cc" * 12, "board_type": 1, "version": "1.1.0", "link": 2}
    found, _ = match_discovered("can:x", rows, [secure])       # a SECURE CAN node: SMP in its session
    assert [(f.node, f.uid, f.protocol) for f in found] == [(4, "cc" * 12, "smp")]


def test_image_check(signed_image):
    img, err = image_check(str(signed_image), None)
    assert img is not None and err is None
    img, err = image_check(str(signed_image), (img.board_type or 0) + 1)
    assert img is not None and err is not None and err.code.startswith("image.")
    img, err = image_check("/nonexistent.bin", None)
    assert img is None and err is not None


def test_a_second_row_of_a_connected_device_does_not_leak_its_connection(fake_umcub):
    from umcub_gui.app.connections import Connections
    calls, _ = fake_umcub
    c = Connections()
    t = Target("can:virtual:x", 5, "", "", "")
    first = c.open(t, "smp")
    assert c.open(t, "smp") is first                      # the open device, not a second connection
    assert sum(1 for k in calls if k[0] == "connect") == 1
