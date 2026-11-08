"""Device jobs: each runs the blocking host library calls in its own thread and reports through Qt signals.

A job opens the connection, does its work and closes it again: the port is free between jobs.
"""
import os
import threading
import time
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
    log = Signal(str)
    finished = Signal(object)           # Result


class Job:
    """Base: run() in a thread; its return value or UmcubError becomes the Result."""

    def __init__(self):
        self.signals = Signals()

    def start(self):
        threading.Thread(target=self._main, daemon=True).start()

    def _main(self):
        try:
            res = Result(True, self.run())
        except umcub.Cancelled as e:
            res = Result(False, cancelled=True, error_code=e.code, error_text=str(e))
        except umcub.UmcubError as e:
            res = Result(False, error_code=e.code, error_text=str(e))
        except Exception as e:          # e.g. OSError of an adapter unplugged mid-transfer: still a finished job
            res = Result(False, error_code="error", error_text=f"{type(e).__name__}: {e}")
        self.done(res)
        self.signals.finished.emit(res)

    def run(self):
        raise NotImplementedError

    def done(self, res):
        """After run(), in the worker thread (e.g. the history row)."""

    def connect(self, t):
        return umcub.connect(t.spec, node=t.node, uid=t.uid or None, admin_key=t.admin_key or None,
                             device_key=t.device_key or None)


class AdaptersJob(Job):
    def run(self):
        return umcub.adapters()


class DiscoverJob(Job):
    def __init__(self, spec):
        super().__init__()
        self.spec = spec

    def run(self):
        return umcub.discover(self.spec)


class ConnectJob(Job):
    """Opens the device, returns its link identity (None for a device without one) and closes it."""

    def __init__(self, target):
        super().__init__()
        self.target = target

    def run(self):
        with self.connect(self.target) as dev:
            return dev.identity


class FlashJob(Job):
    """umcub.flash() on one device; writes a history row."""

    def __init__(self, target, image_path, options, history):
        super().__init__()
        self.target, self.image_path, self.options, self.history = target, image_path, options, history
        self.img = self.identity = None
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        self.started = time.time()
        self.img = umcub.Image.load(self.image_path)
        o = self.options
        with self.connect(self.target) as dev:
            self.identity = dev.identity
            self.signals.log.emit(f"connected: {self.target.spec}")
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
