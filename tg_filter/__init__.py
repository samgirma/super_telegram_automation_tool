"""Trim scraped member CSVs down to rows that have a username."""

from tg_common.storage import filter_member_csv

__all__ = ["filter_member_csv"]
