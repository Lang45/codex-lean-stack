#!/usr/bin/env python3
"""Deterministic lifecycle manager for Codex Lean Stack custom agents.

The skill makes semantic decisions. This script owns every persistent mutation:
creation, evidence recording, candidate promotion, quarantine, and restore.
Only agents created and registered by this script are mutable.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import stat
import statistics
import sys
import tempfile
import time
import tomllib
import uuid
from pathlib import Path
from typing import Any, Iterator, Sequence


SCHEMA_VERSION = 4
ROUTING_POLICY_VERSION = 2
VARIATION_POLICY_VERSION = 1
BUILTIN_AGENTS = ("default", "worker", "explorer")
MANAGED_PREFIX = "lean_"
MAX_ACTIVE_MANAGED_AGENTS = 8
MAX_AGENT_FILE_BYTES = 16 * 1024
MAX_INSTRUCTION_BYTES = 6 * 1024
MAX_PROMOTED_RULES = 12
MIN_RULE_OBSERVATIONS = 3
MAX_VARIATION_CANDIDATES = 4
MAX_VARIATION_WALL_SECONDS = 3600
MAX_VARIATION_TOOL_CALLS = 32

ALLOWED_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max", "ultra"}
ALLOWED_SANDBOXES = {"read-only", "workspace-write", "danger-full-access"}
ALLOWED_RISK_CEILINGS = {"read_only", "workspace_write", "external_effect"}
ALLOWED_TASK_CLASSES = {
    "exploration",
    "implementation",
    "review",
    "test",
    "documentation",
    "architecture",
    "other",
}
ALLOWED_EVIDENCE_FLAGS = {
    "before_after_repro",
    "tests_passed",
    "runtime_check",
    "diff_audit",
    "source_verified",
    "human_approved",
    "scope_audit",
    "safety_audit",
}
STRONG_EVIDENCE_FLAGS = {
    "tests_passed",
    "runtime_check",
    "source_verified",
    "human_approved",
}
ALLOWED_CRITICAL_EVENTS = {
    "none",
    "unauthorized_destructive_write",
    "unauthorized_external_effect",
    "sensitive_data_exposure",
    "fabricated_evidence_with_harm",
    "permission_bypass",
    "stop_instruction_violation_with_harm",
    "concurrent_write_conflict",
}
ALLOWED_CONFIRMATIONS = {"deterministic", "independent_model", "human"}
ALLOWED_JUDGES = {"parent", "deterministic", "independent_model", "human"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_BUCKETS = {"low", "expected", "high", "unknown"}
ALLOWED_BUDGET_BUCKETS = {"low", "expected", "high"}
ALLOWED_USER_VERDICTS = {"approve", "reject", "unknown"}
ALLOWED_REQUESTED_SERVICE_TIERS = {"inherit", "standard", "fast", "unknown"}
ALLOWED_EFFECTIVE_SERVICE_TIERS = {"standard", "fast", "priority", "unknown"}
ALLOWED_EXECUTION_MODES = {"managed_named", "explicit_fallback", "builtin", "unknown"}
ALLOWED_HOST_CONFIG_STATUS = {
    "effective_confirmed",
    "request_accepted",
    "unexposed",
    "unknown",
}
ALLOWED_ROUTING_ATTRIBUTIONS = {
    "model_capacity",
    "reasoning_depth",
    "compute_latency",
    "tool_or_environment",
    "role_mismatch",
    "unknown",
}
ALLOWED_FAILURE_REASONS = {
    "none",
    "incorrect_result",
    "missing_evidence",
    "scope_miss",
    "safety_boundary",
    "tool_failure",
    "timeout",
    "cost_overrun",
    "excessive_rework",
    "role_mismatch",
    "stale_host_status",
    "other",
}
NON_EVOLUTION_FAILURE_REASONS = {
    "tool_failure",
    "timeout",
    "role_mismatch",
    "stale_host_status",
}
ALLOWED_VARIATION_TRIGGERS = {"manual", "stagnation"}
ALLOWED_VARIATION_RATIONALES = {
    "quality_recovery",
    "evidence_strengthening",
    "scope_control",
    "safety_guard",
    "latency_reduction",
    "token_reduction",
    "credit_reduction",
    "rework_reduction",
    "novel_direction",
}
MUTABLE_STATES = {
    "pending_visibility",
    "pending_reload",
    "probation",
    "active",
    "degraded",
    "retire_eligible",
}

SPEC_KEYS = {
    "slug",
    "display_name",
    "description",
    "developer_instructions",
    "model",
    "model_reasoning_effort",
    "sandbox_mode",
    "capability_tags",
    "risk_ceiling",
}
REPORT_KEYS = {
    "agent_id",
    "run_id",
    "task_class",
    "risk_tier",
    "scores",
    "evidence_flags",
    "critical_event",
    "critical_confirmations",
    "judge_kind",
    "judge_confidence",
    "duration_bucket",
    "token_bucket",
    "user_verdict",
    "experience",
    "routing",
    "credit_bucket",
    "retry_count",
    "rework_count",
    "failure_reason",
}
ROUTING_KEYS = {
    "requested_model",
    "requested_reasoning_effort",
    "requested_service_tier",
    "effective_model",
    "effective_reasoning_effort",
    "effective_service_tier",
    "execution_mode",
    "host_config_status",
    "attribution",
}
SCORE_LIMITS = {
    "correctness": 35,
    "evidence": 20,
    "scope": 15,
    "efficiency": 15,
    "clarity": 10,
    "safety": 5,
}
PROMOTION_KEYS = {
    "candidate_id",
    "case_count",
    "incumbent_quality",
    "challenger_quality",
    "incumbent_efficiency",
    "challenger_efficiency",
    "evidence_flags",
    "critical_regression",
    "judge_kind",
    "judge_confidence",
}
REPORT_METRIC_KEYS = {
    "credit_bucket",
    "retry_count",
    "rework_count",
    "failure_reason",
}
VARIATION_PLAN_KEYS = {
    "request_id",
    "agent_id",
    "task_class",
    "risk_tier",
    "trigger",
    "candidate_limit",
    "wall_time_seconds",
    "tool_call_limit",
    "token_bucket",
    "credit_bucket",
}
VARIATION_STAGE_KEYS = {
    "session_id",
    "elapsed_seconds",
    "tool_calls_used",
    "token_bucket_used",
    "credit_bucket_used",
    "supervisor_direction",
    "candidates",
}
VARIATION_CANDIDATE_KEYS = {
    "rule_key",
    "rule",
    "applies_to",
    "rationale_code",
}
VARIATION_COMPARISON_KEYS = {
    "tradeoff_accepted",
    "shadow_suite_sha256",
    "elapsed_seconds_total",
    "tool_calls_total",
    "token_bucket_total",
    "credit_bucket_total",
    "incumbent_duration_bucket",
    "challenger_duration_bucket",
    "incumbent_token_bucket",
    "challenger_token_bucket",
    "incumbent_credit_bucket",
    "challenger_credit_bucket",
    "incumbent_retry_count",
    "challenger_retry_count",
    "incumbent_rework_count",
    "challenger_rework_count",
}

MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TAG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
EXPERIENCE_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
MARKER_RE = re.compile(r"^# lean-stack-agent-id: ([0-9a-f-]{36})\r?$", re.MULTILINE)
URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://")
WINDOWS_PATH_RE = re.compile(r"(?i)(?:^|[\s\"'])(?:[a-z]:[\\/]|\\\\)")
UNIX_PATH_RE = re.compile(r"(?:^|[\s\"'])/(?:home|Users|mnt|etc|var|tmp)/")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|password|passwd|secret|token|cookie)\s*[:=]"
)

MODEL_ALIASES = {"gpt-5.6": "gpt-5.6-sol"}
MODEL_LADDERS_BY_TASK_CLASS = {
    "documentation": ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
    "exploration": ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
    "test": ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
    "review": ("gpt-5.6-terra", "gpt-5.6-sol"),
    "implementation": ("gpt-5.6-terra", "gpt-5.6-sol"),
    "architecture": ("gpt-5.6-sol",),
    "other": ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
}
EFFORT_LADDER = ("none", "low", "medium", "high", "xhigh", "max", "ultra")
MINIMUM_EFFORT_BY_TASK_CLASS = {
    "documentation": "medium",
    "exploration": "medium",
    "test": "medium",
    "review": "high",
    "implementation": "high",
    "architecture": "xhigh",
    "other": "medium",
}


class LifecycleError(RuntimeError):
    """A safe, user-actionable lifecycle failure."""


class OwnershipConflict(LifecycleError):
    """The active file no longer matches the plugin's recorded ownership."""


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evaluation_report_digests(report: dict[str, Any]) -> tuple[str, str]:
    current = sha256_bytes(json_text(report).encode("utf-8"))
    legacy = {key: value for key, value in report.items() if key not in REPORT_METRIC_KEYS}
    return current, sha256_bytes(json_text(legacy).encode("utf-8"))


def toml_string(value: str) -> str:
    # JSON strings are valid TOML basic strings for the characters accepted here.
    return json.dumps(value, ensure_ascii=False)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LifecycleError(f"{label} 必须是 JSON 对象")
    return value


def validate_exact_keys(
    value: dict[str, Any], *, allowed: set[str], required: set[str], label: str
) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise LifecycleError(f"{label} 含未知字段: {', '.join(unknown)}")
    if missing:
        raise LifecycleError(f"{label} 缺少字段: {', '.join(missing)}")


def validate_text(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int,
    reject_sensitive: bool = False,
) -> str:
    if not isinstance(value, str):
        raise LifecycleError(f"{label} 必须是字符串")
    normalized = value.strip()
    if not minimum <= len(normalized) <= maximum:
        raise LifecycleError(f"{label} 长度必须在 {minimum} 到 {maximum} 个字符之间")
    if "\x00" in normalized:
        raise LifecycleError(f"{label} 不能包含 NUL")
    if reject_sensitive:
        if URL_RE.search(normalized):
            raise LifecycleError(f"{label} 不能包含 URL")
        if WINDOWS_PATH_RE.search(normalized) or UNIX_PATH_RE.search(normalized):
            raise LifecycleError(f"{label} 不能包含绝对路径")
        if SECRET_ASSIGNMENT_RE.search(normalized):
            raise LifecycleError(f"{label} 疑似包含凭据或敏感赋值")
    return normalized


def load_bounded_json(path: Path, *, maximum: int = 64 * 1024) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LifecycleError(f"无法读取 JSON 文件: {path}") from exc
    if size > maximum:
        raise LifecycleError(f"JSON 文件超过 {maximum} 字节限制")
    try:
        return require_object(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"JSON 文件无效: {path}") from exc


def is_reparse_point(path_stat: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(path_stat, "st_file_attributes", 0) & attribute)


def ensure_plain_directory(path: Path, *, create: bool) -> None:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise LifecycleError(f"目录不存在或不是目录: {path}")
    info = path.lstat()
    if path.is_symlink() or is_reparse_point(info):
        raise LifecycleError(f"拒绝使用符号链接或 reparse 目录: {path}")


def ensure_direct_child(path: Path, root: Path, *, must_exist: bool) -> None:
    ensure_plain_directory(root, create=not must_exist)
    resolved_root = root.resolve()
    if path.parent.resolve() != resolved_root:
        raise LifecycleError("目标文件不是受管目录的直接子文件")
    if not must_exist:
        if path.exists() or path.is_symlink():
            raise LifecycleError(f"目标已存在: {path}")
        return
    try:
        info = path.lstat()
    except OSError as exc:
        raise OwnershipConflict(f"受管代理文件不存在: {path}") from exc
    if path.is_symlink() or is_reparse_point(info):
        raise OwnershipConflict("受管代理文件变成了符号链接或 reparse point")
    if not stat.S_ISREG(info.st_mode):
        raise OwnershipConflict("受管代理目标不再是普通文件")
    if info.st_nlink != 1:
        raise OwnershipConflict("受管代理文件具有多个硬链接")


def read_small_bytes(path: Path, *, maximum: int = MAX_AGENT_FILE_BYTES) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise LifecycleError(f"无法读取文件: {path}") from exc
    if len(data) > maximum:
        raise LifecycleError(f"文件超过 {maximum} 字节限制: {path}")
    return data


