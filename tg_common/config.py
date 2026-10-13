"""Reads credentials and runtime knobs from the environment or .env."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent.parent

T = TypeVar("T", int, float)


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str
    data_dir: Path
    add_delay: float
    scrape_delay: float
    flood_sleep_threshold: int

    def session_file(self, name: str) -> Path:
        return self.data_dir / f"{name}.session"


class ConfigError(RuntimeError):
    pass


def _raw(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _number(name: str, default: T, cast: Callable[[str], T]) -> T:
    value = _raw(name)
    if value is None:
        return default
    try:
        val = cast(value)
        if val < 0:
            raise ConfigError(f"{name} must be non-negative, got {value!r}")
        return val
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {value!r}") from exc


def load_settings(data_dir: Path | None = None) -> Settings:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    api_id_raw = _raw("TG_API_ID")
    api_hash = _raw("TG_API_HASH")
    phone = _raw("TG_PHONE")

    missing = [
        name
        for name, value in (
            ("TG_API_ID", api_id_raw),
            ("TG_API_HASH", api_hash),
            ("TG_PHONE", phone),
        )
        if value is None
    ]
    if missing:
        raise ConfigError(
            "Missing " + ", ".join(missing) + ".\n"
            "Copy .env.example to .env and fill in your values.\n"
            "Get api_id and api_hash from https://my.telegram.org -> API development tools."
        )

    assert api_id_raw is not None
    assert api_hash is not None
    assert phone is not None

    try:
        api_id = int(api_id_raw)
        if api_id <= 0:
            raise ValueError("api_id must be positive")
    except ValueError as exc:
        raise ConfigError(f"TG_API_ID must be a positive integer, got {api_id_raw!r}") from exc

    target_dir = Path(data_dir) if data_dir else ROOT / "data"
    target_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        data_dir=target_dir,
        add_delay=_number("TG_ADD_DELAY", 5.0, float),
        scrape_delay=_number("TG_SCRAPE_DELAY", 1.0, float),
        flood_sleep_threshold=_number("TG_FLOOD_SLEEP_THRESHOLD", 0, int),
    )


__all__ = ["ROOT", "ConfigError", "Settings", "load_settings"]
