from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dji2yt.naming import is_prefixed, prefixed_name, resolve_shot_time, shot_time_from_name

JST = ZoneInfo("Asia/Tokyo")


def test_parse_new_dji_name():
    t = shot_time_from_name("DJI_20261012153012_0001_D.MP4", JST)
    assert t == datetime(2026, 10, 12, 15, 30, 12, tzinfo=JST)


def test_old_dji_name_falls_back_to_probe():
    probed = datetime(2026, 10, 12, 6, 30, tzinfo=timezone.utc)
    t = resolve_shot_time("DJI_0001.MP4", JST, probed=probed)
    assert t == datetime(2026, 10, 12, 15, 30, tzinfo=JST)


def test_prefix_is_idempotent():
    t = datetime(2026, 10, 12, 15, 30, tzinfo=JST)
    n = prefixed_name("DJI_20261012153012_0001_D.MP4", t)
    assert n == "2026-10-12_1530_DJI_20261012153012_0001_D.MP4"
    assert is_prefixed(n)
    assert prefixed_name(n, t) == n
    assert shot_time_from_name(n, JST).minute == 30
