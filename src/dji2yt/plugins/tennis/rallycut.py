"""Detect tennis rallies from ball-hit sounds and cut out the dead time.

Approach (numpy only, no heavy deps):
1. Decode mono audio with ffmpeg.
2. High-frequency spectral flux -> "transient strength" envelope (100 fps).
   Ball hits are short broadband pops, so they stand out above ~1.5 kHz
   while voices and wind mostly don't.
3. Peak-pick against a local adaptive threshold -> hit times.
4. Group hits whose gap <= ``max_gap`` into rallies, pad, merge.
5. Concatenate the kept ranges with ffmpeg's concat demuxer.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 16000
HOP = 160  # 10 ms
N_FFT = 512
FPS = SR / HOP


@dataclass
class RallyCutSettings:
    sensitivity: float = 10.0  # higher = fewer hits detected
    fmin_hz: float = 1500.0
    min_hit_gap: float = 0.25  # s, two hits can't be closer than this
    max_gap: float = 4.0  # s, hits further apart start a new rally
    min_hits: int = 3  # a rally needs at least this many hits (serve+return+1)
    pre: float = 2.0  # s kept before the first hit (toss / ready position)
    post: float = 2.5  # s kept after the last hit
    min_keep_ratio: float = 0.05  # if less than this is kept, assume detection failed
    reencode: bool = False  # True = frame-accurate cuts, much slower

    @classmethod
    def from_dict(cls, d: dict) -> RallyCutSettings:
        names = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in names})


# ---- audio ---------------------------------------------------------------
def load_audio(path: Path) -> np.ndarray:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SR),
            "-f",
            "s16le",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16)


def hit_envelope(audio: np.ndarray, fmin_hz: float = 1500.0) -> np.ndarray:
    """Positive high-band spectral flux per 10 ms frame."""
    n_frames = max(0, (len(audio) - N_FFT) // HOP + 1)
    if n_frames < 2:
        return np.zeros(max(n_frames, 0), dtype=np.float32)
    window = np.hanning(N_FFT).astype(np.float32)
    lo = int(fmin_hz / (SR / N_FFT))
    env = np.zeros(n_frames, dtype=np.float32)
    prev = None
    chunk = 6000  # frames per chunk (~60 s) to bound memory
    for start in range(0, n_frames, chunk):
        stop = min(n_frames, start + chunk)
        idx = np.arange(start, stop)[:, None] * HOP + np.arange(N_FFT)[None, :]
        frames = audio[idx].astype(np.float32) / 32768.0 * window
        mag = np.log1p(100.0 * np.abs(np.fft.rfft(frames, axis=1))[:, lo:])
        if prev is not None:
            mag_full = np.vstack([prev[None, :], mag])
        else:
            mag_full = np.vstack([mag[:1], mag])
        flux = np.maximum(mag_full[1:] - mag_full[:-1], 0.0).sum(axis=1)
        env[start:stop] = flux
        prev = mag[-1]
    return env


def _moving_mean(x: np.ndarray, w: int) -> np.ndarray:
    c = np.cumsum(np.concatenate([[0.0], x]))
    half = w // 2
    lo = np.clip(np.arange(len(x)) - half, 0, len(x))
    hi = np.clip(np.arange(len(x)) + half + 1, 0, len(x))
    return (c[hi] - c[lo]) / (hi - lo)


def pick_hits(env: np.ndarray, sensitivity: float = 10.0, min_gap: float = 0.25) -> np.ndarray:
    """Return hit times in seconds."""
    if len(env) == 0:
        return np.zeros(0)
    med = float(np.median(env))
    mad = float(np.median(np.abs(env - med))) or 1e-6
    local = _moving_mean(env, int(FPS))  # 1 s neighbourhood
    # must stand out both globally (vs. the noise floor) and locally (vs. the last second)
    thr = np.maximum(med + sensitivity * mad, 1.5 * local)
    w = max(1, int(min_gap * FPS))
    padded = np.pad(env, w, mode="constant", constant_values=-np.inf)
    local_max = np.lib.stride_tricks.sliding_window_view(padded, 2 * w + 1).max(axis=1)
    peaks = np.flatnonzero((env >= local_max) & (env > thr))
    # de-duplicate flat-topped peaks
    keep = []
    last = -np.inf
    for p in peaks:
        if p - last >= w:
            keep.append(p)
            last = p
    return np.asarray(keep, dtype=float) / FPS


# ---- segmentation --------------------------------------------------------
def group_rallies(
    hits: np.ndarray | list[float],
    duration: float,
    max_gap: float = 4.0,
    min_hits: int = 3,
    pre: float = 2.0,
    post: float = 2.5,
) -> list[tuple[float, float]]:
    hits = sorted(float(h) for h in hits)
    groups: list[list[float]] = []
    for h in hits:
        if groups and h - groups[-1][-1] <= max_gap:
            groups[-1].append(h)
        else:
            groups.append([h])
    segs = [
        (max(0.0, g[0] - pre), min(duration, g[-1] + post)) for g in groups if len(g) >= min_hits
    ]
    merged: list[tuple[float, float]] = []
    for a, b in segs:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def detect_rallies(path: Path, s: RallyCutSettings | None = None) -> list[tuple[float, float]]:
    s = s or RallyCutSettings()
    audio = load_audio(path)
    duration = len(audio) / SR
    env = hit_envelope(audio, s.fmin_hz)
    hits = pick_hits(env, s.sensitivity, s.min_hit_gap)
    return group_rallies(hits, duration, s.max_gap, s.min_hits, s.pre, s.post)


# ---- cutting -------------------------------------------------------------
def cut_video(
    src: Path, segments: list[tuple[float, float]], out: Path, reencode: bool = False
) -> Path:
    if not segments:
        raise ValueError("no segments to keep")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ffconcat", delete=False) as fh:
        fh.write("ffconcat version 1.0\n")
        src_escaped = str(src.resolve()).replace("'", r"'\''")
        for a, b in segments:
            fh.write(f"file '{src_escaped}'\ninpoint {a:.3f}\noutpoint {b:.3f}\n")
        listfile = fh.name
    codec = (
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k"]
        if reencode
        else ["-c", "copy"]
    )
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                listfile,
                *codec,
                "-avoid_negative_ts",
                "make_zero",
                "-movflags",
                "+faststart",
                str(out),
            ],
            check=True,
        )
    finally:
        Path(listfile).unlink(missing_ok=True)
    return out
