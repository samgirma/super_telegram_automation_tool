"""CLI: python -m tg_adder -t @channel --from data/group.csv"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from tg_common.config import ConfigError, load_settings
from tg_common.client import connect
from tg_adder.adder import add_members


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg_adder",
        description="Add members from a scraped CSV to a Telegram group.",
    )
    parser.add_argument(
        "-t",
        "--target",
        required=True,
        metavar="GROUP",
        help="group to add members to. Must be a megagroup you administer.",
    )
    parser.add_argument(
        "-f",
        "--from",
        dest="csv_path",
        type=Path,
        required=True,
        help="CSV produced by tg_scraper, e.g. data/mygroup.csv",
    )
    parser.add_argument(
        "--session",
        default="adder",
        help="session name, cached to data/<session>.session (default: adder)",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        help="seconds between invites. Defaults to TG_ADD_DELAY (5).",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        help="stop after this many invite attempts",
    )
    parser.add_argument(
        "--include-bots",
        action="store_true",
        help="also try to add bots, which always fail. Off by default.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without sending any invites",
    )
    parser.add_argument(
        "--log",
        type=Path,
        help="attempt log path. Defaults to data/adder_log_<group>.csv",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = await connect(settings, args.session)
    try:
        report = await add_members(
            client,
            settings,
            args.target,
            args.csv_path,
            delay=args.delay,
            limit=args.limit,
            include_bots=args.include_bots,
            dry_run=args.dry_run,
            log_path=args.log,
        )
    finally:
        await client.disconnect()
    print(report.summary())
    print(f"  log -> {report.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted. Rerun to resume where you left off.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
