from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "lean-stack"
    / "scripts"
    / "bump_plugin_version.py"
)
SPEC = importlib.util.spec_from_file_location("lean_stack_bump_plugin_version", SCRIPT)
assert SPEC and SPEC.loader
bump_plugin_version = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bump_plugin_version)


class PluginVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest = self.root / ".codex-plugin" / "plugin.json"
        self.manifest.parent.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self, version: str = "0.1.0+codex.old") -> bytes:
        payload = {
            "name": "example-plugin",
            "version": version,
            "description": "Preserve me.",
            "skills": "./skills/",
            "interface": {"displayName": "示例"},
        }
        data = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        self.manifest.write_bytes(data)
        return data

    def read_manifest(self) -> dict[str, object]:
        return json.loads(self.manifest.read_text(encoding="utf-8"))

    def test_release_contract(self) -> None:
        cases = {
            "feature": "0.2.0+codex.fixed",
            "fix": "0.1.1+codex.fixed",
            "breaking": "1.0.0+codex.fixed",
        }
        for change, expected in cases.items():
            with self.subTest(change=change):
                self.write_manifest()
                result = bump_plugin_version.update_plugin_version(
                    self.root,
                    change=change,
                    expected_version="0.1.0+codex.old",
                    cachebuster="fixed",
                )
                manifest = self.read_manifest()
                self.assertEqual(manifest["version"], expected)
                self.assertEqual(manifest["description"], "Preserve me.")
                self.assertEqual(result["new_version"], expected)
                self.assertIn(b"\\u793a\\u4f8b", self.manifest.read_bytes())

        # Dry-run and compare-and-swap prevent accidental double bumps.
        original = self.write_manifest()
        preview = bump_plugin_version.update_plugin_version(
            self.root,
            change="feature",
            expected_version="0.1.0+codex.old",
            cachebuster="fixed",
            dry_run=True,
        )
        self.assertFalse(preview["modified"])
        self.assertEqual(self.manifest.read_bytes(), original)

        bump_plugin_version.update_plugin_version(
            self.root,
            change="feature",
            expected_version="0.1.0+codex.old",
            cachebuster="fixed",
        )
        once = self.manifest.read_bytes()
        with self.assertRaises(bump_plugin_version.VersionError):
            bump_plugin_version.update_plugin_version(
                self.root,
                change="feature",
                expected_version="0.1.0+codex.old",
                cachebuster="second",
            )
        self.assertEqual(self.manifest.read_bytes(), once)

        # Invalid inputs never change the original bytes.
        cases = [
            ("0.1+codex.old", "fixed"),
            ("0.1.0+foreign.meta", "fixed"),
            ("0.1.0+codex.old", "INVALID TOKEN"),
            ("0.1.0+codex.old", "two--hyphens"),
        ]
        for version, token in cases:
            with self.subTest(version=version, token=token):
                original = self.write_manifest(version)
                with self.assertRaises(bump_plugin_version.VersionError):
                    bump_plugin_version.update_plugin_version(
                        self.root,
                        change="feature",
                        expected_version=version,
                        cachebuster=token,
                    )
                self.assertEqual(self.manifest.read_bytes(), original)

        # Lock contention and atomic replace failure preserve the manifest.
        original = self.write_manifest()
        lock = self.manifest.with_name(f"{self.manifest.name}.release.lock")
        lock.write_text("existing\n", encoding="ascii")
        with self.assertRaises(bump_plugin_version.VersionError):
            bump_plugin_version.update_plugin_version(
                self.root,
                change="feature",
                expected_version="0.1.0+codex.old",
                cachebuster="fixed",
            )
        self.assertEqual(self.manifest.read_bytes(), original)
        lock.unlink()

        with mock.patch.object(
            bump_plugin_version.os, "replace", side_effect=OSError("replace failed")
        ):
            with self.assertRaises(OSError):
                bump_plugin_version.update_plugin_version(
                    self.root,
                    change="feature",
                    expected_version="0.1.0+codex.old",
                    cachebuster="fixed",
                )
        self.assertEqual(self.manifest.read_bytes(), original)
        self.assertFalse(lock.exists())
        self.assertEqual(list(self.manifest.parent.glob(".plugin.json.*.tmp")), [])

        # A reparse-point metadata directory is rejected before any write.
        original = self.write_manifest()
        real_lstat = bump_plugin_version.os.lstat

        def marked_reparse(path):
            metadata = real_lstat(path)
            if Path(path) == self.manifest.parent:
                metadata = mock.Mock(
                    st_mode=metadata.st_mode,
                    st_file_attributes=(
                        getattr(metadata, "st_file_attributes", 0)
                        | bump_plugin_version.REPARSE_POINT_FLAG
                    ),
                )
            return metadata

        with mock.patch.object(
            bump_plugin_version.os, "lstat", side_effect=marked_reparse
        ):
            with self.assertRaises(bump_plugin_version.VersionError):
                bump_plugin_version.update_plugin_version(
                    self.root,
                    change="feature",
                    expected_version="0.1.0+codex.old",
                    cachebuster="fixed",
                )
        self.assertEqual(self.manifest.read_bytes(), original)

        # Failure after replace is explicit: the new version may already exist.
        with mock.patch.object(
            bump_plugin_version, "fsync_directory", side_effect=OSError("fsync failed")
        ):
            with self.assertRaises(bump_plugin_version.DurabilityError):
                bump_plugin_version.update_plugin_version(
                    self.root,
                    change="feature",
                    expected_version="0.1.0+codex.old",
                    cachebuster="fixed",
                )
        self.assertEqual(self.read_manifest()["version"], "0.2.0+codex.fixed")
        self.assertFalse(lock.exists())
        self.assertEqual(list(self.manifest.parent.glob(".plugin.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
