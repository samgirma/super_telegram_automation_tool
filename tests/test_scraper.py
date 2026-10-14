from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    FloodWaitError,
    UsernameNotOccupiedError,
)
from telethon.tl import types
from telethon.tl.types import channels as channel_types

from tg_common.config import Settings
from tg_common.storage import MemberRecord, MemberStore
from tg_scraper.scraper import ScrapeReport, _is_skippable, scrape


class FakeUser(types.User):
    def __init__(
        self,
        id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        bot: bool = False,
        deleted: bool = False,
        empty: bool = False,
    ) -> None:
        super().__init__(
            id=id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            bot=bot,
            deleted=deleted,
        )
        if empty:
            self.empty = True


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


def test_is_skippable() -> None:
    bot = FakeUser(id=1, username="bot_user", bot=True)
    assert _is_skippable(bot, include_bots=False) is True
    assert _is_skippable(bot, include_bots=True) is False

    deleted = FakeUser(id=2, username="deleted_user", deleted=True)
    assert _is_skippable(deleted, include_bots=False) is True

    no_user = FakeUser(id=3, username=None)
    assert _is_skippable(no_user, include_bots=False) is True

    valid = FakeUser(id=4, username="valid_user")
    assert _is_skippable(valid, include_bots=False) is False


def test_scrape_channel_success(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        channel = MagicMock(spec=types.Channel)
        channel.id = 999
        channel.title = "Target Group"

        users = [
            FakeUser(id=1, username="user1", first_name="User", last_name="One"),
            FakeUser(id=2, username="user2", first_name="User", last_name="Two"),
            FakeUser(id=3, username=None),  # should be skipped
            FakeUser(id=4, username="botuser", bot=True),  # bot skipped
        ]

        part_result = MagicMock(spec=channel_types.ChannelParticipants)
        part_result.users = users

        client.side_effect = [part_result]

        out_csv = tmp_path / "target.csv"
        progress_reports: list[tuple[int, int, int, int, int | None]] = []

        def on_progress(seen: int, new: int, dup: int, skipped: int, expected: int | None) -> None:
            progress_reports.append((seen, new, dup, skipped, expected))

        with (
            patch("tg_scraper.scraper.resolve", new_callable=AsyncMock, return_value=channel),
            patch("tg_scraper.scraper.participant_count", new_callable=AsyncMock, return_value=100),
        ):
            report = await scrape(
                client,
                dummy_settings,
                "@target",
                output=out_csv,
                limit=10,
                on_progress=on_progress,
            )

        assert isinstance(report, ScrapeReport)
        assert report.seen == 4
        assert report.new == 2
        assert report.skipped == 2
        assert report.duplicates == 0
        assert out_csv.exists()

        store = MemberStore(out_csv).load()
        assert len(store) == 2
        assert 1 in store
        assert 2 in store
        assert "user1" in [m.username for m in store]

    asyncio.run(run())


def test_scrape_deduplication(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        channel = MagicMock(spec=types.Channel)
        channel.id = 999
        channel.title = "Dedupe Group"

        out_csv = tmp_path / "dedupe.csv"
        existing_store = MemberStore(out_csv)
        existing_store.add(MemberRecord(
            user_id=1,
            username="user1",
            first_name="",
            last_name="",
            is_premium=False,
            is_verified=False,
            is_scam=False,
            is_bot=False,
            is_restricted=False,
            status="active",
            source="old",
            source_id=1,
        ))
        existing_store.flush()

        users = [
            FakeUser(id=1, username="user1"),  # duplicate
            FakeUser(id=2, username="user2"),  # new
        ]
        part_result = MagicMock(spec=channel_types.ChannelParticipants)
        part_result.users = users
        client.side_effect = [part_result]

        with (
            patch("tg_scraper.scraper.resolve", new_callable=AsyncMock, return_value=channel),
            patch("tg_scraper.scraper.participant_count", new_callable=AsyncMock, return_value=2),
        ):
            report = await scrape(client, dummy_settings, "@dedupe", output=out_csv)

        assert report.new == 1
        assert report.duplicates == 1

        store = MemberStore(out_csv).load()
        assert len(store) == 2

    asyncio.run(run())


def test_scrape_flood_wait_flushes_and_stops(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        channel = MagicMock(spec=types.Channel)
        channel.id = 999
        channel.title = "Flood Group"

        out_csv = tmp_path / "flood.csv"

        part_result = MagicMock(spec=channel_types.ChannelParticipants)
        part_result.users = [FakeUser(id=10, username="user10")]

        exc = FloodWaitError(request=None)
        exc.seconds = 300

        client.side_effect = [part_result, exc]

        with (
            patch("tg_scraper.scraper.PAGE_SIZE", 1),
            patch("tg_scraper.scraper.resolve", new_callable=AsyncMock, return_value=channel),
            patch("tg_scraper.scraper.participant_count", new_callable=AsyncMock, return_value=50),
            pytest.raises(RuntimeError) as exc_info,
        ):
            await scrape(client, dummy_settings, "@flood", output=out_csv)

        assert "300s flood wait" in str(exc_info.value)
        assert out_csv.exists()
        store = MemberStore(out_csv).load()
        assert 10 in store

    asyncio.run(run())


def test_scrape_chat_admin_required(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        channel = MagicMock(spec=types.Channel)
        channel.id = 999
        channel.title = "No Admin Group"

        exc = ChatAdminRequiredError(request=None)
        client.side_effect = exc

        with (
            patch("tg_scraper.scraper.resolve", new_callable=AsyncMock, return_value=channel),
            patch("tg_scraper.scraper.participant_count", new_callable=AsyncMock, return_value=50),
            pytest.raises(ValueError) as exc_info,
        ):
            await scrape(client, dummy_settings, "@noadmin", output=tmp_path / "out.csv")

        assert "need admin rights" in str(exc_info.value)

    asyncio.run(run())


def test_scrape_private_channel_error(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        exc = ChannelPrivateError(request=None)

        with (
            patch("tg_scraper.scraper.resolve", new_callable=AsyncMock, side_effect=exc),
            pytest.raises(ValueError) as exc_info,
        ):
            await scrape(client, dummy_settings, "@private", output=tmp_path / "out.csv")

        assert "is private" in str(exc_info.value)

    asyncio.run(run())


def test_scrape_username_unoccupied(dummy_settings: Settings, tmp_path: Path) -> None:
    async def run() -> None:
        client = AsyncMock()
        exc = UsernameNotOccupiedError(request=None)

        with (
            patch("tg_scraper.scraper.resolve", new_callable=AsyncMock, side_effect=exc),
            pytest.raises(ValueError) as exc_info,
        ):
            await scrape(client, dummy_settings, "@badusername", output=tmp_path / "out.csv")

        assert "cannot resolve" in str(exc_info.value)

    asyncio.run(run())
