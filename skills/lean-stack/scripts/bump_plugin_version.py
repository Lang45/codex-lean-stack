#!/usr/bin/env python3
"""Atomically bump a plugin SemVer base and write one Codex cachebuster."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator


MAX_MANIFEST_BYTES = 1024 * 1024
PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
CACHEBUSTER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
CHANGE_TO_AXIS = {
    "breaking": "major",
    "feature": "minor",
    "fix": "patch",
}
REPARSE_POINT_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class VersionError(RuntimeError):
    """A fail-closed plugin release error."""


class DurabilityError(VersionError):
    """The manifest was replaced but directory durability was not confirmed."""


def default_cachebuster() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def validate_cachebuster(value: str) -> str:
    if not CACHEBUSTER_RE.fullmatch(value) or "--" in value:
        raise VersionError(
            "cachebuster must be 1-64 lowercase letters, digits, or single hyphens"
        )
    return value


def parse_semver(version: str) -> tuple[int, int, int, str | None, str | None]:
    if len(version) > 128:
        raise VersionError("version exceeds 128 characters")
    match = SEMVER_RE.fullmatch(version)
    if match is None:
        raise VersionError(f"version is not strict SemVer: {version}")
    prerelease = match.group("prerelease")
    if prerelease:
        for identifier in prerelease.split("."):
            if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                raise VersionError("numeric prerelease identifiers cannot contain leading zeroes")
    build = match.group("build")
    if build is not None and not build.startswith("codex."):
        raise VersionError(
            "existing build metadata is not Codex-owned; refusing to overwrite it"
        )
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        prerelease,
        build,
    )


def bump_base(version: str, change: str) -> str:
    major, minor, patch, _, _ = parse_semver(version)
    if change == "breaking":
        return f"{major + 1}.0.0"
    if change == "feature":
        return f"{major}.{minor + 1}.0"
    if change == "fix":
        return f"{major}.{minor}.{patch + 1}"
    raise VersionError(f"unsupported change type: {change}")


def ensure_plain_path(path: Path, *, label: str, directory: bool) -> None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError as exc:
        raise VersionError(f"missing {label}: {path}") from exc
    is_link = stat.S_ISLNK(metadata.st_mode)
    is_reparse = bool(getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT_FLAG)
    if is_link or is_reparse:
        raise VersionError(f"{label} cannot be a link or reparse point: {path}")
    expected_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected_type:
        expected = "directory" if directory else "regular file"
        raise VersionError(f"{label} must be a {expected}: {path}")


def manifest_path_for(plugin_root: Path) -> Path:
    root = plugin_root.expanduser().absolute()
    metadata_directory = root / ".codex-plugin"
    manifest = metadata_directory / "plugin.json"
    ensure_plain_path(root, label="plugin root", directory=True)
    ensure_plain_path(metadata_directory, label="plugin metadata directory", directory=True)
    ensure_plain_path(manifest, label="manifest", directory=False)
    return manifest


def read_manifest(manifest_path: Path) -> tuple[bytes, dict[str, Any]]:
    data = manifest_path.read_bytes()
    if len(data) > MAX_MANIFEST_BYTES:
        raise VersionError("manifest exceeds 1 MiB")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VersionError(f"manifest is not valid UTF-8 JSON: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise VersionError("manifest must contain a JSON object")
    name = payload.get("name")
    if not isinstance(name, str) or not PLUGIN_NAME_RE.fullmatch(name):
        raise VersionError("manifest name is missing or invalid")
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise VersionError("manifest version is missing or invalid")
    parse_semver(version)
    return data, payload


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def release_lock(manifest_path: Path) -> Iterator[None]:
    lock_path = manifest_path.with_name(f"{manifest_path.name}.release.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise VersionError(
            f"release lock already exists; inspect it before manual removal: {lock_path}"
        ) from exc
    owned = True
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        if owned:
            with contextlib.suppress(FileNotFoundError):
                lock_path.unlink()


def atomic_replace_json(
    manifest_path: Path,
    payload: dict[str, Any],
    expected_original: bytes,
) -> None:
    data = (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        raise VersionError("generated manifest failed JSON validation") from exc
    if not isinstance(parsed, dict) or parsed.get("version") != payload.get("version"):
        raise VersionError("generated manifest failed version validation")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", suffix=".tmp", dir=manifest_path.parent
    )
    temporary = Path(temporary_name)
    try:
        ensure_plain_path(manifest_path, label="manifest", directory=False)
        if os.name != "nt":
            os.fchmod(descriptor, stat.S_IMODE(os.lstat(manifest_path).st_mode))
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        ensure_plain_path(manifest_path, label="manifest", directory=False)
        if manifest_path.read_bytes() != expected_original:
            raise VersionError("manifest changed after it was read; refusing to overwrite")
        os.replace(temporary, manifest_path)
        try:
            fsync_directory(manifest_path.parent)
        except OSError as exc:
            raise DurabilityError(
                "manifest was replaced with "
                f"{payload.get('version')!r}, but directory durability confirmation failed; "
                "inspect the current manifest before any retry"
            ) from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def update_plugin_version(
    plugin_root: Path,
    *,
    change: str,
    expected_version: str,
    cachebuster: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if change not in CHANGE_TO_AXIS:
        raise VersionError(f"unsupported change type: {change}")
    token = validate_cachebuster(cachebuster or default_cachebuster())
    manifest_path = manifest_path_for(plugin_root)

    def prepare() -> tuple[bytes, dict[str, Any], str, str, str]:
        original, manifest = read_manifest(manifest_path)
        current = manifest["version"]
        assert isinstance(current, str)
        if current != expected_version:
            raise VersionError(
                f"expected version {expected_version!r}, found {current!r}; refusing a second bump"
            )
        next_base = bump_base(current, change)
        next_version = f"{next_base}+codex.{token}"
        updated = dict(manifest)
        updated["version"] = next_version
        return original, updated, current, next_base, next_version

    if dry_run:
        _, _, current, next_base, next_version = prepare()
    else:
        with release_lock(manifest_path):
            original, updated, current, next_base, next_version = prepare()
            atomic_replace_json(manifest_path, updated, original)

    return {
        "ok": True,
        "action": "version_preview" if dry_run else "version_bumped",
        "change": change,
        "axis": CHANGE_TO_AXIS[change],
        "old_version": current,
        "new_base": next_base,
        "new_version": next_version,
        "cachebuster": token,
        "modified": not dry_run,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically bump a plugin SemVer base and add one Codex cachebuster."
    )
    parser.add_argument("plugin_root", type=Path)
    parser.add_argument(
        "--change",
        choices=sorted(CHANGE_TO_AXIS),
        required=True,
        help="breaking=major, feature=minor, fix=patch",
    )
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--cachebuster")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    result = update_plugin_version(
        arguments.plugin_root,
        change=arguments.change,
        expected_version=arguments.expected_version,
        cachebuster=arguments.cachebuster,
        dry_run=arguments.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (VersionError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
