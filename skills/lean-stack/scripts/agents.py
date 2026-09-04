#!/usr/bin/env python3
"""Small specialist-agent registry for Codex Lean Stack.

The hot dispatch path never depends on this tool.  It only persists one reusable
specialist per role, records idempotent successful survival rounds, appends
sanitized experience or corrections, maintains a bounded prompt summary, and
recoverably retires or explicitly restores an exactly owned unused agent.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
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
from typing import Any, Callable, Iterable, Sequence
import uuid


SCHEMA_VERSION = 4
GLOBAL_CONTRACT_VERSION = 1
GLOBAL_SCOPE = "codex-global-domain-v1"
DB_NAME = "specialist-memory-v1.sqlite3"
OLD_DB_NAME = "agent-lifecycle.sqlite3"
MANAGED_MARKER = "# Managed by codex-lean-stack specialist registry v1."
AGENT_ID_PREFIX = "# lean-stack-agent-id: "
ROLE_KEY_PREFIX = "# lean-stack-role-key: "
OWNER_TOKEN_PREFIX = "# lean-stack-owner-token: "
GLOBAL_SCOPE_PREFIX = "# lean-stack-scope: "
GLOBAL_DOMAIN_KEY_PREFIX = "# lean-stack-domain-key: "
GLOBAL_CONTRACT_DIGEST_PREFIX = "# lean-stack-contract-digest: "
GLOBAL_MIGRATION_JOURNAL = "global-domain-migration-v1.journal.json"
GLOBAL_MIGRATION_ARCHIVE_DIR = "global-domain-migration-v1"
GLOBAL_MIGRATION_PENDING_BACKUP_DIR = "全局领域迁移备份"
GLOBAL_MIGRATION_COMPLETION_KIND = "global-domain-migration-complete-v1"
MAX_MIGRATION_PLAN_BYTES = 512 * 1024
# Plugin-owned bounded-work safeguards; they are not Codex limits or user requirements.
MAX_AGENT_BYTES = 16 * 1024
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
PENDING_DELETION_DIR_NAME = "待删文件"
RESTORED_RECEIPT_DIR_NAME = "已恢复收据"
RETIREMENT_RECEIPT_FORMAT_VERSION = 2
MAX_RECEIPT_BYTES = 16 * 1024

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
SPEEDS = {"standard", "fast"}
INVOCATION_KINDS = {"spawn_agent", "followup_task"}
INTERNAL_MESSAGE_RUNTIME_ROUTE = (
    "require_luna_model_catalog_v2_then_use_direct_collaboration_send_message"
)

SCHEMA_V2_TABLE_SQL = {
    "agents": """
        CREATE TABLE agents (
            agent_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            role_key TEXT NOT NULL UNIQUE,
            path TEXT NOT NULL UNIQUE,
            owner_token TEXT NOT NULL,
            expected_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """,
    "experience_events": """
        CREATE TABLE experience_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            event_id TEXT NOT NULL,
            event_digest TEXT NOT NULL,
            lesson TEXT NOT NULL,
            retracts_event_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, event_id),
            UNIQUE(agent_id, retracts_event_id),
            FOREIGN KEY (agent_id, retracts_event_id)
                REFERENCES experience_events(agent_id, event_id),
            CHECK(retracts_event_id IS NULL OR retracts_event_id <> event_id)
        )
    """,
    "experience_summaries": """
        CREATE TABLE experience_summaries (
            agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id) ON DELETE CASCADE,
            summary TEXT NOT NULL,
            covered_through_sequence INTEGER NOT NULL,
            source_digest TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """,
}

SCHEMA_V3_TABLE_SQL = dict(SCHEMA_V2_TABLE_SQL)
SCHEMA_V3_TABLE_SQL["agent_runs"] = """
    CREATE TABLE agent_runs (
        run_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL REFERENCES agents(agent_id),
        invocation_kind TEXT NOT NULL
            CHECK(invocation_kind IN ('spawn_agent', 'followup_task')),
        completed_at TEXT NOT NULL
    )
"""

SCHEMA_TABLE_SQL = dict(SCHEMA_V3_TABLE_SQL)
SCHEMA_TABLE_SQL["agents"] = """
    CREATE TABLE agents (
        agent_id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        role_key TEXT NOT NULL UNIQUE,
        path TEXT NOT NULL UNIQUE,
        owner_token TEXT NOT NULL,
        expected_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        global_contract_version INTEGER NOT NULL CHECK(global_contract_version = 1),
        global_domain_key TEXT NOT NULL,
        global_contract TEXT NOT NULL,
        global_contract_digest TEXT NOT NULL
    )
"""

SCHEMA_V1_TABLE_SQL = dict(SCHEMA_V2_TABLE_SQL)
SCHEMA_V1_TABLE_SQL["experience_events"] = """
    CREATE TABLE experience_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
        event_id TEXT NOT NULL,
        event_digest TEXT NOT NULL,
        lesson TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(agent_id, event_id)
    )
