"""Independent-review regressions for PR #2; all writes use temporary homes."""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest import mock
import uuid

import test_agents as registry_fixture
from test_chain_audit import SCRIPTS, load_script

ROOTED = ("/", "/foo", "//server/share", r"\foo\bar", r"C:\foo", "C:/foo", r"\\server\share")
RELATIVE = ("I/O", "SQLite/TOML", "src/module.py", "./module.py", "../src/module.py", r"src\module.py")


class PersistentBoundaryReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = registry_fixture.SpecialistRegistryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.registry = self.fixture.registry
        self.agents = registry_fixture.agents

    def snapshot(self):
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            schema = tuple(connection.execute(
                "SELECT type,name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            ))
            tables = tuple(
                row[1] for row in schema if row[0] == "table"
            )
            database = {
                "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
                "schema": schema,
                "rows": {
                    table: tuple(connection.execute(f'SELECT * FROM "{table}"'))
                    for table in tables
                },
            }
        return database, {
            p.name: p.read_bytes() for p in self.registry.agents_dir.glob("*.toml")
        }

    def test_all_root_forms_are_rejected_by_lesson_and_contract_fields(self):
        for root in ROOTED:
            with self.subTest(root=root), self.assertRaises(self.agents.SpecialistError):
                self.agents.validate_lesson(f"Keep {root}.")
            for field in self.agents.GLOBAL_CONTRACT_FIELDS:
                contract = self.fixture.contract()
                contract[field] = f"Keep {root}." if field == "domain" else [f"Keep {root}."]
                for payload in (contract, json.dumps(contract)):
                    with self.subTest(root=root, field=field, json=isinstance(payload, str)):
                        with self.assertRaises(self.agents.SpecialistError):
                            self.agents.normalize_global_contract(payload, domain_key="review")

    def test_legitimate_relative_text_and_quotes_still_round_trip(self):
        created = self.fixture.ensure()
        lesson = 'Check "quoted" ' + "; ".join(RELATIVE) + "."
        contract = self.fixture.contract('Review "quoted" terms')
        contract["input_shapes"] = [lesson]
        for payload in (contract, json.dumps(contract)):
            _, _, normalized = self.agents.normalize_global_contract(payload, domain_key="review")
            self.assertEqual(normalized, contract)
        saved = self.fixture.improve_with_lesson(
            name=created["name"], expected_sha256=created["sha256"], lesson=lesson,
            event_id=str(uuid.uuid4()),
        )
        recalled = self.registry.recall(name=created["name"], expected_sha256=saved["sha256"])
        self.assertIn(lesson, recalled["experience"])
        self.assertEqual(self.registry.status(for_routing=True)["registered_count"], 1)
        self.assertTrue(self.registry.complete_run(
            name=created["name"], expected_sha256=saved["sha256"], run_id=str(uuid.uuid4()),
            invocation_kind="spawn_agent", outcome="success",
        )["ok"])

    def test_public_persistence_rejects_root_forms_without_any_record_or_file_change(self):
        created = self.fixture.ensure()
        before = self.snapshot()
        for root in ROOTED:
            for command in ("improve", "complete-run"):
                argv = ["--codex-home", str(self.fixture.codex_home), command,
                        "--name", created["name"], "--expected-sha256", created["sha256"],
                        "--lesson", f"Keep {root}.", "--origin-term", "fixture-project"]
                if command == "complete-run":
                    argv += ["--run-id", str(uuid.uuid4()), "--invocation-kind", "spawn_agent", "--outcome", "success"]
                with self.subTest(root=root, command=command):
                    with self.assertRaises(self.agents.SpecialistError):
                        self.agents.dispatch(self.agents.build_parser().parse_args(argv))
                    self.assertEqual(self.snapshot(), before)
            bad = self.fixture.contract()
            bad["input_shapes"] = [f"Keep {root}."]
            with self.assertRaises(self.agents.SpecialistError):
                self.fixture.ensure(role_key="other-review", global_contract=bad)
            self.assertEqual(self.snapshot(), before)

    def test_migration_contract_and_correction_inputs_reject_roots_before_mutation(self):
        created = self.fixture.ensure()
        event_id = str(uuid.uuid4())
        self.fixture.improve_with_lesson(
            name=created["name"], expected_sha256=created["sha256"],
            lesson="Preserve original evidence.", event_id=event_id,
        )
        rows = self.fixture.downgrade_registry(3)
        plan_path = self.fixture.write_migration_plan(rows)
        original_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        before = self.snapshot()
        for root in ROOTED:
            for target in ("contract", "correction", "instructions"):
                plan = copy.deepcopy(original_plan)
                item = plan["roles"][0]
                if target == "contract":
                    item["global_contract"]["input_shapes"] = [f"Keep {root}."]
                elif target == "correction":
                    item["experience_corrections"] = [{"event_id": event_id, "lesson": f"Keep {root}."}]
                else:
                    item["instructions"] = f"Keep {root}."
                plan_path.write_text(json.dumps(plan), encoding="utf-8")
                with self.subTest(root=root, target=target), self.assertRaises(self.agents.SpecialistError):
                    self.agents.dispatch(self.agents.build_parser().parse_args([
                        "--codex-home", str(self.fixture.codex_home), "migrate-global", "--plan", str(plan_path),
                    ]))
                self.assertEqual(self.snapshot(), before)
        original_plan["roles"][0]["global_contract"]["input_shapes"] = list(RELATIVE)
        plan_path.write_text(json.dumps(original_plan), encoding="utf-8")
        self.assertTrue(self.registry.migrate_global(plan_path=plan_path)["ok"])


class CompletionReplayReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = registry_fixture.SpecialistRegistryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.registry = self.fixture.registry
        self.agents = registry_fixture.agents
        self.created = self.fixture.ensure()
        self.request = dict(
            name=self.created["name"], expected_sha256=self.created["sha256"],
            run_id=str(uuid.uuid4()), invocation_kind="spawn_agent", outcome="success",
            lesson="Preserve independently verified evidence.", origin_terms=("fixture-project",),
        )

    def snapshot(self):
        return self.fixture.registry_rows(), Path(self.created["path"]).read_bytes()

    def test_original_and_returned_sha_replay_are_read_only_and_do_not_duplicate(self):
        completed = self.registry.complete_run(**self.request)
        before = self.snapshot()
        for sha in (self.request["expected_sha256"], completed["sha256"]):
            replay = self.registry.complete_run(**dict(self.request, expected_sha256=sha))
            self.assertEqual(replay["action"], "completion_already_recorded")
            self.assertEqual(replay["experience_event_id"], completed["experience_event_id"])
            self.assertEqual(replay["sha256"], completed["sha256"])
            self.assertEqual(self.snapshot(), before)
        later = self.fixture.improve_with_lesson(
            name=self.created["name"], expected_sha256=completed["sha256"],
            lesson="Retain a later independent result.", event_id=str(uuid.uuid4()),
        )
        before = self.snapshot()
        replay = self.registry.complete_run(**dict(self.request, expected_sha256=later["sha256"]))
        self.assertEqual(replay["action"], "completion_already_recorded")
        self.assertEqual(self.snapshot(), before)

    def test_completion_receipt_replay_uses_live_ownership_not_a_stale_cas(self):
        completed = self.registry.complete_run(**self.request)
        before = self.snapshot()
        unrelated_sha = "f" * 64
        self.assertNotIn(
            unrelated_sha,
            (self.request["expected_sha256"], completed["sha256"]),
        )

        replay = self.registry.complete_run(
            **dict(self.request, expected_sha256=unrelated_sha)
        )
        self.assertEqual(replay["action"], "completion_already_recorded")
        self.assertEqual(self.snapshot(), before)

        with self.assertRaises(self.agents.SpecialistError):
            self.registry.complete_run(
                **dict(self.request, expected_sha256="not-a-sha256")
            )
        self.assertEqual(self.snapshot(), before)

    def test_conflicting_replays_and_first_write_stale_cas_are_rejected(self):
        completed = self.registry.complete_run(**self.request)
        before = self.snapshot()
        changes = (
            {"lesson": "A different result."},
            {"name": "other_specialist"},
            {"outcome": "failure"},
            {"invocation_kind": "followup_task"},
            {"loaded_experience_digest": "0" * 64},
            {"retracts_event_id": str(uuid.uuid4())},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(self.agents.SpecialistError):
                self.registry.complete_run(**dict(self.request, expected_sha256=completed["sha256"], **change))
            self.assertEqual(self.snapshot(), before)
        with self.assertRaises(self.agents.SpecialistError):
            self.registry.complete_run(**dict(self.request, run_id=str(uuid.uuid4())))
        self.assertEqual(self.snapshot(), before)
        with self.assertRaisesRegex(
            self.agents.SpecialistError,
            "recorded with a completion receipt",
        ):
            self.registry.record_run(
                name=self.request["name"],
                expected_sha256=completed["sha256"],
                run_id=self.request["run_id"],
                invocation_kind=self.request["invocation_kind"],
                outcome=self.request["outcome"],
            )
        self.assertEqual(self.snapshot(), before)

    def test_ordinary_run_id_cannot_be_replayed_as_a_completion(self):
        run_id = str(uuid.uuid4())
        self.registry.record_run(
            name=self.created["name"],
            expected_sha256=self.created["sha256"],
            run_id=run_id,
            invocation_kind="spawn_agent",
            outcome="success",
        )
        before = self.snapshot()

        with self.assertRaisesRegex(
            self.agents.SpecialistError,
            "without a completion receipt",
        ):
            self.registry.complete_run(
                name=self.created["name"],
                expected_sha256=self.created["sha256"],
                run_id=run_id,
                invocation_kind="spawn_agent",
                outcome="success",
            )
        self.assertEqual(self.snapshot(), before)

    def test_replay_cannot_omit_an_already_recorded_experience(self):
        completed = self.registry.complete_run(**self.request)
        before = self.snapshot()
        replay = dict(self.request, expected_sha256=completed["sha256"])
        replay.pop("lesson")

        with self.assertRaisesRegex(
            self.agents.SpecialistError,
            "different experience",
        ):
            self.registry.complete_run(**replay)
        self.assertEqual(self.snapshot(), before)

    def test_replay_cannot_add_experience_to_a_completion_without_one(self):
        request = dict(self.request)
        request.pop("lesson")
        completed = self.registry.complete_run(**request)
        before = self.snapshot()

        replay = self.registry.complete_run(
            **dict(request, expected_sha256=completed["sha256"])
        )
        self.assertEqual(replay["action"], "completion_already_recorded")
        self.assertEqual(replay["experience_action"], "not_requested")
        self.assertEqual(self.snapshot(), before)

        with self.assertRaisesRegex(
            self.agents.SpecialistError,
            "different experience",
        ):
            self.registry.complete_run(
                **dict(
                    request,
                    expected_sha256=completed["sha256"],
                    lesson="A later experience must not change the receipt.",
                )
            )
        self.assertEqual(self.snapshot(), before)

    def test_unrelated_experience_does_not_block_no_experience_replay(self):
        unrelated = self.fixture.improve_with_lesson(
            name=self.created["name"],
            expected_sha256=self.created["sha256"],
            lesson="An unrelated retained result.",
            event_id=str(uuid.uuid4()),
        )
        request = dict(self.request, expected_sha256=unrelated["sha256"])
        request.pop("lesson")
        completed = self.registry.complete_run(**request)
        before = self.snapshot()

        replay = self.registry.complete_run(
            **dict(request, expected_sha256=completed["sha256"])
        )
        self.assertEqual(replay["action"], "completion_already_recorded")
        self.assertEqual(replay["experience_action"], "not_requested")
        self.assertEqual(self.snapshot(), before)

    def test_completed_replay_still_rejects_actual_owned_file_drift(self):
        result = self.registry.complete_run(**self.request)
        path = Path(self.created["path"])
        path.write_bytes(path.read_bytes() + b"\n# untracked edit\n")
        before = self.snapshot()
        with self.assertRaises(self.agents.SpecialistError):
            self.registry.complete_run(**dict(self.request, expected_sha256=result["sha256"]))
        self.assertEqual(self.snapshot(), before)

    def test_correction_replay_with_returned_sha_preserves_target_and_raw_events(self):
        old = self.registry.complete_run(**self.request)
        corrected_request = dict(
            self.request, run_id=str(uuid.uuid4()), expected_sha256=old["sha256"],
            lesson="Correct the earlier interpretation.", retracts_event_id=old["experience_event_id"],
        )
        result = self.registry.complete_run(**corrected_request)
        before = self.snapshot()
        replay = self.registry.complete_run(**dict(corrected_request, expected_sha256=result["sha256"]))
        self.assertEqual(replay["experience_action"], "experience_correction_already_recorded")
        self.assertEqual(replay["retracts_event_id"], old["experience_event_id"])
        self.assertEqual(self.snapshot(), before)

    def test_migrated_legacy_event_cannot_stand_in_for_a_completion_receipt(self):
        legacy_id = str(uuid.uuid5(uuid.UUID(self.request["run_id"]),
                                  f"retained-completion:{self.request['expected_sha256']}"))
        # Produce a valid old-format completion, including its TOML digest.
        real_uuid5 = self.agents.uuid.uuid5
        with mock.patch.object(self.agents.uuid, "uuid5", side_effect=lambda ns, name:
                               uuid.UUID(legacy_id) if ns == uuid.UUID(self.request["run_id"])
                               else real_uuid5(ns, name)):
            recorded = self.registry.complete_run(**self.request)
        # Model a migrated v6 row: the run and old CAS-bound event survive, but
        # no historical command can safely backfill a completion receipt.
        with contextlib.closing(self.fixture.db()) as connection:
            connection.execute(
                "UPDATE agent_runs SET completion_receipt_version=NULL, "
                "completion_experience_event_id=NULL WHERE run_id=?",
                (self.request["run_id"],),
            )
            connection.commit()
        before = self.snapshot()
        self.assertEqual(recorded["experience_event_id"], legacy_id)
        omitted_original = dict(self.request)
        omitted_original.pop("lesson")
        current = dict(self.request, expected_sha256=recorded["sha256"])
        omitted_current = dict(self.request, expected_sha256=recorded["sha256"])
        omitted_current.pop("lesson")
        for replay in (self.request, omitted_original, current, omitted_current):
            with self.subTest(replay_has_lesson="lesson" in replay), self.assertRaisesRegex(
                self.agents.SpecialistError,
                "cannot prove.*recorded by complete-run",
            ):
                self.registry.complete_run(**replay)
            self.assertEqual(self.snapshot(), before)

    def test_migrated_unknown_run_rejects_a_separately_appended_stable_event(self):
        run_id = str(uuid.uuid4())
        self.registry.record_run(
            name=self.created["name"], expected_sha256=self.created["sha256"],
            run_id=run_id, invocation_kind="spawn_agent", outcome="success",
        )
        event_id = str(uuid.uuid5(uuid.UUID(run_id), "retained-completion:v2"))
        saved = self.fixture.improve_with_lesson(
            name=self.created["name"], expected_sha256=self.created["sha256"],
            lesson=self.request["lesson"], event_id=event_id,
        )
        with contextlib.closing(self.fixture.db()) as connection:
            connection.execute(
                "UPDATE agent_runs SET completion_receipt_version=NULL "
                "WHERE run_id=?",
                (run_id,),
            )
            connection.commit()
        before = self.snapshot()

        with self.assertRaisesRegex(
            self.agents.SpecialistError,
            "cannot prove.*recorded by complete-run",
        ):
            self.registry.complete_run(
                name=self.created["name"], expected_sha256=saved["sha256"],
                run_id=run_id, invocation_kind="spawn_agent", outcome="success",
                lesson=self.request["lesson"], origin_terms=("fixture-project",),
            )
        self.assertEqual(self.snapshot(), before)


    def test_preexisting_unbound_event_cannot_be_claimed_as_a_completion(self):
        event_id = str(uuid.uuid5(uuid.UUID(self.request["run_id"]), "retained-completion:v2"))
        saved = self.fixture.improve_with_lesson(
            name=self.created["name"], expected_sha256=self.created["sha256"],
            lesson=self.request["lesson"], event_id=event_id,
        )
        before = self.snapshot()
        with self.assertRaisesRegex(self.agents.SpecialistError, "earlier operation"):
            self.registry.complete_run(**dict(self.request, expected_sha256=saved["sha256"]))
        self.assertEqual(self.snapshot(), before)


class MaintenanceLockReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.cost = load_script("cost_check")
        self.installer = load_script("install_plugin")
        self.release = load_script("bump_plugin_version")
        self.state = self.home / "lean-stack" / self.cost.STATE_NAME
        self.state.parent.mkdir()
        self.agents_path = self.home / "AGENTS.md"
        self.agents_path.write_text("Keep the existing body.\n", encoding="utf-8")
        self.manifest = self.home / ".codex-plugin" / "plugin.json"
        self.manifest.parent.mkdir()
        self.manifest.write_text(json.dumps({"name": "example", "version": "1.0.0"}), encoding="utf-8")
        self.holder_path = self.home / "holder.py"
        self.holder_path.write_text(
            "import importlib.util, os, sys\nfrom pathlib import Path\n"
            "spec=importlib.util.spec_from_file_location('holder_module',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "with getattr(m,sys.argv[2])(Path(sys.argv[3])):\n"
            " print('LOCKED',flush=True)\n"
            " if sys.stdin.readline().strip()=='exit': os._exit(91)\n",
            encoding="utf-8",
        )

    @contextlib.contextmanager
    def holder(self, module, function, path):
        child = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(self.holder_path), str(SCRIPTS / (module + ".py")), function, str(path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        )
        reader = ThreadPoolExecutor(max_workers=1)
        try:
            self.assertEqual(reader.submit(child.stdout.readline).result(timeout=10), "LOCKED\n")
            yield child
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
            reader.shutdown(wait=True)

    def test_install_abrupt_exit_and_kill_release_without_touching_document(self):
        for mode in ("exit", "kill"):
            with self.subTest(mode=mode):
                before = self.agents_path.read_bytes()
                with self.holder("install_plugin", "update_lock", self.agents_path) as child:
                    if mode == "exit":
                        child.communicate("exit\n", timeout=10)
                        self.assertEqual(child.returncode, 91)
                    else:
                        child.kill(); child.wait(timeout=10)
                self.assertEqual(self.agents_path.read_bytes(), before)
                self.assertTrue(self.installer.preflight_default_invocation(self.home)["ok"])
                self.assertEqual(self.agents_path.read_bytes(), before)
                result = self.installer.ensure_default_invocation(self.home)
                self.assertTrue(result["ok"])

    def test_install_live_holder_blocks_preflight_and_releases(self):
        before = self.agents_path.read_bytes()
        with self.holder("install_plugin", "update_lock", self.agents_path) as child:
            with self.assertRaises(self.installer.InstallError):
                self.installer.preflight_default_invocation(self.home)
            self.assertEqual(self.agents_path.read_bytes(), before)
            child.communicate("release\n", timeout=10)
            self.assertEqual(child.returncode, 0)
        self.assertTrue(self.installer.preflight_default_invocation(self.home)["ok"])

    def test_release_abrupt_exit_and_kill_do_not_block_next_version_update(self):
        for mode in ("exit", "kill"):
            with self.subTest(mode=mode):
                version = json.loads(self.manifest.read_text())["version"]
                before = self.manifest.read_bytes()
                with self.holder("bump_plugin_version", "release_lock", self.manifest) as child:
                    if mode == "exit":
                        child.communicate("exit\n", timeout=10)
                        self.assertEqual(child.returncode, 91)
                    else:
                        child.kill(); child.wait(timeout=10)
                self.assertEqual(self.manifest.read_bytes(), before)
                self.assertTrue(self.release.update_plugin_version(
                    self.home, change="fix", expected_version=version, cachebuster="probe",
                )["ok"])

    @unittest.skipIf(os.name == "nt", "POSIX directory locking and rename semantics")
    def test_replacing_cost_anchor_cannot_admit_a_second_writer(self):
        first = self.cost.record(codex_home=self.home, checked_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc), expected_state_sha256=None)
        before = self.state.read_bytes()
        anchor = self.state.with_name(f".{self.state.name}.lock")
        with self.holder("cost_check", "record_lock", self.state) as child:
            old_identity = os.stat(anchor)
            replacement = anchor.with_name("replacement")
            replacement.touch()
            os.replace(replacement, anchor)
            self.assertFalse(os.path.samestat(old_identity, os.stat(anchor)))
            contender = subprocess.run(
                [sys.executable, "-X", "utf8", str(SCRIPTS / "cost_check.py"), "--codex-home", str(self.home),
                 "record", "--checked-at", "2026-09-02T00:00:00Z", "--expected-state-sha256", first["state_sha256"]],
                capture_output=True, text=True, encoding="utf-8", timeout=10,
            )
            self.assertEqual(contender.returncode, 2, contender.stdout + contender.stderr)
            self.assertEqual(self.state.read_bytes(), before)
            child.communicate("release\n", timeout=10)
        self.assertTrue(self.cost.record(codex_home=self.home, checked_at=dt.datetime(2026, 9, 2, tzinfo=dt.timezone.utc), expected_state_sha256=first["state_sha256"])["ok"])


    def test_all_helpers_release_after_caught_exceptions(self):
        for module, function, target in (
            (self.cost, "record_lock", self.state),
            (self.installer, "update_lock", self.agents_path),
            (self.release, "release_lock", self.manifest),
        ):
            with self.subTest(function=function):
                with self.assertRaisesRegex(ValueError, "injected"):
                    with getattr(module, function)(target):
                        raise ValueError("injected")
                with getattr(module, function)(target):
                    pass

    def test_preopen_anchor_replacement_is_rejected_for_each_helper(self):
        cases = (
            (self.cost, "record_lock", self.state, self.state.with_name(f".{self.state.name}.lock"), self.cost.CostCheckError),
            (self.installer, "update_lock", self.agents_path, self.home / ".AGENTS.md.lean-stack.lock", self.installer.InstallError),
            (self.release, "release_lock", self.manifest, self.manifest.with_name("plugin.json.release.lock"), self.release.VersionError),
        )
        for module, function, target, anchor, error in cases:
            with self.subTest(function=function):
                anchor.touch()
                replacement = anchor.with_name(anchor.name + ".replacement")
                replacement.touch()
                original_open = os.open
                swapped = False
                def swap_before_open(path, *args, **kwargs):
                    nonlocal swapped
                    if Path(path) == anchor and not swapped:
                        self.assertFalse(args[0] & os.O_CREAT)
                        swapped = True
                        os.replace(replacement, anchor)
                    return original_open(path, *args, **kwargs)
                with mock.patch.object(os, "open", side_effect=swap_before_open):
                    with self.assertRaisesRegex(error, "changed"):
                        with getattr(module, function)(target):
                            self.fail("replacement must not enter the critical section")
                self.assertTrue(swapped)
                with getattr(module, function)(target):
                    pass

    def test_nonempty_legacy_install_and_release_markers_are_not_stolen(self):
        for module, function, target, anchor, error in (
            (self.installer, "update_lock", self.agents_path, self.home / ".AGENTS.md.lean-stack.lock", self.installer.InstallError),
            (self.release, "release_lock", self.manifest, self.manifest.with_name("plugin.json.release.lock"), self.release.VersionError),
        ):
            with self.subTest(function=function):
                original = target.read_bytes()
                marker = b"pid=12345\n"
                anchor.write_bytes(marker)
                with self.assertRaisesRegex(error, "legacy lock"):
                    with getattr(module, function)(target):
                        self.fail("unknown legacy marker must not be taken over")
                self.assertEqual(anchor.read_bytes(), marker)
                self.assertEqual(target.read_bytes(), original)

    def test_install_and_release_reject_linked_anchors_before_mutation(self):
        outside = self.home / "unrelated"
        outside.write_bytes(b"must remain unchanged")
        for module, function, target, anchor, error in (
            (self.installer, "update_lock", self.agents_path, self.home / ".AGENTS.md.lean-stack.lock", self.installer.InstallError),
            (self.release, "release_lock", self.manifest, self.manifest.with_name("plugin.json.release.lock"), self.release.VersionError),
        ):
            with self.subTest(function=function):
                original = target.read_bytes()
                os.link(outside, anchor)
                with self.assertRaises(error):
                    with getattr(module, function)(target):
                        self.fail("hard links must not enter the critical section")
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(outside.read_bytes(), b"must remain unchanged")
                anchor.unlink()

    def test_standalone_cli_loads_sibling_from_unrelated_working_directory(self):
        for name in ("cost_check", "install_plugin", "bump_plugin_version"):
            with self.subTest(name=name):
                result = subprocess.run(
                    [sys.executable, "-X", "utf8", str(SCRIPTS / (name + ".py")), "--help"],
                    cwd=self.home, capture_output=True, text=True, encoding="utf-8", timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
