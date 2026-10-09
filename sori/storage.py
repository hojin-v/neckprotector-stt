from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from sori.keybindings import DEFAULT_HOTKEY, valid_hotkey


def data_directory() -> Path:
    if os.environ.get("SORI_DATA_DIR"):
        return Path(os.environ["SORI_DATA_DIR"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Sori"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Sori"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "sori"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temp = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()


@dataclass
class Settings:
    hotkey: str = DEFAULT_HOTKEY
    mode: str = "toggle"
    language: str = "Korean"
    device: str = "auto"
    microphone: str = ""
    auto_paste: bool = True
    clipboard: str = "today"
    archive_directory: str = ""
    hold_ms: int = 250
    input_method: str = "paste"

    @classmethod
    def load(cls, directory: Path) -> Settings:
        try:
            raw = json.loads((directory / "settings.json").read_text(encoding="utf-8"))
            result = cls(**{key: value for key, value in raw.items() if key in {f.name for f in fields(cls)}})
            if result.mode not in {"toggle", "hold"} or result.clipboard not in {"today", "latest"}:
                raise ValueError("Invalid settings")
            if not valid_hotkey(result.hotkey):
                raise ValueError("Invalid hotkey")
            if result.language not in {"Korean", "English", "Japanese", "Chinese", "auto"}:
                raise ValueError("Invalid language")
            if result.device not in {"auto", "cpu", "cuda", "xpu", "mps"}:
                raise ValueError("Invalid device")
            if result.input_method not in {"paste", "unicode"}:
                raise ValueError("Invalid input method")
            if not isinstance(result.hold_ms, int) or not 100 <= result.hold_ms <= 2000:
                raise ValueError("Invalid hold delay")
            return result
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def save(self, directory: Path) -> None:
        atomic_write(directory / "settings.json", json.dumps(asdict(self), ensure_ascii=False, indent=2))


class HistoryStore:
    """SQLite is authoritative; Markdown and JSONL are recoverable daily views."""

    def __init__(self, directory: Path, archive_directory: str = ""):
        directory.mkdir(parents=True, exist_ok=True)
        self.archive = Path(archive_directory).expanduser() if archive_directory else directory / "history"
        self.db = sqlite3.connect(directory / "history.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, day TEXT NOT NULL,
            session TEXT NOT NULL, text TEXT NOT NULL, duration REAL NOT NULL,
            language TEXT NOT NULL, target TEXT NOT NULL,
            delivery TEXT NOT NULL DEFAULT 'clipboard'
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS entries_day ON entries(day, timestamp)")
        self.db.commit()
        self.export_error = ""
        try:
            self.export_all()
        except OSError as exc:
            self.export_error = str(exc)

    def add(self, text: str, timestamp: datetime, session: str, duration: float,
            language: str, target: str = "") -> dict:
        text = text.strip()
        if not text:
            raise ValueError("Empty transcription")
        timestamp = timestamp.astimezone()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO entries(timestamp,day,session,text,duration,language,target) VALUES (?,?,?,?,?,?,?)",
                (timestamp.isoformat(timespec="seconds"), timestamp.date().isoformat(), session, text,
                 round(duration, 3), language, target),
            )
        # Export is deliberately separate. A failed export never rolls back the transcript.
        return dict(self.db.execute("SELECT * FROM entries WHERE id=?", (cur.lastrowid,)).fetchone())

    def delivered(self, entry_id: int, delivery: str) -> None:
        with self.db:
            self.db.execute("UPDATE entries SET delivery=? WHERE id=?", (delivery, entry_id))

    def entries(self, day: str | None = None, search: str = "") -> list[dict]:
        conditions, args = [], []
        if day:
            conditions.append("day=?")
            args.append(day)
        if search:
            conditions.append("instr(lower(text), lower(?)) > 0")
            args.append(search)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return [dict(row) for row in self.db.execute("SELECT * FROM entries" + where + " ORDER BY timestamp, id", args)]

    def days(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT DISTINCT day FROM entries ORDER BY day DESC")]

    def clipboard_text(self, day: str, latest: str, mode: str) -> str:
        return latest if mode == "latest" else "\n".join(row["text"] for row in self.entries(day))

    def export_day(self, day: str) -> None:
        rows = self.entries(day)
        self.write_export(self.archive, day, rows)

    @staticmethod
    def write_export(archive: Path, day: str, rows: list[dict]) -> None:
        if not rows:
            return
        lines = [f"# 소리 · {day}", "", f"받아쓰기 {len(rows)}건 · {sum(len(r['text']) for r in rows):,}자", ""]
        last_session = None
        for row in rows:
            stamp = datetime.fromisoformat(row["timestamp"])
            if last_session != row["session"]:
                lines.extend(["---", ""])
                last_session = row["session"]
            lines.extend([f"### {stamp:%H:%M:%S} ({stamp:%z})", "",
                          f"{row['duration']:.1f}초 · {row['language']} · {row['target'] or '음성 입력'}", "",
                          row["text"], ""])
        atomic_write(archive / f"{day}.md", "\n".join(lines))
        atomic_write(archive / f"{day}.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))

    def export_all(self) -> None:
        for day in self.days():
            self.export_day(day)

    def close(self) -> None:
        self.db.close()
