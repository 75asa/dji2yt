"""Configuration loading (TOML)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DriveConfig:
    folder_id: str
    rename_on_drive: bool = True
    extensions: tuple[str, ...] = (".mp4",)


@dataclass
class YouTubeConfig:
    privacy: str = "unlisted"
    # Playlist every upload goes into. Formatted with `shot_at` (datetime).
    # Set to "" to disable. e.g. "{shot_at:%Y-%m-%d} DJI" or "DJI"
    playlist_template: str = "{shot_at:%Y-%m-%d} DJI"
    playlist_privacy: str = "unlisted"
    category_id: str = "17"  # Sports
    description_template: str = "Shot at {shot_at:%Y-%m-%d %H:%M}\nOriginal: {original_name}"
    max_uploads_per_run: int = 5


@dataclass
class Config:
    drive: DriveConfig
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    timezone: str = "Asia/Tokyo"
    work_dir: Path = Path("work")
    state_path: Path = Path("state.db")
    client_secret_path: Path = Path("client_secret.json")
    token_path: Path = Path("token.json")
    plugins_enabled: list[str] = field(default_factory=list)
    plugin_settings: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_config(path: str | Path) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    base = Path(path).resolve().parent

    def p(key: str, default: str) -> Path:
        v = Path(raw.get(key, default))
        return v if v.is_absolute() else base / v

    drive_raw = raw["drive"]
    drive = DriveConfig(
        folder_id=drive_raw["folder_id"],
        rename_on_drive=drive_raw.get("rename_on_drive", True),
        extensions=tuple(e.lower() for e in drive_raw.get("extensions", [".mp4"])),
    )
    youtube = YouTubeConfig(**raw.get("youtube", {}))

    plugins_raw = dict(raw.get("plugins", {}))
    enabled = plugins_raw.pop("enabled", [])
    return Config(
        drive=drive,
        youtube=youtube,
        timezone=raw.get("timezone", "Asia/Tokyo"),
        work_dir=p("work_dir", "work"),
        state_path=p("state_path", "state.db"),
        client_secret_path=p("client_secret_path", "client_secret.json"),
        token_path=p("token_path", "token.json"),
        plugins_enabled=list(enabled),
        plugin_settings={k: v for k, v in plugins_raw.items() if isinstance(v, dict)},
    )
