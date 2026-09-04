from __future__ import annotations

import codecs
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "lean-stack"
    / "scripts"
    / "install_plugin.py"
)
SPEC = importlib.util.spec_from_file_location("lean_stack_install_plugin", SCRIPT)
assert SPEC and SPEC.loader
install_plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install_plugin)


class PluginInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.plugin_root = self.root / "plugins" / "codex-lean-stack"
        self.manifest = self.plugin_root / ".codex-plugin" / "plugin.json"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(
            json.dumps(
                {
                    "name": "codex-lean-stack",
                    "version": "2.10.0+codex.test",
                    "skills": "./skills/",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.codex_home = self.root / "codex-home"
        self.codex_home.mkdir()
        self.agents = self.codex_home / "AGENTS.md"
        self.marketplace = self.root / ".agents" / "plugins" / "marketplace.json"
        self.marketplace.parent.mkdir(parents=True)
        self.marketplace.write_text(
            json.dumps(
                {
                    "name": "personal",
                    "plugins": [
                        {
                            "name": "codex-lean-stack",
                            "source": {
                                "source": "local",
                                "path": "./plugins/codex-lean-stack",
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_default_line_is_added_once_and_preserves_crlf_and_bom(self) -> None:
        original = codecs.BOM_UTF8 + "保留第一行\r\n\r\n# 其他规则\r\n".encode("utf-8")
        self.agents.write_bytes(original)

        first = install_plugin.ensure_default_invocation(self.codex_home)
        once = self.agents.read_bytes()
        second = install_plugin.ensure_default_invocation(self.codex_home)

        self.assertTrue(first["modified"])
        self.assertFalse(second["modified"])
        self.assertEqual(self.agents.read_bytes(), once)
        self.assertTrue(once.startswith(codecs.BOM_UTF8))
        text = once[len(codecs.BOM_UTF8) :].decode("utf-8")
        self.assertEqual(text.count(install_plugin.DEFAULT_INVOCATION_LINE), 1)
        self.assertTrue(text.startswith("保留第一行\r\n" + install_plugin.DEFAULT_INVOCATION_LINE))
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_first_existing_newline_style_is_used_without_normalizing_the_rest(self) -> None:
        original = "第一行\n第二行\r\n第三行\r第四行"
        self.agents.write_text(original, encoding="utf-8", newline="")
        install_plugin.ensure_default_invocation(self.codex_home)
        text = self.agents.read_text(encoding="utf-8", newline="")
        self.assertTrue(
            text.startswith("第一行\n" + install_plugin.DEFAULT_INVOCATION_LINE + "\n")
        )
        self.assertIn("第二行\r\n第三行\r第四行", text)

    def test_existing_user_global_invocation_is_not_duplicated(self) -> None:
        original = (
            install_plugin.USER_GLOBAL_INVOCATION_LINE + "\n# 用户的其他全局规则\n"
        ).encode("utf-8")
        self.agents.write_bytes(original)

        preflight = install_plugin.preflight_default_invocation(self.codex_home)

        def successful_runner(command, **kwargs):
            return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")

        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            result = install_plugin.install_plugin(
                self.plugin_root,
                marketplace="personal",
                marketplace_path=self.marketplace,
                codex_home=self.codex_home,
                runner=successful_runner,
            )

        self.assertEqual(preflight["action"], "agents_default_present")
        self.assertFalse(result["agents"]["modified"])
        self.assertEqual(self.agents.read_bytes(), original)

    def test_successful_install_adds_line_after_codex_returns_zero(self) -> None:
        self.agents.write_text("保护现有内容。\n", encoding="utf-8")
        calls: list[list[str]] = []

        def successful_runner(command, **kwargs):
            calls.append(command)
            self.assertEqual(kwargs["encoding"], "utf-8")
            self.assertTrue(
                (self.codex_home / ".AGENTS.md.lean-stack.lock").exists()
            )
            return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")

        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            result = install_plugin.install_plugin(
                self.plugin_root,
                marketplace="personal",
                marketplace_path=self.marketplace,
                codex_home=self.codex_home,
                runner=successful_runner,
            )

        self.assertEqual(
            calls,
            [["codex.exe", "plugin", "add", "codex-lean-stack@personal", "--json"]],
        )
        self.assertEqual(result["action"], "plugin_installed_with_default_invocation")
        self.assertIn(
            install_plugin.DEFAULT_INVOCATION_LINE,
            self.agents.read_text(encoding="utf-8"),
        )

    def test_failed_install_does_not_touch_agents(self) -> None:
        original = b"preserve me\n"
        self.agents.write_bytes(original)

        def failed_runner(command, **kwargs):
            return SimpleNamespace(returncode=9, stdout="", stderr="install failed")

        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(install_plugin.InstallError, "exit code 9"):
                install_plugin.install_plugin(
                    self.plugin_root,
                    marketplace_path=self.marketplace,
                    codex_home=self.codex_home,
                    runner=failed_runner,
                )
        self.assertEqual(self.agents.read_bytes(), original)

    def test_runner_oserror_does_not_touch_agents(self) -> None:
        original = b"preserve me\n"
        self.agents.write_bytes(original)

        def broken_runner(command, **kwargs):
            raise OSError("cannot start Codex CLI")

        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(OSError, "cannot start Codex CLI"):
                install_plugin.install_plugin(
                    self.plugin_root,
                    marketplace_path=self.marketplace,
                    codex_home=self.codex_home,
                    runner=broken_runner,
                )
        self.assertEqual(self.agents.read_bytes(), original)
        self.assertFalse(
            (self.codex_home / ".AGENTS.md.lean-stack.lock").exists()
        )

    def test_invalid_agents_or_plugin_identity_fails_closed(self) -> None:
        self.agents.write_bytes(b"\xff")
        with self.assertRaisesRegex(install_plugin.InstallError, "not valid UTF-8"):
            install_plugin.ensure_default_invocation(self.codex_home)

        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["name"] = "another-plugin"
        self.manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(install_plugin.InstallError, "only accepts plugin"):
            install_plugin.read_manifest(self.plugin_root)

    def test_agents_preflight_failure_prevents_plugin_install(self) -> None:
        self.agents.write_bytes(b"\xff")
        calls = 0

        def unexpected_runner(command, **kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(install_plugin.InstallError, "not valid UTF-8"):
                install_plugin.install_plugin(
                    self.plugin_root,
                    marketplace_path=self.marketplace,
                    codex_home=self.codex_home,
                    runner=unexpected_runner,
                )
        self.assertEqual(calls, 0)

    def test_lock_conflict_fails_closed_without_changing_agents(self) -> None:
        original = b"preserve\n"
        self.agents.write_bytes(original)
        lock = self.codex_home / ".AGENTS.md.lean-stack.lock"
        lock.write_text("busy\n", encoding="ascii")
        with self.assertRaisesRegex(install_plugin.InstallError, "lock already exists"):
            install_plugin.preflight_default_invocation(self.codex_home)
        self.assertEqual(self.agents.read_bytes(), original)

    def test_install_lock_conflict_prevents_plugin_install(self) -> None:
        original = b"preserve\n"
        self.agents.write_bytes(original)
        lock = self.codex_home / ".AGENTS.md.lean-stack.lock"
        lock.write_text("busy\n", encoding="ascii")
        calls = 0

        def unexpected_runner(command, **kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(install_plugin.InstallError, "lock already exists"):
                install_plugin.install_plugin(
                    self.plugin_root,
                    marketplace_path=self.marketplace,
                    codex_home=self.codex_home,
                    runner=unexpected_runner,
                )
        self.assertEqual(calls, 0)
        self.assertEqual(self.agents.read_bytes(), original)

    def test_atomic_replace_failure_preserves_original_and_cleans_temporary(self) -> None:
        original = b"preserve\n"
        self.agents.write_bytes(original)
        with mock.patch.object(
            install_plugin.os, "replace", side_effect=OSError("replace failed")
        ):
            with self.assertRaisesRegex(OSError, "replace failed"):
                install_plugin.ensure_default_invocation(self.codex_home)

        self.assertEqual(self.agents.read_bytes(), original)
        self.assertEqual(
            list(self.codex_home.glob(".AGENTS.md.*.tmp")),
            [],
        )
        self.assertFalse(
            (self.codex_home / ".AGENTS.md.lean-stack.lock").exists()
        )

    def test_dangling_symlink_is_rejected_when_supported(self) -> None:
        target = self.codex_home / "missing-target"
        try:
            self.agents.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        with self.assertRaisesRegex(install_plugin.InstallError, "link or reparse point"):
            install_plugin.ensure_default_invocation(self.codex_home)

    def test_marketplace_must_point_to_this_source_root(self) -> None:
        payload = json.loads(self.marketplace.read_text(encoding="utf-8"))
        payload["plugins"][0]["source"]["path"] = "./plugins/a-different-copy"
        self.marketplace.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(install_plugin.InstallError, "does not match plugin root"):
            install_plugin.verify_marketplace_source(
                self.marketplace,
                marketplace="personal",
                plugin_root=self.plugin_root,
            )


if __name__ == "__main__":
    unittest.main()
