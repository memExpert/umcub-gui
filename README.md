# umcub-gui

Desktop flasher for devices running the [umcub](https://github.com/memExpert/umcub) bootloader: pick an adapter,
find the devices, upload signed images, check and confirm them, keep a history.

**Status: milestone 3 of [docs/plan.md](docs/plan.md).** A device table filled by discovery (umcub link nodes, CAN
nodes) or by hand, each row with its own image and protocol; the checked rows are flashed with progress per row, the
devices of one serial port in turn and CAN / UDP devices in parallel, then each device checks its image (failed rows
can be retried). Shared settings: adapter, SECURE key files, slot, test / permanent mark, reset. A history tab
(SQLite in the user data folder); the last session, table included, comes back at the next start; Settings holds the
board name files and the plugin folder.

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
