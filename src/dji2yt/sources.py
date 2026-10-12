"""Where videos come from.

* :class:`LocalSource` — a folder on disk, typically synced by Google Drive for
  desktop (``~/Library/CloudStorage/GoogleDrive-.../マイドライブ/DJI Device/...``).
  No API download, renames sync back to Drive automatically, and the Drive
  account doesn't have to be the one authorised for YouTube.
* :class:`DriveSource` — the Drive API, for running without a synced folder
  (e.g. in the cloud).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .drive import Drive
from .naming import strip_prefix

log = logging.getLogger(__name__)


@dataclass
class SourceFile:
    id: str  # stable across renames; used as the state key
    name: str
    size: int
    created_time: datetime
    duration: float = 0.0  # 0 = unknown (probe it)
    path: Path | None = None  # set for local files


class LocalSource:
    is_local = True

    def __init__(
        self,
        root: Path,
        extensions: tuple[str, ...],
        min_age_minutes: float = 10,
        max_depth: int = 3,
    ):
        self.root = root
        self.extensions = extensions
        self.min_age = min_age_minutes * 60
        self.max_depth = max_depth

    def list(self) -> list[SourceFile]:
        if not self.root.is_dir():
            raise SystemExit(f"source folder not found: {self.root}")
        now = time.time()
        files: list[SourceFile] = []
        for p in self.root.rglob("*"):
            rel_depth = len(p.relative_to(self.root).parts) - 1
            if rel_depth > self.max_depth or p.name.startswith(".") or not p.is_file():
                continue
            if not p.name.lower().endswith(self.extensions):
                continue
            st = p.stat()
            if now - st.st_mtime < self.min_age:
                log.info("skip %s: modified %.0fs ago (still syncing?)", p.name, now - st.st_mtime)
                continue
            files.append(
                SourceFile(
                    # DJI names embed timestamp + counter, so the unprefixed name is unique
                    id=f"local:{strip_prefix(p.name)}",
                    name=p.name,
                    size=st.st_size,
                    created_time=datetime.fromtimestamp(st.st_mtime, timezone.utc),
                    path=p,
                )
            )
        files.sort(key=lambda f: strip_prefix(f.name))
        return files

    def fetch(self, f: SourceFile, work_dir: Path) -> Path:
        assert f.path is not None
        return f.path  # read in place; Drive for desktop streams it if needed

    def rename(self, f: SourceFile, new_name: str) -> Path:
        assert f.path is not None
        dest = f.path.with_name(new_name)
        f.path.rename(dest)
        f.path, f.name = dest, new_name
        return dest


class DriveSource:
    is_local = False

    def __init__(self, drive: Drive, folder_id: str, extensions: tuple[str, ...]):
        self.drive = drive
        self.folder_id = folder_id
        self.extensions = extensions

    def list(self) -> list[SourceFile]:
        return [
            SourceFile(
                id=d.id, name=d.name, size=d.size, created_time=d.created_time, duration=d.duration
            )
            for d in self.drive.list_videos(self.folder_id, self.extensions)
        ]

    def fetch(self, f: SourceFile, work_dir: Path) -> Path:
        from .drive import DriveFile

        dest = work_dir / strip_prefix(f.name)
        self.drive.download(DriveFile(f.id, f.name, f.size, f.created_time), dest)
        return dest

    def rename(self, f: SourceFile, new_name: str) -> None:
        self.drive.rename(f.id, new_name)
        f.name = new_name
        return None
