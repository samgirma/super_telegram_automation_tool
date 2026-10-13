"""Telethon client setup, cached login, and entity helpers."""

from __future__ import annotations

import sys
from getpass import getpass
from pathlib import Path
from typing import Any, Callable

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession
from telethon.tl import functions, types

from tg_common.config import Settings
from tg_common.storage import atomic_write


def _load_session(path: Path) -> StringSession:
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            return StringSession(raw)
    return StringSession()


def persist_session(client: TelegramClient, path: Path) -> None:
    session_str = client.session.save()
    with atomic_write(path, mode="w", encoding="utf-8", permissions=0o600) as handle:
        handle.write(session_str)


async def connect(
    settings: Settings,
    session_name: str,
    notify: Callable[[str], None] | None = None,
    ask_code: Callable[[], str] | None = None,
    ask_password: Callable[[], str] | None = None,
) -> TelegramClient:
    """Return an authorized client, logging in interactively if needed.

    The optional callables let a caller control how login is presented. The
    defaults reproduce the plain terminal behaviour used by the CLI scripts.
    """
    notify_cb = notify or (lambda msg: print(msg, file=sys.stderr))
    ask_code_cb = ask_code or (lambda: input("Enter the login code: ").strip())
    ask_password_cb = ask_password or (
        lambda: getpass("Two-step verification is on. Enter your password: ")
    )

    path = settings.session_file(session_name)
    client = TelegramClient(
        _load_session(path),
        settings.api_id,
        settings.api_hash,
        flood_sleep_threshold=settings.flood_sleep_threshold,
    )
    await client.connect()

    if await client.is_user_authorized():
        return client

    sent = await client.send_code_request(settings.phone)
    notify_cb(f"Login code sent to {settings.phone}.")
    try:
        await client.sign_in(
            settings.phone, ask_code_cb(), phone_code_hash=sent.phone_code_hash
        )
    except SessionPasswordNeededError:
        await client.sign_in(password=ask_password_cb())

    persist_session(client, path)
    me = await client.get_me()
    username = getattr(me, "username", None)
    notify_cb(f"Logged in as @{username or getattr(me, 'id', 'user')}")
    return client


async def resolve(client: TelegramClient, ref: str) -> Any:
    """Resolve a username, invite link or numeric id to a full entity.

    A channel id that Telethon cannot resolve on its own is retried through
    the linked_chat_id of every chat the account can see. This is how a
    private discussion group with no public handle becomes addressable: the
    access_hash is only available from the parent channel's full info.
    """
    try:
        return await client.get_entity(ref)
    except ValueError:
        found = await _resolve_from_dialogs(client, ref)
        if found is not None:
            return found
        found = await _resolve_via_linked_chat(client, ref)
        if found is not None:
            return found
        raise


async def _resolve_from_dialogs(client: TelegramClient, ref: str) -> Any | None:
    """Look for a numeric id among the chats the account already has.

    Cheap and sufficient in the common case: any chat you administer appears
    in the dialog list with its access hash already cached, so no network
    round trip per chat is needed.
    """
    wanted = _as_id(ref)
    if wanted is None:
        return None
    try:
        dialogs = await client.get_dialogs(limit=None)
    except (FloodWaitError, TypeError, AttributeError):
        return None
    for dialog in dialogs:
        entity = getattr(dialog, "entity", dialog)
        if getattr(entity, "id", None) == wanted:
            return entity
    return None


def _as_id(ref: str | int) -> int | None:
    text = str(ref).strip()
    if text.startswith("-100"):
        text = text[4:]
    return int(text) if text.lstrip("-").isdigit() else None


async def _resolve_via_linked_chat(client: TelegramClient, ref: str) -> Any | None:
    wanted = _as_id(ref)
    if wanted is None:
        return None

    try:
        dialogs = await client.get_dialogs(limit=None)
    except (FloodWaitError, TypeError, AttributeError):
        return None

    for dialog in dialogs:
        entity = getattr(dialog, "entity", dialog)
        if not isinstance(entity, types.Channel):
            continue
        try:
            full = await client(functions.channels.GetFullChannelRequest(entity))
        except (FloodWaitError, ChannelPrivateError, ValueError, TypeError, AttributeError):
            continue
        linked_id = getattr(full.full_chat, "linked_chat_id", None)
        if linked_id != wanted:
            continue
        for chat in full.chats:
            if chat.id == wanted:
                return types.InputChannel(
                    channel_id=chat.id, access_hash=chat.access_hash
                )
    return None


async def participant_count(client: TelegramClient, entity: Any) -> int | None:
    """Best-effort member total, used only for scrape coverage reporting."""
    try:
        if isinstance(entity, types.Channel):
            full = await client(functions.channels.GetFullChannelRequest(entity))
            return full.full_chat.participants_count
        full = await client(functions.messages.GetFullChatRequest(entity.id))
        participants = full.full_chat.participants
        if isinstance(participants, types.ChatParticipantsForbidden):
            return None
        return len(participants.participants)
    except (FloodWaitError, ValueError, TypeError, AttributeError):
        return None


__all__ = ["connect", "participant_count", "persist_session", "resolve"]
