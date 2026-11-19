#!/usr/bin/env python3
"""Install Codex Lean Stack and idempotently register its global activation line."""

from __future__ import annotations

import argparse
import importlib.util
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


# Resolve this sibling explicitly: standalone CLI and import-by-path probes
# must use the same implementation without changing the caller's sys.path.
_lock_spec = importlib.util.spec_from_file_location(
    "_lean_stack_maintenance_lock", Path(__file__).with_name("_maintenance_lock.py")
)
assert _lock_spec is not None and _lock_spec.loader is not None
_locks = importlib.util.module_from_spec(_lock_spec)
_lock_spec.loader.exec_module(_locks)

_update_spec = importlib.util.spec_from_file_location(
    "_lean_stack_atomic_file_update", Path(__file__).with_name("_atomic_file_update.py")
)
assert _update_spec is not None and _update_spec.loader is not None
_updates = importlib.util.module_from_spec(_update_spec)
_update_spec.loader.exec_module(_updates)


PLUGIN_NAME = "codex-lean-stack"
DEFAULT_INVOCATION_LINE = (
    "所有模型和思考程度的父代理必须使用已安装的 `codex-lean-stack`；两个入口按需读取，入口保留"
    "快速判断，确认命中后才读取对应功能分支，选配与协作细节由插件维护。"
)
USER_GLOBAL_INVOCATION_LINE = "必须调用已安装的 `codex-lean-stack` 插件。"
USER_GLOBAL_INVOCATION_PREFIXES = (
    USER_GLOBAL_INVOCATION_LINE.removesuffix("。"),
    "所有模型和思考程度的父代理必须使用已安装的 `codex-lean-stack`",
    "所有模型和思考程度的父代理必须都使用已安装的 `codex-lean-stack`",
    "所有父代理（无论模型与思考程度）必须使用已安装的 `codex-lean-stack`",
)
INVOCATION_SEPARATOR_PUNCTUATION = frozenset("，。；：！？、,.;:!?")
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


def _read_limited(path: Path, *, label: str, limit: int) -> bytes:
    ensure_plain_path(path, label=label, directory=False)
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise InstallError(f"{label} exceeds {limit // (1024 * 1024)} MiB")
    return data


@contextlib.contextmanager
def update_lock(agents_path: Path) -> Iterator[None]:
    """Hold a process-lifetime lock; keep the stable anchor after release."""
    lock = agents_path.with_name(f".{agents_path.name}.lean-stack.lock")
    with _locks.exclusive_lock(
        lock, error_type=InstallError,
        busy_message='AGENTS.md update is already in progress; skip this attempt',
        reject_legacy_marker=True,
    ):
        yield


def read_manifest(plugin_root: Path) -> tuple[str, str]:
    root = plugin_root.expanduser().absolute()
    ensure_plain_path(root, label="plugin root", directory=True)
    manifest_path = root / ".codex-plugin" / "plugin.json"
    ensure_plain_path(manifest_path.parent, label="plugin metadata directory", directory=True)
    data = _read_limited(manifest_path, label="plugin manifest", limit=MAX_MANIFEST_BYTES)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
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
    data = _read_limited(path, label="marketplace file", limit=MAX_MARKETPLACE_BYTES)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
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
    if not isinstance(relative, str) or not relative.startswith("./") or "\x00" in relative:
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
    original = _read_limited(path, label="global AGENTS.md", limit=MAX_AGENTS_BYTES)
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
) -> dict[str, str] | None:
    if expected_original is not None:
        if _read_limited(path, label="global AGENTS.md", limit=MAX_AGENTS_BYTES) != expected_original:
            raise InstallError("global AGENTS.md changed after it was read")
        return _updates.replace_existing(path, expected=expected_original, replacement=replacement)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    staging_owned = True
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if os.name != "nt":
                os.fchmod(handle.fileno(), mode)
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        if path_lexists(path):
            current = _read_limited(path, label="global AGENTS.md", limit=MAX_AGENTS_BYTES)
        else:
            current = None
        if current != expected_original:
            raise InstallError("global AGENTS.md changed after it was read")
        # Windows rename and POSIX link never overwrite a concurrent creator.
        try:
            if os.name == "nt":
                os.rename(temporary, path)
                staging_owned = False
            else:
                os.link(temporary, path)
        except FileExistsError as exc:
            raise InstallError("global AGENTS.md was created after it was read") from exc
        try:
            fsync_directory(path.parent)
        except OSError as exc:
            raise InstallError(
                "global instructions were replaced, but directory durability could not be confirmed"
            ) from exc
    finally:
        if staging_owned:
            primary = sys.exc_info()[1]
            if primary is not None:
                if isinstance(primary, Exception):
                    raise InstallError(f"{primary}; unpublished candidate retained at {temporary}") from primary
                primary.add_note(f"Unpublished candidate retained at {temporary}")
                raise
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup:
                raise InstallError(f"global instructions were written, but staging cleanup failed: {cleanup}") from cleanup