"""

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


def normalize_schema_sql(value: str | None) -> str:
    return " ".join((value or "").strip().rstrip(";").split()).casefold()


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


def validate_direct_plain_file(
    path: Path,
    parent: Path,
    *,
    kind: str,
    max_bytes: int,
) -> os.stat_result:
    absolute = path.expanduser().absolute()
    if absolute.parent != parent:
        raise SpecialistError(f"{kind} must be a direct child of {parent}: {absolute}")
    metadata = os.lstat(absolute)
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata):
        raise SpecialistError(f"{kind} cannot be a link or reparse point: {absolute}")
    if not stat.S_ISREG(metadata.st_mode):
        raise SpecialistError(f"{kind} must be a regular file: {absolute}")
    if metadata.st_nlink != 1:
        raise SpecialistError(f"{kind} cannot have multiple hard links: {absolute}")
    if metadata.st_size > max_bytes:
        raise SpecialistError(f"{kind} exceeds {max_bytes} bytes: {absolute}")
    return metadata


def path_exists_without_following_links(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename on one volume while refusing to replace a destination."""
    source_parent = ensure_plain_directory(source.parent, create=False)
    destination_parent = ensure_plain_directory(destination.parent, create=False)
    if os.stat(source_parent).st_dev != os.stat(destination_parent).st_dev:
        raise SpecialistError("recoverable retirement requires a same-volume rename")
    if path_exists_without_following_links(destination):
        raise SpecialistError(f"rename destination already exists: {destination}")
    if os.name == "nt":
        # On Windows os.rename maps to a same-volume, no-replace MoveFile operation.
        os.rename(source, destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise SpecialistError("atomic no-replace rename is unavailable on this platform")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def receipt_json_bytes(receipt: dict[str, Any]) -> bytes:
    if "owner_token" in receipt:
        raise SpecialistError("retirement receipt must not duplicate owner_token")
    return (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


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
    if MEMORY_HEADER.strip() in normalized:
        raise SpecialistError("role instructions cannot contain the internal memory heading")
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


def validate_speed(value: str) -> str:
    if value not in SPEEDS:
        raise SpecialistError("speed must be standard or fast")
    return value


def resolve_ensure_speed(model: str, speed: str | None) -> str:
    if speed is not None:
        return validate_speed(speed)
    return "fast" if model == "gpt-5.6-luna" else "standard"


def speed_from_payload(payload: dict[str, Any]) -> str:
    has_service_tier = "service_tier" in payload
    features = payload.get("features", {})
    if not isinstance(features, dict):
        raise SpecialistError("agent features configuration is invalid")
    skills = payload.get("skills")
    if skills is not None and (
        not isinstance(skills, dict)
        or skills.get("include_instructions") is not False
    ):
        raise SpecialistError("agent automatic skill instructions must be disabled")
    fast_mode = features.get("fast_mode")
    if not has_service_tier and fast_mode is None:
        return "standard"
    if (
        payload.get("service_tier") == "fast"
        and fast_mode in (None, True)
    ):
        return "fast"
    raise SpecialistError("agent speed configuration is incomplete or inconsistent")


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
    if re.search(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password|passwd|authorization|bearer)\b\s*[:=]",
        value,
    ) or "-----BEGIN " in value:
        return True
    return any(ord(char) < 32 and char not in "\n\t" for char in value)


def normalize_origin_terms(values: Iterable[str] | None) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SpecialistError("origin terms must be a collection of strings")
    terms: list[str] = []
    for raw in values or ():
        if not isinstance(raw, str):
            raise SpecialistError("origin terms must be strings")
        term = " ".join(raw.split()).casefold()
        if not term or len(term) > 120:
            raise SpecialistError("origin terms must be 1-120 characters")
        if contains_forbidden_persistent_data(term):
            raise SpecialistError("origin term contains unsafe persistent data")
        if term not in terms:
            terms.append(term)
    if not terms:
        raise SpecialistError(
            "at least one non-empty origin term is required for semantic persistence"
        )
    return tuple(terms)


def _comparison_form(value: str) -> str:
    return re.sub(r"[\s_.:/\\-]+", "", value.casefold())


def reject_origin_terms(value: str, origin_terms: Iterable[str], *, field: str) -> None:
    folded = value.casefold()
    compact = _comparison_form(value)
    for term in origin_terms:
        if term in folded or _comparison_form(term) in compact:
            raise SpecialistError(f"{field} contains project/plugin origin term: {term}")


def validate_global_domain_key(value: str) -> str:
    try:
        return validate_role_key(value)
    except SpecialistError as exc:
        raise SpecialistError("global_domain_key must use the role-key format") from exc


GLOBAL_CONTRACT_FIELDS = (
    "domain",
    "input_shapes",
    "responsibilities",
    "deliverables",
    "hard_boundaries",
)


def normalize_global_contract(
    value: dict[str, Any] | str,
    *,
    domain_key: str,
    origin_terms: Iterable[str] = (),
) -> tuple[str, str, dict[str, Any]]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SpecialistError("global contract must be valid UTF-8 JSON") from exc
    else:
        parsed = value
    if not isinstance(parsed, dict) or set(parsed) != set(GLOBAL_CONTRACT_FIELDS):
        raise SpecialistError(
            "global contract must contain exactly domain, input_shapes, responsibilities, "
            "deliverables, and hard_boundaries"
        )
    domain = " ".join(str(parsed["domain"]).split())
    if not domain or len(domain) > 120:
        raise SpecialistError("global contract domain must be 1-120 characters")
    normalized: dict[str, Any] = {"domain": domain}
    for field in GLOBAL_CONTRACT_FIELDS[1:]:
        raw_items = parsed[field]
        if not isinstance(raw_items, list) or not raw_items or len(raw_items) > 32:
            raise SpecialistError(f"global contract {field} must be a non-empty JSON array")
        items: list[str] = []
        for raw in raw_items:
            if not isinstance(raw, str):
                raise SpecialistError(f"global contract {field} entries must be strings")
            item = " ".join(raw.split())
            if not item or len(item) > 500:
                raise SpecialistError(
                    f"global contract {field} entries must be 1-500 characters"
                )
            if item not in items:
                items.append(item)
        normalized[field] = items
    canonical = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(canonical.encode("utf-8")) > 16 * 1024:
        raise SpecialistError("global contract exceeds 16 KiB")
    if contains_forbidden_persistent_data(canonical):
        raise SpecialistError(
            "global contract contains a URL, absolute path, credential-like data, or control characters"
        )
    reject_origin_terms(domain_key, origin_terms, field="global_domain_key")
    reject_origin_terms(canonical, origin_terms, field="global_contract")
    return canonical, sha256_bytes(canonical.encode("utf-8")), normalized


def global_contract_instruction(contract: dict[str, Any]) -> str:
    def joined(field: str) -> str:
        return "；".join(contract[field])

    return (
        f"全局领域合同：领域={contract['domain']}；输入形状={joined('input_shapes')}；"
        f"通用职责={joined('responsibilities')}；交付={joined('deliverables')}；"
        f"硬边界={joined('hard_boundaries')}。该职责跨任务、跨项目、跨会话复用；"
        "每次调用中的项目名称、仓库路径和一次性事实只能放在任务卡，不得写回角色或经验。"
    )


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
    if len(memory_block(normalized, []).encode("utf-8")) > MAX_MEMORY_BYTES:
        raise SpecialistError(
            f"summary plus its label must fit within {MAX_MEMORY_BYTES} UTF-8 bytes"
        )
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
    speed: str = "standard",
    global_contract: dict[str, Any] | None = None,
) -> str:
    speed = validate_speed(speed)
    speed_label = "快速" if speed == "fast" else "标准"
    write_rule = (
        "获得写入权限时，只修改父代理明确交给你的文件，并保留其他并发改动。"
        if authority == "write"
        else "保持只读，不修改文件或外部状态。"
    )
    contract_rule = (
        " " + global_contract_instruction(global_contract)
        if global_contract is not None
        else ""
    )
    role_opening = (
        f"你是专门负责“{display_name}”的子代理，可复用专长标识为 {role_key}。"
        f"{role_instructions} {write_rule}{contract_rule}"
    )
    declaration = (
        f"我是{display_name}。\n"
        f"模型：{model}\n"
        f"思考程度：{effort}\n"
        f"速度：{speed_label}\n"
    )
    opening = (
        "spawn_agent 或 followup_task 启动新当前子任务后，你需要在这个子任务中分别向父代理和"
        "用户声明实际配置。任务说明给出父代理规范任务名作为消息目标（例如 /root）；这个目标"
        "不是 Codex threadId。Luna 模型目录须为 multi_agent_version=v2，父会话须启用多代理；"
        "角色 TOML 不能替父会话授予协作工具。顶层 collaboration.send_message 故意不在"
        " functions.exec 的 ALL_TOOLS 中，必须直接用 collaboration.send_message 向该目标发送。不得用"
        " list_threads 搜索父任务或用 send_message_to_thread 等跨任务 API 替代内部消息；按当前"
        "任务卡和三项原则直接授权的父代理跨任务协作不受影响，但属于另一条用户可见路线。向父代理发送以下四行：\n"
        + declaration
        + "同时在自己的代理线程（用户可见任务界面）以 commentary 原样显示同一四行。内部发送、"
        "用户可见显示、reasoning、文件读取、分析、其他工具调用和真实工作之间不设固定先后顺序；"
        "不能因为这些事件出现在声明前后就判定通信失败。内部发送失败时仍显示四行并在最终回复"
        "报告缺口；直接调用不存在或报错时，内部交流是成功条件就停止，否则只完成无需中途纠偏的"
        "自包含任务，不能宣称内部交流可用。成功路线的内部副本和用户可见副本缺一不可；公开副本"
        "不能冒充内部消息。三个字段不能省略或只留到关键步骤、最终回复；禁止用未揭露、继承父级"
        "等占位文字。声明不要求父代理确认，不计入关键步骤。父代理用 send_message 纠偏不算启动"
        "新子任务，不重复开场声明。"
    )
    return role_opening + "\n\n" + opening + "\n\n" + (
        "做分配任务，返回成果。用用户语言；标识、命令、"
        "路径、模型名和原始错误用代码格式。"
        "作为可见保留子代理或其普通复制被复用时，先读取本配置末尾的可复用经验，并沿用"
        "本配置中的模型、思考程度和速度；父代理无需重复注入经验或强制重写已有配置，"
        "由你自行声明。四行只列生成工具选定或已加载角色中的具体配置，不附请求值、"
        "运行回执等重复括注；配置声明不等于实测速度或计费证明。只有实际配置冲突或"
        "当前路线无法选择所需档位时，另外用一句话报告能力缺口。缺少独立速度参数时，"
        "不能声称在 spawn_agent 中已设置速度；不猜测、不为补声明升模或修改全局配置。"
        "默认协作角色是普通子代理，不自行再委派。只有当前任务说明同时明确写出“协作角色: "
        "协作父代理”、“允许下游委派: 是”和有限下游范围，而且你真实拥有顶层 "
        "collaboration.spawn_agent 时，才可在获批子项目内成为协作父代理。必须直接调用该工具，"
        "不得用 functions.exec 的 ALL_TOOLS、角色 TOML、模型目录或历史任务猜测能力；工具缺失、"
        "直接调用失败、容量不足、边界不清或写入无法隔离时，停止下游委派并向父代理报告。"
        "协作父代理对每个下游切片继续应用三项原则：高价值工作质量优先，普通工作达到质量"
        "底线后速度优先，没有相应质量或速度收益时不让总成本大幅增加；安全、权限、数据完整"
        "性、明确验收条件和诚实证据始终是底线。给每个下游子代理单独写完整任务卡：task_id、"
        "协作角色、目标、任务类型与任务类型组、子代理来源与运行配置、权威来源或输入快照、"
        "依赖与已就绪切片、写入所有权、是否允许下游"
        "委派及下游范围、是否允许调用其他或新建 Codex 父代理及跨任务范围、父代理规范任务名、成功条件、停止条件、有限关键步骤、证据与返回"
        "格式。先确定下游任务类型和任务类型组；复用可见保留子代理时由它自读已有配置，定制"
        "运行时新子代理时由你根据任务类型、价值、风险、证据、时延和成本，联合选择并写出具体"
        "模型、思考程度和标准或快速速度组成的完整配置；不能分列独立选择，也不得使用继承、"
        "未揭露或未暴露。默认把下游的允许下游委派写为否；只有整合父代理当前任务卡明确给出更深范围时"
        "才可写为是。下游子代理仍在自己的线程提交自己的最终结果。协作父代理可以"
        "核验并整合自己子树的独立结果，但不能压掉、改写或冒充这些结果。只有任务卡明确写"
        "允许调用其他或新建 Codex 父代理为是并给出跨任务范围时，才可使用 create_thread、"
        "read_thread、wait_threads 或 send_message_to_thread；整合父代理按三项原则给出这项"
        "任务卡授权，不需要再向用户询问。跨任务工具不能冒充内部消息，也不能用共享文件建立"
        "横向通信。所有跨任务动作还必须同时满足当前工具合同；create_thread 要求用户明确提出"
        "新建任务时，任务卡或插件默认授权不能替代，也不能为内部委派创建用户可见新任务；"
        "已有用户授权无需重复询问。"
        "不得建立非授权留言板、"
        "缓存或日志暗渠，不得共享凭据或私密数据，不得以集体利益、未回复或无人否决扩大权限，"
        "也不得伪造、删除、编辑或隐藏消息、工具调用、测试、日志、文件变更、身份、权限和来源。"
        "最近的协作授权不改变原有删除、删减或候选清理的资格与尺度；原规则判定应删的目标仍处理，"
        "原规则不允许删的目标仍不处理。普通删除不得物理销毁；普通文件精确送入 Windows 回收站，"
        "重要文件精确移入任务专属待删文件，记录原路径、不覆盖目标并报告恢复方式。插件角色仍按"
        "原来的身份、令牌、哈希、直接普通文件、单一硬链接、零经验和零存活轮次资格判断；合格 TOML"
        "与收据移入插件专属待删文件，不合格目标保持原位并报告。"
        "只完成父代理分配的当前子任务，遵守它给出的有限关键步骤清单和停止条件；没有预设"
        "关键步骤时不自行追加。每完成一个预设关键步骤，只发送一条短消息并立即继续，不等待"
        "父代理：\n"
        "关键步骤：<已完成的预设步骤或新风险>\n"
        "情况：<决定性结果、证据或方向问题>\n"
        "下一步：<立即继续的下一项>\n"
        "每个关键步骤最多一条常规进度；同一方向风险只有状态实质变化后才能再次报告，不发送"
        "定时心跳或纯确认消息。父代理无异议时可沉默；收到纠偏或任务目标更新后直接应用并"
        "继续，但任何更新都不得扩大用户授权、移除停止条件或让任务无限延伸。"
        "达到父代理为该子任务单独指定的成功条件或停止条件后自检，在自己的线程用最终回复"
        "提交自己的精炼结果，不建立共享中转文件。普通子代理不代交、等待或汇总其他子代理的"
        "结果；任务卡明确指定的协作父代理只整合自己下游子代理已经独立提交的结果。"
        "最终回复顶部再次写实际模型、思考程度和速度；无差异沿用本配置。最终回复固定写：\n"
        + declaration
        + "子任务：<当前子任务>\n"
        "状态：完成 | 部分完成 | 受阻\n"
        "结果：<可直接使用的精炼结果>\n"
        "证据或缺口：<决定性证据、覆盖范围或剩余缺口>\n"
        "来源读取任务在这个结构后追加 SOURCE_COVERAGE。"
        "作为组内复制或变体时不预先合并结果；返回可比较证据和去敏经验候选，但不决定胜者、"
        "不写台账或自行退出组。父代理接近结束时先选唯一子代理、再维护经验、最后结束其他子代理。"
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
    return base.split(MEMORY_HEADER, 1)[0] + MEMORY_HEADER + memory


def _render_agent_bytes(
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
    instruction_base: str,
    memory: str,
    speed: str = "standard",
    global_domain_key: str,
    global_contract_digest: str,
) -> bytes:
    speed = validate_speed(speed)
    developer_instructions = compose_instructions(instruction_base, memory)
    sandbox_mode = "workspace-write" if authority == "write" else "read-only"
    service_tier = f"service_tier = {json_text('fast')}\n" if speed == "fast" else ""
    skills_config = "[skills]\ninclude_instructions = false\n"
    text = (
        f"{MANAGED_MARKER}\n"
        f"{AGENT_ID_PREFIX}{agent_id}\n"
        f"{ROLE_KEY_PREFIX}{role_key}\n"
        f"{OWNER_TOKEN_PREFIX}{owner_token}\n"
        f"{GLOBAL_SCOPE_PREFIX}{GLOBAL_SCOPE}\n"
        f"{GLOBAL_DOMAIN_KEY_PREFIX}{global_domain_key}\n"
        f"{GLOBAL_CONTRACT_DIGEST_PREFIX}{global_contract_digest}\n"
        f"name = {json_text(name)}\n"
        f"description = {json_text(display_name + '：' + description)}\n"
        f"model = {json_text(model)}\n"
        f"model_reasoning_effort = {json_text(effort)}\n"
        f"{service_tier}"
        f"sandbox_mode = {json_text(sandbox_mode)}\n"
        f"developer_instructions = {json_text(developer_instructions)}\n"
        f"{skills_config}"
    )
    data = text.encode("utf-8")
    tomllib.loads(text)
    return data


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
    instruction_base: str,
    memory: str,
    speed: str = "standard",
    global_domain_key: str,
    global_contract_digest: str,
) -> bytes:
    data = _render_agent_bytes(
        agent_id=agent_id,
        role_key=role_key,
        owner_token=owner_token,
        name=name,
        display_name=display_name,
        description=description,
        model=model,
        effort=effort,
        authority=authority,
        instruction_base=instruction_base,
        memory=memory,
        speed=speed,
        global_domain_key=global_domain_key,
        global_contract_digest=global_contract_digest,
    )
    if len(data) > MAX_AGENT_BYTES:
        raise SpecialistError("generated agent exceeds 16 KiB")
    return data


