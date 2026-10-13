"""First-run dependency check and guided installation.

Deliberately imports only the standard library, so it can run before any
third-party package exists. Everything the app needs at runtime is checked
here and offered for install, one package at a time.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass

from tg_app import ui


@dataclass(frozen=True)
class Requirement:
    module: str
    package: str
    label: str
    why: str


REQUIREMENTS = [
    Requirement("telethon", "telethon", "Telethon", "talks to Telegram"),
    Requirement(
        "dotenv", "python-dotenv", "python-dotenv", "reads your .env settings"
    ),
    Requirement(
        "cryptography", "cryptography", "cryptography", "secures the login session"
    ),
]

PIP_FLAGS = ["--disable-pip-version-check", "--no-input", "--quiet"]


def missing() -> list[Requirement]:
    out = []
    for req in REQUIREMENTS:
        try:
            found = importlib.util.find_spec(req.module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            out.append(req)
    return out


def _pip_command() -> list[str]:
    return [sys.executable, "-m", "pip", "install", *PIP_FLAGS]


def install(req: Requirement) -> tuple[bool, str]:
    """Install one package, hiding pip's log spam on success.

    Falls back to a per-user install when the system Python is marked as
    externally managed, which is how most modern distros ship it.
    """
    good, detail = _run_pip([*_pip_command(), req.package])
    if good:
        return True, ""
    if "externally-managed" in detail or "permission" in detail.lower():
        good, detail2 = _run_pip([*_pip_command(), "--user", req.package])
        if good:
            return True, ""
        detail = detail2 or detail
    return False, detail


def _run_pip(cmd: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        return False, "python -m pip is not available on this machine"
    except Exception as exc:  # pragma: no cover - environment specific
        return False, str(exc)

    if proc.returncode == 0:
        return True, ""
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-6:])
    return False, tail or f"pip exited with code {proc.returncode}"


def ensure_dependencies(auto_yes: bool = False) -> bool:
    """Return True when every requirement is importable.

    Prompts before installing anything. Each package is installed on its own
    so progress is legible and a single failure does not abort the rest.
    """
    pending = missing()
    if not pending:
        return True

    print()
    print(ui.warn("Some required components are missing:"))
    for req in pending:
        print(ui.bullet(f"{ui.c(req.package, ui.WHITE, ui.BOLD)}  ({req.why})"))

    print()
    if not auto_yes and not ui.ask_yes_no(
        "Install them now? This only happens once", default=True
    ):
        print(ui.err("Cannot continue without these components."))
        return False

    print()
    for req in pending:
        print(
            f"{ui.c('->', ui.ORANGE, ui.BOLD)} Downloading "
            f"{ui.c(req.label, ui.WHITE, ui.BOLD)} ...",
            end="",
            flush=True,
        )
        good, detail = install(req)
        if good:
            print(f"\r{ui.ok(f'{req.label} installed')}")
        else:
            print(f"\r{ui.err(f'{req.label} failed')}")
            print(ui.step(ui.c(detail, ui.GREY)))
            return False

    importlib.invalidate_caches()
    still_missing = missing()
    if still_missing:
        print(ui.err("Still missing: " + ", ".join(r.package for r in still_missing)))
        return False

    print()
    print(ui.ok("All components are ready."))
    return True
