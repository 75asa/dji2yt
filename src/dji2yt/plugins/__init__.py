"""Plugin API.

A plugin is a subclass of :class:`Plugin` registered under the
``dji2yt.plugins`` entry-point group (built-ins are registered in
``pyproject.toml`` the same way third-party plugins would be).

Lifecycle per video::

    setup(settings, services)          once per run
    annotate(ctx)                      classify / add playlists, tags, title tweaks
    derive(ctx) -> [Derivative]        produce extra videos (e.g. a rally cut)
    after_upload(ctx, uploads)         react to final YouTube IDs

Plugins run in the order listed in ``[plugins] enabled``; later plugins see
what earlier ones wrote to ``ctx``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "dji2yt.plugins"


@dataclass
class Services:
    """Authenticated Google API clients, shared with plugins."""

    drive: Any
    youtube: Any
    calendar: Any
    tz: Any


@dataclass
class Derivative:
    """An extra video produced by a plugin, uploaded alongside the original."""

    key: str  # unique per plugin, e.g. "rallycut"
    path: Path
    title: str
    description: str = ""
    playlists: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class VideoContext:
    drive_id: str
    original_name: str
    name: str  # date-prefixed name
    local_path: Path
    shot_at: datetime
    duration: float
    title: str
    description: str
    work_dir: Path
    playlists: list[str] = field(default_factory=list)  # for the original upload
    tags: list[str] = field(default_factory=list)
    labels: dict[str, Any] = field(default_factory=dict)  # free-form, shared between plugins

    def add_playlist(self, title: str) -> None:
        if title and title not in self.playlists:
            self.playlists.append(title)


class Plugin:
    name: str = "base"

    def setup(self, settings: dict[str, Any], services: Services) -> None:
        self.settings = settings
        self.services = services

    def annotate(self, ctx: VideoContext) -> None:  # noqa: B027
        pass

    def derive(self, ctx: VideoContext) -> list[Derivative]:
        return []

    def after_upload(self, ctx: VideoContext, uploads: dict[str, str]) -> None:  # noqa: B027
        """``uploads`` maps "main" / "<plugin>:<key>" to YouTube video IDs."""


def available_plugins() -> dict[str, type[Plugin]]:
    found: dict[str, type[Plugin]] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            cls = ep.load()
        except Exception as e:  # a broken third-party plugin must not kill the run
            log.error("failed to load plugin %s: %s", ep.name, e)
            continue
        found[ep.name] = cls
    return found


def load_plugins(
    enabled: list[str], settings: dict[str, dict[str, Any]], services: Services
) -> list[Plugin]:
    registry = available_plugins()
    plugins: list[Plugin] = []
    for name in enabled:
        if name not in registry:
            raise SystemExit(f"plugin '{name}' not found. Installed: {sorted(registry)}")
        plugin = registry[name]()
        plugin.name = name
        plugin.setup(settings.get(name, {}), services)
        plugins.append(plugin)
    return plugins
