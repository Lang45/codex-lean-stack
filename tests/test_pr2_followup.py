"""Regression checks for PR #2 lock recovery and front-matter preservation.

All processes and writes are confined to temporary homes. No real Codex install
or user configuration is used. Process death is real, not a mocked exception.
"""
from __future__ import annotations

import codecs
import contextlib
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_chain_audit import SCRIPTS, load_script


class CostLockRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.cost = load_script("cost_check")
        self.state = self.home / "lean-stack" / self.cost.STATE_NAME
        self.state.parent.mkdir()
        self.anchor = self.state.with_name(f".{self.state.name}.lock")
        self.when = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
        self.holder_script = self.home / "holder.py"
        self.holder_script.write_text(
            "import importlib.util, os, sys\n"
            "from pathlib import Path\n"
            "spec = importlib.util.spec_from_file_location('cost', sys.argv[1])\n"
            "cost = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(cost)\n"
            "with cost.record_lock(Path(sys.argv[2])):\n"
            "    print('LOCKED', flush=True)\n"
            "    if sys.stdin.readline().strip() == 'exit':\n"
            "        os._exit(91)\n",
            encoding="utf-8",
        )

    def record(self, expected=None):
        return self.cost.record(
            codex_home=self.home, checked_at=self.when,
            expected_state_sha256=expected,
        )

    @contextlib.contextmanager
    def holder(self):
        with subprocess.Popen(
            [sys.executable, "-X", "utf8", str(self.holder_script),
             str(SCRIPTS / "cost_check.py"), str(self.state)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        ) as child, ThreadPoolExecutor(max_workers=1) as reader:
            try:
                self.assertEqual(reader.submit(child.stdout.readline).result(timeout=10), "LOCKED\n")
                yield child
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=10)

    def test_abrupt_exit_releases_lock_for_first_and_existing_state(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                initial = self.record() if existing else None
                expected = initial["state_sha256"] if initial else None
                with self.holder() as child:
                    child.communicate("exit\n", timeout=10)
                    self.assertEqual(child.returncode, 91)
                self.assertTrue(self.anchor.is_file())
                identity = self.anchor.stat()
                self.assertTrue(self.record(expected)["ok"])
                self.assertTrue(os.path.samestat(identity, self.anchor.stat()))
                self.state.unlink()

    def test_killed_holder_releases_lock_without_manual_cleanup(self):
        initial = self.record()
        before = self.state.read_bytes()
        with self.holder() as child:
            child.kill()
            child.wait(timeout=10)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertTrue(self.record(initial["state_sha256"])["ok"])

    def test_live_holder_blocks_other_process_and_preserves_state(self):
        initial = self.record()
        before = self.state.read_bytes()
        with self.holder() as child:
            contender = subprocess.run(
                [sys.executable, "-X", "utf8", str(SCRIPTS / "cost_check.py"),
                 "--codex-home", str(self.home), "record", "--checked-at",
                 self.cost.format_time(self.when), "--expected-state-sha256", initial["state_sha256"]],
                capture_output=True, text=True, encoding="utf-8", timeout=10,
            )
            self.assertEqual(contender.returncode, 2, contender.stderr)
            self.assertEqual(json.loads(contender.stdout)["action"], self.cost.BUSY_ACTION)
            self.assertEqual(self.state.read_bytes(), before)
            child.communicate("release\n", timeout=10)
            self.assertEqual(child.returncode, 0)
        self.assertTrue(self.record(initial["state_sha256"])["ok"])

    def test_unlocked_anchor_is_reused_without_replacement(self):
        self.anchor.touch()
        identity = self.anchor.stat()
        first = self.record()
        self.assertTrue(self.record(first["state_sha256"])["ok"])
        self.assertTrue(os.path.samestat(identity, self.anchor.stat()))

    def test_exception_releases_the_kernel_lock(self):
        with self.assertRaisesRegex(RuntimeError, "injected"):
            with self.cost.record_lock(self.state):
                raise RuntimeError("injected failure inside the critical section")
        self.assertTrue(self.record()["ok"])

    def test_lock_rejects_hard_link_and_directory_without_touching_state(self):
        target = self.home / "unrelated"
        target.write_bytes(b"preserve me")
        os.link(target, self.anchor)
        with self.assertRaises(self.cost.CostCheckError):
            self.record()
        self.assertEqual(target.read_bytes(), b"preserve me")
        self.assertFalse(self.state.exists())
        self.anchor.unlink()
        self.anchor.mkdir()
        with self.assertRaises((self.cost.CostCheckError, OSError)):
            self.record()
        self.assertFalse(self.state.exists())

    def test_lock_rejects_dangling_and_existing_symlinks(self):
        target = self.home / "unrelated"
        try:
            self.anchor.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        for existing in (False, True):
            if existing:
                target.write_bytes(b"preserve me")
            with self.subTest(existing=existing), self.assertRaises((self.cost.CostCheckError, OSError)):
                self.record()
            self.assertFalse(self.state.exists())
            self.assertEqual(target.exists(), existing)
        self.assertEqual(target.read_bytes(), b"preserve me")


class FrontMatterPreservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.path = self.home / "AGENTS.md"
        self.installer = load_script("install_plugin")
        self.line = self.installer.DEFAULT_INVOCATION_LINE

    def test_front_matter_is_first_and_preserved_byte_for_byte(self):
        for newline in ("\n", "\r\n", "\r"):
            for bom in (b"", codecs.BOM_UTF8):
                for closing in ("---", "..."):
                    with self.subTest(newline=repr(newline), bom=bool(bom), closing=closing):
                        header = newline.join(("---", 'title: "Agent instructions"',
                            'note: "<!-- not an HTML comment -->"', "example: |", "  ---",
                            "  " + self.line, closing)) + newline
                        body = "# Existing instructions" + newline + "Keep this body unchanged."
                        original = bom + (header + body).encode("utf-8")
                        self.path.write_bytes(original)
                        self.assertFalse(self.installer._has_default_invocation(header + body))
                        self.assertTrue(self.installer.ensure_default_invocation(self.home)["modified"])
                        expected = bom + (header + newline + self.line + newline * 2 + body).encode("utf-8")
                        self.assertEqual(self.path.read_bytes(), expected)
                        self.assertTrue(self.installer._has_default_invocation(expected.decode("utf-8-sig")))
                        self.assertFalse(self.installer.ensure_default_invocation(self.home)["modified"])
                        self.assertEqual(self.path.read_bytes(), expected)

    def test_empty_front_matter_and_closing_at_eof(self):
        for text in ("---\n---", "---\n...", "---\n---\n", "---\ntitle: Example\n---"):
            with self.subTest(text=text):
                self.path.write_bytes(text.encode())
                self.installer.ensure_default_invocation(self.home)
                separator = "\n" if text.endswith("\n") else "\n\n"
                expected = text + separator + self.line + "\n\n"
                self.assertEqual(self.path.read_bytes(), expected.encode("utf-8"))
                self.assertFalse(self.installer.ensure_default_invocation(self.home)["modified"])

    def test_existing_body_activation_does_not_rewrite_front_matter(self):
        original = codecs.BOM_UTF8 + ("---\r\ntitle: Example\r\n---\r\n\r\n" + self.line + "\r\n").encode("utf-8")
        self.path.write_bytes(original)
        self.assertFalse(self.installer.ensure_default_invocation(self.home)["modified"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_unterminated_front_matter_is_rejected_without_writes(self):
        for text in ("---", "---\ntitle: Example\n", "---\nexample: |\n  ---\n  " + self.line):
            for operation in (self.installer.preflight_default_invocation, self.installer.ensure_default_invocation):
                with self.subTest(text=text, operation=operation.__name__):
                    self.path.write_bytes(text.encode("utf-8"))
                    with self.assertRaisesRegex(self.installer.InstallError, "front matter"):
                        operation(self.home)
                    self.assertEqual(self.path.read_bytes(), text.encode("utf-8"))
                    self.assertFalse(list(self.home.glob("*.tmp")))

    def test_unterminated_front_matter_stops_install_before_subprocess(self):
        original = b"---\ntitle: Incomplete\n"
        self.path.write_bytes(original)
        runner = mock.Mock()
        with mock.patch.object(self.installer, "read_manifest", return_value=("codex-lean-stack", "5.2.14")), \
             mock.patch.object(self.installer, "verify_marketplace_source"), \
             mock.patch.object(self.installer.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(self.installer.InstallError, "front matter"):
                self.installer.install_plugin(self.home, codex_home=self.home, runner=runner)
        runner.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
