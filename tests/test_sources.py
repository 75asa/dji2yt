import os
import time

from dji2yt.sources import LocalSource


def test_local_source_scans_subfolders_and_filters(tmp_path):
    day = tmp_path / "20261012"
    day.mkdir()
    old = time.time() - 3600
    for n in ["DJI_20261012110609_0113_D.MP4", "DJI_20261012110609_0113_D.LRF", ".hidden.MP4"]:
        (day / n).write_bytes(b"x")
        os.utime(day / n, (old, old))
    (day / "DJI_20261012123718_0115_D.MP4").write_bytes(b"x")  # fresh: still syncing

    src = LocalSource(tmp_path, (".mp4",), min_age_minutes=10)
    files = src.list()
    assert [f.name for f in files] == ["DJI_20261012110609_0113_D.MP4"]

    f = files[0]
    key = f.id
    src.rename(f, "2026-10-12_1106_DJI_20261012110609_0113_D.MP4")
    assert (day / "2026-10-12_1106_DJI_20261012110609_0113_D.MP4").exists()
    assert src.list()[0].id == key  # state key survives the rename
