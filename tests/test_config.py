from __future__ import annotations

from pathlib import Path

import pytest

from tg_common.config import ConfigError, Settings, load_settings


def test_load_settings_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("TG_API_ID", "123456")
    monkeypatch.setenv("TG_API_HASH", "abcdef0123456789abcdef0123456789")
    monkeypatch.setenv("TG_PHONE", "+1234567890")
    monkeypatch.setenv("TG_ADD_DELAY", "3.5")
    monkeypatch.setenv("TG_SCRAPE_DELAY", "0.5")
    monkeypatch.setenv("TG_FLOOD_SLEEP_THRESHOLD", "0")

    settings = load_settings(data_dir=data_dir)
    assert isinstance(settings, Settings)
    assert settings.api_id == 123456
    assert settings.api_hash == "abcdef0123456789abcdef0123456789"
    assert settings.phone == "+1234567890"
    assert settings.data_dir == data_dir
    assert settings.add_delay == 3.5
    assert settings.scrape_delay == 0.5
    assert settings.flood_sleep_threshold == 0
    assert settings.session_file("test") == data_dir / "test.session"


def test_load_settings_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_env = tmp_path / "empty.env"
    monkeypatch.setenv("TG_API_ID", "999")
    monkeypatch.setenv("TG_API_HASH", "hash123")
    monkeypatch.setenv("TG_PHONE", "+987654321")
    monkeypatch.delenv("TG_ADD_DELAY", raising=False)
    monkeypatch.delenv("TG_SCRAPE_DELAY", raising=False)
    monkeypatch.delenv("TG_FLOOD_SLEEP_THRESHOLD", raising=False)

    settings = load_settings(data_dir=tmp_path, env_path=empty_env)
    assert settings.add_delay == 5.0
    assert settings.scrape_delay == 1.0
    assert settings.flood_sleep_threshold == 0


def test_load_settings_missing_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_env = tmp_path / "empty.env"
    monkeypatch.delenv("TG_API_ID", raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)
    monkeypatch.delenv("TG_PHONE", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_settings(env_path=empty_env)
    assert "Missing TG_API_ID, TG_API_HASH, TG_PHONE" in str(exc_info.value)


def test_load_settings_invalid_api_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TG_API_ID", "not_a_number")
    monkeypatch.setenv("TG_API_HASH", "hash")
    monkeypatch.setenv("TG_PHONE", "+123")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(data_dir=tmp_path)
    assert "TG_API_ID must be a positive integer" in str(exc_info.value)


def test_load_settings_negative_api_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TG_API_ID", "-10")
    monkeypatch.setenv("TG_API_HASH", "hash")
    monkeypatch.setenv("TG_PHONE", "+123")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(data_dir=tmp_path)
    assert "TG_API_ID must be a positive integer" in str(exc_info.value)


def test_load_settings_invalid_delay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TG_API_ID", "123")
    monkeypatch.setenv("TG_API_HASH", "hash")
    monkeypatch.setenv("TG_PHONE", "+123")
    monkeypatch.setenv("TG_ADD_DELAY", "invalid_float")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(data_dir=tmp_path)
    assert "TG_ADD_DELAY must be a number" in str(exc_info.value)


def test_load_settings_negative_delay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TG_API_ID", "123")
    monkeypatch.setenv("TG_API_HASH", "hash")
    monkeypatch.setenv("TG_PHONE", "+123")
    monkeypatch.setenv("TG_ADD_DELAY", "-5.0")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(data_dir=tmp_path)
    assert "TG_ADD_DELAY must be non-negative" in str(exc_info.value)
