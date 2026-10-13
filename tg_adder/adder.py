"""Invite logic, one member at a time, every attempt logged."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from telethon import TelegramClient
from telethon.errors import (
    ChannelsTooMuchError,
    ChatAdminRequiredError,
    ChannelPrivateError,
    FloodWaitError,
    InputUserDeactivatedError,
    InviteHashExpiredError,
    InviteRequestSentError,
    PeerFloodError,
    PeerIdInvalidError,
    UserAlreadyParticipantError,
    UserBannedInChannelError,
    UserChannelsTooMuchError,
    UserDeactivatedBanError,
    UserIdInvalidError,
    UserIsBlockedError,
    UserIsBotError,
    UserKickedError,
    UserNotMutualContactError,
    UserNotParticipantError,
    UserPrivacyRestrictedError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl import functions, types

from tg_common.client import resolve
from tg_common.config import Settings
from tg_common.storage import AddLog, MemberRecord, MemberStore, clean_username

# Ineligible rows are normal outcomes, not run failures.
SKIPPED_STATUSES = {"deleted", "kicked", "restricted", "bot"}

AttemptCallback = Callable[[int, MemberRecord, str, str], None]
NotifyCallback = Callable[[str], None]


@dataclass
class AddReport:
    target: str
    attempted: int
    counts: dict[str, int]
    path: Path
    dry_run: bool
    stopped_reason: str | None = None

    def summary(self) -> str:
        head = "would invite" if self.dry_run else "invite attempts"
        tally = ", ".join(f"{k} {v}" for k, v in sorted(self.counts.items()))
        line = f"{self.target}: {self.attempted} {head}"
        line += " -> " + (tally if tally else "nothing to do")
        if self.dry_run:
            line += " (dry run, no log written)"
        if self.stopped_reason:
            line += f" [{self.stopped_reason}]"
        return line


def _classify(exc: Exception) -> tuple[str, str]:
    """Map a Telethon RPC error to a short result label and a readable detail."""
    table: list[tuple[type, str, str]] = [
        (UserAlreadyParticipantError, "already_member", "already in target"),
        (UserPrivacyRestrictedError, "privacy_restricted", "privacy settings block invites"),
        (UserNotMutualContactError, "privacy_restricted", "privacy allows mutual contacts only"),
        (UserBannedInChannelError, "banned", "banned from target"),
        (UserKickedError, "banned", "user was kicked from target"),
        (UserIsBlockedError, "blocked", "user blocked the account"),
        (UserNotParticipantError, "sent", "invite sent"),
        (InviteRequestSentError, "request_sent", "join request already pending"),
        (UserIsBotError, "is_bot", "user is a bot"),
        (InputUserDeactivatedError, "deactivated", "account is deleted"),
        (UserDeactivatedBanError, "deactivated", "account is deactivated or banned"),
        (PeerIdInvalidError, "unreachable", "user has no reachable username or id"),
        (UserIdInvalidError, "unreachable", "invalid user ID"),
        (UserChannelsTooMuchError, "too_many_channels", "user is in too many channels"),
        (ChannelsTooMuchError, "too_many_channels", "account is in too many channels"),
        (PeerFloodError, "peer_flood", "Telegram flagged the invite rate for this account"),
    ]
    for error, result, detail in table:
        if isinstance(exc, error):
            return result, detail
    return "error", type(exc).__name__


def _eligible(record: MemberRecord, include_bots: bool) -> str:
    # InviteToChannelRequest resolves a username server-side. A bare user id
    # carries no access hash, so Telegram rejects it for anyone we have never
    # spoken to, which rules out most scraped members.
    if not clean_username(record.username):
        return "no_username"
    if record.is_bot and not include_bots:
        return "is_bot"
    if record.status in SKIPPED_STATUSES and not include_bots:
        return f"status_{record.status}"
    return ""


async def _invite(client: TelegramClient, channel: Any, record: MemberRecord) -> tuple[str, str]:
    try:
        # users must be a list. Passing a bare string makes Telethon iterate it
        # character by character, which resolves to single letters and fails.
        clean_user = clean_username(record.username)
        await client(
            functions.channels.InviteToChannelRequest(channel, [clean_user])
        )
    except FloodWaitError:
        raise
    except Exception as exc:
        return _classify(exc)
    return "sent", "invite sent"


async def add_members(
    client: TelegramClient,
    settings: Settings,
    target: str,
    csv_path: Path,
    delay: float | None = None,
    limit: int | None = None,
    include_bots: bool = False,
    dry_run: bool = False,
    log_path: Path | None = None,
    on_attempt: AttemptCallback | None = None,
    notify: NotifyCallback | None = None,
) -> AddReport:
    pause = settings.add_delay if delay is None else delay
    source = Path(csv_path)
    if not source.exists():
        raise FileNotFoundError(f"no such CSV: {source}")

    try:
        channel = await resolve(client, target)
    except (UsernameNotOccupiedError, UsernameInvalidError, InviteHashExpiredError) as exc:
        raise ValueError(f"cannot resolve target {target!r}: {exc}") from exc
    except ChannelPrivateError as exc:
        raise ValueError(f"{target!r} is private and your account is not in it") from exc

    if isinstance(channel, types.InputChannel):
        # Reached by numeric id through a parent channel's linked_chat_id. There
        # is no username, so fetch the record to confirm it takes members.
        try:
            full = await client(functions.channels.GetFullChannelRequest(channel))
        except ChannelPrivateError as exc:
            raise ValueError(
                f"{target!r} is a private chat your account cannot inspect"
            ) from exc
        if not full.chats:
            raise ValueError(f"cannot read {target!r}")
        for chat in full.chats:
            if chat.id == channel.channel_id:
                channel = chat
                break
        else:
            raise ValueError(f"could not load the group behind {target!r}")

    if not isinstance(channel, types.Channel):
        raise ValueError("target must be a group or channel, not a personal chat")
    if not channel.megagroup:
        raise ValueError(
            "target is a broadcast channel, so members cannot be added to it. "
            "Enable discussion (or use a group) to turn it into a megagroup first."
        )

    title = getattr(channel, "title", target)
    store = MemberStore(source).load()
    log_file = Path(log_path) if log_path else settings.data_dir / f"adder_log_{title}.csv"
    log = AddLog(log_file).load()

    counts: dict[str, int] = {}
    attempted = 0

    def bump(result: str) -> None:
        counts[result] = counts.get(result, 0) + 1

    try:
        for record in store:
            if limit is not None and attempted >= limit:
                break
            ineligible = _eligible(record, include_bots)
            if ineligible:
                bump(ineligible)
                continue
            if not log.should_attempt(record.user_id):
                bump("already_processed")
                continue

            attempted += 1
            if dry_run:
                log.record(record.user_id, record.username, "would_send")
                bump("would_send")
                continue

            try:
                result, detail = await _invite(client, channel, record)
            except FloodWaitError as exc:
                log.record(record.user_id, record.username, "flood_wait", str(exc.seconds))
                bump("flood_wait")
                if not dry_run:
                    log.write()
                reason = f"Flood wait of {exc.seconds}s after {attempted} attempts"
                msg = (
                    f"{reason}. "
                    f"Progress is saved to {log_file}. Rerun to resume."
                )
                if notify is not None:
                    notify(msg)
                else:
                    print(msg)
                return AddReport(title, attempted, counts, log_file, dry_run, stopped_reason=reason)

            log.record(record.user_id, record.username, result, detail)
            bump(result)
            if not dry_run:
                log.write()

            if on_attempt is not None:
                on_attempt(attempted, record, result, detail)
            if result == "peer_flood":
                # Account-level signal, not a per-user outcome. Pushing on after
                # this is what escalates a flood warning into a length ban.
                reason = "Telegram returned PEER_FLOOD: the invite rate is too high for this account"
                msg = (
                    f"{reason}. Stopping after {attempted} attempts. "
                    "Wait several hours before resuming, and use a larger --delay."
                )
                if notify is not None:
                    notify(msg)
                else:
                    print(msg)
                return AddReport(title, attempted, counts, log_file, dry_run, stopped_reason=reason)
            if pause > 0:
                await asyncio.sleep(pause)
    except ChatAdminRequiredError as exc:
        raise ValueError(
            "you need admin rights in the target group to add members"
        ) from exc
    finally:
        if not dry_run:
            log.write()

    return AddReport(title, attempted, counts, log_file, dry_run)


__all__ = ["AddReport", "add_members"]
