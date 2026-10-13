"""CSV persistence for scraped members and for adder attempt results."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

MEMBER_FIELDS = [
    "user_id",
    "username",
    "first_name",
    "last_name",
    "is_premium",
    "is_verified",
    "is_scam",
    "is_bot",
    "is_restricted",
    "status",
    "source",
    "source_id",
    "collected_at",
]

ADD_FIELDS = ["timestamp", "user_id", "username", "result", "detail"]

OK_RESULTS = {"sent", "request_sent", "already_member"}

# Outcomes that will never change on a rerun, so resuming must skip them.
TERMINAL_RESULTS = {
    "sent",
    "request_sent",
    "already_member",
    "privacy_restricted",
    "banned",
    "blocked",
    "is_bot",
    "no_username",
    "deactivated",
    "unreachable",
    "too_many_channels",
    "peer_flood",
    "status_deleted",
    "status_kicked",
    "status_restricted",
    "status_bot",
    "already_processed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class MemberRecord:
    user_id: int
    username: str
    first_name: str
    last_name: str
    is_premium: bool
    is_verified: bool
    is_scam: bool
    is_bot: bool
    is_restricted: bool
    status: str
    source: str
    source_id: int
    collected_at: str = field(default_factory=_now)

    @classmethod
    def from_user(cls, user, source: str, source_id: int) -> "MemberRecord":
        if getattr(user, "bot", False):
            status = "bot"
        elif getattr(user, "deleted", False):
            status = "deleted"
        elif getattr(user, "kicked", False):
            status = "kicked"
        elif getattr(user, "restricted", False):
            status = "restricted"
        else:
            status = "active"
        return cls(
            user_id=user.id,
            username=(user.username or "").lstrip("@"),
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            is_premium=bool(getattr(user, "premium", False)),
            is_verified=bool(getattr(user, "verified", False)),
            is_scam=bool(getattr(user, "scam", False)),
            is_bot=bool(getattr(user, "bot", False)),
            is_restricted=bool(getattr(user, "restricted", False)),
            status=status,
            source=source,
            source_id=source_id,
        )

    def to_row(self) -> dict:
        row = asdict(self)
        return {key: row[key] for key in MEMBER_FIELDS}


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


class MemberStore:
    """Append-only member CSV that merges into any existing file at the path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.records: dict[int, MemberRecord] = {}
        self.added = 0
        self.duplicates = 0

    def load(self) -> "MemberStore":
        if not self.path.exists():
            return self
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    record = MemberRecord(
                        user_id=int(row["user_id"]),
                        username=(row.get("username") or "").lstrip("@"),
                        first_name=row.get("first_name") or "",
                        last_name=row.get("last_name") or "",
                        is_premium=_as_bool(row.get("is_premium", "")),
                        is_verified=_as_bool(row.get("is_verified", "")),
                        is_scam=_as_bool(row.get("is_scam", "")),
                        is_bot=_as_bool(row.get("is_bot", "")),
                        is_restricted=_as_bool(row.get("is_restricted", "")),
                        status=row.get("status") or "",
                        source=row.get("source") or "",
                        source_id=int(row.get("source_id") or 0),
                        collected_at=row.get("collected_at") or _now(),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                self.records[record.user_id] = record
        return self

    def __contains__(self, user_id: int) -> bool:
        return user_id in self.records

    def __iter__(self) -> Iterator[MemberRecord]:
        return iter(self.records.values())

    def add(self, record: MemberRecord) -> bool:
        if record.user_id in self.records:
            self.duplicates += 1
            return False
        self.records[record.user_id] = record
        self.added += 1
        return True

    def add_all(self, records: Iterable[MemberRecord]) -> None:
        for record in records:
            self.add(record)

    def flush(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=MEMBER_FIELDS)
            writer.writeheader()
            for record in self.records.values():
                writer.writerow(record.to_row())
        return self.path


def filter_member_csv(
    path: Path,
    output: Path | None = None,
    in_place: bool = False,
) -> dict[str, int | Path]:
    """Rewrite a member CSV keeping only rows that have a username.

    Rows are de-duplicated by user_id, and member rows without a username are
    dropped, since a username is the only address the adder can use. The
    original file is backed up (``<name>.bak``) when overwriting in place.
    """
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"no such CSV: {source}")

    store = MemberStore(source).load()
    kept = [record for record in store if record.username.strip()]
    dropped = len(store.records) - len(kept)

    destination = source if in_place else Path(output) if output else source.with_name(
        f"{source.stem}.filtered{source.suffix}"
    )

    if in_place:
        backup = source.with_suffix(source.suffix + ".bak")
        backup.write_bytes(source.read_bytes())

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEMBER_FIELDS)
        writer.writeheader()
        for record in kept:
            writer.writerow(record.to_row())

    result: dict[str, int | Path] = {
        "read": len(store.records),
        "kept": len(kept),
        "dropped": dropped,
        "path": destination,
    }
    if in_place:
        result["backup"] = source.with_suffix(source.suffix + ".bak")
    return result


class AddLog:
    """Append-only log of invite attempts so runs can resume without re-adding."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.results: dict[int, str] = {}
        self.rows: list[dict] = []

    def load(self) -> "AddLog":
        if not self.path.exists():
            return self
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    self.results[int(row["user_id"])] = row.get("result", "")
                except (KeyError, TypeError, ValueError):
                    continue
        return self

    def should_attempt(self, user_id: int) -> bool:
        """Retry only transient failures; terminal outcomes are never repeated."""
        return self.results.get(user_id) not in TERMINAL_RESULTS

    def record(self, user_id: int, username: str, result: str, detail: str = "") -> None:
        row = {
            "timestamp": _now(),
            "user_id": user_id,
            "username": username,
            "result": result,
            "detail": detail,
        }
        self.rows.append(row)
        self.results[user_id] = result

    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for row in self.rows:
            tally[row["result"]] = tally.get(row["result"], 0) + 1
        return tally

    def write(self) -> Path:
        if not self.rows:
            return self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ADD_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerows(self.rows)
        return self.path
