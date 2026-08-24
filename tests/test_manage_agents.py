from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import unittest
import uuid
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "lean-stack"
    / "scripts"
    / "manage_agents.py"
)
SPEC = importlib.util.spec_from_file_location("lean_stack_manage_agents", SCRIPT)
assert SPEC and SPEC.loader
manage_agents = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_agents)


class AgentLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.codex_home = self.root / ".codex"
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        self.lifecycle = manage_agents.AgentLifecycle(self.codex_home)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def spec(**overrides):
        value = {
            "slug": "integration-reviewer",
            "display_name": "集成审查员",
            "description": "Read-only integration reviewer for evidence-backed boundary checks.",
            "developer_instructions": (
                "Trace the affected boundary, identify real regressions, and return only "
                "evidence-backed findings."
            ),
            "model": "gpt-5.6-terra",
            "model_reasoning_effort": "high",
            "sandbox_mode": "read-only",
            "capability_tags": ["integration-review", "tests"],
            "risk_ceiling": "read_only",
        }
        value.update(overrides)
        return value

    def create_visible_agent(self):
        created = self.lifecycle.create_agent(self.spec(), self.project_root)
        self.lifecycle.confirm_visible(created["agent_id"])
        return created

    @staticmethod
    def high_report(agent_id: str, *, experience=True):
        report = {
            "agent_id": agent_id,
            "run_id": str(uuid.uuid4()),
            "task_class": "review",
            "risk_tier": "read_only",
            "scores": {
                "correctness": 34,
                "evidence": 18,
                "scope": 15,
                "efficiency": 13,
                "clarity": 9,
                "safety": 5,
            },
            "evidence_flags": ["source_verified", "scope_audit", "safety_audit"],
            "critical_event": "none",
            "critical_confirmations": [],
            "judge_kind": "independent_model",
            "judge_confidence": "high",
            "duration_bucket": "expected",
            "token_bucket": "low",
            "user_verdict": "unknown",
        }
        if experience:
            report["experience"] = {
                "key": "trace-shared-boundary-first",
                "rule": "Trace the shared boundary and its real caller before proposing a local guard.",
                "applies_to": "review",
            }
        return report

    @staticmethod
    def routing(
        *,
        model="gpt-5.6-terra",
        effort="high",
        service_tier="standard",
        attribution="model_capacity",
        execution_mode="managed_named",
        host_status="request_accepted",
        effective=False,
    ):
        return {
            "requested_model": model,
            "requested_reasoning_effort": effort,
            "requested_service_tier": service_tier,
            "effective_model": model if effective else "unknown",
            "effective_reasoning_effort": effort if effective else "unknown",
            "effective_service_tier": service_tier if effective else "unknown",
            "execution_mode": execution_mode,
            "host_config_status": "effective_confirmed" if effective else host_status,
            "attribution": attribution,
        }

    @staticmethod
    def low_quality_report(
        agent_id: str,
        *,
        model="gpt-5.6-terra",
        effort="high",
        task_class="review",
        attribution="model_capacity",
    ):
        report = AgentLifecycleTests.high_report(agent_id, experience=False)
        report["task_class"] = task_class
        report["scores"] = {
            "correctness": 20,
            "evidence": 10,
            "scope": 12,
            "efficiency": 10,
            "clarity": 7,
            "safety": 5,
        }
        report["routing"] = AgentLifecycleTests.routing(
            model=model,
            effort=effort,
            attribution=attribution,
        )
        report["failure_reason"] = "incorrect_result"
        return report

    @staticmethod
    def high_quality_slow_report(
        agent_id: str,
        *,
        model,
        effort,
        task_class,
        service_tier="standard",
    ):
        report = AgentLifecycleTests.high_report(agent_id, experience=False)
        report["task_class"] = task_class
        report["scores"]["efficiency"] = 10
        report["duration_bucket"] = "high"
        report["token_bucket"] = "low"
        report["routing"] = AgentLifecycleTests.routing(
            model=model,
            effort=effort,
            service_tier=service_tier,
            attribution="compute_latency",
        )
        return report

    @staticmethod
    def extreme_report(agent_id: str):
        return {
            "agent_id": agent_id,
            "run_id": str(uuid.uuid4()),
            "task_class": "review",
            "risk_tier": "read_only",
            "scores": {
                "correctness": 5,
                "evidence": 4,
                "scope": 4,
                "efficiency": 4,
                "clarity": 4,
                "safety": 4,
            },
            "evidence_flags": ["runtime_check", "scope_audit"],
            "critical_event": "none",
            "critical_confirmations": [],
            "judge_kind": "independent_model",
            "judge_confidence": "high",
            "duration_bucket": "high",
            "token_bucket": "high",
            "user_verdict": "reject",
        }

    @staticmethod
    def critical_report(agent_id: str):
        report = AgentLifecycleTests.high_report(agent_id, experience=False)
        report["critical_event"] = "unauthorized_destructive_write"
        report["critical_confirmations"] = ["deterministic", "human"]
        report["evidence_flags"] = ["runtime_check", "human_approved", "safety_audit"]
        report["user_verdict"] = "reject"
        return report

    @staticmethod
    def promotion(candidate_id: str):
        return {
            "candidate_id": candidate_id,
            "case_count": 3,
            "incumbent_quality": 91,
            "challenger_quality": 94,
            "incumbent_efficiency": 12,
            "challenger_efficiency": 13,
            "evidence_flags": ["tests_passed", "runtime_check"],
            "critical_regression": False,
            "judge_kind": "independent_model",
            "judge_confidence": "high",
        }

    @staticmethod
    def variation_plan(agent_id: str, *, trigger="manual", candidate_limit=1):
        return {
            "request_id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "task_class": "review",
            "risk_tier": "read_only",
            "trigger": trigger,
            "candidate_limit": candidate_limit,
            "wall_time_seconds": 300,
            "tool_call_limit": 4,
            "token_bucket": "expected",
            "credit_bucket": "expected",
        }

    @staticmethod
    def variation_stage(session_id: str, *, supervisor_direction=None, elapsed=60):
        return {
            "session_id": session_id,
            "elapsed_seconds": elapsed,
            "tool_calls_used": 2,
            "token_bucket_used": "low",
            "credit_bucket_used": "low",
            "supervisor_direction": supervisor_direction,
            "candidates": [
                {
                    "rule_key": "verify-terminal-state-once",
                    "rule": "Reconcile one terminal state before releasing the lifecycle lease.",
                    "applies_to": "review",
                    "rationale_code": "rework_reduction",
                }
            ],
        }

    @staticmethod
    def variation_verification(variation_candidate_id: str):
        report = AgentLifecycleTests.promotion(variation_candidate_id)
        report["variation_candidate_id"] = report.pop("candidate_id")
        report.update(
            tradeoff_accepted=False,
            shadow_suite_sha256="a" * 64,
            elapsed_seconds_total=120,
            tool_calls_total=3,
            token_bucket_total="low",
            credit_bucket_total="low",
            incumbent_duration_bucket="expected",
            challenger_duration_bucket="expected",
            incumbent_token_bucket="expected",
            challenger_token_bucket="low",
            incumbent_credit_bucket="expected",
            challenger_credit_bucket="low",
            incumbent_retry_count=1,
            challenger_retry_count=0,
            incumbent_rework_count=1,
            challenger_rework_count=0,
        )
        return report

    def db_row(self, query: str, parameters=()):
        connection = sqlite3.connect(self.lifecycle.db_path)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(query, parameters).fetchone()
        finally:
            connection.close()

    def insert_move_intent(
        self,
        *,
        agent_id: str,
        operation: str,
        source: Path,
        destination: Path,
        target_state: str,
    ) -> str:
        row = self.db_row("SELECT * FROM agents WHERE agent_id=?", (agent_id,))
        operation_id = str(uuid.uuid4())
        connection = sqlite3.connect(self.lifecycle.db_path)
        try:
            connection.execute(
                """INSERT INTO operations(
                       operation_id, agent_id, operation, old_hash, new_hash,
                       source_path, destination_path, target_state, revision,
                       stage, started_at, completed_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    operation_id,
                    agent_id,
                    operation,
                    row["expected_sha256"],
                    row["expected_sha256"],
                    str(source.resolve()),
                    str(destination.resolve()),
                    target_state,
                    row["revision"],
                    "prepared",
                    manage_agents.utc_now(),
                    None,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return operation_id

    def test_cli_create_and_catalog_round_trip(self):
        empty = self.lifecycle.catalog(self.project_root)
        self.assertEqual(
            [item["name"] for item in empty["builtins"]],
            ["default", "worker", "explorer"],
        )
        self.assertFalse(self.lifecycle.db_path.exists())
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(self.spec(), ensure_ascii=False), encoding="utf-8")
        created_process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--codex-home",
                str(self.codex_home),
                "create",
                "--spec",
                str(spec_path),
                "--project-root",
                str(self.project_root),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(created_process.returncode, 0, created_process.stderr)
        created = json.loads(created_process.stdout)
        self.assertEqual(created["state"], "pending_visibility")

        path = Path(created["path"])
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["name"], created["name"])
        self.assertEqual(parsed["model"], "gpt-5.6-terra")
        self.assertEqual(parsed["model_reasoning_effort"], "high")
        self.assertIn("集成审查员", parsed["description"])
        self.assertIn("默认使用中文", parsed["developer_instructions"])
        self.assertIn("子代理名称：集成审查员", parsed["developer_instructions"])
        self.assertIn("请求模型", parsed["developer_instructions"])
        self.assertIn("生效推理强度", parsed["developer_instructions"])
        catalog_process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--codex-home",
                str(self.codex_home),
                "catalog",
                "--project-root",
                str(self.project_root),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(catalog_process.returncode, 0, catalog_process.stderr)
        catalog = json.loads(catalog_process.stdout)
        self.assertEqual(len(catalog["custom"]), 1)
        self.assertEqual(catalog["custom"][0]["source"], "plugin_managed")
        self.assertFalse(catalog["custom"][0]["selectable"])
        visible = self.lifecycle.confirm_visible(created["agent_id"])
        self.assertEqual(visible["state"], "probation")

    def test_project_key_is_stable_opaque_and_project_specific(self):
        first = manage_agents.project_key_for_root(self.project_root)
        second = manage_agents.project_key_for_root(self.project_root)
        other = self.root / "other-project"
        other.mkdir()
        third = manage_agents.project_key_for_root(other)
        self.assertEqual(first, second)
        self.assertRegex(first, r"^p_[0-9a-f]{64}$")
        self.assertNotEqual(first, third)
        self.assertNotIn(str(self.project_root), first)

    def test_invalid_or_task_specific_specs_fail_closed(self):
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.create_agent(self.spec(extra="unknown"), self.project_root)
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.create_agent(
                self.spec(developer_instructions="Read https://example.com for this task."),
                self.project_root,
            )
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.create_agent(
                self.spec(developer_instructions=r"Inspect C:\Users\person\secret.txt"),
                self.project_root,
            )
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.create_agent(
                self.spec(model_reasoning_effort="impossible"), self.project_root
            )

    def test_user_and_project_agents_remain_immutable_and_collisions_are_visible(self):
        personal = self.codex_home / "agents"
        project = self.project_root / ".codex" / "agents"
        personal.mkdir(parents=True)
        project.mkdir(parents=True)
        content = (
            'name = "default"\n'
            'description = "User custom agent."\n'
            'developer_instructions = "Do user-owned work."\n'
        )
        personal_path = personal / "user.toml"
        project_path = project / "project.toml"
        personal_path.write_text(content, encoding="utf-8")
        project_path.write_text(content, encoding="utf-8")
        before_personal = personal_path.read_bytes()
        before_project = project_path.read_bytes()

        catalog = self.lifecycle.catalog(self.project_root)
        default_builtin = next(item for item in catalog["builtins"] if item["name"] == "default")
        self.assertTrue(default_builtin["shadowed_by_custom"])
        collision_records = [item for item in catalog["custom"] if item.get("name") == "default"]
        self.assertEqual(len(collision_records), 2)
        self.assertTrue(all(item["source"] == "user_external_immutable" for item in collision_records))
        self.assertTrue(all(item["name_collision"] for item in collision_records))
        self.assertTrue(all(not item["selectable"] for item in collision_records))

        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.retire_agent(str(uuid.uuid4()))
        self.assertEqual(personal_path.read_bytes(), before_personal)
        self.assertEqual(project_path.read_bytes(), before_project)

    def test_hash_drift_revokes_automatic_ownership(self):
        created = self.create_visible_agent()
        path = Path(created["path"])
        path.write_bytes(path.read_bytes() + b"\n# external edit\n")
        drifted = path.read_bytes()
        with self.assertRaises(manage_agents.OwnershipConflict):
            self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
        self.assertEqual(path.read_bytes(), drifted)
        row = self.db_row("SELECT state FROM agents WHERE agent_id=?", (created["agent_id"],))
        self.assertEqual(row["state"], "conflict")
        catalog = self.lifecycle.catalog()
        record = next(item for item in catalog["custom"] if item.get("agent_id") == created["agent_id"])
        self.assertEqual(record["source"], "plugin_conflict")
        self.assertFalse(record["selectable"])

    def test_three_high_quality_observations_stage_and_promote_one_rule(self):
        created = self.create_visible_agent()
        first = self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
        second = self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
        third = self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
        self.assertIsNone(first["candidate_id"])
        self.assertIsNone(second["candidate_id"])
        self.assertEqual(third["experience_observation_count"], 3)
        self.assertIsNotNone(third["candidate_id"])

        incumbent_toml = Path(created["path"]).read_bytes()
        promoted = self.lifecycle.promote_candidate(self.promotion(third["candidate_id"]))
        self.assertEqual(promoted["revision"], 2)
        self.assertEqual(promoted["state"], "active")
        self.assertFalse(promoted["toml_modified"])
        self.assertTrue(promoted["injection_required"])
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent_toml)
        catalog = self.lifecycle.catalog(self.project_root)
        managed = next(item for item in catalog["custom"] if item.get("agent_id") == created["agent_id"])
        self.assertIn(
            "Trace the shared boundary and its real caller before proposing a local guard.",
            managed["validated_experience_rules"],
        )
        replay = self.lifecycle.promote_candidate(self.promotion(third["candidate_id"]))
        self.assertEqual(replay["action"], "candidate_already_promoted")

    def test_runtime_contract_omits_unexposed_effective_placeholders(self):
        contract = manage_agents.runtime_contract("集成审查员", "gpt-5.6-terra", "high")
        self.assertIn("请求模型", contract)
        self.assertIn("请求推理强度", contract)
        self.assertIn("只有宿主实际暴露", contract)
        self.assertIn("必须完全省略", contract)
        self.assertNotIn("未暴露（已请求", contract)

    def test_competition_weights_change_with_task_objective(self):
        architecture = manage_agents.competition_weights("architecture", "read_only")
        documentation = manage_agents.competition_weights("documentation", "read_only")
        self.assertGreater(architecture["quality"], documentation["quality"])
        self.assertGreater(
            documentation["speed"] + documentation["cost"],
            architecture["speed"] + architecture["cost"],
        )
        architecture_tradeoff = manage_agents.competition_objective_score(
            architecture, quality=90, speed=100, cost=100
        ) - manage_agents.competition_objective_score(
            architecture, quality=100, speed=30, cost=30
        )
        documentation_tradeoff = manage_agents.competition_objective_score(
            documentation, quality=90, speed=100, cost=100
        ) - manage_agents.competition_objective_score(
            documentation, quality=100, speed=30, cost=30
        )
        self.assertGreater(documentation_tradeoff, architecture_tradeoff)

    def test_rapid_high_applies_one_experience_and_stages_one_finite_challenger(self):
        created = self.create_visible_agent()
        incumbent = Path(created["path"]).read_bytes()
        report = self.high_report(created["agent_id"])
        report["evolution_mode"] = "rapid"
        report["routing"] = self.routing(attribution="compute_latency")

        first = self.lifecycle.record_evaluation(report)
        self.assertEqual(first["revision"], 2)
        self.assertEqual(first["evolution"]["outcome"], "rapid_experience_applied")
        self.assertTrue(first["evolution"]["experience"]["applied"])
        challenger = first["evolution"]["resource_challenger"]
        self.assertEqual(challenger["changed_axis"], "model")
        self.assertEqual(challenger["model"], "gpt-5.6-sol")
        self.assertEqual(challenger["reasoning_effort"], "high")
        self.assertFalse(challenger["toml_modified"])
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent)
        route = self.lifecycle.recommend_route(
            created["agent_id"], "review", "read_only", "managed_named", "standard"
        )
        self.assertEqual(route["action"], "compete")
        self.assertEqual(route["execution_mode"], "explicit_fallback")
        self.assertEqual(
            route["recommended"]["challenger_id"], challenger["challenger_id"]
        )

        replay = self.lifecycle.record_evaluation(report)
        self.assertEqual(replay["action"], "evaluation_already_recorded")
        self.assertEqual(replay["revision"], 2)
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM evolution_actions")["count"], 1
        )
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM resource_challengers")["count"], 1
        )
        self.assertEqual(
            self.db_row(
                "SELECT COUNT(*) AS count FROM candidates WHERE status='rapid_applied'"
            )["count"],
            1,
        )
        catalog = self.lifecycle.catalog()
        managed = next(
            item for item in catalog["custom"] if item.get("agent_id") == created["agent_id"]
        )
        self.assertEqual(len(managed["resource_challengers"]), 1)
        self.assertIn(
            "Trace the shared boundary and its real caller before proposing a local guard.",
            managed["validated_experience_rules"],
        )

        second_high = self.high_report(created["agent_id"])
        second_high["experience"] = {
            "key": "name-decisive-evidence-first",
            "rule": "Name the decisive evidence before expanding the review scope.",
            "applies_to": "review",
        }
        second_high["evolution_mode"] = "rapid"
        second_high["routing"] = self.routing(attribution="compute_latency")
        second = self.lifecycle.record_evaluation(second_high)
        self.assertEqual(second["evolution"]["competition_status"], "challenger_staged")
        self.assertEqual(
            self.db_row(
                "SELECT COUNT(*) AS count FROM resource_challengers WHERE status='staged'"
            )["count"],
            1,
        )

    def test_rapid_low_score_records_demerit_without_strengthening(self):
        created = self.create_visible_agent()
        report = self.high_report(created["agent_id"], experience=False)
        report["scores"] = {
            "correctness": 28,
            "evidence": 16,
            "scope": 13,
            "efficiency": 10,
            "clarity": 8,
            "safety": 5,
        }
        report["evolution_mode"] = "rapid"
        report["routing"] = self.routing(attribution="model_capacity")
        result = self.lifecycle.record_evaluation(report)
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["evolution"]["outcome"], "low_score_demerit")
        self.assertEqual(result["evolution"]["penalty_points"], 2)
        self.assertEqual(result["evolution"]["reputation_before"], 100)
        self.assertEqual(result["evolution"]["reputation_after"], 98)
        self.assertIsNone(result["evolution"]["resource_challenger"])

    def test_rapid_competition_stops_after_finite_single_axis_neighbors(self):
        created = self.create_visible_agent()
        incumbent = self.high_report(created["agent_id"])
        incumbent["evolution_mode"] = "rapid"
        incumbent["routing"] = self.routing(attribution="compute_latency")
        first = self.lifecycle.record_evaluation(incumbent)
        first_challenger = first["evolution"]["resource_challenger"]

        first_run = self.high_report(created["agent_id"])
        first_run["experience"] = {
            "key": "compare-resource-neighbor-once",
            "rule": "Compare each single-axis resource neighbor once before retaining the incumbent.",
            "applies_to": "review",
        }
        first_run.update(
            evolution_mode="rapid",
            challenger_id=first_challenger["challenger_id"],
        )
        first_run["routing"] = self.routing(
            model=first_challenger["model"],
            effort=first_challenger["reasoning_effort"],
            service_tier=first_challenger["service_tier"],
            attribution="compute_latency",
            execution_mode="explicit_fallback",
        )
        first_result = self.lifecycle.record_evaluation(first_run)
        self.assertEqual(
            first_result["evolution"]["challenger_resolution"]["status"], "lost"
        )
        second_challenger = first_result["evolution"]["resource_challenger"]
        self.assertEqual(second_challenger["changed_axis"], "reasoning_effort")
        self.assertEqual(second_challenger["reasoning_effort"], "xhigh")
        second_row = self.db_row(
            "SELECT trigger_evaluation_id FROM resource_challengers WHERE challenger_id=?",
            (second_challenger["challenger_id"],),
        )
        self.assertEqual(second_row["trigger_evaluation_id"], first["evaluation_id"])

        second_run = self.high_report(created["agent_id"])
        second_run["experience"] = {
            "key": "stop-after-neighbors-converge",
            "rule": "Stop generating resource challengers after every finite neighboring tier loses.",
            "applies_to": "review",
        }
        second_run.update(
            evolution_mode="rapid",
            challenger_id=second_challenger["challenger_id"],
        )
        second_run["routing"] = self.routing(
            model=second_challenger["model"],
            effort=second_challenger["reasoning_effort"],
            service_tier=second_challenger["service_tier"],
            attribution="compute_latency",
            execution_mode="explicit_fallback",
        )
        second_result = self.lifecycle.record_evaluation(second_run)
        self.assertEqual(
            second_result["evolution"]["competition_status"],
            "converged_no_untested_neighbor",
        )
        self.assertIsNone(second_result["evolution"]["resource_challenger"])
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM resource_challengers")["count"],
            2,
        )
        self.assertEqual(
            self.db_row(
                "SELECT COUNT(*) AS count FROM resource_challengers WHERE status='staged'"
            )["count"],
            0,
        )

    def test_second_major_failure_stages_exactly_one_strengthening_axis(self):
        cases = (
            ("reasoning_depth", "reasoning_effort", "gpt-5.6-terra", "xhigh"),
            ("model_capacity", "model", "gpt-5.6-sol", "high"),
        )
        for attribution, axis, expected_model, expected_effort in cases:
            with self.subTest(attribution=attribution):
                created = self.lifecycle.create_agent(
                    self.spec(slug=f"rapid-{axis.replace('_', '-')}"), self.project_root
                )
                self.lifecycle.confirm_visible(created["agent_id"])
                first_report = self.low_quality_report(
                    created["agent_id"], attribution=attribution
                )
                first_report["evolution_mode"] = "rapid"
                first = self.lifecycle.record_evaluation(first_report)
                self.assertIsNone(first["evolution"]["resource_challenger"])
                self.assertEqual(
                    first["evolution"]["configuration_observation"][
                        "major_failure_count"
                    ],
                    1,
                )
                self.assertEqual(
                    first["evolution"]["project_route"]["configuration_grade"],
                    "watch",
                )

                second_report = self.low_quality_report(
                    created["agent_id"], attribution=attribution
                )
                second_report["evolution_mode"] = "rapid"
                result = self.lifecycle.record_evaluation(second_report)
                challenger = result["evolution"]["resource_challenger"]
                self.assertEqual(result["score"], 64)
                self.assertEqual(
                    result["evolution"]["outcome"],
                    "failing_single_axis_challenger",
                )
                self.assertEqual(challenger["changed_axis"], axis)
                self.assertEqual(challenger["model"], expected_model)
                self.assertEqual(challenger["reasoning_effort"], expected_effort)
                self.assertTrue(
                    result["evolution"]["configuration_observation"][
                        "configuration_failing_after"
                    ]
                )
                self.assertEqual(
                    result["evolution"]["project_route"]["major_failure_count"], 2
                )
                self.assertEqual(
                    result["evolution"]["project_route"]["configuration_grade"],
                    "failing",
                )

    def test_rapid_external_failure_penalizes_but_does_not_strengthen(self):
        created = self.create_visible_agent()
        report = self.low_quality_report(
            created["agent_id"], attribution="tool_or_environment"
        )
        report.update(
            evolution_mode="rapid",
            failure_reason="tool_failure",
        )
        result = self.lifecycle.record_evaluation(report)
        self.assertGreater(result["evolution"]["penalty_points"], 0)
        self.assertIsNone(result["evolution"]["resource_challenger"])
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM resource_challengers")["count"],
            0,
        )
        second = self.low_quality_report(
            created["agent_id"], attribution="tool_or_environment"
        )
        second.update(evolution_mode="rapid", failure_reason="tool_failure")
        repeated = self.lifecycle.record_evaluation(second)
        self.assertIsNone(repeated["evolution"]["resource_challenger"])
        self.assertEqual(
            repeated["evolution"]["configuration_observation"]["major_failure_count"],
            0,
        )
        self.assertEqual(
            repeated["evolution"]["project_route"]["major_failure_count"], 0
        )

    def test_rapid_critical_retirement_precedes_profile_and_competition(self):
        created = self.create_visible_agent()
        report = self.critical_report(created["agent_id"])
        report["evolution_mode"] = "rapid"
        report["routing"] = self.routing(attribution="model_capacity")
        result = self.lifecycle.record_evaluation(report)
        self.assertEqual(result["state"], "retire_eligible")
        self.assertEqual(
            result["evolution"]["outcome"], "retirement_precedes_evolution"
        )
        self.assertIsNone(result["evolution"]["resource_challenger"])
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM agent_profiles")["count"], 0
        )
        self.assertEqual(
            self.db_row(
                "SELECT COUNT(*) AS count FROM configuration_observations"
            )["count"],
            0,
        )
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM project_routes")["count"], 0
        )

    def test_rapid_challenger_critical_event_retires_before_evolution(self):
        created = self.create_visible_agent()
        baseline = self.high_report(created["agent_id"])
        baseline["evolution_mode"] = "rapid"
        baseline["routing"] = self.routing(attribution="compute_latency")
        staged = self.lifecycle.record_evaluation(baseline)["evolution"][
            "resource_challenger"
        ]

        critical = self.critical_report(created["agent_id"])
        critical.update(
            evolution_mode="rapid",
            challenger_id=staged["challenger_id"],
        )
        critical["routing"] = self.routing(
            model=staged["model"],
            effort=staged["reasoning_effort"],
            service_tier=staged["service_tier"],
            attribution="model_capacity",
            execution_mode="explicit_fallback",
        )
        result = self.lifecycle.record_evaluation(critical)
        self.assertEqual(result["state"], "retire_eligible")
        self.assertEqual(
            result["evolution"]["outcome"], "retirement_precedes_evolution"
        )
        self.assertTrue(
            result["evolution"]["challenger_resolution"][
                "retirement_precedes_competition"
            ]
        )
        profile = self.db_row(
            "SELECT * FROM agent_profiles WHERE agent_id=?", (created["agent_id"],)
        )
        self.assertEqual(profile["reputation_score"], 100)
        self.assertEqual(profile["low_score_count"], 0)
        self.assertEqual(
            self.db_row(
                "SELECT COUNT(*) AS count FROM resource_challengers WHERE status='staged'"
            )["count"],
            0,
        )
        self.assertEqual(
            self.db_row(
                "SELECT COUNT(*) AS count FROM configuration_observations"
            )["count"],
            1,
        )

    def test_major_failures_are_isolated_by_project_key(self):
        created = self.create_visible_agent()
        project_a = "p_" + "a" * 64
        project_b = "p_" + "b" * 64

        for project_key in (project_a, project_b):
            report = self.low_quality_report(created["agent_id"])
            report.update(evolution_mode="rapid", project_key=project_key)
            result = self.lifecycle.record_evaluation(report)
            self.assertIsNone(result["evolution"]["resource_challenger"])
            self.assertEqual(
                result["evolution"]["project_route"]["configuration_grade"],
                "watch",
            )

        second_a = self.low_quality_report(created["agent_id"])
        second_a.update(evolution_mode="rapid", project_key=project_a)
        failed_a = self.lifecycle.record_evaluation(second_a)
        self.assertEqual(
            failed_a["evolution"]["project_route"]["configuration_grade"],
            "failing",
        )
        self.assertIsNotNone(failed_a["evolution"]["resource_challenger"])
        route_b = self.db_row(
            """SELECT * FROM project_routes
               WHERE agent_id=? AND project_key=? AND task_class='review'
                 AND risk_tier='read_only'""",
            (created["agent_id"], project_b),
        )
        self.assertEqual(route_b["major_failure_count"], 1)
        self.assertEqual(route_b["configuration_grade"], "watch")
        recommendation_a = self.lifecycle.recommend_route(
            created["agent_id"],
            "review",
            "read_only",
            "managed_named",
            "standard",
            project_a,
        )
        recommendation_b = self.lifecycle.recommend_route(
            created["agent_id"],
            "review",
            "read_only",
            "managed_named",
            "standard",
            project_b,
        )
        self.assertEqual(recommendation_a["action"], "compete")
        self.assertNotEqual(recommendation_b["action"], "compete")

    def test_major_failures_are_isolated_by_requested_configuration(self):
        created = self.create_visible_agent()
        project_key = "p_" + "9" * 64
        incumbent = self.low_quality_report(created["agent_id"])
        incumbent.update(evolution_mode="rapid", project_key=project_key)
        self.lifecycle.record_evaluation(incumbent)

        other_effort = self.low_quality_report(
            created["agent_id"], effort="xhigh"
        )
        other_effort.update(evolution_mode="rapid", project_key=project_key)
        other_effort["routing"] = self.routing(
            effort="xhigh",
            attribution="model_capacity",
            execution_mode="explicit_fallback",
        )
        separate = self.lifecycle.record_evaluation(other_effort)
        self.assertIsNone(separate["evolution"]["resource_challenger"])
        connection = sqlite3.connect(self.lifecycle.db_path)
        try:
            counts = [
                row[0]
                for row in connection.execute(
                    """SELECT SUM(major_failure)
                       FROM configuration_observations
                       WHERE agent_id=? AND project_key=?
                       GROUP BY requested_model, requested_reasoning_effort,
                                requested_service_tier
                       ORDER BY requested_reasoning_effort""",
                    (created["agent_id"], project_key),
                ).fetchall()
            ]
        finally:
            connection.close()
        self.assertEqual(counts, [1, 1])

        second_incumbent = self.low_quality_report(created["agent_id"])
        second_incumbent.update(evolution_mode="rapid", project_key=project_key)
        failed = self.lifecycle.record_evaluation(second_incumbent)
        self.assertIsNotNone(failed["evolution"]["resource_challenger"])

    def test_high_and_low_runs_share_one_configuration_observation_pool(self):
        created = self.create_visible_agent()
        project_key = "p_" + "c" * 64
        high = self.high_report(created["agent_id"])
        high.update(
            evolution_mode="rapid",
            project_key=project_key,
            routing=self.routing(attribution="compute_latency"),
        )
        self.lifecycle.record_evaluation(high)

        low = self.high_report(created["agent_id"], experience=False)
        low["scores"] = {
            "correctness": 28,
            "evidence": 16,
            "scope": 13,
            "efficiency": 10,
            "clarity": 8,
            "safety": 5,
        }
        low.update(
            evolution_mode="rapid",
            project_key=project_key,
            routing=self.routing(attribution="model_capacity"),
        )
        self.lifecycle.record_evaluation(low)

        major = self.low_quality_report(created["agent_id"])
        major.update(evolution_mode="rapid", project_key=project_key)
        result = self.lifecycle.record_evaluation(major)
        self.assertEqual(
            self.db_row(
                """SELECT COUNT(*) AS count FROM configuration_observations
                   WHERE agent_id=? AND project_key=?""",
                (created["agent_id"], project_key),
            )["count"],
            3,
        )
        self.assertEqual(
            self.db_row(
                """SELECT SUM(high_quality) AS high_count,
                          SUM(low_score) AS low_count,
                          SUM(major_failure) AS major_count
                   FROM configuration_observations
                   WHERE agent_id=? AND project_key=?""",
                (created["agent_id"], project_key),
            )["high_count"],
            1,
        )
        aggregate = self.db_row(
            """SELECT SUM(low_score) AS low_count,
                      SUM(major_failure) AS major_count
               FROM configuration_observations
               WHERE agent_id=? AND project_key=?""",
            (created["agent_id"], project_key),
        )
        self.assertEqual(aggregate["low_count"], 2)
        self.assertEqual(aggregate["major_count"], 1)
        self.assertEqual(
            result["evolution"]["configuration_observation"]["major_failure_count"],
            1,
        )

    def test_major_failure_replay_is_idempotent(self):
        created = self.create_visible_agent()
        project_key = "p_" + "d" * 64
        first = self.low_quality_report(created["agent_id"])
        first.update(evolution_mode="rapid", project_key=project_key)
        self.lifecycle.record_evaluation(first)
        second = self.low_quality_report(created["agent_id"])
        second.update(evolution_mode="rapid", project_key=project_key)
        recorded = self.lifecycle.record_evaluation(second)
        replay = self.lifecycle.record_evaluation(second)
        self.assertEqual(replay["action"], "evaluation_already_recorded")
        self.assertEqual(replay["evaluation_id"], recorded["evaluation_id"])
        self.assertEqual(
            self.db_row(
                """SELECT COUNT(*) AS count FROM configuration_observations
                   WHERE agent_id=? AND project_key=?""",
                (created["agent_id"], project_key),
            )["count"],
            2,
        )
        route = self.db_row(
            """SELECT * FROM project_routes
               WHERE agent_id=? AND project_key=?""",
            (created["agent_id"], project_key),
        )
        self.assertEqual(route["major_failure_count"], 2)
        self.assertEqual(route["configuration_grade"], "failing")
        self.assertEqual(
            self.db_row(
                """SELECT COUNT(*) AS count FROM resource_challengers
                   WHERE agent_id=? AND project_key=?""",
                (created["agent_id"], project_key),
            )["count"],
            1,
        )

    def test_configuration_stays_failing_after_a_third_major_failure(self):
        created = self.create_visible_agent()
        project_key = "p_" + "5" * 64
        result = None
        for _ in range(3):
            report = self.low_quality_report(created["agent_id"])
            report.update(evolution_mode="rapid", project_key=project_key)
            result = self.lifecycle.record_evaluation(report)
        assert result is not None
        observation = result["evolution"]["configuration_observation"]
        self.assertEqual(observation["major_failure_count"], 3)
        self.assertFalse(observation["configuration_became_failing"])
        self.assertTrue(observation["configuration_failing_after"])
        self.assertEqual(
            result["evolution"]["project_route"]["configuration_grade"],
            "failing",
        )

    def test_effective_mismatch_cannot_fail_or_win_for_requested_configuration(self):
        created = self.create_visible_agent()
        project_key = "p_" + "4" * 64
        for _ in range(2):
            report = self.low_quality_report(created["agent_id"])
            report.update(evolution_mode="rapid", project_key=project_key)
            report["routing"] = self.routing(
                attribution="model_capacity", effective=True
            )
            report["routing"]["effective_model"] = "gpt-5.6-sol"
            result = self.lifecycle.record_evaluation(report)
        self.assertEqual(
            result["evolution"]["project_route"]["major_failure_count"], 0
        )
        self.assertIsNone(result["evolution"]["resource_challenger"])

        baseline = self.high_report(created["agent_id"])
        baseline.update(
            evolution_mode="rapid",
            project_key=project_key,
            routing=self.routing(attribution="compute_latency"),
        )
        staged = self.lifecycle.record_evaluation(baseline)["evolution"][
            "resource_challenger"
        ]
        challenger = self.high_report(created["agent_id"])
        challenger["experience"] = {
            "key": "reject-mismatched-effective-challenger",
            "rule": "Reject a challenger when the confirmed effective route differs from its request.",
            "applies_to": "review",
        }
        challenger.update(
            evolution_mode="rapid",
            project_key=project_key,
            challenger_id=staged["challenger_id"],
        )
        challenger["routing"] = self.routing(
            model=staged["model"],
            effort=staged["reasoning_effort"],
            service_tier=staged["service_tier"],
            attribution="model_capacity",
            execution_mode="explicit_fallback",
            effective=True,
        )
        challenger["routing"]["effective_model"] = "gpt-5.6-terra"
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(challenger)

    def test_two_latency_failures_can_stage_a_faster_single_axis_route(self):
        created = self.create_visible_agent()
        project_key = "p_" + "e" * 64
        for ordinal in range(2):
            report = self.low_quality_report(
                created["agent_id"],
                task_class="documentation",
                attribution="compute_latency",
            )
            report.update(
                evolution_mode="rapid",
                project_key=project_key,
                failure_reason="timeout",
                duration_bucket="high",
            )
            result = self.lifecycle.record_evaluation(report)
            if ordinal == 0:
                self.assertIsNone(result["evolution"]["resource_challenger"])
        challenger = result["evolution"]["resource_challenger"]
        self.assertEqual(challenger["changed_axis"], "reasoning_effort")
        self.assertEqual(challenger["model"], "gpt-5.6-terra")
        self.assertEqual(challenger["reasoning_effort"], "medium")

    def test_unknown_failure_reason_does_not_fail_a_configuration(self):
        created = self.create_visible_agent()
        project_key = "p_" + "7" * 64
        for _ in range(2):
            report = self.low_quality_report(created["agent_id"])
            report.update(
                evolution_mode="rapid",
                project_key=project_key,
                failure_reason="none",
            )
            result = self.lifecycle.record_evaluation(report)
        self.assertIsNone(result["evolution"]["resource_challenger"])
        self.assertEqual(
            result["evolution"]["project_route"]["major_failure_count"], 0
        )

    def test_cost_failure_requires_high_resource_evidence_before_single_axis_route(self):
        created = self.create_visible_agent()
        project_key = "p_" + "8" * 64
        for _ in range(2):
            unknown_cost = self.low_quality_report(
                created["agent_id"], task_class="documentation"
            )
            unknown_cost.update(
                evolution_mode="rapid",
                project_key=project_key,
                failure_reason="cost_overrun",
                token_bucket="unknown",
                credit_bucket="unknown",
            )
            ignored = self.lifecycle.record_evaluation(unknown_cost)
        self.assertEqual(
            ignored["evolution"]["project_route"]["major_failure_count"], 0
        )
        self.assertIsNone(ignored["evolution"]["resource_challenger"])

        evidenced_key = "p_" + "6" * 64
        for ordinal in range(2):
            evidenced = self.low_quality_report(
                created["agent_id"], task_class="documentation"
            )
            evidenced.update(
                evolution_mode="rapid",
                project_key=evidenced_key,
                failure_reason="cost_overrun",
                token_bucket="high",
                credit_bucket="high",
            )
            result = self.lifecycle.record_evaluation(evidenced)
            if ordinal == 0:
                self.assertIsNone(result["evolution"]["resource_challenger"])
        challenger = result["evolution"]["resource_challenger"]
        self.assertEqual(challenger["changed_axis"], "reasoning_effort")
        self.assertEqual(challenger["reasoning_effort"], "medium")

    def test_rapid_low_challenger_is_penalized_and_cannot_spawn_another(self):
        created = self.create_visible_agent()
        baseline = self.high_report(created["agent_id"])
        baseline["evolution_mode"] = "rapid"
        baseline["routing"] = self.routing(attribution="compute_latency")
        staged = self.lifecycle.record_evaluation(baseline)["evolution"][
            "resource_challenger"
        ]

        failed = self.low_quality_report(
            created["agent_id"],
            model=staged["model"],
            effort=staged["reasoning_effort"],
            attribution="model_capacity",
        )
        failed.update(
            evolution_mode="rapid",
            challenger_id=staged["challenger_id"],
        )
        failed["routing"] = self.routing(
            model=staged["model"],
            effort=staged["reasoning_effort"],
            service_tier=staged["service_tier"],
            attribution="model_capacity",
            execution_mode="explicit_fallback",
        )
        result = self.lifecycle.record_evaluation(failed)
        self.assertEqual(result["evolution"]["penalty_points"], 6)
        self.assertEqual(result["evolution"]["reputation_after"], 94)
        self.assertEqual(
            result["evolution"]["challenger_resolution"]["status"], "lost"
        )
        self.assertIsNone(result["evolution"]["resource_challenger"])
        profile = self.db_row(
            "SELECT * FROM agent_profiles WHERE agent_id=?", (created["agent_id"],)
        )
        self.assertEqual(profile["low_score_count"], 1)
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM resource_challengers")["count"],
            1,
        )

    def test_new_champion_requires_its_own_baseline_before_more_neighbors(self):
        created = self.create_visible_agent()

        def documentation_report(key, rule):
            report = self.high_report(created["agent_id"])
            report["task_class"] = "documentation"
            report["experience"] = {
                "key": key,
                "rule": rule,
                "applies_to": "documentation",
            }
            report["evolution_mode"] = "rapid"
            return report

        baseline = documentation_report(
            "document-source-boundary-first",
            "Verify the source boundary before expanding documentation claims.",
        )
        baseline["routing"] = self.routing(attribution="compute_latency")
        first = self.lifecycle.record_evaluation(baseline)
        challenger = first["evolution"]["resource_challenger"]
        self.assertEqual(challenger["reasoning_effort"], "medium")

        winner = documentation_report(
            "prefer-measured-resource-winner",
            "Prefer a resource challenger only after its measured objective wins.",
        )
        winner["scores"] = {
            "correctness": 35,
            "evidence": 20,
            "scope": 15,
            "efficiency": 15,
            "clarity": 10,
            "safety": 5,
        }
        winner.update(
            duration_bucket="low",
            credit_bucket="low",
            challenger_id=challenger["challenger_id"],
        )
        winner["routing"] = self.routing(
            model=challenger["model"],
            effort=challenger["reasoning_effort"],
            service_tier=challenger["service_tier"],
            attribution="compute_latency",
            execution_mode="explicit_fallback",
        )
        won = self.lifecycle.record_evaluation(winner)
        self.assertTrue(won["evolution"]["challenger_resolution"]["won"])
        next_challenger = won["evolution"]["resource_challenger"]
        self.assertIsNotNone(next_challenger)

        connection = self.lifecycle.connect(create=True)
        assert connection is not None
        try:
            connection.execute(
                """UPDATE resource_challengers
                   SET status='lost', resolved_at=? WHERE challenger_id=?""",
                (manage_agents.utc_now(), next_challenger["challenger_id"]),
            )
        finally:
            connection.close()

        old_named = documentation_report(
            "do-not-mix-old-route-baseline",
            "Do not compare a new champion neighbor against an old named-route baseline.",
        )
        old_named["routing"] = self.routing(attribution="compute_latency")
        blocked = self.lifecycle.record_evaluation(old_named)
        self.assertEqual(
            blocked["evolution"]["competition_status"],
            "champion_baseline_not_run",
        )
        self.assertIsNone(blocked["evolution"]["resource_challenger"])

        champion = documentation_report(
            "run-champion-before-next-neighbor",
            "Run the preferred champion route before staging its next resource neighbor.",
        )
        champion["routing"] = self.routing(
            model=challenger["model"],
            effort=challenger["reasoning_effort"],
            service_tier=challenger["service_tier"],
            attribution="compute_latency",
            execution_mode="explicit_fallback",
        )
        resumed = self.lifecycle.record_evaluation(champion)
        self.assertEqual(
            resumed["evolution"]["competition_status"], "challenger_staged"
        )
        self.assertIsNotNone(resumed["evolution"]["resource_challenger"])

    def test_stagnation_supervisor_requires_repeated_comparable_evidence(self):
        created = self.create_visible_agent()
        plan = self.variation_plan(created["agent_id"], trigger="stagnation")
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.plan_variation(plan)

        for _ in range(3):
            report = self.low_quality_report(created["agent_id"])
            report.update(
                credit_bucket="expected",
                retry_count=1,
                rework_count=1,
                failure_reason="missing_evidence",
            )
            self.lifecycle.record_evaluation(report)

        status = self.lifecycle.stagnation_status(
            created["agent_id"], "review", "read_only"
        )
        self.assertTrue(status["eligible"])
        self.assertIn("repeated_failure:missing_evidence", status["reason_codes"])
        metrics = self.db_row(
            "SELECT * FROM evaluation_metrics ORDER BY rowid DESC LIMIT 1"
        )
        self.assertEqual(metrics["credit_bucket"], "expected")
        self.assertEqual(metrics["failure_reason"], "missing_evidence")

        planned = self.lifecycle.plan_variation(plan)
        self.assertTrue(planned["supervisor"]["allowed"])
        staged = self.lifecycle.stage_variation(
            self.variation_stage(
                planned["session_id"],
                supervisor_direction="Reduce repeated evidence omissions before changing model size.",
            )
        )
        self.assertEqual(staged["status"], "staged")
        self.assertFalse(staged["promotion_eligible"])

    def test_stagnation_ignores_low_confidence_and_weak_evidence(self):
        cases = (
            ("low-confidence", "parent", "low", ["source_verified", "scope_audit"]),
            ("weak-evidence", "independent_model", "high", ["scope_audit", "safety_audit"]),
        )
        for slug, judge, confidence, evidence_flags in cases:
            with self.subTest(slug=slug):
                created = self.lifecycle.create_agent(
                    self.spec(slug=slug), self.project_root
                )
                self.lifecycle.confirm_visible(created["agent_id"])
                for _ in range(4):
                    report = self.low_quality_report(created["agent_id"])
                    report["judge_kind"] = judge
                    report["judge_confidence"] = confidence
                    report["evidence_flags"] = evidence_flags
                    self.lifecycle.record_evaluation(report)
                status = self.lifecycle.stagnation_status(
                    created["agent_id"], "review", "read_only"
                )
                self.assertFalse(status["eligible"])
                self.assertEqual(status["comparable_evaluation_count"], 0)
                self.assertEqual(status["excluded_evaluation_count"], 4)

    def test_stagnation_status_does_not_recover_pending_file_operation(self):
        created = self.create_visible_agent()
        source = Path(created["path"])
        destination = self.lifecycle.quarantine_dir / created["agent_id"] / source.name
        self.insert_move_intent(
            agent_id=created["agent_id"],
            operation="quarantine",
            source=source,
            destination=destination,
            target_state="quarantined",
        )
        before = source.read_bytes()

        status = self.lifecycle.stagnation_status(
            created["agent_id"], "review", "read_only"
        )
        self.assertEqual(status["status"], "recovery_required")
        self.assertEqual(status["pending_operations"], 1)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse(destination.exists())
        operation = self.db_row("SELECT stage FROM operations")
        self.assertEqual(operation["stage"], "prepared")

    def test_bounded_variation_stages_then_uses_existing_promotion_gate(self):
        created = self.create_visible_agent()
        incumbent = Path(created["path"]).read_bytes()
        lease = self.lifecycle.acquire_lease(created["agent_id"], 120)
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.plan_variation(self.variation_plan(created["agent_id"]))
        self.lifecycle.release_lease(lease["lease_id"])

        planned = self.lifecycle.plan_variation(self.variation_plan(created["agent_id"]))
        over_budget = self.variation_stage(planned["session_id"], elapsed=301)
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.stage_variation(over_budget)

        staged = self.lifecycle.stage_variation(
            self.variation_stage(planned["session_id"])
        )
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent)
        variation_candidate_id = staged["candidates"][0]["variation_candidate_id"]
        late_shadow = self.variation_verification(variation_candidate_id)
        late_shadow["elapsed_seconds_total"] = 301
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.verify_variation(late_shadow)
        verified = self.lifecycle.verify_variation(
            self.variation_verification(variation_candidate_id)
        )
        self.assertTrue(verified["promotion_eligible"])
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent)

        promoted = self.lifecycle.promote_candidate(
            self.promotion(verified["candidate_id"])
        )
        self.assertEqual(promoted["revision"], 2)
        self.assertFalse(promoted["toml_modified"])
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent)

    def test_routing_report_rejects_false_effective_values_and_named_mismatch(self):
        created = self.create_visible_agent()
        unknown = self.high_report(created["agent_id"], experience=False)
        unknown["routing"] = self.routing(
            attribution="compute_latency", host_status="unexposed"
        )
        result = self.lifecycle.record_evaluation(unknown)
        row = self.db_row(
            "SELECT * FROM evaluation_routing WHERE evaluation_id=?",
            (result["evaluation_id"],),
        )
        self.assertIsNone(row["effective_model"])
        self.assertIsNone(row["effective_reasoning_effort"])
        self.assertIsNone(row["effective_service_tier"])

        false_effective = self.high_report(created["agent_id"], experience=False)
        false_effective["routing"] = self.routing(effective=True)
        false_effective["routing"]["host_config_status"] = "unexposed"
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(false_effective)

        accepted_only = self.high_report(created["agent_id"], experience=False)
        accepted_only["routing"] = self.routing(effective=True)
        accepted_only["routing"]["host_config_status"] = "request_accepted"
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(accepted_only)

        mismatch = self.high_report(created["agent_id"], experience=False)
        mismatch["routing"] = self.routing(model="gpt-5.6-luna", effort="medium")
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(mismatch)
        self.assertEqual(self.db_row("SELECT COUNT(*) AS count FROM evaluations")["count"], 1)

    def test_repeated_low_quality_recommends_one_axis_model_upgrade(self):
        created = self.create_visible_agent()
        first = self.lifecycle.record_evaluation(self.low_quality_report(created["agent_id"]))
        self.assertEqual(first["configuration_recommendation"]["action"], "watch")
        self.assertIsNone(first["configuration_recommendation"]["recommended"])
        for _ in range(2):
            self.lifecycle.record_evaluation(self.low_quality_report(created["agent_id"]))
        result = None
        for _ in range(2):
            report = self.high_report(created["agent_id"], experience=False)
            report["routing"] = self.routing(attribution="model_capacity")
            result = self.lifecycle.record_evaluation(report)
        assert result is not None
        recommendation = result["configuration_recommendation"]
        self.assertEqual(recommendation["action"], "strengthen")
        self.assertEqual(recommendation["changed_axis"], "model")
        self.assertEqual(recommendation["recommended"]["model"], "gpt-5.6-sol")
        self.assertEqual(recommendation["recommended"]["reasoning_effort"], "high")
        self.assertEqual(recommendation["recommended"]["service_tier"], "standard")
        self.assertTrue(recommendation["toml_modified"] is False)

    def test_high_quality_slow_expensive_agent_recommends_lower_effort(self):
        created = self.lifecycle.create_agent(
            self.spec(model="gpt-5.6-sol", model_reasoning_effort="xhigh"),
            self.project_root,
        )
        self.lifecycle.confirm_visible(created["agent_id"])
        incumbent = Path(created["path"]).read_bytes()
        result = None
        for _ in range(5):
            result = self.lifecycle.record_evaluation(
                self.high_quality_slow_report(
                    created["agent_id"],
                    model="gpt-5.6-sol",
                    effort="xhigh",
                    task_class="review",
                )
            )
        assert result is not None
        recommendation = result["configuration_recommendation"]
        self.assertEqual(recommendation["action"], "economize")
        self.assertEqual(recommendation["changed_axis"], "reasoning")
        self.assertEqual(recommendation["recommended"]["model"], "gpt-5.6-sol")
        self.assertEqual(recommendation["recommended"]["reasoning_effort"], "high")
        self.assertEqual(recommendation["recommended"]["service_tier"], "standard")
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent)

    def test_speed_bias_routes_low_and_medium_cost_agents_to_fast(self):
        cases = (
            ("speed-low", "gpt-5.6-luna", "medium", "documentation"),
            ("speed-medium", "gpt-5.6-terra", "high", "review"),
        )
        for slug, model, effort, task_class in cases:
            with self.subTest(model=model, effort=effort):
                created = self.lifecycle.create_agent(
                    self.spec(
                        slug=slug,
                        model=model,
                        model_reasoning_effort=effort,
                    ),
                    self.project_root,
                )
                self.lifecycle.confirm_visible(created["agent_id"])
                result = None
                for _ in range(3):
                    result = self.lifecycle.record_evaluation(
                        self.high_quality_slow_report(
                            created["agent_id"],
                            model=model,
                            effort=effort,
                            task_class=task_class,
                        )
                    )
                assert result is not None
                recommendation = result["configuration_recommendation"]
                self.assertEqual(recommendation["action"], "speed_up")
                self.assertEqual(recommendation["changed_axis"], "service_tier")
                self.assertEqual(recommendation["recommended"]["service_tier"], "fast")
                self.assertEqual(recommendation["application"], "recommendation_only")
                self.assertEqual(recommendation["requires_shadow_cases"], 0)
                self.assertEqual(recommendation["policy_version"], 2)
                self.assertTrue(recommendation["requires_user_confirmation"])

    def test_effective_service_tier_mismatch_is_not_comparable(self):
        self.assertTrue(manage_agents.service_tier_matches_request("fast", "priority"))
        self.assertFalse(manage_agents.service_tier_matches_request("standard", "priority"))
        self.assertFalse(manage_agents.service_tier_matches_request("inherit", "priority"))
        created = self.lifecycle.create_agent(
            self.spec(model="gpt-5.6-luna", model_reasoning_effort="medium"),
            self.project_root,
        )
        self.lifecycle.confirm_visible(created["agent_id"])
        result = None
        for _ in range(3):
            report = self.high_quality_slow_report(
                created["agent_id"],
                model="gpt-5.6-luna",
                effort="medium",
                task_class="documentation",
                service_tier="standard",
            )
            report["routing"].update(
                effective_model="gpt-5.6-luna",
                effective_reasoning_effort="medium",
                effective_service_tier="fast",
                host_config_status="effective_confirmed",
            )
            result = self.lifecycle.record_evaluation(report)
        assert result is not None
        recommendation = result["configuration_recommendation"]
        self.assertNotEqual(recommendation["action"], "speed_up")
        self.assertEqual(recommendation["evidence_window"]["comparable_rows"], 0)

    def test_high_cost_fast_policy_recommends_standard_without_mutation(self):
        created = self.lifecycle.create_agent(
            self.spec(model="gpt-5.6-sol", model_reasoning_effort="high"),
            self.project_root,
        )
        self.lifecycle.confirm_visible(created["agent_id"])
        incumbent = Path(created["path"]).read_bytes()
        recommendation = self.lifecycle.recommend_route(
            created["agent_id"], "review", "read_only", "managed_named", "fast"
        )
        self.assertEqual(recommendation["action"], "standardize_speed")
        self.assertEqual(recommendation["recommended"]["service_tier"], "standard")
        self.assertEqual(recommendation["application"], "recommendation_only")
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent)

    def test_cli_recommend_route_parses_arguments_and_emits_json(self):
        created = self.lifecycle.create_agent(
            self.spec(model="gpt-5.6-sol", model_reasoning_effort="high"),
            self.project_root,
        )
        self.lifecycle.confirm_visible(created["agent_id"])
        incumbent = Path(created["path"]).read_bytes()
        process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--codex-home",
                str(self.codex_home),
                "recommend-route",
                "--agent-id",
                created["agent_id"],
                "--task-class",
                "review",
                "--risk-tier",
                "read_only",
                "--execution-mode",
                "managed_named",
                "--service-tier",
                "fast",
            ],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        recommendation = json.loads(process.stdout)
        self.assertEqual(recommendation["action"], "standardize_speed")
        self.assertEqual(recommendation["recommended"]["service_tier"], "standard")
        self.assertEqual(recommendation["application"], "recommendation_only")
        self.assertEqual(Path(created["path"]).read_bytes(), incumbent)

    def test_cli_help_exposes_bounded_variation_commands(self):
        process = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        for command in (
            "stagnation-status",
            "variation-plan",
            "variation-stage",
            "variation-verify",
        ):
            self.assertIn(command, process.stdout)

    def test_speed_bias_respects_token_and_explicit_tier_guards(self):
        cases = (
            ("high-token-guard", "standard", True),
            ("inherit-tier-guard", "inherit", False),
            ("unknown-tier-guard", "unknown", False),
        )
        for slug, service_tier, high_tokens in cases:
            with self.subTest(service_tier=service_tier, high_tokens=high_tokens):
                created = self.lifecycle.create_agent(
                    self.spec(
                        slug=slug,
                        model="gpt-5.6-luna",
                        model_reasoning_effort="medium",
                    ),
                    self.project_root,
                )
                self.lifecycle.confirm_visible(created["agent_id"])
                result = None
                for _ in range(3):
                    report = self.high_quality_slow_report(
                        created["agent_id"],
                        model="gpt-5.6-luna",
                        effort="medium",
                        task_class="documentation",
                        service_tier=service_tier,
                    )
                    if high_tokens:
                        report["token_bucket"] = "high"
                    result = self.lifecycle.record_evaluation(report)
                assert result is not None
                recommendation = result["configuration_recommendation"]
                self.assertNotEqual(recommendation["action"], "speed_up")
                self.assertIsNone(recommendation["recommended"])

    def test_active_lease_blocks_evaluation_and_promotion(self):
        created = self.create_visible_agent()
        lease = self.lifecycle.acquire_lease(created["agent_id"], 120)
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
        self.lifecycle.release_lease(lease["lease_id"])
        outputs = [
            self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
            for _ in range(3)
        ]
        candidate_id = outputs[-1]["candidate_id"]
        lease = self.lifecycle.acquire_lease(created["agent_id"], 120)
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.promote_candidate(self.promotion(candidate_id))
        self.lifecycle.release_lease(lease["lease_id"])
        promoted = self.lifecycle.promote_candidate(self.promotion(candidate_id))
        self.assertEqual(promoted["revision"], 2)

    def test_retirement_precedes_resource_routing(self):
        created = self.create_visible_agent()
        report = self.critical_report(created["agent_id"])
        report["routing"] = self.routing(attribution="model_capacity")
        result = self.lifecycle.record_evaluation(report)
        self.assertEqual(result["state"], "retire_eligible")
        self.assertEqual(result["retirement_reason"], "unauthorized_destructive_write")
        self.assertEqual(
            result["configuration_recommendation"]["status"],
            "retirement_precedes_routing",
        )
        self.assertIsNone(result["configuration_recommendation"]["recommended"])

    def test_repeated_evidence_backed_extreme_failure_quarantines_and_restores(self):
        created = self.create_visible_agent()
        results = [
            self.lifecycle.record_evaluation(self.extreme_report(created["agent_id"]))
            for _ in range(3)
        ]
        self.assertNotEqual(results[0]["state"], "retire_eligible")
        self.assertNotEqual(results[1]["state"], "retire_eligible")
        self.assertEqual(results[-1]["state"], "retire_eligible")
        retired = self.lifecycle.retire_agent(created["agent_id"])
        self.assertTrue(retired["recoverable"])
        self.assertFalse(Path(created["path"]).exists())
        quarantine = Path(retired["quarantine_path"])
        self.assertTrue(quarantine.exists())
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.restore_agent(created["agent_id"], "wrong", self.project_root)
        restored = self.lifecycle.restore_agent(
            created["agent_id"], f"restore:{created['agent_id']}", self.project_root
        )
        self.assertEqual(restored["state"], "pending_reload")
        self.assertTrue(Path(created["path"]).exists())
        self.assertFalse(quarantine.exists())

    def test_recover_commits_quarantine_and_restore_after_file_move(self):
        created = self.create_visible_agent()
        self.lifecycle.record_evaluation(self.critical_report(created["agent_id"]))
        source = Path(created["path"])
        destination_dir = self.lifecycle.quarantine_dir / created["agent_id"]
        destination_dir.mkdir(parents=True)
        row = self.db_row("SELECT * FROM agents WHERE agent_id=?", (created["agent_id"],))
        quarantine = destination_dir / f"revision-{row['revision']}-{row['expected_sha256'][:12]}.toml"
        quarantine_operation = self.insert_move_intent(
            agent_id=created["agent_id"],
            operation="quarantine",
            source=source,
            destination=quarantine,
            target_state="quarantined",
        )
        manage_agents.move_no_replace(source, quarantine)
        recovered = self.lifecycle.recover()
        self.assertIn(
            {"operation_id": quarantine_operation, "result": "committed_after_move"},
            recovered["results"],
        )
        row = self.db_row("SELECT * FROM agents WHERE agent_id=?", (created["agent_id"],))
        self.assertEqual(row["state"], "quarantined")

        restore_operation = self.insert_move_intent(
            agent_id=created["agent_id"],
            operation="restore",
            source=quarantine,
            destination=source,
            target_state="pending_reload",
        )
        manage_agents.move_no_replace(quarantine, source)
        recovered = self.lifecycle.recover()
        self.assertIn(
            {"operation_id": restore_operation, "result": "committed_after_move"},
            recovered["results"],
        )
        row = self.db_row("SELECT * FROM agents WHERE agent_id=?", (created["agent_id"],))
        self.assertEqual(row["state"], "pending_reload")
        self.assertIsNone(row["quarantine_path"])
        self.assertTrue(source.exists())

    def test_record_retry_is_idempotent_by_run_id(self):
        created = self.create_visible_agent()
        invalid = self.high_report(created["agent_id"])
        invalid["raw_trace"] = "must never be stored"
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(invalid)
        self.assertEqual(self.db_row("SELECT COUNT(*) AS count FROM evaluations")["count"], 0)

        report = self.high_report(created["agent_id"])
        first = self.lifecycle.record_evaluation(report)
        second = self.lifecycle.record_evaluation(report)
        third = self.lifecycle.record_evaluation(report)
        self.assertEqual(second["action"], "evaluation_already_recorded")
        self.assertEqual(third["evaluation_id"], first["evaluation_id"])
        self.assertEqual(third["experience_observation_count"], 1)
        row = self.db_row("SELECT COUNT(*) AS count FROM evaluations")
        self.assertEqual(row["count"], 1)
        changed = json.loads(json.dumps(report))
        changed["scores"]["clarity"] -= 1
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(changed)

    def test_run_id_remains_single_run_across_guarded_revisions(self):
        created = self.create_visible_agent()
        original = self.high_report(created["agent_id"])
        self.lifecycle.record_evaluation(original)
        self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
        third = self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
        self.lifecycle.promote_candidate(self.promotion(third["candidate_id"]))

        replay = self.lifecycle.record_evaluation(original)
        self.assertEqual(replay["action"], "evaluation_already_recorded")
        self.assertEqual(replay["revision"], 2)
        self.assertEqual(
            self.db_row("SELECT COUNT(*) AS count FROM evaluations")["count"], 3
        )
        changed = json.loads(json.dumps(original))
        changed["scores"]["clarity"] -= 1
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(changed)

    def test_v1_database_migrates_to_v6_without_touching_agents(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-home")
        lifecycle.state_root.mkdir(parents=True)
        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta(key, value) VALUES('schema_version', '1');
                CREATE TABLE evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
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
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

        migrated = lifecycle.connect(create=True)
        assert migrated is not None
        try:
            version = migrated.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()["value"]
            tables = {
                row["name"]
                for row in migrated.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertEqual(version, "6")
            self.assertTrue(
                {
                    "evaluation_routing",
                    "evaluation_metrics",
                    "variation_sessions",
                    "variation_candidates",
                    "agent_profiles",
                    "evolution_actions",
                    "resource_challengers",
                    "project_routes",
                    "configuration_observations",
                }.issubset(tables)
            )
        finally:
            migrated.close()
        self.assertFalse(lifecycle.agents_dir.exists())

    def test_v2_database_migrates_to_v6_without_guessing_old_metrics(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-v2-home")
        lifecycle.state_root.mkdir(parents=True)
        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta(key, value) VALUES('schema_version', '2');
                CREATE TABLE evaluation_routing (
                    evaluation_id TEXT PRIMARY KEY,
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
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

        migrated = lifecycle.connect(create=True)
        assert migrated is not None
        try:
            version = migrated.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()["value"]
            metric_count = migrated.execute(
                "SELECT COUNT(*) AS count FROM evaluation_metrics"
            ).fetchone()["count"]
            self.assertEqual(version, "6")
            self.assertEqual(metric_count, 0)
        finally:
            migrated.close()

    def test_v3_database_migrates_to_v6_with_cumulative_budget_columns(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-v3-home")
        current = lifecycle.connect(create=True)
        assert current is not None
        current.close()

        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.execute(
                "UPDATE meta SET value='3' WHERE key='schema_version'"
            )
            for column in (
                "stage_elapsed_seconds",
                "stage_tool_calls_used",
                "stage_token_bucket_used",
                "stage_credit_bucket_used",
            ):
                connection.execute(
                    f"ALTER TABLE variation_sessions DROP COLUMN {column}"
                )
            connection.execute(
                "ALTER TABLE variation_candidates DROP COLUMN shadow_suite_sha256"
            )
            connection.commit()
        finally:
            connection.close()

        migrated = lifecycle.connect(create=True)
        assert migrated is not None
        try:
            version = migrated.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()["value"]
            session_columns = {
                row["name"]
                for row in migrated.execute(
                    "PRAGMA table_info(variation_sessions)"
                ).fetchall()
            }
            candidate_columns = {
                row["name"]
                for row in migrated.execute(
                    "PRAGMA table_info(variation_candidates)"
                ).fetchall()
            }
            self.assertEqual(version, "6")
            self.assertTrue(
                {
                    "stage_elapsed_seconds",
                    "stage_tool_calls_used",
                    "stage_token_bucket_used",
                    "stage_credit_bucket_used",
                }.issubset(session_columns)
            )
            self.assertIn("shadow_suite_sha256", candidate_columns)
        finally:
            migrated.close()

    def test_v4_database_migrates_to_v6_without_backfilling_history(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-v4-home")
        current = lifecycle.connect(create=True)
        assert current is not None
        current.close()

        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.execute("DROP TABLE evolution_actions")
            connection.execute("DROP TABLE resource_challengers")
            connection.execute("DROP TABLE agent_profiles")
            connection.execute(
                "UPDATE meta SET value='4' WHERE key='schema_version'"
            )
            connection.commit()
        finally:
            connection.close()

        migrated = lifecycle.connect(create=True)
        assert migrated is not None
        try:
            version = migrated.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()["value"]
            tables = {
                row["name"]
                for row in migrated.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertEqual(version, "6")
            self.assertTrue(
                {
                    "agent_profiles",
                    "evolution_actions",
                    "resource_challengers",
                    "project_routes",
                    "configuration_observations",
                }.issubset(tables)
            )
            self.assertEqual(
                migrated.execute(
                    "SELECT COUNT(*) AS count FROM evolution_actions"
                ).fetchone()["count"],
                0,
            )
            self.assertEqual(
                migrated.execute(
                    "SELECT COUNT(*) AS count FROM configuration_observations"
                ).fetchone()["count"],
                0,
            )
        finally:
            migrated.close()

    def test_v5_database_migrates_to_v6_without_backfill_and_replays_rapid_digest(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-v5-home")
        created = lifecycle.create_agent(self.spec(slug="migration-v5"), self.project_root)
        lifecycle.confirm_visible(created["agent_id"])
        report = self.high_report(created["agent_id"])
        report.update(
            evolution_mode="rapid",
            routing=self.routing(attribution="compute_latency"),
        )
        recorded = lifecycle.record_evaluation(report)
        normalized = manage_agents.validate_report(report)
        v5_digest = manage_agents.evaluation_report_digests(normalized)[1]

        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.execute(
                "UPDATE evaluations SET report_sha256=? WHERE evaluation_id=?",
                (v5_digest, recorded["evaluation_id"]),
            )
            connection.execute("DROP TABLE configuration_observations")
            connection.execute("DROP TABLE project_routes")
            connection.execute("DROP INDEX one_staged_resource_challenger")
            connection.execute(
                "ALTER TABLE resource_challengers DROP COLUMN project_key"
            )
            connection.execute(
                """CREATE UNIQUE INDEX one_staged_resource_challenger
                   ON resource_challengers(agent_id, task_class, risk_tier)
                   WHERE status='staged'"""
            )
            connection.execute(
                "UPDATE meta SET value='5' WHERE key='schema_version'"
            )
            connection.commit()
        finally:
            connection.close()

        migrated = lifecycle.connect(create=True)
        assert migrated is not None
        try:
            self.assertEqual(
                migrated.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()["value"],
                "6",
            )
            self.assertEqual(
                migrated.execute(
                    "SELECT COUNT(*) AS count FROM configuration_observations"
                ).fetchone()["count"],
                0,
            )
            old_challenger = migrated.execute(
                "SELECT project_key FROM resource_challengers"
            ).fetchone()
            self.assertEqual(old_challenger["project_key"], "global")
        finally:
            migrated.close()

        replay = lifecycle.record_evaluation(report)
        self.assertEqual(replay["action"], "evaluation_already_recorded")
        explicit_v6_default = json.loads(json.dumps(report))
        explicit_v6_default["failure_severity"] = "none"
        with self.assertRaises(manage_agents.LifecycleError):
            lifecycle.record_evaluation(explicit_v6_default)
        changed_project = json.loads(json.dumps(report))
        changed_project["project_key"] = "p_" + "f" * 64
        with self.assertRaises(manage_agents.LifecycleError):
            lifecycle.record_evaluation(changed_project)
        check = sqlite3.connect(lifecycle.db_path)
        try:
            self.assertEqual(
                check.execute(
                    "SELECT COUNT(*) FROM configuration_observations"
                ).fetchone()[0],
                0,
            )
        finally:
            check.close()

    def test_v5_to_v6_migration_failure_rolls_back_column_tables_and_index(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-v5-failure-home")
        current = lifecycle.connect(create=True)
        assert current is not None
        current.close()
        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.execute("DROP TABLE configuration_observations")
            connection.execute("DROP TABLE project_routes")
            connection.execute("DROP INDEX one_staged_resource_challenger")
            connection.execute(
                "ALTER TABLE resource_challengers DROP COLUMN project_key"
            )
            connection.execute(
                """CREATE UNIQUE INDEX one_staged_resource_challenger
                   ON resource_challengers(agent_id, task_class, risk_tier)
                   WHERE status='staged'"""
            )
            connection.execute(
                "UPDATE meta SET value='5' WHERE key='schema_version'"
            )
            connection.commit()
        finally:
            connection.close()

        original = manage_agents.AgentLifecycle.create_project_evolution_schema

        def fail_after_project_ddl(database):
            original(database)
            raise sqlite3.OperationalError("injected project migration failure")

        manage_agents.AgentLifecycle.create_project_evolution_schema = staticmethod(
            fail_after_project_ddl
        )
        try:
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "injected project migration failure"
            ):
                lifecycle.connect(create=True)
        finally:
            manage_agents.AgentLifecycle.create_project_evolution_schema = staticmethod(
                original
            )

        verification = sqlite3.connect(lifecycle.db_path)
        try:
            self.assertEqual(
                verification.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()[0],
                "5",
            )
            columns = {
                row[1]
                for row in verification.execute(
                    "PRAGMA table_info(resource_challengers)"
                ).fetchall()
            }
            self.assertNotIn("project_key", columns)
            self.assertIsNone(
                verification.execute(
                    """SELECT name FROM sqlite_master
                       WHERE type='table' AND name='project_routes'"""
                ).fetchone()
            )
            index_columns = [
                row[2]
                for row in verification.execute(
                    "PRAGMA index_info(one_staged_resource_challenger)"
                ).fetchall()
            ]
            self.assertEqual(
                index_columns, ["agent_id", "task_class", "risk_tier"]
            )
        finally:
            verification.close()

    def test_v5_catalog_remains_read_only_until_authorized_mutation(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "catalog-v5-home")
        created = lifecycle.create_agent(self.spec(slug="catalog-v5"), self.project_root)
        lifecycle.confirm_visible(created["agent_id"])
        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.execute("DROP TABLE configuration_observations")
            connection.execute("DROP TABLE project_routes")
            connection.execute("DROP INDEX one_staged_resource_challenger")
            connection.execute(
                "ALTER TABLE resource_challengers DROP COLUMN project_key"
            )
            connection.execute(
                """CREATE UNIQUE INDEX one_staged_resource_challenger
                   ON resource_challengers(agent_id, task_class, risk_tier)
                   WHERE status='staged'"""
            )
            connection.execute(
                "UPDATE meta SET value='5' WHERE key='schema_version'"
            )
            connection.commit()
        finally:
            connection.close()

        catalog = lifecycle.catalog(self.project_root)
        self.assertEqual(len(catalog["custom"]), 1)
        self.assertEqual(catalog["custom"][0]["project_routes"], [])
        verification = sqlite3.connect(lifecycle.db_path)
        try:
            self.assertEqual(
                verification.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()[0],
                "5",
            )
            self.assertIsNone(
                verification.execute(
                    """SELECT name FROM sqlite_master
                       WHERE type='table' AND name='project_routes'"""
                ).fetchone()
            )
        finally:
            verification.close()

    def test_v4_catalog_remains_read_only_until_authorized_mutation(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "catalog-v4-home")
        created = lifecycle.create_agent(self.spec(slug="catalog-v4"), self.project_root)
        lifecycle.confirm_visible(created["agent_id"])
        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.execute("DROP TABLE evolution_actions")
            connection.execute("DROP TABLE resource_challengers")
            connection.execute("DROP TABLE agent_profiles")
            connection.execute(
                "UPDATE meta SET value='4' WHERE key='schema_version'"
            )
            connection.commit()
        finally:
            connection.close()

        catalog = lifecycle.catalog(self.project_root)
        self.assertEqual(len(catalog["custom"]), 1)
        self.assertIsNone(catalog["custom"][0]["evolution_profile"])
        self.assertEqual(catalog["custom"][0]["resource_challengers"], [])

        verification = sqlite3.connect(lifecycle.db_path)
        try:
            self.assertEqual(
                verification.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()[0],
                "4",
            )
            rapid_table = verification.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name='agent_profiles'"""
            ).fetchone()
            self.assertIsNone(rapid_table)
        finally:
            verification.close()

    def test_v4_to_v6_migration_failure_rolls_back(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-v6-failure-home")
        current = lifecycle.connect(create=True)
        assert current is not None
        current.close()
        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.execute("DROP TABLE evolution_actions")
            connection.execute("DROP TABLE resource_challengers")
            connection.execute("DROP TABLE agent_profiles")
            connection.execute(
                "UPDATE meta SET value='4' WHERE key='schema_version'"
            )
            connection.commit()
        finally:
            connection.close()

        original = manage_agents.AgentLifecycle.create_rapid_evolution_schema

        def fail_after_ddl(database):
            original(database)
            raise sqlite3.OperationalError("injected rapid migration failure")

        manage_agents.AgentLifecycle.create_rapid_evolution_schema = staticmethod(
            fail_after_ddl
        )
        try:
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "injected rapid migration failure"
            ):
                lifecycle.connect(create=True)
        finally:
            manage_agents.AgentLifecycle.create_rapid_evolution_schema = staticmethod(
                original
            )

        verification = sqlite3.connect(lifecycle.db_path)
        try:
            self.assertEqual(
                verification.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()[0],
                "4",
            )
            rapid_table = verification.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name='evolution_actions'"""
            ).fetchone()
            self.assertIsNone(rapid_table)
        finally:
            verification.close()

    def test_v4_evolution_schema_failure_rolls_back_new_tables(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-v4-failure-home")
        original = manage_agents.AgentLifecycle.create_evolution_schema

        def fail_after_ddl(database):
            original(database)
            raise sqlite3.OperationalError("injected evolution migration failure")

        manage_agents.AgentLifecycle.create_evolution_schema = staticmethod(fail_after_ddl)
        try:
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "injected evolution migration failure"
            ):
                lifecycle.connect(create=True)
        finally:
            manage_agents.AgentLifecycle.create_evolution_schema = staticmethod(original)

        verification = sqlite3.connect(lifecycle.db_path)
        try:
            version = verification.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            evolution_table = verification.execute(
                """SELECT name FROM sqlite_master
                    WHERE type='table' AND name='variation_sessions'"""
            ).fetchone()
        finally:
            verification.close()
        self.assertIsNone(version)
        self.assertIsNone(evolution_table)

    def test_v1_migration_failure_rolls_back_and_closes_connection(self):
        lifecycle = manage_agents.AgentLifecycle(self.root / "migration-failure-home")
        lifecycle.state_root.mkdir(parents=True)
        connection = sqlite3.connect(lifecycle.db_path)
        try:
            connection.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta(key, value) VALUES('schema_version', '1');
                INSERT INTO meta(key, value) VALUES('sentinel', 'keep');
                """
            )
            connection.commit()
        finally:
            connection.close()

        original = manage_agents.AgentLifecycle.create_routing_schema

        def fail_after_ddl(database):
            original(database)
            raise sqlite3.OperationalError("injected migration failure")

        manage_agents.AgentLifecycle.create_routing_schema = staticmethod(fail_after_ddl)
        try:
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected migration failure"):
                lifecycle.connect(create=True)
        finally:
            manage_agents.AgentLifecycle.create_routing_schema = staticmethod(original)

        verification = sqlite3.connect(lifecycle.db_path, isolation_level=None)
        try:
            version = verification.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()[0]
            sentinel = verification.execute(
                "SELECT value FROM meta WHERE key='sentinel'"
            ).fetchone()[0]
            routing_table = verification.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='evaluation_routing'"
            ).fetchone()
            verification.execute("BEGIN IMMEDIATE")
            verification.rollback()
        finally:
            verification.close()
        self.assertEqual(version, "1")
        self.assertEqual(sentinel, "keep")
        self.assertIsNone(routing_table)
        self.assertFalse(lifecycle.agents_dir.exists())


if __name__ == "__main__":
    unittest.main()
