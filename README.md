# umcub-gui

Desktop flasher for devices running the [umcub](https://github.com/memExpert/umcub) bootloader: pick an adapter,
find the devices, upload signed images, check and confirm them, keep a history.

**Status: first screens (milestone 2 of [docs/plan.md](docs/plan.md)).** One form: adapter list, link device discovery,
connection (node / UID, SECURE key files), one-device upload over SMP or lite with progress, cancel, the device's check
of the image and an optional reset; a history tab (SQLite in the user data folder). The last session's choices come
back at the next start; Settings holds the board name files and the plugin folder.

- Adapters: everything the OS or python-can exposes - USB-UART, USB-RS485, USB-CAN, USB-Ethernet / any network, the
  board's own USB CDC - plus Python plugins for other adapters.
- Linux and Windows; Python, Qt (PySide6).
- All device logic lives in the umcub host library (`tools/host` of the umcub repository); this repository holds the
  UI and the application layer only.

## Development

```sh
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[test]"
python -m umcub_gui
pytest
```

To work on the host library at the same time: `pip install -e ../umcub/tools/host` after the line above.

## License

Apache-2.0, see [LICENSE](LICENSE).
