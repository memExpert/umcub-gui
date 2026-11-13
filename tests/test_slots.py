"""Slot jobs (service role): the slot list, verify / hash vs file / test boot / permanent on several devices, read a
slot back to a file. Over the open connection when connected, else their own."""
import hashlib

import umcub

from umcub_gui.app.connections import Connections
from umcub_gui.app.jobs import Target
from umcub_gui.app.slots import ReadJob, SlotActionJob, SlotsJob


def t(node):
    return Target("/dev/ttyUSB0", node, "", "", "")


def run(qtbot, job):
    with qtbot.waitSignal(job.signals.finished, timeout=5000) as blocker:
        job.start()
    return blocker.args[0]


def test_slot_list(qtbot, fake_umcub):
    calls, answers = fake_umcub
    res = run(qtbot, SlotsJob(t(5), Connections()))
    assert res.ok and res.value == answers["images"] and ("images", 5) in calls


def test_verify_several(qtbot, fake_umcub):
    calls, answers = fake_umcub
    answers["verify"] = {6: False, 7: umcub.DeviceError(rc=8, code="smp.device", reason="not supported")}
    res = run(qtbot, SlotActionJob([(0, t(5), ""), (1, t(6), ""), (2, t(7), "")], "verify", 0, 1, Connections()))
    assert res.value[:2] == [(0, True, "valid"), (1, False, "invalid")]
    assert res.value[2][:2] == (2, False)       # a library error: its text
    assert "not supported" in res.value[2][2] and ("verify", 5, 0, 1) in calls


def test_hash_vs_file(qtbot, fake_umcub, signed_image):
    _, answers = fake_umcub
    data = signed_image.read_bytes()
    answers["hash"] = {5: (hashlib.sha256(data).digest(), len(data)), 6: (b"\0" * 32, len(data))}
    res = run(qtbot, SlotActionJob([(0, t(5), str(signed_image)), (1, t(6), str(signed_image)), (2, t(7), "")],
                                   "hash", 0, 1, Connections()))
    assert [(ok, text) for _, ok, text in res.value] == [(True, "matches"), (False, "differs"), (False, "no_image")]


def test_marks_use_the_secondary_hash(qtbot, fake_umcub):
    calls, answers = fake_umcub
    res = run(qtbot, SlotActionJob([(0, t(5), "")], "test", 0, 1, Connections()))
    assert res.value == [(0, True, "marked_test")] and ("mark", 5, b"\x22" * 32, False) in calls
    res = run(qtbot, SlotActionJob([(0, t(5), "")], "permanent", 0, 1, Connections()))
    assert res.value == [(0, True, "marked_permanent")] and ("mark", 5, b"\x22" * 32, True) in calls
    answers["images"] = answers["images"][:1]                      # nothing in the secondary slot
    res = run(qtbot, SlotActionJob([(0, t(5), "")], "test", 0, 1, Connections()))
    assert res.value == [(0, False, "no_secondary")]


def test_read_to_file(qtbot, fake_umcub, tmp_path):
    _, answers = fake_umcub
    out = tmp_path / "slot.bin"
    job = ReadJob(t(5), 0, 0, str(out), Connections())
    progress = []
    job.signals.progress.connect(lambda d, n: progress.append((d, n)))
    res = run(qtbot, job)
    assert res.ok and out.read_bytes() == answers["read"] and progress[-1] == (300, 300)


def test_read_cancelled_writes_nothing(qtbot, fake_umcub, tmp_path):
    out = tmp_path / "slot.bin"
    job = ReadJob(t(5), 0, 0, str(out), Connections())
    job.cancel()
    res = run(qtbot, job)
    assert res.cancelled and not out.exists()


def test_slot_jobs_use_the_open_connection(qtbot, fake_umcub):
    calls, _ = fake_umcub
    c = Connections()
    c.open(t(5), "smp")
    calls.clear()
    run(qtbot, SlotsJob(t(5), c))
    run(qtbot, SlotActionJob([(0, t(5), "")], "verify", 0, 0, c))
    assert not [x for x in calls if x[0] in ("open", "connect", "close")]