def effective_agents_path(home: Path) -> Path:
    # ReplaceFileW error 1177 may have moved the old rules to recovery while
    # leaving the proposed file unpublished. Never treat that as a first install.
    for filename in ("AGENTS.md", "AGENTS.override.md"):
        target = home / filename
        if path_lexists(target):
            continue
        for work in home.glob(f".{filename}.recovery-*"):
            ensure_plain_path(work, label="instruction recovery directory", directory=True)
            previous, proposed = work / "previous", work / "proposed"
            if not (path_lexists(previous) and path_lexists(proposed)):
                continue
            raw = _read_limited(work / "operation.json", label="instruction recovery record", limit=MAX_AGENTS_BYTES)
            try:
                record = json.loads(raw.decode("utf-8"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise InstallError(f"invalid instruction recovery record; inspect {work}") from exc
            if (not isinstance(record, dict) or record.get("target") != str(target.absolute())
                    or record.get("candidate") != "proposed" or record.get("displaced") != "previous"):
                raise InstallError(f"unverified instruction recovery record; inspect {work}")
            ensure_plain_path(previous, label="previous instruction recovery file", directory=False)
            ensure_plain_path(proposed, label="proposed instruction recovery file", directory=False)
            raise InstallError(
                f"instruction recovery is required before retrying: {target} is missing; "
                f"previous user rules are at {previous}, proposed rules are at {proposed}; "
                f"inspect {work / 'operation.json'} before restoring either file"
            )
    override = home / "AGENTS.override.md"
    _, text, _, _, _ = _read_agents(override)
    return override if text.strip() else home / "AGENTS.md"


def _frontmatter_end(text: str) -> int:
    """Return the end of an opening YAML block without parsing or rewriting it.

    A delimiter inside an indented YAML scalar is not a closing delimiter.
    An unclosed opening block is ambiguous, so reject it before installation.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n").rstrip(" \t") != "---":
        return 0
    offset = len(lines[0])
    for line in lines[1:]:
        offset += len(line)
        if line.rstrip("\r\n").rstrip(" \t") in ("---", "..."):
            return offset
    raise InstallError("unterminated YAML front matter; refusing to change global instructions")


def _markdown_inline_blocks(text: str) -> Iterator[tuple[list[str], tuple[str, str] | None]]:
    block_start = re.compile(r"^ {0,3}(?:<!--|>|#{1,6}(?:[ \t]|$)|(?:[-+*]|1[.)])[ \t]+\S)")
    separator = re.compile(r" {0,3}(?:([*_-])(?:[ \t]*\1){2,}|[=-]+)[ \t]*")
    paragraph = []
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        fence = None
        if marker:
            run, suffix = marker.groups()
            if run[0] == "~" or "`" not in suffix:
                fence = (run, suffix)
        if not line.strip() or fence or block_start.match(line) or separator.fullmatch(line):
            if paragraph:
                yield paragraph, None
                paragraph = []
            yield [line], fence
        else:
            paragraph.append(line)
    if paragraph:
        yield paragraph, None


def _visible_instruction_lines(text: str) -> Iterator[str]:
    # Inline spans can cross soft line breaks. Match equal-length backtick
    # runs within each paragraph before interpreting HTML comment delimiters.
    fence = ""
    in_comment = False
    for block, marker in _markdown_inline_blocks(text):
        if not in_comment:
            if marker:
                run, suffix = marker
                if not fence:
                    fence = run
                elif run[0] == fence[0] and len(run) >= len(fence) and not suffix.strip():
                    fence = ""
                continue
            if fence:
                continue
        last_tick = {
            len(mark[0]): (number, mark.start())
            for number, line in enumerate(block)
            for mark in re.finditer(r"`+", line)
        }
        ticks = 0
        for number, line in enumerate(block):
            starts_in_code_span = bool(ticks)
            if not in_comment and "`" not in line and "<!--" not in line:
                if not starts_in_code_span:
                    yield line
                continue
            visible = []
            start = 0
            for mark in re.finditer(r"`+|<!--|-->", line):
                token = mark[0]
                if in_comment:
                    if token == "-->":
                        in_comment = False
                        start = mark.end()
                elif token.startswith("`"):
                    width = len(token)
                    if ticks == width:
                        ticks = 0
                    elif not ticks and last_tick[width] > (number, mark.start()):
                        ticks = width
                elif token == "<!--" and not ticks:
                    visible.append(line[start:mark.start()])
                    in_comment = True
            if not in_comment:
                visible.append(line[start:])
            if not starts_in_code_span:
                yield "".join(visible)


def _has_default_invocation(text: str) -> bool:
    for line in _visible_instruction_lines(text[_frontmatter_end(text):]):
        if line == DEFAULT_INVOCATION_LINE:
            return True
        for prefix in USER_GLOBAL_INVOCATION_PREFIXES:
            if not line.startswith(prefix):
                continue
            remainder = line[len(prefix) :]
            if not remainder or remainder[0] in INVOCATION_SEPARATOR_PUNCTUATION:
                return True
    return False


def _prepare_default_invocation(agents_path: Path) -> tuple[bytes | None, bytes | None, int]:
    original, text, has_bom, newline, mode = _read_agents(agents_path)
    if _has_default_invocation(text):
        return original, None, mode

    first_line = text.splitlines()[0] if text else ""
    frontmatter_end = _frontmatter_end(text)
    if frontmatter_end:
        prefix, body = text[:frontmatter_end], text[frontmatter_end:]
        # Keep metadata at byte zero (after a preserved BOM) and unchanged.
        # Separate the new instruction from both delimiters and existing body.
        separator = newline if prefix.endswith(("\n", "\r")) else newline * 2
        updated = f"{prefix}{separator}{DEFAULT_INVOCATION_LINE}{newline}{newline}{body}"
    elif "`" in first_line or "<!--" in first_line or re.match(r"^ {0,3}~{3,}", first_line):
        # The first line could open markup that continues across the next line.
        updated = f"{DEFAULT_INVOCATION_LINE}{newline}{newline}{text}"
    elif text:
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
    if len(replacement) > MAX_AGENTS_BYTES:
        raise InstallError("updated global AGENTS.md exceeds 1 MiB")
    if original is not None:
        _updates.preflight_existing(agents_path, expected=original)
    return original, replacement, mode


def _preflight_result(agents_path: Path, replacement: bytes | None) -> dict[str, Any]:
    return {
        "ok": True,
        "action": "agents_default_present" if replacement is None else "agents_default_ready",
        "agents_path": str(agents_path),
    }


def _apply_default_invocation(agents_path: Path, original: bytes | None,
                              replacement: bytes | None, mode: int) -> dict[str, Any]:
    recovery: dict[str, str] | None = None
    if replacement is not None:
        recovery = _atomic_replace(
            agents_path, expected_original=original, replacement=replacement, mode=mode,
        )
    elif _read_agents(agents_path)[0] != original:
        raise InstallError("global AGENTS.md changed after it was read")
    return {
        "ok": True,
        "action": "agents_default_added" if replacement is not None else "agents_default_present",
        "modified": replacement is not None,
        "agents_path": str(agents_path),
        "line": DEFAULT_INVOCATION_LINE,
        **(recovery or {}),
    }


def ensure_default_invocation(codex_home: Path | None = None) -> dict[str, Any]:
    home = resolve_codex_home(codex_home)
    ensure_plain_path(home, label="Codex home", directory=True)
    with update_lock(home / "AGENTS.md"):
        target = effective_agents_path(home)
        return _apply_default_invocation(target, *_prepare_default_invocation(target))


def preflight_default_invocation(codex_home: Path | None = None) -> dict[str, Any]:
    home = resolve_codex_home(codex_home)
    ensure_plain_path(home, label="Codex home", directory=True)
    with update_lock(home / "AGENTS.md"):
        target = effective_agents_path(home)
        _, replacement, _ = _prepare_default_invocation(target)
        return _preflight_result(target, replacement)


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _cli_listing(command: list[str], key: str, runner: Runner,
                 options: dict[str, Any]) -> list[Any]:
    result = runner(command, **options)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no diagnostic").strip()
        raise InstallError(f"Codex {key} lookup failed with exit code {result.returncode}: {detail}")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, RecursionError) as exc:
        raise InstallError(f"Codex {key} lookup returned invalid JSON") from exc
    entries = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise InstallError(f"Codex lookup did not return the {key} list")
    return entries


def _verify_cli_marketplace(executable: str, marketplace: str, marketplace_path: Path,
                           runner: Runner, options: dict[str, Any]) -> None:
    entries = _cli_listing([executable, "plugin", "marketplace", "list", "--json"],
                           "marketplaces", runner, options)
    roots = [entry.get("root") for entry in entries
             if isinstance(entry, dict) and entry.get("name") == marketplace]
    if (len(roots) != 1 or not isinstance(roots[0], str) or "\x00" in roots[0]
            or not Path(roots[0]).is_absolute()):
        raise InstallError(f"Codex did not resolve one local root for marketplace {marketplace!r}")
    selected = Path(roots[0]) / ".agents" / "plugins" / "marketplace.json"
    if selected.resolve() != marketplace_path.expanduser().resolve():
        raise InstallError(f"Codex selected a different marketplace file: {selected}")


def _verify_installed(executable: str, marketplace: str, plugin_root: Path, version: str,
                      runner: Runner, options: dict[str, Any]) -> None:
    entries = _cli_listing([executable, "plugin", "list", "--marketplace", marketplace, "--json"],
                           "installed", runner, options)
    matches = [entry for entry in entries if isinstance(entry, dict)
               and entry.get("pluginId") == f"{PLUGIN_NAME}@{marketplace}"]
    if len(matches) != 1:
        raise InstallError("Codex did not report exactly one installed copy of the requested plugin")
    entry = matches[0]
    if entry.get("installed") is not True or entry.get("enabled") is not True:
        raise InstallError("Codex did not confirm that the requested plugin is installed and enabled")
    if entry.get("version") != version:
        raise InstallError(f"Codex reports installed version {entry.get('version')!r}, expected {version!r}")
    source = entry.get("source")
    if not isinstance(source, dict) or source.get("source") != "local":
        raise InstallError("Codex did not report a local source for the installed plugin")
    path = source.get("path")
    if (not isinstance(path, str) or "\x00" in path or not Path(path).is_absolute()
            or Path(path).resolve() != plugin_root.expanduser().resolve()):
        raise InstallError("Codex reports a different source for the installed plugin")


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
    environment["CODEX_HOME"] = str(home)
    options = dict(capture_output=True, text=True, encoding="utf-8", errors="replace",
                   env=environment, check=False)
    # One home-level lock coordinates both files, including older helpers that
    # only knew about AGENTS.md. Never edit an inactive base behind an override.
    with update_lock(home / "AGENTS.md"):
        agents_path = effective_agents_path(home)
        prepared = _prepare_default_invocation(agents_path)
        agents_preflight = _preflight_result(agents_path, prepared[1])
        _verify_cli_marketplace(executable, marketplace, verified_marketplace_path, runner, options)
        verify_marketplace_source(
            verified_marketplace_path, marketplace=marketplace, plugin_root=plugin_root,
        )
        completed = runner(command, **options)
        if completed.returncode != 0:
            detail = (
                completed.stderr or completed.stdout or "unknown install failure"
            ).strip()
            raise InstallError(
                f"plugin install failed with exit code {completed.returncode}: {detail}"
            )
        try:
            _verify_installed(executable, marketplace, plugin_root, version, runner, options)
            verify_marketplace_source(
                verified_marketplace_path, marketplace=marketplace, plugin_root=plugin_root,
            )
            if read_manifest(plugin_root) != (name, version):
                raise InstallError("plugin identity or version changed during installation")
            if effective_agents_path(home) != agents_path:
                raise InstallError("active global instructions changed during installation")
            agents_result = _apply_default_invocation(agents_path, *prepared)
        except (OSError, InstallError) as exc:
            raise InstallError(
                f"Codex plugin add succeeded, but global activation could not be confirmed: {exc}"
            ) from exc
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
