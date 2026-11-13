# PyInstaller: the program as a folder (dist/umcub-gui/), Linux and Windows. In a venv with the program installed
# (`pip install . pyinstaller`: an editable install is not found), from the repository root:
#   pyinstaller --noconfirm packaging/umcub-gui.spec
# packaging/appimage.sh turns the Linux folder into an AppImage. `umcub-gui --self-test` checks a build.
from can.interfaces import BACKENDS

a = Analysis(
    ["launcher.py"],
    # python-can imports its interfaces by name (can:<interface>:<channel>). From its own table, not by importing them
    # (collect_submodules): a Windows-only interface fails to import on Linux and would be left out silently.
    hiddenimports=sorted(module for module, _ in BACKENDS.values()),
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="umcub-gui", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="umcub-gui")
