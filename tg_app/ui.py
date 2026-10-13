"""Colored terminal output: banner, boxes, menus and prompts.

Kept dependency-free so it works before anything is installed, which is what
lets the first-run dependency check print a styled banner.
"""

from __future__ import annotations

import os
import shutil
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
GREY = "\033[90m"

ORANGE = "\033[38;5;208m"
LIME = "\033[38;5;154m"

# Status glyphs. ASCII-only fallback when the terminal can't handle unicode.
_GLYPHS = {
    "ok": "[+]",
    "warn": "[!]",
    "err": "[x]",
    "info": "[i]",
    "step": "->",
    "bullet": "*",
    "arrow": ">",
}


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


def supports_color(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return True


_ENABLED = None


def color_enabled() -> bool:
    global _ENABLED
    if _ENABLED is None:
        _enable_windows_ansi()
        _ENABLED = supports_color()
    return _ENABLED


def c(text: str, *styles: str) -> str:
    """Wrap text in ANSI styles, or return it untouched when color is off."""
    if not styles or not color_enabled():
        return str(text)
    return "".join(styles) + str(text) + RESET


def ok(msg: str) -> str:
    return f"{c(_GLYPHS['ok'], GREEN, BOLD)} {msg}"


def warn(msg: str) -> str:
    return f"{c(_GLYPHS['warn'], YELLOW, BOLD)} {msg}"


def err(msg: str) -> str:
    return f"{c(_GLYPHS['err'], RED, BOLD)} {msg}"


def info(msg: str) -> str:
    return f"{c(_GLYPHS['info'], CYAN, BOLD)} {msg}"


def step(msg: str) -> str:
    return f"  {c(_GLYPHS['step'], GREY)} {msg}"


def bullet(msg: str) -> str:
    return f"   {c(_GLYPHS['bullet'], GREY)} {msg}"


def terminal_width(default: int = 68) -> int:
    try:
        return min(shutil.get_terminal_size((default, 20)).columns, 92)
    except Exception:
        return default


def hr(width: int | None = None, char: str = "-") -> str:
    width = width or terminal_width()
    return c(char * width, GREY)


def title(text: str, width: int | None = None) -> str:
    width = width or terminal_width()
    inner = f" {text} "
    pad = max(width - len(inner), 0)
    left = pad // 2
    right = pad - left
    return c("-" * left + inner + "-" * right, CYAN, BOLD)


def banner(author: str, version: str = "1.0") -> str:
    width = terminal_width()
    lines = [
        c("  T G   S C R A P E R   &   A D D E R  ", ORANGE, BOLD),
        c("  Telegram member tools, without the guesswork  ", GREY),
        c(f"  built by github.com/{author}   v{version}", CYAN),
    ]
    top = c("+" + "-" * (width - 2) + "+", ORANGE)
    bot = top
    body = []
    for line in lines:
        visible = _visible_len(line)
        pad = max(width - 4 - visible, 0)
        body.append(c("|", ORANGE) + " " + line + " " * pad + " " + c("|", ORANGE))
    return "\n".join([top, *body, bot])


def _visible_len(text: str) -> int:
    """Length ignoring ANSI escapes, so padding lines up when colored."""
    length = 0
    in_escape = False
    for ch in text:
        if ch == "\033":
            in_escape = True
        elif in_escape and ch == "m":
            in_escape = False
        elif not in_escape:
            length += 1
    return length


def section(text: str) -> None:
    print()
    print(title(text))


def print_ok(msg: str) -> None:
    print(ok(msg))


def print_warn(msg: str) -> None:
    print(warn(msg))


def print_err(msg: str) -> None:
    print(err(msg), file=sys.stderr)


def print_info(msg: str) -> None:
    print(info(msg))


def ask(prompt: str, default: str | None = None) -> str:
    """Ask for a line of input. Empty answer falls back to the default."""
    suffix = f" {c('[' + default + ']', GREY)}" if default is not None else ""
    try:
        answer = input(f"{c(chr(0x2192), ORANGE, BOLD)} {prompt}{suffix}: ").strip()
    except EOFError:
        return default or ""
    if not answer and default is not None:
        return default
    return answer


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = ask(f"{prompt} {c('(' + hint + ')', GREY)}").lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def ask_choice(prompt: str, options: list[str], default: str | None = None) -> str:
    """Ask until the answer is one of the allowed options."""
    while True:
        answer = ask(prompt, default)
        lowered = {o.lower(): o for o in options}
        if answer.lower() in lowered:
            return lowered[answer.lower()]
        print_err(f"Please enter one of: {', '.join(options)}")


def menu(items: list[tuple[str, str, str]]) -> None:
    """Render numbered menu rows: (key, label, description)."""
    width = terminal_width()
    for key, label, desc in items:
        keytxt = c(f" {key:>2} ", BLACK, BOLD, "\033[48;5;208m")
        print(f"   {keytxt}  {c(label, WHITE, BOLD)}")
        print(f"        {c(desc, GREY)}")
        print(f"        {hr(width - 12)}")


def pause(msg: str = "Press Enter to return to the menu") -> None:
    try:
        input(f"\n{step(msg)} ")
    except EOFError:
        pass


def clear() -> None:
    """Wipe the terminal, but only when it is an interactive one."""
    if os.environ.get("NO_CLEAR"):
        return
    if not (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()):
        return
    os.system("cls" if os.name == "nt" else "clear")
