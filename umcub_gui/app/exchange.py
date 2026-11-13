"""Exchange log (developer role): the library's tap on every connection the app opens. Events arrive from worker
threads; the window's timer calls flush(), which hands them over in one batch (thousands while flashing)."""
import collections
import threading
import time

from PySide6.QtCore import QObject, Signal


def line(ev, d, full=False):
    """One log line of the event and its umcub.describe() `d`: time, direction, connection, kind, link node,
    summary, the bytes (cut unless `full`)."""
    node = f" node {d.node}" if d.node is not None else ""
    shown = ev.payload.hex() if full else ev.payload[:24].hex() + ("..." if len(ev.payload) > 24 else "")
    wall = time.time() - (time.monotonic() - ev.time)     # TapEvent.time is time.monotonic()
    return f"{time.strftime('%H:%M:%S', time.localtime(wall))}.{int(wall * 1000) % 1000:03d} " \
           f"{'->' if ev.direction == 'tx' else '<-'} {ev.connection} {d.kind}{node} {d.text}  {shown}"


class ExchangeLog(QObject):
    batch = Signal(list)        # [(TapEvent, node)] since the last flush

    def __init__(self, keep=20000):
        super().__init__()
        self._lock = threading.Lock()
        self._new = []
        self._kept = collections.deque(maxlen=keep)

    def __call__(self, ev, node=None):
        """The tap: any thread. `node`: the node a connection was opened for (CAN: its IDs), else None."""
        with self._lock:
            self._new.append((ev, node))
            self._kept.append((ev, node))

    def flush(self):
        with self._lock:
            new, self._new = self._new, []
        if new:
            self.batch.emit(new)

    def events(self):
        with self._lock:
            return list(self._kept)

    def clear(self):
        with self._lock:
            self._new.clear()
            self._kept.clear()
