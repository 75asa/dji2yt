import subprocess
import wave

import numpy as np

from dji2yt.media import probe
from dji2yt.plugins.tennis.rallycut import SR, cut_video, detect_rallies, group_rallies


def test_group_rallies_drops_singletons_and_merges():
    hits = [5, 6.5, 8, 30, 31, 32, 33.5, 50, 70, 71, 72]
    segs = group_rallies(hits, duration=80, max_gap=4, min_hits=3, pre=2, post=2.5)
    assert segs == [(3, 10.5), (28, 36.0), (68, 74.5)]


def test_group_rallies_merges_overlap():
    segs = group_rallies([1, 2, 3, 7.5, 8.5, 9.5], 20, max_gap=4, min_hits=3, pre=2, post=2.5)
    assert segs == [(0.0, 12.0)]


def _synth(tmp_path, hits, duration=60.0):
    rng = np.random.default_rng(0)
    n = int(duration * SR)
    audio = rng.normal(0, 0.01, n)  # background hiss
    # low-frequency "voices" that should be ignored
    t = np.arange(n) / SR
    audio += 0.05 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 0.1 * t) > 0.5)
    for h in hits:
        i = int(h * SR)
        click = rng.normal(0, 0.6, 400) * np.exp(-np.arange(400) / 60)
        audio[i : i + 400] += click
    wav = tmp_path / "a.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    mp4 = tmp_path / "v.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=green:s=320x180:r=30:d={duration}",
            "-i",
            str(wav),
            "-c:v",
            "libx264",
            "-g",
            "30",
            "-c:a",
            "aac",
            "-shortest",
            str(mp4),
        ],
        check=True,
    )
    return mp4


def test_end_to_end_detect_and_cut(tmp_path):
    hits = [5, 6.5, 8, 9.5, 25, 26.2, 27.4, 45]  # 2 rallies + a stray hit
    mp4 = _synth(tmp_path, hits)
    segs = detect_rallies(mp4)
    assert len(segs) == 2
    assert abs(segs[0][0] - 3) < 0.2 and abs(segs[0][1] - 12) < 0.2
    assert abs(segs[1][0] - 23) < 0.2 and abs(segs[1][1] - 29.9) < 0.2
    out = cut_video(mp4, segs, tmp_path / "cut.mp4")
    kept = sum(b - a for a, b in segs)
    assert abs(probe(out).duration - kept) < 2.5  # stream copy snaps to keyframes
