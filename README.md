# Super Telegram Automation Tool

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Read the members of Telegram groups you belong to into clean, username-only
CSVs, and invite a chosen set into a group you own or administer. A friendly
console app wraps the CLI tools underneath.

## Install

```bash
git clone git@github.com:samgirma/super_telegram_automation_tool.git
cd super_telegram_automation_tool
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/sta
```

The console app checks and installs any missing dependencies, creates `.env` on
first run, logs you in once, and shows a numbered menu: scrape, add, filter,
view data. Get `api_id` / `api_hash` from <https://my.telegram.org> under
**API development tools**.

## CLI

```bash
python -m tg_scraper -t @somegroup                                    # scrape to data/<group>.csv
python -m tg_adder  -t @mygroup -f data/somegroup.csv --dry-run       # preview invites
python -m tg_adder  -t @mygroup -f data/somegroup.csv                 # send invites
python -m tg_filter data/somegroup.csv --in-place                     # drop rows without a username
```

Scrapes merge and resume. Adds resume, skip anyone already handled, and stop on
a flood. Always dry-run first.

## Warning

Mass-inviting people who never asked to hear from you is spam, it is against
Telegram's terms, and it is the fastest way to get your account restricted. Use
this for people who opted in — your own communities and subscribers. You are
responsible for how you use it.

## Support

If this is useful, please ⭐ star the repo — it helps others find it.

MIT licensed.
