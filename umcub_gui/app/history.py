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
    error_text: str             # in the language of that time; shown from error_code + error_params when known
    app_version: str
    error_params: str = ""      # JSON of the library error's params (i18n.record_error)


_COLUMNS = [f.name for f in fields(Record)]


class History:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)     # jobs write from worker threads
        self.lock = threading.Lock()
        self.db.execute(f"CREATE TABLE IF NOT EXISTS flash ({', '.join(_COLUMNS)})")
        have = {r[1] for r in self.db.execute("PRAGMA table_info(flash)")}
        for c in _COLUMNS:
            if c not in have:                   # a database of an older program version
                self.db.execute(f"ALTER TABLE flash ADD COLUMN {c} DEFAULT ''")
        self.db.commit()

    def add(self, record):
        with self.lock:
            self.db.execute(f"INSERT INTO flash VALUES ({', '.join('?' * len(_COLUMNS))})", astuple(record))
            self.db.commit()

    def records(self, limit=None):
        """Newest first; `limit`: only that many (a station keeps thousands)."""
        with self.lock:
            rows = self.db.execute(f"SELECT {', '.join(_COLUMNS)} FROM flash ORDER BY started DESC"
                                   + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()
        return [Record(*r) for r in rows]
