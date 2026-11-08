"""History: one row per flash job in SQLite, newest first, kept across restarts."""
from umcub_gui.app.history import History, Record


def record(**kw):
    base = dict(started=1000.0, finished=1012.5, uid="00" * 12, board_type=0x46103001, board="0x46103001 (Blue Pill)",
                node=5, adapter="/dev/ttyUSB1", image_name="app.signed.bin", image_version="1.2.3",
                image_hash="ab" * 32, result="ok", checked="verify", error_code="", error_text="",
                app_version="0.0.1")
    base.update(kw)
    return Record(**base)


def test_add_and_list(tmp_path):
    h = History(tmp_path / "history.sqlite")
    h.add(record())
    h.add(record(started=2000.0, result="error", checked=None, error_code="flash.invalid", error_text="invalid"))
    rows = h.records()
    assert [r.started for r in rows] == [2000.0, 1000.0]
    assert rows[0].error_code == "flash.invalid" and rows[0].checked is None
    assert rows[1] == record()


def test_kept_across_restarts(tmp_path):
    History(tmp_path / "h.sqlite").add(record(node=None, uid=""))
    rows = History(tmp_path / "h.sqlite").records()
    assert len(rows) == 1 and rows[0].node is None


def test_creates_the_folder(tmp_path):
    h = History(tmp_path / "new" / "dir" / "h.sqlite")
    h.add(record())
    assert len(h.records()) == 1
