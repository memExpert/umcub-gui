"""Board name files and the plugin folder from the settings are loaded at start and after the settings dialog."""
import umcub

from umcub_gui.app.extensions import load_extensions
from umcub_gui.app.settings import Settings


def test_names_and_plugins(qsettings, tmp_path):
    (tmp_path / "a.json").write_text('{"0x46103001": "Board A"}')
    (tmp_path / "b.json").write_text('{"0x46103001": "Board B"}')
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "gui_test_transport.py").write_text(
        "import umcub\n"
        "def register():\n"
        "    umcub.register_transport('guitest', lambda target, node: None, description='gui test')\n")
    s = Settings(qsettings)
    s.set_board_name_files([str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    s.set_plugins_folder(str(plugins))
    try:
        assert load_extensions(s) == []
        assert umcub.board_label(0x46103001) == "0x46103001 (Board B)"
        assert "guitest" in umcub.transports()
    finally:
        umcub.load_board_names()


def test_errors_are_returned(qsettings, tmp_path):
    (tmp_path / "bad.json").write_text("{")
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "broken_plugin.py").write_text("raise RuntimeError('boom')\n")
    s = Settings(qsettings)
    s.set_board_name_files([str(tmp_path / "bad.json")])
    s.set_plugins_folder(str(plugins))
    errors = load_extensions(s)
    assert any("bad.json" in e for e in errors) and any("broken_plugin" in e and "boom" in e for e in errors)
