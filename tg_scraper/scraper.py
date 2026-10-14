"""Participant enumeration and CSV export."""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl import functions, types
from telethon.tl.types import channels as channel_types

from tg_common.client import participant_count, resolve
from tg_common.config import Settings
from tg_common.storage import MemberRecord, MemberStore, clean_username, slugify

# Telegram returns at most 200 participants per GetParticipants call.
PAGE_SIZE = 200

# Rows buffered before an atomic write to disk. Small enough that a crash loses little.
FLUSH_EVERY = 500

# Members read between progress reports. Independent of FLUSH_EVERY so a
# caller watching progress sees movement even when few rows are new.
REPORT_EVERY = PAGE_SIZE

# Consecutive pages without new rows before we assume Telegram has stopped
# returning usable results. Guards against endless paging loops.
MAX_STALL_PAGES = 3

ProgressCallback = Callable[[int, int, int, int, int | None], None]


@dataclass
class ScrapeReport:
    source: str
    source_id: int
    seen: int
    new: int
    duplicates: int
    skipped: int
    expected: int | None
    path: Path
    seconds: float
    stopped_early: bool = False

    @property
    def coverage(self) -> float | None:
        if not self.expected:
            return None
        return min(self.seen / self.expected, 1.0)

    @property
    def rate(self) -> float:
        return self.seen / self.seconds if self.seconds > 0 else 0.0

    def summary(self) -> str:
        line = (
            f"{self.source}: {self.new} new, {self.duplicates} already known, "
            f"{self.skipped} without a usable username "
            f"({self.seen} read in {self.seconds:.1f}s, {self.rate:.0f}/s)"
        )
        if self.coverage is not None:
            line += f", {self.coverage:.0%} of {self.expected} reported members"
        else:
            line += ", total member count unavailable"
        if self.stopped_early:
            line += " [ended early: Telegram stopped returning results]"
        return line


def _is_skippable(user: Any, include_bots: bool) -> bool:
    if getattr(user, "bot", False):
        return not include_bots
    if getattr(user, "deleted", False):
        return True
    return not clean_username(getattr(user, "username", None))


async def _iter_channel_users(
    client: TelegramClient,
    channel: Any,
    search: str | None,
    delay: float,
) -> AsyncIterator[types.User]:
    """Page a channel or megagroup with GetParticipants.

    Telethon's own iter_participants pages internally, so a delay has to be
    applied here instead in order to land once per request rather than once per
    member. With PAGE_SIZE=200 that is the difference between a scrape taking
    seconds and taking hours.
    """
    offset = 0
    stalled = 0
    while True:
        request = functions.channels.GetParticipantsRequest(
            channel=channel,
            filter=types.ChannelParticipantsSearch(search or ""),
            offset=offset,
            limit=PAGE_SIZE,
            hash=0,
        )
        result = await client(request)

        if isinstance(result, channel_types.ChannelParticipantsNotModified):
            return

        page = (
            getattr(result, "users", [])
            if isinstance(result, channel_types.ChannelParticipants)
            else []
        )

        fresh = 0
        for user in page:
            if isinstance(user, types.User) and not getattr(user, "empty", False):
                fresh += 1
                yield user

        offset += len(page)
        if delay > 0:
            await asyncio.sleep(delay)
        if len(page) < PAGE_SIZE:
            return
        if fresh == 0:
            stalled += 1
            if stalled >= MAX_STALL_PAGES:
                return
        else:
            stalled = 0


async def _iter_chat_users(client: TelegramClient, chat: Any) -> AsyncIterator[types.User]:
    """Yield users of a legacy basic group.

    Basic groups have no paged GetParticipants request, so the full chat is
    fetched once and the user list is taken from it.
    """
    full = await client(functions.messages.GetFullChatRequest(chat.id))
    for user in getattr(full, "users", []) or []:
        if isinstance(user, types.User) and not getattr(user, "empty", False):
            yield user


async def _iter_users(
    client: TelegramClient,
    entity: Any,
    search: str | None,
    delay: float,
) -> AsyncIterator[types.User]:
    if isinstance(entity, types.Channel):
        async for user in _iter_channel_users(client, entity, search, delay):
            yield user
    else:
        async for user in _iter_chat_users(client, entity):
            yield user


async def scrape(
    client: TelegramClient,
    settings: Settings,
    source: str,
    output: Path | None = None,
    include_bots: bool = False,
    limit: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> ScrapeReport:
    try:
        entity = await resolve(client, source)
    except (UsernameNotOccupiedError, UsernameInvalidError) as exc:
        raise ValueError(f"cannot resolve {source!r}: {exc}") from exc
    except ChannelPrivateError as exc:
        raise ValueError(
            f"{source!r} is private. Your account must already be a member to read it."
        ) from exc

    source_title = getattr(entity, "title", None) or slugify(source)
    source_id = entity.id
    expected = await participant_count(client, entity)

    target = Path(output) if output else settings.data_dir / f"{slugify(source_title)}.csv"
    store = MemberStore(target).load()
    initial_count = len(store)

    # Channels need a non-empty search filter to page past the first chunk.
    search = "" if isinstance(entity, types.Channel) else None
    delay = settings.scrape_delay

    seen = 0
    new = 0
    duplicates = 0
    skipped = 0
    unflushed = 0
    last_report = 0
    started = time.monotonic()

    def report() -> None:
        elapsed = time.monotonic() - started
        if on_progress is not None:
            on_progress(seen, new, duplicates, skipped, expected)
        else:
            print(
                f"  {seen} read, {new} new, {duplicates} known, "
                f"{seen / max(elapsed, 1e-6):.0f}/s"
                + (f" of ~{expected}" if expected else ""),
                file=sys.stderr,
            )

    try:
        async for user in _iter_users(client, entity, search, delay):
            seen += 1
            if _is_skippable(user, include_bots):
                skipped += 1
            elif user.id in store:
                duplicates += 1
            else:
                record = MemberRecord.from_user(user, source_title, source_id)
                if store.add(record):
                    new += 1
                    unflushed += 1

            if unflushed >= FLUSH_EVERY:
                store.flush()
                unflushed = 0

            # Report on read count, not on new rows, so a group full of
            # already-known or unaddressable members still shows movement.
            if seen - last_report >= REPORT_EVERY:
                last_report = seen
                report()

            if limit is not None and seen >= limit:
                break
    except ChatAdminRequiredError as exc:
        raise ValueError(
            f"need admin rights in {source_title!r} to list its members"
        ) from exc
    except FloodWaitError as exc:
        raise RuntimeError(
            f"Telegram asked for a {exc.seconds}s flood wait partway through "
            f"{source_title!r}. Progress so far was saved to {target}; rerun to resume."
        ) from exc
    finally:
        # Guarantee that all pending members are atomically written to disk on
        # completion, error, or user interruption (Ctrl-C).
        if unflushed > 0 or (initial_count == 0 and len(store) > 0 and not target.exists()):
            store.flush()

    seconds = time.monotonic() - started
    if seen and seen != last_report:
        report()

    return ScrapeReport(
        source=source_title,
        source_id=source_id,
        seen=seen,
        new=new,
        duplicates=duplicates,
        skipped=skipped,
        expected=expected,
        path=target,
        seconds=seconds,
        stopped_early=bool(expected and seen < expected * 0.5 and seen > 0),
    )


__all__ = ["ScrapeReport", "scrape"]
