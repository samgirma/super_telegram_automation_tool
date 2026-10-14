from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from tg_common.storage import (
    AddLog,
    MemberRecord,
    MemberStore,
    atomic_write,
    clean_username,
    filter_member_csv,
    scan_data_dir,
    slugify,
)


@dataclass
class DummyUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bot: bool = False
    deleted: bool = False
    kicked: bool = False
    restricted: bool = False
    premium: bool = False
    verified: bool = False
    scam: bool = False


def test_clean_username_and_slugify() -> None:
    assert clean_username("@alice") == "alice"
    assert clean_username("  bob  ") == "bob"
    assert clean_username(None) == ""

    assert slugify("@Cool Group!") == "cool_group"
    assert slugify("___") == "target"
    assert slugify("Group 123") == "group_123"


def test_member_record_from_user() -> None:
    user = DummyUser(
        id=101,
        username="@testuser",
        first_name="First",
        last_name="Last",
        premium=True,
    )
    rec = MemberRecord.from_user(user, source="Test Chat", source_id=202)
    assert rec.user_id == 101
    assert rec.username == "testuser"
    assert rec.first_name == "First"
    assert rec.last_name == "Last"
    assert rec.is_premium is True
    assert rec.status == "active"
    assert rec.source == "Test Chat"
    assert rec.source_id == 202

    row = rec.to_row()
    assert row["user_id"] == 101
    assert row["username"] == "testuser"
    assert row["is_premium"] is True


def test_member_record_statuses() -> None:
    bot = DummyUser(id=1, bot=True)
    assert MemberRecord.from_user(bot, "s", 0).status == "bot"

    deleted = DummyUser(id=2, deleted=True)
    assert MemberRecord.from_user(deleted, "s", 0).status == "deleted"

    kicked = DummyUser(id=3, kicked=True)
    assert MemberRecord.from_user(kicked, "s", 0).status == "kicked"

    restricted = DummyUser(id=4, restricted=True)
    assert MemberRecord.from_user(restricted, "s", 0).status == "restricted"


def test_atomic_write_success(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "output.txt"
    with atomic_write(target, mode="w", permissions=0o600) as handle:
        handle.write("hello atomic world")

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello atomic world"
    if os.name != "nt":
        mode = target.stat().st_mode & 0o777
        assert mode == 0o600


def test_atomic_write_cleanup_on_error(tmp_path: Path) -> None:
    target = tmp_path / "fail.txt"
    target.write_text("original", encoding="utf-8")

    with pytest.raises(RuntimeError):
        with atomic_write(target, mode="w") as handle:
            handle.write("new content")
            raise RuntimeError("disk boom")

    assert target.read_text(encoding="utf-8") == "original"
    # Ensure no leftover temporary files in directory
    tmps = list(tmp_path.glob(".*.tmp.*"))
    assert tmps == []


def test_member_store_crud_and_atomic_flush(tmp_path: Path) -> None:
    csv_file = tmp_path / "members.csv"
    store = MemberStore(csv_file)
    assert len(store) == 0

    rec1 = MemberRecord.from_user(DummyUser(id=10, username="user10"), "s", 1)
    rec2 = MemberRecord.from_user(DummyUser(id=20, username="user20"), "s", 1)

    assert store.add(rec1) is True
    assert store.add(rec1) is False
    assert store.duplicates == 1
    assert store.added == 1
    assert 10 in store
    assert 99 not in store

    store.add(rec2)
    assert len(store) == 2

    store.flush()
    assert csv_file.exists()

    # Reload from disk
    loaded = MemberStore(csv_file).load()
    assert len(loaded) == 2
    assert 10 in loaded
    assert 20 in loaded
    assert loaded.records[10].username == "user10"


def test_filter_member_csv_separate_output(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    store = MemberStore(source_csv)
    store.add(MemberRecord.from_user(DummyUser(id=1, username="has_user"), "s", 1))
    store.add(MemberRecord.from_user(DummyUser(id=2, username=""), "s", 1))
    store.flush()

    out_csv = tmp_path / "out.csv"
    res = filter_member_csv(source_csv, output=out_csv)

    assert res["read"] == 2
    assert res["kept"] == 1
    assert res["dropped"] == 1
    assert res["path"] == out_csv
    assert "backup" not in res

    filtered_store = MemberStore(out_csv).load()
    assert len(filtered_store) == 1
    assert 1 in filtered_store
    assert 2 not in filtered_store


def test_filter_member_csv_in_place(tmp_path: Path) -> None:
    source_csv = tmp_path / "group.csv"
    store = MemberStore(source_csv)
    store.add(MemberRecord.from_user(DummyUser(id=100, username="valid"), "s", 1))
    store.add(MemberRecord.from_user(DummyUser(id=200, username=None), "s", 1))
    store.flush()

    res = filter_member_csv(source_csv, in_place=True)
    assert res["kept"] == 1
    assert res["dropped"] == 1
    assert res["path"] == source_csv

    backup_path = res["backup"]
    assert isinstance(backup_path, Path)
    assert backup_path.exists()
    assert backup_path.name == "group.csv.bak"

    # Backup should contain both rows
    backup_store = MemberStore(backup_path).load()
    assert len(backup_store) == 2

    # In-place file should contain only valid row
    in_place_store = MemberStore(source_csv).load()
    assert len(in_place_store) == 1
    assert 100 in in_place_store


def test_filter_member_csv_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        filter_member_csv(tmp_path / "nonexistent.csv")


def test_add_log_lifecycle(tmp_path: Path) -> None:
    log_path = tmp_path / "adder_log.csv"
    log = AddLog(log_path).load()

    assert log.should_attempt(1) is True

    log.record(1, "alice", "sent", "invite sent")
    log.record(2, "bob", "banned", "user was banned")
    log.record(3, "carol", "error", "transient network failure")

    assert log.should_attempt(1) is False  # sent is terminal
    assert log.should_attempt(2) is False  # banned is terminal
    assert log.should_attempt(3) is True   # error is non-terminal, so retryable
    assert log.should_attempt(4) is True   # unseen

    counts = log.counts()
    assert counts["sent"] == 1
    assert counts["banned"] == 1
    assert counts["error"] == 1

    log.write()
    assert log_path.exists()

    # Reload log from disk and verify persisted results
    reloaded = AddLog(log_path).load()
    assert reloaded.should_attempt(1) is False
    assert reloaded.should_attempt(2) is False
    assert reloaded.should_attempt(3) is True


def test_scan_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Empty dir scan
    assert scan_data_dir(data_dir) == []

    # Create normal member CSV
    csv1 = data_dir / "group1.csv"
    store = MemberStore(csv1)
    store.add(MemberRecord.from_user(DummyUser(id=1, username="u1"), "s", 1))
    store.add(MemberRecord.from_user(DummyUser(id=2, username=""), "s", 1))
    store.flush()

    # Create adder log CSV (should be ignored by scan_data_dir)
    log_csv = data_dir / "adder_log_group1.csv"
    log = AddLog(log_csv)
    log.record(1, "u1", "sent")
    log.write()

    # Create non-csv file
    (data_dir / "notes.txt").write_text("hello", encoding="utf-8")

    files = scan_data_dir(data_dir)
    assert len(files) == 1
    item = files[0]
    assert item.name == "group1.csv"
    assert item.rows == 2
    assert item.with_username == 1
    assert item.blank == 1
