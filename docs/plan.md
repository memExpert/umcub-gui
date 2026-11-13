# umcub GUI: plan

Draft of 2026-11-05.

## Goal and scope

A desktop **flasher** for devices running the umcub bootloader: pick an adapter, find the devices, upload signed
images, check and mark them, keep a history. It works with every adapter class the bootloader can be reached
through (USB-UART, USB-RS485, USB-CAN, USB-Ethernet / any network, the board's own USB CDC) and lets users add a
driver for an adapter the app does not know.

Out of scope: configuring or building the bootloader (Kconfig, toolchain), signing images, job packages. Images
arrive signed (and encrypted, if used) from the firmware build.

## Decisions

| Topic | Decision |
|---|---|
| Language / UI | Python, PySide6 (Qt 6, LGPL) |
| Device logic | the `umcub` host library of the umcub repository; the GUI holds no protocol code |
| Repository | separate GitHub repository `umcub-gui`; depends on `umcub` by the source archive of a tag (`subdirectory=tools/host`; a git URL would clone all submodules) |
| OS | Linux and Windows; macOS not planned |
| Users | firmware developers, production operators, service engineers, end customers; UI roles show what a role needs |
| Custom adapters | Python plugins: a plugin folder (works in the installer build) and pip packages (entry points) |
| UI language | English first; translations as files added without rebuilding |
| History | local SQLite, export to CSV / JSON; written through an interface so a server can be added later |
| Packaging | PyInstaller (one folder per OS), plus `pip install` for developers |
| License | Apache-2.0, like umcub |

## Users and roles

Roles only shape the UI (which screens and actions are shown); they are not a security boundary: anybody with the
keys can use the CLI. The real boundaries are on the device and in the keys:

- slot readback exists only in builds with `UMCUB_CFG_READBACK` (off by default) and is then answered only inside an
  encrypted SECURE link session, so only holders of the admin key can read;
- uploads need a signed image; SECURE transports need the admin key (or, later, a server signature).

How the service role is unlocked (password, key, server account) is **open** (see Open questions).

| Role | Sees |
|---|---|
| End customer | one device, upload, result |
| Operator | discovery, upload to many devices, result list, history |
| Service engineer | + slots, verify, hash, test boot / permanent marks, readback, device info, history export |
| Developer | + exchange log, bus sniffer, text console, raw SMP |

## Features

First version:
- adapter list (detected serial ports, CAN interfaces, network interfaces, plugins) and saved connections
- connect: direct, umcub link node / UID, SECURE with key files (paths stored, never the keys), CAN node IDs
- image info before upload (version, hash, board type) and board type check against the device
- board names: a user-loaded catalog maps the board type id a device reports (`board_type`, 32 bits, Kconfig
  `UMCUB_CFG_BOARD_TYPE`; the hardware revision does not matter) to a controller name, shown in the discovery list, the
  device panel, the image check and the history; unknown ids stay as hex. Loaded from a file, several files merge,
  later also from a server
- upload with progress and cancel; SMP or lite chosen by the user (the bootloader build decides, the app does not
  probe); after the upload the device checks the image without sending it back (verify, else hash; "not checked"
  when it cannot); reset afterwards as a checkbox
- discovery of link nodes; upload to several devices, in parallel where the adapters / bus allow it
- slots: state, verify, hash, test boot / permanent marks; readback for the service role
- exchange log, link bus sniffer, text console (developer role)
- history per device UID with export

Later:
- USB DFU of the board (needs a DFU implementation in the library, libusb access, WinUSB on Windows; decided later)
- SECURE sessions signed by a server (see TODO.md of umcub), accounts, history upload to a server
- admin key with a passphrase / from the OS key store

Dropped: job packages, one image broadcast to all devices at once, Kconfig / builds / signing.

## Adapters

The app never drives USB itself; every adapter reaches it through the OS or a driver library:

| Adapter | Seen as | Library today |
|---|---|---|
| USB-UART, USB-RS485, board USB CDC | serial port | `serial:` (pyserial): any FTDI / CH340 / CP210x / CDC |
| USB-CAN | python-can interface | `can:<interface>:<channel>`: SocketCAN, PCAN, slcan, gs_usb, Vector, Kvaser ... |
| USB-Ethernet, any network | network interface | `udp:` (sockets); discovery needs the interface to broadcast on |
| anything else | plugin | not yet: `open_connection()` knows only `serial`, `udp`, `can` |

A plugin is one of:
- a **connection** class (`send(kind, payload)`, `recv(kind, timeout)`, `text()`, `close()`, `stream`, `mtu`) for a
  byte stream or packet transport the OS does not expose as a port or socket;
- a **python-can interface** (python-can's own plugin mechanism) for a CAN adapter python-can does not know: then the
  whole ISO-TP path is reused.

Plugins run inside the app with full rights: the app loads them only from its plugin folder or installed packages and
lists what it loaded.

## Architecture

```
umcub-gui (separate repository)
  ui/        Qt windows and widgets, roles, translations     no device logic
  app/       jobs (one worker thread per device job), queue, cancel, results,
             settings (QSettings), history (SQLite), plugin loading
      |  calls
umcub host library (umcub repository, tools/host/umcub)
  adapters    list of adapters: serial ports, CAN configs, network interfaces, plugins     new
  transports  registry: scheme -> class, plugins by entry points / folder                   new
  parallel    one shared python-can bus per CAN channel; exclusive_key(): what takes turns   new
  device, link, smp, lite                                                                   exist
  flash       upload with checks; SMP or lite given by the caller                           new
  tap         callback for every frame sent / received (log, sniffer)                       new
```

- Threads: library calls block; every device job runs in its own worker thread and reports progress through Qt
  signals. `Smp` already owns one asyncio loop per instance, so one `Smp` per thread works.
- Several devices (decided): a serial port is one half-duplex bus (RS485 has no arbitration, a device answers after
  writing its flash), so its devices take turns; CAN and UDP devices run in parallel. The library tells which is which
  (`umcub.exclusive_key(spec)`) and shares one python-can bus per CAN channel (single-handle drivers such as PCAN on
  Windows open a channel once); the app runs one thread per medium, the rows of a medium in turn.
- Errors: the library raises `UmcubError` subclasses with English text. For translations they also carry a stable
  code and parameters; the GUI translates by code and shows the text as a fallback.
- Translations: Qt Linguist `.ts` sources, compiled `.qm` files in a `translations/` folder next to the app, loaded
  by locale or a setting; a new language is one file.
- Connections: Connect keeps the checked devices open until Disconnect (one port per serial adapter, shared by its
  nodes), a keepalive ping (interval in Settings) keeps SECURE sessions alive and shows lost devices; jobs use the
  open connections, or open their own when not connected.
- Settings: QSettings (adapter defaults, saved connections, key file paths, role); the last session's choices
  (adapter, key files, upload options, the device table with protocols and images) come back at the next start, the
  rows unchecked so that nothing is flashed by accident. History: SQLite in the user data
  directory: start / end time, UID, board type, node, adapter, image name / version / hash, result, error, app
  version, plus the board name it had at that time (names can change later).

## Changes in the umcub host library

In order; each with host tests (and the CLI uses them too):

1. Transport registry: `open_connection()` dispatches on the scheme to registered classes; plugins through the entry
   point group `umcub.transports` and a plugin folder argument.
2. `umcub.adapters()`: detected adapters with a display name and a ready connection string (pyserial `list_ports`
   with VID / PID, `can.detect_available_configs()`, network interfaces, plugin entries).
3. Several devices: one shared bus per CAN channel, `exclusive_key()` for what must take turns (a serial port).
4. `flash()`: one upload call (protocol given by the caller) with progress, cancel, board type check before and a
   check without readback after.
5. Frame tap: an optional callback on every frame (direction, kind, bytes, time); `sniff()` becomes a tap user that
   can stop (today it runs until interrupted and prints through `out=print`).
6. Error codes on `UmcubError`.
7. SECURE signing through a function next to `admin_key` as a file (prepares server signing).
8. Install extras: build-only dependencies (`esp-idf-kconfig`, signing) in an extra such as `umcub[build]`, after
   checking what is imported at start; version tags.
9. Board name catalog: `load_board_names(path)` -> {board_type: name} and a lookup that falls back to hex, so
   the CLI shows the same names (`umcub discover --names <file>`). JSON (standard library), one name per board
   type, no revision; kept by the user next to their images, e.g. `{"0x00010002": "Pump controller"}`.
10. CAN discovery: `discover()` on CAN asks nodes 0..7 (the default IDs) a lite frame of no known kind, else an SMP
   echo, with the channel kept open for all probes.

## Testing

- Library: host tests in umcub as today, plus tests for the registry, hub, tap and `flash()`.
- GUI: pytest-qt for the app layer and the windows against fakes of the host library calls (`connect`, `flash`,
  `discover`, `adapters`); later an end-to-end run against the host simulation of umcub (to check what the link e2e
  test offers, e.g. `serve --pty-link`).
- Hardware: the umcub bench (H755, Blue Pill A/B on RS485, Black Pill, CAN) on Linux; Windows with real adapters
  (FTDI, CH340, PCAN or gs_usb) before a release.

## Milestones

1. Library: registry, adapters, error codes, tap, `flash()`, extras, first tag. Done: umcub v0.2.0.
2. GUI skeleton: repository, CI (Linux + Windows), adapter list, connect, upload one device, history. Done, with link
   discovery (a Discover button filling a device list) and the Settings dialog (board names, plugin folder).
3. Several devices: the device table (each row its own image), serial rows in turn and CAN / UDP in parallel,
   failed rows retried; CAN discovery. Done: umcub v0.3.1.
4. Slots, verify, hash, test boot / permanent marks, readback; roles. Done: a slot panel for the selected device
   (actions on the checked rows, or the selected one when none is checked), roles as a setting without unlock (how
   the service role is unlocked is still open). No Confirm button: in recovery nothing runs, the application
   confirms itself; lite devices have no slots.
5. Log, sniffer, console; translations; installers; Windows hardware check.

## Open questions

- How the service role is unlocked (password, key file, server account): with colleagues.
- Whether readback must be refused per key on the device (two admin keys, a firmware change with a size cost).
- USB DFU: library implementation (pyusb) or `dfu-util`; WinUSB on Windows.
