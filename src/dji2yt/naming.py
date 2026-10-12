"""Shot-time detection and date-prefixed naming."""

from __future__ import annotations

import re
from datetime import datetime, tzinfo

# e.g. DJI_20261012153000_0001_D.MP4 / DJI_20261012_153000.MP4
_DJI_TS = re.compile(r"(20\d{2})(\d{2})(\d{2})_?(\d{2})(\d{2})(\d{2})")
_PREFIXED = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}_")


def is_prefixed(name: str) -> bool:
    return bool(_PREFIXED.match(name))


def strip_prefix(name: str) -> str:
    return _PREFIXED.sub("", name)


def shot_time_from_name(name: str, tz: tzinfo) -> datetime | None:
    m = _DJI_TS.search(strip_prefix(name))
    if not m:
        return None
    try:
        return datetime(*map(int, m.groups()), tzinfo=tz)  # camera clock = local time
    except ValueError:
        return None


def resolve_shot_time(
    name: str,
    tz: tzinfo,
    probed: datetime | None = None,
    fallback: datetime | None = None,
) -> datetime:
    """Filename timestamp > container creation_time > Drive createdTime."""
    for candidate in (shot_time_from_name(name, tz), probed, fallback):
        if candidate is not None:
            return candidate.astimezone(tz)
    raise ValueError(f"cannot determine shot time for {name}")


def prefixed_name(name: str, shot_at: datetime) -> str:
    return f"{shot_at:%Y-%m-%d_%H%M}_{strip_prefix(name)}"
