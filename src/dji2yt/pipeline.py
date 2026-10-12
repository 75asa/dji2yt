"""Core pipeline: Drive -> rename -> plugins -> YouTube (unlisted) -> playlists."""

from __future__ import annotations

import hashlib
import logging
import shutil
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from .auth import load_credentials
from .config import Config
from .drive import Drive
from .media import probe
from .naming import is_prefixed, prefixed_name, resolve_shot_time, strip_prefix
from .plugins import Plugin, Services, VideoContext, load_plugins
from .sources import DriveSource, LocalSource, SourceFile
from .state import State
from .youtube import QuotaExceeded, YouTube

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, cfg: Config, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.tz = ZoneInfo(cfg.timezone)
        creds = load_credentials(cfg.token_path)
        self.services = Services(
            drive=build("drive", "v3", credentials=creds, cache_discovery=False),
            youtube=build("youtube", "v3", credentials=creds, cache_discovery=False),
            calendar=build("calendar", "v3", credentials=creds, cache_discovery=False),
            tz=self.tz,
        )
        if cfg.local:
            self.source = LocalSource(
                cfg.local.path, cfg.local.extensions, cfg.local.min_age_minutes
            )
            self.rename_enabled = cfg.local.rename
        else:
            self.source = DriveSource(
                Drive(self.services.drive), cfg.drive.folder_id, cfg.drive.extensions
            )
            self.rename_enabled = cfg.drive.rename_on_drive
        self.yt = YouTube(self.services.youtube)
        self.state = State(cfg.state_path)
        self.plugins: list[Plugin] = load_plugins(
            cfg.plugins_enabled, cfg.plugin_settings, self.services
        )

    # ------------------------------------------------------------------
    def run(self, limit: int | None = None) -> None:
        limit = limit or self.cfg.youtube.max_uploads_per_run
        files = [f for f in self.source.list() if not self.state.is_done(f.id)]
        log.info("%d new video(s) found", len(files))
        for f in files[:limit]:
            try:
                self.process(f)
            except QuotaExceeded:
                log.warning("YouTube quota exhausted; remaining files will be retried next run")
                return
            except Exception as e:
                log.exception("failed: %s", f.name)
                if not self.dry_run:
                    self.state.mark(f.id, f.name, "failed", repr(e))

    # ------------------------------------------------------------------
    def process(self, f: SourceFile) -> None:
        work = self.cfg.work_dir / hashlib.sha1(f.id.encode()).hexdigest()[:12]
        work.mkdir(parents=True, exist_ok=True)
        try:
            self._process(f, work)
        finally:
            if not self.dry_run:
                shutil.rmtree(work, ignore_errors=True)

    def _process(self, f: SourceFile, work) -> None:
        log.info("processing %s (%.1f GB)", f.name, f.size / 1e9)
        original = strip_prefix(f.name)
        if self.source.is_local:
            local = self.source.fetch(f, work)
            info = probe(local)
            duration, probed_ct = info.duration, info.creation_time
        elif self.dry_run:
            # don't pull multi-GB files just to preview names/playlists
            log.info("[dry-run] skip download")
            local = work / original
            duration, probed_ct = f.duration, None
        else:
            local = self.source.fetch(f, work)
            info = probe(local)
            duration, probed_ct = info.duration, info.creation_time
        shot_at = resolve_shot_time(f.name, self.tz, probed_ct, f.created_time)
        new_name = f.name if is_prefixed(f.name) else prefixed_name(f.name, shot_at)

        if new_name != f.name and self.rename_enabled:
            if self.dry_run:
                log.info("[dry-run] rename %s -> %s", f.name, new_name)
            else:
                old_name = f.name
                renamed = self.source.rename(f, new_name)
                if renamed is not None:
                    local = renamed
                log.info("renamed %s -> %s", old_name, new_name)

        yc = self.cfg.youtube
        fmt = {"shot_at": shot_at, "original_name": original, "name": new_name}
        ctx = VideoContext(
            drive_id=f.id,
            original_name=original,
            name=new_name,
            local_path=local,
            shot_at=shot_at,
            duration=duration,
            title=new_name.rsplit(".", 1)[0],
            description=yc.description_template.format(**fmt),
            work_dir=work,
        )
        if yc.playlist_template:
            ctx.add_playlist(yc.playlist_template.format(**fmt))

        for p in self.plugins:
            p.annotate(ctx)
        log.info("labels=%s playlists=%s", ctx.labels, ctx.playlists)

        # derive before uploading so plugins can still adjust the main upload's playlists
        if self.dry_run:
            log.info("[dry-run] skip derive()")
            derived = []
        else:
            derived = [(f"{p.name}:{d.key}", d) for p in self.plugins for d in p.derive(ctx)]

        uploads: dict[str, str] = {}
        uploads["main"] = self._upload(
            f.id, "main", local, ctx.title, ctx.description, ctx.tags, ctx.playlists, shot_at
        )
        for key, d in derived:
            uploads[key] = self._upload(
                f.id, key, d.path, d.title, d.description or ctx.description,
                d.tags or ctx.tags, d.playlists, shot_at,
            )
        for p in self.plugins:
            p.after_upload(ctx, uploads)

        if not self.dry_run:
            self.state.mark(f.id, new_name, "done")
        log.info("done %s -> %s", new_name, uploads)

    def _upload(self, drive_id, key, path, title, description, tags, playlists, shot_at) -> str:
        yc = self.cfg.youtube
        if self.dry_run:
            log.info("[dry-run] upload %s as '%s' -> playlists %s", path.name, title, playlists)
            return f"dry-run:{key}"

        video_id = self.state.uploaded(drive_id, key)
        if video_id is None:
            video_id = self.yt.upload(
                path, title, description, tags, yc.privacy, yc.category_id,
                recorded_at=shot_at.isoformat(),
            )
            self.state.record_upload(drive_id, key, video_id)
            log.info("uploaded %s -> https://youtu.be/%s", key, video_id)

        for title_ in playlists:
            if self.state.in_playlist(video_id, title_):
                continue
            pid = self.yt.ensure_playlist(title_, yc.playlist_privacy)
            self.yt.add_to_playlist(pid, video_id)
            self.state.record_playlist(video_id, title_)
        return video_id
