"""Behavioral regressions found by the 5.2.13 end-to-end source audit.

All writes use temporary homes. The installer subprocess is deliberately fake:
these tests do not claim to verify a live Codex host or install a plugin.
"""
from __future__ import annotations

import codecs
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import datetime as dt
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "lean-stack" / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"audit_{name}", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agents = load_script("agents")
installer = load_script("install_plugin")


class InstallationChainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.base = self.home / "AGENTS.md"
        self.override = self.home / "AGENTS.override.md"
        self.plugin = self.root / "plugins" / "codex-lean-stack"
        (self.plugin / ".codex-plugin").mkdir(parents=True)
        (self.plugin / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "codex-lean-stack", "version": "5.2.13+codex.test"}),
            encoding="utf-8",
        )
        self.marketplace = self.root / ".agents" / "plugins" / "marketplace.json"
        self.marketplace.parent.mkdir(parents=True)
        self.marketplace.write_text(json.dumps({
            "name": "personal", "plugins": [{"name": "codex-lean-stack", "source": {
                "source": "local", "path": "./plugins/codex-lean-stack"
            }}]
        }), encoding="utf-8")

    def install(self, runner):
        with mock.patch.object(installer.shutil, "which", return_value="codex.exe"):
            return installer.install_plugin(
                self.plugin, marketplace_path=self.marketplace,
                codex_home=self.home, runner=runner,
            )

    def test_explicit_home_is_forwarded_to_the_install_subprocess(self):
        captured = {}

        def runner(command, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "other-home")}):
            self.install(runner)
        self.assertEqual(captured["env"]["CODEX_HOME"], str(self.home))
        self.assertEqual(captured["env"]["PYTHONUTF8"], "1")

    def test_nonempty_override_is_the_only_activation_target(self):
        base = b"# Preserve the inactive base\n"
        original = codecs.BOM_UTF8 + "# Active instructions\r\n\r\nOther rule.\r\n".encode()
        self.base.write_bytes(base)
        self.override.write_bytes(original)
        preflight = installer.preflight_default_invocation(self.home)
        first = installer.ensure_default_invocation(self.home)
        once = self.override.read_bytes()
        second = installer.ensure_default_invocation(self.home)
        self.assertEqual(preflight["agents_path"], str(self.override))
        self.assertEqual(first["agents_path"], str(self.override))
        self.assertTrue(first["modified"])
        self.assertFalse(second["modified"])
        self.assertEqual(self.base.read_bytes(), base)
        self.assertEqual(self.override.read_bytes(), once)
        self.assertTrue(once.startswith(codecs.BOM_UTF8))
        self.assertIn(installer.DEFAULT_INVOCATION_LINE.encode(), once)
        self.assertNotIn(b"\n", once.replace(b"\r\n", b""))

    def test_empty_override_preserves_fallback_and_original_bytes(self):
        self.override.write_bytes(codecs.BOM_UTF8 + b"\r\n")
        result = installer.ensure_default_invocation(self.home)
        self.assertEqual(result["agents_path"], str(self.base))
        self.assertEqual(self.override.read_bytes(), codecs.BOM_UTF8 + b"\r\n")

    def test_invalid_override_is_rejected_before_running_installer(self):
        self.override.write_bytes(b"\xff")
        runner = mock.Mock()
        with self.assertRaises(installer.InstallError):
            self.install(runner)
        runner.assert_not_called()
        self.assertFalse(self.base.exists())

    def test_changed_instruction_selection_is_not_reported_as_success(self):
        self.base.write_bytes(b"# Original\n")

        def runner(command, **kwargs):
            self.override.write_text("# Newly active override\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")

        with self.assertRaisesRegex(installer.InstallError, "changed"):
            self.install(runner)
        self.assertEqual(self.base.read_bytes(), b"# Original\n")
        self.assertEqual(self.override.read_text(), "# Newly active override\n")

    def test_examples_and_comments_do_not_count_as_activation(self):
        line = installer.DEFAULT_INVOCATION_LINE
        examples = (
            f"```text\n{line}\n```\n",
            f"~~~~text\n{line}\n~~~~\n",
            f"<!--\n{line}\n-->\n",
            f"# Notes <!--\n{line}\n-->\n",
            f"---\nexample: |\n  {line}\n---\n",
        )
        for text in examples:
            with self.subTest(text=text.splitlines()[0]):
                self.assertFalse(installer._has_default_invocation(text))
                self.base.write_text(text, encoding="utf-8", newline="")
                result = installer.ensure_default_invocation(self.home)
                written = self.base.read_text(encoding="utf-8", newline="")
                self.assertTrue(result["modified"])
                if text.startswith("---\n"):
                    # Metadata remains first; the instruction belongs to the body.
                    self.assertEqual(written, text + "\n" + line + "\n\n")
                else:
                    self.assertTrue(written.startswith(line + "\n"))
                    self.assertTrue(written.endswith(text))
                self.assertFalse(installer.ensure_default_invocation(self.home)["modified"])


class RegistryChainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.registry = agents.SpecialistRegistry(self.root / "home")

    def create(self):
        return self.registry.ensure(
            role_key="evidence-review", display_name="证据复核员",
            description="核对已定位证据并保留适用边界。", role_instructions="交付可核验的复核结论。",
            model="gpt-6-sol", effort="high", authority="read",
            global_domain_key="evidence-review",
            global_contract={
                "domain": "证据复核", "input_shapes": ["已定位证据"],
                "responsibilities": ["复核结论及适用边界"], "deliverables": ["有证据的结论"],
                "hard_boundaries": ["不修改未授权文件"],
            }, origin_terms=("audit-fixture-project",),
        )

    def improve(self, created, lesson, **kwargs):
        return self.registry.improve_with_lesson(
            name=created["name"], expected_sha256=created["sha256"], lesson=lesson,
            event_id=str(uuid.uuid4()), origin_terms=("audit-fixture-project",), **kwargs,
        )

    def rows(self):
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            return {table: connection.execute(f"SELECT * FROM {table}").fetchall()
                    for table in ("agents", "agent_runs", "experience_events", "experience_summaries")}

    def test_dangling_database_link_cannot_create_an_external_database(self):
        outside = self.root / "outside.sqlite3"
        try:
            self.registry.db_path.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation is unavailable: {exc}")
        with self.assertRaisesRegex(agents.SpecialistError, "link"):
            self.create()
        self.assertFalse(outside.exists())
        self.assertEqual(list(self.registry.agents_dir.glob("*.toml")), [])

    def test_hard_linked_database_is_not_mutated(self):
        created = self.create()
        alias = self.root / "alias.sqlite3"
        os.link(self.registry.db_path, alias)
        original = alias.read_bytes()
        with self.assertRaisesRegex(agents.SpecialistError, "link"):
            self.improve(created, "先验证来源再执行。")
        self.assertEqual(alias.read_bytes(), original)

    def test_long_first_lesson_preserves_recall_routing_and_compaction(self):
        created = self.create()
        lesson = "保留适用边界和原始证据。" * 250  # 3,000 chars, 9,000 UTF-8 bytes.
        result = self.improve(created, lesson)
        self.assertTrue(result["compaction"]["needed"])
        recalled = self.registry.recall(name=created["name"], expected_sha256=result["sha256"])
        self.assertIsNone(recalled["retention_state"]["experience_digest"])
        self.assertFalse(recalled["retention_state"]["experience_loaded"])
        self.assertEqual(recalled["retention_state"]["active_experience_count"], 1)
        self.assertIn("待摘要压缩", recalled["opening_status"])
        self.assertEqual(self.registry.status(for_routing=True)["registered_count"], 1)
        self.assertEqual(self.registry.status(for_dashboard=True)["active_experience_count"], 1)
        self.registry.complete_run(
            name=created["name"], expected_sha256=result["sha256"],
            run_id=str(uuid.uuid4()), invocation_kind="spawn_agent", outcome="success",
        )
        batch = result["compaction"]
        compacted = self.registry.improve_with_summary(
            name=created["name"], expected_sha256=result["sha256"],
            summary="保留来源证据和适用边界，不把局部观察泛化。",
            covered_through=batch["covered_through"], source_digest=batch["source_digest"],
            origin_terms=("audit-fixture-project",),
        )
        run_id = str(uuid.uuid4())
        recalled = self.registry.recall(
            name=created["name"], expected_sha256=compacted["sha256"], run_id=run_id,
        )
        self.assertTrue(recalled["retention_state"]["experience_loaded"])
        digest = recalled["retention_state"]["experience_digest"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        run = dict(name=created["name"], expected_sha256=compacted["sha256"],
                   run_id=run_id, invocation_kind="spawn_agent", outcome="success",
                   loaded_experience_digest=digest,
                   experience_receipt=recalled["experience_receipt"])
        self.registry.complete_run(**run)
        self.registry.complete_run(**run)
        self.assertEqual(self.registry.recall(name=created["name"])["retention_state"]["survival_rounds"], 2)
        self.assertEqual(self.rows()["experience_events"][0][4], lesson)

    def test_legacy_unloaded_memory_is_read_without_rewriting_user_data(self):
        created = self.create()
        result = self.improve(created, "保留适用边界和原始证据。" * 250)
        path = Path(created["path"])
        data = path.read_bytes()
        # Reconstruct the exact old empty-window representation, keeping the ledger consistent.
        current = agents.SpecialistRegistry._experience_memory(__import__("tomllib").loads(data.decode()))
        old = data.replace(current.encode(), agents.memory_block("", []).encode())
        path.write_bytes(old)
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            connection.execute("UPDATE agents SET expected_sha256=?", (agents.sha256_bytes(old),))
            connection.commit()
        recalled = self.registry.recall(name=created["name"])
        self.assertIsNone(recalled["retention_state"]["experience_digest"])
        self.assertEqual(path.read_bytes(), old)
        self.assertTrue(result["compaction"]["needed"])

    def test_compaction_accounts_for_summary_and_rendered_labels(self):
        event = {"sequence": 1, "event_id": str(uuid.uuid4()), "lesson": "继续保留边界。" * 40,
                 "event_digest": "a" * 64, "retracts_event_id": None}
        summary = "证" * 1200
        self.assertLess(len(event["lesson"].encode()), agents.MAX_MEMORY_BYTES)
        self.assertGreater(len(agents.memory_block(summary, [event["lesson"]]).encode()), agents.MAX_MEMORY_BYTES)
        batch = self.registry._compression_batch(summary, [event])
        self.assertIsNotNone(batch)
        self.assertEqual(batch["events"][0]["lesson"], event["lesson"])
        self.assertIn("UTF-8", batch["instruction"])
        self.assertIsNone(self.registry._compression_batch(summary, []))

    def test_experience_faults_restore_exact_database_and_toml(self):
        for operation in ("improve", "complete-run"):
            for stage in ("ledger", "count", "compaction", "commit"):
                with self.subTest(operation=operation, stage=stage):
                    self.registry = agents.SpecialistRegistry(self.root / f"home-{operation}-{stage}")
                    created = self.create()
                    path = Path(created["path"])
                    before = path.read_bytes()
                    rows_before = self.rows()
                    real = self.registry.connect()

                    class FaultConnection:
                        def execute(inner, sql, *args, **kwargs):
                            if ((stage == "ledger" and sql.startswith("UPDATE agents SET expected_sha256"))
                                or (stage == "count" and sql.startswith("SELECT COUNT(*) FROM experience_events WHERE"))
                                or (stage == "commit" and sql == "COMMIT")):
                                raise sqlite3.OperationalError(f"injected {stage} failure")
                            return real.execute(sql, *args, **kwargs)

                        def __getattr__(inner, name):
                            return getattr(real, name)

                    with mock.patch.object(self.registry, "connect", return_value=FaultConnection()), \
                         contextlib.ExitStack() as stack:
                        if stage == "compaction":
                            stack.enter_context(mock.patch.object(self.registry, "_compression_batch",
                                side_effect=sqlite3.OperationalError("injected compaction failure")))
                        with self.assertRaisesRegex(sqlite3.OperationalError, "injected"):
                            if operation == "improve":
                                self.improve(created, "先验证边界再执行。")
                            else:
                                self.registry.complete_run(
                                    name=created["name"], expected_sha256=created["sha256"],
                                    run_id=str(uuid.uuid4()), invocation_kind="spawn_agent", outcome="success",
                                    lesson="先验证边界再执行。", origin_terms=("audit-fixture-project",),
                                )
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(self.rows(), rows_before)
                    self.registry.recall(name=created["name"])

    def test_absolute_posix_and_unc_paths_cannot_enter_new_experience(self):
        for value in ("Read /home/alice/private/report.txt first.", r"Read \\server\private\report.txt first."):
            with self.subTest(value=value), self.assertRaises(agents.SpecialistError):
                agents.validate_lesson(value)
        for value in ("Keep SQLite/TOML consistent.", "Test I/O boundaries.", "Use src/module.py as a relative example."):
            self.assertEqual(agents.validate_lesson(value), value)

    def test_contract_rejects_non_text_domain_and_embedded_control_characters(self):
        base = {"domain": "Review", "input_shapes": ["Evidence"], "responsibilities": ["Review"],
                "deliverables": ["Findings"], "hard_boundaries": ["Read only"]}
        for invalid in (None, 12, ["Review"], {"name": "Review"}, "Review\x00data"):
            with self.subTest(invalid=invalid), self.assertRaises(agents.SpecialistError):
                agents.normalize_global_contract({**base, "domain": invalid}, domain_key="review")


class CostMaintenanceChainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.cost = load_script("cost_check")
        self.when = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)

    def record(self, day=1, expected=None):
        return self.cost.record(codex_home=self.home, checked_at=self.when.replace(day=day),
                                expected_state_sha256=expected)

    def test_concurrent_record_cannot_pass_the_same_compare_and_swap(self):
        initial = self.record()
        entered = threading.Event()
        release = threading.Event()
        real_replace = self.cost.atomic_replace
        calls = []

        def paused_replace(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test did not release first writer")
            return real_replace(*args, **kwargs)

        with mock.patch.object(self.cost, "atomic_replace", side_effect=paused_replace), ThreadPoolExecutor(1) as pool:
            first = pool.submit(self.record, 2, initial["state_sha256"])
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(self.cost.CostCheckError):
                    self.record(3, initial["state_sha256"])
            finally:
                release.set()
            self.assertTrue(first.result(timeout=5)["ok"])
        self.assertEqual(len(calls), 1)
        # A persistent anchor is harmless: test that the kernel lock is released.
        with self.cost.record_lock(self.home / "lean-stack" / self.cost.STATE_NAME):
            pass

    def test_failed_first_write_does_not_leave_a_poisoned_state_file(self):
        real_fdopen = self.cost.os.fdopen

        class PartialWrite:
            def __init__(inner, *args, **kwargs):
                inner.handle = real_fdopen(*args, **kwargs)

            def __enter__(inner):
                inner.handle.__enter__()
                return inner

            def __exit__(inner, *args):
                return inner.handle.__exit__(*args)

            def write(inner, value):
                inner.handle.write(value[:8])
                raise OSError("injected partial write")

        with mock.patch.object(self.cost.os, "fdopen", side_effect=PartialWrite):
            with self.assertRaisesRegex(OSError, "partial write"):
                self.record()
        state = self.home / "lean-stack" / self.cost.STATE_NAME
        self.assertFalse(state.exists())
        with self.cost.record_lock(state):
            pass
        self.assertTrue(self.record()["ok"])


if __name__ == "__main__":
    unittest.main()
