import umcub

from umcub_gui.ui.main_window import MainWindow


def test_main_window(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    assert "umcub" in win.windowTitle()


def test_host_library():
    assert callable(umcub.connect) and callable(umcub.discover)
    # what stage 1 of the plan added (umcub v0.2.0)
    for name in ("adapters", "flash", "add_tap", "load_board_names", "board_label", "load_plugins"):
        assert callable(getattr(umcub, name)), name
