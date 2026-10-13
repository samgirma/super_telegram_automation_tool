"""Summarise the CSV files already sitting in the data folder."""

from __future__ import annotations

from tg_app import ui
from tg_common.storage import DataFileInfo, scan_data_dir

# Backward-compatibility alias
DataFile = DataFileInfo
scan = scan_data_dir


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


__all__ = ["DataFile", "render", "scan"]
