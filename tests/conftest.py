import pytest
import umcub
from PySide6.QtCore import QSettings


@pytest.fixture
def qsettings(tmp_path):
    """Settings in a temporary INI file instead of the user's."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def fake_name(spec):
    """Connection.name as the library gives it: a serial port, "ip:port" for UDP, "interface:channel" for CAN."""
    if spec.startswith("can:"):
        return spec[4:]
    return f"{spec}:1337" if spec[0].isdigit() else spec


class FakeConn:
    """umcub.open_connection(): a port the program keeps open."""

    def __init__(self, spec, calls):
        self.spec, self.calls = spec, calls

    def close(self):
        self.calls.append(("close conn", self.spec))


class FakeDevice:
    def __init__(self, identity, spec, node, calls, answers):
        self.identity, self.spec, self.node, self.calls, self.answers = identity, spec, node, calls, answers

    def text(self, cmd):
        self.calls.append(("text", self.spec, self.node, cmd))
        return self.answers["text"]

    def ping(self, protocol):
        self.calls.append(("ping", self.spec, self.node, protocol))
        if self.node in self.answers["lost_nodes"]:
            raise umcub.NoAnswer(code="smp.no_answer")

    def close(self):
        self.calls.append(("close", self.spec, self.node))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def fake_umcub(monkeypatch):
    """The host library calls the app makes, recorded; tests set the answers. answers["delay"] makes each upload
    take that long; answers["most_at_once"] counts the uploads that ran together per device string;
    answers["fail_nodes"]: nodes whose upload fails (flash.invalid); answers["lost_nodes"]: nodes that no longer
    answer a ping."""
    import threading
    import time

    lock = threading.Lock()
    running = {}

    calls = []
    answers = {"identity": {"addr": 5, "uid": "00" * 12, "board_type": 0x46103001, "board_rev": 1, "link": 1,
                            "enc": False, "closed": False, "version": "1.0.0"},
               "flash": "verify", "devices": [], "adapters": [], "delay": 0.0, "most_at_once": {},
               "fail_nodes": set(), "lost_nodes": set(),
               # SMP slot requests: images() list, verify / hash answers per node, read data
               "images": [dict(image=0, slot=0, version="1.0.0", hash=b"\x11" * 32, active=True, confirmed=True,
                               pending=False, permanent=False, bootable=True),
                          dict(image=0, slot=1, version="1.0.1", hash=b"\x22" * 32, active=False, confirmed=False,
                               pending=False, permanent=False, bootable=True)],
               "verify": {}, "hash": {}, "read": b"\xab" * 300, "text": "umcub 0.1.0 board 0x46103001\r\n"}

    def tapped(tap, spec):
        """A connection with a tap shows one frame in it, as the library's tap would: a HELLO to node 5, on CAN an
        SMP echo (no node in it: the CAN IDs select the node)."""
        if tap and spec.startswith("can:"):
            tap(umcub.TapEvent(1.0, "tx", umcub.KIND_SMP, bytes([2, 0, 0, 0, 0, 0, 1, 0]), fake_name(spec)))
        elif tap:
            from umcub import link
            tap(umcub.TapEvent(1.0, "tx", umcub.KIND_LINK, link.make_frame(link.T_HELLO, 0, 5, 1, b""),
                               fake_name(spec)))

    def open_connection(spec, node=0, tap=None):
        calls.append(("open", spec))
        tapped(tap, spec)
        return FakeConn(spec, calls)

    def connect(spec, node=None, uid=None, admin_key=None, device_key=None, timeout=3.0, tap=None):
        shared = isinstance(spec, FakeConn)         # a port the program keeps open
        spec = spec.spec if shared else spec
        calls.append(("connect", spec, node, uid, admin_key, device_key) + (("shared",) if shared else ()))
        if not shared:
            tapped(tap, spec)
        if isinstance(answers.get("connect"), Exception):
            raise answers["connect"]
        return FakeDevice(answers["identity"], spec, node, calls, answers)

    def flash(dev, img, protocol, slot, test, permanent, reset, progress, cancel):
        calls.append(("flash", img.version, protocol, slot, test, permanent, reset))
        with lock:
            running[dev.spec] = running.get(dev.spec, 0) + 1
            answers["most_at_once"][dev.spec] = max(answers["most_at_once"].get(dev.spec, 0), running[dev.spec])
        try:
            for done in (img.size // 2, img.size):
                if cancel.is_set():
                    raise umcub.Cancelled(code="cancelled.upload")
                time.sleep(answers["delay"] / 2)
                progress(done, img.size)
        finally:
            with lock:
                running[dev.spec] -= 1
        if dev.node in answers["fail_nodes"]:
            raise umcub.UmcubError(code="flash.invalid")
        if isinstance(answers["flash"], Exception):
            raise answers["flash"]
        return answers["flash"]

    def discover(spec, tap=None, **kw):
        if not isinstance(spec, FakeConn):
            tapped(tap, spec)
        calls.append(("discover", spec.spec if isinstance(spec, FakeConn) else spec)
                     + (("shared",) if isinstance(spec, FakeConn) else ()))
        return answers["devices"]

    def adapters(**kw):
        calls.append(("adapters",))
        return answers["adapters"]

    class FakeSmp:
        """umcub.Smp on a FakeDevice: answers from `answers`, an Exception answer is raised."""

        def __init__(self, dev):
            self.node = dev.node

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def _answer(self, what, default):
            a = answers[what].get(self.node, default)
            if isinstance(a, Exception):
                raise a
            return a

        def images(self):
            calls.append(("images", self.node))
            return answers["images"]

        def verify(self, image, slot):
            calls.append(("verify", self.node, image, slot))
            return self._answer("verify", True)

        def hash(self, image, slot, off=0, length=0):
            calls.append(("hash", self.node, image, slot))
            return self._answer("hash", (b"\x11" * 32, 300))

        def mark(self, image_hash, permanent=False):
            calls.append(("mark", self.node, image_hash, permanent))

        def read(self, image, slot, off=0, length=0, progress=None, cancel=None):
            calls.append(("read", self.node, image, slot))
            data = answers["read"]
            for done in range(128, len(data) + 128, 128):
                if cancel is not None and cancel.is_set():
                    raise umcub.Cancelled(code="cancelled.read")
                progress(min(done, len(data)), len(data))
            return data

    monkeypatch.setattr(umcub, "open_connection", open_connection)
    monkeypatch.setattr(umcub, "connect", connect)
    monkeypatch.setattr(umcub, "flash", flash)
    monkeypatch.setattr(umcub, "discover", discover)
    monkeypatch.setattr(umcub, "adapters", adapters)
    monkeypatch.setattr(umcub, "Smp", FakeSmp)
    return calls, answers


@pytest.fixture
def signed_image(tmp_path):
    """A small signed MCUboot image file, 1.2.3 for board type 0x46103001 (header, payload, SHA-256 and board type
    TLVs)."""
    import hashlib
    import struct

    payload = b"\x11" * 256
    tlvs = struct.pack("<HH", 0x10, 32) + hashlib.sha256(payload).digest() + struct.pack("<HHI", 0xA0, 4, 0x46103001)
    hdr = struct.pack("<IIHHIIBBHI", 0x96F3B83D, 0, 32, 0, len(payload), 0, 1, 2, 3, 0)
    path = tmp_path / "app.signed.bin"
    path.write_bytes(hdr.ljust(32, b"\0") + payload + struct.pack("<HH", 0x6907, 4 + len(tlvs)) + tlvs)
    return path
