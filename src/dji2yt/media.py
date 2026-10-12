"""ffprobe / ffmpeg helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ProbeResult:
    duration: float
    creation_time: datetime | None


def probe(path: Path) -> ProbeResult:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    fmt = json.loads(out).get("format", {})
    ct = fmt.get("tags", {}).get("creation_time")
    created = None
    if ct:
        try:
            created = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except ValueError:
            created = None
    return ProbeResult(duration=float(fmt.get("duration", 0.0)), creation_time=created)


def require_ffmpeg() -> None:
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        raise SystemExit(
            f"{', '.join(missing)} not found on PATH. Install with `brew install ffmpeg`."
        )
