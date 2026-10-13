# Running this on another device

## What is in this folder

```
tg_scrapor_adder/
  tg_app/         menu-driven console app that wraps everything below
  tg_scraper/     reads members of a group/channel into a CSV
  tg_adder/       invites those members into a group you administer
  tg_filter/      strips rows without a username from an existing CSV
  tg_common/      shared config, login, CSV handling
  data/           where CSVs and logs are written (empty to start)
  requirements.txt
  .env.example     copy this to .env and fill it in
  README.md        full reference
  SETUP.md         this file
```

The quickest path is the console app in step 4; the raw commands are there too
if you prefer them.

Deliberately **not** included: `.env` (your API keys) and any `.session`
files. A `.session` file is a logged-in credential for your Telegram account —
anyone holding it has full access to that account. Never copy one between
devices or send it anywhere. Log in fresh on the new machine instead.

Same reasoning for scraped CSVs: they contain real people's usernames, so move
them only if you actually need them.

## 1. Install Python

Needs Python 3.10 or newer.

```bash
python3 --version
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
```

Activate it. Pick the line for your shell:

```bash
source .venv/bin/activate          # bash / zsh
source .venv/bin/activate.fish     # fish
.venv\Scripts\activate             # Windows PowerShell
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

## 3. Create `.env` and fill it in

```bash
cp .env.example .env
```

Open `.env` and set:

- `TG_API_ID` and `TG_API_HASH` — from <https://my.telegram.org> under
  **API development tools**. These are tied to your Telegram account, so the
  values are the same on every device.
- `TG_PHONE` — your number in international format, digits and `+` only.
- The remaining settings have working defaults. Leave `TG_ADD_DELAY=5` alone
  to start.

## 4. Log in and run

The console app handles login, configuration and both tools in one menu:

```bash
python -m tg_app
```

If `.env` is missing it offers to create it. If dependencies are missing it
offers to install them. If a saved session already exists it shows the account
and asks whether to continue as that user, or log in again. A fresh login uses
the phone from `.env`: Telegram sends a code to your Telegram app, and asks for
your password if two-step verification is on. Then it shows a numbered menu,
and the session is cached so later runs start without a prompt.

If you prefer the raw commands, the sections below do the same thing by hand.

### Scrape

```bash
python -m tg_scraper -t @somegroup --limit 5
```

### Add

Always dry-run first. `--dry-run` reports who would be contacted and writes
nothing:

```bash
python -m tg_adder -t @yourgroup -f data/somegroup.csv --dry-run
```

Then run it for real:

```bash
python -m tg_adder -t @yourgroup -f data/somegroup.csv
```

Useful flags:

| Flag | Meaning |
| --- | --- |
| `-t` / `--target` | Group to invite into. Must be a megagroup you administer. |
| `-f` / `--from` | CSV of members to invite, produced by `tg_scraper`. |
| `-d` / `--delay` | Seconds between invites. Overrides `TG_ADD_DELAY`. |
| `-n` / `--limit` | Stop after this many attempts. |
| `--dry-run` | Report only; send nothing. |
| `--session` | Session name, cached as `data/<name>.session`. |

Progress is appended to `data/adder_log_<group>.csv`. Rerunning resumes: people
already handled are skipped, so you never double-invite.

## Notes

- The target must be a **megagroup**, not a broadcast channel. Broadcast
  channels cannot take members and the script refuses them.
- Only members with a public username can be invited. Rows without one are
  reported as `no_username` and skipped.
- If Telegram returns `PEER_FLOOD`, the run stops on purpose. It is an
  account-level rate signal; continuing risks a length ban. Wait several
  hours, then resume with a larger `--delay`.
