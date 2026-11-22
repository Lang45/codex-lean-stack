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

    def plan(self, goals: list[dict], *, session: str | None = None, mode: str | None = None) -> dict:
        request = {"goals": goals}
        if mode is not None:
            request["mode"] = mode
        source = self.input_file("plan.json", request)
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

    def continuous_goals(self, count: int = 13) -> list[dict]:
        goals = self.goals(count)
        for goal in goals:
            goal.update(
                outcome=f"{goal['id']} 的完整用户结果",
                acceptance="下一阶段的操作、证据与验收均已完成。",
                milestone={"id": "M01", "title": "首批证据或试运行", "final": False},
            )
            goal["work"][0].update(kind="core", milestone="M01")
        return goals

    def spawn_assigned(self, goal_id: str, work_id: str) -> str:
        goal = next(row for row in self.status()["goals"] if row["id"] == goal_id)
        work = next(row for row in goal["work"] if row["id"] == work_id)
        path = work["executor"]
        name = path.rsplit("/", 1)[-1]
        call = {
            "tool_name": "collaborationspawn_agent", "tool_use_id": f"call-batch-{goal_id}-{work_id}",
            "tool_input": {"task_name": name, "message": "执行当前主线的已分配工作包。"},
        }
        opened = self.hook("PreToolUse", **call)
        self.assertNotEqual(self.permission(opened), "deny", opened)
        self.hook("PostToolUse", **call, tool_response=json.dumps({"task_name": path}))
        self.assertEqual(self.work_status(goal=goal_id, work=work_id), "running")
        return path

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

    def observe_legacy_spawn(self, task_name: str) -> None:
        call = {
            "tool_name": "collaboration.spawn_agent", "tool_use_id": f"call-legacy-{uuid.uuid4()}",
            "tool_input": {"task_name": task_name, "message": "[lean-work G01/W01] 执行工作包。"},
        }
        opened = self.hook("PreToolUse", **call)
        self.assertNotEqual(self.permission(opened), "deny", opened)
        self.hook("PostToolUse", **call, tool_response=json.dumps({"task_name": f"/root/{task_name}"}))

    def test_explicit_coverage_request_marks_the_session_for_a_plan(self) -> None:
        for prompt, count in (
            ("十三条未完成主线必须逐条持续有实际工作的代理，直到该条完成并交付才退出派遣。", 13),
            ("按14条主线表每条排几个，持续多排。", 14),
            ("每条主线持续有代理，直到该条交付。", 13),
        ):
            with self.subTest(prompt=prompt):
                self.session = str(uuid.uuid4())
                self.hook("UserPromptSubmit", prompt=prompt)
                pending = self.status()
                self.assertEqual(pending["status"], "needs_plan")
                self.assertEqual(pending["mode"], "continuous")
                self.assertTrue(self.table_path().is_file())
                table = self.plan(self.continuous_goals(count))
                self.assertEqual(len(table["goals"]), count)
                self.assertTrue(all(state == "ready" for state in table["coverage"].values()))

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

    def test_first_batch_cannot_leave_eleven_undelivered_goals_without_coverage(self) -> None:
        goals = self.continuous_goals()
        goals[2]["work"].append({"id": "W02", "title": "旁路材料整理", "kind": "support", "milestone": "M01"})
        self.plan(goals, mode="continuous")
        paths = [self.spawn_assigned(goal["id"], "W01") for goal in goals]
        support = self.spawn_assigned("G03", "W02")
        self.observe_agents(
            (paths[0], "running"), (paths[1], "running"),
            (paths[2], {"completed": "首批证据就绪。"}), (support, "running"),
            *((path, {"completed": "这一个首批工作包缺少输入。"}) for path in paths[3:]),
        )
        self.update("accept", goal="G03", work="W01", evidence="仅验收首批工作包，整条主线仍未完成。")
        for goal in goals[3:]:
            self.update(
                "block", goal=goal["id"], work="W01",
                blocker="这一个工作包的输入未就绪。", evidence="仅限这个工作包的输入清单。",
            )
        first_batch = self.status()
        self.assertEqual(sum(not goal["delivered"] for goal in first_batch["goals"]), 13)
        self.assertEqual(first_batch["coverage"], {
            goal["id"]: "working" if index < 2 else "needs_continuation"
            for index, goal in enumerate(goals)
        })

        wait = self.hook("PreToolUse", tool_name="collaborationwait_agent", tool_input={})
        self.assertEqual(self.permission(wait), "deny", wait)
        self.assertEqual(self.hook("Stop", stop_hook_active=False).get("decision"), "block")
        local_tool = {"tool_name": "exec_command", "tool_input": {"cmd": "git status --short"}}
        local = self.hook("PreToolUse", **local_tool)
        self.assertNotEqual(self.permission(local), "deny", local)
        self.assertIn("G03", local["hookSpecificOutput"]["additionalContext"])

        goals[3]["work"].append({"id": "W02", "title": "取得关键缺失输入", "kind": "unblock", "milestone": "M01"})
        self.assertEqual(self.plan(goals, mode="continuous")["coverage"]["G04"], "ready")
        still_pending = self.hook("PreToolUse", **local_tool)
        self.assertEqual(self.permission(still_pending), "deny", still_pending)
        unblock = self.spawn_assigned("G04", "W02")
        self.assertEqual(self.status()["coverage"]["G04"], "working")
        self.observe_agents(
            (paths[0], "running"), (paths[1], "running"), (unblock, "running"),
            (support, {"completed": "旁路材料已整理。"}),
        )
        self.update("accept", goal="G03", work="W02", evidence="只验收了辅助材料。")
        partial = self.input_file("deliver-nonfinal.json", {
            "action": "deliver", "goal": "G03", "milestone": "M01", "evidence": "首批工作包已验收。",
        })
        denied = self.invoke("update", "--session", self.session, "--input", partial)
        self.assertNotEqual(denied.returncode, 0)

        goals[2]["milestone"] = {"id": "M02", "title": "实际操作和独立验收", "final": True}
        advanced = self.plan(goals, mode="continuous")
        self.assertEqual(advanced["coverage"]["G03"], "needs_continuation")
        old_receipts = self.input_file("deliver-old-work.json", {
            "action": "deliver", "goal": "G03", "milestone": "M02", "evidence": "仅有首批工作验收回执。",
        })
        denied = self.invoke("update", "--session", self.session, "--input", old_receipts)
        self.assertNotEqual(denied.returncode, 0)
        goals[2]["work"].append({"id": "W03", "title": "完成真实入口验收", "kind": "core", "milestone": "M02"})
        self.assertEqual(self.plan(goals, mode="continuous")["coverage"]["G03"], "ready")
        final = self.spawn_assigned("G03", "W03")
        self.observe_agents(
            (paths[0], "running"), (paths[1], "running"), (unblock, "running"),
            (final, {"completed": "实际操作和独立验收已返回。"}),
        )
        self.update("accept", goal="G03", work="W03", evidence="独立核对实际入口和回执。")
        self.update("deliver", goal="G03", milestone="M02", evidence="已经逐条交付第三条完整结果。")

        before = self.status()
        self.assertEqual([row["id"] for row in before["goals"] if row["delivered"]], ["G03"])
        self.assertEqual(before["coverage"]["G03"], "delivered")
        recovered = self.hook("SessionStart", source="compact")
        context = recovered["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("G03", context)
        for goal in before["goals"]:
            if not goal["delivered"]:
                self.assertIn(goal["id"], context)
        self.assertEqual(self.status(), before)

    def test_continuous_goal_can_stop_only_with_an_explicit_whole_goal_blocker(self) -> None:
        self.plan(self.continuous_goals(1), mode="continuous")
        blocker = {
            "goal": "G01", "blocker": "决定整条主线的外部接口停用，暂无可执行替代。",
            "evidence": "接口停用回执与替代路径核对。",
        }
        while_ready = self.input_file("block-ready-goal.json", {
            "action": "block_goal", **blocker, "resume_when": "接口恢复且可读取所需实证。",
        })
        denied = self.invoke("update", "--session", self.session, "--input", while_ready)
        self.assertNotEqual(denied.returncode, 0)
        self.update(
            "block", goal="G01", work="W01", blocker="这一个工作包缺少输入。",
            evidence="该工作包的输入清单。",
        )
        self.assertEqual(self.status()["coverage"]["G01"], "needs_continuation")
        self.assertEqual(self.hook("Stop", stop_hook_active=False).get("decision"), "block")
        incomplete = self.input_file("block-goal-incomplete.json", {"action": "block_goal", **blocker})
        denied = self.invoke("update", "--session", self.session, "--input", incomplete)
        self.assertNotEqual(denied.returncode, 0)

        self.update("block_goal", **blocker, resume_when="接口恢复且可读取所需实证。")
        self.assertNotEqual(self.hook("Stop", stop_hook_active=False).get("decision"), "block")
        stopped = self.status()
        self.assertFalse(stopped["goals"][0]["delivered"])
        self.assertEqual(stopped["coverage"]["G01"], "whole_blocked")

        self.update("unblock_goal", goal="G01", evidence="外部接口已恢复。")
        self.assertEqual(self.status()["coverage"]["G01"], "needs_continuation")
        wait = self.hook("PreToolUse", tool_name="collaborationwait_agent", tool_input={})
        self.assertEqual(self.permission(wait), "deny", wait)

    def test_active_dispatch_requires_an_unambiguous_ready_assignment(self) -> None:
        tools = (
            ("collaborationspawn_agent", "task_name"),
            ("collaborationfollowup_task", "target"),
        )

        def arguments(tool: str, parameter: str, value: str, message: str = "执行当前工作。") -> dict:
            return {
                "tool_name": tool, "tool_use_id": f"call-assignment-{uuid.uuid4()}",
                "tool_input": {parameter: value, "message": message},
            }

        for tool, parameter in tools:
            value = "unassigned" if parameter == "task_name" else "/root/unassigned"
            unrestricted = self.hook("PreToolUse", **arguments(tool, parameter, value))
            self.assertNotEqual(self.permission(unrestricted), "deny", unrestricted)
        self.assertFalse(self.table_path().exists())

        table = self.plan(self.goals(2))
        ready, blocked = (goal["work"][0]["executor"] for goal in table["goals"])
        self.update("block", goal="G02", work="W01", blocker="输入未就绪。", evidence="当前输入清单。")
        for tool, parameter in tools:
            ready_value = ready.rsplit("/", 1)[-1] if parameter == "task_name" else ready
            for path in ("/root/unassigned", blocked):
                with self.subTest(tool=tool, path=path):
                    value = path.rsplit("/", 1)[-1] if parameter == "task_name" else path
                    denied = self.hook("PreToolUse", **arguments(tool, parameter, value))
                    self.assertEqual(self.permission(denied), "deny", denied)
                    reason = denied["hookSpecificOutput"]["permissionDecisionReason"]
                    self.assertIn(parameter, reason)
                    self.assertIn(ready_value, reason)
            call = arguments(tool, parameter, ready_value)
            permitted = self.hook("PreToolUse", **call)
            self.assertNotEqual(self.permission(permitted), "deny", permitted)
            self.hook("PostToolUse", **call, tool_response="Error: controlled unsuccessful dispatch")
        self.assertEqual(self.work_status(), "ready")

        self.hook("UserPromptSubmit", prompt="本轮不再派任何子代理，先只说明当前证据。")
        self.assertEqual(self.status()["status"], "paused")
        for tool, parameter in tools:
            value = "unassigned" if parameter == "task_name" else "/root/unassigned"
            unrestricted = self.hook("PreToolUse", **arguments(tool, parameter, value))
            self.assertNotEqual(self.permission(unrestricted), "deny", unrestricted)

    def test_duplicate_ready_executor_is_rejected_and_delivered_guard_releases(self) -> None:
        goals = self.goals(2)
        for goal in goals:
            goal["work"][0]["executor"] = "/root/shared"
        duplicate = self.input_file("duplicate-executor.json", {"goals": goals})
        rejected = self.invoke("plan", "--session", self.session, "--cwd", str(self.workspace), "--input", duplicate)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse(self.table_path().exists())

        self.plan(self.goals(1))
        self.observe_legacy_spawn("legacy_worker")
        work = self.status()["goals"][0]["work"][0]
        self.assertEqual(work["dispatch"]["task_path"], "/root/legacy_worker")
        self.observe_agents(("/root/legacy_worker", {"completed": "工作包已返回。"}))
        self.update("accept", goal="G01", work="W01", evidence="工作包的验收已完成。")
        self.update("deliver", goal="G01", evidence="本表唯一主线已完整交付。")
        untracked = self.hook(
            "PreToolUse", tool_name="collaborationspawn_agent", tool_use_id="call-after-delivery",
            tool_input={"task_name": "new_task", "message": "处理另一个任务。"},
        )
        self.assertNotEqual(self.permission(untracked), "deny", untracked)

    def test_distinct_legacy_followups_cannot_reserve_the_same_actor(self) -> None:
        self.plan(self.goals(1))
        self.observe_legacy_spawn("shared")
        self.observe_agents(("/root/shared", {"completed": "原工作包已返回。"}))
        goals = self.goals(3)
        self.plan(goals)

        def call(goal: str) -> dict:
            return {
                "tool_name": "collaborationfollowup_task", "tool_use_id": f"call-{goal}",
                "tool_input": {"target": "/root/shared", "message": f"[lean-work {goal}/W01] 接续工作。"},
            }

        earlier = call("G02")
        admitted = self.hook("PreToolUse", **earlier)
        self.assertNotEqual(self.permission(admitted), "deny", admitted)
        before_replay = self.table_path().read_bytes()
        self.plan(goals)
        self.assertEqual(self.table_path().read_bytes(), before_replay)
        replay = self.hook("PreToolUse", **earlier)
        self.assertNotEqual(self.permission(replay), "deny", replay)
        for goal, executor in ((goals[1], "/root/other"), (goals[2], "/root/shared")):
            with self.subTest(goal=goal["id"], executor=executor):
                candidate = {**goal, "work": [{**goal["work"][0], "executor": executor}]}
                source = self.input_file("change-reserved-executor.json", {"goals": [candidate]})
                result = self.invoke(
                    "plan", "--session", self.session, "--cwd", str(self.workspace), "--input", source,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.table_path().read_bytes(), before_replay)
        denied = self.hook("PreToolUse", **call("G03"))
        self.assertEqual(self.permission(denied), "deny", denied)
        conflicting_path = {**earlier, "tool_use_id": "call-G02-other-path"}
        conflicting_path["tool_input"] = {**earlier["tool_input"], "target": "/root/other"}
        denied = self.hook("PreToolUse", **conflicting_path)
        self.assertEqual(self.permission(denied), "deny", denied)

        self.hook("PostToolUse", **earlier, tool_response="Error: controlled unsuccessful dispatch")
        pending = call("G03")
        retry = self.hook("PreToolUse", **pending)
        self.assertNotEqual(self.permission(retry), "deny", retry)
        self.update("retry", goal="G03", work="W01", evidence="原生执行检查确认这次派发未启动。")
        goals[2]["work"][0]["executor"] = "/root/other"
        updated = self.plan(goals)
        self.assertEqual(updated["goals"][2]["work"][0]["executor"], "/root/other")
        self.hook("PostToolUse", **pending, tool_response="")
        self.assertEqual(self.work_status(goal="G03"), "ready")
        replacement = self.hook(
            "PreToolUse", tool_name="collaborationspawn_agent", tool_use_id="call-replacement",
            tool_input={"task_name": "other", "message": "执行已重新分配的工作包。"},
        )
        self.assertNotEqual(self.permission(replacement), "deny", replacement)

    def test_native_dispatch_failure_does_not_cover_a_work_package(self) -> None:
        self.plan(self.goals(1))
        call = {
            "tool_name": "collaboration.spawn_agent",
            "tool_use_id": "call-failed-spawn",
            "tool_input": {"task_name": "retry", "message": "[lean-work G01/W01] 完成指定工作包。"},
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
            "tool_input": {"task_name": "worker", "message": "[lean-work G01/W01] 执行工作包。"},
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
        self.observe_legacy_spawn("worker")
        self.observe_agents(("/root/worker", {"completed": "工作包已返回。"}))
        self.assertEqual(self.work_status(), "returned")

        wait = self.hook("PreToolUse", tool_name="collaboration.wait_agent", tool_input={})
        self.assertEqual(self.permission(wait), "deny", wait)
        self.assertRegex(wait["hookSpecificOutput"]["permissionDecisionReason"], r"采用|验收|交付")

    def test_late_and_prior_turn_rosters_cannot_authorize_wait(self) -> None:
        self.plan(self.goals(1))
        self.observe_legacy_spawn("worker")
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

    def test_structured_dispatch_and_followup_preserve_individual_goal_acceptance(self) -> None:
        goals = self.goals()
        executor = self.plan(goals)["goals"][0]["work"][0]["executor"]
        self.assertRegex(executor, r"^/root/[a-z0-9_]+$")
        self.assertEqual(self.plan(goals)["goals"][0]["work"][0]["executor"], executor)
        native_name = executor.rsplit("/", 1)[-1]
        spawn = {
            "tool_name": "collaborationspawn_agent",
            "tool_use_id": "call-spawn",
            "tool_input": {
                "fork_turns": "none", "message": "执行第一个工作包。",
                "model": "gpt-6.2-sol", "reasoning_effort": "medium", "task_name": native_name,
            },
        }
        receipt = json.dumps({"task_name": executor, "nickname": native_name})
        self.hook("PostToolUse", **spawn, tool_response=receipt)
        self.assertEqual(self.work_status(), "ready")
        wrong_path = {**spawn, "tool_use_id": "call-spawn-wrong-path"}
        attempted = self.hook("PreToolUse", **wrong_path)
        self.assertNotEqual(self.permission(attempted), "deny", attempted)
        self.hook("PostToolUse", **wrong_path, tool_response='{"task_name":"/root/other","nickname":"other"}')
        self.assertEqual(self.work_status(), "ready")
        start = self.hook("PreToolUse", **spawn)
        self.assertNotEqual(self.permission(start), "deny", start)
        self.hook("PostToolUse", **spawn, tool_response=receipt)
        active = self.status()["goals"][0]["work"][0]
        self.assertEqual(active["status"], "running")
        self.assertEqual(active["dispatch"]["task_path"], executor)
        next_work = {"id": "W02", "title": "仍需满足的另一项验收", "executor": executor}
        for works in (
            [{**goals[0]["work"][0], "executor": "/root/other"}],
            [*goals[0]["work"], next_work],
        ):
            reassign = self.input_file("reassign.json", {"goals": [{**goals[0], "work": works}]})
            result = self.invoke(
                "plan", "--session", self.session, "--cwd", str(self.workspace), "--input", reassign,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.status()["goals"][0]["work"], [active])
        premature = self.input_file("accept-premature.json", {
            "action": "accept", "goal": "G01", "work": "W01", "evidence": "只有派发回执。",
        })
        rejected = self.invoke("update", "--session", self.session, "--input", premature)
        self.assertNotEqual(rejected.returncode, 0)
        self.observe_agents(
            (executor, {"completed": "第一个工作包已返回。"}), tool_name="collaborationlist_agents",
        )
        self.assertEqual(self.work_status(), "returned")

        self.update("accept", goal="G01", work="W01", evidence="独立复核只通过第一个工作包。")
        goals[0]["work"].append(next_work)
        self.plan(goals)
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
            "tool_input": {"target": executor, "message": "接续第二个工作包。"},
        }
        misdirected = {
            **followup, "tool_use_id": "call-followup-wrong-path",
            "tool_input": {"target": "/root/other", "message": "[lean-work G01/W02] 接续第二个工作包。"},
        }
        denied = self.hook("PreToolUse", **misdirected)
        self.assertEqual(self.permission(denied), "deny", denied)
        reuse = self.hook("PreToolUse", **followup)
        self.assertNotEqual(self.permission(reuse), "deny", reuse)
        self.hook("PostToolUse", **followup, tool_response="")
        self.assertEqual(self.work_status(work="W02"), "running")
        self.observe_agents(
            (executor, {"completed": "第二个工作包已返回。"}), tool_name="collaborationlist_agents",
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
                "tool_input": {"task_name": f"worker_{index}", "message": f"[lean-work G{index:02d}/W01] 执行工作包。"},
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
        self.observe_legacy_spawn("actual")
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
            "tool_input": {"task_name": "worker", "message": "[lean-work G01/W01] 执行工作包。"},
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
