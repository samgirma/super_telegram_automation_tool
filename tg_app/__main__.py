"""Entry point: banner, dependency check, .env wizard, then the menu.

Only the standard library and tg_app.ui are imported at module load, so the
first-run experience works on a machine where nothing is installed yet.
Everything that needs Telethon is imported lazily after the dependency step.
"""

from __future__ import annotations

from pathlib import Path

from tg_app import ui

AUTHOR = "samgirma"
VERSION = "1.0"


def _env_path() -> Path:
    from tg_common.config import ROOT

    return ROOT / ".env"


def main() -> int:
    ui.clear()
    print()
    print(ui.banner(AUTHOR, VERSION))
    print()

    from tg_app import bootstrap

    if not bootstrap.ensure_dependencies():
        return 2

    from tg_app import envsetup

    env_path = _env_path()
    if envsetup.needs_setup(env_path):
        if not envsetup.run_wizard(env_path):
            print(ui.err("Setup was cancelled."))
            return 2

    from tg_app.app import main as run_app

    return run_app()


__all__ = ["AUTHOR", "VERSION", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
