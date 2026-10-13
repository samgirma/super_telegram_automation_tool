"""Participant enumeration and CSV export."""

from __future__ import annotations

import asyncio
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    ChatAdminRequiredError,
    ChannelPrivateError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl import functions, types
from telethon.tl.types import channels as channel_types

from tg_common.client import participant_count, resolve
from tg_common.config import Settings
from tg_common.storage import MEMBER_FIELDS, MemberRecord, MemberStore

_UNSAFE = re.compile(r"[^a-z0-9_]+")

# Telegram returns at most 200 participants per GetParticipants call.
PAGE_SIZE = 200

# Rows buffered before a write to disk. Small enough that a crash loses little.
FLUSH_EVERY = 500

# Members read between progress reports. Independent of FLUSH_EVERY so a
# caller watching progress sees movement even when few rows are new.
REPORT_EVERY = PAGE_SIZE

# Consecutive pages without new rows before we assume Telegram has stopped
# returning usable results. Guards against endless paging loops.
MAX_STALL_PAGES = 3


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


def _is_skippable(user: types.User, include_bots: bool) -> bool:
    if getattr(user, "bot", False):
        return not include_bots
    if getattr(user, "deleted", False):
        return True
    return not _clean_username(user)


def _clean_username(user: types.User) -> str:
    return (getattr(user, "username", None) or "").lstrip("@")


def _slug(text: str) -> str:
    cleaned = _UNSAFE.sub("_", (text or "source").lstrip("@").lower()).strip("_")
    return cleaned or "source"


async def _iter_channel_users(client: TelegramClient, channel, search: str | None, delay: float):
    """Page a channel or megagroup with GetParticipants.

    Telethon's own iter_participants pages internally, so a delay has to be
    applied here instead in order to land once per request rather than once per
    member. With PAGE_SIZE=200 that is the difference between a scrape taking
    seconds and taking hours.
    """
    offset = 0
    stalled = 0
    pages = 0
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

        page = getattr(result, "users", []) if isinstance(
            result, channel_types.ChannelParticipants
        ) else []

        fresh = 0
        for user in page:
            if isinstance(user, types.User) and not getattr(user, "empty", False):
                fresh += 1
                yield user

        offset += len(page)
        pages += 1
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


async def _iter_chat_users(client: TelegramClient, chat):
    """Yield users of a legacy basic group.

    Basic groups have no paged GetParticipants request, so the full chat is
    fetched once and the user list is taken from it.
    """
    full = await client(functions.messages.GetFullChatRequest(chat.id))
    for user in getattr(full, "users", []) or []:
        if isinstance(user, types.User) and not getattr(user, "empty", False):
            yield user


async def _iter_users(client: TelegramClient, entity, search: str | None, delay: float):
    if isinstance(entity, types.Channel):
        async for user in _iter_channel_users(client, entity, search, delay):
            yield user
    else:
        async for user in _iter_chat_users(client, entity):
            yield user


def _write_rows(path: Path, rows: list[dict]) -> None:
    """Append a batch, adding a header only when the file is new."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEMBER_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


async def scrape(
    client: TelegramClient,
    settings: Settings,
    source: str,
    output: Path | None = None,
    include_bots: bool = False,
    limit: int | None = None,
    on_progress=None,
) -> ScrapeReport:
    try:
        entity = await resolve(client, source)
    except (UsernameNotOccupiedError, UsernameInvalidError) as exc:
        raise ValueError(f"cannot resolve {source!r}: {exc}") from exc
    except ChannelPrivateError as exc:
        raise ValueError(
            f"{source!r} is private. Your account must already be a member to read it."
        ) from exc

    source_title = getattr(entity, "title", None) or _slug(source)
    source_id = entity.id
    expected = await participant_count(client, entity)

    target = Path(output) if output else settings.data_dir / f"{_slug(source_title)}.csv"
    known = MemberStore(target).load()
    known_ids = set(known.records)

    # Channels need a non-empty search filter to page past the first chunk.
    search = "" if isinstance(entity, types.Channel) else None
    delay = settings.scrape_delay

    seen = 0
    new = 0
    duplicates = 0
    skipped = 0
    pending: list[dict] = []
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
            elif user.id in known_ids:
                duplicates += 1
            else:
                known_ids.add(user.id)
                pending.append(
                    MemberRecord.from_user(user, source_title, source_id).to_row()
                )
                new += 1

            if len(pending) >= FLUSH_EVERY:
                _write_rows(target, pending)
                pending = []

            # Report on read count, not on new rows, so a group full of
            # already-known or unaddressable members still shows movement.
            if seen - last_report >= REPORT_EVERY:
                last_report = seen
                report()

            if limit is not None and seen >= limit:
                break
    except ChatAdminRequiredError as exc:
        _write_rows(target, pending)
        raise ValueError(
            f"need admin rights in {source_title!r} to list its members"
        ) from exc
    except FloodWaitError as exc:
        _write_rows(target, pending)
        raise RuntimeError(
            f"Telegram asked for a {exc.seconds}s flood wait partway through "
            f"{source_title!r}. Progress so far was saved to {target}; rerun to resume."
        ) from exc

    _write_rows(target, pending)
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