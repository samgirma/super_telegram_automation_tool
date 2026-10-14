# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-14

### Added
- **Atomic File Writing**: Implemented `atomic_write` context manager in `tg_common.storage` providing crash-safe writes (`tempfile.mkstemp` + `os.fsync` + `os.replace` + cleanup on failure) with configurable POSIX permissions (`0o600` default for sensitive files).
- **Session & Env Credential Security**: Restricted POSIX permissions (`0o600`) when persisting Telegram session credentials and generating `.env` configuration files.
- **Console Entrypoints**: Configured CLI console scripts (`sta`, `tg-scraper`, `tg-adder`, and `tg-filter`) in `pyproject.toml` alongside existing `python -m` invocations.
- **Packaging & Build System**: Standardized `pyproject.toml` using `setuptools.build_meta`, defining explicit dependencies and optional `dev` extra (`pytest`, `ruff`, `mypy`, `build`, `pyflakes`).
- **Comprehensive Test Suite**: Added 48 unit and integration tests across 8 modules covering configuration parsing, atomic storage, client session persistence, interactive UI utilities, member scraping, invite logic, and CLI argument parsing.
- **Strict Static Typing**: Annotated all 28 source and test files with complete type hints; verified with `mypy --strict` rules.
- **Enhanced Exception Classification**: Added Telegram RPC error classification for `UserDeactivatedBanError`, `UserKickedError`, `UserIdInvalidError`, `UserNotMutualContactError`, and others.

### Changed
- **Centralized Storage**: Replaced duplicated CSV reading/writing, filename slugification, and directory scanning logic across `tg_app` and `tg_common` with unified `scan_data_dir()`, `MemberStore`, and `AddLog` implementations.
- **Scraper Crash Resilience**: Ensured `tg_scraper.scraper` flushes pending records in a `finally:` block, preventing data loss on `KeyboardInterrupt` (`Ctrl-C`), flood waits, or network disconnections.
- **Adder Immediate Flush**: Updated `tg_adder.adder` to flush invite attempt logs atomically after every single user, eliminating duplicate invites or lost logs during inter-invite delays.
- **Hard Stop Enforcement**: Enforced strict termination on `PeerFloodError` and `FloodWaitError` without workarounds, recording stop reasons in `AddReport` for UI display.
- **Console Safety Prompts**: Added explicit confirmation prompts in `tg_app` prior to destructive in-place CSV filtering and before initiating live invites without prior dry-run preview.
- **Clean CLI Interruption Handling**: Entrypoints catch `KeyboardInterrupt` cleanly, report preserved progress, and exit with status code 130.

### Fixed
- Fixed unhandled `KeyboardInterrupt` crashes in the `.env` configuration wizard and CLI entry points.
- Fixed potential data corruption in `tg_filter` by writing to a temporary file before renaming to `.bak` and replacing the target file.
- Prevented potential race conditions and partial file writes when writing `.session` credential files.
