#!/usr/bin/env python3
"""Install Codex Lean Stack and idempotently register its global activation line."""

from __future__ import annotations

import argparse
import codecs
import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator


PLUGIN_NAME = "codex-lean-stack"
DEFAULT_INVOCATION_LINE = (
    "默认调用已安装的 `codex-lean-stack` 插件；是否启动子代理仍由插件自身规则决定。"
)
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MARKETPLACE_BYTES = 4 * 1024 * 1024
MAX_AGENTS_BYTES = 1024 * 1024
MARKETPLACE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
REPARSE_POINT_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class InstallError(RuntimeError):
    """A fail-closed installation or global-instruction update error."""


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT_FLAG)


def path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def ensure_plain_path(path: Path, *, label: str, directory: bool) -> None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError as exc:
        raise InstallError(f"missing {label}: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
        raise InstallError(f"{label} cannot be a link or reparse point: {path}")
    matches = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not matches:
        expected = "directory" if directory else "regular file"
        raise InstallError(f"{label} must be a {expected}: {path}")


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def update_lock(agents_path: Path) -> Iterator[None]:
    lock_path = agents_path.with_name(f".{agents_path.name}.lean-stack.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise InstallError(
            f"AGENTS.md update lock already exists; inspect it before retrying: {lock_path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            lock_path.unlink()


def read_manifest(plugin_root: Path) -> tuple[str, str]:
    root = plugin_root.expanduser().absolute()
    ensure_plain_path(root, label="plugin root", directory=True)
    manifest_path = root / ".codex-plugin" / "plugin.json"
    ensure_plain_path(manifest_path.parent, label="plugin metadata directory", directory=True)
    ensure_plain_path(manifest_path, label="plugin manifest", directory=False)
    data = manifest_path.read_bytes()
    if len(data) > MAX_MANIFEST_BYTES:
        raise InstallError("plugin manifest exceeds 1 MiB")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError("plugin manifest is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise InstallError("plugin manifest must contain a JSON object")
    name = payload.get("name")
    version = payload.get("version")
    if name != PLUGIN_NAME:
        raise InstallError(
            f"installer only accepts plugin {PLUGIN_NAME!r}, found {name!r}"
        )
    if not isinstance(version, str) or not version:
        raise InstallError("plugin manifest version is missing or invalid")
    return name, version


def default_marketplace_path() -> Path:
    return (Path.home() / ".agents" / "plugins" / "marketplace.json").absolute()


def verify_marketplace_source(
    marketplace_path: Path,
    *,
    marketplace: str,
    plugin_root: Path,
) -> None:
    path = marketplace_path.expanduser().absolute()
    ensure_plain_path(path, label="marketplace file", directory=False)
    data = path.read_bytes()
    if len(data) > MAX_MARKETPLACE_BYTES:
        raise InstallError("marketplace file exceeds 4 MiB")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError("marketplace file is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("name") != marketplace:
        raise InstallError(
            f"expected marketplace {marketplace!r} in {path}, "
            f"found {payload.get('name') if isinstance(payload, dict) else None!r}"
        )
    entries = payload.get("plugins")
    if not isinstance(entries, list):
        raise InstallError("marketplace plugins field must be an array")
    matching = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME
    ]
    if len(matching) != 1:
        raise InstallError(
            f"marketplace must contain exactly one {PLUGIN_NAME!r} entry"
        )
    source = matching[0].get("source")
    if not isinstance(source, dict) or source.get("source") != "local":
        raise InstallError("plugin marketplace source must be a local source object")
    relative = source.get("path")
    if not isinstance(relative, str) or not relative.startswith("./"):
        raise InstallError("plugin marketplace source path must start with './'")
    if len(path.parents) < 3:
        raise InstallError("marketplace path does not have a repository or home root")
    marketplace_root = path.parents[2]
    source_path = (marketplace_root / relative[2:]).resolve()
    expected_root = plugin_root.expanduser().absolute().resolve()
    if source_path != expected_root:
        raise InstallError(
            f"marketplace source {source_path} does not match plugin root {expected_root}"
        )


def resolve_codex_home(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().absolute()
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser().absolute()
    return (Path.home() / ".codex").absolute()


def _read_agents(path: Path) -> tuple[bytes | None, str, bool, str, int]:
    if not path_lexists(path):
        return None, "", False, "\n", 0o600
    ensure_plain_path(path, label="global AGENTS.md", directory=False)
    original = path.read_bytes()
    if len(original) > MAX_AGENTS_BYTES:
        raise InstallError("global AGENTS.md exceeds 1 MiB")
    has_bom = original.startswith(codecs.BOM_UTF8)
    body = original[len(codecs.BOM_UTF8) :] if has_bom else original
    try:
        text = body.decode("utf-8")
    except UnicodeError as exc:
        raise InstallError("global AGENTS.md is not valid UTF-8") from exc
    if "\x00" in text:
        raise InstallError("global AGENTS.md contains a NUL byte")
    first_newline = re.search(r"\r\n|\r|\n", text)
    newline = first_newline.group(0) if first_newline else "\n"
    mode = stat.S_IMODE(os.lstat(path).st_mode)
    return original, text, has_bom, newline, mode


def _atomic_replace(
    path: Path,
    *,
    expected_original: bytes | None,
    replacement: bytes,
    mode: int,
) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        if path_lexists(path):
            ensure_plain_path(path, label="global AGENTS.md", directory=False)
            current = path.read_bytes()
        else:
            current = None
        if current != expected_original:
            raise InstallError("global AGENTS.md changed after it was read")
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _preflight_default_invocation_locked(agents_path: Path) -> dict[str, Any]:
    _, text, _, _, _ = _read_agents(agents_path)
    return {
        "ok": True,
        "action": (
            "agents_default_present"
            if DEFAULT_INVOCATION_LINE in text.splitlines()
            else "agents_default_ready"
        ),
        "agents_path": str(agents_path),
    }


def _ensure_default_invocation_locked(agents_path: Path) -> dict[str, Any]:
    original, text, has_bom, newline, mode = _read_agents(agents_path)
    if DEFAULT_INVOCATION_LINE in text.splitlines():
        return {
            "ok": True,
            "action": "agents_default_present",
            "modified": False,
            "agents_path": str(agents_path),
            "line": DEFAULT_INVOCATION_LINE,
        }

    if text:
        first_break = re.search(r"\r\n|\r|\n", text)
        if first_break is None:
            updated = f"{text}{newline}{DEFAULT_INVOCATION_LINE}{newline}"
        else:
            updated = (
                f"{text[: first_break.end()]}"
                f"{DEFAULT_INVOCATION_LINE}{newline}"
                f"{text[first_break.end():]}"
            )
    else:
        updated = f"{DEFAULT_INVOCATION_LINE}{newline}"

    replacement = updated.encode("utf-8")
    if has_bom:
        replacement = codecs.BOM_UTF8 + replacement
    _atomic_replace(
        agents_path,
        expected_original=original,
        replacement=replacement,
        mode=mode,
    )
    return {
        "ok": True,
        "action": "agents_default_added",
        "modified": True,
        "agents_path": str(agents_path),
        "line": DEFAULT_INVOCATION_LINE,
    }


def ensure_default_invocation(codex_home: Path | None = None) -> dict[str, Any]:
    home = resolve_codex_home(codex_home)
    ensure_plain_path(home, label="Codex home", directory=True)
    agents_path = home / "AGENTS.md"
    with update_lock(agents_path):
        return _ensure_default_invocation_locked(agents_path)


def preflight_default_invocation(codex_home: Path | None = None) -> dict[str, Any]:
    home = resolve_codex_home(codex_home)
    ensure_plain_path(home, label="Codex home", directory=True)
    agents_path = home / "AGENTS.md"
    with update_lock(agents_path):
        return _preflight_default_invocation_locked(agents_path)


Runner = Callable[..., subprocess.CompletedProcess[str]]


def install_plugin(
    plugin_root: Path,
    *,
    marketplace: str = "personal",
    marketplace_path: Path | None = None,
    codex_home: Path | None = None,
    codex_command: str = "codex",
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    if not MARKETPLACE_RE.fullmatch(marketplace):
        raise InstallError(f"invalid marketplace name: {marketplace!r}")
    name, version = read_manifest(plugin_root)
    verified_marketplace_path = marketplace_path or default_marketplace_path()
    verify_marketplace_source(
        verified_marketplace_path,
        marketplace=marketplace,
        plugin_root=plugin_root,
    )
    executable = shutil.which(codex_command)
    if executable is None:
        candidate = Path(codex_command).expanduser()
        if not candidate.is_file():
            raise InstallError(f"Codex CLI was not found: {codex_command}")
        executable = str(candidate.absolute())
    command = [executable, "plugin", "add", f"{name}@{marketplace}", "--json"]
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    home = resolve_codex_home(codex_home)
    ensure_plain_path(home, label="Codex home", directory=True)
    agents_path = home / "AGENTS.md"
    with update_lock(agents_path):
        agents_preflight = _preflight_default_invocation_locked(agents_path)
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            detail = (
                completed.stderr or completed.stdout or "unknown install failure"
            ).strip()
            raise InstallError(
                f"plugin install failed with exit code {completed.returncode}: {detail}"
            )
        agents_result = _ensure_default_invocation_locked(agents_path)
    return {
        "ok": True,
        "action": "plugin_installed_with_default_invocation",
        "plugin": name,
        "version": version,
        "marketplace": marketplace,
        "marketplace_path": str(verified_marketplace_path.expanduser().absolute()),
        "install_exit_code": completed.returncode,
        "agents_preflight": agents_preflight,
        "agents": agents_result,
    }


def parse_args() -> argparse.Namespace:
    default_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description=(
            "Install Codex Lean Stack, then idempotently add its one-line default "
            "invocation instruction to the user's global AGENTS.md."
        )
    )
    parser.add_argument("--plugin-root", type=Path, default=default_root)
    parser.add_argument("--marketplace", default="personal")
    parser.add_argument("--marketplace-path", type=Path)
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--codex-command", default="codex")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    result = install_plugin(
        arguments.plugin_root,
        marketplace=arguments.marketplace,
        marketplace_path=arguments.marketplace_path,
        codex_home=arguments.codex_home,
        codex_command=arguments.codex_command,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (InstallError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
