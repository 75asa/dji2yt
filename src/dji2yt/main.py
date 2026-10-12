"""CLI entry point."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dji2yt")
    ap.add_argument("-c", "--config", default="config.toml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="OAuth login (opens a browser) and save token")

    run = sub.add_parser("run", help="process new videos once")
    run.add_argument("--dry-run", action="store_true", help="no rename/upload/state writes")
    run.add_argument("--limit", type=int)

    sub.add_parser("plugins", help="list installed plugins")

    rc = sub.add_parser("rallycut", help="detect rallies in a local file (for tuning)")
    rc.add_argument("file", type=Path)
    rc.add_argument("--out", type=Path, help="also write the cut video here")

    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)

    if args.cmd == "plugins":
        from .plugins import available_plugins

        for name, cls in sorted(available_plugins().items()):
            print(f"{name}\t{cls.__module__}.{cls.__qualname__}")
        return

    if args.cmd == "rallycut":
        from .plugins.tennis.rallycut import RallyCutSettings, cut_video, detect_rallies

        s = RallyCutSettings()
        segs = detect_rallies(args.file, s)
        total = sum(b - a for a, b in segs)
        for i, (a, b) in enumerate(segs, 1):
            print(f"{i:3d}  {a:8.1f} - {b:8.1f}  ({b - a:5.1f}s)")
        print(f"{len(segs)} rallies, {total:.0f}s kept")
        if args.out:
            cut_video(args.file, segs, args.out)
            print(f"wrote {args.out}")
        return

    from .config import load_config

    cfg = load_config(args.config)

    if args.cmd == "auth":
        from .auth import run_login

        run_login(cfg.client_secret_path, cfg.token_path)
        print(f"saved {cfg.token_path}")
        return

    if args.cmd == "run":
        from .pipeline import Pipeline

        Pipeline(cfg, dry_run=args.dry_run).run(limit=args.limit)


if __name__ == "__main__":
    main()
