"""CLI: python -m tg_filter data/*.csv"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tg_common.storage import filter_member_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg_filter",
        description=(
            "Rewrite member CSVs keeping only rows that have a username. "
            "Rows without one can never be invited, so they are dropped."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="CSV",
        help="member CSV to filter, e.g. data/mygroup.csv",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write the result here. Only valid with a single CSV. "
        "Defaults to data/<name>.filtered.csv.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="overwrite the original after backing it up to <name>.csv.bak",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output and len(args.paths) > 1:
        print("error: -o/--output needs exactly one CSV", file=sys.stderr)
        return 2
    if args.output and args.in_place:
        print("error: choose one of -o/--output or --in-place", file=sys.stderr)
        return 2

    failures = 0
    try:
        for path in args.paths:
            try:
                result = filter_member_csv(
                    path, output=args.output, in_place=args.in_place
                )
            except (FileNotFoundError, ValueError) as exc:
                print(f"{path}: error: {exc}", file=sys.stderr)
                failures += 1
                continue
            line = (
                f"{path.name}: {result['read']} read, {result['kept']} kept, "
                f"{result['dropped']} dropped -> {result['path']}"
            )
            if "backup" in result:
                line += f" (backup: {result['backup']})"
            print(line)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    return 1 if failures else 0


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
