from __future__ import annotations

from pathlib import Path

import pytest

import tg_adder.__main__ as adder_main
import tg_filter.__main__ as filter_main
import tg_scraper.__main__ as scraper_main


def test_scraper_cli_parser() -> None:
    parser = scraper_main.build_parser()
    args = parser.parse_args(["-t", "@group1", "-t", "@group2", "--limit", "10", "--include-bots"])
    assert args.target == ["@group1", "@group2"]
    assert args.limit == 10
    assert args.include_bots is True

    # Missing required -t should exit
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_adder_cli_parser(tmp_path: Path) -> None:
    parser = adder_main.build_parser()
    csv_file = str(tmp_path / "test.csv")
    args = parser.parse_args(["-t", "@mygroup", "-f", csv_file, "--dry-run", "-d", "3.0"])
    assert args.target == "@mygroup"
    assert str(args.csv_path) == csv_file
    assert args.dry_run is True
    assert args.delay == 3.0

    # Missing required -f should exit
    with pytest.raises(SystemExit):
        parser.parse_args(["-t", "@mygroup"])


def test_filter_cli_parser(tmp_path: Path) -> None:
    parser = filter_main.build_parser()
    f1 = str(tmp_path / "f1.csv")
    args = parser.parse_args([f1, "--in-place"])
    assert len(args.paths) == 1
    assert args.in_place is True

    # Incompatible options check in main
    code = filter_main.main([f1, "-o", str(tmp_path / "out.csv"), "--in-place"])
    assert code == 2

    # Multiple files with -o check in main
    f2 = str(tmp_path / "f2.csv")
    code = filter_main.main([f1, f2, "-o", str(tmp_path / "out.csv")])
    assert code == 2
