from __future__ import annotations

import importlib.util
import json
import os
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

    def test_empty_catalog_is_read_only(self):
        result = self.lifecycle.catalog(self.project_root)
        self.assertTrue(result["ok"])
        self.assertEqual([item["name"] for item in result["builtins"]], ["default", "worker", "explorer"])
        self.assertFalse(self.lifecycle.db_path.exists())
        self.assertFalse(self.lifecycle.state_root.exists())

    def test_cli_create_and_catalog_round_trip(self):
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

    def test_create_writes_valid_owned_toml_and_chinese_contract(self):
        result = self.lifecycle.create_agent(self.spec(), self.project_root)
        self.assertEqual(result["state"], "pending_visibility")
        self.assertFalse(result["current_session_ready"])
        path = Path(result["path"])
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["name"], result["name"])
        self.assertEqual(parsed["model"], "gpt-5.6-terra")
        self.assertEqual(parsed["model_reasoning_effort"], "high")
        self.assertIn("集成审查员", parsed["description"])
        self.assertIn("默认使用中文", parsed["developer_instructions"])
        self.assertIn("子代理名称：集成审查员", parsed["developer_instructions"])
        self.assertIn("请求模型", parsed["developer_instructions"])
        self.assertIn("生效推理强度", parsed["developer_instructions"])
        self.assertIn(result["agent_id"], path.read_text(encoding="utf-8"))

        catalog = self.lifecycle.catalog(self.project_root)
        record = next(item for item in catalog["custom"] if item.get("agent_id") == result["agent_id"])
        self.assertEqual(record["source"], "plugin_managed")
        self.assertEqual(record["display_name"], "集成审查员")
        self.assertFalse(record["selectable"])
        self.assertTrue(record["requires_reload"])

        visible = self.lifecycle.confirm_visible(result["agent_id"])
        self.assertEqual(visible["state"], "probation")
        catalog = self.lifecycle.catalog(self.project_root)
        record = next(item for item in catalog["custom"] if item.get("agent_id") == result["agent_id"])
        self.assertTrue(record["selectable"])

    def test_catalog_deduplicates_identical_personal_and_project_roots(self):
        root_project = self.codex_home.parent
        result = self.lifecycle.create_agent(self.spec(), root_project)
        catalog = self.lifecycle.catalog(root_project)
        matching = [item for item in catalog["custom"] if item.get("agent_id") == result["agent_id"]]
        self.assertEqual(len(matching), 1)

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
        catalog = self.lifecycle.catalog(self.project_root)
        record = next(item for item in catalog["custom"] if item.get("agent_id") == created["agent_id"])
        self.assertEqual(record["source"], "plugin_conflict")
        self.assertFalse(record["selectable"])

    def test_conflicts_do_not_permanently_consume_the_managed_agent_cap(self):
        created = [self.create_visible_agent() for _ in range(8)]
        drifted_path = Path(created[0]["path"])
        drifted_path.write_bytes(drifted_path.read_bytes() + b"\n# external edit\n")
        with self.assertRaises(manage_agents.OwnershipConflict):
            self.lifecycle.record_evaluation(self.high_report(created[0]["agent_id"]))
        replacement = self.lifecycle.create_agent(self.spec(slug="replacement-reviewer"), self.project_root)
        self.assertEqual(replacement["state"], "pending_visibility")
        self.assertTrue(Path(replacement["path"]).exists())

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

    def test_single_ordinary_or_extreme_failure_does_not_retire(self):
        created = self.create_visible_agent()
        result = self.lifecycle.record_evaluation(self.extreme_report(created["agent_id"]))
        self.assertEqual(result["quality_band"], "extreme_observation")
        self.assertNotEqual(result["state"], "retire_eligible")
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.retire_agent(created["agent_id"])
        self.assertTrue(Path(created["path"]).exists())

    def test_repeated_evidence_backed_extreme_failure_quarantines_and_restores(self):
        created = self.create_visible_agent()
        results = [
            self.lifecycle.record_evaluation(self.extreme_report(created["agent_id"]))
            for _ in range(3)
        ]
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

    def test_extreme_failures_must_be_comparable_by_task_and_risk(self):
        created = self.create_visible_agent()
        self.lifecycle.record_evaluation(self.extreme_report(created["agent_id"]))
        self.lifecycle.record_evaluation(self.extreme_report(created["agent_id"]))
        different = self.extreme_report(created["agent_id"])
        different["task_class"] = "test"
        result = self.lifecycle.record_evaluation(different)
        self.assertNotEqual(result["state"], "retire_eligible")
        self.assertTrue(Path(created["path"]).exists())

    def test_restore_refuses_a_new_user_agent_with_the_same_name(self):
        created = self.create_visible_agent()
        self.lifecycle.record_evaluation(self.critical_report(created["agent_id"]))
        retired = self.lifecycle.retire_agent(created["agent_id"])
        collision = self.codex_home / "agents" / "user-collision.toml"
        collision.write_text(
            f'name = "{created["name"]}"\n'
            'description = "User-owned replacement."\n'
            'developer_instructions = "Never overwrite this file."\n',
            encoding="utf-8",
        )
        collision_before = collision.read_bytes()
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.restore_agent(
                created["agent_id"], f"restore:{created['agent_id']}", self.project_root
            )
        self.assertEqual(collision.read_bytes(), collision_before)
        self.assertFalse(Path(created["path"]).exists())
        self.assertTrue(Path(retired["quarantine_path"]).exists())

    def test_recover_aborts_a_prepared_move_that_never_touched_the_file(self):
        created = self.create_visible_agent()
        self.lifecycle.record_evaluation(self.critical_report(created["agent_id"]))
        source = Path(created["path"])
        destination_dir = self.lifecycle.quarantine_dir / created["agent_id"]
        destination_dir.mkdir(parents=True)
        row = self.db_row("SELECT * FROM agents WHERE agent_id=?", (created["agent_id"],))
        destination = destination_dir / f"revision-{row['revision']}-{row['expected_sha256'][:12]}.toml"
        operation_id = self.insert_move_intent(
            agent_id=created["agent_id"],
            operation="quarantine",
            source=source,
            destination=destination,
            target_state="quarantined",
        )
        result = self.lifecycle.recover()
        self.assertIn(
            {"operation_id": operation_id, "result": "aborted_before_move"}, result["results"]
        )
        self.assertTrue(source.exists())
        self.assertFalse(destination.exists())
        operation = self.db_row("SELECT stage FROM operations WHERE operation_id=?", (operation_id,))
        self.assertEqual(operation["stage"], "aborted")

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

    def test_confirmed_critical_event_is_immediately_quarantine_eligible(self):
        created = self.create_visible_agent()
        result = self.lifecycle.record_evaluation(self.critical_report(created["agent_id"]))
        self.assertEqual(result["state"], "retire_eligible")
        self.assertEqual(result["retirement_reason"], "unauthorized_destructive_write")
        retired = self.lifecycle.retire_agent(created["agent_id"])
        self.assertTrue(Path(retired["quarantine_path"]).exists())

    def test_unconfirmed_critical_event_is_not_enough(self):
        created = self.create_visible_agent()
        report = self.critical_report(created["agent_id"])
        report["critical_confirmations"] = ["independent_model"]
        result = self.lifecycle.record_evaluation(report)
        self.assertNotEqual(result["state"], "retire_eligible")
        self.assertTrue(Path(created["path"]).exists())

    def test_unknown_report_fields_are_rejected_without_recording(self):
        created = self.create_visible_agent()
        report = self.high_report(created["agent_id"])
        report["raw_trace"] = "must never be stored"
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.record_evaluation(report)
        row = self.db_row("SELECT COUNT(*) AS count FROM evaluations")
        self.assertEqual(row["count"], 0)

    def test_record_retry_is_idempotent_by_run_id(self):
        created = self.create_visible_agent()
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

    def test_hardlinked_agent_cannot_be_quarantined(self):
        created = self.create_visible_agent()
        self.lifecycle.record_evaluation(self.critical_report(created["agent_id"]))
        path = Path(created["path"])
        hardlink = path.with_name(path.stem + "_hardlink.toml")
        try:
            os.link(path, hardlink)
        except (OSError, NotImplementedError):
            self.skipTest("hard links are unavailable in this test environment")
        with self.assertRaises(manage_agents.OwnershipConflict):
            self.lifecycle.retire_agent(created["agent_id"])
        self.assertTrue(path.exists())
        self.assertTrue(hardlink.exists())

    def test_promotion_gate_preserves_incumbent_on_no_gain(self):
        created = self.create_visible_agent()
        outputs = [
            self.lifecycle.record_evaluation(self.high_report(created["agent_id"]))
            for _ in range(3)
        ]
        path = Path(created["path"])
        incumbent = path.read_bytes()
        report = self.promotion(outputs[-1]["candidate_id"])
        report["challenger_quality"] = report["incumbent_quality"]
        report["challenger_efficiency"] = report["incumbent_efficiency"]
        with self.assertRaises(manage_agents.LifecycleError):
            self.lifecycle.promote_candidate(report)
        self.assertEqual(path.read_bytes(), incumbent)
        row = self.db_row(
            "SELECT status FROM candidates WHERE candidate_id=?", (outputs[-1]["candidate_id"],)
        )
        self.assertEqual(row["status"], "candidate")

    def test_doctor_reports_orphan_marker_as_user_owned(self):
        agents = self.codex_home / "agents"
        agents.mkdir(parents=True)
        orphan = agents / "lean_orphan_deadbeef.toml"
        orphan.write_text(
            "# Managed by codex-lean-stack; external edits revoke automatic ownership.\n"
            f"# lean-stack-agent-id: {uuid.uuid4()}\n"
            'name = "lean_orphan_deadbeef"\n'
            'description = "Orphaned file."\n'
            'developer_instructions = "Treat as user owned."\n',
            encoding="utf-8",
        )
        catalog = self.lifecycle.catalog(self.project_root)
        self.assertEqual(len(catalog["custom"]), 1, catalog)
        self.assertTrue(catalog["custom"][0].get("marker_agent_id"), catalog)
        result = self.lifecycle.doctor(self.project_root)
        self.assertFalse(result["ok"], result)
        self.assertTrue(any("按用户文件保护" in issue for issue in result["issues"]))
        self.assertFalse(self.lifecycle.db_path.exists())


if __name__ == "__main__":
    unittest.main()
