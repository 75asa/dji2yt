from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dji2yt.plugins import Services, VideoContext
from dji2yt.plugins.tennis import TennisPlugin

JST = ZoneInfo("Asia/Tokyo")


class FakeCalendar:
    def __init__(self, events):
        # events: list of title strings or (title, location) tuples
        self.events = [e if isinstance(e, tuple) else (e, "") for e in events]

    def events(self):
        return self

    def list(self, **kw):
        self.kw = kw
        return self

    def execute(self):
        return {"items": [{"summary": t, "location": loc} for t, loc in self.events]}


def _ctx():
    return VideoContext(
        drive_id="x", original_name="a.mp4", name="a.mp4", local_path=Path("a.mp4"),
        shot_at=datetime(2026, 10, 12, 10, 0, tzinfo=JST), duration=3600,
        title="a", description="", work_dir=Path("."), playlists=["2026-10-12 DJI"],
    )


def _plugin(titles, **settings):
    p = TennisPlugin()
    p.name = "tennis"
    p.setup(settings, Services(None, None, FakeCalendar(titles), JST))
    return p


def test_match_beats_practice():
    p = _plugin(["テニス部", ("関西庭球部実業団 vs 小野薬品＠くにじま#11-12", "くにじまテニスコート")],
                playlist_target="full")
    ctx = _ctx()
    p.annotate(ctx)
    assert ctx.labels["tennis"] == "match"
    assert ctx.playlists == ["2026-10-12 DJI", "MyTennisMatch"]


def test_practice_with_cut_target_keeps_full_out_of_tennis_playlist():
    p = _plugin([("いぬねこ@伏見港#3", "伏見港公園 テニスコート")])
    ctx = _ctx()
    p.annotate(ctx)
    assert ctx.labels["tennis"] == "practice"
    assert ctx.playlists == ["2026-10-12 DJI"]


def test_not_tennis():
    p = _plugin(["歯医者", ("vs 打ち合わせ", "会議室")])
    ctx = _ctx()
    p.annotate(ctx)
    assert "tennis" not in ctx.labels
