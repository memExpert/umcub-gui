"""History of flash jobs: one SQLite row per job, newest first."""
import sqlite3
import threading
from dataclasses import astuple, dataclass, fields
from pathlib import Path


@dataclass
class Record:
    started: float              # time.time()
    finished: float
    uid: str                    # "" when the device has no link identity
    board_type: int | None
    board: str                  # the board label at that time ("0x46103001 (Blue Pill)"): names can change later
    node: int | None
    adapter: str
    image_name: str
    image_version: str
    image_hash: str
    result: str                 # "ok" | "error" | "cancelled"
    checked: str | None         # how the device checked the image: "verify" | "hash" | None
    error_code: str
    error_text: str
    app_version: str


_COLUMNS = [f.name for f in fields(Record)]


class History:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)     # jobs write from worker threads
        self.lock = threading.Lock()
        self.db.execute(f"CREATE TABLE IF NOT EXISTS flash ({', '.join(_COLUMNS)})")
        self.db.commit()

    def add(self, record):
        with self.lock:
            self.db.execute(f"INSERT INTO flash VALUES ({', '.join('?' * len(_COLUMNS))})", astuple(record))
            self.db.commit()

    def records(self):
        with self.lock:
            rows = self.db.execute(f"SELECT {', '.join(_COLUMNS)} FROM flash ORDER BY started DESC").fetchall()
        return [Record(*r) for r in rows]
