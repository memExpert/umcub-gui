"""Several devices in one run: the rows that share a medium (umcub.exclusive_key: one serial port, a half-duplex
bus) take turns, the others run in parallel; a failed device does not stop the rest."""
import threading
from dataclasses import dataclass, replace

import umcub
from PySide6.QtCore import QObject, Signal

from .jobs import FlashJob, Result, Target


@dataclass
class Row:
    """One device of the table: where it is, how to talk to it and its image."""
    spec: str
    node: int | None
    uid: str
    protocol: str               # "smp" | "lite"
    image: str
    checked: bool = False       # the user ticks what to flash


class BatchSignals(QObject):
    row_progress = Signal(int, int, int)    # row, done, total
    row_finished = Signal(int, object)      # row, Result
    finished = Signal(object)               # [Result] in row order


class BatchJob:
    def __init__(self, rows, admin_key, device_key, options, history):
        self.rows, self.admin_key, self.device_key = rows, admin_key, device_key
        self.options, self.history = options, history
        self.signals = BatchSignals()
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def start(self):
        groups = {}
        for i, r in enumerate(self.rows):
            groups.setdefault(umcub.exclusive_key(r.spec) or ("parallel", i), []).append(i)
        results = [None] * len(self.rows)
        threads = [threading.Thread(target=self._group, args=(g, results), daemon=True) for g in groups.values()]

        def wait():
            for t in threads:
                t.join()
            self.signals.finished.emit(results)
        for t in threads:
            t.start()
        threading.Thread(target=wait, daemon=True).start()

    def _group(self, indexes, results):
        for i in indexes:
            r = self.rows[i]
            if self.cancel_event.is_set():          # not started: nothing to record
                results[i] = Result(False, cancelled=True, error_code="cancelled.upload", error_text="cancelled")
                self.signals.row_finished.emit(i, results[i])
                continue
            job = FlashJob(Target(r.spec, r.node, r.uid, self.admin_key, self.device_key), r.image,
                           replace(self.options, protocol=r.protocol), self.history)
            job.cancel_event = self.cancel_event
            job.signals.progress.connect(lambda done, total, i=i: self.signals.row_progress.emit(i, done, total))
            res = job.execute()
            results[i] = res
            self.signals.row_finished.emit(i, res)
