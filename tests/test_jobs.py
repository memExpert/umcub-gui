"""Device jobs in a worker thread: connect / discover / adapters / flash, results and history through signals."""
import umcub

from umcub_gui.app.history import History
from umcub_gui.app.jobs import AdaptersJob, ConnectJob, DiscoverJob, FlashJob, FlashOptions, Target

T = Target(spec="/dev/ttyUSB1", node=5, uid="", admin_key="", device_key="")


def run(qtbot, job):
    with qtbot.waitSignal(job.signals.finished, timeout=5000) as blocker:
        job.start()
    return blocker.args[0]


def test_flash_ok(qtbot, fake_umcub, signed_image, tmp_path):
    calls, _ = fake_umcub
    umcub.load_board_names()
    names = tmp_path / "names.json"
    names.write_text('{"0x46103001": "Blue Pill"}')
    umcub.load_board_names(names)
    history = History(tmp_path / "h.sqlite")
    job = FlashJob(T, str(signed_image), FlashOptions(protocol="smp", slot="primary", mark="", reset=True), history)
    progress = []
    job.signals.progress.connect(lambda done, total: progress.append((done, total)))
    res = run(qtbot, job)
    umcub.load_board_names()
    assert res.ok and not res.cancelled and res.value == "verify"
    assert calls[0] == ("connect", "/dev/ttyUSB1", 5, None, None, None)
    assert calls[1] == ("flash", "1.2.3", "smp", None, False, False, True)
    assert progress[-1][0] == progress[-1][1]
    row = history.records()[0]
    assert (row.result, row.checked, row.node, row.uid, row.board_type, row.board, row.image_version) == \
        ("ok", "verify", 5, "00" * 12, 0x46103001, "0x46103001 (Blue Pill)", "1.2.3")
    assert row.image_name == "app.signed.bin" and len(row.image_hash) == 64 and row.finished >= row.started


def test_flash_secondary_test_boot_keys(qtbot, fake_umcub, signed_image, tmp_path):
    calls, _ = fake_umcub
    t = Target(spec="/dev/ttyUSB1", node=None, uid="ab" * 12, admin_key="/k/a.pem", device_key="/k/d.pem")
    res = run(qtbot, FlashJob(t, str(signed_image), FlashOptions(protocol="lite", slot="secondary", mark="test"),
                              History(tmp_path / "h.sqlite")))
    assert res.ok
    assert calls[0] == ("connect", "/dev/ttyUSB1", None, "ab" * 12, "/k/a.pem", "/k/d.pem")
    assert calls[1] == ("flash", "1.2.3", "lite", "secondary", True, False, False)


def test_flash_device_error(qtbot, fake_umcub, signed_image, tmp_path):
    _, answers = fake_umcub
    answers["flash"] = umcub.UmcubError(code="flash.invalid")
    history = History(tmp_path / "h.sqlite")
    res = run(qtbot, FlashJob(T, str(signed_image), FlashOptions(), history))
    assert not res.ok and res.error_code == "flash.invalid" and "invalid" in res.error_text
    row = history.records()[0]
    assert (row.result, row.error_code, row.checked) == ("error", "flash.invalid", None)


def test_flash_no_answer(qtbot, fake_umcub, signed_image, tmp_path):
    _, answers = fake_umcub
    answers["connect"] = umcub.LinkError(code="link.no_hello")
    history = History(tmp_path / "h.sqlite")
    res = run(qtbot, FlashJob(T, str(signed_image), FlashOptions(), history))
    assert not res.ok and res.error_code == "link.no_hello"
    row = history.records()[0]
    assert row.result == "error" and row.uid == "" and row.board_type is None


def test_flash_not_an_image(qtbot, fake_umcub, tmp_path):
    calls, _ = fake_umcub
    bad = tmp_path / "x.bin"
    bad.write_bytes(b"\0" * 64)
    res = run(qtbot, FlashJob(T, str(bad), FlashOptions(), History(tmp_path / "h.sqlite")))
    assert not res.ok and res.error_code == "image.not_signed" and not calls


def test_unexpected_error_still_finishes(qtbot, fake_umcub, signed_image, tmp_path):
    _, answers = fake_umcub
    answers["flash"] = OSError(5, "Input/output error")      # e.g. a USB adapter unplugged during the upload
    history = History(tmp_path / "h.sqlite")
    res = run(qtbot, FlashJob(T, str(signed_image), FlashOptions(), history))
    assert not res.ok and res.error_code == "error" and "Input/output error" in res.error_text
    assert history.records()[0].result == "error"


def test_flash_cancel(qtbot, fake_umcub, signed_image, tmp_path):
    history = History(tmp_path / "h.sqlite")
    job = FlashJob(T, str(signed_image), FlashOptions(), history)
    job.cancel()
    res = run(qtbot, job)
    assert res.cancelled and not res.ok and history.records()[0].result == "cancelled"


def test_discover(qtbot, fake_umcub):
    calls, answers = fake_umcub
    answers["devices"] = [{"addr": 5, "uid": "00" * 12, "board_type": 0x46103001}]
    res = run(qtbot, DiscoverJob("/dev/ttyUSB1"))
    assert res.ok and res.value == answers["devices"] and calls == [("discover", "/dev/ttyUSB1")]


def test_connect_identity(qtbot, fake_umcub):
    _, answers = fake_umcub
    res = run(qtbot, ConnectJob(T))
    assert res.ok and res.value == answers["identity"]


def test_adapters(qtbot, fake_umcub):
    _, answers = fake_umcub
    answers["adapters"] = [umcub.Adapter("/dev/ttyUSB0", "serial", "ttyUSB0", "FT232R", 0x403, 0x6001, "A1", "1-2")]
    res = run(qtbot, AdaptersJob())
    assert res.ok and res.value == answers["adapters"]
