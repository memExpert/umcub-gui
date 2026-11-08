import umcub


def test_host_library():
    assert callable(umcub.connect) and callable(umcub.discover)
    for name in ("adapters", "flash", "add_tap", "load_board_names", "board_label", "load_plugins"):
        assert callable(getattr(umcub, name)), name
