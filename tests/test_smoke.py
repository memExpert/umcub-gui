import umcub

from umcub_gui.ui.main_window import MainWindow


def test_main_window(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    assert "umcub" in win.windowTitle()


def test_host_library():
    assert callable(umcub.connect) and callable(umcub.discover)
