"""Summarise the CSV files already sitting in the data folder."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from tg_app import ui


@dataclass
class DataFile:
    path: Path
    rows: int
    with_username: int
    blank: int

    @property
    def name(self) -> str:
        return self.path.name


def scan(data_dir: Path) -> list[DataFile]:
    if not data_dir.is_dir():
        return []
    found: list[DataFile] = []
    for path in sorted(data_dir.glob("*.csv")):
        if path.name.startswith("adder_log_"):
            continue
        rows = with_user = 0
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or "username" not in reader.fieldnames:
                    continue
                for row in reader:
                    rows += 1
                    if (row.get("username") or "").strip():
                        with_user += 1
        except (OSError, csv.Error):
            continue
        if rows == 0:
            continue
        found.append(
            DataFile(
                path=path,
                rows=rows,
                with_username=with_user,
                blank=rows - with_user,
            )
        )
    return found


def render(files: list[DataFile]) -> None:
    print()
    if not files:
        print(ui.step("No scraped data yet. Run a scrape to create one."))
        return
    print(ui.step("Your saved data:"))
    print()
    total = 0
    for index, item in enumerate(files, start=1):
        total += item.with_username
        keytxt = ui.c(f"{index:>3} ", ui.BLACK, ui.BOLD, "\033[48;5;208m")
        usable = ui.c(f"{item.with_username:,} usable", ui.GREEN, ui.BOLD)
        line = (
            f"  {keytxt} {ui.c(item.name, ui.WHITE, ui.BOLD)}  "
            f"{ui.c(str(item.rows) + ' rows', ui.GREY)}, {usable}"
        )
        if item.blank:
            line += ui.c(f"  ({item.blank:,} without a username)", ui.GREY)
        print(line)
    print()
    print(ui.step(f"Total usable members across all files: {ui.c(f'{total:,}', ui.CYAN, ui.BOLD)}"))
