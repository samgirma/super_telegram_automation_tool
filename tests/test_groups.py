from __future__ import annotations

from unittest.mock import MagicMock, patch

from telethon.tl import types

from tg_app.groups import Choice, _admin_role, _kind, _members, _scrapeable, choose


def test_kind_detection() -> None:
    chat = MagicMock(spec=types.Chat)
    assert _kind(chat) == "group"

    supergroup = MagicMock(spec=types.Channel)
    supergroup.megagroup = True
    assert _kind(supergroup) == "supergroup"

    channel = MagicMock(spec=types.Channel)
    channel.megagroup = False
    assert _kind(channel) == "channel"

    other = MagicMock()
    assert _kind(other) == "chat"


def test_scrapeable_detection() -> None:
    chat = MagicMock(spec=types.Chat)
    assert _scrapeable(chat) is True

    supergroup = MagicMock(spec=types.Channel)
    supergroup.megagroup = True
    assert _scrapeable(supergroup) is True

    broadcast = MagicMock(spec=types.Channel)
    broadcast.megagroup = False
    assert _scrapeable(broadcast) is False


def test_admin_role_detection() -> None:
    # Basic group cannot accept channel invites
    chat = MagicMock(spec=types.Chat)
    assert _admin_role(chat) is None

    # Broadcast channel
    broadcast = MagicMock(spec=types.Channel)
    broadcast.megagroup = False
    assert _admin_role(broadcast) is None

    # Supergroup owner
    owner_sg = MagicMock(spec=types.Channel)
    owner_sg.megagroup = True
    owner_sg.creator = True
    assert _admin_role(owner_sg) == "owner"

    # Supergroup admin with invite rights
    admin_sg = MagicMock(spec=types.Channel)
    admin_sg.megagroup = True
    admin_sg.creator = False
    admin_sg.admin_rights = MagicMock(invite_users=True)
    assert _admin_role(admin_sg) == "admin"

    # Supergroup admin without invite rights
    no_invite_sg = MagicMock(spec=types.Channel)
    no_invite_sg.megagroup = True
    no_invite_sg.creator = False
    no_invite_sg.admin_rights = MagicMock(invite_users=False)
    assert _admin_role(no_invite_sg) is None


def test_members_helper() -> None:
    entity = MagicMock(participants_count=42)
    assert _members(entity) == 42


def test_choose_selection() -> None:
    c1 = Choice(
        entity=MagicMock(),
        title="Admin Group",
        kind="supergroup",
        members=10,
        can_admin=True,
        scrapeable=True,
        role="admin",
    )
    c2 = Choice(
        entity=MagicMock(),
        title="Read Only",
        kind="supergroup",
        members=5,
        can_admin=False,
        scrapeable=True,
    )

    with patch("tg_app.ui.ask", return_value="1"):
        picked = choose([c1, c2], purpose="add")
        assert picked == c1

    with patch("tg_app.ui.ask", return_value="0"):
        picked = choose([c1, c2], purpose="scrape")
        assert picked is None
