#!/usr/bin/env python3
"""Track whether the fixed official cost baseline needs its weekly check.

The hot task path only reads a small local timestamp. The script never uses the
network and never edits plugin files; callers record a date only after checking
the official pages and updating the fixed baseline when needed.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Sequence


STATE_VERSION = 1
STATE_NAME = "cost-check-v1.json"
CURRENT_STATE_KEYS = {"version", "checked_at"}
LEGACY_STATE_KEYS = {
    "version",
    "checked_at",
    "official_fingerprint",
    "sources",
}
OFFICIAL_SOURCE_PREFIXES = (
    "https://learn.chatgpt.com/",
    "https://developers.openai.com/",
    "https://platform.openai.com/",
)
BASELINE_CHECKED_AT = dt.datetime(2026, 8, 27, tzinfo=dt.timezone.utc)
CHECK_INTERVAL = dt.timedelta(days=7)
MAX_STATE_BYTES = 2 * 1024
BUSY_ACTION = "weekly_check_skipped"
REPARSE_POINT_FLAG = 0x400


class CostCheckError(RuntimeError):
    """Fail-closed state or input error for optional weekly maintenance."""


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT_FLAG)


def plain_directory(path: Path, *, create: bool) -> Path:
    absolute = path.expanduser().absolute()
    if create:
        absolute.mkdir(parents=True, exist_ok=True)
    try:
        metadata = os.lstat(absolute)
    except FileNotFoundError as exc:
        raise CostCheckError(f"missing directory: {absolute}") from exc
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata):
        raise CostCheckError(f"directory cannot be a link or reparse point: {absolute}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise CostCheckError(f"path is not a directory: {absolute}")
    return absolute


def state_bytes(path: Path, state_dir: Path) -> bytes:
    absolute = path.expanduser().absolute()
    if absolute.parent != state_dir:
        raise CostCheckError("cost-check state escaped its directory")
    metadata = os.lstat(absolute)
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata):
        raise CostCheckError("cost-check state cannot be a link or reparse point")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise CostCheckError("cost-check state must be one regular file")
    if metadata.st_size > MAX_STATE_BYTES:
        raise CostCheckError("cost-check state is too large")
    return absolute.read_bytes()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise CostCheckError("timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CostCheckError("timestamp must include a time zone")
    return parsed.astimezone(dt.timezone.utc)


def format_time(value: dt.datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CostCheckError("timestamp must include a time zone")
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def load_state(codex_home: Path) -> tuple[dt.datetime, bytes | None, Path, bool]:
    home = plain_directory(codex_home, create=False)
    state_dir = (home / "lean-stack").absolute()
    state_path = state_dir / STATE_NAME
    if not os.path.lexists(state_dir):
        return BASELINE_CHECKED_AT, None, state_path, False
    plain_directory(state_dir, create=False)
    if not os.path.lexists(state_path):
        return BASELINE_CHECKED_AT, None, state_path, False
    data = state_bytes(state_path, state_dir)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CostCheckError("cost-check state is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise CostCheckError("cost-check state has an unexpected shape")
    keys = set(payload)
    legacy = keys == LEGACY_STATE_KEYS
    if keys != CURRENT_STATE_KEYS and not legacy:
        raise CostCheckError("cost-check state has an unexpected shape")
    if payload["version"] != STATE_VERSION:
        raise CostCheckError("cost-check state version is unsupported")
    if legacy:
        fingerprint = payload["official_fingerprint"]
        sources = payload["sources"]
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or not isinstance(sources, list)
            or not 1 <= len(sources) <= 8
            or any(
                not isinstance(source, str)
                or not source.startswith(OFFICIAL_SOURCE_PREFIXES)
                for source in sources
            )
        ):
            raise CostCheckError("legacy cost-check metadata is invalid")
    return parse_time(payload["checked_at"]), data, state_path, legacy


def status(*, codex_home: Path, now: dt.datetime) -> dict[str, Any]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise CostCheckError("current time must include a time zone")
    now_utc = now.astimezone(dt.timezone.utc)
    checked_at, data, state_path, legacy = load_state(codex_home)
    if checked_at > now_utc:
        raise CostCheckError("cost-check state timestamp is in the future")
    next_check = checked_at + CHECK_INTERVAL
    due = now_utc >= next_check
    return {
        "ok": True,
        "action": "official_check_due" if due else "fixed_baseline_current",
        "due": due,
        "checked_at": format_time(checked_at),
        "next_check_at": format_time(next_check),
        "state_path": str(state_path),
        "state_sha256": sha256_bytes(data) if data is not None else None,
        "legacy_state": legacy,
        "normalized_on_next_record": legacy,
        "network_used": False,
        "plugin_modified": False,
    }


def atomic_replace(path: Path, *, expected: bytes, replacement: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        if state_bytes(path, path.parent) != expected:
            raise CostCheckError("cost-check state changed while it was being updated")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def record(
    *,
    codex_home: Path,
    checked_at: dt.datetime,
    expected_state_sha256: str | None,
) -> dict[str, Any]:
    if checked_at.astimezone(dt.timezone.utc) > dt.datetime.now(dt.timezone.utc):
        raise CostCheckError("checked_at cannot be in the future")
    checked_at_text = format_time(checked_at)
    home = plain_directory(codex_home, create=False)
    state_dir = plain_directory(home / "lean-stack", create=True)
    state_path = state_dir / STATE_NAME
    replacement = (
        json.dumps(
            {"version": STATE_VERSION, "checked_at": checked_at_text},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")

    if os.path.lexists(state_path):
        original = state_bytes(state_path, state_dir)
        if expected_state_sha256 is None:
            raise CostCheckError("existing state requires --expected-state-sha256")
        if sha256_bytes(original) != expected_state_sha256:
            raise CostCheckError("expected state SHA-256 is stale")
        atomic_replace(state_path, expected=original, replacement=replacement)
    else:
        if expected_state_sha256 is not None:
            raise CostCheckError("state does not exist but an expected hash was supplied")
        descriptor = os.open(state_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())

    return {
        "ok": True,
        "action": "official_check_recorded",
        "checked_at": checked_at_text,
        "next_check_at": format_time(checked_at + CHECK_INTERVAL),
        "state_path": str(state_path),
        "state_sha256": sha256_bytes(replacement),
        "network_used": False,
        "plugin_modified": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track the weekly due date for the fixed official cost baseline."
    )
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status").add_argument("--now")
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--checked-at")
    record_parser.add_argument("--expected-state-sha256")
    return parser


def dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.command == "status":
        now = parse_time(arguments.now) if arguments.now else dt.datetime.now(dt.timezone.utc)
        return status(codex_home=arguments.codex_home, now=now)
    if arguments.command == "record":
        checked_at = (
            parse_time(arguments.checked_at)
            if arguments.checked_at
            else dt.datetime.now(dt.timezone.utc)
        )
        return record(
            codex_home=arguments.codex_home,
            checked_at=checked_at,
            expected_state_sha256=arguments.expected_state_sha256,
        )
    raise CostCheckError(f"unsupported command: {arguments.command}")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        result = dispatch(arguments)
    except (CostCheckError, OSError) as exc:
        print(
            json.dumps(
                {"ok": False, "action": BUSY_ACTION, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
