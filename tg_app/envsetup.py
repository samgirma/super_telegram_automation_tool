"""Guided first-time .env creation with defaults for the optional knobs."""

from __future__ import annotations

from pathlib import Path

from tg_app import ui

# Non-critical knobs get sensible defaults the user can accept blindly.
DEFAULTS = {
    "TG_ADD_DELAY": "5",
    "TG_SCRAPE_DELAY": "0.2",
    "TG_FLOOD_SLEEP_THRESHOLD": "0",
}

TEMPLATE = """\
# Written by the tg_scraper & adder console app.
# Get api_id / api_hash from https://my.telegram.org -> API development tools

TG_API_ID={api_id}
TG_API_HASH={api_hash}
TG_PHONE={phone}

TG_ADD_DELAY={add_delay}
TG_SCRAPE_DELAY={scrape_delay}
TG_FLOOD_SLEEP_THRESHOLD={flood_sleep}
"""


def _valid_api_id(text: str) -> bool:
    return text.isdigit()


def _valid_api_hash(text: str) -> bool:
    return len(text) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in text)


def _valid_phone(text: str) -> bool:
    body = text[1:] if text.startswith("+") else text
    return text.startswith("+") and body.isdigit()


def needs_setup(env_path: Path) -> bool:
    if not env_path.exists():
        return True
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    required = ("TG_API_ID", "TG_API_HASH", "TG_PHONE")
    return any(not values.get(key) for key in required)


def run_wizard(env_path: Path) -> bool:
    """Interactively write .env. Returns False if the user gives up."""
    print()
    print(ui.info("No configuration found yet. Let's set it up, it takes a minute."))
    print()
    print(ui.step(f"Open {ui.c('https://my.telegram.org', ui.CYAN, ui.BOLD)} and go to"))
    print(ui.step("'API development tools' to get your api_id and api_hash."))
    print()

    api_id = ui.ask("Your TG_API_ID (a number)")
    while not _valid_api_id(api_id):
        print(ui.err("That should be digits only, for example 1234567."))
        api_id = ui.ask("Your TG_API_ID (a number)")

    api_hash = ui.ask("Your TG_API_HASH (32 hex characters)")
    while not _valid_api_hash(api_hash):
        print(ui.err("That should be 32 characters, letters a-f and digits."))
        api_hash = ui.ask("Your TG_API_HASH (32 hex characters)")

    phone = ui.ask("Your phone in international format (for example +251911234567)")
    while not _valid_phone(phone):
        print(ui.err("Start with + and use digits only."))
        phone = ui.ask("Your phone in international format")

    print()
    print(ui.step("The remaining settings have good defaults."))
    add_delay = ui.ask("Seconds between invites", DEFAULTS["TG_ADD_DELAY"])
    scrape_delay = ui.ask("Seconds between member pages", DEFAULTS["TG_SCRAPE_DELAY"])
    flood_sleep = ui.ask(
        "Auto-wait seconds on a Telegram flood limit",
        DEFAULTS["TG_FLOOD_SLEEP_THRESHOLD"],
    )

    env_path.write_text(
        TEMPLATE.format(
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            add_delay=add_delay,
            scrape_delay=scrape_delay,
            flood_sleep=flood_sleep,
        ),
        encoding="utf-8",
    )
    print()
    print(ui.ok(f"Saved your settings to {env_path.name}"))
    return True
