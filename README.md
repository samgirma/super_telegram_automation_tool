# Super Telegram Automation Tool

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Read the members of Telegram groups you belong to into clean, username-only
CSVs, and invite a chosen set into a group you own or administer. A friendly
console app wraps the CLI tools underneath.

## Installation

```bash
git clone git@github.com:samgirma/super_telegram_automation_tool.git
cd super_telegram_automation_tool
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/sta
```

For development and running tests, install with development dependencies:

```bash
.venv/bin/pip install -e ".[dev]"
```

The console app checks and installs any missing runtime dependencies, creates `.env` on
first run, logs you in once, and presents a numbered menu: scrape, add, filter,
and view data. Get `api_id` / `api_hash` from <https://my.telegram.org> under
**API development tools**.

## CLI & Entrypoints

The package installs console command entrypoints for direct command-line usage alongside the standard `python -m` invocations:

| Command | Module Alternative | Description |
|---|---|---|
| `sta` | `python -m tg_app` | Interactive console menu |
| `tg-scraper` | `python -m tg_scraper` | Scrape group members to CSV |
| `tg-adder` | `python -m tg_adder` | Invite users from CSV to group |
| `tg-filter` | `python -m tg_filter` | Filter usernames in CSV |

### Examples

```bash
# Scrape members to data/<group>.csv
tg-scraper -t @somegroup

# Preview invites with a dry run (always recommended first)
tg-adder -t @mygroup -f data/somegroup.csv --dry-run

# Send live invites (with 5-second default delay and flood detection)
tg-adder -t @mygroup -f data/somegroup.csv

# Drop rows without a username (in-place with automatic .bak backup)
tg-filter data/somegroup.csv --in-place
```

Scrapes automatically merge with existing files and resume from where they stopped.
Adds resume from previous logs, skip anyone already handled or ineligible, and stop immediately on flood signals.

## Security & Session Credentials

- **Session Files (`*.session`)**: Contain Telegram MTProto authentication keys and allow full access to your Telegram account. Never share, commit, or expose `.session` files.
- **File Permissions**: On POSIX systems, `.env` and `.session` files are automatically created and updated with restricted permissions (`0o600` / read-write by owner only) to prevent unauthorized access on multi-user machines.
- **Credentials in `.env`**: Store your `TG_API_ID`, `TG_API_HASH`, and `TG_PHONE` securely. `.gitignore` is configured by default to ignore all `.env` files and session artifacts.

## Anti-Spam Policy & Hard Stop Guarantees

This project strictly adheres to Telegram API limits and anti-spam best practices:
- **No Rate-Limit Evasion**: This tool does **not** support proxy rotation, account switching, or flood workarounds.
- **Immediate Hard Stop**: Any flood signal (`PeerFloodError`, `FloodWaitError`) halts operations immediately and saves progress to disk.
- **Crash Resilience**: Atomic writes guarantee that logs and CSV outputs are preserved even on unexpected termination (`Ctrl-C`) or errors.
- **Authorized Communities Only**: Mass-inviting unsolicited contacts violates Telegram's Terms of Service and will result in account restrictions. Use this tool only for members who have opted into your own communities.

## Development & Quality Assurance

All code adheres to strict type safety and linting standards.

### Running Tests

```bash
# Run test suite (48 tests)
.venv/bin/pytest -v
```

### Static Analysis & Type Checking

```bash
# Linting & style checks
.venv/bin/ruff check .

# Static type checking
.venv/bin/mypy tg_common tg_scraper tg_adder tg_filter tg_app tests

# Pyflakes check
.venv/bin/python -m pyflakes tg_common tg_scraper tg_adder tg_filter tg_app tests
```

### Packaging Build

```bash
.venv/bin/python -m build
```

## Support

If this tool is useful, please ⭐ star the repository.

## License

MIT Licensed.
