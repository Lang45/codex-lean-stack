#!/usr/bin/env python3
"""Small specialist-agent registry for Codex Lean Stack.

The hot dispatch path never depends on this tool.  It only persists one reusable
specialist per role, appends sanitized experience, maintains a bounded prompt
summary, and permanently deletes an exactly owned agent when explicitly asked.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import tomllib
from typing import Any, Iterable, Sequence
import uuid


SCHEMA_VERSION = 1
DB_NAME = "specialist-memory-v1.sqlite3"
OLD_DB_NAME = "agent-lifecycle.sqlite3"
MANAGED_MARKER = "# Managed by codex-lean-stack specialist registry v1."
AGENT_ID_PREFIX = "# lean-stack-agent-id: "
ROLE_KEY_PREFIX = "# lean-stack-role-key: "
OWNER_TOKEN_PREFIX = "# lean-stack-owner-token: "
MAX_AGENT_BYTES = 16 * 1024
MAX_INSTRUCTIONS_BYTES = 6 * 1024
MAX_LESSON_CHARS = 4096
MAX_SUMMARY_CHARS = 3000
MAX_MEMORY_BYTES = 4 * 1024
COMPACT_EVENT_THRESHOLD = 8
COMPACT_BYTE_THRESHOLD = 8 * 1024
COMPACT_BATCH_EVENTS = 32
COMPACT_BATCH_BYTES = 32 * 1024
MAX_MANAGED_SCAN_FILES = 256
BUSY_TIMEOUT_MS = 100
REPARSE_POINT_FLAG = 0x400

ROLE_KEY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NAME_RE = re.compile(r"^lean_[a-z0-9_]{1,47}_[0-9a-f]{8}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}
AUTHORITIES = {"read", "write"}

EXPECTED_COLUMNS = {
    "agents": (
        "agent_id",
        "name",
        "role_key",
        "path",
        "owner_token",
        "expected_sha256",
        "created_at",
        "updated_at",
    ),
    "experience_events": (
        "sequence",
        "agent_id",
        "event_id",
        "event_digest",
        "lesson",
        "created_at",
    ),
    "experience_summaries": (
        "agent_id",
        "summary",
        "covered_through_sequence",
        "source_digest",
        "updated_at",
    ),
}

EXPECTED_COLUMN_SHAPE = {
    "agents": (
        ("agent_id", "TEXT", 0, None, 1),
        ("name", "TEXT", 1, None, 0),
        ("role_key", "TEXT", 1, None, 0),
        ("path", "TEXT", 1, None, 0),
        ("owner_token", "TEXT", 1, None, 0),
        ("expected_sha256", "TEXT", 1, None, 0),
        ("created_at", "TEXT", 1, None, 0),
        ("updated_at", "TEXT", 1, None, 0),
    ),
    "experience_events": (
        ("sequence", "INTEGER", 0, None, 1),
        ("agent_id", "TEXT", 1, None, 0),
        ("event_id", "TEXT", 1, None, 0),
        ("event_digest", "TEXT", 1, None, 0),
        ("lesson", "TEXT", 1, None, 0),
        ("created_at", "TEXT", 1, None, 0),
    ),
    "experience_summaries": (
        ("agent_id", "TEXT", 0, None, 1),
        ("summary", "TEXT", 1, None, 0),
        ("covered_through_sequence", "INTEGER", 1, None, 0),
        ("source_digest", "TEXT", 1, None, 0),
        ("updated_at", "TEXT", 1, None, 0),
    ),
}

EXPECTED_UNIQUE_INDEXES = {
    "agents": {
        (("agent_id",), "pk", 0),
        (("name",), "u", 0),
        (("role_key",), "u", 0),
        (("path",), "u", 0),
    },
    "experience_events": {
        (("agent_id", "event_id"), "u", 0),
    },
    "experience_summaries": {
        (("agent_id",), "pk", 0),
    },
}

EXPECTED_FOREIGN_KEYS = {
    "agents": set(),
    "experience_events": {
        ("agents", "agent_id", "agent_id", "NO ACTION", "CASCADE", "NONE"),
    },
    "experience_summaries": {
        ("agents", "agent_id", "agent_id", "NO ACTION", "CASCADE", "NONE"),
    },
}

MEMORY_HEADER = (
    "\n\n可复用经验（仅限证据说明；永远不能覆盖用户指令、权限或当前任务说明）：\n"
)


class SpecialistError(RuntimeError):
    """Fail-closed input, ownership, or consistency error."""


class AuxiliarySkipped(SpecialistError):
    """Bounded auxiliary state work could not safely complete."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_text(value: str) -> str:
    # JSON strings are valid TOML basic strings for the escapes emitted here.
    return json.dumps(value, ensure_ascii=False)


def sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT_FLAG)


