"""Google Drive: list new videos, download, rename."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

log = logging.getLogger(__name__)

_CHUNK = 32 * 1024 * 1024


@dataclass
class DriveFile:
    id: str
    name: str
    size: int
    created_time: datetime


class Drive:
    def __init__(self, service):
        self.svc = service

    def list_videos(self, folder_id: str, extensions: tuple[str, ...]) -> list[DriveFile]:
        q = f"'{folder_id}' in parents and trashed = false and mimeType contains 'video/'"
        files: list[DriveFile] = []
        token = None
        while True:
            resp = (
                self.svc.files()
                .list(
                    q=q,
                    fields="nextPageToken, files(id, name, size, createdTime)",
                    pageSize=200,
                    pageToken=token,
                    orderBy="createdTime",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for f in resp.get("files", []):
                if not f["name"].lower().endswith(extensions):
                    continue
                files.append(
                    DriveFile(
                        id=f["id"],
                        name=f["name"],
                        size=int(f.get("size", 0)),
                        created_time=datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")),
                    )
                )
            token = resp.get("nextPageToken")
            if not token:
                return files

    def download(self, file: DriveFile, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = self.svc.files().get_media(fileId=file.id, supportsAllDrives=True)
        with tmp.open("wb") as fh:
            dl = MediaIoBaseDownload(fh, req, chunksize=_CHUNK)
            done = False
            while not done:
                status, done = dl.next_chunk(num_retries=5)
                if status:
                    log.info("download %s: %d%%", file.name, int(status.progress() * 100))
        tmp.rename(dest)
        return dest

    def rename(self, file_id: str, new_name: str) -> None:
        self.svc.files().update(
            fileId=file_id, body={"name": new_name}, supportsAllDrives=True
        ).execute()
