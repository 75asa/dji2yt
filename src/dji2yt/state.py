"""SQLite state so reruns are idempotent (no double uploads)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    drive_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL,          -- done | failed | skipped
    error      TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS uploads (
    drive_id   TEXT NOT NULL,
    key        TEXT NOT NULL,          -- "main" or a derivative key like "tennis:rallycut"
    video_id   TEXT NOT NULL,
    PRIMARY KEY (drive_id, key)
);
CREATE TABLE IF NOT EXISTS playlist_items (
    video_id   TEXT NOT NULL,
    playlist   TEXT NOT NULL,
    PRIMARY KEY (video_id, playlist)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)

    def is_done(self, drive_id: str) -> bool:
        row = self.db.execute("SELECT status FROM files WHERE drive_id=?", (drive_id,)).fetchone()
        return row is not None and row[0] in ("done", "skipped")

    def mark(self, drive_id: str, name: str, status: str, error: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO files(drive_id,name,status,error,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(drive_id) DO UPDATE SET name=excluded.name, status=excluded.status, "
            "error=excluded.error, updated_at=excluded.updated_at",
            (drive_id, name, status, error, _now()),
        )
        self.db.commit()

    def uploaded(self, drive_id: str, key: str) -> str | None:
        row = self.db.execute(
            "SELECT video_id FROM uploads WHERE drive_id=? AND key=?", (drive_id, key)
        ).fetchone()
        return row[0] if row else None

    def record_upload(self, drive_id: str, key: str, video_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO uploads VALUES(?,?,?)", (drive_id, key, video_id))
        self.db.commit()

    def in_playlist(self, video_id: str, playlist: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM playlist_items WHERE video_id=? AND playlist=?", (video_id, playlist)
            ).fetchone()
            is not None
        )

    def record_playlist(self, video_id: str, playlist: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO playlist_items VALUES(?,?)", (video_id, playlist))
        self.db.commit()
