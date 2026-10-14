from __future__ import annotations

from unittest.mock import patch

import pytest

from tg_app import ui


def test_visible_len() -> None:
    assert ui._visible_len("hello") == 5
    colored = ui.c("hello", ui.GREEN, ui.BOLD)
    assert ui._visible_len(colored) == 5
    assert ui._visible_len("") == 0


def test_supports_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    ui.reset_color_cache()
    assert ui.color_enabled() is False

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    ui.reset_color_cache()
    assert ui.color_enabled() is True

    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    ui.reset_color_cache()
    assert ui.color_enabled() is False

    ui.reset_color_cache()


def test_glyphs_and_formatting() -> None:
    assert "[+]" in ui.ok("success")
    assert "[!]" in ui.warn("warning")
    assert "[x]" in ui.err("failure")
    assert "[i]" in ui.info("information")
    assert "->" in ui.step("next step")
    assert "*" in ui.bullet("bullet item")


def test_layout_elements() -> None:
    line = ui.hr(width=20)
    assert len(ui.c(line)) > 0

    t = ui.title("Settings", width=30)
    assert "Settings" in t

    b = ui.banner("samgirma", "1.0")
    assert "samgirma" in b
    assert "1.0" in b


def test_ask_yes_no() -> None:
    with patch("builtins.input", return_value="y"):
        assert ui.ask_yes_no("Proceed") is True

    with patch("builtins.input", return_value="n"):
        assert ui.ask_yes_no("Proceed") is False

    with patch("builtins.input", return_value=""):
        assert ui.ask_yes_no("Proceed", default=True) is True
        assert ui.ask_yes_no("Proceed", default=False) is False
