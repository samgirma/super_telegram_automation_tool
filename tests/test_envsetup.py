from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from tg_app.envsetup import (
    _valid_api_hash,
    _valid_api_id,
    _valid_phone,
    needs_setup,
    run_wizard,
)


def test_validation_helpers() -> None:
    assert _valid_api_id("123456") is True
    assert _valid_api_id("abc") is False
    assert _valid_api_id("-123") is False

    assert _valid_api_hash("0123456789abcdef0123456789abcdef") is True
    assert _valid_api_hash("0123456789ABCDEF0123456789ABCDEF") is True
    assert _valid_api_hash("tooshort") is False
    assert _valid_api_hash("0123456789abcdef0123456789abcdeg") is False  # 'g' is invalid hex

    assert _valid_phone("+1234567890") is True
    assert _valid_phone("+251911234567") is True
    assert _valid_phone("1234567890") is False  # missing leading +
    assert _valid_phone("+1234abc") is False


def test_needs_setup(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    assert needs_setup(env_file) is True

    # Incomplete file
    env_file.write_text("TG_API_ID=123\n", encoding="utf-8")
    assert needs_setup(env_file) is True

    # Complete file
    env_file.write_text(
        "TG_API_ID=123\nTG_API_HASH=hash\nTG_PHONE=+123\n",
        encoding="utf-8",
    )
    assert needs_setup(env_file) is False


def test_run_wizard_success(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    user_inputs = [
        "123456",                            # api_id
        "0123456789abcdef0123456789abcdef",  # api_hash
        "+1234567890",                       # phone
        "5",                                 # add_delay
        "0.2",                               # scrape_delay
        "0",                                 # flood_sleep
    ]

    with patch("tg_app.ui.ask", side_effect=user_inputs):
        result = run_wizard(env_file)

    assert result is True
    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")
    assert "TG_API_ID=123456" in content
    assert "TG_API_HASH=0123456789abcdef0123456789abcdef" in content
    assert "TG_PHONE=+1234567890" in content

    if os.name != "nt":
        assert env_file.stat().st_mode & 0o777 == 0o600


def test_run_wizard_interrupted(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    with patch("tg_app.ui.ask", side_effect=KeyboardInterrupt):
        result = run_wizard(env_file)

    assert result is False
    assert not env_file.exists()
