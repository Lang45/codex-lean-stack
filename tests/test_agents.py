from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import tomllib
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "lean-stack" / "scripts" / "agents.py"
SPEC = importlib.util.spec_from_file_location("lean_stack_agents", SCRIPT)
assert SPEC and SPEC.loader
agents = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agents)


class SpecialistRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.codex_home = Path(self.temporary.name) / "codex-home"
        self.registry = agents.SpecialistRegistry(self.codex_home)

    def ensure(
        self,
        *,
        role_key: str = "qml-binding-diagnostics",
        authority: str = "read",
        display_name: str | None = None,
        description: str = "重复完成一个边界清晰、可复核的专门工作。",
        role_instructions: str = "交付直接可消费的结果和必要证据。",
        model: str = "gpt-5.6-terra",
        effort: str = "high",
        expected_sha256: str | None = None,
    ):
        return self.registry.ensure(
            role_key=role_key,
            display_name=display_name
            or ("QML 绑定诊断员" if role_key.startswith("qml") else "回归测试执行员"),
            description=description,
            role_instructions=role_instructions,
            model=model,
            effort=effort,
            authority=authority,
            expected_sha256=expected_sha256,
        )

    def db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.registry.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def test_ensure_creates_one_specialist_and_reuses_the_same_role(self) -> None:
        first = self.ensure()
        second = self.ensure()

        self.assertEqual(first["action"], "created")
        self.assertEqual(first["host_visibility"], "requires_new_task")
        self.assertEqual(second["action"], "reused")
        self.assertTrue(second["compatible"])
        self.assertEqual(first["name"], second["name"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)

        payload = tomllib.loads(Path(first["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], first["name"])
        self.assertEqual(payload["sandbox_mode"], "read-only")
        self.assertIn("QML 绑定诊断员", payload["developer_instructions"])
        self.assertIn("请求模型 gpt-5.6-terra", payload["developer_instructions"])

    def test_distinct_repeated_work_gets_distinct_writable_or_read_specialists(self) -> None:
        reader = self.ensure(role_key="qml-binding-diagnostics", authority="read")
        writer = self.ensure(role_key="python-regression-implementation", authority="write")

        reader_payload = tomllib.loads(Path(reader["path"]).read_text(encoding="utf-8"))
        writer_payload = tomllib.loads(Path(writer["path"]).read_text(encoding="utf-8"))
        self.assertEqual(reader_payload["sandbox_mode"], "read-only")
        self.assertEqual(writer_payload["sandbox_mode"], "workspace-write")
        self.assertNotEqual(reader["name"], writer["name"])
        self.assertNotIn("唯一", writer_payload["developer_instructions"])

    def test_new_database_has_only_ownership_and_experience_tables(self) -> None:
        self.ensure()
        with contextlib.closing(self.db()) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(
            tables,
            {"agents", "experience_events", "experience_summaries"},
        )
        self.assertEqual(version, 1)
        for removed in (
            "leases",
            "evaluations",
            "project_routes",
            "candidates",
            "operations",
            "variation_sessions",
        ):
            self.assertNotIn(removed, tables)

    def test_unversioned_unknown_database_is_never_initialized_or_migrated(self) -> None:
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            connection.execute("CREATE TABLE legacy_data(value TEXT)")
            connection.execute("INSERT INTO legacy_data(value) VALUES('keep-me')")
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            objects = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            value = connection.execute("SELECT value FROM legacy_data").fetchone()[0]
        self.assertEqual(objects, {"legacy_data"})
        self.assertEqual(version, 0)
        self.assertEqual(value, "keep-me")

    def test_versioned_database_with_wrong_columns_is_rejected_before_use(self) -> None:
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE agents(agent_id TEXT PRIMARY KEY);
                CREATE TABLE experience_events(sequence INTEGER PRIMARY KEY);
                CREATE TABLE experience_summaries(agent_id TEXT PRIMARY KEY);
                PRAGMA user_version = 1;
                """
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            columns = [
                row[1] for row in connection.execute("PRAGMA table_info(agents)")
            ]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(columns, ["agent_id"])
        self.assertEqual(version, 1)

    def test_versioned_database_with_missing_constraints_is_rejected(self) -> None:
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role_key TEXT NOT NULL,
                    path TEXT NOT NULL,
                    owner_token TEXT NOT NULL,
                    expected_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE experience_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE experience_summaries (
                    agent_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    covered_through_sequence INTEGER NOT NULL,
                    source_digest TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                PRAGMA user_version = 1;
                """
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            unique_indexes = [
                row for row in connection.execute("PRAGMA index_list(agents)")
            ]
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)
        self.assertEqual(len(unique_indexes), 1)

    def test_versioned_database_with_extra_trigger_is_rejected(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                """
                CREATE TRIGGER unexpected_agent_update
                BEFORE UPDATE ON agents
                BEGIN
                    SELECT RAISE(IGNORE);
                END
                """
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        self.assertEqual(path.read_bytes(), before)

    def test_versioned_database_with_extra_named_index_is_rejected(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "CREATE INDEX unexpected_agent_timestamp ON agents(updated_at)"
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        self.assertEqual(path.read_bytes(), before)

    def test_unowned_managed_role_file_blocks_duplicate_creation(self) -> None:
        role_key = "qml-binding-diagnostics"
        agent_id = str(uuid.uuid4())
        owner_token = uuid.uuid4().hex
        name = agents.specialist_name(role_key, agent_id)
        base = agents.base_instructions(
            display_name="QML 绑定诊断员",
            role_key=role_key,
            role_instructions="交付直接可消费的结果和必要证据。",
            model="gpt-5.6-terra",
            effort="high",
            authority="read",
        )
        data = agents.build_agent_bytes(
            agent_id=agent_id,
            role_key=role_key,
            owner_token=owner_token,
            name=name,
            display_name="QML 绑定诊断员",
            description="模拟文件落盘后、ledger 提交前的进程崩溃。",
            model="gpt-5.6-terra",
            effort="high",
            authority="read",
            developer_instructions=agents.compose_instructions(
                base, agents.memory_block("", [])
            ),
        )
        orphan_path = self.registry.agents_dir / "lean_renamed_orphan.toml"
        agents.write_new_file(orphan_path, data)

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)

    def test_ensure_reconfigures_one_role_with_cas_and_preserves_experience(self) -> None:
        created = self.ensure()
        lesson = "验证后的单轴胜出配置必须保留已有经验。"
        improved = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=str(uuid.uuid4()),
        )
        path = Path(created["path"])
        before = path.read_bytes()

        preview = self.ensure(
            display_name="QML 根因核对员",
            description="采用验证后胜出的配置重复诊断 QML 根因。",
            role_instructions="先核对实际依赖图，再返回最小可复核修法。",
            model="gpt-5.6-luna",
            effort="medium",
            authority="write",
        )
        self.assertEqual(preview["action"], "reconfiguration_required")
        self.assertFalse(preview["compatible"])
        self.assertEqual(path.read_bytes(), before)

        reconfigured = self.ensure(
            display_name="QML 根因核对员",
            description="采用验证后胜出的配置重复诊断 QML 根因。",
            role_instructions="先核对实际依赖图，再返回最小可复核修法。",
            model="gpt-5.6-luna",
            effort="medium",
            authority="write",
            expected_sha256=improved["sha256"],
        )
        self.assertEqual(reconfigured["action"], "reconfigured")
        self.assertTrue(reconfigured["experience_preserved"])
        self.assertEqual(reconfigured["agent_id"], created["agent_id"])
        self.assertEqual(reconfigured["owner_token"], created["owner_token"])
        self.assertEqual(reconfigured["path"], created["path"])
        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["model_reasoning_effort"], "medium")
        self.assertEqual(payload["sandbox_mode"], "workspace-write")
        self.assertIn("QML 根因核对员", payload["description"])
        self.assertIn("实际依赖图", payload["developer_instructions"])
        self.assertIn(lesson, payload["developer_instructions"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )

    def test_ensure_reconfiguration_rejects_stale_cas_without_mutation(self) -> None:
        created = self.ensure()
        before = Path(created["path"]).read_bytes()
        with self.assertRaises(agents.SpecialistError):
            self.ensure(
                description="不同配置。",
                expected_sha256="0" * 64,
            )
        self.assertEqual(Path(created["path"]).read_bytes(), before)
        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)

    def test_old_lifecycle_database_is_never_opened_migrated_or_deleted(self) -> None:
        old = self.registry.old_db_path
        old.write_bytes(b"opaque-old-lifecycle-data")
        before = old.read_bytes()

        self.ensure()

        self.assertEqual(old.read_bytes(), before)
        self.assertNotEqual(old, self.registry.db_path)

    def test_good_experience_is_idempotent_and_updates_the_agent_memory(self) -> None:
        created = self.ensure()
        event_id = str(uuid.uuid4())
        lesson = "先核对真实运行时依赖，再修改共享绑定。"

        first = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=event_id,
        )
        replay = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=first["sha256"],
            lesson=lesson,
            event_id=event_id,
        )

        self.assertEqual(first["action"], "experience_recorded")
        self.assertEqual(replay["action"], "experience_already_recorded")
        self.assertEqual(replay["experience_count"], 1)
        text = (self.registry.agents_dir / f"{created['name']}.toml").read_text(encoding="utf-8")
        self.assertIn(lesson, text)

        with self.assertRaises(agents.SpecialistError):
            self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=replay["sha256"],
                lesson="同一个事件不能改写成另一条经验。",
                event_id=event_id,
            )

    def test_raw_experience_is_unlimited_and_compaction_never_deletes_it(self) -> None:
        created = self.ensure()
        current_hash = created["sha256"]
        compaction = None
        lessons = []
        for index in range(20):
            lesson = f"经验 {index}：保留可复核证据并避免重复读取。"
            lessons.append(lesson)
            result = self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=lesson,
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            if result["compaction"]["needed"]:
                compaction = result["compaction"]

        self.assertIsNotNone(compaction)
        assert compaction is not None
        with contextlib.closing(self.db()) as connection:
            before = list(
                connection.execute(
                    "SELECT sequence, lesson FROM experience_events ORDER BY sequence"
                )
            )
        self.assertEqual(len(before), 20)
        self.assertEqual([row["lesson"] for row in before], lessons)

        summary = "保留证据、复用完整来源覆盖，并避免重复读取和返工。"
        with mock.patch.object(
            self.registry,
            "_pending_events",
            wraps=self.registry._pending_events,
        ) as pending:
            compacted = self.registry.improve_with_summary(
                name=created["name"],
                expected_sha256=current_hash,
                summary=summary,
                covered_through=compaction["covered_through"],
                source_digest=compaction["source_digest"],
            )
        self.assertEqual(pending.call_count, 1)
        self.assertTrue(compacted["raw_experience_preserved"])
        with contextlib.closing(self.db()) as connection:
            after = list(
                connection.execute(
                    "SELECT sequence, lesson FROM experience_events ORDER BY sequence"
                )
            )
            summary_row = connection.execute(
                "SELECT * FROM experience_summaries"
            ).fetchone()
        self.assertEqual([(row["sequence"], row["lesson"]) for row in before], [(row["sequence"], row["lesson"]) for row in after])
        self.assertEqual(summary_row["covered_through_sequence"], compaction["covered_through"])
        self.assertIn(summary, Path(created["path"]).read_text(encoding="utf-8"))

    def test_compaction_triggers_at_eight_pending_events(self) -> None:
        created = self.ensure()
        current_hash = created["sha256"]
        for index in range(7):
            result = self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"短经验 {index}",
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            self.assertFalse(result["compaction"]["needed"])
        eighth = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=current_hash,
            lesson="短经验 7",
            event_id=str(uuid.uuid4()),
        )
        self.assertTrue(eighth["compaction"]["needed"])

    def test_improve_reads_one_bounded_pending_window(self) -> None:
        created = self.ensure()
        with contextlib.closing(self.db()) as connection:
            for index in range(100):
                lesson = f"历史经验 {index}"
                connection.execute(
                    "INSERT INTO experience_events(agent_id,event_id,event_digest,lesson,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (
                        created["agent_id"],
                        str(uuid.uuid4()),
                        agents.sha256_bytes(lesson.encode("utf-8")),
                        lesson,
                        agents.utc_now(),
                    ),
                )
            connection.commit()

        with mock.patch.object(
            self.registry,
            "_pending_events",
            wraps=self.registry._pending_events,
        ) as pending:
            result = self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=created["sha256"],
                lesson="新经验只读取一个有界窗口。",
                event_id=str(uuid.uuid4()),
            )

        self.assertEqual(pending.call_count, 1)
        self.assertTrue(result["compaction"]["needed"])
        self.assertLessEqual(
            len(result["compaction"]["events"]), agents.COMPACT_BATCH_EVENTS
        )
        self.assertEqual(result["experience_count"], 101)

    def test_stale_compaction_cannot_overwrite_a_newer_summary(self) -> None:
        created = self.ensure()
        current_hash = created["sha256"]
        compaction = None
        for index in range(8):
            result = self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"并发经验 {index}",
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            compaction = result["compaction"]
        assert compaction and compaction["needed"]
        refreshed = self.registry.improve_with_summary(
            name=created["name"],
            expected_sha256=current_hash,
            summary="最新压缩摘要。",
            covered_through=compaction["covered_through"],
            source_digest=compaction["source_digest"],
        )
        with self.assertRaises(agents.SpecialistError):
            self.registry.improve_with_summary(
                name=created["name"],
                expected_sha256=refreshed["sha256"],
                summary="迟到旧摘要。",
                covered_through=compaction["covered_through"] - 1,
                source_digest=compaction["source_digest"],
            )

    def test_delete_is_permanent_exact_and_has_no_quarantine(self) -> None:
        created = self.ensure()
        result = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )
        self.assertTrue(result["deleted"])
        self.assertFalse(result["recoverable"])
        self.assertFalse(Path(created["path"]).exists())
        self.assertFalse((self.registry.state_dir / "quarantine").exists())
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)

    def test_delete_rejects_wrong_token_hash_drift_and_external_files(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        external = self.registry.agents_dir / "user_agent.toml"
        external.write_text('name = "user_agent"\n', encoding="utf-8")
        external_before = external.read_bytes()

        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token="0" * 32,
            )
        self.assertTrue(path.exists())

        path.write_bytes(path.read_bytes() + b"\n# external edit\n")
        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertTrue(path.exists())
        self.assertEqual(external.read_bytes(), external_before)

    def test_delete_rejects_hard_linked_agent(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        linked = path.with_name(path.stem + "_link.toml")
        try:
            os.link(path, linked)
        except OSError as exc:
            self.skipTest(f"hard links unavailable: {exc}")
        self.addCleanup(lambda: linked.exists() and linked.unlink())

        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertTrue(path.exists())

    def test_missing_file_registry_cleanup_requires_exact_hash_and_token(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        first = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson="孤儿账本清理也必须验证所有权凭据。",
            event_id=str(uuid.uuid4()),
        )
        path.unlink()

        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256="0" * 64,
                owner_token=created["owner_token"],
            )
        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=first["sha256"],
                owner_token="0" * 32,
            )

        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )

        cleaned = self.registry.delete(
            name=created["name"],
            expected_sha256=first["sha256"],
            owner_token=created["owner_token"],
        )
        self.assertEqual(cleaned["action"], "stale_registry_row_removed")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                0,
            )

    def test_locked_database_fails_within_the_bounded_auxiliary_timeout(self) -> None:
        self.ensure()
        blocker = sqlite3.connect(self.registry.db_path, isolation_level=None)
        self.addCleanup(blocker.close)
        blocker.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with self.assertRaises(sqlite3.OperationalError):
            self.registry.ensure(
                role_key="another-specialty",
                display_name="另一个执行员",
                description="执行另一种重复工作。",
                role_instructions="返回直接成果。",
                model="gpt-5.6-luna",
                effort="medium",
                authority="read",
            )
        elapsed = time.monotonic() - started
        blocker.execute("ROLLBACK")
        self.assertLess(elapsed, 1.0)

    def test_cli_error_is_auxiliary_skipped(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "ensure",
                    "--role-key",
                    "Invalid Role",
                    "--display-name",
                    "执行员",
                    "--description",
                    "说明",
                    "--instructions",
                    "完成任务",
                    "--model",
                    "gpt-5.6-luna",
                    "--reasoning-effort",
                    "medium",
                    "--authority",
                    "read",
                ]
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(output.getvalue())["action"], "auxiliary_skipped")

    def test_cli_ensure_improve_delete_round_trip(self) -> None:
        ensure_output = io.StringIO()
        with contextlib.redirect_stdout(ensure_output):
            ensure_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "ensure",
                    "--role-key",
                    "source-contract-verification",
                    "--display-name",
                    "来源契约核对员",
                    "--description",
                    "重复核对来源边界和契约。",
                    "--instructions",
                    "返回精确来源覆盖和证据缺口。",
                    "--model",
                    "gpt-5.6-luna",
                    "--reasoning-effort",
                    "medium",
                    "--authority",
                    "read",
                ]
            )
        created = json.loads(ensure_output.getvalue())
        self.assertEqual(ensure_exit, 0)
        self.assertEqual(created["action"], "created")

        improve_output = io.StringIO()
        with contextlib.redirect_stdout(improve_output):
            improve_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "improve",
                    "--name",
                    created["name"],
                    "--expected-sha256",
                    created["sha256"],
                    "--event-id",
                    str(uuid.uuid4()),
                    "--lesson",
                    "完整来源覆盖可替代父代理的重复语义读取。",
                ]
            )
        improved = json.loads(improve_output.getvalue())
        self.assertEqual(improve_exit, 0)
        self.assertEqual(improved["action"], "experience_recorded")

        delete_output = io.StringIO()
        with contextlib.redirect_stdout(delete_output):
            delete_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "delete",
                    "--name",
                    created["name"],
                    "--expected-sha256",
                    improved["sha256"],
                    "--owner-token",
                    created["owner_token"],
                ]
            )
        deleted = json.loads(delete_output.getvalue())
        self.assertEqual(delete_exit, 0)
        self.assertTrue(deleted["deleted"])


if __name__ == "__main__":
    unittest.main()