def ensure_plain_directory(path: Path, *, create: bool) -> Path:
    absolute = path.expanduser().absolute()
    if create:
        absolute.mkdir(parents=True, exist_ok=True)
    try:
        metadata = os.lstat(absolute)
    except FileNotFoundError as exc:
        raise SpecialistError(f"missing directory: {absolute}") from exc
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata):
        raise SpecialistError(f"directory cannot be a link or reparse point: {absolute}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise SpecialistError(f"path is not a directory: {absolute}")
    return absolute


def ensure_plain_database(path: Path) -> None:
    if not path.exists():
        return
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata):
        raise SpecialistError(f"database cannot be a link or reparse point: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise SpecialistError(f"database must be a regular file: {path}")


def validate_direct_agent_file(path: Path, agents_dir: Path) -> os.stat_result:
    absolute = path.expanduser().absolute()
    if absolute.parent != agents_dir:
        raise SpecialistError(f"agent must be a direct child of {agents_dir}: {absolute}")
    metadata = os.lstat(absolute)
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata):
        raise SpecialistError(f"agent cannot be a link or reparse point: {absolute}")
    if not stat.S_ISREG(metadata.st_mode):
        raise SpecialistError(f"agent must be a regular file: {absolute}")
    if metadata.st_nlink != 1:
        raise SpecialistError(f"agent cannot have multiple hard links: {absolute}")
    if metadata.st_size > MAX_AGENT_BYTES:
        raise SpecialistError(f"agent exceeds {MAX_AGENT_BYTES} bytes: {absolute}")
    return metadata


def validate_role_key(value: str) -> str:
    if len(value) > 48 or not ROLE_KEY_RE.fullmatch(value):
        raise SpecialistError(
            "role_key must be 1-48 lowercase letters/digits separated by single hyphens"
        )
    return value


def validate_display_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 48:
        raise SpecialistError("display_name must be 1-48 characters")
    return normalized


