# umcub-gui

Desktop flasher for devices running the [umcub](https://github.com/memExpert/umcub) bootloader: pick an adapter,
find the devices, upload signed images, check and mark them, keep a history.

**Status: milestone 5 of [docs/plan.md](docs/plan.md).** A device table filled by discovery (umcub link nodes, CAN
nodes, each row with its UID, board and "found" / "not found") or by hand, each row with its own image and protocol;
the checked rows are flashed with progress per row, the devices of one serial port in turn and CAN / UDP devices in
parallel, then each device checks its image (failed rows can be retried). Connect keeps the checked devices
connected (a SECURE session authenticated once, the devices of a serial port sharing it) until Disconnect, pinging
them so the sessions stay open and lost devices show. Shared settings: adapter, SECURE key files, slot, test /
permanent mark, reset. A history tab (SQLite in the user data folder); the last session, table included, comes back
at the next start with no row checked; Settings holds the board name files, the plugin folder, the keepalive
interval and the role.

Roles only shape the window: customer flashes; operator also discovers and sees the history; service adds the slot
panel - the image slots of the selected device, verify, hash against the row's image, test boot / permanent marks
for the secondary slot and readback to a file, on the checked rows or the selected one when none is checked
(readback: the selected one); developer adds a Developer tab - the exchange log of every connection (pause, clear,
save, the selected device only) and a text console to the selected device.

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
