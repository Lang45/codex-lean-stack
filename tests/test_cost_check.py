from __future__ import annotations

import ast
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "skills" / "lean-stack" / "scripts" / "cost_check.py"
SPEC = importlib.util.spec_from_file_location("lean_stack_cost_check", SCRIPT_PATH)
assert SPEC and SPEC.loader
COST_CHECK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COST_CHECK
SPEC.loader.exec_module(COST_CHECK)

UTC = dt.timezone.utc


class CostCheckTests(unittest.TestCase):
    def make_home(self, temporary: str) -> Path:
        home = Path(temporary) / "codex-home"
        home.mkdir()
        return home

    def record(self, home: Path, checked_at: dt.datetime, expected: str | None = None):
        return COST_CHECK.record(
            codex_home=home,
            checked_at=checked_at,
            expected_state_sha256=expected,
        )

    def test_initial_baseline_is_current_until_exact_seven_day_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            before = COST_CHECK.status(
                codex_home=home,
                now=dt.datetime(2026, 9, 2, 23, 59, 59, tzinfo=UTC),
            )
            due = COST_CHECK.status(
                codex_home=home,
                now=dt.datetime(2026, 9, 3, 0, 0, 0, tzinfo=UTC),
            )

        self.assertFalse(before["due"])
        self.assertEqual(before["action"], "fixed_baseline_current")
        self.assertTrue(due["due"])
        self.assertEqual(due["action"], "official_check_due")
        self.assertFalse(due["network_used"])
        self.assertFalse(due["plugin_modified"])

    def test_record_resets_the_due_date_without_modifying_the_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            checked_at = dt.datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
            recorded = self.record(home, checked_at)
            before = COST_CHECK.status(
                codex_home=home,
                now=checked_at + dt.timedelta(days=7) - dt.timedelta(microseconds=1),
            )
            due = COST_CHECK.status(
                codex_home=home,
                now=checked_at + dt.timedelta(days=7),
            )

        self.assertFalse(before["due"])
        self.assertTrue(due["due"])
        self.assertFalse(recorded["network_used"])
        self.assertFalse(recorded["plugin_modified"])

    def test_future_record_and_existing_future_state_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            future = dt.datetime(2099, 1, 1, tzinfo=UTC)
            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "cannot be in the future"):
                self.record(home, future)

            state_dir = home / "lean-stack"
            state_dir.mkdir()
            (state_dir / COST_CHECK.STATE_NAME).write_text(
                json.dumps(
                    {"version": 1, "checked_at": "2099-01-01T00:00:00Z"}
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "timestamp is in the future"):
                COST_CHECK.status(
                    codex_home=home,
                    now=dt.datetime(2026, 9, 5, tzinfo=UTC),
                )

    def test_existing_state_requires_its_current_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            first = self.record(home, dt.datetime(2026, 9, 2, tzinfo=UTC))
            state_path = Path(first["state_path"])
            original = state_path.read_bytes()

            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "requires"):
                self.record(home, dt.datetime(2026, 9, 3, tzinfo=UTC))
            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "stale"):
                self.record(
                    home,
                    dt.datetime(2026, 9, 3, tzinfo=UTC),
                    expected="0" * 64,
                )
            self.assertEqual(state_path.read_bytes(), original)

            updated = self.record(
                home,
                dt.datetime(2026, 9, 3, tzinfo=UTC),
                expected=first["state_sha256"],
            )
            status = COST_CHECK.status(
                codex_home=home,
                now=dt.datetime(2026, 9, 3, tzinfo=UTC),
            )

        self.assertNotEqual(updated["state_sha256"], first["state_sha256"])
        self.assertEqual(status["checked_at"], "2026-09-03T00:00:00Z")

    def test_state_contains_only_version_and_checked_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            result = self.record(home, dt.datetime(2026, 9, 2, tzinfo=UTC))
            payload = json.loads(Path(result["state_path"]).read_text(encoding="utf-8"))

        self.assertEqual(set(payload), {"version", "checked_at"})

    def test_legacy_state_is_read_and_normalized_on_next_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            state_dir = home / "lean-stack"
            state_dir.mkdir()
            state_path = state_dir / COST_CHECK.STATE_NAME
            state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "checked_at": "2026-08-26T15:31:12.492528Z",
                        "official_fingerprint": "a" * 64,
                        "sources": ["https://learn.chatgpt.com/docs/pricing"],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            legacy = COST_CHECK.status(
                codex_home=home,
                now=dt.datetime(2026, 8, 27, tzinfo=UTC),
            )
            updated = self.record(
                home,
                dt.datetime(2026, 8, 27, tzinfo=UTC),
                expected=legacy["state_sha256"],
            )
            payload = json.loads(Path(updated["state_path"]).read_text(encoding="utf-8"))

        self.assertTrue(legacy["legacy_state"])
        self.assertTrue(legacy["normalized_on_next_record"])
        self.assertEqual(set(payload), {"version", "checked_at"})

    def test_invalid_legacy_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            state_dir = home / "lean-stack"
            state_dir.mkdir()
            (state_dir / COST_CHECK.STATE_NAME).write_text(
                json.dumps(
                    {
                        "version": 1,
                        "checked_at": "2026-08-26T15:31:12.492528Z",
                        "official_fingerprint": "not-a-digest",
                        "sources": ["https://example.com/pricing"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "legacy"):
                COST_CHECK.status(
                    codex_home=home,
                    now=dt.datetime(2026, 8, 27, tzinfo=UTC),
                )

    def test_invalid_state_shape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            state_dir = home / "lean-stack"
            state_dir.mkdir()
            (state_dir / COST_CHECK.STATE_NAME).write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "unexpected shape"):
                COST_CHECK.status(
                    codex_home=home,
                    now=dt.datetime(2026, 9, 2, tzinfo=UTC),
                )

    def test_state_with_multiple_hard_links_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            recorded = self.record(home, dt.datetime(2026, 9, 2, tzinfo=UTC))
            os.link(recorded["state_path"], home / "second-link.json")
            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "one regular file"):
                COST_CHECK.status(
                    codex_home=home,
                    now=dt.datetime(2026, 9, 2, tzinfo=UTC),
                )

    def test_state_symbolic_link_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            state_dir = home / "lean-stack"
            state_dir.mkdir()
            target = home / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            try:
                os.symlink(target, state_dir / COST_CHECK.STATE_NAME)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")
            with self.assertRaisesRegex(COST_CHECK.CostCheckError, "link or reparse"):
                COST_CHECK.status(
                    codex_home=home,
                    now=dt.datetime(2026, 9, 2, tzinfo=UTC),
                )

    def test_cli_returns_json_and_a_nonzero_code_for_safe_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = self.make_home(temporary)
            self.record(home, dt.datetime(2026, 9, 1, tzinfo=UTC))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                success = COST_CHECK.main(
                    [
                        "--codex-home",
                        str(home),
                        "status",
                        "--now",
                        "2026-09-01T00:00:00Z",
                    ]
                )
            self.assertEqual(success, 0)
            self.assertTrue(json.loads(output.getvalue())["ok"])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                skipped = COST_CHECK.main(
                    [
                        "--codex-home",
                        str(home),
                        "record",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(skipped, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "weekly_check_skipped")

    def test_script_has_no_network_client(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = ("http", "requests", "socket", "urllib.request", "websocket")
        self.assertFalse(
            any(name == item or name.startswith(item + ".") for name in imported for item in forbidden)
        )
        self.assertNotIn("urlopen(", source)


if __name__ == "__main__":
    unittest.main()