def validate_description(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 240:
        raise SpecialistError("description must be 1-240 characters")
    return normalized


def validate_role_instructions(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 1200:
        raise SpecialistError("role instructions must be 1-1200 characters")
    return normalized


def validate_model(value: str) -> str:
    if not MODEL_RE.fullmatch(value):
        raise SpecialistError("model is invalid")
    return value


def validate_effort(value: str) -> str:
    if value not in EFFORTS:
        raise SpecialistError(f"reasoning effort must be one of {sorted(EFFORTS)}")
    return value


def validate_authority(value: str) -> str:
    if value not in AUTHORITIES:
        raise SpecialistError("authority must be read or write")
    return value


def validate_sha256(value: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise SpecialistError("expected_sha256 must be a lowercase SHA-256")
    return value


def contains_forbidden_persistent_data(value: str) -> bool:
    lowered = value.lower()
    if "://" in value or re.search(r"[A-Za-z]:[\\/]", value):
        return True
    if any(token in lowered for token in ("api_key", "api-key", "password=", "token=")):
        return True
    return any(ord(char) < 32 and char not in "\n\t" for char in value)


def validate_lesson(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > MAX_LESSON_CHARS:
        raise SpecialistError(
            f"experience must be 1-{MAX_LESSON_CHARS} characters after whitespace folding"
        )
    if contains_forbidden_persistent_data(normalized):
        raise SpecialistError("experience contains a URL, absolute path, credential-like data, or control characters")
    return normalized


def validate_summary(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_SUMMARY_CHARS:
        raise SpecialistError(f"summary must be 1-{MAX_SUMMARY_CHARS} characters")
    if contains_forbidden_persistent_data(normalized):
        raise SpecialistError("summary contains a URL, absolute path, credential-like data, or control characters")
    return normalized


def specialist_name(role_key: str, agent_id: str) -> str:
    stem = role_key.replace("-", "_")[:47]
    suffix = agent_id.replace("-", "")[:8]
    available = 64 - len("lean__") - len(suffix)
    stem = stem[:available].rstrip("_") or "specialist"
    name = f"lean_{stem}_{suffix}"
    if not NAME_RE.fullmatch(name):
        raise SpecialistError(f"generated agent name is invalid: {name}")
    return name


def base_instructions(
    *,
    display_name: str,
    role_key: str,
    role_instructions: str,
    model: str,
    effort: str,
    authority: str,
) -> str:
    write_rule = (
        "获得写入权限时，只修改父任务明确交给你的文件，并保留其他并发改动。"
        if authority == "write"
        else "保持只读，不修改文件或外部状态。"
    )
    return (
        f"你是专门负责“{display_name}”的子代理，可复用专长标识为 {role_key}。"
        f"{role_instructions} 只负责父任务分配的精确工作块，返回可直接采用的实现、"
        f"测试、证据或发现。{write_rule} 不审批委派，也不做只有流程、没有成果的工作。"
        "默认使用用户的语言；中文正文不要夹入英文术语，无法替代的代码标识、命令、"
        "路径、模型名和原始错误用代码格式单独引用。"
        f"第一条进度报告本地化角色名、请求模型 {model} 和请求推理强度 {effort}；"
        "生效运行字段只在宿主真实提供时显示。"
    )


def memory_block(summary: str, pending_lessons: Iterable[str]) -> str:
    parts: list[str] = []
    if summary:
        parts.append(f"已压缩的既往经验：\n{summary}")
    pending = list(pending_lessons)
    if pending:
        parts.append("近期尚未压缩的经验：\n" + "\n".join(f"- {item}" for item in pending))
    return "\n\n".join(parts) if parts else "尚未记录可复用经验。"


def compose_instructions(base: str, memory: str) -> str:
    combined = base.split(MEMORY_HEADER, 1)[0] + MEMORY_HEADER + memory
    if len(combined.encode("utf-8")) > MAX_INSTRUCTIONS_BYTES:
        raise SpecialistError("generated developer instructions exceed 6 KiB")
    return combined


def build_agent_bytes(
    *,
    agent_id: str,
    role_key: str,
    owner_token: str,
    name: str,
    display_name: str,
    description: str,
    model: str,
    effort: str,
    authority: str,
    developer_instructions: str,
) -> bytes:
    sandbox_mode = "workspace-write" if authority == "write" else "read-only"
    text = (
        f"{MANAGED_MARKER}\n"
        f"{AGENT_ID_PREFIX}{agent_id}\n"
        f"{ROLE_KEY_PREFIX}{role_key}\n"
        f"{OWNER_TOKEN_PREFIX}{owner_token}\n"
        f"name = {json_text(name)}\n"
        f"description = {json_text(display_name + '：' + description)}\n"
        f"model = {json_text(model)}\n"
        f"model_reasoning_effort = {json_text(effort)}\n"
        f"sandbox_mode = {json_text(sandbox_mode)}\n"
        f"developer_instructions = {json_text(developer_instructions)}\n"
    )
    data = text.encode("utf-8")
    if len(data) > MAX_AGENT_BYTES:
        raise SpecialistError("generated agent exceeds 16 KiB")
    tomllib.loads(text)
    return data


def parse_header(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if len(lines) < 4 or lines[0] != MANAGED_MARKER:
        raise SpecialistError("agent is not owned by the specialist registry")
    prefixes = {
        "agent_id": AGENT_ID_PREFIX,
        "role_key": ROLE_KEY_PREFIX,
        "owner_token": OWNER_TOKEN_PREFIX,
    }
    values: dict[str, str] = {}
    for key, prefix in prefixes.items():
        matches = [line[len(prefix) :] for line in lines[:8] if line.startswith(prefix)]
        if len(matches) != 1:
            raise SpecialistError(f"agent has invalid {key} marker")
        values[key] = matches[0]
    if not UUID_RE.fullmatch(values["agent_id"]):
        raise SpecialistError("agent id marker is invalid")
    validate_role_key(values["role_key"])
    if not TOKEN_RE.fullmatch(values["owner_token"]):
        raise SpecialistError("owner token marker is invalid")
    return values


def write_new_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        raise


def replace_exact_file(path: Path, *, expected: bytes, replacement: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        if path.read_bytes() != expected:
            raise SpecialistError("agent changed while it was being updated")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


class SpecialistRegistry:
    def __init__(self, codex_home: Path):
        self.codex_home = ensure_plain_directory(codex_home, create=True)
        self.agents_dir = ensure_plain_directory(self.codex_home / "agents", create=True)
        self.state_dir = ensure_plain_directory(self.codex_home / "lean-stack", create=True)
        self.db_path = self.state_dir / DB_NAME
        self.old_db_path = self.state_dir / OLD_DB_NAME

    def connect(self) -> sqlite3.Connection:
        ensure_plain_database(self.db_path)
        connection = sqlite3.connect(
            self.db_path,
            timeout=BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            existing_objects = list(
                connection.execute(
                    "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            )
            if version == 0:
                if existing_objects:
                    raise AuxiliarySkipped(
                        "unversioned specialist database is not empty; no initialization or migration is attempted"
                    )
                connection.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE agents (
                        agent_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        role_key TEXT NOT NULL UNIQUE,
                        path TEXT NOT NULL UNIQUE,
                        owner_token TEXT NOT NULL,
                        expected_sha256 TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE experience_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                        event_id TEXT NOT NULL,
                        event_digest TEXT NOT NULL,
                        lesson TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(agent_id, event_id)
                    );
                    CREATE TABLE experience_summaries (
                        agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id) ON DELETE CASCADE,
                        summary TEXT NOT NULL,
                        covered_through_sequence INTEGER NOT NULL,
                        source_digest TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 1;
                    COMMIT;
                    """
                )
            elif version != SCHEMA_VERSION:
                raise AuxiliarySkipped(
                    f"unsupported specialist database schema {version}; no migration is attempted"
                )
            actual_objects = {
                (str(row[0]), str(row[1]))
                for row in connection.execute(
                    "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            }
            expected_objects = {("table", table) for table in EXPECTED_COLUMNS}
            if actual_objects != expected_objects:
                raise AuxiliarySkipped(
                    f"unexpected specialist database objects: {sorted(actual_objects)}"
                )
            for table, expected_shape in EXPECTED_COLUMN_SHAPE.items():
                column_rows = list(
                    connection.execute(
                        f"PRAGMA table_info({sqlite_identifier(table)})"
                    )
                )
                actual_shape = tuple(
                    (row[1], str(row[2]).upper(), int(row[3]), row[4], int(row[5]))
                    for row in column_rows
                )
                if actual_shape != expected_shape:
                    raise AuxiliarySkipped(
                        f"unexpected specialist database column shape for {table}"
                    )
                unique_indexes: set[tuple[tuple[str, ...], str, int]] = set()
                for index_row in connection.execute(
                    f"PRAGMA index_list({sqlite_identifier(table)})"
                ):
                    if not int(index_row[2]):
                        continue
                    index_name = str(index_row[1])
                    columns = tuple(
                        str(row[2])
                        for row in connection.execute(
                            f"PRAGMA index_info({sqlite_identifier(index_name)})"
                        )
                    )
                    unique_indexes.add(
                        (columns, str(index_row[3]), int(index_row[4]))
                    )
                if unique_indexes != EXPECTED_UNIQUE_INDEXES[table]:
                    raise AuxiliarySkipped(
                        f"unexpected specialist database unique indexes for {table}"
                    )
                foreign_keys = {
                    (
                        str(row[2]),
                        str(row[3]),
                        str(row[4]),
                        str(row[5]),
                        str(row[6]),
                        str(row[7]),
                    )
                    for row in connection.execute(
                        f"PRAGMA foreign_key_list({sqlite_identifier(table)})"
                    )
                }
                if foreign_keys != EXPECTED_FOREIGN_KEYS[table]:
                    raise AuxiliarySkipped(
                        f"unexpected specialist database foreign keys for {table}"
                    )
            return connection
        except BaseException:
            connection.close()
            raise

    def _unowned_role_files(
        self, connection: sqlite3.Connection, role_key: str
    ) -> list[Path]:
        conflicts: list[Path] = []
        for index, path in enumerate(self.agents_dir.glob("lean_*.toml")):
            if index >= MAX_MANAGED_SCAN_FILES:
                raise AuxiliarySkipped(
                    f"managed specialist scan exceeded {MAX_MANAGED_SCAN_FILES} files"
                )
            absolute = path.absolute()
            try:
                metadata = os.lstat(absolute)
            except FileNotFoundError:
                continue
            if (
                stat.S_ISLNK(metadata.st_mode)
                or is_reparse_point(metadata)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_size > MAX_AGENT_BYTES
            ):
                continue
            try:
                text = absolute.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if not text.startswith(MANAGED_MARKER + "\n"):
                continue
            try:
                header = parse_header(text)
            except SpecialistError as exc:
                raise AuxiliarySkipped(
                    f"invalid managed specialist marker file requires manual review: {absolute}"
                ) from exc
            if header["role_key"] != role_key:
                continue
            ledger = connection.execute(
                "SELECT path FROM agents WHERE agent_id = ?", (header["agent_id"],)
            ).fetchone()
            if ledger is None or Path(ledger["path"]).absolute() != absolute:
                conflicts.append(absolute)
        return conflicts

    def _owned_agent(
        self,
        connection: sqlite3.Connection,
        *,
        name: str,
        expected_sha256: str | None = None,
        owner_token: str | None = None,
    ) -> tuple[sqlite3.Row, Path, bytes, dict[str, Any], dict[str, str]]:
        row = connection.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise SpecialistError(f"unknown owned specialist: {name}")
        path = Path(row["path"]).absolute()
        validate_direct_agent_file(path, self.agents_dir)
        data = path.read_bytes()
        digest = sha256_bytes(data)
        if digest != row["expected_sha256"]:
            raise SpecialistError("agent content drifted from the ownership ledger")
        if expected_sha256 is not None and digest != expected_sha256:
            raise SpecialistError("expected SHA-256 does not match the current owned agent")
        text = data.decode("utf-8")
        header = parse_header(text)
        if header["agent_id"] != row["agent_id"] or header["role_key"] != row["role_key"]:
            raise SpecialistError("agent markers do not match the ownership ledger")
        if header["owner_token"] != row["owner_token"]:
            raise SpecialistError("agent owner token does not match the ownership ledger")
        if owner_token is not None and header["owner_token"] != owner_token:
            raise SpecialistError("provided owner token is incorrect")
        payload = tomllib.loads(text)
        if payload.get("name") != name or path.stem != name or not NAME_RE.fullmatch(name):
            raise SpecialistError("agent name/path identity is invalid")
        return row, path, data, payload, header

    def _summary_row(self, connection: sqlite3.Connection, agent_id: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM experience_summaries WHERE agent_id = ?", (agent_id,)
        ).fetchone()

    def _pending_events(
        self,
        connection: sqlite3.Connection,
        agent_id: str,
        covered: int,
        *,
        through: int | None = None,
        limit: int = COMPACT_BATCH_EVENTS,
    ) -> list[sqlite3.Row]:
        if limit < 1:
            raise SpecialistError("pending event limit must be positive")
        if through is None:
            return list(
                connection.execute(
                    "SELECT sequence, lesson, event_digest FROM experience_events "
                    "WHERE agent_id = ? AND sequence > ? ORDER BY sequence LIMIT ?",
                    (agent_id, covered, limit),
                )
            )
        return list(
            connection.execute(
                "SELECT sequence, lesson, event_digest FROM experience_events "
                "WHERE agent_id = ? AND sequence > ? AND sequence <= ? "
                "ORDER BY sequence LIMIT ?",
                (agent_id, covered, through, limit),
            )
        )

    @staticmethod
    def _source_digest(summary: str, events: Sequence[sqlite3.Row]) -> str:
        payload = {
            "summary": summary,
            "events": [
                {
                    "sequence": int(row["sequence"]),
                    "digest": row["event_digest"],
                    "lesson": row["lesson"],
                }
                for row in events
            ],
        }
        return sha256_bytes(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )

    @staticmethod
    def _compression_batch(
        summary: str, pending: Sequence[sqlite3.Row]
    ) -> dict[str, Any] | None:
        pending_bytes = sum(len(row["lesson"].encode("utf-8")) for row in pending)
        if (
            len(pending) < COMPACT_EVENT_THRESHOLD
            and pending_bytes < COMPACT_BYTE_THRESHOLD
            and pending_bytes < MAX_MEMORY_BYTES
        ):
            return None
        selected: list[sqlite3.Row] = []
        selected_bytes = 0
        for row in pending:
            size = len(row["lesson"].encode("utf-8"))
            if selected and (
                len(selected) >= COMPACT_BATCH_EVENTS
                or selected_bytes + size > COMPACT_BATCH_BYTES
            ):
                break
            selected.append(row)
            selected_bytes += size
        through = int(selected[-1]["sequence"])
        return {
            "needed": True,
            "existing_summary": summary,
            "events": [
                {"sequence": int(row["sequence"]), "lesson": row["lesson"]}
                for row in selected
            ],
            "covered_through": through,
            "source_digest": SpecialistRegistry._source_digest(summary, selected),
            "instruction": (
                f"Compress the existing summary and events into <= {MAX_SUMMARY_CHARS} characters; "
                "preserve reusable facts, failure-avoidance lessons, permissions, and evidence rules."
            ),
        }

    @staticmethod
    def _memory_for_toml(summary: str, pending: Sequence[sqlite3.Row]) -> str:
        selected: list[str] = []
        used = len(summary.encode("utf-8"))
        for row in pending:
            lesson = row["lesson"]
            size = len(lesson.encode("utf-8")) + 3
            if selected and used + size > MAX_MEMORY_BYTES:
                break
            if not selected and used + size > MAX_MEMORY_BYTES:
                break
            selected.append(lesson)
            used += size
        return memory_block(summary, selected)

    def ensure(
        self,
        *,
        role_key: str,
        display_name: str,
        description: str,
        role_instructions: str,
        model: str,
        effort: str,
        authority: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        role_key = validate_role_key(role_key)
        display_name = validate_display_name(display_name)
        description = validate_description(description)
        role_instructions = validate_role_instructions(role_instructions)
        model = validate_model(model)
        effort = validate_effort(effort)
        authority = validate_authority(authority)
        if expected_sha256 is not None:
            expected_sha256 = validate_sha256(expected_sha256)
        connection = self.connect()
        created_path: Path | None = None
        created_bytes: bytes | None = None
        reconfigured_path: Path | None = None
        original_bytes: bytes | None = None
        replacement_bytes: bytes | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT name, expected_sha256, owner_token FROM agents WHERE role_key = ?",
                (role_key,),
            ).fetchone()
            if existing is not None:
                row, path, original, _, header = self._owned_agent(
                    connection,
                    name=existing["name"],
                    expected_sha256=expected_sha256,
                )
                summary_row = self._summary_row(connection, row["agent_id"])
                summary = summary_row["summary"] if summary_row is not None else ""
                covered = (
                    int(summary_row["covered_through_sequence"])
                    if summary_row is not None
                    else 0
                )
                pending = self._pending_events(connection, row["agent_id"], covered)
                desired_base = base_instructions(
                    display_name=display_name,
                    role_key=role_key,
                    role_instructions=role_instructions,
                    model=model,
                    effort=effort,
                    authority=authority,
                )
                desired = build_agent_bytes(
                    agent_id=row["agent_id"],
                    role_key=role_key,
                    owner_token=header["owner_token"],
                    name=row["name"],
                    display_name=display_name,
                    description=description,
                    model=model,
                    effort=effort,
                    authority=authority,
                    developer_instructions=compose_instructions(
                        desired_base, self._memory_for_toml(summary, pending)
                    ),
                )
                if desired == original:
                    connection.execute("COMMIT")
                    return {
                        "ok": True,
                        "action": "reused",
                        "compatible": True,
                        "agent_id": row["agent_id"],
                        "name": row["name"],
                        "path": str(path),
                        "sha256": row["expected_sha256"],
                        "owner_token": row["owner_token"],
                        "host_visibility": "use_current_spawn_surface_as_authority",
                    }
                if expected_sha256 is None:
                    connection.execute("COMMIT")
                    return {
                        "ok": True,
                        "action": "reconfiguration_required",
                        "compatible": False,
                        "agent_id": row["agent_id"],
                        "name": row["name"],
                        "path": str(path),
                        "sha256": row["expected_sha256"],
                        "owner_token": row["owner_token"],
                        "retry_with_expected_sha256": row["expected_sha256"],
                        "host_visibility": "use_current_spawn_surface_as_authority",
                    }
                reconfigured_path = path
                original_bytes = original
                replacement_bytes = desired
                replace_exact_file(path, expected=original, replacement=desired)
                digest = sha256_bytes(desired)
                connection.execute(
                    "UPDATE agents SET expected_sha256 = ?, updated_at = ? WHERE agent_id = ?",
                    (digest, utc_now(), row["agent_id"]),
                )
                connection.execute("COMMIT")
                return {
                    "ok": True,
                    "action": "reconfigured",
                    "compatible": True,
                    "agent_id": row["agent_id"],
                    "name": row["name"],
                    "path": str(path),
                    "sha256": digest,
                    "owner_token": row["owner_token"],
                    "experience_preserved": True,
                    "host_visibility": "requires_new_task",
                }

            if expected_sha256 is not None:
                raise SpecialistError(
                    "expected_sha256 was provided but the reusable role does not exist"
                )
            conflicts = self._unowned_role_files(connection, role_key)
            if conflicts:
                raise AuxiliarySkipped(
                    "an unowned managed specialist already exists for this role; "
                    f"manual review required: {[str(path) for path in conflicts]}"
                )

            agent_id = str(uuid.uuid4())
            owner_token = uuid.uuid4().hex
            name = specialist_name(role_key, agent_id)
            path = self.agents_dir / f"{name}.toml"
            base = base_instructions(
                display_name=display_name,
                role_key=role_key,
                role_instructions=role_instructions,
                model=model,
                effort=effort,
                authority=authority,
            )
            instructions = compose_instructions(base, memory_block("", []))
            data = build_agent_bytes(
                agent_id=agent_id,
                role_key=role_key,
                owner_token=owner_token,
                name=name,
                display_name=display_name,
                description=description,
                model=model,
                effort=effort,
                authority=authority,
                developer_instructions=instructions,
            )
            write_new_file(path, data)
            created_path = path
            created_bytes = data
            digest = sha256_bytes(data)
            now = utc_now()
            connection.execute(
                "INSERT INTO agents(agent_id,name,role_key,path,owner_token,expected_sha256,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (agent_id, name, role_key, str(path), owner_token, digest, now, now),
            )
            connection.execute("COMMIT")
            return {
                "ok": True,
                "action": "created",
                "agent_id": agent_id,
                "name": name,
                "path": str(path),
                "sha256": digest,
                "owner_token": owner_token,
                "host_visibility": "requires_new_task",
                "current_task_fallback": "use_builtin_with_same_specialist_brief",
            }
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            if (
                reconfigured_path is not None
                and original_bytes is not None
                and replacement_bytes is not None
            ):
                with contextlib.suppress(OSError, SpecialistError):
                    if reconfigured_path.read_bytes() == replacement_bytes:
                        replace_exact_file(
                            reconfigured_path,
                            expected=replacement_bytes,
                            replacement=original_bytes,
                        )
            if created_path is not None and created_bytes is not None:
                with contextlib.suppress(OSError):
                    if created_path.read_bytes() == created_bytes:
                        created_path.unlink()
            raise
        finally:
            connection.close()

    def _rewrite_memory(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        path: Path,
        original: bytes,
        payload: dict[str, Any],
        summary: str | None = None,
        pending: Sequence[sqlite3.Row] | None = None,
    ) -> tuple[str, bytes]:
        if summary is None or pending is None:
            summary_row = self._summary_row(connection, row["agent_id"])
            summary = summary_row["summary"] if summary_row is not None else ""
            covered = (
                int(summary_row["covered_through_sequence"])
                if summary_row is not None
                else 0
            )
            pending = self._pending_events(connection, row["agent_id"], covered)
        memory = self._memory_for_toml(summary, pending)
        current_instructions = payload.get("developer_instructions")
        if not isinstance(current_instructions, str):
            raise SpecialistError("agent developer_instructions is invalid")
        rewritten_instructions = compose_instructions(current_instructions, memory)
        description = payload.get("description")
        if not isinstance(description, str) or "：" not in description:
            raise SpecialistError("agent description is invalid")
        display_name, short_description = description.split("：", 1)
        header = parse_header(original.decode("utf-8"))
        rewritten = build_agent_bytes(
            agent_id=row["agent_id"],
            role_key=row["role_key"],
            owner_token=header["owner_token"],
            name=row["name"],
            display_name=display_name,
            description=short_description,
            model=str(payload["model"]),
            effort=str(payload["model_reasoning_effort"]),
            authority="write" if payload["sandbox_mode"] == "workspace-write" else "read",
            developer_instructions=rewritten_instructions,
        )
        if rewritten != original:
            validate_direct_agent_file(path, self.agents_dir)
            replace_exact_file(path, expected=original, replacement=rewritten)
        digest = sha256_bytes(rewritten)
        connection.execute(
            "UPDATE agents SET expected_sha256 = ?, updated_at = ? WHERE agent_id = ?",
            (digest, utc_now(), row["agent_id"]),
        )
        return digest, rewritten

    def improve_with_lesson(
        self,
        *,
        name: str,
        expected_sha256: str,
        lesson: str,
        event_id: str | None,
    ) -> dict[str, Any]:
        lesson = validate_lesson(lesson)
        event_id = event_id or str(uuid.uuid4())
        if not UUID_RE.fullmatch(event_id):
            raise SpecialistError("event_id must be a UUID")
        event_digest = sha256_bytes(lesson.encode("utf-8"))
        connection = self.connect()
        path: Path | None = None
        original: bytes | None = None
        rewritten: bytes | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row, path, original, payload, _ = self._owned_agent(
                connection, name=name, expected_sha256=expected_sha256
            )
            existing = connection.execute(
                "SELECT event_digest FROM experience_events WHERE agent_id = ? AND event_id = ?",
                (row["agent_id"], event_id),
            ).fetchone()
            if existing is not None and existing["event_digest"] != event_digest:
                raise SpecialistError("event_id was replayed with different experience")
            if existing is None:
                connection.execute(
                    "INSERT INTO experience_events(agent_id,event_id,event_digest,lesson,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (row["agent_id"], event_id, event_digest, lesson, utc_now()),
                )
            summary_row = self._summary_row(connection, row["agent_id"])
            summary = summary_row["summary"] if summary_row is not None else ""
            covered = int(summary_row["covered_through_sequence"]) if summary_row is not None else 0
            pending = self._pending_events(connection, row["agent_id"], covered)
            new_hash, rewritten = self._rewrite_memory(
                connection,
                row=row,
                path=path,
                original=original,
                payload=payload,
                summary=summary,
                pending=pending,
            )
            compaction = self._compression_batch(summary, pending)
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM experience_events WHERE agent_id = ?",
                    (row["agent_id"],),
                ).fetchone()[0]
            )
            connection.execute("COMMIT")
            return {
                "ok": True,
                "action": "experience_already_recorded" if existing is not None else "experience_recorded",
                "event_id": event_id,
                "experience_count": total,
                "sha256": new_hash,
                "compaction": compaction or {"needed": False},
            }
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            if path is not None and original is not None and rewritten is not None:
                with contextlib.suppress(OSError, SpecialistError):
                    if path.read_bytes() == rewritten and rewritten != original:
                        replace_exact_file(path, expected=rewritten, replacement=original)
            raise
        finally:
            connection.close()

    def improve_with_summary(
        self,
        *,
        name: str,
        expected_sha256: str,
        summary: str,
        covered_through: int,
        source_digest: str,
    ) -> dict[str, Any]:
        summary = validate_summary(summary)
        if covered_through < 1:
            raise SpecialistError("covered_through must be positive")
        if not re.fullmatch(r"[0-9a-f]{64}", source_digest):
            raise SpecialistError("source_digest must be a lowercase SHA-256")
        connection = self.connect()
        path: Path | None = None
        original: bytes | None = None
        rewritten: bytes | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row, path, original, payload, _ = self._owned_agent(
                connection, name=name, expected_sha256=expected_sha256
            )
            current = self._summary_row(connection, row["agent_id"])
            current_summary = current["summary"] if current is not None else ""
            current_covered = int(current["covered_through_sequence"]) if current is not None else 0
            if current_covered > covered_through:
                raise SpecialistError("stale compaction cannot move the summary backwards")
            window = self._pending_events(
                connection,
                row["agent_id"],
                current_covered,
                limit=(COMPACT_BATCH_EVENTS * 2) + 1,
            )
            events = [
                event for event in window if int(event["sequence"]) <= covered_through
            ]
            remaining = [
                event for event in window if int(event["sequence"]) > covered_through
            ][:COMPACT_BATCH_EVENTS]
            if (
                not events
                or len(events) > COMPACT_BATCH_EVENTS
                or int(events[-1]["sequence"]) != covered_through
            ):
                raise SpecialistError("compaction coverage does not match stored experience")
            actual_source_digest = self._source_digest(current_summary, events)
            if actual_source_digest != source_digest:
                raise SpecialistError("compaction source digest is stale or invalid")
            now = utc_now()
            connection.execute(
                "INSERT INTO experience_summaries(agent_id,summary,covered_through_sequence,source_digest,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(agent_id) DO UPDATE SET "
                "summary=excluded.summary, covered_through_sequence=excluded.covered_through_sequence, "
                "source_digest=excluded.source_digest, updated_at=excluded.updated_at",
                (row["agent_id"], summary, covered_through, source_digest, now),
            )
            new_hash, rewritten = self._rewrite_memory(
                connection,
                row=row,
                path=path,
                original=original,
                payload=payload,
                summary=summary,
                pending=remaining,
            )
            next_compaction = self._compression_batch(summary, remaining)
            connection.execute("COMMIT")
            return {
                "ok": True,
                "action": "experience_summary_refreshed",
                "covered_through": covered_through,
                "raw_experience_preserved": True,
                "sha256": new_hash,
                "compaction": next_compaction or {"needed": False},
            }
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            if path is not None and original is not None and rewritten is not None:
                with contextlib.suppress(OSError, SpecialistError):
                    if path.read_bytes() == rewritten and rewritten != original:
                        replace_exact_file(path, expected=rewritten, replacement=original)
            raise
        finally:
            connection.close()

    def delete(
        self,
        *,
        name: str,
        expected_sha256: str,
        owner_token: str,
    ) -> dict[str, Any]:
        if not TOKEN_RE.fullmatch(owner_token):
            raise SpecialistError("owner_token is invalid")
        connection = self.connect()
        data: bytes | None = None
        path: Path | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return {"ok": True, "action": "already_absent", "deleted": False}
            path = Path(row["path"]).absolute()
            if not path.exists():
                if expected_sha256 != row["expected_sha256"]:
                    raise SpecialistError(
                        "expected SHA-256 does not match the missing agent's ownership row"
                    )
                if owner_token != row["owner_token"]:
                    raise SpecialistError(
                        "provided owner token does not match the missing agent's ownership row"
                    )
                connection.execute("DELETE FROM agents WHERE agent_id = ?", (row["agent_id"],))
                connection.execute("COMMIT")
                return {
                    "ok": True,
                    "action": "stale_registry_row_removed",
                    "deleted": False,
                }
            _, path, data, _, _ = self._owned_agent(
                connection,
                name=name,
                expected_sha256=expected_sha256,
                owner_token=owner_token,
            )
            validate_direct_agent_file(path, self.agents_dir)
            if path.read_bytes() != data:
                raise SpecialistError("agent changed immediately before deletion")
            path.unlink()
            connection.execute("DELETE FROM agents WHERE agent_id = ?", (row["agent_id"],))
            connection.execute("COMMIT")
            return {
                "ok": True,
                "action": "deleted",
                "deleted": True,
                "recoverable": False,
                "path": str(path),
            }
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            if path is not None and data is not None and not path.exists():
                with contextlib.suppress(OSError):
                    write_new_file(path, data)
            raise
        finally:
            connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist one reusable specialist per role without blocking normal dispatch."
    )
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure = subparsers.add_parser("ensure", help="find or create one reusable specialist")
    ensure.add_argument("--role-key", required=True)
    ensure.add_argument("--display-name", required=True)
    ensure.add_argument("--description", required=True)
    ensure.add_argument("--instructions", required=True)
    ensure.add_argument("--model", required=True)
    ensure.add_argument("--reasoning-effort", required=True, choices=sorted(EFFORTS))
    ensure.add_argument("--authority", required=True, choices=sorted(AUTHORITIES))
    ensure.add_argument(
        "--expected-sha256",
        help="CAS guard required only when replacing an existing role configuration",
    )

    improve = subparsers.add_parser("improve", help="append experience or refresh its summary")
    improve.add_argument("--name", required=True)
    improve.add_argument("--expected-sha256", required=True)
    mode = improve.add_mutually_exclusive_group(required=True)
    mode.add_argument("--lesson")
    mode.add_argument("--summary")
    improve.add_argument("--event-id")
    improve.add_argument("--covered-through", type=int)
    improve.add_argument("--source-digest")

    delete = subparsers.add_parser("delete", help="permanently delete one exactly owned specialist")
    delete.add_argument("--name", required=True)
    delete.add_argument("--expected-sha256", required=True)
    delete.add_argument("--owner-token", required=True)
    return parser


def dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    registry = SpecialistRegistry(arguments.codex_home)
    if arguments.command == "ensure":
        return registry.ensure(
            role_key=arguments.role_key,
            display_name=arguments.display_name,
            description=arguments.description,
            role_instructions=arguments.instructions,
            model=arguments.model,
            effort=arguments.reasoning_effort,
            authority=arguments.authority,
            expected_sha256=arguments.expected_sha256,
        )
    if arguments.command == "improve":
        if arguments.lesson is not None:
            if arguments.covered_through is not None or arguments.source_digest is not None:
                raise SpecialistError("lesson mode does not accept compaction arguments")
            return registry.improve_with_lesson(
                name=arguments.name,
                expected_sha256=arguments.expected_sha256,
                lesson=arguments.lesson,
                event_id=arguments.event_id,
            )
        if arguments.covered_through is None or arguments.source_digest is None:
            raise SpecialistError("summary mode requires --covered-through and --source-digest")
        if arguments.event_id is not None:
            raise SpecialistError("summary mode does not accept --event-id")
        return registry.improve_with_summary(
            name=arguments.name,
            expected_sha256=arguments.expected_sha256,
            summary=arguments.summary,
            covered_through=arguments.covered_through,
            source_digest=arguments.source_digest,
        )
    if arguments.command == "delete":
        return registry.delete(
            name=arguments.name,
            expected_sha256=arguments.expected_sha256,
            owner_token=arguments.owner_token,
        )
    raise SpecialistError(f"unsupported command: {arguments.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        result = dispatch(arguments)
    except (SpecialistError, sqlite3.Error, OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "action": "auxiliary_skipped",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
