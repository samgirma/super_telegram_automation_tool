"""Fetch the account's own chats and let the user pick one by number."""

from __future__ import annotations

from dataclasses import dataclass

from telethon import TelegramClient
from telethon.tl import types

from tg_app import ui


@dataclass
class Choice:
    entity: types.TypeChat
    title: str
    kind: str
    members: int | None
    can_admin: bool
    scrapeable: bool = False
    role: str | None = None


def _kind(entity) -> str:
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel):
        if entity.megagroup:
            return "supergroup"
        return "channel"
    return "chat"


def _scrapeable(entity) -> bool:
    """True when member lists can actually be read for this chat.

    Broadcast channels have no readable member list, even for their owner, so
    they are excluded. Basic groups and supergroups (megagroups) qualify.
    """
    if isinstance(entity, types.Chat):
        return True
    return isinstance(entity, types.Channel) and entity.megagroup


def _members(entity) -> int | None:
    return getattr(entity, "participants_count", None)


def _admin_role(entity) -> str | None:
    """Return "owner", "admin" or None for how the account relates to a chat.

    Only supergroups accept the channel invites the adder sends, so basic
    groups and broadcast channels never qualify. The role gate is whether the
    account can actually invite, not merely administer.
    """
    if not isinstance(entity, types.Channel) or not entity.megagroup:
        return None
    if getattr(entity, "creator", False):
        return "owner"
    rights = getattr(entity, "admin_rights", None)
    if rights is not None and getattr(rights, "invite_users", False):
        return "admin"
    return None


async def fetch(client: TelegramClient) -> list[Choice]:
    dialogs = await client.get_dialogs(limit=None)
    choices: list[Choice] = []
    for dialog in dialogs:
        entity = getattr(dialog, "entity", None)
        if not isinstance(entity, (types.Chat, types.Channel)):
            continue
        role = _admin_role(entity)
        choices.append(
            Choice(
                entity=entity,
                title=getattr(entity, "title", None) or "(untitled)",
                kind=_kind(entity),
                members=_members(entity),
                can_admin=role is not None,
                scrapeable=_scrapeable(entity),
                role=role,
            )
        )
    choices.sort(key=lambda ch: (not ch.can_admin, -(ch.members or 0)))
    return choices


def render(choices: list[Choice], purpose: str) -> None:
    print()
    if purpose == "add":
        label = "group(s) you can invite members into"
    else:
        label = "group(s) whose members can be read"
    count = ui.c(str(len(choices)), ui.WHITE, ui.BOLD)
    print(ui.step(f"Found {count} {label}."))
    print()
    for index, choice in enumerate(choices, start=1):
        tag = ""
        if purpose == "add" and choice.role:
            tag = ui.c(f"  (you can invite, {choice.role})", ui.GREEN)
        members = (
            f"{choice.members:,} members" if choice.members is not None else "size unknown"
        )
        keytxt = ui.c(f"{index:>3} ", ui.BLACK, ui.BOLD, "\033[48;5;208m")
        print(
            f"  {keytxt} {ui.c(choice.title, ui.WHITE, ui.BOLD)}  "
            f"{ui.c('[' + choice.kind + ']', ui.CYAN)} {ui.c(members, ui.GREY)}{tag}"
        )


def choose(choices: list[Choice], purpose: str) -> Choice | None:
    if purpose == "add":
        choices = [c for c in choices if c.can_admin]
    elif purpose == "scrape":
        choices = [c for c in choices if c.scrapeable]
    if not choices:
        if purpose == "add":
            print(
                ui.warn(
                    "None of your groups allow you to invite members. "
                    "You must be an admin or owner of a supergroup."
                )
            )
        elif purpose == "scrape":
            print(
                ui.warn(
                    "None of your chats can be scraped. Broadcast channels "
                    "have no readable member list."
                )
            )
        else:
            print(ui.warn("Your account is not in any groups or channels."))
        return None

    render(choices, purpose)
    print()

    prompt = (
        "Enter the number to work with"
        if purpose != "add"
        else "Enter the number of the group to add members to"
    )
    while True:
        answer = ui.ask(prompt, "0")
        if answer == "0" or answer == "":
            return None
        if not answer.isdigit():
            print(ui.err("Please type a number, or 0 to cancel."))
            continue
        index = int(answer)
        if not 1 <= index <= len(choices):
            print(ui.err(f"Choose a number between 1 and {len(choices)}."))
            continue
        return choices[index - 1]
