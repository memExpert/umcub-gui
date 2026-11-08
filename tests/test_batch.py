"""Several devices in one run: the rows of one serial port take turns, CAN / UDP rows and other ports run in
parallel; a failed device does not stop the others; cancel stops what has not finished."""
from umcub_gui.app.batch import BatchJob, Row
from umcub_gui.app.history import History
from umcub_gui.app.jobs import FlashOptions


def rows(image, *specs_nodes):
    return [Row(spec=s, node=n, uid="", protocol="smp", image=str(image)) for s, n in specs_nodes]


def run(qtbot, job):
    with qtbot.waitSignal(job.signals.finished, timeout=10000) as blocker:
        job.start()
    return blocker.args[0]


def test_serial_takes_turns_can_in_parallel(qtbot, fake_umcub, signed_image, tmp_path):
    calls, answers = fake_umcub
    answers["delay"] = 0.3
    rs = rows(signed_image, ("/dev/ttyUSB1", 5), ("/dev/ttyUSB1", 6), ("can:virtual:x", 1), ("can:virtual:x", 2),
              ("/dev/ttyUSB0", 7))
    job = BatchJob(rs, "", "", FlashOptions(), History(tmp_path / "h.sqlite"))
    done = []
    job.signals.row_finished.connect(lambda i, res: done.append((i, res.ok)))
    results = run(qtbot, job)
    assert [r.ok for r in results] == [True] * 5 and sorted(done) == [(i, True) for i in range(5)]
    assert answers["most_at_once"] == {"/dev/ttyUSB1": 1, "can:virtual:x": 2, "/dev/ttyUSB0": 1}
    connects = [c for c in calls if c[0] == "connect"]
    assert sorted((c[1], c[2]) for c in connects) == sorted((r.spec, r.node) for r in rs)


def test_failure_does_not_stop_the_others(qtbot, fake_umcub, signed_image, tmp_path):
    _, answers = fake_umcub
    answers["fail_nodes"] = {6}
    history = History(tmp_path / "h.sqlite")
    results = run(qtbot, BatchJob(rows(signed_image, ("/dev/ttyUSB1", 5), ("/dev/ttyUSB1", 6), ("/dev/ttyUSB1", 7)),
                                  "", "", FlashOptions(), history))
    assert [r.ok for r in results] == [True, False, True] and results[1].error_code == "flash.invalid"
    assert sorted(r.result for r in history.records()) == ["error", "ok", "ok"]


def test_row_progress_and_keys(qtbot, fake_umcub, signed_image, tmp_path):
    calls, _ = fake_umcub
    job = BatchJob([Row(spec="/dev/ttyUSB1", node=None, uid="ab" * 12, protocol="lite", image=str(signed_image))],
                   "/k/a.pem", "/k/d.pem", FlashOptions(slot="secondary", mark="test", reset=True),
                   History(tmp_path / "h.sqlite"))
    progress = []
    job.signals.row_progress.connect(lambda i, d, t: progress.append((i, d, t)))
    assert run(qtbot, job)[0].ok
    assert calls[0] == ("connect", "/dev/ttyUSB1", None, "ab" * 12, "/k/a.pem", "/k/d.pem")
    assert calls[1] == ("flash", "1.2.3", "lite", "secondary", True, False, True)
    assert progress[-1][0] == 0 and progress[-1][1] == progress[-1][2]


def test_cancel(qtbot, fake_umcub, signed_image, tmp_path):
    calls, answers = fake_umcub
    answers["delay"] = 0.4
    job = BatchJob(rows(signed_image, ("/dev/ttyUSB1", 5), ("/dev/ttyUSB1", 6)), "", "", FlashOptions(),
                   History(tmp_path / "h.sqlite"))
    job.signals.row_progress.connect(lambda i, d, t: job.cancel())      # during the first upload
    results = run(qtbot, job)
    assert results[1].cancelled and not results[1].ok
    assert [c[2] for c in calls if c[0] == "connect"] == [5]           # the second was never opened
