"""Tennis plugin.

* Classifies a video as a match / practice by looking for an overlapping
  Google Calendar event whose title contains one of the configured keywords.
* Adds it to MyTennisMatch / MyTennisPractice.
* Optionally uploads a "rally cut" version with the dead time between points
  removed (see :mod:`.rallycut`).

Settings (``[plugins.tennis]`` in config.toml)::

    calendar_ids      = ["primary"]
    match_keywords    = ["試合", "大会", "match"]
    practice_keywords = ["練習", "レッスン", "テニス", "practice"]
    margin_minutes    = 30
    match_playlist    = "MyTennisMatch"
    practice_playlist = "MyTennisPractice"
    rallycut          = true
    playlist_target   = "cut"     # which upload goes into the tennis playlists: cut | full | both
    [plugins.tennis.rallycut_settings]
    sensitivity = 10.0
    max_gap     = 4.0
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from .. import Derivative, Plugin, Services, VideoContext
from .rallycut import RallyCutSettings, cut_video, detect_rallies

log = logging.getLogger(__name__)


class TennisPlugin(Plugin):
    def setup(self, settings: dict[str, Any], services: Services) -> None:
        super().setup(settings, services)
        s = settings
        self.calendar_ids = s.get("calendar_ids", ["primary"])
        self.match_kw = [k.lower() for k in s.get("match_keywords", ["試合", "大会", "match"])]
        self.practice_kw = [
            k.lower() for k in s.get("practice_keywords", ["練習", "レッスン", "テニス", "practice"])
        ]
        self.margin = timedelta(minutes=s.get("margin_minutes", 30))
        self.playlists = {
            "match": s.get("match_playlist", "MyTennisMatch"),
            "practice": s.get("practice_playlist", "MyTennisPractice"),
        }
        self.rallycut = s.get("rallycut", True)
        self.target = s.get("playlist_target", "cut" if self.rallycut else "full")
        if self.target not in ("cut", "full", "both"):
            raise SystemExit("tennis.playlist_target must be cut | full | both")
        self.rc = RallyCutSettings.from_dict(s.get("rallycut_settings", {}))

    # ------------------------------------------------------------------
    def classify(self, ctx: VideoContext) -> tuple[str | None, str | None]:
        start = ctx.shot_at - self.margin
        end = ctx.shot_at + timedelta(seconds=ctx.duration) + self.margin
        kind: str | None = None
        event_title: str | None = None
        for cal in self.calendar_ids:
            resp = (
                self.services.calendar.events()
                .list(
                    calendarId=cal,
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            for ev in resp.get("items", []):
                title = ev.get("summary", "")
                t = title.lower()
                if any(k in t for k in self.match_kw):
                    return "match", title  # match wins over practice
                if kind is None and any(k in t for k in self.practice_kw):
                    kind, event_title = "practice", title
        return kind, event_title

    def annotate(self, ctx: VideoContext) -> None:
        self._base_playlists = list(ctx.playlists)
        kind, event_title = self.classify(ctx)
        if kind is None:
            return
        ctx.labels["tennis"] = kind
        ctx.labels["tennis_event"] = event_title
        ctx.tags += ["tennis", kind]
        if event_title:
            ctx.description = f"{event_title}\n{ctx.description}"
        if self.target in ("full", "both") or not self.rallycut:
            ctx.add_playlist(self.playlists[kind])
        log.info("tennis %s: %s", kind, event_title)

    def derive(self, ctx: VideoContext) -> list[Derivative]:
        kind = ctx.labels.get("tennis")
        if kind is None or not self.rallycut:
            return []
        segs = detect_rallies(ctx.local_path, self.rc)
        kept = sum(b - a for a, b in segs)
        ratio = kept / ctx.duration if ctx.duration else 0
        log.info("rallycut: %d rallies, %.0fs/%.0fs kept (%.0f%%)",
                 len(segs), kept, ctx.duration, ratio * 100)
        if not segs or ratio < self.rc.min_keep_ratio:
            log.warning("rallycut: detection looks unreliable, skipping cut version")
            if self.target == "cut":  # fall back so the video still lands in the playlist
                ctx.add_playlist(self.playlists[kind])
            return []
        if ratio > 0.95:
            log.info("rallycut: nothing meaningful to cut")
            return []
        out = ctx.work_dir / f"{ctx.local_path.stem}_rallycut.mp4"
        cut_video(ctx.local_path, segs, out, reencode=self.rc.reencode)
        playlists = list(self._base_playlists)
        if self.target in ("cut", "both"):
            playlists.append(self.playlists[kind])
        return [
            Derivative(
                key="rallycut",
                path=out,
                title=f"{ctx.title} (rally cut)",
                playlists=playlists,
                tags=ctx.tags + ["rallycut"],
            )
        ]
