"""YouTube: resumable upload and playlist management."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

_CHUNK = 64 * 1024 * 1024
_RETRY_STATUS = {500, 502, 503, 504}


class QuotaExceeded(RuntimeError):
    pass


def _is_quota_error(e: HttpError) -> bool:
    return e.resp.status == 403 and b"quotaExceeded" in (e.content or b"")


class YouTube:
    def __init__(self, service):
        self.svc = service
        self._playlists: dict[str, str] | None = None

    # ---- upload -------------------------------------------------------
    def upload(
        self,
        path: Path,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        privacy: str = "unlisted",
        category_id: str = "17",
        recorded_at: str | None = None,
    ) -> str:
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        }
        if recorded_at:
            body["recordingDetails"] = {"recordingDate": recorded_at}
        media = MediaFileUpload(str(path), chunksize=_CHUNK, resumable=True, mimetype="video/*")
        parts = "snippet,status" + (",recordingDetails" if recorded_at else "")
        req = self.svc.videos().insert(part=parts, body=body, media_body=media)

        response = None
        attempt = 0
        while response is None:
            try:
                status, response = req.next_chunk()
                if status:
                    log.info("upload %s: %d%%", path.name, int(status.progress() * 100))
                attempt = 0
            except HttpError as e:
                if _is_quota_error(e):
                    raise QuotaExceeded(str(e)) from e
                if e.resp.status not in _RETRY_STATUS or attempt >= 8:
                    raise
                attempt += 1
                wait = min(2**attempt, 120) + random.random()
                log.warning("upload error %s, retry in %.0fs", e.resp.status, wait)
                time.sleep(wait)
        video_id = response["id"]
        actual = response.get("status", {}).get("privacyStatus")
        if actual != privacy:
            log.warning(
                "video %s is %s (requested %s). Unaudited API projects force private uploads.",
                video_id, actual, privacy,
            )
        return video_id

    # ---- playlists ----------------------------------------------------
    def _load_playlists(self) -> dict[str, str]:
        if self._playlists is None:
            self._playlists = {}
            token = None
            while True:
                resp = (
                    self.svc.playlists()
                    .list(part="snippet", mine=True, maxResults=50, pageToken=token)
                    .execute()
                )
                for p in resp.get("items", []):
                    self._playlists.setdefault(p["snippet"]["title"], p["id"])
                token = resp.get("nextPageToken")
                if not token:
                    break
        return self._playlists

    def ensure_playlist(self, title: str, privacy: str = "unlisted") -> str:
        pls = self._load_playlists()
        if title in pls:
            return pls[title]
        try:
            resp = (
                self.svc.playlists()
                .insert(
                    part="snippet,status",
                    body={"snippet": {"title": title}, "status": {"privacyStatus": privacy}},
                )
                .execute()
            )
        except HttpError as e:
            if _is_quota_error(e):
                raise QuotaExceeded(str(e)) from e
            raise
        pls[title] = resp["id"]
        log.info("created playlist %s", title)
        return resp["id"]

    def add_to_playlist(self, playlist_id: str, video_id: str) -> None:
        try:
            self.svc.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
        except HttpError as e:
            if _is_quota_error(e):
                raise QuotaExceeded(str(e)) from e
            raise
