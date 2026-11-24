"""--self-test: what a packaged build (PyInstaller) can lose - modules loaded by name, python-can's interfaces, an
adapter source, Qt plugins - checked by the built program itself in CI."""
import sys

from umcub_gui import selftest
from umcub_gui.__main__ import main


def test_self_test_passes_in_the_development_tree(capsys):
    assert main(["--self-test"]) == 0
    assert "self-test: ok" in capsys.readouterr().out


def test_self_test_reports_a_missing_module(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "smpclient", None)     # as if the build left it out
    assert main(["--self-test"]) == 1
    assert "smpclient" in capsys.readouterr().out


def test_self_test_reports_a_failing_adapter_source(monkeypatch):
    """umcub.adapters() skips a source that fails (a transport whose modules the build lacks): reported here."""
    import umcub

    def adapters(errors=None, **kw):
        errors.append("serial: ModuleNotFoundError: No module named 'serial.tools.list_ports_linux'")
        return []
    monkeypatch.setattr(umcub, "adapters", adapters)
    assert any("list_ports_linux" in f for f in selftest.run())


def test_a_can_interface_needing_a_vendor_package_is_no_failure():
    """python-can's own interface modules must be there; the vendor packages some of them import are optional."""
    assert selftest.missing_can_interfaces() == []


def test_self_test_writes_the_report_to_a_file(tmp_path):
    """A windowed build (Windows) has no stdout: CI reads the report from a file."""
    report = tmp_path / "report.txt"
    assert main(["--self-test", str(report)]) == 0
    assert report.read_text(encoding="utf-8") == "self-test: ok\n"


def test_self_test_reports_missing_translations(monkeypatch, tmp_path):
    """A build made without tools/translations.py release would start in English only."""
    from umcub_gui.app import i18n
    monkeypatch.setattr(i18n, "BUILTIN", tmp_path)
    assert any("translations" in f for f in selftest.run())


def test_candlelight_libusb_checked_on_windows_only(monkeypatch, tmp_path):
    """Windows: the gs_usb modules and the libusb-1.0.dll of the libusb1 package (without it pyusb searches its own,
    which crashed) must be in the build; elsewhere SocketCAN lists candleLight adapters and nothing is checked."""
    import types
    pkg = tmp_path / "usb1"
    pkg.mkdir()
    for name, module in (("usb1", types.SimpleNamespace(__file__=str(pkg / "__init__.py"))),
                         ("gs_usb", types.ModuleType("gs_usb")), ("gs_usb.gs_usb", types.ModuleType("gs_usb.gs_usb")),
                         ("usb", types.ModuleType("usb")), ("usb.backend", types.ModuleType("usb.backend")),
                         ("usb.backend.libusb1", types.ModuleType("usb.backend.libusb1"))):
        monkeypatch.setitem(sys.modules, name, module)
    selftest.candlelight_libusb(platform="linux")               # nothing to check
    try:
        selftest.candlelight_libusb(platform="win32")
        raise AssertionError("a missing libusb-1.0.dll must fail")
    except RuntimeError as e:
        assert "libusb-1.0.dll" in str(e)
    (pkg / "libusb-1.0.dll").write_bytes(b"")
    selftest.candlelight_libusb(platform="win32")