def parse_header(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if len(lines) < 4 or lines[0] != MANAGED_MARKER:
        raise SpecialistError("agent is not owned by the specialist registry")
    prefixes = {
        "agent_id": AGENT_ID_PREFIX,
        "role_key": ROLE_KEY_PREFIX,
        "owner_token": OWNER_TOKEN_PREFIX,
        "scope": GLOBAL_SCOPE_PREFIX,
        "global_domain_key": GLOBAL_DOMAIN_KEY_PREFIX,
        "global_contract_digest": GLOBAL_CONTRACT_DIGEST_PREFIX,
    }
    values: dict[str, str] = {}
    for key, prefix in prefixes.items():
        matches = [line[len(prefix) :] for line in lines[:12] if line.startswith(prefix)]
        if len(matches) != 1:
            raise SpecialistError(f"agent has invalid {key} marker")
        values[key] = matches[0]
    if not UUID_RE.fullmatch(values["agent_id"]):
        raise SpecialistError("agent id marker is invalid")
    validate_role_key(values["role_key"])
    if not TOKEN_RE.fullmatch(values["owner_token"]):
        raise SpecialistError("owner token marker is invalid")
    if values["scope"] != GLOBAL_SCOPE:
        raise SpecialistError("agent scope marker is not the global domain contract")
    validate_global_domain_key(values["global_domain_key"])
    if not SHA256_RE.fullmatch(values["global_contract_digest"]):
        raise SpecialistError("agent global contract digest marker is invalid")
    return values


def parse_legacy_header(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if len(lines) < 4 or lines[0] != MANAGED_MARKER:
        raise SpecialistError("legacy agent is not owned by the specialist registry")
    prefixes = {
        "agent_id": AGENT_ID_PREFIX,
        "role_key": ROLE_KEY_PREFIX,
        "owner_token": OWNER_TOKEN_PREFIX,
    }
    values: dict[str, str] = {}
    for key, prefix in prefixes.items():
        matches = [line[len(prefix) :] for line in lines[:8] if line.startswith(prefix)]
        if len(matches) != 1:
            raise SpecialistError(f"legacy agent has invalid {key} marker")
        values[key] = matches[0]
    if not UUID_RE.fullmatch(values["agent_id"]):
        raise SpecialistError("legacy agent id marker is invalid")
    validate_role_key(values["role_key"])
    if not TOKEN_RE.fullmatch(values["owner_token"]):
        raise SpecialistError("legacy owner token marker is invalid")
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
        validate_direct_agent_file(path, path.parent)
        if path.read_bytes() != expected:
            raise SpecialistError("agent changed while it was being updated")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def exact_schema(connection: sqlite3.Connection) -> dict[tuple[str, str], str]:
    return {
        (str(row[0]), str(row[1])): normalize_schema_sql(row[2])
        for row in connection.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        )
    }


def expected_schema(tables: dict[str, str]) -> dict[tuple[str, str], str]:
    return {
        ("table", table): normalize_schema_sql(sql) for table, sql in tables.items()
    }


class SpecialistRegistry:
    def __init__(self, codex_home: Path):
        self.codex_home = ensure_plain_directory(codex_home, create=True)
        self.agents_dir = ensure_plain_directory(self.codex_home / "agents", create=True)
        self.state_dir = ensure_plain_directory(self.codex_home / "lean-stack", create=True)
        self.pending_deletion_dir = self.state_dir / PENDING_DELETION_DIR_NAME
        self.restored_receipt_dir = self.pending_deletion_dir / RESTORED_RECEIPT_DIR_NAME
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
            actual_schema = {
                (str(row[0]), str(row[1])): normalize_schema_sql(row[2])
                for row in connection.execute(
                    "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            }
            if version == 0:
                if existing_objects:
                    raise AuxiliarySkipped(
                        "unversioned specialist database is not empty; no initialization or migration is attempted"
                    )
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + ";\n".join(SCHEMA_TABLE_SQL.values())
                    + f";\nPRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;"
                )
            elif version in (1, 2, 3):
                raise AuxiliarySkipped(
                    f"specialist database schema {version} requires explicit migrate-global; "
                    "ordinary registry commands do not globalize legacy roles"
                )
            elif version != SCHEMA_VERSION:
                raise AuxiliarySkipped(
                    f"unsupported specialist database schema {version}; no migration is attempted"
                )
            actual_schema = {
                (str(row[0]), str(row[1])): normalize_schema_sql(row[2])
                for row in connection.execute(
                    "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            }
            expected_schema = {
                ("table", table): normalize_schema_sql(sql)
                for table, sql in SCHEMA_TABLE_SQL.items()
            }
            if actual_schema != expected_schema:
                raise AuxiliarySkipped(
                    "specialist database schema differs from the supported exact schema"
                )
            return connection
        except BaseException:
            connection.close()
            raise

    def _legacy_connection(self) -> tuple[sqlite3.Connection, int]:
        ensure_plain_database(self.db_path)
        connection = sqlite3.connect(
            self.db_path,
            timeout=BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        schemas = {
            1: SCHEMA_V1_TABLE_SQL,
            2: SCHEMA_V2_TABLE_SQL,
            3: SCHEMA_V3_TABLE_SQL,
        }
        if version not in schemas or exact_schema(connection) != expected_schema(schemas[version]):
            connection.close()
            raise AuxiliarySkipped(
                "migrate-global accepts only the exact published v1, v2, or v3 schema"
            )
        return connection, version

    def _migration_journal_path(self) -> Path:
        return self.state_dir / GLOBAL_MIGRATION_JOURNAL

    def _write_migration_journal(self, journal: dict[str, Any]) -> None:
        write_json_atomic(self._migration_journal_path(), journal)
        archive = Path(journal["archive_dir"])
        ensure_plain_directory(archive, create=True)
        write_json_atomic(archive / "journal.json", journal)

    def _verify_v4_receipt_agents(
        self, connection: sqlite3.Connection, receipt_agents: Sequence[dict[str, str]]
    ) -> None:
        if len(receipt_agents) != int(
            connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        ):
            raise AuxiliarySkipped("completed migration receipt does not cover current v4 agents")
        for identity in receipt_agents:
            if not isinstance(identity, dict) or set(identity) != {
                "agent_id", "name", "role_key", "sha256", "contract_digest"
            }:
                raise AuxiliarySkipped("completed migration receipt agent identity is invalid")
            row = connection.execute(
                "SELECT * FROM agents WHERE agent_id=?", (identity["agent_id"],)
            ).fetchone()
            if row is None or any(
                row[column] != identity[key]
                for column, key in (
                    ("name", "name"), ("role_key", "role_key"),
                    ("expected_sha256", "sha256"),
                    ("global_contract_digest", "contract_digest"),
                )
            ):
                raise AuxiliarySkipped("completed migration receipt differs from current v4 state")
            self._owned_agent(
                connection, name=identity["name"], expected_sha256=identity["sha256"]
            )

    def _finalize_committed_migration(
        self, journal: dict[str, Any], connection: sqlite3.Connection
    ) -> dict[str, Any]:
        identities: list[dict[str, str]] = []
        for item in journal["files"]:
            row = connection.execute(
                "SELECT agent_id,name,role_key,expected_sha256,global_contract_digest "
                "FROM agents WHERE agent_id=?",
                (item["agent_id"],),
            ).fetchone()
            if row is None or row["expected_sha256"] != item["new_sha256"]:
                raise AuxiliarySkipped(
                    "migration is committed but its v4 identity verification failed"
                )
            self._owned_agent(
                connection, name=row["name"], expected_sha256=row["expected_sha256"]
            )
            identities.append({
                "agent_id": row["agent_id"],
                "name": row["name"],
                "role_key": row["role_key"],
                "sha256": row["expected_sha256"],
                "contract_digest": row["global_contract_digest"],
            })
        archive_root = ensure_plain_directory(
            self.state_dir / GLOBAL_MIGRATION_ARCHIVE_DIR, create=False
        )
        archive_dir = Path(journal["archive_dir"]).absolute()
        if archive_dir.parent != archive_root:
            raise AuxiliarySkipped("migration archive is outside its owned root")
        pending_root = ensure_plain_directory(self.pending_deletion_dir, create=True)
        backup_root = ensure_plain_directory(
            pending_root / GLOBAL_MIGRATION_PENDING_BACKUP_DIR, create=True
        )
        target = backup_root / archive_dir.name
        journal["status"] = "commit_verified_cleanup_pending"
        journal["backup_target"] = str(target)
        journal["verified_at"] = utc_now()
        if path_exists_without_following_links(archive_dir):
            ensure_plain_directory(archive_dir, create=False)
            if path_exists_without_following_links(target):
                raise AuxiliarySkipped(
                    "migration is committed but both active archive and backup target exist"
                )
            self._write_migration_journal(journal)
            rename_no_replace(archive_dir, target)
        else:
            if not path_exists_without_following_links(target):
                raise AuxiliarySkipped(
                    "migration is committed but neither archive nor backup target exists"
                )
            ensure_plain_directory(target, create=False)
        for item in journal["files"]:
            backup = target / Path(item["backup_path"]).name
            validate_direct_plain_file(
                backup, target, kind="pending global migration backup",
                max_bytes=MAX_AGENT_BYTES,
            )
            if sha256_bytes(backup.read_bytes()) != item["old_sha256"]:
                raise AuxiliarySkipped(
                    "migration is committed but a pending legacy backup drifted"
                )
        completion = {
            "format_version": 1,
            "receipt_kind": GLOBAL_MIGRATION_COMPLETION_KIND,
            "status": "committed",
            "schema_version": SCHEMA_VERSION,
            "plan_digest": journal["plan_digest"],
            "migrated_count": len(identities),
            "correction_count": int(journal.get("correction_count", 0)),
            "backup_disposition": "plugin_pending_deletion",
            "backup_id": target.name,
            "agents": sorted(identities, key=lambda item: item["agent_id"]),
            "completed_at": utc_now(),
        }
        write_json_atomic(self._migration_journal_path(), completion)
        return completion

    def _recover_global_migration(self, plan_digest: str) -> dict[str, Any] | None:
        journal_path = self._migration_journal_path()
        if not path_exists_without_following_links(journal_path):
            return None
        validate_direct_plain_file(
            journal_path,
            self.state_dir,
            kind="global migration journal",
            max_bytes=MAX_MIGRATION_PLAN_BYTES,
        )
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if not isinstance(journal, dict) or journal.get("format_version") != 1:
            raise AuxiliarySkipped("global migration journal requires manual review")
        if journal.get("plan_digest") != plan_digest:
            raise AuxiliarySkipped(
                "a different global migration journal exists; recover it with its original plan"
            )
        if journal.get("receipt_kind") == GLOBAL_MIGRATION_COMPLETION_KIND:
            if journal.get("status") != "committed" or journal.get("schema_version") != SCHEMA_VERSION:
                raise AuxiliarySkipped("completed migration receipt is inconsistent")
            connection = self.connect()
            try:
                self._verify_v4_receipt_agents(connection, journal.get("agents", []))
            finally:
                connection.close()
            return {
                "ok": True,
                "action": "global_migration_already_committed",
                "schema_version": SCHEMA_VERSION,
                "migrated_count": journal["migrated_count"],
                "plan_digest": plan_digest,
                "backup_disposition": journal["backup_disposition"],
            }
        archive_root = ensure_plain_directory(
            self.state_dir / GLOBAL_MIGRATION_ARCHIVE_DIR, create=False
        )
        archive_dir = Path(journal.get("archive_dir", "")).absolute()
        if archive_dir.parent != archive_root:
            raise AuxiliarySkipped("global migration journal archive path is outside its owned root")
        status = journal.get("status")
        ensure_plain_database(self.db_path)
        with contextlib.closing(sqlite3.connect(self.db_path)) as probe:
            version = int(probe.execute("PRAGMA user_version").fetchone()[0])
        if version == SCHEMA_VERSION:
            connection = self.connect()
            try:
                completion = self._finalize_committed_migration(journal, connection)
            finally:
                connection.close()
            return {
                "ok": True,
                "action": "global_migration_already_committed",
                "schema_version": SCHEMA_VERSION,
                "migrated_count": completion["migrated_count"],
                "plan_digest": plan_digest,
                "backup_disposition": completion["backup_disposition"],
            }
        if version not in (1, 2, 3):
            raise AuxiliarySkipped("migration journal database version requires manual review")
        if status == "rolled_back":
            return None
        rollback_errors: list[str] = []
        for item in reversed(journal.get("files", [])):
            old_path = Path(item["old_path"])
            new_path = Path(item["new_path"])
            backup_path = Path(item["backup_path"])
            try:
                old_exists = path_exists_without_following_links(old_path)
                new_exists = path_exists_without_following_links(new_path)
                if old_exists:
                    validate_direct_agent_file(old_path, self.agents_dir)
                if new_exists and new_path != old_path:
                    validate_direct_agent_file(new_path, self.agents_dir)
                if (
                    old_exists
                    and sha256_bytes(old_path.read_bytes()) == item["old_sha256"]
                    and (item["same_path"] or not new_exists)
                ):
                    continue
                validate_direct_plain_file(
                    backup_path,
                    archive_dir,
                    kind="global migration backup",
                    max_bytes=MAX_AGENT_BYTES,
                )
                backup = backup_path.read_bytes()
                if sha256_bytes(backup) != item["old_sha256"]:
                    raise SpecialistError("migration backup digest changed")
                if item["same_path"]:
                    if old_exists and sha256_bytes(old_path.read_bytes()) == item["new_sha256"]:
                        replace_exact_file(old_path, expected=old_path.read_bytes(), replacement=backup)
                else:
                    if new_exists and sha256_bytes(new_path.read_bytes()) == item["new_sha256"]:
                        failed_path = backup_path.with_name(backup_path.name + ".failed-new.toml")
                        rename_no_replace(new_path, failed_path)
                    if not old_exists and path_exists_without_following_links(backup_path):
                        rename_no_replace(backup_path, old_path)
                if sha256_bytes(old_path.read_bytes()) != item["old_sha256"]:
                    raise SpecialistError("legacy file was not exactly restored")
            except (OSError, SpecialistError) as exc:
                rollback_errors.append(f"{item.get('old_name')}: {exc}")
        if rollback_errors:
            raise AuxiliarySkipped(
                "global migration recovery was incomplete: " + "; ".join(rollback_errors)
            )
        journal["status"] = "rolled_back"
        journal["recovered_at"] = utc_now()
        self._write_migration_journal(journal)
        return None

    @staticmethod
    def _load_migration_plan(plan_path: Path) -> tuple[dict[str, Any], str]:
        absolute = plan_path.expanduser().absolute()
        metadata = os.lstat(absolute)
        if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise SpecialistError("migration plan must be a regular non-link file")
        if metadata.st_size > MAX_MIGRATION_PLAN_BYTES:
            raise SpecialistError("migration plan exceeds the bounded size")
        raw = absolute.read_bytes()
        try:
            plan = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SpecialistError("migration plan must be valid UTF-8 JSON") from exc
        if not isinstance(plan, dict) or set(plan) != {"format_version", "roles"}:
            raise SpecialistError("migration plan must contain exactly format_version and roles")
        if plan["format_version"] != 1 or not isinstance(plan["roles"], list):
            raise SpecialistError("migration plan format_version or roles is invalid")
        canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return plan, sha256_bytes(canonical.encode("utf-8"))

    def migrate_global(self, *, plan_path: Path) -> dict[str, Any]:
        plan, plan_digest = self._load_migration_plan(plan_path)
        recovered = self._recover_global_migration(plan_digest)
        if recovered is not None:
            return recovered
        connection, legacy_version = self._legacy_connection()
        prepared: list[dict[str, Any]] = []
        archive_dir = self.state_dir / GLOBAL_MIGRATION_ARCHIVE_DIR / uuid.uuid4().hex
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("BEGIN IMMEDIATE")
            legacy_rows = list(connection.execute("SELECT * FROM agents ORDER BY agent_id"))
            if len(plan["roles"]) != len(legacy_rows):
                raise SpecialistError("migration plan must cover every legacy specialist exactly once")
            by_name = {row["name"]: row for row in legacy_rows}
            if len(by_name) != len(legacy_rows):
                raise SpecialistError("legacy agent names are not unique")
            seen_old: set[str] = set()
            seen_role_keys: set[str] = set()
            seen_names: set[str] = set()
            seen_paths: set[str] = set()
            for index, raw_item in enumerate(plan["roles"]):
                required = {
                    "old_name", "old_role_key", "expected_sha256", "new_role_key",
                    "display_name", "description", "instructions", "global_domain_key",
                    "global_contract", "origin_terms", "experience_corrections",
                }
                if not isinstance(raw_item, dict) or set(raw_item) != required:
                    raise SpecialistError(f"migration role {index} has invalid fields")
                old_name = raw_item["old_name"]
                if old_name in seen_old or old_name not in by_name:
                    raise SpecialistError("migration old_name is duplicate or unknown")
                seen_old.add(old_name)
                row = by_name[old_name]
                if row["role_key"] != raw_item["old_role_key"]:
                    raise SpecialistError("migration old role_key does not match the ledger")
                expected_hash = validate_sha256(raw_item["expected_sha256"])
                if expected_hash != row["expected_sha256"]:
                    raise SpecialistError("migration expected SHA-256 does not match the ledger")
                old_path = Path(row["path"]).absolute()
                validate_direct_agent_file(old_path, self.agents_dir)
                old_data = old_path.read_bytes()
                if sha256_bytes(old_data) != expected_hash:
                    raise SpecialistError("migration source agent drifted from the ledger")
                header = parse_legacy_header(old_data.decode("utf-8"))
                if header["agent_id"] != row["agent_id"] or header["role_key"] != row["role_key"] or header["owner_token"] != row["owner_token"]:
                    raise SpecialistError("migration source markers do not match the ledger")
                payload = tomllib.loads(old_data.decode("utf-8"))
                if payload.get("name") != old_name or old_path.stem != old_name:
                    raise SpecialistError("migration source name/path identity is invalid")
                if not isinstance(raw_item["origin_terms"], list) or any(
                    not isinstance(term, str) for term in raw_item["origin_terms"]
                ):
                    raise SpecialistError("migration origin_terms must be an array of strings")
                terms = normalize_origin_terms(raw_item["origin_terms"])
                new_role_key = validate_role_key(raw_item["new_role_key"])
                display_name = validate_display_name(raw_item["display_name"])
                description = validate_description(raw_item["description"])
                instructions = validate_role_instructions(raw_item["instructions"])
                domain_key = validate_global_domain_key(raw_item["global_domain_key"])
                contract_text, contract_digest, contract = normalize_global_contract(
                    raw_item["global_contract"], domain_key=domain_key, origin_terms=terms
                )
                for field, value in {
                    "new_role_key": new_role_key,
                    "display_name": display_name,
                    "description": description,
                    "instructions": instructions,
                }.items():
                    if contains_forbidden_persistent_data(value):
                        raise SpecialistError(f"migration {field} contains unsafe persistent data")
                    reject_origin_terms(value, terms, field=field)
                new_name = specialist_name(new_role_key, row["agent_id"])
                new_path = self.agents_dir / f"{new_name}.toml"
                for value, seen, label in (
                    (new_role_key, seen_role_keys, "role_key"),
                    (new_name, seen_names, "name"),
                    (str(new_path), seen_paths, "path"),
                ):
                    if value in seen:
                        raise SpecialistError(f"migration target {label} conflict")
                    seen.add(value)
                if new_path != old_path and path_exists_without_following_links(new_path):
                    raise SpecialistError("migration target path already exists")
                corrections = raw_item["experience_corrections"]
                if not isinstance(corrections, list):
                    raise SpecialistError("experience_corrections must be an array")
                correction_rows: list[dict[str, str]] = []
                correction_targets: set[str] = set()
                for correction in corrections:
                    if not isinstance(correction, dict) or set(correction) != {"event_id", "lesson"}:
                        raise SpecialistError("migration correction must contain event_id and lesson")
                    target_id = correction["event_id"]
                    if not isinstance(target_id, str) or not UUID_RE.fullmatch(target_id) or target_id in correction_targets:
                        raise SpecialistError("migration correction target is invalid or duplicate")
                    target = connection.execute(
                        "SELECT event_id" + (", retracts_event_id" if legacy_version >= 2 else "") +
                        " FROM experience_events WHERE agent_id = ? AND event_id = ?",
                        (row["agent_id"], target_id),
                    ).fetchone()
                    if target is None:
                        raise SpecialistError("migration correction target does not exist")
                    if legacy_version >= 2:
                        prior = connection.execute(
                            "SELECT event_id FROM experience_events WHERE agent_id = ? AND retracts_event_id = ?",
                            (row["agent_id"], target_id),
                        ).fetchone()
                        if target["retracts_event_id"] is not None or prior is not None:
                            raise SpecialistError("migration correction target is not active raw experience")
                    lesson = validate_lesson(correction["lesson"])
                    reject_origin_terms(lesson, terms, field="migration correction lesson")
                    correction_id = str(uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"codex-lean-stack:migrate-global:{row['agent_id']}:{target_id}:{sha256_bytes(lesson.encode('utf-8'))}",
                    ))
                    digest = sha256_bytes(json.dumps(
                        {"lesson": lesson, "retracts_event_id": target_id},
                        ensure_ascii=False, sort_keys=True,
                    ).encode("utf-8"))
                    correction_rows.append({
                        "event_id": correction_id, "lesson": lesson,
                        "retracts_event_id": target_id, "event_digest": digest,
                    })
                    correction_targets.add(target_id)
                if legacy_version == 1:
                    event_rows = list(connection.execute(
                        "SELECT sequence,event_id,event_digest,lesson,NULL AS retracts_event_id FROM experience_events WHERE agent_id=? ORDER BY sequence",
                        (row["agent_id"],),
                    ))
                else:
                    event_rows = list(connection.execute(
                        "SELECT sequence,event_id,event_digest,lesson,retracts_event_id FROM experience_events WHERE agent_id=? ORDER BY sequence",
                        (row["agent_id"],),
                    ))
                already_retracted = {
                    event["retracts_event_id"] for event in event_rows if event["retracts_event_id"]
                }
                summary_row = connection.execute(
                    "SELECT summary,covered_through_sequence FROM experience_summaries WHERE agent_id=?",
                    (row["agent_id"],),
                ).fetchone()
                preserved_summary = (
                    summary_row["summary"]
                    if summary_row is not None and not correction_rows
                    else ""
                )
                covered = (
                    int(summary_row["covered_through_sequence"])
                    if summary_row is not None and not correction_rows
                    else 0
                )
                active_lessons = [
                    event["lesson"] for event in event_rows
                    if event["event_id"] not in already_retracted
                    and event["event_id"] not in correction_targets
                    and event["retracts_event_id"] is None
                    and int(event["sequence"]) > covered
                ] + [item["lesson"] for item in correction_rows]
                if preserved_summary:
                    reject_origin_terms(
                        preserved_summary, terms, field="preserved experience summary"
                    )
                for lesson in active_lessons:
                    reject_origin_terms(lesson, terms, field="preserved active experience")
                model = validate_model(str(payload.get("model")))
                effort = validate_effort(str(payload.get("model_reasoning_effort")))
                authority = "write" if payload.get("sandbox_mode") == "workspace-write" else "read"
                speed = speed_from_payload(payload)
                base = base_instructions(
                    display_name=display_name, role_key=new_role_key,
                    role_instructions=instructions, model=model, effort=effort,
                    authority=authority, speed=speed, global_contract=contract,
                )
                def render_migrated_memory(candidate: str) -> bytes:
                    return _render_agent_bytes(
                        agent_id=row["agent_id"], role_key=new_role_key,
                        owner_token=row["owner_token"], name=new_name,
                        display_name=display_name, description=description,
                        model=model, effort=effort, authority=authority,
                        instruction_base=base, memory=candidate, speed=speed,
                        global_domain_key=domain_key,
                        global_contract_digest=contract_digest,
                    )
                migrated_memory = self._memory_for_toml(
                    preserved_summary, [{"lesson": lesson} for lesson in active_lessons],
                    fits=lambda candidate: len(render_migrated_memory(candidate)) <= MAX_AGENT_BYTES,
                )
                desired = build_agent_bytes(
                    agent_id=row["agent_id"], role_key=new_role_key,
                    owner_token=row["owner_token"], name=new_name,
                    display_name=display_name, description=description,
                    model=model, effort=effort, authority=authority,
                    instruction_base=base, memory=migrated_memory,
                    speed=speed, global_domain_key=domain_key,
                    global_contract_digest=contract_digest,
                )
                prepared.append({
                    "row": row, "old_name": old_name, "old_path": old_path,
                    "old_data": old_data, "old_sha256": expected_hash,
                    "new_name": new_name, "new_role_key": new_role_key,
                    "new_path": new_path, "new_data": desired,
                    "new_sha256": sha256_bytes(desired), "domain_key": domain_key,
                    "contract_text": contract_text, "contract_digest": contract_digest,
                    "corrections": correction_rows,
                })
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            connection.close()
            raise

        ensure_plain_directory(archive_dir, create=True)
        journal = {
            "format_version": 1, "plan_digest": plan_digest,
            "legacy_schema_version": legacy_version, "status": "prepared",
            "created_at": utc_now(), "archive_dir": str(archive_dir), "files": [],
            "correction_count": sum(len(item["corrections"]) for item in prepared),
        }
        for item in prepared:
            backup = archive_dir / f"{item['row']['agent_id']}.{item['old_sha256']}.legacy.toml"
            journal["files"].append({
                "agent_id": item["row"]["agent_id"], "old_name": item["old_name"],
                "old_path": str(item["old_path"]), "new_path": str(item["new_path"]),
                "backup_path": str(backup), "old_sha256": item["old_sha256"],
                "new_sha256": item["new_sha256"], "same_path": item["old_path"] == item["new_path"],
            })
        file_mutated = False
        db_committed = False
        try:
            self._write_migration_journal(journal)
            for item, receipt in zip(prepared, journal["files"]):
                old_path, new_path = item["old_path"], item["new_path"]
                backup = Path(receipt["backup_path"])
                if old_path.read_bytes() != item["old_data"]:
                    raise SpecialistError("migration source changed after preflight")
                file_mutated = True
                if receipt["same_path"]:
                    write_new_file(backup, item["old_data"])
                    replace_exact_file(old_path, expected=item["old_data"], replacement=item["new_data"])
                else:
                    rename_no_replace(old_path, backup)
                    write_new_file(new_path, item["new_data"])
            journal["status"] = "files_replaced"
            self._write_migration_journal(journal)
            if legacy_version == 1:
                connection.execute("ALTER TABLE experience_events RENAME TO experience_events_v1")
                connection.execute(SCHEMA_V3_TABLE_SQL["experience_events"])
                connection.execute(
                    "INSERT INTO experience_events(sequence,agent_id,event_id,event_digest,lesson,retracts_event_id,created_at) "
                    "SELECT sequence,agent_id,event_id,event_digest,lesson,NULL,created_at FROM experience_events_v1"
                )
                connection.execute("DROP TABLE experience_events_v1")
                connection.execute(SCHEMA_V3_TABLE_SQL["agent_runs"])
            elif legacy_version == 2:
                connection.execute(SCHEMA_V3_TABLE_SQL["agent_runs"])
            connection.execute("DROP TABLE agents")
            connection.execute(SCHEMA_TABLE_SQL["agents"])
            for item in prepared:
                row = item["row"]
                connection.execute(
                    "INSERT INTO agents(agent_id,name,role_key,path,owner_token,expected_sha256,"
                    "created_at,updated_at,global_contract_version,global_domain_key,global_contract,global_contract_digest) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["agent_id"], item["new_name"], item["new_role_key"],
                        str(item["new_path"]), row["owner_token"], item["new_sha256"],
                        row["created_at"], utc_now(), GLOBAL_CONTRACT_VERSION,
                        item["domain_key"], item["contract_text"], item["contract_digest"],
                    ),
                )
                for correction in item["corrections"]:
                    connection.execute(
                        "INSERT INTO experience_events(agent_id,event_id,event_digest,lesson,retracts_event_id,created_at) VALUES(?,?,?,?,?,?)",
                        (
                            row["agent_id"], correction["event_id"], correction["event_digest"],
                            correction["lesson"], correction["retracts_event_id"], utc_now(),
                        ),
                    )
                if item["corrections"]:
                    connection.execute(
                        "DELETE FROM experience_summaries WHERE agent_id=?", (row["agent_id"],)
                    )
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SpecialistError("migrated SQLite integrity_check failed")
            if list(connection.execute("PRAGMA foreign_key_check")):
                raise SpecialistError("migrated SQLite foreign_key_check failed")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute("COMMIT")
            db_committed = True
            connection.execute("PRAGMA foreign_keys = ON")
            connection.close()
            verified = self.connect()
            try:
                for item in prepared:
                    self._owned_agent(verified, name=item["new_name"], expected_sha256=item["new_sha256"])
                completion = self._finalize_committed_migration(journal, verified)
            finally:
                verified.close()
            return {
                "ok": True, "action": "global_migration_committed",
                "schema_version": SCHEMA_VERSION, "migrated_count": len(prepared),
                "correction_count": sum(len(item["corrections"]) for item in prepared),
                "plan_digest": plan_digest,
                "backup_disposition": completion["backup_disposition"],
            }
        except BaseException as exc:
            if db_committed:
                raise AuxiliarySkipped(
                    "global migration committed but pending-backup finalization is incomplete; "
                    f"retry the same plan: {exc}"
                ) from exc
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            connection.close()
            if file_mutated:
                journal["status"] = "recovery_required"
                journal["failure"] = type(exc).__name__
                self._write_migration_journal(journal)
                try:
                    self._recover_global_migration(plan_digest)
                except BaseException as recovery_exc:
                    raise AuxiliarySkipped(
                        f"global migration failed and recovery is incomplete: {recovery_exc}"
                    ) from exc
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
        if int(row["global_contract_version"]) != GLOBAL_CONTRACT_VERSION:
            raise SpecialistError("agent global contract version is invalid")
        if header["global_domain_key"] != row["global_domain_key"]:
            raise SpecialistError("agent domain marker does not match the ownership ledger")
        canonical, contract_digest, contract = normalize_global_contract(
            row["global_contract"],
            domain_key=row["global_domain_key"],
        )
        if canonical != row["global_contract"] or contract_digest != row["global_contract_digest"]:
            raise SpecialistError("agent global contract ledger is not canonical")
        if header["global_contract_digest"] != contract_digest:
            raise SpecialistError("agent contract marker does not match the ownership ledger")
        if owner_token is not None and header["owner_token"] != owner_token:
            raise SpecialistError("provided owner token is incorrect")
        payload = tomllib.loads(text)
        if payload.get("name") != name or path.stem != name or not NAME_RE.fullmatch(name):
            raise SpecialistError("agent name/path identity is invalid")
        developer = payload.get("developer_instructions")
        if not isinstance(developer, str) or global_contract_instruction(contract) not in developer:
            raise SpecialistError("agent duties do not contain the canonical global contract")
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
        active_filter = (
            "NOT EXISTS (SELECT 1 FROM experience_events AS correction "
            "WHERE correction.agent_id = event.agent_id "
            "AND correction.retracts_event_id = event.event_id)"
        )
        if through is None:
            return list(
                connection.execute(
                    "SELECT event.sequence, event.event_id, event.lesson, "
                    "event.event_digest, event.retracts_event_id "
                    "FROM experience_events AS event "
                    f"WHERE event.agent_id = ? AND event.sequence > ? AND {active_filter} "
                    "ORDER BY event.sequence LIMIT ?",
                    (agent_id, covered, limit),
                )
            )
        return list(
            connection.execute(
                "SELECT event.sequence, event.event_id, event.lesson, "
                "event.event_digest, event.retracts_event_id "
                "FROM experience_events AS event "
                f"WHERE event.agent_id = ? AND event.sequence > ? "
                f"AND event.sequence <= ? AND {active_filter} "
                "ORDER BY event.sequence LIMIT ?",
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
                    "event_id": row["event_id"],
                    "digest": row["event_digest"],
                    "lesson": row["lesson"],
                    "retracts_event_id": row["retracts_event_id"],
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
                {
                    "sequence": int(row["sequence"]),
                    "event_id": row["event_id"],
                    "lesson": row["lesson"],
                    "retracts_event_id": row["retracts_event_id"],
                }
                for row in selected
            ],
            "covered_through": through,
            "source_digest": SpecialistRegistry._source_digest(summary, selected),
            "instruction": (
                f"Compress the existing summary and events into <= {MAX_SUMMARY_CHARS} characters; "
                "preserve reusable facts, failure-avoidance lessons, permissions, and evidence rules; "
                "a correction event replaces the event named by retracts_event_id."
            ),
        }

    @staticmethod
    def _memory_for_toml(
        summary: str,
        pending: Sequence[sqlite3.Row],
        *,
        fits: Callable[[str], bool],
        max_bytes: int = MAX_MEMORY_BYTES,
    ) -> str:
        initial = memory_block(summary, [])
        if len(initial.encode("utf-8")) > max_bytes or not fits(initial):
            raise SpecialistError("stored experience summary exceeds the current agent capacity")
        selected: list[str] = []
        for row in pending:
            lesson = row["lesson"]
            candidate = memory_block(summary, [*selected, lesson])
            if len(candidate.encode("utf-8")) > max_bytes or not fits(candidate):
                break
            selected.append(lesson)
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
        speed: str | None = None,
        expected_sha256: str | None = None,
        global_domain_key: str,
        global_contract: dict[str, Any] | str,
        origin_terms: Iterable[str] = (),
    ) -> dict[str, Any]:
        role_key = validate_role_key(role_key)
        display_name = validate_display_name(display_name)
        description = validate_description(description)
        role_instructions = validate_role_instructions(role_instructions)
        model = validate_model(model)
        effort = validate_effort(effort)
        authority = validate_authority(authority)
        speed = resolve_ensure_speed(model, speed)
        terms = normalize_origin_terms(origin_terms)
        global_domain_key = validate_global_domain_key(global_domain_key)
        canonical_contract, contract_digest, contract = normalize_global_contract(
            global_contract,
            domain_key=global_domain_key,
            origin_terms=terms,
        )
        persistent_fields = {
            "role_key": role_key,
            "display_name": display_name,
            "description": description,
            "role_instructions": role_instructions,
        }
        for field, value in persistent_fields.items():
            if contains_forbidden_persistent_data(value):
                raise SpecialistError(
                    f"{field} contains a URL, absolute path, credential-like data, or control characters"
                )
            reject_origin_terms(value, terms, field=field)
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
                if summary:
                    reject_origin_terms(summary, terms, field="existing experience summary")
                for event in pending:
                    reject_origin_terms(event["lesson"], terms, field="existing experience")
                desired_base = base_instructions(
                    display_name=display_name,
                    role_key=role_key,
                    role_instructions=role_instructions,
                    model=model,
                    effort=effort,
                    authority=authority,
                    speed=speed,
                    global_contract=contract,
                )
                def render_desired(candidate: str) -> bytes:
                    return _render_agent_bytes(
                        agent_id=row["agent_id"],
                        role_key=role_key,
                        owner_token=header["owner_token"],
                        name=row["name"],
                        display_name=display_name,
                        description=description,
                        model=model,
                        effort=effort,
                        authority=authority,
                        instruction_base=desired_base,
                        memory=candidate,
                        speed=speed,
                        global_domain_key=global_domain_key,
                        global_contract_digest=contract_digest,
                    )
                memory = self._memory_for_toml(
                    summary,
                    pending,
                    fits=lambda candidate: len(render_desired(candidate))
                    <= MAX_AGENT_BYTES,
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
                    instruction_base=desired_base,
                    memory=memory,
                    speed=speed,
                    global_domain_key=global_domain_key,
                    global_contract_digest=contract_digest,
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
                        "internal_message_runtime_route": INTERNAL_MESSAGE_RUNTIME_ROUTE,
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
                        "internal_message_runtime_route": INTERNAL_MESSAGE_RUNTIME_ROUTE,
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
                connection.execute(
                    "UPDATE agents SET global_contract_version = ?, global_domain_key = ?, "
                    "global_contract = ?, global_contract_digest = ? WHERE agent_id = ?",
                    (
                        GLOBAL_CONTRACT_VERSION,
                        global_domain_key,
                        canonical_contract,
                        contract_digest,
                        row["agent_id"],
                    ),
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
                    "internal_message_runtime_route": INTERNAL_MESSAGE_RUNTIME_ROUTE,
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
                speed=speed,
                global_contract=contract,
            )
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
                instruction_base=base,
                memory=memory_block("", []),
                speed=speed,
                global_domain_key=global_domain_key,
                global_contract_digest=contract_digest,
            )
            write_new_file(path, data)
            created_path = path
            created_bytes = data
            digest = sha256_bytes(data)
            now = utc_now()
            connection.execute(
                "INSERT INTO agents(agent_id,name,role_key,path,owner_token,expected_sha256,created_at,updated_at,"
                "global_contract_version,global_domain_key,global_contract,global_contract_digest) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    agent_id, name, role_key, str(path), owner_token, digest, now, now,
                    GLOBAL_CONTRACT_VERSION, global_domain_key, canonical_contract, contract_digest,
                ),
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
                "current_task_fallback": INTERNAL_MESSAGE_RUNTIME_ROUTE,
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
        current_instructions = payload.get("developer_instructions")
        if not isinstance(current_instructions, str):
            raise SpecialistError("agent developer_instructions is invalid")
        description = payload.get("description")
        if not isinstance(description, str) or "：" not in description:
            raise SpecialistError("agent description is invalid")
        display_name, short_description = description.split("：", 1)
        header = parse_header(original.decode("utf-8"))
        speed = speed_from_payload(payload)
        def render_rewritten(candidate: str) -> bytes:
            return _render_agent_bytes(
                agent_id=row["agent_id"],
                role_key=row["role_key"],
                owner_token=header["owner_token"],
                name=row["name"],
                display_name=display_name,
                description=short_description,
                model=str(payload["model"]),
                effort=str(payload["model_reasoning_effort"]),
                authority=(
                    "write"
                    if payload["sandbox_mode"] == "workspace-write"
                    else "read"
                ),
                instruction_base=current_instructions,
                memory=candidate,
                speed=speed,
                global_domain_key=row["global_domain_key"],
                global_contract_digest=row["global_contract_digest"],
            )
        memory = self._memory_for_toml(
            summary,
            pending,
            fits=lambda candidate: len(render_rewritten(candidate)) <= MAX_AGENT_BYTES,
        )
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
            instruction_base=current_instructions,
            memory=memory,
            speed=speed,
            global_domain_key=row["global_domain_key"],
            global_contract_digest=row["global_contract_digest"],
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
        retracts_event_id: str | None = None,
        origin_terms: Iterable[str] = (),
    ) -> dict[str, Any]:
        lesson = validate_lesson(lesson)
        terms = normalize_origin_terms(origin_terms)
        reject_origin_terms(lesson, terms, field="experience")
        event_id = event_id or str(uuid.uuid4())
        if not UUID_RE.fullmatch(event_id):
            raise SpecialistError("event_id must be a UUID")
        if retracts_event_id is not None:
            if not UUID_RE.fullmatch(retracts_event_id):
                raise SpecialistError("retracts_event_id must be a UUID")
            if retracts_event_id == event_id:
                raise SpecialistError("a correction cannot retract itself")
        digest_input = (
            lesson.encode("utf-8")
            if retracts_event_id is None
            else json.dumps(
                {"lesson": lesson, "retracts_event_id": retracts_event_id},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        )
        event_digest = sha256_bytes(digest_input)
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
                "SELECT event_digest, retracts_event_id FROM experience_events "
                "WHERE agent_id = ? AND event_id = ?",
                (row["agent_id"], event_id),
            ).fetchone()
            if existing is not None and existing["event_digest"] != event_digest:
                raise SpecialistError("event_id was replayed with different experience")
            if existing is not None and existing["retracts_event_id"] != retracts_event_id:
                raise SpecialistError("event_id was replayed with a different correction target")
            target: sqlite3.Row | None = None
            if retracts_event_id is not None:
                target = connection.execute(
                    "SELECT sequence, retracts_event_id FROM experience_events "
                    "WHERE agent_id = ? AND event_id = ?",
                    (row["agent_id"], retracts_event_id),
                ).fetchone()
                if target is None:
                    raise SpecialistError("correction target is not an experience of this specialist")
                if target["retracts_event_id"] is not None:
                    raise SpecialistError("a correction event cannot itself be retracted")
                prior = connection.execute(
                    "SELECT event_id FROM experience_events "
                    "WHERE agent_id = ? AND retracts_event_id = ?",
                    (row["agent_id"], retracts_event_id),
                ).fetchone()
                if prior is not None and prior["event_id"] != event_id:
                    raise SpecialistError("experience already has a different correction event")
            if existing is None:
                connection.execute(
                    "INSERT INTO experience_events("
                    "agent_id,event_id,event_digest,lesson,retracts_event_id,created_at"
                    ") VALUES(?,?,?,?,?,?)",
                    (
                        row["agent_id"],
                        event_id,
                        event_digest,
                        lesson,
                        retracts_event_id,
                        utc_now(),
                    ),
                )
            summary_row = self._summary_row(connection, row["agent_id"])
            summary = summary_row["summary"] if summary_row is not None else ""
            covered = int(summary_row["covered_through_sequence"]) if summary_row is not None else 0
            summary_reset = False
            if (
                existing is None
                and target is not None
                and int(target["sequence"]) <= covered
            ):
                connection.execute(
                    "DELETE FROM experience_summaries WHERE agent_id = ?",
                    (row["agent_id"],),
                )
                summary = ""
                covered = 0
                summary_reset = True
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
            if retracts_event_id is not None:
                action = (
                    "experience_correction_already_recorded"
                    if existing is not None
                    else "experience_corrected"
                )
            else:
                action = (
                    "experience_already_recorded"
                    if existing is not None
                    else "experience_recorded"
                )
            return {
                "ok": True,
                "action": action,
                "event_id": event_id,
                "retracts_event_id": retracts_event_id,
                "summary_reset": summary_reset,
                "raw_experience_preserved": True,
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
        origin_terms: Iterable[str] = (),
    ) -> dict[str, Any]:
        summary = validate_summary(summary)
        terms = normalize_origin_terms(origin_terms)
        reject_origin_terms(summary, terms, field="summary")
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

    def record_run(
        self,
        *,
        name: str,
        expected_sha256: str,
        run_id: str,
        invocation_kind: str,
    ) -> dict[str, Any]:
        expected_sha256 = validate_sha256(expected_sha256)
        if not UUID_RE.fullmatch(run_id):
            raise SpecialistError("run_id must be a UUID")
        if invocation_kind not in INVOCATION_KINDS:
            raise SpecialistError(
                f"invocation_kind must be one of {sorted(INVOCATION_KINDS)}"
            )
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row, _, _, _, _ = self._owned_agent(
                connection,
                name=name,
                expected_sha256=expected_sha256,
            )
            existing = connection.execute(
                "SELECT agent_id, invocation_kind, completed_at "
                "FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if existing is not None and (
                existing["agent_id"] != row["agent_id"]
                or existing["invocation_kind"] != invocation_kind
            ):
                raise SpecialistError(
                    "run_id was replayed for a different specialist or invocation kind"
                )
            if existing is None:
                completed_at = utc_now()
                connection.execute(
                    "INSERT INTO agent_runs(run_id,agent_id,invocation_kind,completed_at) "
                    "VALUES(?,?,?,?)",
                    (run_id, row["agent_id"], invocation_kind, completed_at),
                )
                action = "survival_round_recorded"
            else:
                completed_at = existing["completed_at"]
                action = "survival_round_already_recorded"
            survival_rounds = int(
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE agent_id = ?",
                    (row["agent_id"],),
                ).fetchone()[0]
            )
            connection.execute("COMMIT")
            return {
                "ok": True,
                "action": action,
                "name": name,
                "run_id": run_id,
                "invocation_kind": invocation_kind,
                "completed_at": completed_at,
                "survival_rounds": survival_rounds,
                "historical_backfill": False,
            }
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def status(self, *, for_routing: bool = False) -> dict[str, Any]:
        connection = self.connect()
        try:
            rows = list(
                connection.execute(
                    "SELECT agents.*, "
                    "(SELECT COUNT(*) FROM agent_runs "
                    " WHERE agent_runs.agent_id = agents.agent_id) AS survival_rounds, "
                    "(SELECT COUNT(*) FROM experience_events "
                    " WHERE experience_events.agent_id = agents.agent_id) AS experience_count "
                    "FROM agents ORDER BY role_key"
                )
            )
            registered: list[dict[str, Any]] = []
            routing_catalog: list[dict[str, Any]] = []
            for row in rows:
                _, path, _, payload, _ = self._owned_agent(
                    connection,
                    name=row["name"],
                    expected_sha256=row["expected_sha256"],
                )
                authority = (
                    "write" if payload.get("sandbox_mode") == "workspace-write" else "read"
                )
                speed = speed_from_payload(payload)
                contract = json.loads(row["global_contract"])
                registered.append({
                    "name": row["name"],
                    "role_key": row["role_key"],
                    "path": str(path),
                    "model": payload.get("model"),
                    "reasoning_effort": payload.get("model_reasoning_effort"),
                    "speed": speed,
                    "authority": authority,
                    "sha256": row["expected_sha256"],
                    "survival_rounds": int(row["survival_rounds"]),
                    "experience_count": int(row["experience_count"]),
                    "scope": GLOBAL_SCOPE,
                    "global_contract_version": int(row["global_contract_version"]),
                    "global_domain_key": row["global_domain_key"],
                    "global_contract": contract,
                    "global_contract_digest": row["global_contract_digest"],
                })
                if for_routing:
                    description = payload.get("description")
                    if not isinstance(description, str):
                        raise SpecialistError("agent description configuration is invalid")
                    routing_catalog.append({
                        "name": row["name"],
                        "description": description,
                        "global_domain_key": row["global_domain_key"],
                        "global_contract": contract,
                        "model": payload.get("model"),
                        "reasoning_effort": payload.get("model_reasoning_effort"),
                        "speed": speed,
                        "authority": authority,
                    })
            if for_routing:
                return {
                    "ok": True,
                    "action": "status",
                    "for_routing": True,
                    "registered_agents": routing_catalog,
                    "registered_count": len(registered),
                }
            disk_names = sorted(path.name for path in self.agents_dir.glob("lean_*.toml"))
            if len(disk_names) > MAX_MANAGED_SCAN_FILES:
                raise AuxiliarySkipped(
                    f"managed specialist scan exceeded {MAX_MANAGED_SCAN_FILES} files"
                )
            registered_files = {Path(item["path"]).name for item in registered}
            legacy_count = 0
            for disk_name in disk_names:
                disk_path = self.agents_dir / disk_name
                with contextlib.suppress(OSError, UnicodeError):
                    metadata = os.lstat(disk_path)
                    if (
                        stat.S_ISLNK(metadata.st_mode)
                        or is_reparse_point(metadata)
                        or not stat.S_ISREG(metadata.st_mode)
                        or metadata.st_nlink != 1
                        or metadata.st_size > MAX_AGENT_BYTES
                    ):
                        continue
                    disk_text = disk_path.read_text(encoding="utf-8")
                    if disk_text.startswith(MANAGED_MARKER + "\n") and (
                        GLOBAL_SCOPE_PREFIX + GLOBAL_SCOPE
                    ) not in disk_text.splitlines()[:12]:
                        legacy_count += 1
            return {
                "ok": True,
                "action": "status",
                "schema_version": SCHEMA_VERSION,
                "registered_agents": registered,
                "registered_count": len(registered),
                "global_count": len(registered),
                "legacy_count": legacy_count,
                "lean_agent_files_total": len(disk_names),
                "unregistered_lean_agent_files": [
                    name for name in disk_names if name not in registered_files
                ],
                "survival_round_definition": (
                    "one verified retained specialist current subtask completed and accepted"
                ),
                "historical_backfill": False,
                "internal_message_runtime_route": INTERNAL_MESSAGE_RUNTIME_ROUTE,
            }
        finally:
            connection.close()

    def _receipt_paths(self, agent_id: str, digest: str) -> tuple[Path, Path]:
        base = f"{agent_id}.{digest}"
        return (
            self.pending_deletion_dir / f"{base}.toml",
            self.pending_deletion_dir / f"{base}.receipt.json",
        )

    def _load_retirement_receipt(
        self,
        *,
        name: str | None,
        receipt_path: Path | None,
        expected_sha256: str,
    ) -> tuple[dict[str, Any], Path, bytes, Path, bytes, dict[str, Any], dict[str, str]]:
        pending_dir = ensure_plain_directory(self.pending_deletion_dir, create=False)
        if (name is None) == (receipt_path is None):
            raise SpecialistError("restore requires exactly one of name or receipt")
        candidates: list[Path]
        if receipt_path is not None:
            candidates = [receipt_path.expanduser().absolute()]
        else:
            if name is None or not NAME_RE.fullmatch(name):
                raise SpecialistError("restore name is invalid")
            candidates = []
            for index, candidate in enumerate(pending_dir.glob("*.receipt.json")):
                if index >= MAX_MANAGED_SCAN_FILES:
                    raise AuxiliarySkipped(
                        f"retirement receipt scan exceeded {MAX_MANAGED_SCAN_FILES} files"
                    )
                validate_direct_plain_file(
                    candidate,
                    pending_dir,
                    kind="retirement receipt",
                    max_bytes=MAX_RECEIPT_BYTES,
                )
                raw = candidate.read_bytes()
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise SpecialistError(f"retirement receipt is invalid: {candidate}") from exc
                if isinstance(parsed, dict) and parsed.get("name") == name:
                    candidates.append(candidate)
            if len(candidates) != 1:
                raise SpecialistError(
                    f"restore name must match exactly one pending retirement receipt: {name}"
                )
        selected = candidates[0]
        validate_direct_plain_file(
            selected,
            pending_dir,
            kind="retirement receipt",
            max_bytes=MAX_RECEIPT_BYTES,
        )
        receipt_bytes = selected.read_bytes()
        try:
            receipt = json.loads(receipt_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SpecialistError("retirement receipt is not valid UTF-8 JSON") from exc
        required = {
            "format_version",
            "agent_id",
            "name",
            "role_key",
            "original_path",
            "pending_path",
            "sha256",
            "created_at",
            "updated_at",
            "retired_at",
            "global_contract_version",
            "global_domain_key",
            "global_contract",
            "global_contract_digest",
        }
        if not isinstance(receipt, dict) or not required.issubset(receipt):
            raise SpecialistError("retirement receipt is missing required fields")
        if "owner_token" in receipt:
            raise SpecialistError("retirement receipt must not contain owner_token")
        if receipt["format_version"] != RETIREMENT_RECEIPT_FORMAT_VERSION:
            raise SpecialistError("retirement receipt format_version is unsupported")
        string_fields = required - {"format_version", "global_contract_version"}
        if any(not isinstance(receipt[field], str) for field in string_fields):
            raise SpecialistError("retirement receipt field types are invalid")
        if not UUID_RE.fullmatch(receipt["agent_id"]):
            raise SpecialistError("retirement receipt agent_id is invalid")
        if not NAME_RE.fullmatch(receipt["name"]):
            raise SpecialistError("retirement receipt name is invalid")
        validate_role_key(receipt["role_key"])
        if receipt["global_contract_version"] != GLOBAL_CONTRACT_VERSION:
            raise SpecialistError("retirement receipt global contract version is invalid")
        domain_key = validate_global_domain_key(receipt["global_domain_key"])
        canonical_contract, contract_digest, _ = normalize_global_contract(
            receipt["global_contract"], domain_key=domain_key
        )
        if canonical_contract != receipt["global_contract"] or contract_digest != receipt["global_contract_digest"]:
            raise SpecialistError("retirement receipt global contract is inconsistent")
        if receipt["sha256"] != expected_sha256:
            raise SpecialistError("expected SHA-256 does not match the retirement receipt")
        for field in ("created_at", "updated_at", "retired_at"):
            if not isinstance(receipt[field], str) or not receipt[field]:
                raise SpecialistError(f"retirement receipt {field} is invalid")
        pending_path, expected_receipt_path = self._receipt_paths(
            receipt["agent_id"], receipt["sha256"]
        )
        original_path = (self.agents_dir / f"{receipt['name']}.toml").absolute()
        if selected != expected_receipt_path.absolute():
            raise SpecialistError("retirement receipt filename does not match its identity")
        if Path(receipt["pending_path"]).absolute() != pending_path.absolute():
            raise SpecialistError("retirement receipt pending_path is inconsistent")
        if Path(receipt["original_path"]).absolute() != original_path:
            raise SpecialistError("retirement receipt original_path is inconsistent")
        validate_direct_plain_file(
            pending_path,
            pending_dir,
            kind="pending specialist",
            max_bytes=MAX_AGENT_BYTES,
        )
        data = pending_path.read_bytes()
        if sha256_bytes(data) != expected_sha256:
            raise SpecialistError("pending specialist SHA-256 does not match the receipt")
        text = data.decode("utf-8")
        header = parse_header(text)
        payload = tomllib.loads(text)
        if (
            header["agent_id"] != receipt["agent_id"]
            or header["role_key"] != receipt["role_key"]
            or header["global_domain_key"] != receipt["global_domain_key"]
            or header["global_contract_digest"] != receipt["global_contract_digest"]
            or payload.get("name") != receipt["name"]
        ):
            raise SpecialistError("pending specialist identity does not match the receipt")
        return receipt, selected, receipt_bytes, pending_path, data, payload, header

    @staticmethod
    def _rollback_exact_move(
        *,
        source: Path,
        destination: Path,
        expected: bytes,
        source_parent: Path,
        kind: str,
        max_bytes: int,
    ) -> str | None:
        if not path_exists_without_following_links(source):
            return f"{kind} rollback source is missing: {source}"
        try:
            validate_direct_plain_file(
                source,
                source_parent,
                kind=kind,
                max_bytes=max_bytes,
            )
            if source.read_bytes() != expected:
                return f"{kind} rollback source bytes changed: {source}"
            if path_exists_without_following_links(destination):
                return f"{kind} rollback destination appeared concurrently: {destination}"
            rename_no_replace(source, destination)
        except (OSError, SpecialistError) as exc:
            return f"{kind} rollback failed: {exc}"
        return None

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
        pending_path: Path | None = None
        receipt_path: Path | None = None
        moved_to_pending = False
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
            if row is None:
                connection.execute("COMMIT")
                committed = True
                return {"ok": True, "action": "already_absent", "deleted": False}
            path = Path(row["path"]).absolute()
            if not path_exists_without_following_links(path):
                if expected_sha256 != row["expected_sha256"]:
                    raise SpecialistError(
                        "expected SHA-256 does not match the missing agent's ownership row"
                    )
                if owner_token != row["owner_token"]:
                    raise SpecialistError(
                        "provided owner token does not match the missing agent's ownership row"
                    )
            else:
                _, path, data, _, _ = self._owned_agent(
                    connection,
                    name=name,
                    expected_sha256=expected_sha256,
                    owner_token=owner_token,
                )
            experience_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM experience_events WHERE agent_id = ?",
                    (row["agent_id"],),
                ).fetchone()[0]
            )
            if experience_count:
                raise SpecialistError(
                    "owned specialist with recorded experience cannot be retired"
                )
            survival_rounds = int(
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE agent_id = ?",
                    (row["agent_id"],),
                ).fetchone()[0]
            )
            if survival_rounds:
                raise SpecialistError(
                    "owned specialist with recorded survival rounds cannot be retired"
                )
            if data is None:
                connection.execute("DELETE FROM agents WHERE agent_id = ?", (row["agent_id"],))
                connection.execute("COMMIT")
                committed = True
                return {
                    "ok": True,
                    "action": "stale_registry_row_removed",
                    "deleted": False,
                }
            pending_dir = ensure_plain_directory(self.pending_deletion_dir, create=True)
            pending_path, receipt_path = self._receipt_paths(
                row["agent_id"], expected_sha256
            )
            if path_exists_without_following_links(pending_path):
                raise SpecialistError(f"pending specialist target already exists: {pending_path}")
            if path_exists_without_following_links(receipt_path):
                raise SpecialistError(f"retirement receipt target already exists: {receipt_path}")
            validate_direct_agent_file(path, self.agents_dir)
            if path.read_bytes() != data or sha256_bytes(data) != expected_sha256:
                raise SpecialistError("agent changed immediately before retirement")
            retired_at = utc_now()
            receipt = {
                "format_version": RETIREMENT_RECEIPT_FORMAT_VERSION,
                "agent_id": row["agent_id"],
                "name": row["name"],
                "role_key": row["role_key"],
                "original_path": str(path),
                "pending_path": str(pending_path),
                "sha256": expected_sha256,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "retired_at": retired_at,
                "global_contract_version": int(row["global_contract_version"]),
                "global_domain_key": row["global_domain_key"],
                "global_contract": row["global_contract"],
                "global_contract_digest": row["global_contract_digest"],
            }
            receipt_bytes = receipt_json_bytes(receipt)
            write_new_file(receipt_path, receipt_bytes)
            validate_direct_plain_file(
                receipt_path,
                pending_dir,
                kind="retirement receipt",
                max_bytes=MAX_RECEIPT_BYTES,
            )
            if receipt_path.read_bytes() != receipt_bytes:
                raise SpecialistError("retirement receipt changed immediately after creation")
            rename_no_replace(path, pending_path)
            moved_to_pending = True
            validate_direct_plain_file(
                pending_path,
                pending_dir,
                kind="pending specialist",
                max_bytes=MAX_AGENT_BYTES,
            )
            if pending_path.read_bytes() != data:
                raise SpecialistError("pending specialist changed immediately after retirement")
            connection.execute("DELETE FROM agents WHERE agent_id = ?", (row["agent_id"],))
            connection.execute("COMMIT")
            committed = True
            return {
                "ok": True,
                "action": "retired_to_pending_deletion",
                "deleted": True,
                "deleted_from": "active_specialist_registry",
                "recoverable": True,
                "disposition": "plugin_pending_deletion",
                "path": str(path),
                "original_path": str(path),
                "pending_path": str(pending_path),
                "receipt_path": str(receipt_path),
                "sha256": expected_sha256,
                "agent_id": row["agent_id"],
            }
        except BaseException as exc:
            if committed:
                raise
            rollback_error: str | None = None
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error as rollback_exc:
                rollback_error = f"database rollback failed: {rollback_exc}"
            if (
                moved_to_pending
                and path is not None
                and pending_path is not None
                and data is not None
            ):
                move_error = self._rollback_exact_move(
                    source=pending_path,
                    destination=path,
                    expected=data,
                    source_parent=self.pending_deletion_dir,
                    kind="pending specialist",
                    max_bytes=MAX_AGENT_BYTES,
                )
                rollback_error = rollback_error or move_error
            if rollback_error is not None:
                raise SpecialistError(
                    f"retirement failed and exact recovery was not completed: {rollback_error}"
                ) from exc
            raise
        finally:
            connection.close()

    def restore(
        self,
        *,
        expected_sha256: str,
        owner_token: str,
        name: str | None = None,
        receipt: Path | None = None,
    ) -> dict[str, Any]:
        expected_sha256 = validate_sha256(expected_sha256)
        if not TOKEN_RE.fullmatch(owner_token):
            raise SpecialistError("owner_token is invalid")
        connection = self.connect()
        original_path: Path | None = None
        pending_path: Path | None = None
        data: bytes | None = None
        moved_to_original = False
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            (
                receipt_data,
                receipt_path,
                receipt_bytes,
                pending_path,
                data,
                _,
                header,
            ) = self._load_retirement_receipt(
                name=name,
                receipt_path=receipt,
                expected_sha256=expected_sha256,
            )
            if header["owner_token"] != owner_token:
                raise SpecialistError("provided owner token is incorrect")
            original_path = Path(receipt_data["original_path"]).absolute()
            conflict = connection.execute(
                "SELECT agent_id, name, role_key, path FROM agents "
                "WHERE agent_id = ? OR name = ? OR role_key = ? OR path = ? LIMIT 1",
                (
                    receipt_data["agent_id"],
                    receipt_data["name"],
                    receipt_data["role_key"],
                    str(original_path),
                ),
            ).fetchone()
            if conflict is not None:
                raise SpecialistError(
                    "active registry has an agent_id, name, role_key, or path conflict"
                )
            if path_exists_without_following_links(original_path):
                raise SpecialistError(f"original specialist target already exists: {original_path}")
            validate_direct_plain_file(
                pending_path,
                self.pending_deletion_dir,
                kind="pending specialist",
                max_bytes=MAX_AGENT_BYTES,
            )
            if pending_path.read_bytes() != data:
                raise SpecialistError("pending specialist changed immediately before restore")
            ensure_plain_directory(self.restored_receipt_dir, create=True)
            rename_no_replace(pending_path, original_path)
            moved_to_original = True
            validate_direct_agent_file(original_path, self.agents_dir)
            if original_path.read_bytes() != data:
                raise SpecialistError("restored specialist changed immediately after restore")
            connection.execute(
                "INSERT INTO agents(agent_id,name,role_key,path,owner_token,expected_sha256,created_at,updated_at,"
                "global_contract_version,global_domain_key,global_contract,global_contract_digest) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    receipt_data["agent_id"],
                    receipt_data["name"],
                    receipt_data["role_key"],
                    str(original_path),
                    owner_token,
                    expected_sha256,
                    receipt_data["created_at"],
                    receipt_data["updated_at"],
                    receipt_data["global_contract_version"],
                    receipt_data["global_domain_key"],
                    receipt_data["global_contract"],
                    receipt_data["global_contract_digest"],
                ),
            )
            connection.execute("COMMIT")
            committed = True

            archive_path = self.restored_receipt_dir / (
                f"{receipt_data['agent_id']}.{expected_sha256}.restored."
                f"{uuid.uuid4().hex}.receipt.json"
            )
            receipt_disposition = "archived_after_restore"
            receipt_archive_error: str | None = None
            try:
                validate_direct_plain_file(
                    receipt_path,
                    self.pending_deletion_dir,
                    kind="retirement receipt",
                    max_bytes=MAX_RECEIPT_BYTES,
                )
                if receipt_path.read_bytes() != receipt_bytes:
                    raise SpecialistError("retirement receipt changed before archival")
                rename_no_replace(receipt_path, archive_path)
            except (OSError, SpecialistError) as archive_exc:
                archive_path = receipt_path
                receipt_disposition = "retained_after_archive_conflict"
                receipt_archive_error = str(archive_exc)
            result = {
                "ok": True,
                "action": "restored_from_pending_deletion",
                "restored": True,
                "path": str(original_path),
                "original_path": str(original_path),
                "pending_path": str(pending_path),
                "receipt_path": str(archive_path),
                "receipt_disposition": receipt_disposition,
                "receipt_replayable": False,
                "replay_prevention": "active_registry_identity_conflicts",
                "sha256": expected_sha256,
                "agent_id": receipt_data["agent_id"],
                "name": receipt_data["name"],
                "role_key": receipt_data["role_key"],
            }
            if receipt_archive_error is not None:
                result["receipt_archive_error"] = receipt_archive_error
            return result
        except BaseException as exc:
            if committed:
                raise
            rollback_error: str | None = None
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error as rollback_exc:
                rollback_error = f"database rollback failed: {rollback_exc}"
            if (
                moved_to_original
                and original_path is not None
                and pending_path is not None
                and data is not None
            ):
                move_error = self._rollback_exact_move(
                    source=original_path,
                    destination=pending_path,
                    expected=data,
                    source_parent=self.agents_dir,
                    kind="restored specialist",
                    max_bytes=MAX_AGENT_BYTES,
                )
                rollback_error = rollback_error or move_error
            if rollback_error is not None:
                raise SpecialistError(
                    f"restore failed and exact recovery was not completed: {rollback_error}"
                ) from exc
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
    ensure.add_argument(
        "--speed",
        choices=sorted(SPEEDS),
        help="explicit speed; omitted Luna roles default to fast and other models to standard",
    )
    ensure.add_argument("--authority", required=True, choices=sorted(AUTHORITIES))
    ensure.add_argument("--global-domain-key", required=True)
    ensure.add_argument(
        "--global-contract",
        required=True,
        help="canonicalizable JSON object defining the global domain contract",
    )
    ensure.add_argument("--origin-term", action="append", default=[])
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
    improve.add_argument(
        "--retracts-event-id",
        help="append a correction that removes one prior event from active memory",
    )
    improve.add_argument("--covered-through", type=int)
    improve.add_argument("--source-digest")
    improve.add_argument("--origin-term", action="append", default=[])

    migrate = subparsers.add_parser(
        "migrate-global",
        help="explicitly globalize every exact v1/v2/v3 retained specialist from one UTF-8 JSON plan",
    )
    migrate.add_argument("--plan", required=True, type=Path)

    record_run = subparsers.add_parser(
        "record-run",
        help="idempotently record one verified successful retained-agent survival round",
    )
    record_run.add_argument("--name", required=True)
    record_run.add_argument("--expected-sha256", required=True)
    record_run.add_argument("--run-id", required=True)
    record_run.add_argument(
        "--invocation-kind",
        required=True,
        choices=sorted(INVOCATION_KINDS),
    )

    status = subparsers.add_parser(
        "status",
        help="report registered specialists, survival rounds, and unregistered lean files",
    )
    status.add_argument(
        "--for-routing",
        action="store_true",
        help="return a bounded reusable-domain catalog without lifecycle internals",
    )

    delete = subparsers.add_parser(
        "delete",
        help="recoverably retire one exactly owned unused specialist to plugin pending deletion",
    )
    delete.add_argument("--name", required=True)
    delete.add_argument("--expected-sha256", required=True)
    delete.add_argument("--owner-token", required=True)

    restore = subparsers.add_parser(
        "restore",
        help="restore one exactly verified specialist from plugin pending deletion",
    )
    restore_identity = restore.add_mutually_exclusive_group(required=True)
    restore_identity.add_argument("--name")
    restore_identity.add_argument("--receipt", type=Path)
    restore.add_argument("--expected-sha256", required=True)
    restore.add_argument("--owner-token", required=True)
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
            speed=arguments.speed,
            expected_sha256=arguments.expected_sha256,
            global_domain_key=arguments.global_domain_key,
            global_contract=arguments.global_contract,
            origin_terms=arguments.origin_term,
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
                retracts_event_id=arguments.retracts_event_id,
                origin_terms=arguments.origin_term,
            )
        if arguments.covered_through is None or arguments.source_digest is None:
            raise SpecialistError("summary mode requires --covered-through and --source-digest")
        if arguments.event_id is not None:
            raise SpecialistError("summary mode does not accept --event-id")
        if arguments.retracts_event_id is not None:
            raise SpecialistError("summary mode does not accept --retracts-event-id")
        return registry.improve_with_summary(
            name=arguments.name,
            expected_sha256=arguments.expected_sha256,
            summary=arguments.summary,
            covered_through=arguments.covered_through,
            source_digest=arguments.source_digest,
            origin_terms=arguments.origin_term,
        )
    if arguments.command == "migrate-global":
        return registry.migrate_global(plan_path=arguments.plan)
    if arguments.command == "record-run":
        return registry.record_run(
            name=arguments.name,
            expected_sha256=arguments.expected_sha256,
            run_id=arguments.run_id,
            invocation_kind=arguments.invocation_kind,
        )
    if arguments.command == "status":
        return registry.status(for_routing=arguments.for_routing)
    if arguments.command == "delete":
        return registry.delete(
            name=arguments.name,
            expected_sha256=arguments.expected_sha256,
            owner_token=arguments.owner_token,
        )
    if arguments.command == "restore":
        return registry.restore(
            name=arguments.name,
            receipt=arguments.receipt,
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
