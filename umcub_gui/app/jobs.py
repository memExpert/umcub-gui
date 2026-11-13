"""Device jobs: each runs the blocking host library calls in its own thread and reports through Qt signals.

A job uses the connection Connect keeps open (Connections), or opens its own and closes it when done.
"""
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

import umcub
from PySide6.QtCore import QObject, Signal

from .. import __version__
from .history import Record


@dataclass
class Target:
    """Which device: the device string plus a link node / UID and the SECURE key files ("" = none)."""
    spec: str
    node: int | None
    uid: str
    admin_key: str
    device_key: str


@dataclass
class FlashOptions:
    protocol: str = "smp"       # "smp" | "lite"
    slot: str = "primary"       # "primary": SMP's image field (works on every build); "secondary"
    mark: str = ""              # "" | "test" | "permanent" (secondary slot)
    reset: bool = False


@dataclass
class Result:
    ok: bool
    value: object = None        # what the job returns: identity, devices, adapters, how the image was checked
    cancelled: bool = False
    error_code: str = ""        # UmcubError code, for translations
    error_text: str = ""        # English text, the fallback


class Signals(QObject):
    progress = Signal(int, int)         # done, total
    finished = Signal(object)           # Result


class Job:
    """Base: run() in a thread; its return value or UmcubError becomes the Result."""

    def __init__(self):
        self.signals = Signals()

    def start(self):
        threading.Thread(target=lambda: self.signals.finished.emit(self.execute()), daemon=True).start()

    def execute(self):
        """run() and done() in the calling thread; the Result."""
        try:
            res = Result(True, self.run())
        except umcub.Cancelled as e:
            res = Result(False, cancelled=True, error_code=e.code, error_text=str(e))
        except umcub.UmcubError as e:
            res = Result(False, error_code=e.code, error_text=str(e))
        except Exception as e:          # e.g. OSError of an adapter unplugged mid-transfer: still a finished job
            res = Result(False, error_code="error", error_text=f"{type(e).__name__}: {e}")
        self.done(res)
        return res

    def run(self):
        raise NotImplementedError

    def done(self, res):
        """After run(), in the worker thread (e.g. the history row)."""


def connect_target(t, conn=None):
    """umcub.connect() of a target, over `conn` (an open port) or its own connection. A node address selects the
    device; the UID only one without an address (the library prefers the UID)."""
    return umcub.connect(conn or t.spec, node=t.node, uid=(t.uid or None) if t.node is None else None,
                         admin_key=t.admin_key or None, device_key=t.device_key or None)


@contextmanager
def device_for(t, connections):
    """The target's device: the one Connect keeps open (under its port's lock, left open), else its own connection."""
    opened = connections.device(t)
    if opened:
        with opened[1]:
            yield opened[0]
    else:
        with connect_target(t) as dev:
            yield dev


class AdaptersJob(Job):
    def run(self):
        return umcub.adapters()


class DiscoverJob(Job):
    """Over the open port of `spec` when the window is connected to it, else on its own connection."""

    def __init__(self, spec, connections):
        super().__init__()
        self.spec, self.connections = spec, connections

    def run(self):
        port = self.connections.port(self.spec)
        if not port:
            return umcub.discover(self.spec)
        with port[1]:
            return umcub.discover(port[0])


class OpenJob(Job):
    """Connect: opens and keeps the devices of `items` [(row, Target, protocol)]; returns [(row, identity or None,
    error text or "")]: one device that does not answer does not stop the others."""

    def __init__(self, items, connections):
        super().__init__()
        self.items, self.connections = items, connections

    def run(self):
        out = []
        for row, t, protocol in self.items:
            try:
                out.append((row, self.connections.open(t, protocol).identity, ""))
            except umcub.UmcubError as e:
                out.append((row, None, str(e)))
        return out


class KeepaliveJob(Job):
    """Pings the open devices; returns the targets that no longer answer (closed)."""

    def __init__(self, connections):
        super().__init__()
        self.connections = connections

    def run(self):
        return self.connections.ping_all()


class CancellableJob(Job):
    """A job that stops at its next step once cancel() was called (cancel_event goes to the library)."""

    def __init__(self):
        super().__init__()
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()


class FlashJob(CancellableJob):
    """umcub.flash() on one device; writes a history row."""

    def __init__(self, target, image_path, options, history, connections):
        super().__init__()
        self.target, self.image_path, self.options, self.history = target, image_path, options, history
        self.connections = connections
        self.img = self.identity = None

    def run(self):
        self.started = time.time()
        self.img = umcub.Image.load(self.image_path)
        with device_for(self.target, self.connections) as dev:
            return self._flash(dev)

    def _flash(self, dev):
        o = self.options
        self.identity = dev.identity
        return umcub.flash(dev, self.img, o.protocol, slot=None if o.slot == "primary" else o.slot,
                           test=o.mark == "test", permanent=o.mark == "permanent", reset=o.reset,
                           progress=self.signals.progress.emit, cancel=self.cancel_event)

    def done(self, res):
        if self.img is None:
            return                          # not an image: nothing was sent
        i = self.identity or {}
        bt = i.get("board_type")
        self.history.add(Record(
            started=self.started, finished=time.time(), uid=i.get("uid", ""), board_type=bt,
            board=umcub.board_label(bt) if bt is not None else "", node=self.target.node, adapter=self.target.spec,
            image_name=os.path.basename(self.image_path), image_version=self.img.version,
            image_hash=self.img.hash.hex(), result="ok" if res.ok else "cancelled" if res.cancelled else "error",
            checked=res.value if res.ok else None, error_code=res.error_code, error_text=res.error_text,
            app_version=__version__))
