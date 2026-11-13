"""Exchange log (developer role): every payload of every connection the app opens, from worker threads to the window
in batches; kept for Save, bounded."""
import threading
import time

import umcub
from umcub import link

from umcub_gui.app.connections import Connections
from umcub_gui.app.exchange import ExchangeLog, line
from umcub_gui.app.jobs import DiscoverJob, Target


def hello_event(node=5, conn="/dev/ttyUSB0"):
    return umcub.TapEvent(12.5, "tx", umcub.KIND_LINK, link.make_frame(link.T_HELLO, 0, node, 1, b""), conn)


def test_events_from_threads_come_in_batches():
    log = ExchangeLog()
    got = []
    log.batch.connect(got.extend)
    threads = [threading.Thread(target=lambda: [log(hello_event()) for _ in range(50)]) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    log.flush()                                     # the window's timer calls it
    assert len(got) == 200 and len(log.events()) == 200
    log.flush()
    assert len(got) == 200                          # nothing twice


def test_kept_events_are_bounded():
    log = ExchangeLog(keep=10)
    for _ in range(25):
        log(hello_event())
    assert len(log.events()) == 10
    log.clear()
    assert log.events() == []


def test_line_is_described():
    text = line(hello_event(), umcub.describe(hello_event()))
    assert "->" in text and "/dev/ttyUSB0" in text and "link" in text and "node 5" in text and "HELLO" in text
    assert line(hello_event(), umcub.describe(hello_event()), full=True).endswith(hello_event().payload.hex())


def test_connections_and_discover_are_tapped(qtbot, fake_umcub):
    log = ExchangeLog()
    c = Connections(tap=log)
    c.open(Target("/dev/ttyUSB0", 5, "", "", ""), "smp")                    # shared port: tapped when opened
    c.open(Target("can:socketcan:can0", 1, "", "", ""), "smp")              # own connection
    c.open(Target("192.168.1.50", None, "", "", ""), "smp")
    DiscoverJob("/dev/ttyUSB1", c).execute()
    assert sorted(e.connection for e, _ in log.events()) == ["/dev/ttyUSB0", "/dev/ttyUSB1", "192.168.1.50:1337",
                                                          "socketcan:can0"]
    # the node of each event's connection: on CAN the IDs select it, an SMP packet does not say it
    assert sorted(n for _, n in log.events() if n is not None) == [1]
    # the connection name of each device string, for the "selected device only" filter
    assert c.names == {"/dev/ttyUSB0": "/dev/ttyUSB0", "/dev/ttyUSB1": "/dev/ttyUSB1",
                       "can:socketcan:can0": "socketcan:can0", "192.168.1.50": "192.168.1.50:1337"}


def test_line_shows_the_event_time():
    ev = hello_event()
    ev.time = time.monotonic() - 3600                       # an hour ago (TapEvent.time is time.monotonic())
    then = time.time() - 3600                               # taken after ev.time: the event's minute or the one before
    text = line(ev, umcub.describe(ev))
    assert any(text.startswith(time.strftime("%H:%M", time.localtime(then + d))) for d in (0, -60))
