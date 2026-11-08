"""Settings in QSettings: the last session's choices (restored at the next start) and the app settings."""
import json
from dataclasses import asdict, dataclass, field, fields

from PySide6.QtCore import QSettings

from .batch import Row


@dataclass
class Session:
    """What the main window shows: the adapter, the key files, the upload options and the device table."""
    adapter: str = ""           # device string (umcub.connect)
    admin_key: str = ""         # key file paths only, never the keys
    device_key: str = ""
    slot: str = "primary"       # "primary" | "secondary"
    mark: str = ""              # secondary slot: "" | "test" | "permanent"
    reset: bool = False
    rows: list = field(default_factory=list)    # [Row]


class Settings:
    def __init__(self, qsettings=None):
        self.q = qsettings if qsettings is not None else QSettings()

    def session(self):
        s = Session()
        for f in fields(Session):
            v = self.q.value(f"session/{f.name}")
            if v is None:
                continue
            if f.name == "rows":
                v = [Row(**r) for r in json.loads(v)]
            elif f.name == "reset":
                v = v in (True, "true", "1")
            setattr(s, f.name, v)
        return s

    def save_session(self, s):
        for f in fields(Session):
            v = getattr(s, f.name)
            self.q.setValue(f"session/{f.name}", json.dumps([asdict(r) for r in v]) if f.name == "rows" else v)

    def board_name_files(self):
        return [f for f in self.q.value("board_names", "").split("\n") if f]

    def set_board_name_files(self, files):
        self.q.setValue("board_names", "\n".join(files))

    def plugins_folder(self):
        return self.q.value("plugins_folder", "")

    def set_plugins_folder(self, folder):
        self.q.setValue("plugins_folder", folder)
