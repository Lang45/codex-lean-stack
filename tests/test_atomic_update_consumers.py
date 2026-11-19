"""Exercise the public maintenance consumers with a late external writer."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "skills/lean-stack/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("consumer_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install = load("install_plugin")
bump = load("bump_plugin_version")


class AtomicUpdateConsumerTests(unittest.TestCase):
    def setUp(self):
        # Deliberately retained: these files are publication/recovery evidence.
        self.workspace = Path(tempfile.mkdtemp(prefix="atomic-consumers-"))

    @staticmethod
    def external_write(path, data):
        subprocess.run(
            [sys.executable, "-B", "-c",
             "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(bytes.fromhex(sys.argv[2]))",
             str(path), data.hex()],
            check=True, capture_output=True,
        )

    def make_manifest(self):
        root = self.workspace / "plugin"
        metadata = root / ".codex-plugin"
        metadata.mkdir(parents=True)
        path = metadata / "plugin.json"
        path.write_text(json.dumps({"name": "example-plugin", "version": "1.0.0"}), encoding="utf-8")
        return root, path

    def test_global_instruction_consumer_retains_a_late_external_edit(self):
        home = self.workspace / "codex-home"
        home.mkdir()
        path = home / "AGENTS.md"
        path.write_bytes(b"original\n")
        concurrent = b"externally saved instructions\n"
        publish = install._updates._exchange

        def late_writer(*args):
            self.external_write(path, concurrent)
            return publish(*args)

        with mock.patch.object(install._updates, "_exchange", side_effect=late_writer):
            with self.assertRaisesRegex(OSError, "was published") as conflict:
                install.ensure_default_invocation(home)
        self.assertEqual(conflict.exception.recovery_path.read_bytes(), concurrent)
        self.assertIn(install.DEFAULT_INVOCATION_LINE.encode("utf-8"), path.read_bytes())

    def test_version_consumer_retains_a_late_external_edit(self):
        root, path = self.make_manifest()
        concurrent = b'{"name":"example-plugin","version":"1.0.0","external":"saved"}\n'
        publish = bump._updates._exchange

        def late_writer(*args):
            self.external_write(path, concurrent)
            return publish(*args)

        with mock.patch.object(bump._updates, "_exchange", side_effect=late_writer):
            with self.assertRaisesRegex(OSError, "was published") as conflict:
                bump.update_plugin_version(root, change="fix", expected_version="1.0.0", cachebuster="fixed")
        self.assertEqual(conflict.exception.recovery_path.read_bytes(), concurrent)
        self.assertEqual(json.loads(path.read_bytes())["version"], "1.0.1+codex.fixed")

    def test_success_receipts_retain_previous_bytes_outside_the_source_package(self):
        root, path = self.make_manifest()
        original = path.read_bytes()
        result = bump.update_plugin_version(root, change="fix", expected_version="1.0.0", cachebuster="fixed")
        previous = Path(result["previous_path"])
        self.assertEqual(previous.read_bytes(), original)
        self.assertFalse(previous.is_relative_to(root))
        self.assertTrue(result["modified"])


if __name__ == "__main__":
    unittest.main()
