"""Open connections kept by the window: one port per serial adapter shared by its nodes, CAN / UDP per node; pings
keep them alive and find the lost ones."""
import threading

import umcub

from umcub_gui.app.connections import Connections
from umcub_gui.app.jobs import Target


def t(spec, node, uid=""):
    return Target(spec, node, uid, "/k/a.pem", "/k/d.pem")


def test_serial_nodes_share_one_port(fake_umcub):
    calls, _ = fake_umcub
    c = Connections()
    a, b = c.open(t("/dev/ttyUSB0", 5), "smp"), c.open(t("/dev/ttyUSB0", 6), "smp")
    assert calls == [("open", "/dev/ttyUSB0"),
                     ("connect", "/dev/ttyUSB0", 5, None, "/k/a.pem", "/k/d.pem", "shared"),
                     ("connect", "/dev/ttyUSB0", 6, None, "/k/a.pem", "/k/d.pem", "shared")]
    assert c.device(t("/dev/ttyUSB0", 5))[0] is a and c.device(t("/dev/ttyUSB0", 6))[0] is b
    assert c.device(t("/dev/ttyUSB0", 5))[1] is c.device(t("/dev/ttyUSB0", 6))[1]     # one lock: one at a time
    assert c.port("/dev/ttyUSB0") is not None and c.port("/dev/ttyUSB1") is None
    calls.clear()
    c.close_all()
    assert sorted(calls) == [("close", "/dev/ttyUSB0", 5), ("close", "/dev/ttyUSB0", 6), ("close conn", "/dev/ttyUSB0")]
    assert c.device(t("/dev/ttyUSB0", 5)) is None and not c


def test_can_nodes_own_connections(fake_umcub):
    calls, _ = fake_umcub
    c = Connections()
    c.open(t("can:socketcan:can0", 1), "smp")
    c.open(t("can:socketcan:can0", 2), "smp")
    assert [x[0] for x in calls] == ["connect", "connect"] and "shared" not in calls[0]
    assert c.device(t("can:socketcan:can0", 1))[1] is not c.device(t("can:socketcan:can0", 2))[1]
    assert c.port("can:socketcan:can0") is None          # no port to discover over: CAN discover probes itself


def test_ping_finds_the_lost(fake_umcub):
    calls, answers = fake_umcub
    answers["lost_nodes"] = {6}
    c = Connections()
    c.open(t("/dev/ttyUSB0", 5), "smp")
    c.open(t("/dev/ttyUSB0", 6), "lite")
    lost = c.ping_all()
    assert lost == [t("/dev/ttyUSB0", 6)]
    assert ("ping", "/dev/ttyUSB0", 5, "smp") in calls and ("ping", "/dev/ttyUSB0", 6, "lite") in calls
    assert c.device(t("/dev/ttyUSB0", 6)) is None and c.device(t("/dev/ttyUSB0", 5)) is not None
    assert ("close", "/dev/ttyUSB0", 6) in calls and ("close conn", "/dev/ttyUSB0") not in calls


def test_ping_skips_a_busy_port(fake_umcub):
    calls, _ = fake_umcub
    c = Connections()
    c.open(t("/dev/ttyUSB0", 5), "smp")
    lock = c.device(t("/dev/ttyUSB0", 5))[1]
    lock.acquire()
    try:
        done = []
        th = threading.Thread(target=lambda: done.append(c.ping_all()))
        th.start()
        th.join(2)
    finally:
        lock.release()
    assert done == [[]] and not [x for x in calls if x[0] == "ping"]      # a job on that port keeps it alive anyway


def test_open_failure_leaves_nothing_open(fake_umcub):
    calls, answers = fake_umcub
    answers["connect"] = umcub.LinkError(code="link.no_hello")
    c = Connections()
    try:
        c.open(t("/dev/ttyUSB0", 9), "smp")
        raise AssertionError("no error")
    except umcub.LinkError:
        pass
    assert ("close conn", "/dev/ttyUSB0") in calls and not c


def test_node_wins_over_uid(fake_umcub):
    """A node address selects the device; the UID only one without an address (the library prefers the UID)."""
    calls, _ = fake_umcub
    c = Connections()
    c.open(t("/dev/ttyUSB1", 5, "00" * 12), "smp")
    c.open(t("/dev/ttyUSB1", None, "ab" * 12), "smp")
    assert [x[2:4] for x in calls if x[0] == "connect"] == [(5, None), (None, "ab" * 12)]
