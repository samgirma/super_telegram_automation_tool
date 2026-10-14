"""CLI: python -m tg_scraper -t @group"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from tg_common.client import connect
from tg_common.config import ConfigError, load_settings
from tg_scraper.scraper import scrape


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg_scraper",
        description="Scrape Telegram group or channel members into a CSV in data/.",
    )
    parser.add_argument(
        "-t",
        "--target",
        action="append",
        required=True,
        metavar="GROUP",
        help="group or channel to scrape. Repeat for several. @username, invite link or id.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="CSV path. Defaults to data/<group name>.csv. Existing rows are kept and deduped.",
    )
    parser.add_argument(
        "--session",
        default="scraper",
        help="session name, cached to data/<session>.session (default: scraper)",
    )
    parser.add_argument(
        "--include-bots",
        action="store_true",
        help="keep bots in the CSV. Bots are skipped by default.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="stop after reading this many members (default: no limit)",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = await connect(settings, args.session)
    failures = 0
    try:
        for target in args.target:
            try:
                report = await scrape(
                    client,
                    settings,
                    target,
                    output=args.output,
                    include_bots=args.include_bots,
                    limit=args.limit,
                )
            except (ValueError, RuntimeError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                failures += 1
                continue
            print(report.summary())
            print(f"  -> {report.path}")
    finally:
        await client.disconnect()
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted. Progress so far was saved to disk.", file=sys.stderr)
        return 130


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