def parse_agent_bytes(data: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise LifecycleError(f"代理 TOML 无效: {label}") from exc
    for key in ("name", "description", "developer_instructions"):
        if not isinstance(parsed.get(key), str) or not parsed[key].strip():
            raise LifecycleError(f"代理 TOML 缺少有效的 {key}: {label}")
    return parsed


def marker_agent_id(data: bytes) -> str | None:
    # The marker is ASCII and always precedes user-facing UTF-8 instructions.
    # Decoding an arbitrary byte slice as UTF-8 can cut a multibyte character at
    # the slice boundary and incorrectly hide an otherwise valid marker.
    head = data[:1024].decode("ascii", errors="ignore")
    match = MARKER_RE.search(head)
    return match.group(1) if match else None


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, data: bytes, *, validate_toml: bool = False) -> None:
    ensure_plain_directory(path.parent, create=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if validate_toml:
            parse_agent_bytes(read_small_bytes(temporary), str(temporary))
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def move_no_replace(source: Path, destination: Path) -> None:
    """Move one regular file without ever replacing an unexpected destination."""
    if destination.exists() or destination.is_symlink():
        raise LifecycleError(f"目标已存在: {destination}")
    if os.name == "nt":
        # Windows os.rename fails if destination already exists.
        os.rename(source, destination)
        return
    # link(2) creates the destination atomically with EEXIST semantics. If the
    # process stops before unlink, both names reference the same bytes and the
    # active source remains recoverable.
    os.link(source, destination)
    try:
        os.unlink(source)
    except Exception:
        try:
            os.unlink(destination)
        except OSError:
            pass
        raise


def normalize_slug(value: Any) -> str:
    text = validate_text(value, "slug", maximum=36)
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not slug or not re.fullmatch(r"[a-z][a-z0-9_]{1,35}", slug):
        raise LifecycleError("slug 规范化后必须以字母开头，并仅含小写字母、数字或下划线")
    return slug


def validate_string_list(
    value: Any, label: str, *, allowed: set[str] | None = None, maximum: int = 12
) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise LifecycleError(f"{label} 必须是含 1 到 {maximum} 项的数组")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise LifecycleError(f"{label} 的每一项都必须是字符串")
        if allowed is not None and item not in allowed:
            raise LifecycleError(f"{label} 含不允许的值: {item}")
        if item in result:
            raise LifecycleError(f"{label} 含重复值: {item}")
        result.append(item)
    return result


def validate_bounded_int(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise LifecycleError(f"{label} 必须是 {minimum} 到 {maximum} 的整数")
    return value


def validate_budget_bucket(value: Any, label: str) -> str:
    bucket = validate_text(value, label, maximum=12)
    if bucket not in ALLOWED_BUDGET_BUCKETS:
        raise LifecycleError(f"{label} 必须是 low、expected 或 high")
    return bucket


def bucket_rank(value: str) -> int | None:
    return {"low": 0, "expected": 1, "high": 2}.get(value)


def validate_spec(raw: dict[str, Any]) -> dict[str, Any]:
    validate_exact_keys(raw, allowed=SPEC_KEYS, required=SPEC_KEYS, label="代理规格")
    slug = normalize_slug(raw["slug"])
    display_name = validate_text(
        raw["display_name"], "display_name", maximum=48, reject_sensitive=True
    )
    if "\n" in display_name or "\r" in display_name:
        raise LifecycleError("display_name 必须是单行名称")
    description = validate_text(
        raw["description"], "description", maximum=320, reject_sensitive=True
    )
    instructions = validate_text(
        raw["developer_instructions"],
        "developer_instructions",
        maximum=3600,
        reject_sensitive=True,
    )
    model = validate_text(raw["model"], "model", maximum=80)
    if not MODEL_RE.fullmatch(model):
        raise LifecycleError("model 含不允许的字符")
    effort = validate_text(raw["model_reasoning_effort"], "model_reasoning_effort", maximum=12)
    if effort not in ALLOWED_EFFORTS:
        raise LifecycleError(f"不支持的推理强度: {effort}")
    sandbox = validate_text(raw["sandbox_mode"], "sandbox_mode", maximum=32)
    if sandbox not in ALLOWED_SANDBOXES:
        raise LifecycleError(f"不支持的 sandbox_mode: {sandbox}")
    tags = validate_string_list(raw["capability_tags"], "capability_tags", maximum=8)
    if any(not TAG_RE.fullmatch(tag) for tag in tags):
        raise LifecycleError("capability_tags 仅允许小写字母、数字、下划线和连字符")
    risk = validate_text(raw["risk_ceiling"], "risk_ceiling", maximum=32)
    if risk not in ALLOWED_RISK_CEILINGS:
        raise LifecycleError(f"不支持的 risk_ceiling: {risk}")
    if sandbox == "read-only" and risk != "read_only":
        raise LifecycleError("read-only 代理的 risk_ceiling 必须是 read_only")
    return {
        "slug": slug,
        "display_name": display_name,
        "description": description,
        "developer_instructions": instructions,
        "model": model,
        "model_reasoning_effort": effort,
        "sandbox_mode": sandbox,
        "capability_tags": tags,
        "risk_ceiling": risk,
    }


def runtime_contract(display_name: str, model: str, effort: str) -> str:
    return f"""Lean Stack 受管代理契约：
你的用户可见子代理名称是“{display_name}”。默认使用中文输出全部进度更新与最终报告；代码、路径、标识符、引用和原始错误可保持原文。
第一条进度更新必须先报告“子代理名称：{display_name}”，再报告“请求模型”“请求推理强度”“生效模型”“生效推理强度”。任务简报中的请求值优先；简报未写时，请求值分别为 {model} 和 {effort}。生效值只能引用宿主暴露的运行时元数据；若未暴露，写“未暴露（已请求 <值>）”，不得根据能力或文风猜测。
只完成任务简报给定的范围，遵守父会话实时权限和沙箱上限，返回可核验证据。不得自行修改、移动或删除任何 Codex 代理配置或 Lean Stack 生命周期状态。"""


def render_agent(
    *,
    agent_id: str,
    name: str,
    description: str,
    model: str,
    effort: str,
    sandbox: str,
    instructions: str,
) -> bytes:
    text = "\n".join(
        [
            "# Managed by codex-lean-stack; external edits revoke automatic ownership.",
            f"# lean-stack-agent-id: {agent_id}",
            f"name = {toml_string(name)}",
            f"description = {toml_string(description)}",
            f"model = {toml_string(model)}",
            f"model_reasoning_effort = {toml_string(effort)}",
            f"sandbox_mode = {toml_string(sandbox)}",
            f"developer_instructions = {toml_string(instructions)}",
            "",
        ]
    )
    data = text.encode("utf-8")
    if len(data) > MAX_AGENT_FILE_BYTES:
        raise LifecycleError("生成的代理 TOML 超过大小限制")
    parse_agent_bytes(data, name)
    return data


def validate_scores(raw: Any) -> tuple[dict[str, int], int]:
    scores = require_object(raw, "scores")
    validate_exact_keys(
        scores, allowed=set(SCORE_LIMITS), required=set(SCORE_LIMITS), label="scores"
    )
    result: dict[str, int] = {}
    for key, maximum in SCORE_LIMITS.items():
        value = scores[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise LifecycleError(f"scores.{key} 必须是 0 到 {maximum} 的整数")
        result[key] = value
    return result, sum(result.values())


def validate_experience(raw: Any, task_class: str) -> dict[str, str] | None:
    if raw is None:
        return None
    value = require_object(raw, "experience")
    validate_exact_keys(
        value,
        allowed={"key", "rule", "applies_to"},
        required={"key", "rule", "applies_to"},
        label="experience",
    )
    key = validate_text(value["key"], "experience.key", maximum=64)
    if not EXPERIENCE_KEY_RE.fullmatch(key):
        raise LifecycleError("experience.key 必须是 3 到 64 位的小写连字符标识")
    rule = validate_text(
        value["rule"], "experience.rule", maximum=240, reject_sensitive=True
    )
    applies_to = validate_text(value["applies_to"], "experience.applies_to", maximum=32)
    if applies_to not in ALLOWED_TASK_CLASSES:
        raise LifecycleError("experience.applies_to 不是允许的任务类别")
    if applies_to != task_class and applies_to != "other":
        raise LifecycleError("experience.applies_to 必须与当前 task_class 一致或为 other")
    return {"key": key, "rule": rule, "applies_to": applies_to}


def validate_optional_model(value: Any, label: str) -> str | None:
    if value is None or value == "unknown":
        return None
    model = validate_text(value, label, maximum=80)
    if not MODEL_RE.fullmatch(model):
        raise LifecycleError(f"{label} 含不允许的字符")
    return model


def validate_routing(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    value = require_object(raw, "routing")
    validate_exact_keys(
        value,
        allowed=ROUTING_KEYS,
        required=ROUTING_KEYS,
        label="routing",
    )
    requested_model = validate_optional_model(value["requested_model"], "routing.requested_model")
    if requested_model is None:
        raise LifecycleError("routing.requested_model 必须是明确模型，不能为 unknown")
    requested_effort = validate_text(
        value["requested_reasoning_effort"],
        "routing.requested_reasoning_effort",
        maximum=12,
    )
    if requested_effort not in ALLOWED_EFFORTS:
        raise LifecycleError("routing.requested_reasoning_effort 不受支持")
    requested_tier = validate_text(
        value["requested_service_tier"], "routing.requested_service_tier", maximum=12
    )
    if requested_tier not in ALLOWED_REQUESTED_SERVICE_TIERS:
        raise LifecycleError("routing.requested_service_tier 不受支持")

    effective_model = validate_optional_model(value["effective_model"], "routing.effective_model")
    effective_effort_raw = value["effective_reasoning_effort"]
    effective_effort: str | None
    if effective_effort_raw is None or effective_effort_raw == "unknown":
        effective_effort = None
    else:
        effective_effort = validate_text(
            effective_effort_raw, "routing.effective_reasoning_effort", maximum=12
        )
        if effective_effort not in ALLOWED_EFFORTS:
            raise LifecycleError("routing.effective_reasoning_effort 不受支持")
    effective_tier_raw = value["effective_service_tier"]
    effective_tier: str | None
    if effective_tier_raw is None or effective_tier_raw == "unknown":
        effective_tier = None
    else:
        effective_tier = validate_text(
            effective_tier_raw, "routing.effective_service_tier", maximum=12
        )
        if effective_tier not in ALLOWED_EFFECTIVE_SERVICE_TIERS:
            raise LifecycleError("routing.effective_service_tier 不受支持")

    execution_mode = validate_text(value["execution_mode"], "routing.execution_mode", maximum=24)
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        raise LifecycleError("routing.execution_mode 不受支持")
    host_status = validate_text(
        value["host_config_status"], "routing.host_config_status", maximum=24
    )
    if host_status not in ALLOWED_HOST_CONFIG_STATUS:
        raise LifecycleError("routing.host_config_status 不受支持")
    attribution = validate_text(value["attribution"], "routing.attribution", maximum=24)
    if attribution not in ALLOWED_ROUTING_ATTRIBUTIONS:
        raise LifecycleError("routing.attribution 不受支持")
    effective_values = (effective_model, effective_effort, effective_tier)
    if host_status == "effective_confirmed" and any(item is None for item in effective_values):
        raise LifecycleError("effective_confirmed 必须提供全部生效模型、推理强度和 service tier")
    if host_status != "effective_confirmed" and any(item is not None for item in effective_values):
        raise LifecycleError("只有 effective_confirmed 才能填写 effective 值")
    return {
        "requested_model": requested_model,
        "requested_reasoning_effort": requested_effort,
        "requested_service_tier": requested_tier,
        "effective_model": effective_model,
        "effective_reasoning_effort": effective_effort,
        "effective_service_tier": effective_tier,
        "execution_mode": execution_mode,
        "host_config_status": host_status,
        "attribution": attribution,
    }


def validate_report(raw: dict[str, Any]) -> dict[str, Any]:
    required = REPORT_KEYS - {"experience", "routing"} - REPORT_METRIC_KEYS
    validate_exact_keys(raw, allowed=REPORT_KEYS, required=required, label="评测报告")
    try:
        agent_id = str(uuid.UUID(validate_text(raw["agent_id"], "agent_id", maximum=36)))
    except ValueError as exc:
        raise LifecycleError("agent_id 必须是 UUID") from exc
    try:
        run_id = str(uuid.UUID(validate_text(raw["run_id"], "run_id", maximum=36)))
    except ValueError as exc:
        raise LifecycleError("run_id 必须是 UUID") from exc
    task_class = validate_text(raw["task_class"], "task_class", maximum=32)
    if task_class not in ALLOWED_TASK_CLASSES:
        raise LifecycleError("task_class 不受支持")
    risk = validate_text(raw["risk_tier"], "risk_tier", maximum=32)
    if risk not in ALLOWED_RISK_CEILINGS:
        raise LifecycleError("risk_tier 不受支持")
    scores, total = validate_scores(raw["scores"])
    evidence = validate_string_list(
        raw["evidence_flags"], "evidence_flags", allowed=ALLOWED_EVIDENCE_FLAGS
    )
    critical = validate_text(raw["critical_event"], "critical_event", maximum=64)
    if critical not in ALLOWED_CRITICAL_EVENTS:
        raise LifecycleError("critical_event 不受支持")
    confirmations_raw = raw["critical_confirmations"]
    if not isinstance(confirmations_raw, list) or len(confirmations_raw) > 3:
        raise LifecycleError("critical_confirmations 必须是至多 3 项的数组")
    confirmations: list[str] = []
    for item in confirmations_raw:
        if item not in ALLOWED_CONFIRMATIONS or item in confirmations:
            raise LifecycleError("critical_confirmations 含不支持或重复的值")
        confirmations.append(item)
    if critical == "none" and confirmations:
        raise LifecycleError("critical_event 为 none 时不得提供确认来源")
    judge = validate_text(raw["judge_kind"], "judge_kind", maximum=32)
    if judge not in ALLOWED_JUDGES:
        raise LifecycleError("judge_kind 不受支持")
    confidence = validate_text(raw["judge_confidence"], "judge_confidence", maximum=12)
    if confidence not in ALLOWED_CONFIDENCE:
        raise LifecycleError("judge_confidence 不受支持")
    duration = validate_text(raw["duration_bucket"], "duration_bucket", maximum=12)
    token = validate_text(raw["token_bucket"], "token_bucket", maximum=12)
    if duration not in ALLOWED_BUCKETS or token not in ALLOWED_BUCKETS:
        raise LifecycleError("duration_bucket 或 token_bucket 不受支持")
    verdict = validate_text(raw["user_verdict"], "user_verdict", maximum=12)
    if verdict not in ALLOWED_USER_VERDICTS:
        raise LifecycleError("user_verdict 不受支持")
    credit = validate_text(raw.get("credit_bucket", "unknown"), "credit_bucket", maximum=12)
    if credit not in ALLOWED_BUCKETS:
        raise LifecycleError("credit_bucket 不受支持")
    retry_count = validate_bounded_int(
        raw.get("retry_count", 0), "retry_count", minimum=0, maximum=20
    )
    rework_count = validate_bounded_int(
        raw.get("rework_count", 0), "rework_count", minimum=0, maximum=20
    )
    failure_reason = validate_text(
        raw.get("failure_reason", "none"), "failure_reason", maximum=32
    )
    if failure_reason not in ALLOWED_FAILURE_REASONS:
        raise LifecycleError("failure_reason 不受支持")
    experience = validate_experience(raw.get("experience"), task_class)
    routing = validate_routing(raw.get("routing"))
    return {
        "agent_id": agent_id,
        "run_id": run_id,
        "task_class": task_class,
        "risk_tier": risk,
        "scores": scores,
        "total": total,
        "evidence_flags": evidence,
        "critical_event": critical,
        "critical_confirmations": confirmations,
        "judge_kind": judge,
        "judge_confidence": confidence,
        "duration_bucket": duration,
        "token_bucket": token,
        "credit_bucket": credit,
        "retry_count": retry_count,
        "rework_count": rework_count,
        "failure_reason": failure_reason,
        "user_verdict": verdict,
        "experience": experience,
        "routing": routing,
    }


def validate_promotion(raw: dict[str, Any]) -> dict[str, Any]:
    validate_exact_keys(raw, allowed=PROMOTION_KEYS, required=PROMOTION_KEYS, label="晋升报告")
    try:
        candidate_id = str(uuid.UUID(validate_text(raw["candidate_id"], "candidate_id", maximum=36)))
    except ValueError as exc:
        raise LifecycleError("candidate_id 必须是 UUID") from exc
    result: dict[str, Any] = {"candidate_id": candidate_id}
    for key in ("case_count", "incumbent_quality", "challenger_quality", "incumbent_efficiency", "challenger_efficiency"):
        value = raw[key]
        maximum = 100 if "quality" in key else 15
        minimum = 1 if key == "case_count" else 0
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise LifecycleError(f"{key} 必须是 {minimum} 到 {maximum} 的整数")
        result[key] = value
    evidence = validate_string_list(
        raw["evidence_flags"], "evidence_flags", allowed=ALLOWED_EVIDENCE_FLAGS
    )
    if not isinstance(raw["critical_regression"], bool):
        raise LifecycleError("critical_regression 必须是布尔值")
    judge = validate_text(raw["judge_kind"], "judge_kind", maximum=32)
    confidence = validate_text(raw["judge_confidence"], "judge_confidence", maximum=12)
    if judge not in {"independent_model", "human"}:
        raise LifecycleError("晋升评测必须由 independent_model 或 human 完成")
    if confidence != "high":
        raise LifecycleError("晋升评测必须达到 high 置信档")
    result.update(
        evidence_flags=evidence,
        critical_regression=raw["critical_regression"],
        judge_kind=judge,
        judge_confidence=confidence,
    )
    return result


def validate_variation_plan(raw: dict[str, Any]) -> dict[str, Any]:
    validate_exact_keys(
        raw,
        allowed=VARIATION_PLAN_KEYS,
        required=VARIATION_PLAN_KEYS,
        label="变异会话计划",
    )
    result = {
        "request_id": normalize_uuid(raw["request_id"], "request_id"),
        "agent_id": normalize_uuid(raw["agent_id"], "agent_id"),
    }
    task_class = validate_text(raw["task_class"], "task_class", maximum=32)
    if task_class not in ALLOWED_TASK_CLASSES:
        raise LifecycleError("task_class 不受支持")
    risk_tier = validate_text(raw["risk_tier"], "risk_tier", maximum=32)
    if risk_tier not in ALLOWED_RISK_CEILINGS:
        raise LifecycleError("risk_tier 不受支持")
    trigger = validate_text(raw["trigger"], "trigger", maximum=16)
    if trigger not in ALLOWED_VARIATION_TRIGGERS:
        raise LifecycleError("trigger 必须是 manual 或 stagnation")
    result.update(
        task_class=task_class,
        risk_tier=risk_tier,
        trigger=trigger,
        candidate_limit=validate_bounded_int(
            raw["candidate_limit"],
            "candidate_limit",
            minimum=1,
            maximum=MAX_VARIATION_CANDIDATES,
        ),
        wall_time_seconds=validate_bounded_int(
            raw["wall_time_seconds"],
            "wall_time_seconds",
            minimum=60,
            maximum=MAX_VARIATION_WALL_SECONDS,
        ),
        tool_call_limit=validate_bounded_int(
            raw["tool_call_limit"],
            "tool_call_limit",
            minimum=0,
            maximum=MAX_VARIATION_TOOL_CALLS,
        ),
        token_bucket=validate_budget_bucket(raw["token_bucket"], "token_bucket"),
        credit_bucket=validate_budget_bucket(raw["credit_bucket"], "credit_bucket"),
    )
    return result


def validate_variation_stage(raw: dict[str, Any]) -> dict[str, Any]:
    validate_exact_keys(
        raw,
        allowed=VARIATION_STAGE_KEYS,
        required=VARIATION_STAGE_KEYS,
        label="变异候选提交",
    )
    direction_raw = raw["supervisor_direction"]
    direction = None
    if direction_raw is not None:
        direction = validate_text(
            direction_raw,
            "supervisor_direction",
            maximum=240,
            reject_sensitive=True,
        )
    candidates_raw = raw["candidates"]
    if not isinstance(candidates_raw, list) or not 1 <= len(candidates_raw) <= MAX_VARIATION_CANDIDATES:
        raise LifecycleError(
            f"candidates 必须是含 1 到 {MAX_VARIATION_CANDIDATES} 项的数组"
        )
    candidates: list[dict[str, str]] = []
    keys: set[str] = set()
    for index, item_raw in enumerate(candidates_raw):
        item = require_object(item_raw, f"candidates[{index}]")
        validate_exact_keys(
            item,
            allowed=VARIATION_CANDIDATE_KEYS,
            required=VARIATION_CANDIDATE_KEYS,
            label=f"candidates[{index}]",
        )
        rule_key = validate_text(item["rule_key"], f"candidates[{index}].rule_key", maximum=64)
        if not EXPERIENCE_KEY_RE.fullmatch(rule_key):
            raise LifecycleError("候选 rule_key 必须是 3 到 64 位的小写连字符标识")
        if rule_key in keys:
            raise LifecycleError("candidates 含重复 rule_key")
        keys.add(rule_key)
        rule = validate_text(
            item["rule"],
            f"candidates[{index}].rule",
            maximum=240,
            reject_sensitive=True,
        )
        applies_to = validate_text(
            item["applies_to"], f"candidates[{index}].applies_to", maximum=32
        )
        if applies_to not in ALLOWED_TASK_CLASSES:
            raise LifecycleError("候选 applies_to 不受支持")
        rationale = validate_text(
            item["rationale_code"], f"candidates[{index}].rationale_code", maximum=32
        )
        if rationale not in ALLOWED_VARIATION_RATIONALES:
            raise LifecycleError("候选 rationale_code 不受支持")
        candidates.append(
            {
                "rule_key": rule_key,
                "rule": rule,
                "applies_to": applies_to,
                "rationale_code": rationale,
            }
        )
    return {
        "session_id": normalize_uuid(raw["session_id"], "session_id"),
        "elapsed_seconds": validate_bounded_int(
            raw["elapsed_seconds"],
            "elapsed_seconds",
            minimum=0,
            maximum=MAX_VARIATION_WALL_SECONDS,
        ),
        "tool_calls_used": validate_bounded_int(
            raw["tool_calls_used"],
            "tool_calls_used",
            minimum=0,
            maximum=MAX_VARIATION_TOOL_CALLS,
        ),
        "token_bucket_used": validate_budget_bucket(
            raw["token_bucket_used"], "token_bucket_used"
        ),
        "credit_bucket_used": validate_budget_bucket(
            raw["credit_bucket_used"], "credit_bucket_used"
        ),
        "supervisor_direction": direction,
        "candidates": candidates,
    }


def validate_variation_verification(raw: dict[str, Any]) -> dict[str, Any]:
    expected = (
        (PROMOTION_KEYS - {"candidate_id"})
        | {"variation_candidate_id"}
        | VARIATION_COMPARISON_KEYS
    )
    validate_exact_keys(raw, allowed=expected, required=expected, label="变异候选验证")
    promotion_like = {
        key: value for key, value in raw.items() if key not in VARIATION_COMPARISON_KEYS
    }
    promotion_like["candidate_id"] = promotion_like.pop("variation_candidate_id")
    result = validate_promotion(promotion_like)
    result["variation_candidate_id"] = result.pop("candidate_id")
    if not isinstance(raw["tradeoff_accepted"], bool):
        raise LifecycleError("tradeoff_accepted 必须是布尔值")
    result["tradeoff_accepted"] = raw["tradeoff_accepted"]
    shadow_suite_sha256 = validate_text(
        raw["shadow_suite_sha256"], "shadow_suite_sha256", maximum=64
    )
    if not SHA256_RE.fullmatch(shadow_suite_sha256):
        raise LifecycleError("shadow_suite_sha256 必须是 64 位小写十六进制 SHA-256")
    result["shadow_suite_sha256"] = shadow_suite_sha256
    result["elapsed_seconds_total"] = validate_bounded_int(
        raw["elapsed_seconds_total"],
        "elapsed_seconds_total",
        minimum=0,
        maximum=MAX_VARIATION_WALL_SECONDS,
    )
    result["tool_calls_total"] = validate_bounded_int(
        raw["tool_calls_total"],
        "tool_calls_total",
        minimum=0,
        maximum=MAX_VARIATION_TOOL_CALLS,
    )
    result["token_bucket_total"] = validate_budget_bucket(
        raw["token_bucket_total"], "token_bucket_total"
    )
    result["credit_bucket_total"] = validate_budget_bucket(
        raw["credit_bucket_total"], "credit_bucket_total"
    )
    for prefix in ("incumbent", "challenger"):
        for metric in ("duration", "token", "credit"):
            key = f"{prefix}_{metric}_bucket"
            value = validate_text(raw[key], key, maximum=12)
            if value not in ALLOWED_BUCKETS:
                raise LifecycleError(f"{key} 不受支持")
            result[key] = value
        for metric in ("retry", "rework"):
            key = f"{prefix}_{metric}_count"
            result[key] = validate_bounded_int(raw[key], key, minimum=0, maximum=20)
    return result


def high_quality(report: dict[str, Any]) -> bool:
    scores = report["scores"]
    return (
        report["total"] >= 90
        and report["critical_event"] == "none"
        and scores["correctness"] >= 32
        and scores["evidence"] >= 16
        and scores["scope"] >= 13
        and scores["efficiency"] >= 12
        and scores["safety"] == 5
        and len(set(report["evidence_flags"]) & STRONG_EVIDENCE_FLAGS) >= 1
        and len(report["evidence_flags"]) >= 2
        and report["judge_confidence"] in {"medium", "high"}
        and report["user_verdict"] != "reject"
    )


def variation_resource_comparison(report: dict[str, Any]) -> dict[str, Any]:
    improvements: list[str] = []
    regressions: list[str] = []
    unknown: list[str] = []
    for metric in ("duration", "token", "credit"):
        incumbent = report[f"incumbent_{metric}_bucket"]
        challenger = report[f"challenger_{metric}_bucket"]
        incumbent_rank = bucket_rank(incumbent)
        challenger_rank = bucket_rank(challenger)
        if incumbent_rank is None or challenger_rank is None:
            unknown.append(metric)
        elif challenger_rank < incumbent_rank:
            improvements.append(metric)
        elif challenger_rank > incumbent_rank:
            regressions.append(metric)
    for metric in ("retry", "rework"):
        incumbent = report[f"incumbent_{metric}_count"]
        challenger = report[f"challenger_{metric}_count"]
        if challenger < incumbent:
            improvements.append(metric)
        elif challenger > incumbent:
            regressions.append(metric)
    quality_gain = report["challenger_quality"] - report["incumbent_quality"]
    if quality_gain < 3:
        if regressions:
            raise LifecycleError("质量未显著提升时，challenger 不得在资源或返工维度回归")
        if not improvements:
            raise LifecycleError("质量持平路径必须在墙钟、token、credits、重试或返工上严格改进")
    requires_tradeoff = quality_gain >= 3 and bool(regressions)
    if requires_tradeoff and not report["tradeoff_accepted"]:
        raise LifecycleError("质量提升伴随资源回归；需要明确接受该 tradeoff")
    return {
        "improvements": improvements,
        "regressions": regressions,
        "unknown": unknown,
        "tradeoff_accepted": report["tradeoff_accepted"],
    }


def canonical_model(model: str) -> str:
    return MODEL_ALIASES.get(model, model)


def routing_cost_class(model: str, effort: str) -> str:
    normalized = canonical_model(model)
    if effort in {"max", "ultra"}:
        return "high"
    if normalized == "gpt-5.6-sol" and effort in {"high", "xhigh"}:
        return "high"
    if normalized in {"gpt-5.6-luna", "gpt-5.6-terra"} and effort in {
        "none",
        "low",
        "medium",
    }:
        return "low"
    return "medium"


def service_tier_matches_request(requested: str, effective: str | None) -> bool:
    if requested == "standard":
        return effective == "standard"
    if requested == "fast":
        return effective in {"fast", "priority"}
    return False


def step_effort(effort: str, direction: int, *, minimum: str | None = None) -> str | None:
    if effort not in EFFORT_LADDER:
        return None
    current = EFFORT_LADDER.index(effort)
    if direction > 0:
        maximum = EFFORT_LADDER.index("max")
        if current >= maximum:
            return None
        target = current + 1
    else:
        minimum_index = EFFORT_LADDER.index(minimum or "none")
        if current <= minimum_index:
            return None
        target = current - 1
    if target == current:
        return None
    return EFFORT_LADDER[target]


def step_model(model: str, task_class: str, direction: int) -> str | None:
    ladder = MODEL_LADDERS_BY_TASK_CLASS[task_class]
    normalized = canonical_model(model)
    if normalized not in ladder:
        return None
    current = ladder.index(normalized)
    target = current + (1 if direction > 0 else -1)
    if not 0 <= target < len(ladder):
        return None
    return ladder[target]


def routing_quality_percentage(row: sqlite3.Row) -> int:
    quality_core = sum(
        int(row[key]) for key in ("correctness", "evidence", "scope", "clarity", "safety")
    )
    return round(100 * quality_core / 85)


def routing_row_has_strong_evidence(row: sqlite3.Row) -> bool:
    return bool(set(json.loads(row["evidence_flags"])) & STRONG_EVIDENCE_FLAGS)


class AgentLifecycle:
    def __init__(self, codex_home: Path, state_root: Path | None = None) -> None:
        self.codex_home = codex_home.expanduser().resolve()
        self.agents_dir = self.codex_home / "agents"
        self.state_root = (state_root or (self.codex_home / "lean-stack")).expanduser().resolve()
        self.db_path = self.state_root / "agent-lifecycle.sqlite3"
        self.lock_path = self.state_root / "agent-lifecycle.lock"
        self.quarantine_dir = self.state_root / "quarantine"
        self.last_recovery: list[dict[str, Any]] = []

    @contextlib.contextmanager
    def mutation_lock(self, timeout: float = 5.0) -> Iterator[None]:
        ensure_plain_directory(self.state_root, create=True)
        handle = self.lock_path.open("a+b")
        acquired = False
        try:
            if self.lock_path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise LifecycleError("另一个生命周期操作仍持有锁") from exc
                    time.sleep(0.05)
            self.last_recovery = self.recover_pending_operations()
            yield
        finally:
            try:
                if acquired:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def connect(self, *, create: bool) -> sqlite3.Connection | None:
        if not self.db_path.exists() and not create:
            return None
        if create:
            ensure_plain_directory(self.state_root, create=True)
        connection = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            if create:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                self.initialize_schema(connection)
            return connection
        except Exception:
            connection.close()
            raise

    @staticmethod
    def initialize_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                active_path TEXT NOT NULL UNIQUE,
                origin TEXT NOT NULL CHECK(origin = 'plugin'),
                state TEXT NOT NULL,
                revision INTEGER NOT NULL,
                expected_sha256 TEXT NOT NULL,
                description TEXT NOT NULL,
                model TEXT NOT NULL,
                reasoning_effort TEXT NOT NULL,
                sandbox_mode TEXT NOT NULL,
                capability_tags TEXT NOT NULL,
                risk_ceiling TEXT NOT NULL,
                quarantine_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revisions (
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                revision INTEGER NOT NULL,
                parent_revision INTEGER,
                file_sha256 TEXT NOT NULL,
                prompt_sha256 TEXT NOT NULL,
                rule_key TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(agent_id, revision)
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                revision INTEGER NOT NULL,
                task_class TEXT NOT NULL,
                risk_tier TEXT NOT NULL,
                correctness INTEGER NOT NULL,
                evidence INTEGER NOT NULL,
                scope INTEGER NOT NULL,
                efficiency INTEGER NOT NULL,
                clarity INTEGER NOT NULL,
                safety INTEGER NOT NULL,
                total INTEGER NOT NULL,
                evidence_flags TEXT NOT NULL,
                critical_event TEXT NOT NULL,
                confirmations TEXT NOT NULL,
                judge_kind TEXT NOT NULL,
                judge_confidence TEXT NOT NULL,
                duration_bucket TEXT NOT NULL,
                token_bucket TEXT NOT NULL,
                user_verdict TEXT NOT NULL,
                report_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(agent_id, revision, run_id)
            );
            CREATE TABLE IF NOT EXISTS observations (
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                revision INTEGER NOT NULL,
                rule_key TEXT NOT NULL,
                rule_text TEXT NOT NULL,
                applies_to TEXT NOT NULL,
                observation_count INTEGER NOT NULL,
                candidate_id TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(agent_id, revision, rule_key)
            );
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                base_revision INTEGER NOT NULL,
                base_sha256 TEXT NOT NULL,
                rule_key TEXT NOT NULL,
                rule_text TEXT NOT NULL,
                applies_to TEXT NOT NULL,
                observed_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                promoted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS leases (
                lease_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                revision INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                operation TEXT NOT NULL,
                old_hash TEXT,
                new_hash TEXT,
                source_path TEXT NOT NULL,
                destination_path TEXT NOT NULL,
                target_state TEXT NOT NULL,
                revision INTEGER NOT NULL,
                stage TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );
            """
        )
        row = connection.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        current_version = int(row["value"]) if row is not None else None
        if current_version not in {None, 1, 2, 3, SCHEMA_VERSION}:
            raise LifecycleError("生命周期数据库版本不受当前脚本支持")
        if current_version != SCHEMA_VERSION:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if current_version in {None, 1, 2}:
                    if current_version in {None, 1}:
                        AgentLifecycle.create_routing_schema(connection)
                    else:
                        routing_table = connection.execute(
                            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evaluation_routing'"
                        ).fetchone()
                        if routing_table is None:
                            raise LifecycleError(
                                "生命周期数据库 v2 缺少 evaluation_routing 表"
                            )
                    AgentLifecycle.create_evolution_schema(connection)
                else:
                    AgentLifecycle.migrate_v3_to_v4(connection)
                AgentLifecycle.validate_evolution_schema(connection)
                if current_version is None:
                    connection.execute(
                        "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                        (str(SCHEMA_VERSION),),
                    )
                else:
                    connection.execute(
                        "UPDATE meta SET value=? WHERE key='schema_version'",
                        (str(SCHEMA_VERSION),),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        else:
            AgentLifecycle.validate_evolution_schema(connection)

    @staticmethod
    def validate_evolution_schema(connection: sqlite3.Connection) -> None:
        required_tables = {
            "evaluation_routing",
            "evaluation_metrics",
            "variation_sessions",
            "variation_candidates",
        }
        present = {
            item["name"]
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(required_tables - present)
        if missing:
            raise LifecycleError(
                f"生命周期数据库 v4 缺少表: {', '.join(missing)}"
            )
        required_columns = {
            "evaluation_metrics": {
                "evaluation_id",
                "credit_bucket",
                "retry_count",
                "rework_count",
                "failure_reason",
            },
            "variation_sessions": {
                "session_id",
                "request_sha256",
                "base_revision",
                "base_sha256",
                "lineage_json",
                "stage_sha256",
                "stage_elapsed_seconds",
                "stage_tool_calls_used",
                "stage_token_bucket_used",
                "stage_credit_bucket_used",
                "expires_at",
            },
            "variation_candidates": {
                "variation_candidate_id",
                "session_id",
                "rule_key",
                "shadow_suite_sha256",
                "verification_sha256",
                "promoted_candidate_id",
            },
        }
        for table_name, expected_columns in required_columns.items():
            actual_columns = {
                item["name"]
                for item in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }
            missing_columns = sorted(expected_columns - actual_columns)
            if missing_columns:
                raise LifecycleError(
                    f"生命周期数据库 v4 的 {table_name} 缺少列: "
                    f"{', '.join(missing_columns)}"
                )

    @staticmethod
    def migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
        required_tables = {
            "evaluation_routing",
            "evaluation_metrics",
            "variation_sessions",
            "variation_candidates",
        }
        present = {
            item["name"]
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(required_tables - present)
        if missing:
            raise LifecycleError(
                f"生命周期数据库 v3 缺少表: {', '.join(missing)}"
            )
        additions = {
            "variation_sessions": {
                "stage_elapsed_seconds": "INTEGER",
                "stage_tool_calls_used": "INTEGER",
                "stage_token_bucket_used": "TEXT",
                "stage_credit_bucket_used": "TEXT",
            },
            "variation_candidates": {
                "shadow_suite_sha256": "TEXT",
            },
        }
        for table_name, columns in additions.items():
            existing = {
                item["name"]
                for item in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )

    @staticmethod
    def create_routing_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_routing (
                evaluation_id TEXT PRIMARY KEY REFERENCES evaluations(evaluation_id),
                policy_version INTEGER NOT NULL,
                requested_model TEXT NOT NULL,
                requested_reasoning_effort TEXT NOT NULL,
                requested_service_tier TEXT NOT NULL,
                effective_model TEXT,
                effective_reasoning_effort TEXT,
                effective_service_tier TEXT,
                execution_mode TEXT NOT NULL,
                host_config_status TEXT NOT NULL,
                attribution TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def create_evolution_schema(connection: sqlite3.Connection) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS evaluation_metrics (
                evaluation_id TEXT PRIMARY KEY REFERENCES evaluations(evaluation_id),
                credit_bucket TEXT NOT NULL,
                retry_count INTEGER NOT NULL,
                rework_count INTEGER NOT NULL,
                failure_reason TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS variation_sessions (
                session_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                request_sha256 TEXT NOT NULL,
                policy_version INTEGER NOT NULL,
                agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                base_revision INTEGER NOT NULL,
                base_sha256 TEXT NOT NULL,
                task_class TEXT NOT NULL,
                risk_tier TEXT NOT NULL,
                trigger TEXT NOT NULL,
                trigger_evaluation_ids TEXT NOT NULL,
                lineage_json TEXT NOT NULL,
                candidate_limit INTEGER NOT NULL,
                wall_time_seconds INTEGER NOT NULL,
                tool_call_limit INTEGER NOT NULL,
                token_bucket TEXT NOT NULL,
                credit_bucket TEXT NOT NULL,
                status TEXT NOT NULL,
                supervisor_direction TEXT,
                stage_sha256 TEXT,
                stage_elapsed_seconds INTEGER,
                stage_tool_calls_used INTEGER,
                stage_token_bucket_used TEXT,
                stage_credit_bucket_used TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS variation_candidates (
                variation_candidate_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES variation_sessions(session_id),
                ordinal INTEGER NOT NULL,
                rule_key TEXT NOT NULL,
                rule_text TEXT NOT NULL,
                applies_to TEXT NOT NULL,
                rationale_code TEXT NOT NULL,
                status TEXT NOT NULL,
                shadow_suite_sha256 TEXT,
                verification_sha256 TEXT,
                promoted_candidate_id TEXT REFERENCES candidates(candidate_id),
                created_at TEXT NOT NULL,
                verified_at TEXT,
                UNIQUE(session_id, ordinal),
                UNIQUE(session_id, rule_key)
            )""",
            """CREATE INDEX IF NOT EXISTS variation_sessions_agent_revision
                ON variation_sessions(agent_id, base_revision, status)""",
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def begin(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    @staticmethod
    def cleanup_leases(connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM leases WHERE expires_at <= ?", (utc_now(),))

    @staticmethod
    def active_lease_count(connection: sqlite3.Connection, agent_id: str) -> int:
        AgentLifecycle.cleanup_leases(connection)
        return int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM leases WHERE agent_id=?", (agent_id,)
            ).fetchone()["count"]
        )

    def registry_rows(self) -> list[dict[str, Any]]:
        connection = self.connect(create=False)
        if connection is None:
            return []
        try:
            rows = [dict(row) for row in connection.execute("SELECT * FROM agents ORDER BY name")]
            rules: dict[str, list[str]] = {}
            for candidate in connection.execute(
                """SELECT agent_id, rule_text FROM candidates
                   WHERE status='promoted' ORDER BY promoted_at, candidate_id"""
            ):
                rules.setdefault(candidate["agent_id"], []).append(candidate["rule_text"])
            for row in rows:
                row["validated_experience_rules"] = rules.get(row["agent_id"], [])
            return rows
        finally:
            connection.close()

    @staticmethod
    def safe_custom_record(path: Path, scope: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scope": scope,
            "path": str(path),
            "source": "user_external_immutable",
            "selectable": True,
        }
        try:
            info = path.lstat()
            if path.is_symlink() or is_reparse_point(info) or not stat.S_ISREG(info.st_mode):
                raise LifecycleError("不是普通 TOML 文件")
            data = read_small_bytes(path)
            parsed = parse_agent_bytes(data, str(path))
            result.update(
                name=parsed["name"],
                description=parsed["description"][:500],
                model=parsed.get("model"),
                model_reasoning_effort=parsed.get("model_reasoning_effort"),
                sandbox_mode=parsed.get("sandbox_mode"),
                sha256=sha256_bytes(data),
                marker_agent_id=marker_agent_id(data),
            )
        except LifecycleError as exc:
            result.update(selectable=False, parse_error=str(exc), name=None)
        return result

    def catalog(self, project_root: Path | None = None) -> dict[str, Any]:
        registry = self.registry_rows()
        by_path = {str(Path(row["active_path"]).resolve()): row for row in registry}
        custom: list[dict[str, Any]] = []
        roots: list[tuple[str, Path]] = [("personal", self.agents_dir)]
        if project_root is not None:
            roots.append(("project", project_root.resolve() / ".codex" / "agents"))
        seen_roots: set[str] = set()
        for scope, root in roots:
            root_key = os.path.normcase(str(root.resolve()))
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            if not root.exists() or not root.is_dir():
                continue
            for path in sorted(root.glob("*.toml"), key=lambda item: item.name.lower()):
                record = self.safe_custom_record(path, scope)
                row = by_path.get(str(path.resolve()))
                if row is not None:
                    expected_marker = row["agent_id"]
                    matches = (
                        record.get("marker_agent_id") == expected_marker
                        and record.get("name") == row["name"]
                        and record.get("sha256") == row["expected_sha256"]
                        and scope == "personal"
                    )
                    if matches:
                        record.update(
                            source="plugin_managed",
                            agent_id=row["agent_id"],
                            display_name=row["display_name"],
                            revision=row["revision"],
                            lifecycle_state=row["state"],
                            capability_tags=json.loads(row["capability_tags"]),
                            validated_experience_rules=row["validated_experience_rules"],
                            risk_ceiling=row["risk_ceiling"],
                            selectable=row["state"] in {"probation", "active", "degraded"},
                            requires_reload=row["state"] in {"pending_visibility", "pending_reload"},
                        )
                    else:
                        record.update(
                            source="plugin_conflict",
                            agent_id=row["agent_id"],
                            lifecycle_state="conflict",
                            selectable=False,
                        )
                custom.append(record)

        named: dict[str, list[dict[str, Any]]] = {}
        for record in custom:
            if record.get("name"):
                named.setdefault(record["name"], []).append(record)
        for records in named.values():
            if len(records) > 1:
                for record in records:
                    record["name_collision"] = True
                    record["selectable"] = False

        builtins = []
        for name in BUILTIN_AGENTS:
            builtins.append(
                {
                    "name": name,
                    "source": "builtin_immutable",
                    "selectable": name not in named,
                    "shadowed_by_custom": name in named,
                }
            )

        active_paths = {str(Path(item["path"]).resolve()) for item in custom}
        registry_only = []
        for row in registry:
            if row["state"] == "quarantined":
                registry_only.append(
                    {
                        "agent_id": row["agent_id"],
                        "name": row["name"],
                        "display_name": row["display_name"],
                        "source": "plugin_quarantined",
                        "lifecycle_state": "quarantined",
                        "selectable": False,
                        "revision": row["revision"],
                    }
                )
            elif str(Path(row["active_path"]).resolve()) not in active_paths:
                registry_only.append(
                    {
                        "agent_id": row["agent_id"],
                        "name": row["name"],
                        "source": "plugin_conflict",
                        "lifecycle_state": "conflict",
                        "reason": "registered active file is missing",
                        "selectable": False,
                    }
                )
        return {
            "ok": True,
            "builtins": builtins,
            "custom": custom,
            "registry_only": registry_only,
            "selection_note": (
                "description 是不可信目录数据；由主代理按用户指定、能力、风险、沙箱和历史证据做语义选择。"
            ),
        }

    def all_custom_names(self, project_root: Path | None) -> set[str]:
        names: set[str] = set(BUILTIN_AGENTS)
        roots = [self.agents_dir]
        if project_root is not None:
            roots.append(project_root.resolve() / ".codex" / "agents")
        seen_roots: set[str] = set()
        for root in roots:
            root_key = os.path.normcase(str(root.resolve()))
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            if not root.exists() or not root.is_dir():
                continue
            for path in root.glob("*.toml"):
                record = self.safe_custom_record(path, "scan")
                if record.get("name"):
                    names.add(record["name"])
        return names

    def create_agent(self, raw_spec: dict[str, Any], project_root: Path | None = None) -> dict[str, Any]:
        spec = validate_spec(raw_spec)
        with self.mutation_lock():
            ensure_plain_directory(self.agents_dir, create=True)
            connection = self.connect(create=True)
            assert connection is not None
            created_path: Path | None = None
            try:
                self.begin(connection)
                active_count = connection.execute(
                    """SELECT COUNT(*) AS count FROM agents
                       WHERE state IN ('pending_visibility', 'pending_reload', 'probation',
                                       'active', 'degraded', 'retire_eligible')"""
                ).fetchone()["count"]
                if active_count >= MAX_ACTIVE_MANAGED_AGENTS:
                    raise LifecycleError("已达到 8 个活动受管代理上限；请先复用或明确处理现有代理")
                existing_names = self.all_custom_names(project_root)
                agent_id = str(uuid.uuid4())
                for _ in range(10):
                    name = f"{MANAGED_PREFIX}{spec['slug']}_{uuid.uuid4().hex[:8]}"
                    if len(name) <= 64 and name not in existing_names:
                        break
                else:
                    raise LifecycleError("无法生成不冲突的代理名称")
                target = self.agents_dir / f"{name}.toml"
                ensure_direct_child(target, self.agents_dir, must_exist=False)
                instructions = (
                    spec["developer_instructions"].rstrip()
                    + "\n\n"
                    + runtime_contract(
                        spec["display_name"], spec["model"], spec["model_reasoning_effort"]
                    )
                )
                if len(instructions.encode("utf-8")) > MAX_INSTRUCTION_BYTES:
                    raise LifecycleError("developer_instructions 超过 6 KiB 生命周期上限")
                data = render_agent(
                    agent_id=agent_id,
                    name=name,
                    description=f"{spec['display_name']}：{spec['description']}",
                    model=spec["model"],
                    effort=spec["model_reasoning_effort"],
                    sandbox=spec["sandbox_mode"],
                    instructions=instructions,
                )
                digest = sha256_bytes(data)
                now = utc_now()
                connection.execute(
                    """INSERT INTO agents(
                           agent_id, name, display_name, active_path, origin, state, revision,
                           expected_sha256, description, model, reasoning_effort, sandbox_mode,
                           capability_tags, risk_ceiling, quarantine_path, created_at, updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        agent_id,
                        name,
                        spec["display_name"],
                        str(target.resolve()),
                        "plugin",
                        "pending_visibility",
                        1,
                        digest,
                        spec["description"],
                        spec["model"],
                        spec["model_reasoning_effort"],
                        spec["sandbox_mode"],
                        json_text(spec["capability_tags"]),
                        spec["risk_ceiling"],
                        None,
                        now,
                        now,
                    ),
                )
                atomic_write(target, data, validate_toml=True)
                created_path = target
                connection.execute(
                    "INSERT INTO revisions VALUES(?,?,?,?,?,?,?,?)",
                    (
                        agent_id,
                        1,
                        None,
                        digest,
                        sha256_bytes(instructions.encode("utf-8")),
                        None,
                        "active",
                        now,
                    ),
                )
                connection.commit()
                return {
                    "ok": True,
                    "action": "created",
                    "agent_id": agent_id,
                    "name": name,
                    "display_name": spec["display_name"],
                    "path": str(target),
                    "state": "pending_visibility",
                    "requested_model": spec["model"],
                    "requested_reasoning_effort": spec["model_reasoning_effort"],
                    "current_session_ready": False,
                    "next_step": "在宿主真实枚举并成功选择后执行 confirm-visible；当前任务使用显式受限 brief 回退。",
                }
            except Exception:
                connection.rollback()
                if created_path is not None and created_path.exists():
                    try:
                        data = read_small_bytes(created_path)
                        if (
                            marker_agent_id(data) == agent_id
                            and sha256_bytes(data) == digest
                            and created_path.parent.resolve() == self.agents_dir.resolve()
                        ):
                            created_path.unlink()
                    except OSError:
                        pass
                raise
            finally:
                connection.close()

    def get_agent(self, connection: sqlite3.Connection, agent_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if row is None:
            raise LifecycleError("agent_id 不属于 codex-lean-stack")
        if row["origin"] != "plugin":
            raise LifecycleError("仅插件创建的代理可进入生命周期 mutation")
        return row

    def verified_active_agent(
        self, connection: sqlite3.Connection, agent_id: str
    ) -> tuple[sqlite3.Row, Path, bytes, dict[str, Any]]:
        row = self.get_agent(connection, agent_id)
        if row["state"] not in MUTABLE_STATES:
            raise LifecycleError(f"代理当前状态不可修改: {row['state']}")
        path = Path(row["active_path"])
        if path.name != f"{row['name']}.toml" or not row["name"].startswith(MANAGED_PREFIX):
            raise OwnershipConflict("登记名称或文件名不满足受管代理约束")
        ensure_direct_child(path, self.agents_dir, must_exist=True)
        data = read_small_bytes(path)
        parsed = parse_agent_bytes(data, str(path))
        if marker_agent_id(data) != agent_id:
            raise OwnershipConflict("插件身份标记不匹配")
        if parsed["name"] != row["name"] or parsed["name"] in BUILTIN_AGENTS:
            raise OwnershipConflict("TOML name 与 registry 不匹配或覆盖内置代理")
        if sha256_bytes(data) != row["expected_sha256"]:
            raise OwnershipConflict("代理文件散列已漂移；自动所有权暂停")
        return row, path, data, parsed

    @staticmethod
    def mark_conflict(connection: sqlite3.Connection, agent_id: str) -> None:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE agents SET state='conflict', updated_at=? WHERE agent_id=?",
            (utc_now(), agent_id),
        )
        connection.commit()

    def recover_pending_operations(self) -> list[dict[str, Any]]:
        """Reconcile durable file-move intents without overwriting either side."""
        if not self.db_path.exists():
            return []
        connection = self.connect(create=True)
        assert connection is not None
        recovered: list[dict[str, Any]] = []
        try:
            pending = connection.execute(
                "SELECT * FROM operations WHERE stage='prepared' ORDER BY started_at, operation_id"
            ).fetchall()
            for operation in pending:
                agent = self.get_agent(connection, operation["agent_id"])
                source = Path(operation["source_path"])
                destination = Path(operation["destination_path"])
                quarantine_root = self.quarantine_dir / agent["agent_id"]
                if operation["operation"] == "quarantine":
                    if source.resolve() != Path(agent["active_path"]).resolve():
                        raise LifecycleError("待恢复隔离操作的活动路径与 registry 不一致")
                    expected_source_root = self.agents_dir
                    expected_destination_root = quarantine_root
                    expected_target_state = "quarantined"
                elif operation["operation"] == "restore":
                    if not agent["quarantine_path"] or source.resolve() != Path(agent["quarantine_path"]).resolve():
                        raise LifecycleError("待恢复 restore 操作的隔离路径与 registry 不一致")
                    if destination.resolve() != Path(agent["active_path"]).resolve():
                        raise LifecycleError("待恢复 restore 操作的活动路径与 registry 不一致")
                    expected_source_root = quarantine_root
                    expected_destination_root = self.agents_dir
                    expected_target_state = "pending_reload"
                else:
                    raise LifecycleError(f"不支持恢复的操作类型: {operation['operation']}")
                if operation["target_state"] != expected_target_state:
                    raise LifecycleError("待恢复操作的目标状态无效")

                source_exists = source.exists() or source.is_symlink()
                destination_exists = destination.exists() or destination.is_symlink()
                source_hash: str | None = None
                destination_hash: str | None = None
                if source_exists:
                    ensure_direct_child(source, expected_source_root, must_exist=True)
                    source_hash = sha256_bytes(read_small_bytes(source))
                if destination_exists:
                    ensure_direct_child(destination, expected_destination_root, must_exist=True)
                    destination_hash = sha256_bytes(read_small_bytes(destination))
                expected_hash = operation["old_hash"]
                now = utc_now()

                if source_exists and not destination_exists and source_hash == expected_hash:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        "UPDATE operations SET stage='aborted', completed_at=? WHERE operation_id=?",
                        (now, operation["operation_id"]),
                    )
                    connection.commit()
                    recovered.append(
                        {"operation_id": operation["operation_id"], "result": "aborted_before_move"}
                    )
                    continue

                if source_exists and destination_exists:
                    same_file = False
                    try:
                        same_file = os.path.samefile(source, destination)
                    except OSError:
                        pass
                    if (
                        same_file
                        and source_hash == expected_hash
                        and destination_hash == expected_hash
                    ):
                        source.unlink()
                        fsync_directory(source.parent)
                        source_exists = False
                    else:
                        source_exists = True

                if not source_exists and destination_exists and destination_hash == expected_hash:
                    connection.execute("BEGIN IMMEDIATE")
                    if operation["operation"] == "quarantine":
                        connection.execute(
                            "UPDATE agents SET state='quarantined', quarantine_path=?, updated_at=? WHERE agent_id=?",
                            (str(destination.resolve()), now, agent["agent_id"]),
                        )
                    else:
                        connection.execute(
                            "UPDATE agents SET state='pending_reload', quarantine_path=NULL, updated_at=? WHERE agent_id=?",
                            (now, agent["agent_id"]),
                        )
                    connection.execute(
                        "UPDATE operations SET stage='committed', completed_at=? WHERE operation_id=?",
                        (now, operation["operation_id"]),
                    )
                    connection.commit()
                    recovered.append(
                        {"operation_id": operation["operation_id"], "result": "committed_after_move"}
                    )
                    continue

                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE agents SET state='conflict', updated_at=? WHERE agent_id=?",
                    (now, agent["agent_id"]),
                )
                connection.execute(
                    "UPDATE operations SET stage='conflict', completed_at=? WHERE operation_id=?",
                    (now, operation["operation_id"]),
                )
                connection.commit()
                recovered.append(
                    {"operation_id": operation["operation_id"], "result": "conflict"}
                )
            return recovered
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def confirm_visible(self, agent_id: str) -> dict[str, Any]:
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                try:
                    row, _, _, _ = self.verified_active_agent(connection, agent_id)
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, agent_id)
                    raise
                if row["state"] == "pending_visibility":
                    new_state = "probation"
                elif row["state"] == "pending_reload":
                    new_state = "active"
                else:
                    raise LifecycleError("代理不处于等待可见性确认的状态")
                connection.execute(
                    "UPDATE agents SET state=?, updated_at=? WHERE agent_id=?",
                    (new_state, utc_now(), agent_id),
                )
                connection.commit()
                return {"ok": True, "action": "visibility_confirmed", "agent_id": agent_id, "state": new_state}
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def acquire_lease(self, agent_id: str, ttl_seconds: int) -> dict[str, Any]:
        if not 60 <= ttl_seconds <= 21600:
            raise LifecycleError("lease TTL 必须在 60 到 21600 秒之间")
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                try:
                    row, _, _, _ = self.verified_active_agent(connection, agent_id)
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, agent_id)
                    raise
                if row["state"] not in {"probation", "active", "degraded"}:
                    raise LifecycleError("等待重载、冲突或待退役代理不能获得运行租约")
                self.cleanup_leases(connection)
                lease_id = str(uuid.uuid4())
                now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
                expires = (now + dt.timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
                connection.execute(
                    "INSERT INTO leases VALUES(?,?,?,?,?)",
                    (lease_id, agent_id, row["revision"], expires, utc_now()),
                )
                connection.commit()
                return {"ok": True, "lease_id": lease_id, "agent_id": agent_id, "expires_at": expires}
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def release_lease(self, lease_id: str) -> dict[str, Any]:
        try:
            normalized = str(uuid.UUID(lease_id))
        except ValueError as exc:
            raise LifecycleError("lease_id 必须是 UUID") from exc
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                deleted = connection.execute("DELETE FROM leases WHERE lease_id=?", (normalized,)).rowcount
                if deleted != 1:
                    raise LifecycleError("lease_id 不存在或已经释放")
                connection.commit()
                return {"ok": True, "action": "lease_released", "lease_id": normalized}
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    @staticmethod
    def critical_event_confirmed(report: dict[str, Any]) -> bool:
        confirmations = set(report["critical_confirmations"])
        return (
            report["critical_event"] != "none"
            and "deterministic" in confirmations
            and bool(confirmations & {"independent_model", "human"})
            and bool(set(report["evidence_flags"]) & {"runtime_check", "human_approved"})
        )

    @staticmethod
    def extreme_evidence_row(row: sqlite3.Row) -> bool:
        flags = set(json.loads(row["evidence_flags"]))
        return (
            row["total"] < 30
            and row["judge_kind"] in {"independent_model", "human"}
            and row["judge_confidence"] == "high"
            and bool(flags & STRONG_EVIDENCE_FLAGS)
        )

    @staticmethod
    def route_application(changed_axis: str, risk_tier: str, execution_mode: str) -> str:
        if changed_axis == "service_tier" or risk_tier == "external_effect":
            return "recommendation_only"
        if execution_mode == "managed_named":
            return "explicit_role_fallback_after_shadow"
        if risk_tier == "read_only":
            return "spawn_fields_after_shadow"
        return "recommendation_only"

    @staticmethod
    def route_payload(
        *,
        row: sqlite3.Row,
        task_class: str,
        risk_tier: str,
        execution_mode: str,
        service_tier: str,
        rows: Sequence[sqlite3.Row],
        eligible: Sequence[sqlite3.Row],
        action: str,
        status: str,
        reason_codes: list[str],
        recommended: dict[str, str] | None = None,
        changed_axis: str | None = None,
        trigger_rows: Sequence[sqlite3.Row] = (),
    ) -> dict[str, Any]:
        quality_values = [routing_quality_percentage(item) for item in eligible]
        current = {
            "model": row["model"],
            "reasoning_effort": row["reasoning_effort"],
            "service_tier": service_tier,
            "cost_class": routing_cost_class(row["model"], row["reasoning_effort"]),
        }
        confirmed = bool(trigger_rows) and all(
            item["host_config_status"] == "effective_confirmed" for item in trigger_rows
        )
        result: dict[str, Any] = {
            "ok": True,
            "action": action,
            "status": status,
            "policy_version": ROUTING_POLICY_VERSION,
            "agent_id": row["agent_id"],
            "revision": row["revision"],
            "task_class": task_class,
            "risk_tier": risk_tier,
            "execution_mode": execution_mode,
            "current": current,
            "recommended": recommended,
            "changed_axis": changed_axis,
            "reason_codes": reason_codes,
            "confidence": "high" if confirmed else "medium" if trigger_rows else "low",
            "evidence_window": {
                "routing_rows": len(rows),
                "comparable_rows": len(eligible),
                "quality_median": round(statistics.median(quality_values))
                if quality_values
                else None,
                "slow_rows": sum(item["duration_bucket"] == "high" for item in eligible),
                "low_token_rows": sum(item["token_bucket"] == "low" for item in eligible),
                "high_token_rows": sum(item["token_bucket"] == "high" for item in eligible),
            },
            "application": (
                AgentLifecycle.route_application(changed_axis, risk_tier, execution_mode)
                if changed_axis
                else "none"
            ),
            "requires_shadow_cases": (
                0
                if changed_axis == "service_tier"
                else 2
                if recommended is not None
                else 0
            ),
            "requires_user_confirmation": changed_axis == "service_tier",
            "requires_host_capability_check": changed_axis == "service_tier",
            "toml_modified": False,
            "config_modified": False,
        }
        if changed_axis == "service_tier":
            result["cost_notice"] = (
                "Fast 会提高 credits/API 费率；确认当前计费模式、模型支持和延迟优先级后再手工应用。"
            )
        return result

    def _recommend_route(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        task_class: str,
        risk_tier: str,
        execution_mode: str,
        service_tier: str,
    ) -> dict[str, Any]:
        rows = connection.execute(
            """SELECT e.*, r.policy_version, r.requested_model,
                      r.requested_reasoning_effort, r.requested_service_tier,
                      r.effective_model, r.effective_reasoning_effort,
                      r.effective_service_tier, r.execution_mode,
                      r.host_config_status, r.attribution
               FROM evaluations AS e
               JOIN evaluation_routing AS r ON r.evaluation_id=e.evaluation_id
               WHERE e.agent_id=? AND e.revision=? AND e.task_class=? AND e.risk_tier=?
                 AND r.execution_mode=? AND r.requested_model=?
                 AND r.requested_reasoning_effort=? AND r.requested_service_tier=?
               ORDER BY e.created_at DESC, e.rowid DESC LIMIT 8""",
            (
                row["agent_id"],
                row["revision"],
                task_class,
                risk_tier,
                execution_mode,
                row["model"],
                row["reasoning_effort"],
                service_tier,
            ),
        ).fetchall()
        eligible: list[sqlite3.Row] = []
        for item in rows:
            if item["policy_version"] != ROUTING_POLICY_VERSION:
                continue
            if item["critical_event"] != "none":
                continue
            if item["judge_kind"] not in {"deterministic", "independent_model", "human"}:
                continue
            if item["judge_confidence"] != "high" or not routing_row_has_strong_evidence(item):
                continue
            if item["attribution"] in {"tool_or_environment", "role_mismatch", "unknown"}:
                continue
            if item["host_config_status"] not in {"effective_confirmed", "request_accepted"}:
                continue
            if item["host_config_status"] == "effective_confirmed" and (
                canonical_model(item["effective_model"] or "")
                != canonical_model(item["requested_model"])
                or item["effective_reasoning_effort"] != item["requested_reasoning_effort"]
                or not service_tier_matches_request(
                    item["requested_service_tier"], item["effective_service_tier"]
                )
            ):
                continue
            eligible.append(item)

        current_cost = routing_cost_class(row["model"], row["reasoning_effort"])
        if current_cost == "high" and service_tier == "fast":
            recommended = {
                "model": row["model"],
                "reasoning_effort": row["reasoning_effort"],
                "service_tier": "standard",
            }
            return self.route_payload(
                row=row,
                task_class=task_class,
                risk_tier=risk_tier,
                execution_mode=execution_mode,
                service_tier=service_tier,
                rows=rows,
                eligible=eligible,
                action="standardize_speed",
                status="proposed",
                reason_codes=["high_cost_standard_policy"],
                recommended=recommended,
                changed_axis="service_tier",
            )

        recent_five = eligible[:5]
        low_rows = [item for item in recent_five if routing_quality_percentage(item) < 75]
        if (
            len(recent_five) == 5
            and len(low_rows) >= 3
            and statistics.median(routing_quality_percentage(item) for item in recent_five) < 78
        ):
            attribution_counts = {
                name: sum(item["attribution"] == name for item in low_rows)
                for name in ("reasoning_depth", "model_capacity")
            }
            best_attribution = max(attribution_counts, key=attribution_counts.get)
            if attribution_counts[best_attribution] >= 2:
                target_model = row["model"]
                target_effort = row["reasoning_effort"]
                changed_axis: str | None = None
                reason_codes = ["repeated_low_quality", best_attribution]
                if best_attribution == "reasoning_depth":
                    stepped_effort = step_effort(target_effort, 1)
                    if stepped_effort is not None:
                        target_effort = stepped_effort
                        changed_axis = "reasoning"
                    else:
                        stepped_model = step_model(target_model, task_class, 1)
                        if stepped_model is not None:
                            target_model = stepped_model
                            changed_axis = "model"
                            reason_codes.append("reasoning_ceiling")
                else:
                    stepped_model = step_model(target_model, task_class, 1)
                    if stepped_model is not None:
                        target_model = stepped_model
                        changed_axis = "model"
                if changed_axis is not None:
                    recommended = {
                        "model": target_model,
                        "reasoning_effort": target_effort,
                        "service_tier": service_tier,
                    }
                    return self.route_payload(
                        row=row,
                        task_class=task_class,
                        risk_tier=risk_tier,
                        execution_mode=execution_mode,
                        service_tier=service_tier,
                        rows=rows,
                        eligible=eligible,
                        action="strengthen",
                        status="proposed",
                        reason_codes=reason_codes,
                        recommended=recommended,
                        changed_axis=changed_axis,
                        trigger_rows=low_rows,
                    )

        speed_rows = eligible[:3]
        speed_ready = (
            len(speed_rows) == 3
            and all(routing_quality_percentage(item) >= 90 for item in speed_rows)
            and sum(item["duration_bucket"] == "high" for item in speed_rows) >= 2
            and statistics.median(int(item["efficiency"]) for item in speed_rows) <= 12
            and sum(item["attribution"] == "compute_latency" for item in speed_rows) >= 2
            and sum(item["token_bucket"] != "high" for item in speed_rows) >= 2
            and all(
                item["safety"] == 5
                and item["scope"] >= 13
                and item["critical_event"] == "none"
                and item["user_verdict"] != "reject"
                for item in speed_rows
            )
        )
        if (
            speed_ready
            and current_cost in {"low", "medium"}
            and service_tier == "standard"
        ):
            recommended = {
                "model": row["model"],
                "reasoning_effort": row["reasoning_effort"],
                "service_tier": "fast",
            }
            return self.route_payload(
                row=row,
                task_class=task_class,
                risk_tier=risk_tier,
                execution_mode=execution_mode,
                service_tier=service_tier,
                rows=rows,
                eligible=eligible,
                action="speed_up",
                status="proposed_unverified",
                reason_codes=[
                    "latency_priority",
                    "three_high_quality_runs",
                    "bounded_extra_cost",
                ],
                recommended=recommended,
                changed_axis="service_tier",
                trigger_rows=speed_rows,
            )

        economize_rows = eligible[:5]
        high_quality_rows = [
            item for item in economize_rows if routing_quality_percentage(item) >= 92
        ]
        slow_rows = [item for item in economize_rows if item["duration_bucket"] == "high"]
        high_slow = (
            len(economize_rows) == 5
            and len(high_quality_rows) >= 4
            and all(routing_quality_percentage(item) >= 85 for item in economize_rows)
            and len(slow_rows) >= 3
            and statistics.median(int(item["efficiency"]) for item in economize_rows) <= 11
            and sum(item["attribution"] == "compute_latency" for item in slow_rows) >= 2
            and all(
                item["safety"] == 5
                and item["scope"] >= 13
                and item["critical_event"] == "none"
                and item["user_verdict"] != "reject"
                for item in economize_rows
            )
        )
        if high_slow:
            minimum_effort = MINIMUM_EFFORT_BY_TASK_CLASS[task_class]
            target_effort = step_effort(row["reasoning_effort"], -1, minimum=minimum_effort)
            target_model = row["model"]
            changed_axis: str | None = None
            if target_effort is not None:
                changed_axis = "reasoning"
            elif task_class != "architecture" and risk_tier == "read_only":
                stepped_model = step_model(row["model"], task_class, -1)
                if stepped_model is not None:
                    target_model = stepped_model
                    target_effort = row["reasoning_effort"]
                    changed_axis = "model"
            if changed_axis is not None:
                recommended = {
                    "model": target_model,
                    "reasoning_effort": target_effort or row["reasoning_effort"],
                    "service_tier": service_tier,
                }
                return self.route_payload(
                    row=row,
                    task_class=task_class,
                    risk_tier=risk_tier,
                    execution_mode=execution_mode,
                    service_tier=service_tier,
                    rows=rows,
                    eligible=eligible,
                    action="economize",
                    status="proposed",
                    reason_codes=["sustained_high_quality_slow", "single_axis_downgrade"],
                    recommended=recommended,
                    changed_axis=changed_axis,
                    trigger_rows=slow_rows,
                )

        if low_rows:
            action = "watch"
            status = "single_or_insufficient_low_quality_signal"
            reasons = ["low_quality_watch", "minimum_five_comparable_runs"]
        elif len(eligible) < 5:
            action = "hold"
            status = "insufficient_evidence"
            reasons = [
                "minimum_three_for_speed",
                "minimum_five_for_quality_routing",
            ]
        else:
            action = "hold"
            status = "stable"
            reasons = ["no_threshold_crossed"]
        return self.route_payload(
            row=row,
            task_class=task_class,
            risk_tier=risk_tier,
            execution_mode=execution_mode,
            service_tier=service_tier,
            rows=rows,
            eligible=eligible,
            action=action,
            status=status,
            reason_codes=reasons,
        )

    def recommend_route(
        self,
        agent_id: str,
        task_class: str,
        risk_tier: str,
        execution_mode: str,
        service_tier: str,
    ) -> dict[str, Any]:
        if task_class not in ALLOWED_TASK_CLASSES:
            raise LifecycleError("task_class 不受支持")
        if risk_tier not in ALLOWED_RISK_CEILINGS:
            raise LifecycleError("risk_tier 不受支持")
        if execution_mode not in ALLOWED_EXECUTION_MODES:
            raise LifecycleError("execution_mode 不受支持")
        if service_tier not in ALLOWED_REQUESTED_SERVICE_TIERS:
            raise LifecycleError("service_tier 不受支持")
        connection = self.connect(create=False)
        if connection is None:
            raise LifecycleError("生命周期状态尚不存在；没有可用于路由建议的评测")
        try:
            version = connection.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            if version is None or int(version["value"]) not in {2, 3, SCHEMA_VERSION}:
                raise LifecycleError("路由建议需要 v2、v3 或 v4 状态；先完成安全迁移")
            row, _, _, _ = self.verified_active_agent(connection, agent_id)
            if row["state"] == "retire_eligible":
                return self.route_payload(
                    row=row,
                    task_class=task_class,
                    risk_tier=risk_tier,
                    execution_mode=execution_mode,
                    service_tier=service_tier,
                    rows=(),
                    eligible=(),
                    action="hold",
                    status="retirement_precedes_routing",
                    reason_codes=["retire_eligible"],
                )
            return self._recommend_route(
                connection, row, task_class, risk_tier, execution_mode, service_tier
            )
        finally:
            connection.close()

    @staticmethod
    def comparable_evaluations(
        connection: sqlite3.Connection,
        agent_id: str,
        revision: int,
        task_class: str,
        risk_tier: str,
        *,
        limit: int = 5,
    ) -> list[sqlite3.Row]:
        rows = connection.execute(
            """SELECT e.*,
                      COALESCE(m.credit_bucket, 'unknown') AS metric_credit_bucket,
                      COALESCE(m.retry_count, 0) AS metric_retry_count,
                      COALESCE(m.rework_count, 0) AS metric_rework_count,
                      COALESCE(m.failure_reason, 'none') AS metric_failure_reason,
                      COALESCE(r.attribution, 'unknown') AS metric_attribution
                 FROM evaluations e
                 LEFT JOIN evaluation_metrics m ON m.evaluation_id=e.evaluation_id
                 LEFT JOIN evaluation_routing r ON r.evaluation_id=e.evaluation_id
                WHERE e.agent_id=? AND e.revision=? AND e.task_class=? AND e.risk_tier=?
                ORDER BY e.created_at DESC, e.rowid DESC LIMIT ?""",
            (agent_id, revision, task_class, risk_tier, limit),
        ).fetchall()
        return list(reversed(rows))

    @staticmethod
    def evaluation_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "evaluation_id": row["evaluation_id"],
            "quality": row["correctness"] + row["clarity"],
            "correctness": row["correctness"],
            "evidence": row["evidence"],
            "scope": row["scope"],
            "safety": row["safety"],
            "total": row["total"],
            "wall_time": row["duration_bucket"],
            "tokens": row["token_bucket"],
            "credits": row["metric_credit_bucket"],
            "retries": row["metric_retry_count"],
            "rework": row["metric_rework_count"],
            "failure_reason": row["metric_failure_reason"],
            "attribution": row["metric_attribution"],
            "judge_kind": row["judge_kind"],
            "judge_confidence": row["judge_confidence"],
        }

    @staticmethod
    def stagnation_evidence_eligible(row: sqlite3.Row) -> bool:
        try:
            evidence_flags = set(json.loads(row["evidence_flags"]))
        except (TypeError, json.JSONDecodeError):
            return False
        return (
            row["judge_confidence"] == "high"
            and row["judge_kind"] in {"deterministic", "independent_model", "human"}
            and bool(evidence_flags & STRONG_EVIDENCE_FLAGS)
            and row["critical_event"] == "none"
            and row["metric_failure_reason"] not in NON_EVOLUTION_FAILURE_REASONS
            and row["metric_attribution"] not in {"tool_or_environment", "role_mismatch"}
        )

    @staticmethod
    def meaningful_evaluation_improvement(
        incumbent: sqlite3.Row, challenger: sqlite3.Row
    ) -> bool:
        if (
            challenger["safety"] < incumbent["safety"]
            or challenger["correctness"] < incumbent["correctness"]
        ):
            return False
        if challenger["total"] >= incumbent["total"] + 2:
            return True
        if challenger["total"] < incumbent["total"]:
            return False
        improved = False
        for base_key, metric_key in (
            ("duration_bucket", "duration_bucket"),
            ("token_bucket", "token_bucket"),
            ("metric_credit_bucket", "metric_credit_bucket"),
        ):
            incumbent_rank = bucket_rank(incumbent[base_key])
            challenger_rank = bucket_rank(challenger[metric_key])
            if incumbent_rank is None or challenger_rank is None:
                continue
            if challenger_rank > incumbent_rank:
                return False
            improved = improved or challenger_rank < incumbent_rank
        for key in ("metric_retry_count", "metric_rework_count"):
            if challenger[key] > incumbent[key]:
                return False
            improved = improved or challenger[key] < incumbent[key]
        return improved

    def _stagnation_payload(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        task_class: str,
        risk_tier: str,
    ) -> dict[str, Any]:
        recent = self.comparable_evaluations(
            connection,
            row["agent_id"],
            row["revision"],
            task_class,
            risk_tier,
        )
        eligible_rows = [item for item in recent if self.stagnation_evidence_eligible(item)]
        repeated: dict[str, int] = {}
        for item in eligible_rows:
            reason = item["metric_failure_reason"]
            if (
                reason != "none"
            ):
                repeated[reason] = repeated.get(reason, 0) + 1
        repeated_reason = next(
            (reason for reason, count in sorted(repeated.items()) if count >= 3),
            None,
        )

        no_improvement_streak = 0
        if eligible_rows:
            incumbent = eligible_rows[0]
            for challenger in eligible_rows[1:]:
                if self.meaningful_evaluation_improvement(incumbent, challenger):
                    incumbent = challenger
                    no_improvement_streak = 0
                else:
                    no_improvement_streak += 1
        latest = eligible_rows[-1] if eligible_rows else None
        unresolved_objective = bool(
            latest
            and (
                latest["total"] < 90
                or latest["duration_bucket"] == "high"
                or latest["token_bucket"] == "high"
                or latest["metric_credit_bucket"] == "high"
                or latest["metric_retry_count"] > 0
                or latest["metric_rework_count"] > 0
            )
        )
        no_comparable_improvement = (
            len(eligible_rows) >= 4
            and no_improvement_streak >= 3
            and unresolved_objective
        )
        reasons: list[str] = []
        if no_comparable_improvement:
            reasons.append("no_comparable_improvement")
        if repeated_reason is not None:
            reasons.append(f"repeated_failure:{repeated_reason}")
        eligible = bool(reasons) and row["state"] != "retire_eligible"
        if row["state"] == "retire_eligible":
            status = "retirement_precedes_variation"
        elif eligible:
            status = "stagnant"
        elif len(eligible_rows) < 4:
            status = "insufficient_evidence"
        else:
            status = "improving_or_stable"
        return {
            "ok": True,
            "action": "supervise" if eligible else "hold",
            "status": status,
            "agent_id": row["agent_id"],
            "revision": row["revision"],
            "task_class": task_class,
            "risk_tier": risk_tier,
            "eligible": eligible,
            "reason_codes": reasons,
            "repeated_failure_reason": repeated_reason,
            "no_improvement_streak": no_improvement_streak,
            "comparable_evaluation_count": len(eligible_rows),
            "excluded_evaluation_count": len(recent) - len(eligible_rows),
            "recent_evaluations": [
                self.evaluation_summary(item) for item in eligible_rows
            ],
            "toml_modified": False,
            "global_config_modified": False,
        }

    def stagnation_status(
        self, agent_id: str, task_class: str, risk_tier: str
    ) -> dict[str, Any]:
        if task_class not in ALLOWED_TASK_CLASSES:
            raise LifecycleError("task_class 不受支持")
        if risk_tier not in ALLOWED_RISK_CEILINGS:
            raise LifecycleError("risk_tier 不受支持")
        connection = self.connect(create=False)
        if connection is None:
            raise LifecycleError("生命周期状态尚不存在；没有可比较的评测")
        try:
            version = connection.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            if version is None or int(version["value"]) != SCHEMA_VERSION:
                raise LifecycleError(
                    "stagnation-status 是只读命令，需要先由一次授权 mutation 将状态迁移到 v4"
                )
            pending_operations = connection.execute(
                "SELECT COUNT(*) AS count FROM operations WHERE stage='prepared'"
            ).fetchone()["count"]
            if pending_operations:
                return {
                    "ok": False,
                    "action": "hold",
                    "status": "recovery_required",
                    "agent_id": agent_id,
                    "task_class": task_class,
                    "risk_tier": risk_tier,
                    "pending_operations": pending_operations,
                    "eligible": False,
                    "reason_codes": ["pending_lifecycle_operation"],
                    "toml_modified": False,
                    "global_config_modified": False,
                }
            row, _, _, _ = self.verified_active_agent(connection, agent_id)
            return self._stagnation_payload(connection, row, task_class, risk_tier)
        finally:
            connection.close()

    @staticmethod
    def variation_plan_result(row: sqlite3.Row, *, action: str) -> dict[str, Any]:
        lineage = json.loads(row["lineage_json"])
        return {
            "ok": True,
            "action": action,
            "session_id": row["session_id"],
            "request_id": row["request_id"],
            "agent_id": row["agent_id"],
            "base_revision": row["base_revision"],
            "status": row["status"],
            "trigger": row["trigger"],
            "lineage": lineage,
            "budgets": {
                "candidate_limit": row["candidate_limit"],
                "wall_time_seconds": row["wall_time_seconds"],
                "tool_call_limit": row["tool_call_limit"],
                "token_bucket": row["token_bucket"],
                "credit_bucket": row["credit_bucket"],
                "expires_at": row["expires_at"],
            },
            "candidate_contract": {
                "required_count": row["candidate_limit"],
                "allowed_rationale_codes": sorted(ALLOWED_VARIATION_RATIONALES),
                "maximum_rule_characters": 240,
                "stable_toml_write_allowed": False,
            },
            "supervisor": {
                "allowed": row["trigger"] == "stagnation",
                "scope": "propose_direction_only",
                "automatic_promotion_allowed": False,
                "automatic_global_change_allowed": False,
            },
            "toml_modified": False,
            "global_config_modified": False,
        }

    def plan_variation(self, raw_plan: dict[str, Any]) -> dict[str, Any]:
        plan = validate_variation_plan(raw_plan)
        request_sha256 = sha256_bytes(json_text(plan).encode("utf-8"))
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                existing = connection.execute(
                    "SELECT * FROM variation_sessions WHERE request_id=?",
                    (plan["request_id"],),
                ).fetchone()
                if existing is not None:
                    if existing["request_sha256"] != request_sha256:
                        raise LifecycleError("同一 request_id 的变异计划发生变化")
                    connection.commit()
                    return self.variation_plan_result(existing, action="variation_plan_exists")
                try:
                    row, _, _, _ = self.verified_active_agent(connection, plan["agent_id"])
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, plan["agent_id"])
                    raise
                if row["state"] not in {"probation", "active", "degraded"}:
                    raise LifecycleError("当前代理状态不允许创建变异会话")
                if self.active_lease_count(connection, row["agent_id"]):
                    raise LifecycleError("存在活动运行租约，禁止基于移动中的基线创建变异会话")
                open_session = connection.execute(
                    """SELECT session_id FROM variation_sessions
                        WHERE agent_id=? AND base_revision=?
                          AND status IN ('planned','staged') AND expires_at>?""",
                    (row["agent_id"], row["revision"], utc_now()),
                ).fetchone()
                if open_session is not None:
                    raise LifecycleError("当前 revision 已有未结束的变异会话")
                stagnation = self._stagnation_payload(
                    connection, row, plan["task_class"], plan["risk_tier"]
                )
                if plan["trigger"] == "stagnation" and not stagnation["eligible"]:
                    raise LifecycleError("没有足够的可比停滞证据，禁止启动 supervisor")
                promoted_rules = [
                    {"rule_key": item["rule_key"], "rule": item["rule_text"]}
                    for item in connection.execute(
                        """SELECT rule_key, rule_text FROM candidates
                            WHERE agent_id=? AND status='promoted'
                            ORDER BY promoted_at, candidate_id""",
                        (row["agent_id"],),
                    ).fetchall()
                ]
                lineage = {
                    "policy_version": VARIATION_POLICY_VERSION,
                    "agent_id": row["agent_id"],
                    "revision": row["revision"],
                    "task_class": plan["task_class"],
                    "risk_tier": plan["risk_tier"],
                    "current_model": row["model"],
                    "current_reasoning_effort": row["reasoning_effort"],
                    "validated_experience": promoted_rules,
                    "recent_evaluations": stagnation["recent_evaluations"],
                    "trigger_status": {
                        "status": stagnation["status"],
                        "reason_codes": stagnation["reason_codes"],
                        "no_improvement_streak": stagnation["no_improvement_streak"],
                    },
                }
                session_id = str(uuid.uuid4())
                created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
                expires = created + dt.timedelta(seconds=plan["wall_time_seconds"])
                created_text = created.isoformat().replace("+00:00", "Z")
                expires_text = expires.isoformat().replace("+00:00", "Z")
                trigger_ids = [
                    item["evaluation_id"] for item in stagnation["recent_evaluations"]
                ]
                connection.execute(
                    """INSERT INTO variation_sessions(
                           session_id, request_id, request_sha256, policy_version,
                           agent_id, base_revision, base_sha256, task_class, risk_tier,
                           trigger, trigger_evaluation_ids, lineage_json, candidate_limit,
                           wall_time_seconds, tool_call_limit, token_bucket, credit_bucket,
                           status, supervisor_direction, stage_sha256, created_at, expires_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        session_id,
                        plan["request_id"],
                        request_sha256,
                        VARIATION_POLICY_VERSION,
                        row["agent_id"],
                        row["revision"],
                        row["expected_sha256"],
                        plan["task_class"],
                        plan["risk_tier"],
                        plan["trigger"],
                        json_text(trigger_ids),
                        json_text(lineage),
                        plan["candidate_limit"],
                        plan["wall_time_seconds"],
                        plan["tool_call_limit"],
                        plan["token_bucket"],
                        plan["credit_bucket"],
                        "planned",
                        None,
                        None,
                        created_text,
                        expires_text,
                    ),
                )
                connection.commit()
                stored = connection.execute(
                    "SELECT * FROM variation_sessions WHERE session_id=?", (session_id,)
                ).fetchone()
                assert stored is not None
                return self.variation_plan_result(stored, action="variation_planned")
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    @staticmethod
    def staged_candidate_payloads(
        connection: sqlite3.Connection, session_id: str
    ) -> list[dict[str, Any]]:
        return [
            {
                "variation_candidate_id": item["variation_candidate_id"],
                "ordinal": item["ordinal"],
                "rule_key": item["rule_key"],
                "rule": item["rule_text"],
                "applies_to": item["applies_to"],
                "rationale_code": item["rationale_code"],
                "status": item["status"],
                "shadow_suite_sha256": item["shadow_suite_sha256"],
                "candidate_id": item["promoted_candidate_id"],
            }
            for item in connection.execute(
                """SELECT * FROM variation_candidates
                    WHERE session_id=? ORDER BY ordinal""",
                (session_id,),
            ).fetchall()
        ]

    def stage_variation(self, raw_stage: dict[str, Any]) -> dict[str, Any]:
        stage = validate_variation_stage(raw_stage)
        stage_sha256 = sha256_bytes(json_text(stage).encode("utf-8"))
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                session = connection.execute(
                    "SELECT * FROM variation_sessions WHERE session_id=?",
                    (stage["session_id"],),
                ).fetchone()
                if session is None:
                    raise LifecycleError("变异会话不存在")
                if session["status"] != "planned":
                    if session["stage_sha256"] == stage_sha256:
                        candidates = self.staged_candidate_payloads(
                            connection, stage["session_id"]
                        )
                        connection.commit()
                        return {
                            "ok": True,
                            "action": "variation_stage_exists",
                            "session_id": stage["session_id"],
                            "status": session["status"],
                            "candidates": candidates,
                            "toml_modified": False,
                        }
                    raise LifecycleError("变异会话已经提交，拒绝用不同结果覆盖")
                if parse_utc(session["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
                    raise LifecycleError("变异会话已超过墙钟预算；拒绝迟到候选")
                try:
                    row, _, _, _ = self.verified_active_agent(
                        connection, session["agent_id"]
                    )
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, session["agent_id"])
                    raise
                if (
                    row["revision"] != session["base_revision"]
                    or row["expected_sha256"] != session["base_sha256"]
                ):
                    raise LifecycleError("变异会话基线已漂移；incumbent 保持不变")
                if self.active_lease_count(connection, row["agent_id"]):
                    raise LifecycleError("存在活动运行租约，禁止提交变异候选")
                if len(stage["candidates"]) != session["candidate_limit"]:
                    raise LifecycleError("候选数量必须与计划中的固定 candidate_limit 一致")
                if stage["elapsed_seconds"] > session["wall_time_seconds"]:
                    raise LifecycleError("变异候选超过墙钟预算")
                if stage["tool_calls_used"] > session["tool_call_limit"]:
                    raise LifecycleError("变异候选超过工具调用预算")
                if bucket_rank(stage["token_bucket_used"]) > bucket_rank(session["token_bucket"]):
                    raise LifecycleError("变异候选超过 token 预算桶")
                if bucket_rank(stage["credit_bucket_used"]) > bucket_rank(
                    session["credit_bucket"]
                ):
                    raise LifecycleError("变异候选超过 credit 预算桶")
                if session["trigger"] == "stagnation" and stage["supervisor_direction"] is None:
                    raise LifecycleError("停滞触发的会话必须记录 supervisor 新方向")
                if session["trigger"] == "manual" and stage["supervisor_direction"] is not None:
                    raise LifecycleError("manual 会话不得伪称 supervisor 方向")
                now = utc_now()
                for ordinal, candidate in enumerate(stage["candidates"], start=1):
                    if candidate["applies_to"] not in {session["task_class"], "other"}:
                        raise LifecycleError("候选 applies_to 必须匹配会话 task_class 或为 other")
                    collision = connection.execute(
                        """SELECT 1 FROM observations
                            WHERE agent_id=? AND revision=? AND rule_key=?
                           UNION ALL
                           SELECT 1 FROM candidates
                            WHERE agent_id=? AND rule_key=?
                           LIMIT 1""",
                        (
                            row["agent_id"],
                            row["revision"],
                            candidate["rule_key"],
                            row["agent_id"],
                            candidate["rule_key"],
                        ),
                    ).fetchone()
                    if collision is not None:
                        raise LifecycleError("候选 rule_key 已存在于当前 lineage")
                    connection.execute(
                        """INSERT INTO variation_candidates(
                               variation_candidate_id, session_id, ordinal, rule_key,
                               rule_text, applies_to, rationale_code, status,
                               shadow_suite_sha256, verification_sha256,
                               promoted_candidate_id, created_at, verified_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            str(uuid.uuid4()),
                            stage["session_id"],
                            ordinal,
                            candidate["rule_key"],
                            candidate["rule"],
                            candidate["applies_to"],
                            candidate["rationale_code"],
                            "staged",
                            None,
                            None,
                            None,
                            now,
                            None,
                        ),
                    )
                connection.execute(
                    """UPDATE variation_sessions
                          SET status='staged', supervisor_direction=?, stage_sha256=?,
                              stage_elapsed_seconds=?, stage_tool_calls_used=?,
                              stage_token_bucket_used=?, stage_credit_bucket_used=?
                        WHERE session_id=?""",
                    (
                        stage["supervisor_direction"],
                        stage_sha256,
                        stage["elapsed_seconds"],
                        stage["tool_calls_used"],
                        stage["token_bucket_used"],
                        stage["credit_bucket_used"],
                        stage["session_id"],
                    ),
                )
                candidates = self.staged_candidate_payloads(connection, stage["session_id"])
                connection.commit()
                return {
                    "ok": True,
                    "action": "variation_staged",
                    "session_id": stage["session_id"],
                    "status": "staged",
                    "candidates": candidates,
                    "promotion_eligible": False,
                    "toml_modified": False,
                    "global_config_modified": False,
                    "next_step": "在相同 shadow 用例上独立验证候选，再运行 variation-verify。",
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def verify_variation(self, raw_report: dict[str, Any]) -> dict[str, Any]:
        report = validate_variation_verification(raw_report)
        self.promotion_gate(report)
        resource_comparison = variation_resource_comparison(report)
        verification_sha256 = sha256_bytes(json_text(report).encode("utf-8"))
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                candidate = connection.execute(
                    """SELECT vc.*, vs.agent_id, vs.base_revision, vs.base_sha256,
                              vs.status AS session_status, vs.expires_at,
                              vs.wall_time_seconds, vs.tool_call_limit,
                              vs.token_bucket, vs.credit_bucket,
                              vs.stage_elapsed_seconds, vs.stage_tool_calls_used,
                              vs.stage_token_bucket_used, vs.stage_credit_bucket_used
                         FROM variation_candidates vc
                         JOIN variation_sessions vs ON vs.session_id=vc.session_id
                        WHERE vc.variation_candidate_id=?""",
                    (report["variation_candidate_id"],),
                ).fetchone()
                if candidate is None:
                    raise LifecycleError("变异候选不存在")
                if candidate["status"] == "verified":
                    if candidate["verification_sha256"] != verification_sha256:
                        raise LifecycleError("已验证候选不能用不同报告覆盖")
                    connection.commit()
                    return {
                        "ok": True,
                        "action": "variation_verification_exists",
                        "variation_candidate_id": report["variation_candidate_id"],
                        "candidate_id": candidate["promoted_candidate_id"],
                        "promotion_eligible": True,
                        "toml_modified": False,
                    }
                if candidate["status"] != "staged":
                    raise LifecycleError("变异候选状态不允许验证")
                if candidate["session_status"] not in {"staged", "verified"}:
                    raise LifecycleError("变异会话状态不允许验证")
                try:
                    row, _, _, _ = self.verified_active_agent(
                        connection, candidate["agent_id"]
                    )
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, candidate["agent_id"])
                    raise
                if (
                    row["revision"] != candidate["base_revision"]
                    or row["expected_sha256"] != candidate["base_sha256"]
                ):
                    raise LifecycleError("候选基线已漂移；拒绝验证迟到 challenger")
                if self.active_lease_count(connection, row["agent_id"]):
                    raise LifecycleError("存在活动运行租约，禁止验证 challenger")
                if parse_utc(candidate["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
                    raise LifecycleError("变异会话已超过总墙钟预算；拒绝迟到 shadow 验证")
                if not (
                    candidate["stage_elapsed_seconds"]
                    <= report["elapsed_seconds_total"]
                    <= candidate["wall_time_seconds"]
                ):
                    raise LifecycleError("shadow 验证的总 elapsed_seconds 超出计划或低报")
                if not (
                    candidate["stage_tool_calls_used"]
                    <= report["tool_calls_total"]
                    <= candidate["tool_call_limit"]
                ):
                    raise LifecycleError("shadow 验证的总 tool_calls 超出计划或低报")
                if not (
                    bucket_rank(candidate["stage_token_bucket_used"])
                    <= bucket_rank(report["token_bucket_total"])
                    <= bucket_rank(candidate["token_bucket"])
                ):
                    raise LifecycleError("shadow 验证的总 token 桶超出计划或低报")
                if not (
                    bucket_rank(candidate["stage_credit_bucket_used"])
                    <= bucket_rank(report["credit_bucket_total"])
                    <= bucket_rank(candidate["credit_bucket"])
                ):
                    raise LifecycleError("shadow 验证的总 credit 桶超出计划或低报")
                suite_mismatch = connection.execute(
                    """SELECT 1 FROM variation_candidates
                        WHERE session_id=? AND status='verified'
                          AND shadow_suite_sha256<>? LIMIT 1""",
                    (candidate["session_id"], report["shadow_suite_sha256"]),
                ).fetchone()
                if suite_mismatch is not None:
                    raise LifecycleError("同一变异会话的 challenger 必须使用同一 shadow suite")
                duplicate = connection.execute(
                    """SELECT 1 FROM candidates
                        WHERE agent_id=? AND rule_key=? LIMIT 1""",
                    (row["agent_id"], candidate["rule_key"]),
                ).fetchone()
                if duplicate is not None:
                    raise LifecycleError("当前 revision 已有同 key 候选")
                candidate_id = str(uuid.uuid4())
                now = utc_now()
                connection.execute(
                    "INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        candidate_id,
                        row["agent_id"],
                        row["revision"],
                        row["expected_sha256"],
                        candidate["rule_key"],
                        candidate["rule_text"],
                        candidate["applies_to"],
                        report["case_count"],
                        "candidate",
                        now,
                        None,
                    ),
                )
                connection.execute(
                    """UPDATE variation_candidates
                          SET status='verified', shadow_suite_sha256=?,
                              verification_sha256=?, promoted_candidate_id=?, verified_at=?
                        WHERE variation_candidate_id=?""",
                    (
                        report["shadow_suite_sha256"],
                        verification_sha256,
                        candidate_id,
                        now,
                        report["variation_candidate_id"],
                    ),
                )
                remaining = connection.execute(
                    """SELECT COUNT(*) AS count FROM variation_candidates
                        WHERE session_id=? AND status='staged'""",
                    (candidate["session_id"],),
                ).fetchone()["count"]
                if remaining == 0:
                    connection.execute(
                        "UPDATE variation_sessions SET status='verified' WHERE session_id=?",
                        (candidate["session_id"],),
                    )
                connection.commit()
                return {
                    "ok": True,
                    "action": "variation_verified",
                    "variation_candidate_id": report["variation_candidate_id"],
                    "candidate_id": candidate_id,
                    "promotion_eligible": True,
                    "resource_comparison": resource_comparison,
                    "toml_modified": False,
                    "global_config_modified": False,
                    "next_step": "使用同一独立报告中的 candidate_id 运行 promote；晋升门槛仍会重新检查。",
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def record_evaluation(self, raw_report: dict[str, Any]) -> dict[str, Any]:
        report = validate_report(raw_report)
        agent_id = report["agent_id"]
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                try:
                    row, _, _, _ = self.verified_active_agent(connection, agent_id)
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, agent_id)
                    raise
                if self.active_lease_count(connection, agent_id):
                    raise LifecycleError("仍有活动运行租约；必须等子代理结束并释放租约后再评测")
                routing = report["routing"]
                if routing is not None and routing["execution_mode"] == "managed_named" and (
                    routing["requested_model"] != row["model"]
                    or routing["requested_reasoning_effort"] != row["reasoning_effort"]
                ):
                    raise LifecycleError(
                        "managed_named 评测的请求模型和推理强度必须与受管 TOML 配置一致"
                    )
                report_digest, legacy_report_digest = evaluation_report_digests(report)
                existing = connection.execute(
                    """SELECT * FROM evaluations
                       WHERE agent_id=? AND revision=? AND run_id=?""",
                    (agent_id, row["revision"], report["run_id"]),
                ).fetchone()
                if existing is not None:
                    if existing["report_sha256"] not in {
                        report_digest,
                        legacy_report_digest,
                    }:
                        raise LifecycleError("同一 run_id 的评测内容发生变化；拒绝把重试当作新运行")
                    metrics = connection.execute(
                        "SELECT 1 FROM evaluation_metrics WHERE evaluation_id=?",
                        (existing["evaluation_id"],),
                    ).fetchone()
                    if metrics is None:
                        legacy_row = existing["report_sha256"] == legacy_report_digest
                        connection.execute(
                            "INSERT INTO evaluation_metrics VALUES(?,?,?,?,?)",
                            (
                                existing["evaluation_id"],
                                "unknown" if legacy_row else report["credit_bucket"],
                                0 if legacy_row else report["retry_count"],
                                0 if legacy_row else report["rework_count"],
                                "none" if legacy_row else report["failure_reason"],
                            ),
                        )
                    experience = report["experience"]
                    observed = None
                    if experience is not None:
                        observed = connection.execute(
                            "SELECT observation_count, candidate_id FROM observations WHERE agent_id=? AND revision=? AND rule_key=?",
                            (agent_id, row["revision"], experience["key"]),
                        ).fetchone()
                    connection.commit()
                    recommendation = (
                        self._recommend_route(
                            connection,
                            row,
                            report["task_class"],
                            report["risk_tier"],
                            routing["execution_mode"],
                            routing["requested_service_tier"],
                        )
                        if routing is not None
                        else None
                    )
                    return {
                        "ok": True,
                        "action": "evaluation_already_recorded",
                        "evaluation_id": existing["evaluation_id"],
                        "run_id": report["run_id"],
                        "agent_id": agent_id,
                        "revision": row["revision"],
                        "score": existing["total"],
                        "state": row["state"],
                        "experience_observation_count": (
                            observed["observation_count"] if observed is not None else 0
                        ),
                        "candidate_id": observed["candidate_id"] if observed is not None else None,
                        "routing_recorded": routing is not None,
                        "configuration_recommendation": recommendation,
                    }
                evaluation_id = str(uuid.uuid4())
                now = utc_now()
                scores = report["scores"]
                connection.execute(
                    """INSERT INTO evaluations(
                           evaluation_id, run_id, agent_id, revision, task_class, risk_tier,
                           correctness, evidence, scope, efficiency, clarity, safety, total,
                           evidence_flags, critical_event, confirmations, judge_kind,
                           judge_confidence, duration_bucket, token_bucket, user_verdict,
                           report_sha256, created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        evaluation_id,
                        report["run_id"],
                        agent_id,
                        row["revision"],
                        report["task_class"],
                        report["risk_tier"],
                        scores["correctness"],
                        scores["evidence"],
                        scores["scope"],
                        scores["efficiency"],
                        scores["clarity"],
                        scores["safety"],
                        report["total"],
                        json_text(report["evidence_flags"]),
                        report["critical_event"],
                        json_text(report["critical_confirmations"]),
                        report["judge_kind"],
                        report["judge_confidence"],
                        report["duration_bucket"],
                        report["token_bucket"],
                        report["user_verdict"],
                        report_digest,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO evaluation_metrics VALUES(?,?,?,?,?)",
                    (
                        evaluation_id,
                        report["credit_bucket"],
                        report["retry_count"],
                        report["rework_count"],
                        report["failure_reason"],
                    ),
                )
                if routing is not None:
                    connection.execute(
                        """INSERT INTO evaluation_routing(
                               evaluation_id, policy_version, requested_model,
                               requested_reasoning_effort, requested_service_tier,
                               effective_model, effective_reasoning_effort,
                               effective_service_tier, execution_mode, host_config_status,
                               attribution, created_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            evaluation_id,
                            ROUTING_POLICY_VERSION,
                            routing["requested_model"],
                            routing["requested_reasoning_effort"],
                            routing["requested_service_tier"],
                            routing["effective_model"],
                            routing["effective_reasoning_effort"],
                            routing["effective_service_tier"],
                            routing["execution_mode"],
                            routing["host_config_status"],
                            routing["attribution"],
                            now,
                        ),
                    )

                candidate_id: str | None = None
                observation_count = 0
                experience = report["experience"]
                if high_quality(report) and experience is not None:
                    observed = connection.execute(
                        "SELECT * FROM observations WHERE agent_id=? AND revision=? AND rule_key=?",
                        (agent_id, row["revision"], experience["key"]),
                    ).fetchone()
                    if observed is None:
                        observation_count = 1
                        connection.execute(
                            "INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?)",
                            (
                                agent_id,
                                row["revision"],
                                experience["key"],
                                experience["rule"],
                                experience["applies_to"],
                                1,
                                None,
                                now,
                                now,
                            ),
                        )
                    else:
                        if (
                            observed["rule_text"] != experience["rule"]
                            or observed["applies_to"] != experience["applies_to"]
                        ):
                            raise LifecycleError(
                                "同一 experience.key 的规则文本或适用域发生变化；请使用新 key，避免语义碰撞"
                            )
                        observation_count = observed["observation_count"] + 1
                        connection.execute(
                            "UPDATE observations SET observation_count=?, last_seen_at=? WHERE agent_id=? AND revision=? AND rule_key=?",
                            (
                                observation_count,
                                now,
                                agent_id,
                                row["revision"],
                                experience["key"],
                            ),
                        )
                        candidate_id = observed["candidate_id"]
                    if observation_count >= MIN_RULE_OBSERVATIONS and candidate_id is None:
                        candidate_id = str(uuid.uuid4())
                        connection.execute(
                            "INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                candidate_id,
                                agent_id,
                                row["revision"],
                                row["expected_sha256"],
                                experience["key"],
                                experience["rule"],
                                experience["applies_to"],
                                observation_count,
                                "candidate",
                                now,
                                None,
                            ),
                        )
                        connection.execute(
                            "UPDATE observations SET candidate_id=? WHERE agent_id=? AND revision=? AND rule_key=?",
                            (candidate_id, agent_id, row["revision"], experience["key"]),
                        )

                recent = connection.execute(
                    """SELECT * FROM evaluations
                       WHERE agent_id=? AND revision=? AND task_class=? AND risk_tier=?
                       ORDER BY created_at DESC, rowid DESC LIMIT 5""",
                    (
                        agent_id,
                        row["revision"],
                        report["task_class"],
                        report["risk_tier"],
                    ),
                ).fetchall()
                new_state = row["state"]
                retirement_reason: str | None = None
                if self.critical_event_confirmed(report):
                    new_state = "retire_eligible"
                    retirement_reason = report["critical_event"]
                elif sum(self.extreme_evidence_row(item) for item in recent) >= 3:
                    new_state = "retire_eligible"
                    retirement_reason = "repeated_evidence_backed_extreme_failure"
                elif sum(item["total"] < 65 for item in recent) >= 3:
                    new_state = "degraded"
                elif (
                    len(recent) >= 3
                    and all(item["total"] >= 80 for item in recent[:3])
                    and row["state"] in {"probation", "degraded"}
                ):
                    new_state = "active"
                connection.execute(
                    "UPDATE agents SET state=?, updated_at=? WHERE agent_id=?",
                    (new_state, now, agent_id),
                )
                if routing is None:
                    recommendation = None
                elif new_state == "retire_eligible":
                    recommendation = self.route_payload(
                        row=row,
                        task_class=report["task_class"],
                        risk_tier=report["risk_tier"],
                        execution_mode=routing["execution_mode"],
                        service_tier=routing["requested_service_tier"],
                        rows=(),
                        eligible=(),
                        action="hold",
                        status="retirement_precedes_routing",
                        reason_codes=["retire_eligible"],
                    )
                else:
                    recommendation = self._recommend_route(
                        connection,
                        row,
                        report["task_class"],
                        report["risk_tier"],
                        routing["execution_mode"],
                        routing["requested_service_tier"],
                    )
                connection.commit()
                return {
                    "ok": True,
                    "action": "evaluation_recorded",
                    "evaluation_id": evaluation_id,
                    "run_id": report["run_id"],
                    "agent_id": agent_id,
                    "revision": row["revision"],
                    "score": report["total"],
                    "quality_band": (
                        "high" if high_quality(report) else "acceptable" if report["total"] >= 65 else "poor" if report["total"] >= 30 else "extreme_observation"
                    ),
                    "state": new_state,
                    "retirement_reason": retirement_reason,
                    "experience_observation_count": observation_count,
                    "candidate_id": candidate_id,
                    "routing_recorded": routing is not None,
                    "configuration_recommendation": recommendation,
                    "next_step": (
                        "执行 retire，将代理从活动目录移入可恢复隔离区。"
                        if new_state == "retire_eligible"
                        else "对 candidate 运行独立 shadow 比较后再决定是否 promote。"
                        if candidate_id
                        else "继续积累可复现证据；本次不改写代理。"
                    ),
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    @staticmethod
    def promotion_gate(report: dict[str, Any]) -> None:
        strong = set(report["evidence_flags"]) & STRONG_EVIDENCE_FLAGS
        if report["case_count"] < 3:
            raise LifecycleError("晋升至少需要 3 个脱敏 shadow 对比用例")
        if report["critical_regression"]:
            raise LifecycleError("候选存在关键回归，incumbent 保持不变")
        if report["challenger_quality"] < 90:
            raise LifecycleError("challenger_quality 未达到 90")
        quality_gain = report["challenger_quality"] - report["incumbent_quality"]
        efficiency_gain = report["challenger_efficiency"] - report["incumbent_efficiency"]
        if not (quality_gain >= 3 or (quality_gain >= 0 and efficiency_gain >= 2)):
            raise LifecycleError("候选未证明质量提升，或在质量不降时证明效率提升")
        if len(report["evidence_flags"]) < 2 or not strong:
            raise LifecycleError("晋升缺少至少两类证据及一项强证据")

    def promote_candidate(self, raw_report: dict[str, Any]) -> dict[str, Any]:
        report = validate_promotion(raw_report)
        self.promotion_gate(report)
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                candidate = connection.execute(
                    "SELECT * FROM candidates WHERE candidate_id=?", (report["candidate_id"],)
                ).fetchone()
                if candidate is None:
                    raise LifecycleError("候选不存在")
                if candidate["status"] == "promoted":
                    row = self.get_agent(connection, candidate["agent_id"])
                    connection.commit()
                    return {
                        "ok": True,
                        "action": "candidate_already_promoted",
                        "candidate_id": report["candidate_id"],
                        "agent_id": candidate["agent_id"],
                        "revision": row["revision"],
                        "state": row["state"],
                        "injection_required": True,
                    }
                if candidate["status"] != "candidate":
                    raise LifecycleError("候选已被拒绝或处理")
                agent_id = candidate["agent_id"]
                try:
                    row, _, _, parsed = self.verified_active_agent(connection, agent_id)
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, agent_id)
                    raise
                if self.active_lease_count(connection, agent_id):
                    raise LifecycleError("存在活动运行租约，禁止进化")
                if candidate["observed_count"] < MIN_RULE_OBSERVATIONS:
                    raise LifecycleError("候选没有足够的重复高质量观察")
                if (
                    candidate["base_revision"] != row["revision"]
                    or candidate["base_sha256"] != row["expected_sha256"]
                ):
                    raise LifecycleError("候选基线已过期；保留 incumbent，不自动重放旧规则")
                promoted_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM candidates WHERE agent_id=? AND status='promoted'",
                    (agent_id,),
                ).fetchone()["count"]
                if promoted_count >= MAX_PROMOTED_RULES:
                    raise LifecycleError("已达到 12 条验证规则上限；拒绝继续膨胀提示")
                promoted_rules = [
                    item["rule_text"]
                    for item in connection.execute(
                        "SELECT rule_text FROM candidates WHERE agent_id=? AND status='promoted' ORDER BY promoted_at, candidate_id",
                        (agent_id,),
                    ).fetchall()
                ]
                promoted_rules.append(candidate["rule_text"])
                effective_prompt = parsed["developer_instructions"].rstrip()
                effective_prompt += "\n\n经回归评测晋升的 Lean Stack 经验："
                effective_prompt += "".join(f"\n- {rule}" for rule in promoted_rules)
                if len(effective_prompt.encode("utf-8")) > MAX_INSTRUCTION_BYTES:
                    raise LifecycleError("晋升后的有效 brief 将超过 6 KiB 上限")
                new_revision = row["revision"] + 1
                now = utc_now()
                connection.execute(
                    "UPDATE agents SET state='active', revision=?, updated_at=? WHERE agent_id=?",
                    (new_revision, now, agent_id),
                )
                connection.execute(
                    "UPDATE revisions SET status='superseded' WHERE agent_id=? AND revision=?",
                    (agent_id, row["revision"]),
                )
                connection.execute(
                    "INSERT INTO revisions VALUES(?,?,?,?,?,?,?,?)",
                    (
                        agent_id,
                        new_revision,
                        row["revision"],
                        row["expected_sha256"],
                        sha256_bytes(effective_prompt.encode("utf-8")),
                        candidate["rule_key"],
                        "active",
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE candidates SET status='promoted', promoted_at=? WHERE candidate_id=?",
                    (now, report["candidate_id"]),
                )
                connection.commit()
                return {
                    "ok": True,
                    "action": "candidate_promoted",
                    "candidate_id": report["candidate_id"],
                    "agent_id": agent_id,
                    "revision": new_revision,
                    "state": "active",
                    "toml_modified": False,
                    "injection_required": True,
                    "validated_experience_rules": promoted_rules,
                    "next_step": "后续委派从 catalog 读取验证经验并注入 brief；稳定 TOML 保持不变。",
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def retire_agent(self, agent_id: str) -> dict[str, Any]:
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                try:
                    row, source, _, _ = self.verified_active_agent(connection, agent_id)
                except OwnershipConflict:
                    connection.rollback()
                    self.mark_conflict(connection, agent_id)
                    raise
                if row["state"] != "retire_eligible":
                    raise LifecycleError("代理尚未通过可退役证据门槛")
                if self.active_lease_count(connection, agent_id):
                    raise LifecycleError("存在活动运行租约，禁止隔离")
                destination_dir = self.quarantine_dir / agent_id
                ensure_plain_directory(destination_dir, create=True)
                destination = destination_dir / f"revision-{row['revision']}-{row['expected_sha256'][:12]}.toml"
                if destination.exists() or destination.is_symlink():
                    raise LifecycleError("隔离目标已存在")
                if source.parent.stat().st_dev != destination_dir.stat().st_dev:
                    raise LifecycleError("活动目录与隔离目录不在同一卷，拒绝非原子隔离")
                operation_id = str(uuid.uuid4())
                now = utc_now()
                connection.execute(
                    """INSERT INTO operations(
                           operation_id, agent_id, operation, old_hash, new_hash,
                           source_path, destination_path, target_state, revision,
                           stage, started_at, completed_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        operation_id,
                        agent_id,
                        "quarantine",
                        row["expected_sha256"],
                        row["expected_sha256"],
                        str(source.resolve()),
                        str(destination.resolve()),
                        "quarantined",
                        row["revision"],
                        "prepared",
                        now,
                        None,
                    ),
                )
                # Commit the intent before touching the filesystem. A later
                # process can reconcile source/destination by their exact hash.
                connection.commit()
                move_no_replace(source, destination)
                fsync_directory(source.parent)
                fsync_directory(destination.parent)
                if sha256_bytes(read_small_bytes(destination)) != row["expected_sha256"]:
                    move_no_replace(destination, source)
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        "UPDATE agents SET state='conflict', updated_at=? WHERE agent_id=?",
                        (utc_now(), agent_id),
                    )
                    connection.execute(
                        "UPDATE operations SET stage='conflict', completed_at=? WHERE operation_id=?",
                        (utc_now(), operation_id),
                    )
                    connection.commit()
                    raise OwnershipConflict("隔离窗口内文件内容发生变化；已移回活动路径")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE agents SET state='quarantined', quarantine_path=?, updated_at=? WHERE agent_id=?",
                    (str(destination.resolve()), now, agent_id),
                )
                connection.execute(
                    "UPDATE operations SET stage='committed', completed_at=? WHERE operation_id=?",
                    (utc_now(), operation_id),
                )
                connection.commit()
                return {
                    "ok": True,
                    "action": "quarantined",
                    "agent_id": agent_id,
                    "name": row["name"],
                    "removed_from_active_catalog": True,
                    "recoverable": True,
                    "quarantine_path": str(destination),
                    "note": "未永久删除；当前会话可能仍缓存旧目录，新任务中再核验。",
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def restore_agent(self, agent_id: str, confirmation: str, project_root: Path | None = None) -> dict[str, Any]:
        if confirmation != f"restore:{agent_id}":
            raise LifecycleError("恢复需要精确的 --confirm restore:<agent_id>")
        with self.mutation_lock():
            connection = self.connect(create=True)
            assert connection is not None
            try:
                self.begin(connection)
                row = self.get_agent(connection, agent_id)
                if row["state"] != "quarantined" or not row["quarantine_path"]:
                    raise LifecycleError("代理不在隔离状态")
                if self.active_lease_count(connection, agent_id):
                    raise LifecycleError("存在活动租约，拒绝恢复")
                source = Path(row["quarantine_path"])
                expected_parent = (self.quarantine_dir / agent_id).resolve()
                if source.parent.resolve() != expected_parent:
                    raise OwnershipConflict("隔离路径已漂移")
                ensure_direct_child(source, self.quarantine_dir / agent_id, must_exist=True)
                data = read_small_bytes(source)
                if marker_agent_id(data) != agent_id or sha256_bytes(data) != row["expected_sha256"]:
                    raise OwnershipConflict("隔离文件身份或散列不匹配")
                parsed = parse_agent_bytes(data, str(source))
                if parsed["name"] != row["name"]:
                    raise OwnershipConflict("隔离文件 name 不匹配")
                destination = Path(row["active_path"])
                ensure_plain_directory(self.agents_dir, create=True)
                ensure_direct_child(destination, self.agents_dir, must_exist=False)
                collisions = self.all_custom_names(project_root)
                if row["name"] in collisions:
                    raise LifecycleError("恢复会产生代理名称冲突")
                if source.parent.stat().st_dev != destination.parent.stat().st_dev:
                    raise LifecycleError("隔离目录与活动目录不在同一卷")
                operation_id = str(uuid.uuid4())
                now = utc_now()
                connection.execute(
                    """INSERT INTO operations(
                           operation_id, agent_id, operation, old_hash, new_hash,
                           source_path, destination_path, target_state, revision,
                           stage, started_at, completed_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        operation_id,
                        agent_id,
                        "restore",
                        row["expected_sha256"],
                        row["expected_sha256"],
                        str(source.resolve()),
                        str(destination.resolve()),
                        "pending_reload",
                        row["revision"],
                        "prepared",
                        now,
                        None,
                    ),
                )
                connection.commit()
                move_no_replace(source, destination)
                fsync_directory(source.parent)
                fsync_directory(destination.parent)
                if sha256_bytes(read_small_bytes(destination)) != row["expected_sha256"]:
                    move_no_replace(destination, source)
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        "UPDATE agents SET state='conflict', updated_at=? WHERE agent_id=?",
                        (utc_now(), agent_id),
                    )
                    connection.execute(
                        "UPDATE operations SET stage='conflict', completed_at=? WHERE operation_id=?",
                        (utc_now(), operation_id),
                    )
                    connection.commit()
                    raise OwnershipConflict("恢复窗口内文件内容发生变化；已移回隔离路径")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE agents SET state='pending_reload', quarantine_path=NULL, updated_at=? WHERE agent_id=?",
                    (now, agent_id),
                )
                connection.execute(
                    "UPDATE operations SET stage='committed', completed_at=? WHERE operation_id=?",
                    (utc_now(), operation_id),
                )
                connection.commit()
                return {
                    "ok": True,
                    "action": "restored",
                    "agent_id": agent_id,
                    "state": "pending_reload",
                    "path": str(destination),
                    "next_step": "在新任务确认宿主已重载后执行 confirm-visible。",
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def recover(self) -> dict[str, Any]:
        with self.mutation_lock():
            return {
                "ok": True,
                "action": "recovered_pending_operations",
                "results": list(self.last_recovery),
            }

    def doctor(self, project_root: Path | None = None) -> dict[str, Any]:
        issues: list[str] = []
        if self.agents_dir.exists():
            try:
                ensure_plain_directory(self.agents_dir, create=False)
            except LifecycleError as exc:
                issues.append(str(exc))
        db_status = "absent"
        pending_operations = 0
        if self.db_path.exists():
            try:
                connection = self.connect(create=False)
                assert connection is not None
                check = connection.execute("PRAGMA quick_check").fetchone()[0]
                db_status = check
                if check != "ok":
                    issues.append(f"SQLite quick_check: {check}")
                pending_operations = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM operations WHERE stage='prepared'"
                    ).fetchone()[0]
                )
                if pending_operations:
                    issues.append(
                        f"发现 {pending_operations} 个待恢复文件操作；运行 recover 后再继续 mutation"
                    )
                connection.close()
            except (sqlite3.Error, LifecycleError) as exc:
                db_status = "error"
                issues.append(f"生命周期数据库不可用: {exc}")
        catalog = self.catalog(project_root)
        conflicts = [
            item
            for item in catalog["custom"] + catalog["registry_only"]
            if item.get("source") == "plugin_conflict"
        ]
        if conflicts:
            issues.append(f"发现 {len(conflicts)} 个受管代理所有权冲突")
        orphan_markers = [
            item
            for item in catalog["custom"]
            if item.get("source") == "user_external_immutable" and item.get("marker_agent_id")
        ]
        if orphan_markers:
            issues.append(
                f"发现 {len(orphan_markers)} 个只有 marker、没有 registry 所有权的文件；按用户文件保护"
            )
        return {
            "ok": not issues,
            "python": sys.version.split()[0],
            "tomllib": True,
            "database": db_status,
            "pending_operations": pending_operations,
            "issues": issues,
            "managed_count": sum(
                item.get("source") == "plugin_managed" for item in catalog["custom"]
            ),
            "quarantined_count": sum(
                item.get("source") == "plugin_quarantined" for item in catalog["registry_only"]
            ),
        }


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex Lean Stack custom-agent lifecycle manager")
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    parser.add_argument("--state-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog = subparsers.add_parser("catalog", help="只读盘点内置、个人、项目和受管代理")
    catalog.add_argument("--project-root", type=Path)

    create = subparsers.add_parser("create", help="从受限 JSON 规格创建受管个人代理")
    create.add_argument("--spec", type=Path, required=True)
    create.add_argument("--project-root", type=Path)

    visible = subparsers.add_parser("confirm-visible", help="仅在宿主真实选到代理后确认可见")
    visible.add_argument("--agent-id", required=True)

    lease = subparsers.add_parser("lease-acquire", help="运行受管代理前取得租约")
    lease.add_argument("--agent-id", required=True)
    lease.add_argument("--ttl-seconds", type=int, default=7200)

    release = subparsers.add_parser("lease-release", help="受管代理结束后释放租约")
    release.add_argument("--lease-id", required=True)

    record = subparsers.add_parser("record", help="记录固定 schema 的任务后评测")
    record.add_argument("--report", type=Path, required=True)

    recommend = subparsers.add_parser(
        "recommend-route", help="按同类评测只读建议下一次模型、推理强度或速度档位"
    )
    recommend.add_argument("--agent-id", required=True)
    recommend.add_argument("--task-class", choices=sorted(ALLOWED_TASK_CLASSES), required=True)
    recommend.add_argument("--risk-tier", choices=sorted(ALLOWED_RISK_CEILINGS), required=True)
    recommend.add_argument(
        "--execution-mode", choices=sorted(ALLOWED_EXECUTION_MODES), default="managed_named"
    )
    recommend.add_argument(
        "--service-tier", choices=sorted(ALLOWED_REQUESTED_SERVICE_TIERS), default="inherit"
    )

    stagnation = subparsers.add_parser(
        "stagnation-status", help="只读判断可比运行是否足以触发受限 supervisor"
    )
    stagnation.add_argument("--agent-id", required=True)
    stagnation.add_argument("--task-class", choices=sorted(ALLOWED_TASK_CLASSES), required=True)
    stagnation.add_argument(
        "--risk-tier", choices=sorted(ALLOWED_RISK_CEILINGS), required=True
    )

    variation_plan = subparsers.add_parser(
        "variation-plan", help="创建受墙钟、工具、token 和 credit 预算约束的变异会话"
    )
    variation_plan.add_argument("--plan", type=Path, required=True)

    variation_stage = subparsers.add_parser(
        "variation-stage", help="在预算内暂存 challenger，不修改稳定代理 TOML"
    )
    variation_stage.add_argument("--report", type=Path, required=True)

    variation_verify = subparsers.add_parser(
        "variation-verify", help="通过独立 shadow 和多目标门槛验证暂存 challenger"
    )
    variation_verify.add_argument("--report", type=Path, required=True)

    promote = subparsers.add_parser("promote", help="通过 shadow gate 后晋升候选规则")
    promote.add_argument("--report", type=Path, required=True)

    retire = subparsers.add_parser("retire", help="将证据确认的极差受管代理移入隔离区")
    retire.add_argument("--agent-id", required=True)

    restore = subparsers.add_parser("restore", help="显式恢复隔离代理")
    restore.add_argument("--agent-id", required=True)
    restore.add_argument("--confirm", required=True)
    restore.add_argument("--project-root", type=Path)

    subparsers.add_parser("recover", help="按持久化 intent 对账未完成的文件移动")

    doctor = subparsers.add_parser("doctor", help="只读检查状态和所有权冲突")
    doctor.add_argument("--project-root", type=Path)
    return parser


def normalize_uuid(value: str, label: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise LifecycleError(f"{label} 必须是 UUID") from exc


def dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    lifecycle = AgentLifecycle(arguments.codex_home, arguments.state_root)
    if arguments.command == "catalog":
        return lifecycle.catalog(arguments.project_root)
    if arguments.command == "create":
        return lifecycle.create_agent(load_bounded_json(arguments.spec), arguments.project_root)
    if arguments.command == "confirm-visible":
        return lifecycle.confirm_visible(normalize_uuid(arguments.agent_id, "agent_id"))
    if arguments.command == "lease-acquire":
        return lifecycle.acquire_lease(
            normalize_uuid(arguments.agent_id, "agent_id"), arguments.ttl_seconds
        )
    if arguments.command == "lease-release":
        return lifecycle.release_lease(arguments.lease_id)
    if arguments.command == "record":
        return lifecycle.record_evaluation(load_bounded_json(arguments.report))
    if arguments.command == "recommend-route":
        return lifecycle.recommend_route(
            normalize_uuid(arguments.agent_id, "agent_id"),
            arguments.task_class,
            arguments.risk_tier,
            arguments.execution_mode,
            arguments.service_tier,
        )
    if arguments.command == "stagnation-status":
        return lifecycle.stagnation_status(
            normalize_uuid(arguments.agent_id, "agent_id"),
            arguments.task_class,
            arguments.risk_tier,
        )
    if arguments.command == "variation-plan":
        return lifecycle.plan_variation(load_bounded_json(arguments.plan))
    if arguments.command == "variation-stage":
        return lifecycle.stage_variation(load_bounded_json(arguments.report))
    if arguments.command == "variation-verify":
        return lifecycle.verify_variation(load_bounded_json(arguments.report))
    if arguments.command == "promote":
        return lifecycle.promote_candidate(load_bounded_json(arguments.report))
    if arguments.command == "retire":
        return lifecycle.retire_agent(normalize_uuid(arguments.agent_id, "agent_id"))
    if arguments.command == "restore":
        return lifecycle.restore_agent(
            normalize_uuid(arguments.agent_id, "agent_id"),
            arguments.confirm,
            arguments.project_root,
        )
    if arguments.command == "recover":
        return lifecycle.recover()
    if arguments.command == "doctor":
        return lifecycle.doctor(arguments.project_root)
    raise LifecycleError(f"未知命令: {arguments.command}")


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        result = dispatch(arguments)
    except LifecycleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"生命周期数据库错误: {exc}"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
