"""Slot jobs (service role): the image slots of a device, verify / hash against the file / test boot / permanent on
one or several devices, and reading a slot back to a file. SMP devices only (lite has no slot requests)."""
import umcub
from umcub.smp import file_hash

from . import i18n
from .jobs import CancellableJob, Job, device_for


class SlotsJob(Job):
    """The image slots of one device: umcub.Smp.images()."""

    def __init__(self, target, connections):
        super().__init__()
        self.target, self.connections = target, connections

    def run(self):
        with device_for(self.target, self.connections) as dev, umcub.Smp(dev) as smp:
            return smp.images()


class SlotActionJob(Job):
    """One action on the slot (image, slot) of each of `items` [(row, Target, image file)]; returns [(row, ok, code)]
    with ok True / False / None (cannot tell) and a result code the window words (or a library error's text). A device
    that fails does not stop the others."""

    def __init__(self, items, action, image, slot, connections):
        super().__init__()
        self.items, self.action, self.image, self.slot, self.connections = items, action, image, slot, connections

    def run(self):
        out = []
        for row, t, path in self.items:
            try:
                with device_for(t, self.connections) as dev, umcub.Smp(dev) as smp:
                    if self.action == "verify":
                        out.append((row, *self._verify(smp)))
                    elif self.action == "hash":
                        out.append((row, *self._hash(smp, path)))
                    else:
                        out.append((row, *self._mark(smp, self.action == "permanent")))
            except umcub.UmcubError as e:
                out.append((row, False, i18n.message(e)))
        return out

    def _verify(self, smp):
        return (True, "valid") if smp.verify(self.image, self.slot) else (False, "invalid")

    def _hash(self, smp, path):
        if not path:
            return False, "no_image"
        img = umcub.Image.load(path)
        if img.encrypted and self.slot == 0:
            return None, "encrypted_primary"
        sha, _ = smp.hash(self.image, self.slot, 0, img.size)
        return (True, "matches") if sha == file_hash(img.data) else (False, "differs")

    def _mark(self, smp, permanent):
        secondary = [i for i in smp.images() if i["image"] == self.image and i["slot"] == 1 and i["hash"]]
        if not secondary:
            return False, "no_secondary"
        smp.mark(secondary[0]["hash"], permanent)
        return True, "marked_permanent" if permanent else "marked_test"


class ReadJob(CancellableJob):
    """Read the stored image of (image, slot) back into `path` (UMCUB_CFG_READBACK); progress, cancel."""

    def __init__(self, target, image, slot, path, connections):
        super().__init__()
        self.target, self.image, self.slot, self.path, self.connections = target, image, slot, path, connections

    def run(self):
        with device_for(self.target, self.connections) as dev, umcub.Smp(dev) as smp:
            data = smp.read(self.image, self.slot, progress=self.signals.progress.emit, cancel=self.cancel_event)
        with open(self.path, "wb") as f:
            f.write(data)
        return len(data)
