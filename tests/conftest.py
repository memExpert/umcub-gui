import pytest
from PySide6.QtCore import QSettings


@pytest.fixture
def qsettings(tmp_path):
    """Settings in a temporary INI file instead of the user's."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


class FakeDevice:
    def __init__(self, identity, spec, node):
        self.identity, self.spec, self.node = identity, spec, node

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


@pytest.fixture
def fake_umcub(monkeypatch):
    """The host library calls the app makes, recorded; tests set the answers. answers["delay"] makes each upload
    take that long; answers["most_at_once"] counts the uploads that ran together per device string;
    answers["fail_nodes"]: nodes whose upload fails (flash.invalid)."""
    import threading
    import time

    import umcub

    lock = threading.Lock()
    running = {}

    calls = []
    answers = {"identity": {"addr": 5, "uid": "00" * 12, "board_type": 0x46103001, "board_rev": 1, "link": 1,
                            "enc": False, "closed": False, "version": "1.0.0"},
               "flash": "verify", "devices": [], "adapters": [], "delay": 0.0, "most_at_once": {},
               "fail_nodes": set()}

    def connect(spec, node=None, uid=None, admin_key=None, device_key=None, timeout=3.0, tap=None):
        calls.append(("connect", spec, node, uid, admin_key, device_key))
        if isinstance(answers.get("connect"), Exception):
            raise answers["connect"]
        return FakeDevice(answers["identity"], spec, node)

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

    def discover(spec, **kw):
        calls.append(("discover", spec))
        return answers["devices"]

    def adapters(**kw):
        calls.append(("adapters",))
        return answers["adapters"]

    monkeypatch.setattr(umcub, "connect", connect)
    monkeypatch.setattr(umcub, "flash", flash)
    monkeypatch.setattr(umcub, "discover", discover)
    monkeypatch.setattr(umcub, "adapters", adapters)
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
