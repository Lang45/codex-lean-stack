"""Process-level contracts for the opt-in dispatch coverage guard."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "lean-stack" / "scripts" / "coverage_runtime.py"


class CoverageRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        # Keep receipts and state outside the repository for failure diagnosis.
        self.workspace = Path(tempfile.mkdtemp(prefix="lean-coverage-contract-"))
        self.plugin_data = self.workspace / "plugin data"
        self.session = str(uuid.uuid4())
        self.turn = str(uuid.uuid4())
        self.env = {**os.environ, "PLUGIN_DATA": str(self.plugin_data)}

    def invoke(self, *args: str, payload: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-B", str(SCRIPT), *args],
            cwd=self.workspace,
            env=self.env,
            input=json.dumps(payload) if payload is not None else "",
            capture_output=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )

    def successful(self, *args: str, payload: dict | None = None) -> dict:
        result = self.invoke(*args, payload=payload)
        self.assertEqual(result.returncode, 0, (args, result.stdout, result.stderr, self.workspace))
        output = json.loads(result.stdout) if result.stdout.strip() else {}
        self.assertIsInstance(output, dict)
        return output

    def input_file(self, name: str, payload: dict) -> str:
        path = self.workspace / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def plan(self, goals: list[dict], *, session: str | None = None) -> dict:
        source = self.input_file("plan.json", {"goals": goals})
        return self.successful(
            "plan", "--session", session or self.session, "--cwd", str(self.workspace), "--input", source,
        )

    def update(self, action: str, **fields: str) -> dict:
        source = self.input_file(f"{action}.json", {"action": action, **fields})
        return self.successful("update", "--session", self.session, "--input", source)

    def status(self, *, session: str | None = None) -> dict:
        return self.successful("status", "--session", session or self.session)

    def hook(self, event: str, *, session: str | None = None, **fields: object) -> dict:
        return self.successful(
            "hook",
            payload={
                "hook_event_name": event,
                "session_id": session or self.session,
                "turn_id": self.turn,
                "cwd": str(self.workspace),
                **fields,
            },
        )

    def table_path(self, *, session: str | None = None) -> Path:
        session_hash = hashlib.sha256((session or self.session).encode("utf-8")).hexdigest()
        return self.plugin_data / "coverage" / f"{session_hash}.json"

    @staticmethod
    def goals(count: int = 13) -> list[dict]:
        return [
            {
                "id": f"G{index:02d}",
                "title": f"主线 {index:02d} 的完整结果",
                "work": [{"id": "W01", "title": "可独立执行并验收的工作包"}],
            }
            for index in range(1, count + 1)
        ]

    def work_status(self, goal: str = "G01", work: str = "W01") -> str:
        goals = self.status()["goals"]
        selected = next(item for item in goals if item["id"] == goal)
        return next(item["status"] for item in selected["work"] if item["id"] == work)

    @staticmethod
    def permission(output: dict) -> str | None:
        return output.get("hookSpecificOutput", {}).get("permissionDecision")

    def observe_agents(self, *agents: tuple[str, str | dict], tool_name: str = "collaboration.list_agents") -> dict:
        response = json.dumps({"agents": [
            {"agent_name": name, "agent_status": status} for name, status in agents
        ]})
        call = {"tool_name": tool_name, "tool_input": {}, "tool_use_id": f"call-list-{uuid.uuid4()}"}
        opened = self.hook("PreToolUse", **call)
        self.assertNotEqual(self.permission(opened), "deny", opened)
        return self.hook("PostToolUse", **call, tool_response=response)

    def test_explicit_coverage_request_marks_the_session_for_a_plan(self) -> None:
        for prompt, count in (
            ("十三条未完成主线必须逐条持续有实际工作的代理，直到该条完成并交付才退出派遣。", 13),
            ("按14条主线表每条排几个，持续多排。", 14),
            ("每条主线持续有代理，直到该条交付。", 13),
        ):
            with self.subTest(prompt=prompt):
                self.session = str(uuid.uuid4())
                self.hook("UserPromptSubmit", prompt=prompt)
                self.assertEqual(self.status()["status"], "needs_plan")
                self.assertTrue(self.table_path().is_file())
                self.plan(self.goals(count))
                self.assertEqual(len(self.status()["goals"]), count)

    def test_ready_unassigned_work_blocks_wait_and_local_work(self) -> None:
        self.plan(self.goals())
        for name, args in (
            ("collaboration.wait_agent", {"timeout_ms": 10000}),
            ("Bash", {"command": "git status --short"}),
            ("exec_command", {"cmd": "git status --short"}),
        ):
            with self.subTest(tool=name):
                output = self.hook("PreToolUse", tool_name=name, tool_input=args)
                self.assertEqual(self.permission(output), "deny", output)
                self.assertEqual(output["hookSpecificOutput"].get("hookEventName"), "PreToolUse")

        status_args = f'status --session {self.session} --data-dir "{self.plugin_data}"'
        for script, permitted in ((SCRIPT, True), (self.workspace / SCRIPT.name, False)):
            with self.subTest(script=script):
                command = f'py -3 -X utf8 -B "{script}" {status_args}'
                output = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": command})
                self.assertEqual(self.permission(output) != "deny", permitted, output)

        request = json.dumps({
            "action": "block", "goal": "G01", "work": "W01",
            "blocker": "还未取得权限。", "evidence": "当前任务授权记录。",
        })
        args = f'update --session {self.session} --data-dir "{self.plugin_data}" --json \'{request}\''
        output = self.hook("PreToolUse", tool_name="Bash", tool_input={
            "command": f'py -3 -X utf8 -B "{SCRIPT}" {args}',
        })
        self.assertNotEqual(self.permission(output), "deny", output)
        self.successful("update", "--session", self.session, "--data-dir", str(self.plugin_data), "--json", request)
        self.assertEqual(self.work_status(), "blocked")

    def test_active_dispatch_requires_an_unambiguous_ready_work_marker(self) -> None:
        tools = (
            ("collaborationspawn_agent", {"task_name": "worker"}),
            ("collaborationfollowup_task", {"target": "/root/worker"}),
        )

        def dispatch(tool: str, arguments: dict, message: str) -> dict:
            return self.hook(
                "PreToolUse", tool_name=tool, tool_use_id=f"call-marker-{uuid.uuid4()}",
                tool_input={**arguments, "message": message},
            )

        for tool, arguments in tools:
            unrestricted = dispatch(tool, arguments, "执行当前工作。")
            self.assertNotEqual(self.permission(unrestricted), "deny", unrestricted)
        self.assertFalse(self.table_path().exists())

        self.plan(self.goals(2))
        self.update("block", goal="G02", work="W01", blocker="输入未就绪。", evidence="当前输入清单。")
        for tool, arguments in tools:
            for message in (
                "执行当前工作。",
                "[lean-work G03/W01] 执行表外工作。",
                "[lean-work G02/W01] 执行尚未就绪的工作。",
                "[lean-work G01/W01] [lean-work G02/W01] 同时执行两项。",
            ):
                with self.subTest(tool=tool, message=message):
                    denied = dispatch(tool, arguments, message)
                    self.assertEqual(self.permission(denied), "deny", denied)
                    reason = denied["hookSpecificOutput"]["permissionDecisionReason"]
                    self.assertRegex(reason, r"\[lean-work [A-Za-z0-9_-]+/[A-Za-z0-9_-]+\]")
            permitted = dispatch(tool, arguments, "[lean-work G01/W01] 执行当前就绪工作。")
            self.assertNotEqual(self.permission(permitted), "deny", permitted)
        self.assertEqual(self.work_status(), "ready")

        self.hook("UserPromptSubmit", prompt="本轮不再派任何子代理，先只说明当前证据。")
        self.assertEqual(self.status()["status"], "paused")
        for tool, arguments in tools:
            unrestricted = dispatch(tool, arguments, "执行当前工作。")
            self.assertNotEqual(self.permission(unrestricted), "deny", unrestricted)

    def test_native_dispatch_failure_does_not_cover_a_work_package(self) -> None:
        self.plan(self.goals(1))
        call = {
            "tool_name": "collaboration.spawn_agent",
            "tool_use_id": "call-failed-spawn",
            "tool_input": {"agent_type": "worker", "message": "[lean-work G01/W01] 完成指定工作包。"},
        }
        attempt = self.hook("PreToolUse", **call)
        self.assertNotEqual(self.permission(attempt), "deny", attempt)
        self.hook("PostToolUse", **call, tool_response="Error: agent limit reached")
        self.assertEqual(self.work_status(), "ready")
        wait = self.hook("PreToolUse", tool_name="collaboration.wait_agent", tool_input={})
        self.assertEqual(self.permission(wait), "deny", wait)

        retry = {**call, "tool_use_id": "call-retry"}
        self.hook("PreToolUse", **retry)
        self.hook("PostToolUse", **retry, tool_response='{"task_name":"/root/retry","nickname":"retry"}')
        dispatch = self.status()["goals"][0]["work"][0]["dispatch"]
        self.assertEqual(dispatch["task_path"], "/root/retry")
        self.assertIsNone(dispatch.get("agent_id"))

    def test_native_child_session_requires_parent_roster_verification_before_wait(self) -> None:
        self.plan(self.goals(1))
        spawn = {
            "tool_name": "collaboration.spawn_agent",
            "tool_use_id": "call-parent-turn",
            "tool_input": {"agent_type": "worker", "message": "[lean-work G01/W01] 执行工作包。"},
        }
        child = {"agent_id": str(uuid.uuid4()), "agent_type": "worker", "turn_id": str(uuid.uuid4())}
        child_session = str(uuid.uuid4())
        self.hook("PreToolUse", **spawn)
        self.hook("SubagentStart", session=child_session, **child)
        self.hook("PostToolUse", **spawn, tool_response='{"task_name":"/root/worker","nickname":"worker"}')
        self.hook("SubagentStop", session=child_session, **child, stop_hook_active=False)

        work = self.status()["goals"][0]["work"][0]
        self.assertIsNone(work["dispatch"].get("agent_id"))
        self.assertNotIn(work["status"], {"returned", "done"})
        self.assertFalse(self.table_path(session=child_session).exists())
        wait_tool = {"tool_name": "collaboration.wait_agent", "tool_input": {}}
        wait = self.hook("PreToolUse", **wait_tool)
        self.assertEqual(self.permission(wait), "deny", wait)
        roster = self.hook("PreToolUse", tool_name="collaboration.list_agents", tool_input={})
        self.assertNotEqual(self.permission(roster), "deny", roster)
        self.observe_agents(("/root/worker", "unrecognized-state"), ("/root/other", "running"))
        still_waiting = self.hook("PreToolUse", **wait_tool)
        self.assertEqual(self.permission(still_waiting), "deny", still_waiting)

        self.observe_agents(("/root/worker", "running"))
        self.assertEqual(self.work_status(), "running")
        admitted = self.hook("PreToolUse", **wait_tool)
        self.assertNotEqual(self.permission(admitted), "deny", admitted)
        stale = self.hook("PreToolUse", **wait_tool)
        self.assertEqual(self.permission(stale), "deny", stale)

        self.hook("Interrupt")
        self.assertEqual(self.status()["status"], "paused")
        self.observe_agents(
            ("/root/worker", {"completed": "实际工作包已返回，等父验收。"}), tool_name="list_agents",
        )
        self.assertEqual(self.work_status(), "returned")
        self.update("resume")
        self.assertEqual(self.work_status(), "returned")
        self.assertFalse(self.status()["goals"][0]["delivered"])

    def test_returned_work_blocks_wait_when_no_agent_is_running(self) -> None:
        self.plan(self.goals(1))
        self.hook(
            "PostToolUse", tool_name="collaboration.spawn_agent", tool_use_id="call-returned",
            tool_input={"message": "[lean-work G01/W01] 执行工作包。"},
            tool_response='{"task_name":"/root/worker","nickname":"worker"}',
        )
        self.observe_agents(("/root/worker", {"completed": "工作包已返回。"}))
        self.assertEqual(self.work_status(), "returned")

        wait = self.hook("PreToolUse", tool_name="collaboration.wait_agent", tool_input={})
        self.assertEqual(self.permission(wait), "deny", wait)
        self.assertRegex(wait["hookSpecificOutput"]["permissionDecisionReason"], r"采用|验收|交付")

    def test_late_and_prior_turn_rosters_cannot_authorize_wait(self) -> None:
        self.plan(self.goals(1))
        self.hook(
            "PostToolUse", tool_name="collaboration.spawn_agent", tool_use_id="call-roster-order",
            tool_input={"message": "[lean-work G01/W01] 执行工作包。"},
            tool_response='{"task_name":"/root/worker","nickname":"worker"}',
        )
        list_tool = {"tool_name": "collaboration.list_agents", "tool_input": {}}
        older = {**list_tool, "tool_use_id": "call-list-1"}
        newer = {**list_tool, "tool_use_id": "call-list-2"}
        self.hook("PreToolUse", **older)
        self.hook("PreToolUse", **newer)
        self.hook("PostToolUse", **newer, tool_response='{"agents":[]}')

        running = '{"agents":[{"agent_name":"/root/worker","agent_status":"running"}]}'
        self.hook("PostToolUse", **older, tool_response=running)
        dispatch = self.status()["goals"][0]["work"][0]["dispatch"]
        self.assertEqual(dispatch["agent_link"], "needs_verify")
        wait_tool = {"tool_name": "collaboration.wait_agent", "tool_input": {}}
        wait = self.hook("PreToolUse", **wait_tool)
        self.assertEqual(self.permission(wait), "deny", wait)

        self.observe_agents(("/root/worker", "running"))
        dispatch = self.status()["goals"][0]["work"][0]["dispatch"]
        self.assertEqual(dispatch["agent_link"], "verified")
        self.turn = str(uuid.uuid4())
        wait = self.hook("PreToolUse", **wait_tool)
        self.assertEqual(self.permission(wait), "deny", wait)
        self.observe_agents(("/root/worker", "running"))
        refreshed = self.hook("PreToolUse", **wait_tool)
        self.assertNotEqual(self.permission(refreshed), "deny", refreshed)

    def test_single_work_acceptance_does_not_deliver_any_goal(self) -> None:
        goals = self.goals()
        goals[0]["work"].append({"id": "W02", "title": "仍需满足的另一项验收"})
        self.plan(goals)
        spawn = {
            "tool_name": "collaborationspawn_agent",
            "tool_use_id": "call-spawn",
            "tool_input": {
                "fork_turns": "none", "message": "[lean-work G01/W01] 执行第一个工作包。",
                "model": "gpt-6.2-sol", "reasoning_effort": "medium", "task_name": "worker",
            },
        }
        start = self.hook("PreToolUse", **spawn)
        self.assertNotEqual(self.permission(start), "deny", start)
        self.hook("PostToolUse", **spawn, tool_response='{"task_name":"/root/worker","nickname":"worker"}')
        self.assertEqual(self.work_status(), "running")
        premature = self.input_file("accept-premature.json", {
            "action": "accept", "goal": "G01", "work": "W01", "evidence": "只有派发回执。",
        })
        rejected = self.invoke("update", "--session", self.session, "--input", premature)
        self.assertNotEqual(rejected.returncode, 0)
        self.observe_agents(
            ("/root/worker", {"completed": "第一个工作包已返回。"}), tool_name="collaborationlist_agents",
        )
        self.assertEqual(self.work_status(), "returned")

        self.update("accept", goal="G01", work="W01", evidence="独立复核只通过第一个工作包。")
        self.update("block", goal="G02", work="W01", blocker="缺少现场样本。", evidence="现场清单无该样本。")
        actual = self.status()["goals"]
        self.assertCountEqual((item["id"] for item in actual), (item["id"] for item in goals))
        affected = [item for item in actual if item["id"] in ("G01", "G02")]
        self.assertEqual([item["delivered"] for item in affected], [False, False])
        self.assertEqual(self.work_status(), "done")
        self.assertEqual(self.work_status(work="W02"), "ready")
        self.assertEqual(self.work_status(goal="G02"), "blocked")
        early_delivery = self.input_file("deliver.json", {"action": "deliver", "goal": "G01", "evidence": "只验收了第一个工作包。"})
        denied_delivery = self.invoke("update", "--session", self.session, "--input", early_delivery)
        self.assertNotEqual(denied_delivery.returncode, 0)
        self.assertEqual(self.status()["goals"], actual)

        followup = {
            "tool_name": "collaborationfollowup_task",
            "tool_use_id": "call-followup",
            "tool_input": {"target": "/root/worker", "message": "[lean-work G01/W02] 接续第二个工作包。"},
        }
        reuse = self.hook("PreToolUse", **followup)
        self.assertNotEqual(self.permission(reuse), "deny", reuse)
        self.hook("PostToolUse", **followup, tool_response="")
        self.assertEqual(self.work_status(work="W02"), "running")
        self.observe_agents(
            ("/root/worker", {"completed": "第二个工作包已返回。"}), tool_name="collaborationlist_agents",
        )
        self.assertEqual(self.work_status(work="W02"), "returned")
        self.update("accept", goal="G01", work="W02", evidence="第二个工作包的验收已完成。")
        self.assertFalse(self.status()["goals"][0]["delivered"])
        delivered = self.update("deliver", goal="G01", evidence="完整主线结果已交付。")
        self.assertEqual([item["id"] for item in delivered["goals"] if item["delivered"]], ["G01"])

    def test_ambiguous_parallel_spawn_returns_do_not_guess_an_agent_uuid(self) -> None:
        self.plan(self.goals(2))
        calls = [
            {
                "tool_name": "collaboration.spawn_agent",
                "tool_use_id": f"call-worker-{index}",
                "tool_input": {"agent_type": "worker", "message": f"[lean-work G{index:02d}/W01] 执行工作包。"},
            }
            for index in (1, 2)
        ]
        agents = [
            {
                "session": str(uuid.uuid4()), "agent_id": str(uuid.uuid4()),
                "agent_type": "worker", "turn_id": str(uuid.uuid4()),
            }
            for _ in calls
        ]
        for call in calls:
            self.hook("PreToolUse", **call)
        for agent in agents:
            self.hook("SubagentStart", **agent)
        for index, call in enumerate(calls, 1):
            response = json.dumps({"task_name": f"/root/worker_{index}", "nickname": f"worker_{index}"})
            self.hook("PostToolUse", **call, tool_response=response)
        self.hook("SubagentStop", **agents[0], stop_hook_active=False)

        for index, goal in enumerate(self.status()["goals"], 1):
            work = goal["work"][0]
            self.assertEqual(work["status"], "running")
            self.assertEqual(work["dispatch"]["task_path"], f"/root/worker_{index}")
            self.assertIsNone(work["dispatch"].get("agent_id"))
        self.observe_agents(("/root/worker_2", {"completed": "第二个执行者已返回。"}))
        self.assertEqual(self.work_status(goal="G02"), "returned")
        self.assertEqual(self.work_status(goal="G01"), "running")
        wait = self.hook("PreToolUse", tool_name="collaboration.wait_agent", tool_input={})
        self.assertEqual(self.permission(wait), "deny", wait)

    def test_manual_verification_requires_the_exact_successful_dispatch_path(self) -> None:
        self.plan(self.goals(2))
        self.hook(
            "PostToolUse", tool_name="collaboration.spawn_agent", tool_use_id="call-verify",
            tool_input={"message": "[lean-work G01/W01] 执行工作包。"},
            tool_response='{"task_name":"/root/actual","nickname":"actual"}',
        )
        request = {
            "work": "W01", "state": "returned",
            "evidence": "原生代理清单中该执行者已返回。",
        }
        for goal, path in (("G01", "/root/other"), ("G02", "/root/actual")):
            with self.subTest(goal=goal, path=path):
                invalid = self.input_file("verify-invalid.json", {
                    "action": "verify", **request, "goal": goal, "task_path": path,
                })
                result = self.invoke("update", "--session", self.session, "--input", invalid)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.work_status(goal="G01"), "running")
        self.assertEqual(self.work_status(goal="G02"), "ready")
        self.update("verify", goal="G01", task_path="/root/actual", **request)
        self.assertEqual(self.work_status(goal="G01"), "returned")
        self.assertFalse(self.status()["goals"][0]["delivered"])

    def test_stop_blocks_once_for_unchanged_work_and_allows_concrete_blockers(self) -> None:
        self.plan(self.goals(1))
        first = self.hook("Stop", stop_hook_active=False)
        self.assertEqual(first.get("decision"), "block", first)
        self.assertIsNot(first.get("continue"), False)
        self.assertTrue(first.get("reason"), first)
        stopped_again = self.hook("Stop", stop_hook_active=False)
        self.assertNotEqual(stopped_again.get("decision"), "block", stopped_again)

        spawn = {
            "tool_name": "collaboration.spawn_agent",
            "tool_use_id": "call-stop-progress",
            "tool_input": {"agent_type": "worker", "message": "[lean-work G01/W01] 执行工作包。"},
        }
        self.hook("PreToolUse", **spawn)
        self.hook("PostToolUse", **spawn, tool_response='{"task_name":"/root/worker","nickname":"worker"}')
        self.observe_agents(("/root/worker", {"completed": "第一个工作包已返回。"}))
        self.update("accept", goal="G01", work="W01", evidence="第一个工作包已经验收。")
        next_plan = self.goals(1)
        next_plan[0]["work"].append({"id": "W02", "title": "已解锁的后续工作包"})
        self.plan(next_plan)

        changed = self.hook("Stop", stop_hook_active=True)
        self.assertEqual(changed.get("decision"), "block", changed)
        self.assertNotEqual(self.hook("Stop", stop_hook_active=True).get("decision"), "block")

        self.update("block", goal="G01", work="W02", blocker="尚缺现场会话和授权", evidence="目标设备当前未授权。")
        self.assertEqual(self.work_status(work="W02"), "blocked")
        wait = self.hook("PreToolUse", tool_name="collaboration.wait_agent", tool_input={})
        self.assertEqual(self.permission(wait), "deny", wait)
        final = self.hook("Stop", stop_hook_active=False)
        self.assertNotEqual(final.get("decision"), "block", final)
        self.assertEqual(len(self.status()["goals"]), 1)

    def test_normal_work_and_child_hooks_do_not_activate_parent_guard(self) -> None:
        self.hook("UserPromptSubmit", prompt="请概括这段说明")
        self.hook("UserPromptSubmit", prompt="请概括这句话：每条主线持续有代理，直到该条交付。")
        local = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "git status"})
        self.assertNotEqual(self.permission(local), "deny", local)
        self.assertNotEqual(self.hook("Stop", stop_hook_active=False).get("decision"), "block")
        self.assertEqual(self.status(), {"status": "inactive"})
        self.assertFalse(self.table_path().exists())

        self.plan(self.goals(1))
        before = self.table_path().read_bytes()
        child = {"agent_id": str(uuid.uuid4()), "agent_type": "worker"}
        local = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "git status"}, **child)
        self.assertNotEqual(self.permission(local), "deny", local)
        self.assertNotEqual(self.hook("Stop", stop_hook_active=False, **child).get("decision"), "block")
        self.assertEqual(self.table_path().read_bytes(), before)

    def test_session_state_isolation_and_corruption_does_not_reinitialize(self) -> None:
        self.plan(self.goals())
        other = str(uuid.uuid4())
        self.assertEqual(self.status(session=other), {"status": "inactive"})
        wait = self.hook("PreToolUse", session=other, tool_name="collaboration.wait_agent", tool_input={})
        self.assertNotEqual(self.permission(wait), "deny", wait)
        self.assertFalse(self.table_path(session=other).exists())
        self.plan(self.goals(1), session=other)
        other_before = self.table_path(session=other).read_bytes()

        damage = b'{"version": incomplete'
        self.table_path().write_bytes(damage)
        replacement = self.input_file("replacement.json", {"goals": self.goals(2)})
        failed_plan = self.invoke(
            "plan", "--session", self.session, "--cwd", str(self.workspace), "--input", replacement,
        )
        self.assertNotEqual(failed_plan.returncode, 0, (failed_plan.stdout, failed_plan.stderr, self.workspace))
        self.assertEqual(self.table_path().read_bytes(), damage)
        self.assertEqual(self.table_path(session=other).read_bytes(), other_before)

    def test_compaction_recovers_all_rows_from_the_current_session_table(self) -> None:
        self.plan(self.goals())
        self.update("block", goal="G04", work="W01", blocker="只等待第 4 条的现场证据。", evidence="现场核对记录尚缺第 4 条。")
        before = self.status()["goals"]
        self.plan(self.goals(1))
        compacted = self.hook("SessionStart", source="compact")
        output = compacted.get("hookSpecificOutput", {})
        self.assertEqual(output.get("hookEventName"), "SessionStart")
        context = output.get("additionalContext", "")
        self.assertIn(self.session, context)
        for goal in before:
            self.assertIn(goal["id"], context)
        self.assertEqual(self.status()["goals"], before)
        self.assertEqual(len(before), 13)
        self.assertEqual(self.work_status(goal="G04"), "blocked")

    def test_explicit_pause_and_interrupt_survive_plan_refresh(self) -> None:
        for stop in (
            "请先停止所有代理派遣，先只说明当前证据。",
            "本轮不再派任何子代理，先只说明当前证据。",
            None,
        ):
            with self.subTest(stop=stop):
                self.session = str(uuid.uuid4())
                self.plan(self.goals(1))
                if stop is None:
                    self.hook("Interrupt")
                    self.hook("UserPromptSubmit", prompt="继续")
                else:
                    self.hook("UserPromptSubmit", prompt="不要停止派遣")
                    self.assertEqual(self.status()["status"], "active")
                    self.hook("UserPromptSubmit", prompt=stop)
                self.assertEqual(self.status()["status"], "paused")
                self.plan(self.goals(1))
                self.hook("SessionStart", source="compact")
                self.assertEqual(self.status()["status"], "paused")
                stopped = self.hook("Stop", stop_hook_active=False)
                self.assertNotEqual(stopped.get("decision"), "block", stopped)
                local = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "git status"})
                self.assertNotEqual(self.permission(local), "deny", local)


if __name__ == "__main__":
    unittest.main()
