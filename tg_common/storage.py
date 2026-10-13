"""CSV persistence for scraped members and for adder attempt results."""

from __future__ import annotations

import csv
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Iterable, Iterator

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

_UNSAFE = re.compile(r"[^a-z0-9_]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_username(text: str | None) -> str:
    """Strip leading @ and whitespace from a username."""
    return (text or "").strip().lstrip("@")


def slugify(text: str) -> str:
    """Convert arbitrary text into a safe filesystem slug."""
    cleaned = _UNSAFE.sub("_", clean_username(text).lower()).strip("_")
    return cleaned or "target"


@contextmanager
def atomic_write(
    target_path: Path,
    mode: str = "w",
    encoding: str = "utf-8",
    newline: str = "",
    permissions: int | None = None,
) -> Iterator[IO[Any]]:
    """Context manager for atomic file writes using a temporary file in the same directory.

    Flushes and syncs to disk before atomically replacing the destination with os.replace.
    Cleans up the temporary file if an exception is raised.
    """
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    prefix = f".{path.name}.tmp."
    temp_dir = path.parent

    is_binary = "b" in mode
    fd, temp_name = tempfile.mkstemp(prefix=prefix, dir=temp_dir)
    temp_path = Path(temp_name)

    if permissions is not None:
        if os.name != "nt":
            try:
                os.chmod(temp_path, permissions)
            except OSError:
                pass
    elif path.exists() and os.name != "nt":
        try:
            stat_res = path.stat()
            os.chmod(temp_path, stat_res.st_mode & 0o777)
        except OSError:
            pass
    elif os.name != "nt":
        try:
            current_umask = os.umask(0)
            os.umask(current_umask)
            os.chmod(temp_path, 0o666 & ~current_umask)
        except OSError:
            pass

    file_obj: IO[Any]
    if is_binary:
        file_obj = open(fd, mode=mode)
    else:
        file_obj = open(fd, mode=mode, encoding=encoding, newline=newline)

    try:
        yield file_obj
        file_obj.flush()
        os.fsync(file_obj.fileno())
        file_obj.close()
        os.replace(temp_path, path)
    except Exception:
        file_obj.close()
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


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
    def from_user(cls, user: Any, source: str, source_id: int) -> "MemberRecord":
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
            user_id=int(user.id),
            username=clean_username(getattr(user, "username", None)),
            first_name=getattr(user, "first_name", "") or "",
            last_name=getattr(user, "last_name", "") or "",
            is_premium=bool(getattr(user, "premium", False)),
            is_verified=bool(getattr(user, "verified", False)),
            is_scam=bool(getattr(user, "scam", False)),
            is_bot=bool(getattr(user, "bot", False)),
            is_restricted=bool(getattr(user, "restricted", False)),
            status=status,
            source=source,
            source_id=source_id,
        )

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        return {key: row[key] for key in MEMBER_FIELDS}


def _as_bool(value: Any) -> bool:
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
                        username=clean_username(row.get("username")),
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

    def __len__(self) -> int:
        return len(self.records)

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
        with atomic_write(self.path, mode="w", newline="", encoding="utf-8") as handle:
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

    destination = (
        source
        if in_place
        else Path(output)
        if output
        else source.with_name(f"{source.stem}.filtered{source.suffix}")
    )

    backup_path: Path | None = None
    if in_place:
        backup_path = source.with_suffix(source.suffix + ".bak")
        with atomic_write(backup_path, mode="wb") as handle:
            handle.write(source.read_bytes())

    with atomic_write(destination, mode="w", newline="", encoding="utf-8") as handle:
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
    if backup_path is not None:
        result["backup"] = backup_path
    return result


class AddLog:
    """Append-only log of invite attempts so runs can resume without re-adding."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.results: dict[int, str] = {}
        self.rows: list[dict[str, Any]] = []
        self._all_rows: list[dict[str, Any]] = []

    def load(self) -> "AddLog":
        if not self.path.exists():
            return self
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    user_id = int(row["user_id"])
                    result = row.get("result", "")
                    self.results[user_id] = result
                    self._all_rows.append(
                        {
                            "timestamp": row.get("timestamp") or _now(),
                            "user_id": user_id,
                            "username": clean_username(row.get("username")),
                            "result": result,
                            "detail": row.get("detail") or "",
                        }
                    )
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
            "username": clean_username(username),
            "result": result,
            "detail": detail,
        }
        self.rows.append(row)
        self._all_rows.append(row)
        self.results[user_id] = result

    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for row in self.rows:
            res = str(row["result"])
            tally[res] = tally.get(res, 0) + 1
        return tally

    def write(self) -> Path:
        """Atomically flush all logged attempts to disk."""
        if not self._all_rows:
            return self.path
        with atomic_write(self.path, mode="w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ADD_FIELDS)
            writer.writeheader()
            writer.writerows(self._all_rows)
        self.rows.clear()
        return self.path


@dataclass(frozen=True)
class DataFileInfo:
    path: Path
    rows: int
    with_username: int
    blank: int

    @property
    def name(self) -> str:
        return self.path.name


def scan_data_dir(data_dir: Path) -> list[DataFileInfo]:
    """Scan data directory for member CSV files and collect row counts."""
    if not data_dir.is_dir():
        return []
    found: list[DataFileInfo] = []
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
                    if clean_username(row.get("username")):
                        with_user += 1
        except (OSError, csv.Error):
            continue
        if rows == 0:
            continue
        found.append(
            DataFileInfo(
                path=path,
                rows=rows,
                with_username=with_user,
                blank=rows - with_user,
            )
        )
    return found


__all__ = [
    "ADD_FIELDS",
    "MEMBER_FIELDS",
    "OK_RESULTS",
    "TERMINAL_RESULTS",
    "AddLog",
    "DataFileInfo",
    "MemberRecord",
    "MemberStore",
    "atomic_write",
    "clean_username",
    "filter_member_csv",
    "scan_data_dir",
    "slugify",
]
