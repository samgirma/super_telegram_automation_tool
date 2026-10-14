from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telethon.errors import (
    FloodWaitError,
    PeerFloodError,
    UserAlreadyParticipantError,
    UserPrivacyRestrictedError,
)
from telethon.tl import types

from tg_adder.adder import (
    AddReport,
    _classify,
    _eligible,
    add_members,
)
from tg_common.config import Settings
from tg_common.storage import AddLog, MemberRecord, MemberStore


@pytest.fixture
def dummy_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_id=123,
        api_hash="hash",
        phone="+123456",
        data_dir=tmp_path / "data",
        add_delay=0.0,
        scrape_delay=0.0,
        flood_sleep_threshold=0,
    )


def test_classify_errors() -> None:
    res, detail = _classify(UserAlreadyParticipantError(request=None))
    assert res == "already_member"

    res, detail = _classify(UserPrivacyRestrictedError(request=None))
    assert res == "privacy_restricted"

    res, detail = _classify(PeerFloodError(request=None))
    assert res == "peer_flood"

    res, detail = _classify(Exception("unknown"))
    assert res == "error"


def test_eligible_filter() -> None:
    valid = MemberRecord(1, "alice", "", "", False, False, False, False, False, "active", "s", 1)
    assert _eligible(valid, include_bots=False) == ""

    no_user = MemberRecord(2, "", "", "", False, False, False, False, False, "active", "s", 1)
    assert _eligible(no_user, include_bots=False) == "no_username"

    bot = MemberRecord(3, "bot", "", "", False, False, False, True, False, "bot", "s", 1)
    assert _eligible(bot, include_bots=False) == "is_bot"
    assert _eligible(bot, include_bots=True) == ""

    deleted = MemberRecord(4, "del", "", "", False, False, False, False, False, "deleted", "s", 1)
    assert _eligible(deleted, include_bots=False) == "status_deleted"


def test_add_members_dry_run(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = MagicMock()
        channel = MagicMock(spec=types.Channel)
        channel.megagroup = True
        channel.title = "Target Group"

        csv_path = tmp_path / "members.csv"
        store = MemberStore(csv_path)
        store.add(MemberRecord(1, "user1", "", "", False, False, False, False, False, "active", "s", 1))
        store.add(MemberRecord(2, "user2", "", "", False, False, False, False, False, "active", "s", 1))
        store.flush()

        with patch("tg_adder.adder.resolve", new_callable=AsyncMock, return_value=channel):
            report = await add_members(
                client,
                dummy_settings,
                "@target",
                csv_path,
                dry_run=True,
            )

        assert isinstance(report, AddReport)
        assert report.dry_run is True
        assert report.attempted == 2
        assert report.counts.get("would_send") == 2
        # In dry run, client is never invoked
        assert client.call_count == 0

    asyncio.run(run())


def test_add_members_success_and_logging(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        channel = MagicMock(spec=types.Channel)
        channel.megagroup = True
        channel.title = "Target Group"

        csv_path = tmp_path / "members.csv"
        store = MemberStore(csv_path)
        store.add(MemberRecord(1, "user1", "", "", False, False, False, False, False, "active", "s", 1))
        store.add(MemberRecord(2, "user2", "", "", False, False, False, False, False, "active", "s", 1))
        store.flush()

        log_path = tmp_path / "adder_log.csv"

        attempts: list[tuple[int, MemberRecord, str, str]] = []

        def on_attempt(attempted: int, record: MemberRecord, result: str, detail: str) -> None:
            attempts.append((attempted, record, result, detail))

        with patch("tg_adder.adder.resolve", new_callable=AsyncMock, return_value=channel):
            report = await add_members(
                client,
                dummy_settings,
                "@target",
                csv_path,
                log_path=log_path,
                on_attempt=on_attempt,
            )

        assert report.attempted == 2
        assert report.counts.get("sent") == 2
        assert len(attempts) == 2
        assert log_path.exists()

        log = AddLog(log_path).load()
        assert log.should_attempt(1) is False
        assert log.should_attempt(2) is False

    asyncio.run(run())


def test_add_members_peer_flood_hard_stop(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        channel = MagicMock(spec=types.Channel)
        channel.megagroup = True
        channel.title = "Flood Group"

        csv_path = tmp_path / "members.csv"
        store = MemberStore(csv_path)
        store.add(MemberRecord(1, "user1", "", "", False, False, False, False, False, "active", "s", 1))
        store.add(MemberRecord(2, "user2", "", "", False, False, False, False, False, "active", "s", 1))
        store.flush()

        log_path = tmp_path / "adder_log.csv"

        # Simulate PeerFloodError on first user
        client.side_effect = PeerFloodError(request=None)

        notifications: list[str] = []

        with patch("tg_adder.adder.resolve", new_callable=AsyncMock, return_value=channel):
            report = await add_members(
                client,
                dummy_settings,
                "@target",
                csv_path,
                log_path=log_path,
                notify=notifications.append,
            )

        # Must stop immediately after 1 attempt, skipping user 2
        assert report.attempted == 1
        assert report.counts.get("peer_flood") == 1
        assert report.stopped_reason is not None
        assert "PEER_FLOOD" in report.stopped_reason
        assert len(notifications) == 1

        # Attempt must be recorded in log
        log = AddLog(log_path).load()
        assert log.should_attempt(1) is False
        assert log.should_attempt(2) is True  # never attempted

    asyncio.run(run())


def test_add_members_flood_wait_hard_stop(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        channel = MagicMock(spec=types.Channel)
        channel.megagroup = True
        channel.title = "FloodWait Group"

        csv_path = tmp_path / "members.csv"
        store = MemberStore(csv_path)
        store.add(MemberRecord(1, "user1", "", "", False, False, False, False, False, "active", "s", 1))
        store.add(MemberRecord(2, "user2", "", "", False, False, False, False, False, "active", "s", 1))
        store.flush()

        log_path = tmp_path / "adder_log.csv"

        exc = FloodWaitError(request=None)
        exc.seconds = 120
        client.side_effect = exc

        notifications: list[str] = []

        with patch("tg_adder.adder.resolve", new_callable=AsyncMock, return_value=channel):
            report = await add_members(
                client,
                dummy_settings,
                "@target",
                csv_path,
                log_path=log_path,
                notify=notifications.append,
            )

        assert report.attempted == 1
        assert report.counts.get("flood_wait") == 1
        assert report.stopped_reason is not None
        assert "120s" in report.stopped_reason

        log = AddLog(log_path).load()
        # flood_wait is logged
        assert 1 in log.results

    asyncio.run(run())
