"""Menu-driven console app: scrape, add, and inspect data, all by number."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from telethon import TelegramClient

from tg_adder.adder import AddReport, add_members
from tg_app import datafiles, groups, ui
from tg_common.client import connect
from tg_common.config import ConfigError, Settings, load_settings
from tg_common.storage import filter_member_csv
from tg_scraper.scraper import ScrapeReport, scrape

SESSION = "app"

# The app logs in with its own session, but an existing session from the CLI
# tools can be adopted after asking, so an already-authorized account is not
# forced through the login code again.
REUSE_CANDIDATES = ("app", "scraper", "adder")

MENU = [
    ("1", "Scrape members", "Read the members of one of your groups into a CSV"),
    ("2", "Add members", "Invite members from a saved CSV into a group you manage"),
    ("3", "Filter a data file", "Drop rows that have no username, so only usable ones remain"),
    ("4", "View saved data", "See what has already been scraped and how many are usable"),
    ("5", "Help", "How the app works and what to watch out for"),
    ("0", "Exit", "Close the app"),
]


def _display_name(me: Any) -> str:
    if me is None:
        return "(unknown account)"
    if getattr(me, "username", None):
        return f"@{me.username}"
    return str(getattr(me, "id", "unknown"))


class App:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: TelegramClient | None = None
        self.session_name = SESSION

    async def _connect(self, session_name: str) -> TelegramClient:
        client = await connect(
            self.settings,
            session_name,
            notify=lambda msg: print(ui.step(msg)),
            ask_code=lambda: ui.ask("Enter the login code Telegram sent you"),
            ask_password=lambda: ui.ask("Two-step password"),
        )
        self.session_name = session_name
        return client

    def _existing_session(self) -> str | None:
        for name in REUSE_CANDIDATES:
            if self.settings.session_file(name).exists():
                return name
        return None

    def _retire_session(self, name: str) -> None:
        path = self.settings.session_file(name)
        if path.exists():
            backup = path.with_name(path.name + ".bak")
            path.replace(backup)
            print(ui.step(f"Old session moved aside to {ui.c(backup.name, ui.WHITE)}"))

    async def start(self) -> None:
        """Reuse a saved login when one exists, otherwise log in."""
        existing = self._existing_session()
        if existing is not None:
            print()
            print(ui.step("Connecting to Telegram ..."))
            client = await self._connect(existing)
            me = await client.get_me()
            name = _display_name(me)
            print(ui.ok(f"Found a saved login: {ui.c(name, ui.WHITE, ui.BOLD)}"))
            if ui.ask_yes_no(f"Continue as {name}", default=True):
                self.client = client
                return
            await client.disconnect()
            print(ui.step("OK, logging in again instead."))
            if existing == SESSION:
                self._retire_session(SESSION)

        print()
        print(ui.step(f"Logging in with {ui.c(self.settings.phone, ui.WHITE)} ..."))
        self.client = await self._connect(SESSION)

    async def ensure_client(self) -> TelegramClient:
        if self.client is None or not self.client.is_connected():
            self.client = await self._connect(self.session_name)
        return self.client

    async def run(self) -> int:
        try:
            await self.start()
        except ConfigError as exc:
            print(ui.err(str(exc)))
            return 2
        except Exception as exc:  # pragma: no cover - network dependent
            print(ui.err(f"Could not log in: {exc}"))
            return 1

        await self.loop()
        return 0

    async def loop(self) -> None:
        first = True
        while True:
            if first:
                first = False
            else:
                ui.clear()
            print()
            ui.menu(MENU)
            files = datafiles.scan(self.settings.data_dir)
            if files:
                total = sum(f.with_username for f in files)
                print(
                    ui.step(
                        f"{ui.c(str(len(files)), ui.WHITE, ui.BOLD)} saved file(s), "
                        f"{ui.c(f'{total:,}', ui.GREEN, ui.BOLD)} usable members total"
                    )
                )
            print()
            choice = ui.ask("Choose an option", "0")
            if choice in {"0", "exit", "q"}:
                print()
                print(ui.ok("Goodbye."))
                return
            if choice not in {"1", "2", "3", "4", "5"}:
                print(ui.err("Unknown option. Type a number from the menu."))
                ui.pause()
                continue
            ui.clear()
            try:
                if choice == "1":
                    await self.scrape_flow()
                elif choice == "2":
                    await self.add_flow()
                elif choice == "3":
                    self.filter_flow()
                elif choice == "4":
                    datafiles.render(datafiles.scan(self.settings.data_dir))
                    ui.pause()
                else:
                    self.help_flow()
            except KeyboardInterrupt:
                print()
                print(ui.warn("Cancelled."))
            except (ValueError, RuntimeError, FileNotFoundError) as exc:
                print(ui.err(str(exc)))
                ui.pause()
            except Exception as exc:  # keep the app alive on unexpected errors
                print(ui.err(f"{type(exc).__name__}: {exc}"))
                ui.pause()

    # -- flows -------------------------------------------------------------

    async def scrape_flow(self) -> None:
        ui.section("Scrape members")
        client = await self.ensure_client()

        print(ui.step("Loading your chats ..."))
        choices = await groups.fetch(client)
        picked = groups.choose(choices, purpose="scrape")
        if picked is None:
            print(ui.warn("Nothing selected."))
            return

        print()
        print(
            ui.info(
                f"Scraping {ui.c(picked.title, ui.WHITE, ui.BOLD)}. "
                "Only members with a username are saved."
            )
        )
        last: dict[str, int | None] = {"line": None}

        def on_progress(seen: int, new: int, dup: int, skipped: int, expected: int | None) -> None:
            last["line"] = seen
            total = f" of ~{expected}" if expected else ""
            sys.stdout.write(
                "\r  "
                + ui.c(
                    f"{seen} read, {new} new, {skipped} skipped{total}",
                    ui.CYAN,
                )
                + "    "
            )
            sys.stdout.flush()

        report = await scrape(client, self.settings, str(picked.entity.id), on_progress=on_progress)

        print()
        print()
        self._show_scrape(report)
        ui.pause()

    def _show_scrape(self, report: ScrapeReport) -> None:
        print(ui.ok(f"Saved to {ui.c(report.path.name, ui.WHITE, ui.BOLD)}"))
        print(ui.bullet(f"{ui.c(str(report.new), ui.GREEN, ui.BOLD)} new members added"))
        if report.duplicates:
            print(ui.bullet(f"{report.duplicates} were already in the file"))
        print(ui.bullet(f"{report.skipped} had no username, so were left out"))
        if report.coverage is not None:
            print(
                ui.bullet(
                    f"read {report.seen:,} of about {report.expected:,} "
                    f"({report.coverage:.0%})"
                )
            )
        if report.stopped_early:
            print(
                ui.warn(
                    "Telegram stopped returning results early. "
                    "Rerun to pick up more."
                )
            )

    async def add_flow(self) -> None:
        ui.section("Add members")
        client = await self.ensure_client()

        files = datafiles.scan(self.settings.data_dir)
        if not files:
            print(ui.warn("You have no saved data to add from. Scrape a group first."))
            return

        datafiles.render(files)
        print()
        picked = self._pick_file(files)
        if picked is None:
            print(ui.warn("Nothing selected."))
            return

        print()
        print(ui.step("Loading your groups ..."))
        choices = await groups.fetch(client)
        target = groups.choose(choices, purpose="add")
        if target is None:
            print(ui.warn("Nothing selected."))
            return

        print()
        preview = ui.ask_yes_no("Preview first without sending anything", default=True)
        if preview:
            report = await add_members(
                client,
                self.settings,
                str(target.entity.id),
                picked.path,
                dry_run=True,
            )
            print()
            self._show_add(report, dry=True)
            print()
            if not ui.ask_yes_no("Looks right. Send the invites now", default=True):
                print(ui.warn("Stopped. Nothing was sent."))
                return
        else:
            if not ui.ask_yes_no(
                f"Skip preview and send live invites to {target.title} directly",
                default=False,
            ):
                print(ui.warn("Stopped. Nothing was sent."))
                return

        print()
        print(
            ui.info(
                f"Inviting into {ui.c(target.title, ui.WHITE, ui.BOLD)}. "
                "This stops itself if Telegram reports a flood."
            )
        )

        def on_attempt(attempted: int, record: Any, result: str, detail: str) -> None:
            colours = {"sent": ui.GREEN, "request_sent": ui.GREEN}
            colour = colours.get(result, ui.YELLOW if result == "already_member" else ui.GREY)
            who = f"@{record.username}" if record.username else str(record.user_id)
            print(f"  {ui.c(f'{attempted:>4}', ui.GREY)} {ui.c(who, ui.WHITE)} {ui.c(result, colour)}")

        report = await add_members(
            client,
            self.settings,
            str(target.entity.id),
            picked.path,
            on_attempt=on_attempt,
        )
        print()
        self._show_add(report, dry=False)
        ui.pause()

    def _pick_file(self, files: list[datafiles.DataFile]) -> datafiles.DataFile | None:
        while True:
            answer = ui.ask("Enter the number of the file to use", "0")
            if answer in {"0", ""}:
                return None
            if not answer.isdigit() or not 1 <= int(answer) <= len(files):
                print(ui.err(f"Choose a number between 1 and {len(files)}."))
                continue
            return files[int(answer) - 1]

    def _show_add(self, report: AddReport, dry: bool) -> None:
        if dry:
            print(ui.ok(f"Preview: {report.attempted} members would be contacted"))
        else:
            sent = report.counts.get("sent", 0) + report.counts.get("request_sent", 0)
            print(ui.ok(f"Done. {sent} invites delivered."))
        for result, count in sorted(report.counts.items()):
            print(ui.bullet(f"{count} x {ui.c(result, ui.GREY)}"))
        if report.stopped_reason:
            print(ui.warn(f"Notice: {report.stopped_reason}"))
        print(ui.step(f"Log: {report.path.name}"))

    def filter_flow(self) -> None:
        ui.section("Filter a data file")
        files = datafiles.scan(self.settings.data_dir)
        if not files:
            print(ui.warn("No data files to filter."))
            return
        datafiles.render(files)
        print()
        picked = self._pick_file(files)
        if picked is None:
            print(ui.warn("Nothing selected."))
            return
        if not ui.ask_yes_no(
            f"Filter '{picked.name}' in-place? A backup ({picked.name}.bak) will be created",
            default=True,
        ):
            print(ui.warn("Cancelled. No files were modified."))
            return
        result = filter_member_csv(picked.path, in_place=True)
        print()
        print(
            ui.ok(
                f"Kept {ui.c(str(result['kept']), ui.GREEN, ui.BOLD)} usable, "
                f"dropped {result['dropped']} without a username."
            )
        )
        backup_val = result.get("backup")
        backup_name = backup_val.name if isinstance(backup_val, Path) else str(backup_val)
        print(ui.step(f"Backup saved as {backup_name}"))
        ui.pause()

    def help_flow(self) -> None:
        ui.section("How this works")
        lines = [
            ("Scrape", "Reads members of a group you are in. Only accounts with a "
                       "public username are saved, since those are the only ones "
                       "that can be contacted later."),
            ("Add", "Invites members from a saved file into a group you manage. "
                    "Always preview first. Only supergroups you administer accept "
                    "invites, so broadcast channels are filtered out."),
            ("Filter", "Removes rows with no username from a file, and backs up "
                       "the original first."),
            ("Watch out", "Telegram limits how many invites an account can send. "
                          "If it reports a flood, the add stops on purpose. Wait "
                          "several hours before trying again, and keep the delay."),
            ("Good practice", "Invite people who opted in or are related to your "
                              "group's topic. Cold-inviting strangers risks your "
                              "account and rarely converts."),
        ]
        print()
        for head, body in lines:
            print(f"  {ui.c(head, ui.WHITE, ui.BOLD)}")
            print(f"    {ui.c(body, ui.GREY)}")
            print()


async def main_async() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(ui.err(str(exc)))
        return 2
    return await App(settings).run()


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print()
        print(ui.warn("Interrupted."))
        return 130


__all__ = ["App", "main", "main_async"]
