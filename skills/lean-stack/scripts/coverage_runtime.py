"""Session-local coverage receipts for explicit sustained delegation."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import tempfile
import time
from typing import Any, Iterator

from _maintenance_lock import exclusive_lock


class CoverageError(RuntimeError):
    pass


class CoverageBusy(CoverageError):
    pass


Row = dict[str, Any]
ID = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
MARKER = re.compile(r"\[lean-work ([A-Za-z0-9_-]{1,32})/([A-Za-z0-9_-]{1,32})\]")
TASK_PATH = re.compile(r"/root(?:/[a-z0-9_-]+)+\Z")
WORK_STATES = {"ready", "running", "returned", "blocked", "done"}
BOARD_STATES = {"needs_plan", "active", "paused"}
MAX_BOARD_BYTES = 192 * 1024
MAX_INPUT_BYTES = 8 * 1024 * 1024
SCRIPT = Path(__file__).absolute()
# The native hook boundary concatenates configured namespaces and tool names.
WAIT_TOOLS = {"wait_agent", "collaboration.wait_agent", "collaborationwait_agent",
              "multi_agent_v1.wait_agent", "multi_agent_v1wait_agent"}
LOCAL_TOOLS = {"Bash", "exec_command", "apply_patch"} | WAIT_TOOLS
SPAWN_TOOLS = {"spawn_agent", "collaboration.spawn_agent", "collaborationspawn_agent"}
FOLLOWUP_TOOLS = {"followup_task", "collaboration.followup_task", "collaborationfollowup_task"}
LIST_TOOLS = {"list_agents", "collaboration.list_agents", "collaborationlist_agents"}

ACTIVATE = re.compile(
    r"^(?:请|现在|本轮|从现在起|接下来|继续|持续|一直|务必|还要|再|我们)?[，, ]*"
    r"(?:持续|一直|继续|每条主线(?:都)?|所有主线(?:都)?)"
    r"(?:逐线|并行|都|要|需要|必须|安排|仍|再|来|多|几名|多个|子)*"
    r"(?:派遣?|调用|启用|分派)(?:多个|更多|几名|子|不同的)*代理"
    r"(?:[，。！？,!?；;：:\s]|$)",
)
MORE_AGENTS = re.compile(r"^(?:请|还要)?(?:继续|持续|一直)(?:并行|多)?派(?:更多|多个|几个|子)*代理(?:[，。！？,!?；;：:\s]|$)")
PER_GOAL = re.compile(
    r"^(?:请)?(?:(?:[0-9一二三四五六七八九十百零〇两]+条|每条|所有)(?:未完成)?主线"
    r"(?:都|必须|要|需要|逐条|分别)*(?:持续|一直)(?:有|安排|保持)(?:实际工作的|在工作的|子)*代理|"
    r"按(?:[0-9一二三四五六七八九十百零〇两]+条|这[些几]条)?主线(?:表)?(?:每条|逐条)"
    r"(?:各)?(?:排|安排|派)(?:几个|多个|几名|若干)(?:子?代理)?[，,\s]*(?:继续|持续)(?:多排|多派))"
    r"(?=[，。！？,!?；;：:\s]|$)",
)
ACTIVATE_EN = re.compile(
    r"^(?:please\s+)?(?:keep\s+(?:dispatching|delegating to)|continue\s+(?:to dispatch|dispatching|delegating to))"
    r"\s+(?:more\s+|multiple\s+)?(?:sub[- ]?)?agents\b|"
    r"^(?:please\s+)?(?:dispatch|assign|delegate to)\s+(?:a\s+)?(?:sub[- ]?)?agents?"
    r"\s+(?:for|to)\s+(?:each|every)\s+(?:main\s+)?(?:goal|track|workstream)\b",
    re.I,
)
PAUSE = re.compile(
    r"^(?:(?:请)?(?:先)?(?:暂停|停止|取消)(?:继续|持续|所有|全部)*(?:子?代理)?"
    r"(?:多派|派遣|派发|调用)(?:子?代理)?|(?:本轮|现在)?不再(?:派|派遣|派发|调用)(?:任何|所有)?(?:子)?代理)"
    r"(?=[，。！？,!?；;：:\s]|$)|"
    r"^(?:请|先)?(?:暂停|停下|停止)(?=[，。！？,!?；;：:]|$)|"
    r"^(?:please\s+)?(?:pause|stop)(?:\s+(?:all\s+)?(?:dispatching|delegating to)\s+(?:sub[- ]?)?agents)?"
    r"(?=[,.!?;:]|$)",
    re.I,
)
RESUME = re.compile(
    r"^(?:请)?(?:继续|恢复)(?:原先的|原来的|原有的|之前的)?(?:持续|逐线)?(?:派遣|派发|多派)(?:子?代理)?"
    r"(?=[，。！？,!?；;：:\s]|$)|^(?:please\s+)?resume\s+(?:sustained|per-workstream)\s+delegation\b", re.I,
)


def object_value(value: Any, label: str) -> Row:
    if not isinstance(value, dict):
        raise CoverageError(f"{label} must be an object")
    return value


def text_value(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise CoverageError(f"{label} must be nonempty text of at most {limit} characters")
    if any(ord(char) < 32 for char in value) or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise CoverageError(f"{label} contains unsupported characters")
    return value.strip()


def row_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise CoverageError(f"{label} must be a stable identifier")
    return value


def fields(row: Row, allowed: set[str], label: str) -> None:
    if row.keys() - allowed:
        raise CoverageError(f"{label} contains unsupported fields")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def existing(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def plain(metadata: os.stat_result, *, directory: bool = False) -> bool:
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    return (expected(metadata.st_mode)
            and not (getattr(metadata, "st_file_attributes", 0) & 0x400)
            and (directory or metadata.st_nlink == 1))


def data_directory(value: str | None = None) -> Path:
    root = value or os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if not root:
        raise CoverageError("coverage data directory is unavailable; use the --data-dir from the hook context")
    return Path(text_value(root, "data directory", 4096)).expanduser().absolute()


def board_path(data: Path, session: str) -> Path:
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()
    return data / "coverage" / f"{digest}.json"


@contextmanager
def board_lock(path: Path, *, create: bool = False) -> Iterator[None]:
    if create:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    deadline = time.monotonic() + 1.5
    with ExitStack() as protection:
        while True:
            try:
                protection.enter_context(exclusive_lock(
                    path.with_suffix(".lock"), error_type=CoverageBusy, busy_message="coverage board is busy",
                ))
                break
            except CoverageBusy as exc:
                if str(exc) != "coverage board is busy" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.03)
        yield


def empty_board(session: str, cwd: str, status: str) -> Row:
    return {"version": 1, "session": session, "cwd": cwd, "status": status, "goals": []}


def read_board(path: Path, session: str) -> Row | None:
    parent = existing(path.parent)
    if parent is None:
        return None
    if not plain(parent, directory=True):
        raise CoverageError("coverage directory must be a plain directory")
    snapshot = existing(path)
    if snapshot is None:
        return None
    if not plain(snapshot) or snapshot.st_size > MAX_BOARD_BYTES:
        raise CoverageError("coverage board must be a bounded single-link file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not plain(opened) or not os.path.samestat(snapshot, opened):
            raise CoverageError("coverage board changed while opening")
        payload = stream.read(MAX_BOARD_BYTES + 1)
    try:
        if len(payload) > MAX_BOARD_BYTES:
            raise CoverageError("coverage board exceeds its size bound")
        board = object_value(json.loads(payload), "coverage board")
        validate_board(board, session)
    except (CoverageError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise CoverageError("coverage board is invalid and was preserved") from exc
    return board


def write_board(path: Path, board: Row) -> None:
    validate_board(board, board["session"])
    payload = json_bytes(board)
    if len(payload) > MAX_BOARD_BYTES:
        raise CoverageError("coverage board exceeds its size bound")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp", delete=False) as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(stream.name, path)


def validate_board(board: Row, session: str) -> None:
    fields(board, {"version", "session", "cwd", "status", "goals", "stop_fingerprint", "observations",
                   "list_issued", "list_applied"}, "coverage board")
    if board.get("version") != 1 or board.get("session") != session or board.get("status") not in BOARD_STATES:
        raise CoverageError("coverage board version, session or status is invalid")
    text_value(board.get("cwd"), "cwd", 4096)
    fingerprint = board.get("stop_fingerprint")
    if fingerprint is not None and (not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
        raise CoverageError("invalid Stop receipt")
    goals = board.get("goals")
    if not isinstance(goals, list):
        raise CoverageError("coverage goals must be a list")
    if board["status"] == "active" and not goals:
        raise CoverageError("an active coverage board must have a plan")
    observations = object_value(board.get("observations", {}), "pending agent lists")
    if len(observations) > 8:
        raise CoverageError("too many pending agent lists")
    issued, applied = board.get("list_issued", 0), board.get("list_applied", 0)
    if type(issued) is not int or type(applied) is not int or not 0 <= applied <= issued:
        raise CoverageError("invalid agent list ordering receipts")
    for call_id, entry in observations.items():
        text_value(call_id, "tool use ID", 256)
        observation = object_value(entry, "agent list snapshot")
        fields(observation, {"sequence", "turn_id", "fingerprint"}, "agent list snapshot")
        text_value(observation.get("turn_id"), "turn ID", 256)
        sequence = observation.get("sequence")
        fingerprint = observation.get("fingerprint")
        if type(sequence) is not int or not 1 <= sequence <= issued:
            raise CoverageError("invalid agent list snapshot ordering receipt")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise CoverageError("invalid agent list snapshot")
    goal_ids = set()
    task_paths = set()
    for entry in goals:
        goal = object_value(entry, "goal")
        fields(goal, {"id", "title", "delivered", "delivery_evidence", "work"}, "goal")
        goal_key = row_id(goal.get("id"), "goal id")
        if goal_key in goal_ids or not isinstance(goal.get("delivered"), bool):
            raise CoverageError("invalid or duplicate goal")
        goal_ids.add(goal_key)
        text_value(goal.get("title"), "goal title", 160)
        works = goal.get("work")
        if not isinstance(works, list) or not works:
            raise CoverageError("every goal needs a work package")
        work_ids = set()
        for entry in works:
            work = object_value(entry, "work")
            fields(work, {"id", "title", "status", "evidence", "blocker", "dispatch"}, "work")
            key = row_id(work.get("id"), "work id")
            status = work.get("status")
            if key in work_ids or status not in WORK_STATES:
                raise CoverageError("invalid or duplicate work")
            work_ids.add(key)
            text_value(work.get("title"), "work title", 160)
            if status in {"returned", "done", "blocked"} or "evidence" in work:
                text_value(work.get("evidence"), "work evidence", 420)
            if status == "blocked":
                text_value(work.get("blocker"), "work blocker", 240)
            elif "blocker" in work:
                raise CoverageError("a blocker belongs on blocked work")
            if status == "running" or "dispatch" in work:
                dispatch = object_value(work.get("dispatch"), "dispatch")
                task_path = validate_dispatch(dispatch)
                if status == "running":
                    if task_path in task_paths:
                        raise CoverageError("a live dispatch cannot cover multiple work packages")
                    task_paths.add(task_path)
        if goal["delivered"]:
            if any(work["status"] != "done" for work in works):
                raise CoverageError("delivered goal has unfinished work")
            text_value(goal.get("delivery_evidence"), "delivery evidence", 420)
        elif "delivery_evidence" in goal:
            raise CoverageError("delivery evidence belongs to delivered goals")
    if board["status"] == "needs_plan" and open_goals(board):
        raise CoverageError("a coverage board awaiting a plan cannot contain open goals")


def validate_dispatch(dispatch: Row) -> str:
    fields(dispatch, {"task_path", "tool_use_id", "agent_link", "verified_turn"}, "dispatch")
    task_path = dispatch.get("task_path")
    if not isinstance(task_path, str) or len(task_path) > 256 or not TASK_PATH.fullmatch(task_path):
        raise CoverageError("dispatch task path is invalid")
    text_value(dispatch.get("tool_use_id"), "tool use ID", 256)
    if dispatch.get("agent_link") not in {"unconfirmed", "needs_verify", "verified"}:
        raise CoverageError("dispatch observation state is invalid")
    if "verified_turn" in dispatch:
        if dispatch["agent_link"] != "verified":
            raise CoverageError("dispatch turn requires a verified observation")
        text_value(dispatch["verified_turn"], "verified turn ID", 256)
    return task_path


def plan_board(board: Row, request: Row, cwd: str) -> None:
    fields(request, {"goals"}, "plan")
    proposed = request.get("goals")
    if not isinstance(proposed, list) or not proposed:
        raise CoverageError("plan needs at least one goal")
    seen_goals = set()
    current = {goal["id"]: goal for goal in board["goals"]}
    for entry in proposed:
        row = object_value(entry, "goal")
        fields(row, {"id", "title", "work"}, "goal")
        key = row_id(row.get("id"), "goal id")
        title = text_value(row.get("title"), "goal title", 160)
        if key in seen_goals:
            raise CoverageError("duplicate goal in plan")
        seen_goals.add(key)
        goal = current.get(key)
        if goal is None:
            goal = {"id": key, "title": title, "delivered": False, "work": []}
            board["goals"].append(goal)
        elif goal["title"] != title:
            raise CoverageError("existing goal IDs keep their title; use a new ID for a distinct goal")
        merge_work(goal, row.get("work"))
    board["cwd"] = cwd
    if board["status"] == "needs_plan":
        if not open_goals(board):
            raise CoverageError("new coverage needs at least one undelivered goal")
        board["status"] = "active"


def merge_work(goal: Row, proposed: Any) -> None:
    if not isinstance(proposed, list) or not proposed:
        raise CoverageError("every goal needs a work package")
    current = {work["id"]: work for work in goal["work"]}
    seen = set()
    for entry in proposed:
        row = object_value(entry, "work")
        fields(row, {"id", "title"}, "work")
        key = row_id(row.get("id"), "work id")
        title = text_value(row.get("title"), "work title", 160)
        if key in seen:
            raise CoverageError("duplicate work in plan")
        seen.add(key)
        if key in current:
            if current[key]["title"] != title:
                raise CoverageError("existing work IDs keep their title; use a new ID for distinct work")
            continue
        if goal["delivered"]:
            raise CoverageError("a delivered goal cannot receive new work")
        goal["work"].append({"id": key, "title": title, "status": "ready"})


def set_paused(board: Row, paused: bool) -> None:
    if paused:
        status = "paused"
    else:
        status = "active" if open_goals(board) else "needs_plan"
    if board["status"] != status:
        if board["status"] == "paused":
            for _, work in pending_work(board):
                if work["status"] == "running":
                    work["dispatch"]["agent_link"] = "needs_verify"
                    work["dispatch"].pop("verified_turn", None)
            board.pop("observations", None)
        board["status"] = status
        board.pop("stop_fingerprint", None)


def find_goal(board: Row, key: str) -> Row | None:
    return next((goal for goal in board["goals"] if goal["id"] == key), None)


def find_work(goal: Row, key: str) -> Row | None:
    return next((work for work in goal["work"] if work["id"] == key), None)


def update_board(board: Row, request: Row) -> None:
    fields(request, {"action", "goal", "work", "evidence", "blocker", "task_path", "state", "turn_id"}, "update")
    action = request.get("action")
    if action in ("pause", "resume"):
        fields(request, {"action"}, "pause or resume")
        set_paused(board, action == "pause")
        return
    goal = find_goal(board, row_id(request.get("goal"), "goal id"))
    if goal is None:
        raise CoverageError("goal is missing")
    evidence = text_value(request.get("evidence"), "evidence", 420)
    if action == "deliver":
        fields(request, {"action", "goal", "evidence"}, "deliver")
        if any(work["status"] != "done" for work in goal["work"]):
            raise CoverageError("goal delivery requires explicit acceptance of all its work")
        if not goal["delivered"]:
            goal.update(delivered=True, delivery_evidence=evidence)
        return
    work = find_work(goal, row_id(request.get("work"), "work id"))
    if work is None or goal["delivered"]:
        raise CoverageError("work is missing or its goal was already delivered")
    status = work["status"]
    if action == "block" and status in {"ready", "running", "returned", "blocked"}:
        fields(request, {"action", "goal", "work", "evidence", "blocker"}, "block")
        blocker = text_value(request.get("blocker"), "blocker", 240)
        work.update(status="blocked", evidence=evidence, blocker=blocker)
    elif action == "verify" and status == "running":
        fields(request, {"action", "goal", "work", "evidence", "task_path", "state", "turn_id"}, "verify")
        dispatch = work["dispatch"]
        state = request.get("state")
        if request.get("task_path") != dispatch["task_path"] or state not in ("running", "returned"):
            raise CoverageError("verify requires the exact dispatched task path and observed running or returned state")
        work.update(status=state, evidence=evidence)
        dispatch["agent_link"] = "verified"
        if state == "running":
            dispatch["verified_turn"] = text_value(request.get("turn_id"), "current parent turn ID", 256)
        else:
            dispatch.pop("verified_turn", None)
        board.pop("observations", None)
    elif action == "accept" and status == "returned":
        fields(request, {"action", "goal", "work", "evidence"}, "accept")
        work.update(status="done", evidence=evidence)
    elif action == "retry" and status in {"running", "returned", "blocked"}:
        fields(request, {"action", "goal", "work", "evidence"}, "retry")
        work.update(status="ready", evidence=evidence)
        work.pop("blocker", None)
        work.pop("dispatch", None)
    else:
        raise CoverageError("update action is incompatible with the work state")


def parse_file(path: Path) -> Row:
    with path.open("rb") as stream:
        data = stream.read(MAX_BOARD_BYTES + 1)
    if len(data) > MAX_BOARD_BYTES:
        raise CoverageError("input exceeds the board size limit")
    return object_value(json.loads(data.decode("utf-8-sig")), "CLI input")


def cli(args: argparse.Namespace) -> Row:
    session = text_value(args.session, "session id", 256)
    path = board_path(data_directory(args.data_dir), session)
    if args.command == "status":
        if existing(path) is None:
            return {"status": "inactive"}
        with board_lock(path):
            return read_board(path, session) or {"status": "inactive"}
    if args.json is not None:
        if len(args.json.encode("utf-8")) > MAX_BOARD_BYTES:
            raise CoverageError("input exceeds the board size limit")
        request = object_value(json.loads(args.json), "CLI input")
    else:
        request = parse_file(args.input)
    cwd = text_value(args.cwd, "cwd", 4096) if args.command == "plan" else None
    with board_lock(path, create=args.command == "plan"):
        previous = read_board(path, session)
        if args.command == "plan":
            board = deepcopy(previous) if previous else empty_board(session, cwd, "needs_plan")
            plan_board(board, request, cwd)
        else:
            if previous is None:
                raise CoverageError("no coverage board for this session")
            board = deepcopy(previous)
            update_board(board, request)
        if board != previous:
            write_board(path, board)
    return board


def quote(argument: str) -> str:
    if os.name == "nt":
        return "'" + argument.replace("'", "''") + "'"
    return shlex.quote(argument)


def cli_command(board: Row, data: Path, action: str) -> str:
    launcher = "py -3 -X utf8 -B" if os.name == "nt" else "python3 -B"
    command = f"{launcher} {quote(str(SCRIPT))} {action} --session {quote(board['session'])} --data-dir {quote(str(data))}"
    if action == "plan":
        command += f" --cwd {quote(board['cwd'])} --input {quote('plan.json')}"
    return command


SHELL_TOKEN = r"(?:'(?:''|[^'\r\n])*'|\"[^\"\r\n]*\"|[^\s'\";&|<>`]+)"
CLI_PATTERN = re.compile(
    r"^\s*(?:py(?:\.exe)?\s+-3|python3?(?:\.exe)?)(?:\s+-X\s+utf8)?(?:\s+-B)?\s+"
    rf"(?P<script>{SHELL_TOKEN})\s+(?:plan|status|update)(?:\s+{SHELL_TOKEN})+\s*$",
    re.I,
)


def own_cli(tool_input: Any) -> bool:
    if not isinstance(tool_input, dict):
        return False
    command = tool_input.get("command", tool_input.get("cmd"))
    if not isinstance(command, str) or "\n" in command or "\r" in command:
        return False
    match = CLI_PATTERN.fullmatch(command)
    if match is None:
        return False
    script = match.group("script")
    if script[0] in {"'", '"'}:
        script = script[1:-1].replace("''", "'")
    return os.path.normcase(os.path.normpath(script)) == os.path.normcase(str(SCRIPT))


def open_goals(board: Row) -> list[Row]:
    return [goal for goal in board["goals"] if not goal["delivered"]]


def pending_work(board: Row) -> Iterator[tuple[Row, Row]]:
    for goal in open_goals(board):
        for work in goal["work"]:
            yield goal, work


def summary(board: Row) -> str:
    groups = []
    goals = open_goals(board)
    labels = {"ready": "待派", "running": "已派", "needs_verify": "待核对", "returned": "待采用",
              "blocked": "阻断", "done": "已验"}
    for goal in goals:
        statuses = {key: 0 for key in ("ready", "running", "needs_verify", "returned", "blocked", "done")}
        for work in goal["work"]:
            key = work["status"]
            if key == "running" and work["dispatch"]["agent_link"] != "verified":
                key = "needs_verify"
            statuses[key] += 1
        counts = "/".join(f"{labels[key]}{count}" for key, count in statuses.items() if count)
        groups.append((goal["id"], goal["title"], counts))
    detailed = "、".join(f"{key} {title[:16]}({counts})" for key, title, counts in groups)
    if len(detailed) <= 1150:
        return detailed
    compact = "、".join(f"{key}({counts})" for key, _, counts in groups)
    if len(compact) <= 1150:
        return compact
    goal_ids = "、".join(goal["id"] for goal in goals)
    return goal_ids if len(goal_ids) <= 1150 else f"{len(goals)} 条，完整列表见状态命令"


def context(event: str, message: str) -> Row:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}


def plan_context(board: Row, data: Path) -> str:
    return (
        "用户已明确要求持续派遣。先按原始要求整理全部仍待交付主线及可独立派遣工作包，"
        "以 {\"goals\":[{\"id\":\"G01\",\"title\":\"主线\",\"work\":[{\"id\":\"W01\",\"title\":\"工作包\"}]}]}"
        f" 写入 plan.json 后登记。命令：{cli_command(board, data, 'plan')}。"
        "派遣消息需包含 [lean-work G01/W01]。"
    )


def recovery_context(board: Row, data: Path, event: str) -> Row:
    if board["status"] == "needs_plan":
        return context(event, plan_context(board, data))
    if not open_goals(board) and board["status"] != "paused":
        return {}
    prefix = "持续派遣已暂停。" if board["status"] == "paused" else "逐线覆盖工作表仍有未交付项。"
    return context(event, f"{prefix}{summary(board)}。完整状态：{cli_command(board, data, 'status')}")


def stop(board: Row, data: Path) -> Row:
    if board["status"] == "paused":
        return {}
    pending = open_goals(board)
    if board["status"] == "needs_plan":
        reason = plan_context(board, data)
        blocked_only = False
    elif not pending:
        return {}
    else:
        reason = (
            f"下列主线尚未交付：{summary(board)}。{cli_command(board, data, 'status')}。"
            "按工作包补派、核对原生代理结果或记录具体阻断，再按整条主线验收；"
            "仅在验收完成后写交付收据。最终答复应明确剩余主线和证据缺口。"
        )
        blocked_only = all(
            all(work["status"] in {"blocked", "done"} for work in goal["work"])
            and any(work["status"] == "blocked" for work in goal["work"])
            for goal in pending
        )
    work_states = [(goal["id"], work["id"], work["status"]) for goal, work in pending_work(board)]
    fingerprint = hashlib.sha256(json_bytes({"status": board["status"], "work": work_states})).hexdigest()
    if blocked_only or board.get("stop_fingerprint") == fingerprint:
        return {"systemMessage": f"逐线覆盖未完成。{reason}"}
    board["stop_fingerprint"] = fingerprint
    return {"decision": "block", "reason": reason}


def tagged_work(board: Row, arguments: Row, *, spawn: bool) -> tuple[Row, Row] | None:
    possible_keys = ("message", "task_message", "task") if spawn else ("message",)
    message = next((arguments[key] for key in possible_keys if isinstance(arguments.get(key), str)), "")
    markers = set(MARKER.findall(message))
    if len(markers) != 1:
        return None
    goal_key, work_key = next(iter(markers))
    goal = find_goal(board, goal_key)
    if goal is None or goal["delivered"]:
        return None
    work = find_work(goal, work_key)
    return (goal, work) if work is not None and work["status"] == "ready" else None


def event_id(event: Row, key: str) -> str | None:
    value = event.get(key)
    return text_value(value, key, 256) if isinstance(value, str) and value else None


def dispatch_fingerprint(board: Row) -> str | None:
    candidates = [(work["dispatch"]["task_path"], work["dispatch"]["tool_use_id"])
                  for _, work in pending_work(board) if work["status"] == "running"]
    return hashlib.sha256(json_bytes(candidates)).hexdigest() if candidates else None


def prepare_agent_list(board: Row, event: Row) -> None:
    call_id = event_id(event, "tool_use_id")
    turn_id = event_id(event, "turn_id")
    fingerprint = dispatch_fingerprint(board)
    if not call_id or not turn_id or fingerprint is None:
        return
    observations = board.setdefault("observations", {})
    if call_id in observations:
        return
    if len(observations) == 8:
        oldest_call = min(observations, key=lambda key: observations[key]["sequence"])
        observations.pop(oldest_call)
    sequence = board.get("list_issued", 0) + 1
    board["list_issued"] = sequence
    observations[call_id] = {"sequence": sequence, "turn_id": turn_id, "fingerprint": fingerprint}


def observe_agent_list(board: Row, event: Row) -> None:
    call_id = event_id(event, "tool_use_id")
    turn_id = event_id(event, "turn_id")
    snapshot = board.get("observations", {}).get(call_id)
    if snapshot is None or snapshot["turn_id"] != turn_id:
        return
    board["observations"].pop(call_id)
    if board.get("observations") == {}:
        board.pop("observations")
    response = event.get("tool_response")
    if (snapshot["sequence"] <= board.get("list_applied", 0)
            or snapshot["fingerprint"] != dispatch_fingerprint(board) or not isinstance(response, str)):
        return
    try:
        result = json.loads(response)
    except ValueError:
        return
    if not isinstance(result, dict) or result.keys() != {"agents"} or not isinstance(result["agents"], list):
        return
    arguments = event.get("tool_input")
    full_list = isinstance(arguments, dict) and arguments.get("path_prefix") is None
    statuses = {}
    for agent in result["agents"]:
        if not isinstance(agent, dict) or agent.keys() != {"agent_name", "agent_status"}:
            return
        path = agent["agent_name"]
        if not isinstance(path, str) or path in statuses:
            return
        statuses[path] = agent["agent_status"]
    board["list_applied"] = snapshot["sequence"]
    for _, work in pending_work(board):
        if work["status"] != "running":
            continue
        dispatch = work["dispatch"]
        path = dispatch["task_path"]
        state = statuses.get(path)
        if state == "running":
            dispatch.update(agent_link="verified", verified_turn=turn_id)
        elif isinstance(state, dict) and state.keys() == {"completed"} and isinstance(state["completed"], str) and state["completed"].strip():
            dispatch["agent_link"] = "verified"
            dispatch.pop("verified_turn", None)
            work.update(status="returned", evidence=f"Native list_agents {call_id}: {path} returned a final result"[:420])
        elif path in statuses or full_list:
            dispatch["agent_link"] = "needs_verify"
            dispatch.pop("verified_turn", None)


def success_path(response: Any) -> str | None:
    if not isinstance(response, str) or len(response) > 1024:
        return None
    try:
        result = json.loads(response)
    except ValueError:
        return None
    if not isinstance(result, dict) or result.keys() - {"task_name", "nickname"}:
        return None
    task_path = result.get("task_name")
    return task_path if isinstance(task_path, str) and len(task_path) <= 256 and TASK_PATH.fullmatch(task_path) else None


def followup_path(response: Any, target: Any) -> str | None:
    if response != "" or not isinstance(target, str) or len(target) > 256:
        return None
    return target if TASK_PATH.fullmatch(target) else None


def register_dispatch(board: Row, event: Row, *, spawn: bool) -> None:
    call_id = event_id(event, "tool_use_id")
    if not call_id:
        return
    arguments = event.get("tool_input")
    if not isinstance(arguments, dict):
        return
    selected = tagged_work(board, arguments, spawn=spawn)
    if selected is None:
        return
    _, work = selected
    response = event.get("tool_response")
    task_path = success_path(response) if spawn else followup_path(response, arguments.get("target"))
    if not task_path:
        return
    for _, other in pending_work(board):
        if other["status"] == "running" and other["dispatch"]["task_path"] == task_path:
            return
    dispatch = {"task_path": task_path, "tool_use_id": call_id, "agent_link": "unconfirmed"}
    work.update(status="running", dispatch=dispatch)
    work.pop("evidence", None)


def pre_tool(board: Row, data: Path, event: Row, name: str) -> Row:
    arguments = event.get("tool_input")
    dispatch = name in SPAWN_TOOLS | FOLLOWUP_TOOLS
    if not dispatch and (name not in LOCAL_TOOLS or own_cli(arguments)):
        return {}
    if dispatch and isinstance(arguments, dict) and tagged_work(board, arguments, spawn=name in SPAWN_TOOLS):
        return {}
    ready = [f"{goal['id']}/{work['id']}" for goal, work in pending_work(board) if work["status"] == "ready"]
    status_command = cli_command(board, data, "status")
    update_command = cli_command(board, data, "update")
    if dispatch:
        if ready:
            reason = ("派遣前必须从当前覆盖表选择一个待派工作包，把该包对应的标记放进任务消息，"
                      f"例如 [lean-work {ready[0]}]，每次调用对应一个包。")
        else:
            reason = ("当前覆盖表没有待派工作包。先核对已派状态、验收已返回结果，"
                      "或根据实际证据登记重试及新工作包。")
    elif ready:
        packages = "、".join(ready[:8]) + (f" 等共 {len(ready)} 项" if len(ready) > 8 else "")
        reason = (f"已登记的可独立派遣工作包仍待派：{packages}。"
                  "先派遣并带 [lean-work G01/W01] 标记，或登记有证据的具体阻断。")
    elif name in WAIT_TOOLS:
        running = [(goal, work) for goal, work in pending_work(board) if work["status"] == "running"]
        if not running:
            reason = ("当前覆盖表没有正在执行的工作包。先验收已返回的结果，接续就绪工作或写入交付收据。"
                      "只剩有证据的阻断时，说明剩余缺口。")
        else:
            turn_id = event_id(event, "turn_id")
            unverified = [f"{goal['id']}/{work['id']}" for goal, work in running
                          if turn_id is None or work["dispatch"].get("verified_turn") != turn_id]
            if not unverified:
                for _, work in running:
                    work["dispatch"]["agent_link"] = "unconfirmed"
                    work["dispatch"].pop("verified_turn", None)
                return {}
            packages = "、".join(unverified[:8]) + (f" 等共 {len(unverified)} 项" if len(unverified) > 8 else "")
            receipt = f"；运行核对需登记 turn_id {turn_id}" if turn_id else ""
            reason = (f"等待前先在当前父级轮次用原生 list_agents 核对以下实际任务路径：{packages}。"
                      f"宿主回执未自动入表时，使用 verify 登记同一路径和实际状态{receipt}。"
                      "已返回的结果按工作包验收，失效的派遣按证据接续或记录阻断。")
    else:
        return {}
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": (f"{reason}完整状态：{status_command}。"
                                     f"登记时可直接执行 {update_command} --json 'JSON 对象'。"),
    }}


def hook(event: Row) -> Row:
    kind = event.get("hook_event_name")
    tool_name = event.get("tool_name", "")
    if kind not in {"UserPromptSubmit", "SessionStart", "Stop", "Interrupt", "PreToolUse", "PostToolUse"}:
        return {}
    if event.get("agent_id") or event.get("agent_type"):
        return {}
    if not isinstance(tool_name, str):
        return {}
    if kind == "PreToolUse" and tool_name not in LOCAL_TOOLS | LIST_TOOLS | SPAWN_TOOLS | FOLLOWUP_TOOLS:
        return {}
    if kind == "PostToolUse" and tool_name not in SPAWN_TOOLS | FOLLOWUP_TOOLS | LIST_TOOLS:
        return {}
    session = text_value(event.get("session_id"), "session id", 256)
    data = data_directory()
    path = board_path(data, session)
    prompt = event.get("prompt")
    activate = kind == "UserPromptSubmit" and isinstance(prompt, str) and any(
        pattern.search(prompt.strip()) for pattern in (ACTIVATE, MORE_AGENTS, PER_GOAL, ACTIVATE_EN)
    )
    if existing(path) is None and not activate:
        return {}
    if kind == "SessionStart":
        with board_lock(path):
            board = read_board(path, session)
        return recovery_context(board, data, kind) if board else {}
    with board_lock(path, create=activate):
        previous = read_board(path, session)
        if previous is None and not activate:
            return {}
        board = deepcopy(previous) if previous else empty_board(
            session, text_value(event.get("cwd"), "cwd", 4096), "needs_plan",
        )
        output = apply_event(board, data, event, kind, tool_name, activate)
        if board != previous:
            write_board(path, board)
    return output


def apply_event(board: Row, data: Path, event: Row, kind: str, tool_name: str, activate: bool) -> Row:
    if kind == "UserPromptSubmit":
        prompt = event.get("prompt")
        if (board["status"] != "active" or open_goals(board)) and isinstance(prompt, str) and PAUSE.search(prompt.strip()):
            set_paused(board, True)
            return recovery_context(board, data, kind)
        if activate or (board["status"] == "paused" and isinstance(prompt, str) and RESUME.search(prompt.strip())):
            set_paused(board, False)
            if activate:
                board.pop("stop_fingerprint", None)
            return recovery_context(board, data, kind)
    elif kind == "Interrupt":
        if board["status"] != "active" or open_goals(board):
            set_paused(board, True)
    elif kind == "Stop":
        return stop(board, data)
    elif not open_goals(board):
        return {}
    elif tool_name in LIST_TOOLS:
        if kind == "PreToolUse":
            prepare_agent_list(board, event)
        elif kind == "PostToolUse":
            observe_agent_list(board, event)
    elif board["status"] == "active":
        if kind == "PreToolUse":
            return pre_tool(board, data, event, tool_name)
        if kind == "PostToolUse":
            register_dispatch(board, event, spawn=tool_name in SPAWN_TOOLS)
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hook")
    for action in ("plan", "status", "update"):
        command = commands.add_parser(action)
        command.add_argument("--session", required=True)
        command.add_argument("--data-dir")
        if action == "plan":
            command.add_argument("--cwd", required=True)
        if action in {"plan", "update"}:
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument("--input", type=Path)
            source.add_argument("--json", help="single-line JSON without a temporary input file")
    args = parser.parse_args()
    event_name = "hook"
    try:
        if args.command == "hook":
            payload = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
            if len(payload) > MAX_INPUT_BYTES:
                raise CoverageError("hook input exceeds its size limit")
            event = object_value(json.loads(payload), "hook input")
            reported_name = event.get("hook_event_name")
            if isinstance(reported_name, str) and reported_name.isascii() and reported_name.isalpha():
                event_name = reported_name[:32]
            result = hook(event)
        else:
            result = cli(args)
    except (CoverageError, OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        if args.command == "hook":
            detail = str(exc) if isinstance(exc, CoverageError) else "unable to process the hook input or coverage file"
            result = {"systemMessage": f"逐线覆盖守卫未处理 {event_name}：{detail}。"}
        else:
            print(f"coverage: {exc}", file=sys.stderr)
            return 1
    sys.stdout.buffer.write(json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
