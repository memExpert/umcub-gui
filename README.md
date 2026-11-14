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
interval, the role and the language (the system's by default; English and Russian, at the next start).

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

## Install

The [releases](https://github.com/memExpert/umcub-gui/releases) hold the program, no Python needed:

- Windows: `umcub-gui-<version>-windows-x64.zip` - unpack it and run `umcub-gui\umcub-gui.exe`. The program is not
  signed, so SmartScreen asks once ("More info" -> "Run anyway").
- Linux (x86_64): `umcub-gui-<version>-linux-x86_64.AppImage` - `chmod +x` it and run it. Serial ports need the user
  in the `dialout` (or `uucp`) group; without FUSE, run it with `APPIMAGE_EXTRACT_AND_RUN=1`.

A language without a new build: put its `umcub_gui_<lang>.qm` into a `translations` folder next to the program
(next to `umcub-gui.exe`, or next to the AppImage file); it also replaces a built-in one.

Plugins from the plugin folder can import the host library, Python's standard library and what the program itself
uses; a plugin needing another package needs the `pip install` setup below.

## Development

```sh
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[test]"
python -m umcub_gui
pytest
```

Translations (Qt Linguist): `python tools/translations.py release` once for the Russian window (the `.qm` files are
built, not kept in git); after changing texts `python tools/translations.py update`, then translate the new strings in
`umcub_gui/translations/*.ts` (pyside6-linguist) - the tests fail while one is missing. Library errors are translated
by their code's template (`umcub_gui/app/error_texts.py`, written by `update` from the pinned library).

To work on the host library at the same time: `pip install -e ../umcub/tools/host` after the line above.

Release: set `__version__` in `umcub_gui/__init__.py` (the package version too), commit, push a tag `v<version>`;
the Release workflow compiles the translations, builds the Windows zip and the Linux AppImage (PyInstaller,
`packaging/`), runs `umcub-gui --self-test` in each - every module loaded by name, python-can's interfaces, the
window, the translations - and publishes them. Run it by hand from the Actions tab to try a build without a release.
Locally, in a venv with the program installed (`pip install . pyinstaller`, not `-e`):
`python tools/translations.py release`, then `pyinstaller --noconfirm packaging/umcub-gui.spec`.

## License

Apache-2.0, see [LICENSE](LICENSE).
