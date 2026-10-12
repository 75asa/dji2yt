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
    duration: float = 0.0  # from Drive's videoMediaMetadata, 0 if not processed yet


class Drive:
    def __init__(self, service):
        self.svc = service

    def _children(self, folder_id: str) -> list[dict]:
        q = (
            f"'{folder_id}' in parents and trashed = false and "
            "(mimeType contains 'video/' or mimeType = 'application/vnd.google-apps.folder')"
        )
        items: list[dict] = []
        token = None
        while True:
            resp = (
                self.svc.files()
                .list(
                    q=q,
                    fields=(
                        "nextPageToken, files(id, name, mimeType, size, createdTime, "
                        "videoMediaMetadata/durationMillis)"
                    ),
                    pageSize=200,
                    pageToken=token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            items += resp.get("files", [])
            token = resp.get("nextPageToken")
            if not token:
                return items

    def list_videos(
        self, folder_id: str, extensions: tuple[str, ...], max_depth: int = 3
    ) -> list[DriveFile]:
        """Videos under ``folder_id``, including date subfolders (e.g. 20261012/).

        DJI also uploads ``.LRF`` proxies with a video/mp4 MIME type; the
        extension filter keeps only the real ``.MP4`` files.
        """
        files: list[DriveFile] = []
        queue = [(folder_id, 0)]
        while queue:
            fid, depth = queue.pop(0)
            for f in self._children(fid):
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    if depth < max_depth:
                        queue.append((f["id"], depth + 1))
                    continue
                if not f["name"].lower().endswith(extensions):
                    continue
                files.append(
                    DriveFile(
                        id=f["id"],
                        name=f["name"],
                        size=int(f.get("size", 0)),
                        created_time=datetime.fromisoformat(
                            f["createdTime"].replace("Z", "+00:00")
                        ),
                        duration=int(f.get("videoMediaMetadata", {}).get("durationMillis", 0))
                        / 1000,
                    )
                )
        files.sort(key=lambda f: f.created_time)
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
