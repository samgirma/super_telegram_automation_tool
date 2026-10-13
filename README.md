# Super Telegram Automation Tool

A Telethon toolkit for Telegram member workflows: read the members of groups you
belong to, keep them as clean CSVs, and invite a chosen set into a group you own
or administer. Drive it from a friendly numbered **console app**, or from the
**CLI scripts** underneath if you prefer flags.

> Built for legitimate growth — opt-in subscribers, your own communities, and
> people who asked to hear from you. Please read [A word of warning](#a-word-of-warning)
> before pointing it at strangers.

## Features

- **One menu, no flags.** `tg_app` walks you through scraping, adding,
  filtering, and inspecting your data by number.
- **First-run friendly.** Checks the dependencies and offers to install what is
  missing, builds `.env` with sensible defaults, and handles login.
- **Session aware.** Shows you which account a saved session belongs to and
  lets you continue as that user or log in again. Nothing is ever deleted.
- **Clean by default.** Only members with a public username are written, so you
  never keep rows that can never be contacted.
- **Resumable.** Scrapes merge into the existing file; adds skip anyone already
  handled. An interrupted run just picks up where it stopped.
- **Safe adding.** Dry-run preview first, a full per-attempt log, and the run
  stops itself the moment Telegram reports a flood.
- **Smart pickers.** Scraping lists only groups whose members can be read;
  adding lists only supergroups you own or administer.

## Quick start

```bash
git clone git@github.com:samgirma/super_telegram_automation_tool.git
cd super_telegram_automation_tool
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m tg_app
```

That is the whole setup. The console app creates `.env` on first run (keep your
`api_id`/`api_hash` handy from <https://my.telegram.org> under **API development
tools**), logs you in once, and drops you at the menu.

## What is in the box

| Path | What it does |
| --- | --- |
| `tg_app/` | Menu-driven console app that wraps everything below. The friendly way in. |
| `tg_scraper/` | Reads the members of groups you are in and writes them to a CSV in `data/`. |
| `tg_adder/` | Reads a CSV from `data/` and invites those members into a group you administer. |
| `tg_filter/` | Strips rows without a username from an existing CSV, backing it up first. |
| `tg_common/` | Shared config, login, entity resolution and CSV handling. |
| `data/` | Where scraped CSVs and adder logs live. Nothing here is committed. |

## Requirements

- Python 3.10 or newer.
- `telethon`, `python-dotenv`, `cryptography` (see `requirements.txt`).
- A Telegram account, plus `api_id`/`api_hash` from
  <https://my.telegram.org> under **API development tools**.

## The console app

If you would rather not remember flags, `tg_app` does the same work through a
numbered menu:

```bash
.venv/bin/python -m tg_app
```

On a machine where nothing is installed yet, it checks for Telethon and the
other requirements and offers to install any that are missing. If there is no
`.env` it walks you through creating one, with sensible defaults for the tuning
knobs. Then it deals with login:

- If a saved session already exists, it connects, shows you the account it
  belongs to, and asks whether to continue as that user. Answer no and it logs
  in again from scratch (moving the old session aside, never deleting it).
- Otherwise it logs in with the phone number from `.env`. Telegram sends a code
  to your Telegram app; enter it (and your two-step password, if you use one).
  The session is then cached, so later runs skip this step.

After that it shows a menu:

1. **Scrape members** — pick one of your groups from a list and read its members.
   Broadcast channels are left out, since their member lists cannot be read.
2. **Add members** — pick a saved CSV, then a group. Only supergroups your
   account owns or administers with invite rights are listed, so broadcast
   channels and ordinary memberships never appear. Preview, then send.
3. **Filter a data file** — drop rows without a username, keeping a `.bak` copy.
4. **View saved data** — see what is in `data/` and how much of it is usable.

It never asks you to type a group name: it fetches your chats and lets you
choose by number. The screen clears between the menu and each option, so you
always start from a clean view. Set `NO_CLEAR=1` to keep the scrollback. The
scalar details are in the sections below; the app is just a front end over the
same code.

## Manual setup (CLI)

If you are not using the console app, set the environment up yourself:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`. Get `TG_API_ID` and `TG_API_HASH` from
<https://my.telegram.org> under **API development tools**, and use your phone
number in international format for `TG_PHONE`.

On first run each script asks for the login code Telegram sends you. If
two-step verification is on it also asks for your password. The session is then
cached in `data/<name>.session`, so later runs start immediately. The scraper
and the adder keep separate sessions, which is also what stops them colliding if
you ever run both at once.

## Scraping

```bash
.venv/bin/python -m tg_scraper -t @somegroup
.venv/bin/python -m tg_scraper -t @groupone -t @grouptwo
.venv/bin/python -m tg_scraper -t @somegroup -o data/members.csv --limit 500
```

Output defaults to `data/<group name>.csv`. Rerunning the same scrape merges
into the existing file and skips members already recorded, so a scrape
interrupted by a flood wait can simply be run again.

Options: `-o/--output`, `--session`, `--include-bots`, `--limit`.

### Speed

Members arrive 200 at a time, so `TG_SCRAPE_DELAY` is a delay **between pages,
not between members**. At the default `0.2` a scrape sustains roughly 1000
members a second, limited mostly by the round trip to Telegram. A 100k-member
group takes a few minutes rather than hours. Rows are written to disk every 500
members, so an interrupted run keeps what it already read, and progress is
printed to stderr as it goes.

Turning `TG_SCRAPE_DELAY` down to `0` removes the pause entirely. That is
faster still, but you will hit flood waits sooner, and a flood wait costs you
minutes of enforced waiting, so it rarely pays off.

### CSV columns

```
user_id, username, first_name, last_name, is_premium, is_verified, is_scam,
is_bot, is_restricted, status, source, source_id, collected_at
```

Only members with a public username are written. Everyone else is counted as
skipped and left out, because a username is the sole address the adder can use
(see below), so a row without one could never be contacted. The summary line
reports how many were skipped, and `--include-bots` additionally lets bot
accounts through.

`status` is one of `active`, `bot`, `deleted`, `kicked` or `restricted`.

### Filtering an existing CSV

The scraper always writes username-only now, but files scraped before that
change still hold unusable rows. Trim them in place with `tg_filter`:

```bash
.venv/bin/python -m tg_filter data/mygroup.csv --in-place
.venv/bin/python -m tg_filter data/one.csv data/two.csv
```

`--in-place` overwrites each file after copying it to `<name>.csv.bak`. Without
it, the result is written next to the original as `<name>.filtered.csv`.
Rows are also de-duplicated by `user_id`.

## Adding members

The target must be a **megagroup** (a group, or a channel with discussion
enabled) that your account administers. Broadcast channels cannot take members
and the script refuses them.

Invites go out by username, so rows lacking one are reported as `no_username`
and skipped. A bare user id carries no access hash for anyone you have never
spoken to, which rules out most scraped members.

```bash
.venv/bin/python -m tg_adder -t @mygroup --dry-run
.venv/bin/python -m tg_adder -t @mygroup -f data/somegroup.csv
```

A target can be given as a username, an invite link, or a numeric id. A
discussion group with no public handle resolves by id, since the access hash
is reachable through the parent channel's `linked_chat_id`:

```bash
.venv/bin/python -m tg_adder -t 3023255456 -f data/somegroup.csv --dry-run
```

If Telegram answers `PEER_FLOOD` the run stops immediately and that user is
marked done. It is an account-level rate signal, not a per-user failure:
keep going and the account earns a length ban. Stop for several hours, then
resume with a larger `--delay`.

Always run `--dry-run` first: it reports exactly who would be contacted and
writes nothing.

Every attempt is appended to `data/adder_log_<group>.csv` with a result:

| Result | Meaning |
| --- | --- |
| `sent` | Invite delivered. |
| `request_sent` | They already had a join request pending. |
| `already_member` | Already in the group. |
| `privacy_restricted` | Their privacy settings block invites. Nothing you can do. |
| `blocked` | They blocked your account. |
| `banned` | Banned from your group. |
| `no_username` | No public username, so there is no way to reach them. |
| `unreachable` | Telegram could not resolve the username. |
| `too_many_channels` | Either side is in too many groups. |
| `flood_wait` | Rate limited. Stops the run and saves progress. |
| `error` | Anything else, with the exception name in `detail`. |

Rerunning resumes where you stopped: members already added are skipped, and so
are permanent failures, because retrying them just wastes rate limit. Only
`flood_wait` and `error` get retried.

Options: `-d/--delay`, `-n/--limit`, `--include-bots`, `--dry-run`, `--log`,
`--session`.

## Security and privacy

- `.env` and `*.session` files are **never** committed. `.gitignore` excludes
  them, along with everything in `data/`.
- A `.session` file is a **logged-in credential** for your Telegram account.
  Anyone holding it has full access to that account. Never share it or copy it
  between devices — log in fresh instead.
- Scraped CSVs contain real people's usernames. Treat them as personal data.

## Things worth knowing

- **Members with no public username cannot be added.** Telegram resolves
  invites by username server-side, and a bare user id carries no access hash,
  so users who have never set a username are unreachable. They are logged as
  `no_username` rather than silently dropped.
- **Channel member lists are not always fully enumerable.** Telegram does not
  serve a complete paginated list for every channel, so the reported coverage
  percentage in the scrape summary can be well under 100%.
- **`FloodWaitError` is handled, not hidden.** The run stops, writes the log and
  tells you to rerun. Nothing here tries to disguise its rate. The delay
  between invites is a fixed interval you control via `TG_ADD_DELAY`, default
  5s; turning it down is the fastest way to get your account rate-limited or
  restricted. Scraping is the cheaper side of this, because reading member
  lists is what your account is doing anyway and pages are large.
- **The scraper needs admin rights** in a group to list all of it, and needs to
  be a member to read anything at all.

## A word of warning

Mass-inviting people who never asked to hear from you is spam, it is against
Telegram's terms, and it is the fastest route to a restricted account. It also
makes the tool useless to you, because a dead account scrapes nothing. The
invite path here works best for people who opted in — subscribers you have a
record of, members who left your own group and could reasonably be welcomed
back, or users who asked to be notified.

This project is a technical toolkit, not a recommendation to spam strangers.
Running it against groups you do not own or people who did not consent is your
responsibility, and in many jurisdictions unsolicited messaging carries legal
liabilities of its own.
