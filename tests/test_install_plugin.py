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

    def with_marketplace_lookup(self, add_runner):
        def cli(command, **kwargs):
            if command[1:] == ["plugin", "marketplace", "list", "--json"]:
                listing = {"marketplaces": [{"name": "personal", "root": str(self.root)}]}
                return SimpleNamespace(returncode=0, stdout=json.dumps(listing), stderr="")
            if command[1:] == ["plugin", "list", "--marketplace", "personal", "--json"]:
                listing = {"installed": [{
                    "pluginId": "codex-lean-stack@personal", "installed": True, "enabled": True,
                    "version": "2.10.0+codex.test",
                    "source": {"source": "local", "path": str(self.plugin_root)},
                }]}
                return SimpleNamespace(returncode=0, stdout=json.dumps(listing), stderr="")
            return add_runner(command, **kwargs)
        return cli

    def test_default_invocation_line_declares_plugin_without_copying_policy(self) -> None:
        line = install_plugin.DEFAULT_INVOCATION_LINE
        self.assertIn("必须使用已安装的 `codex-lean-stack`", line)
        self.assertIn("两个入口按需读取", line)
        self.assertIn("选配与协作细节由插件维护", line)
        for duplicated_policy in (
            "spawn_agent", "reasoning_effort", "fork_turns", "五行", "task_name"
        ):
            self.assertNotIn(duplicated_policy, line)

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
        with self.agents.open(encoding="utf-8", newline="") as stream:
            text = stream.read()
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
                runner=self.with_marketplace_lookup(successful_runner),
            )

        self.assertEqual(preflight["action"], "agents_default_present")
        self.assertFalse(result["agents"]["modified"])
        self.assertEqual(self.agents.read_bytes(), original)

    def test_expanded_parent_global_invocation_is_not_duplicated(self) -> None:
        self.agents.write_text(
            "所有模型和思考程度的父代理必须使用已安装的 `codex-lean-stack`："
            "每次派发显式提交模型与思考程度。\n",
            encoding="utf-8",
        )

        first = install_plugin.ensure_default_invocation(self.codex_home)
        second = install_plugin.ensure_default_invocation(self.codex_home)

        self.assertFalse(first["modified"])
        self.assertFalse(second["modified"])
        text = self.agents.read_text(encoding="utf-8")
        self.assertNotIn(install_plugin.DEFAULT_INVOCATION_LINE, text)

    def test_expanded_parent_global_invocation_with_emphasis_is_not_duplicated(self) -> None:
        original = (
            "本AGENTS.md 修改前每次都需用户明确同意。\n"
            "所有模型和思考程度的父代理必须都使用已安装的 `codex-lean-stack`："
            "会话开头快速实际读取两个按需入口。\n"
        ).encode("utf-8")
        self.agents.write_bytes(original)

        preflight = install_plugin.preflight_default_invocation(self.codex_home)
        ensured = install_plugin.ensure_default_invocation(self.codex_home)

        self.assertEqual(preflight["action"], "agents_default_present")
        self.assertFalse(ensured["modified"])
        self.assertEqual(self.agents.read_bytes(), original)

    def test_current_detailed_parent_contract_is_not_duplicated_by_install(self) -> None:
        original = (
            "# 用户全局规则\n"
            "所有父代理（无论模型与思考程度）必须使用已安装的 `codex-lean-stack`。"
            "新会话第一条用户可见说明包含两个平行、独立的按需入口。"
            "`lean-simplify` 在非简单主任务中按需读取或复用；"
            "`lean-stack` 在首次准备调用 `spawn_agent` 或以 `followup_task` 启动新子任务前"
            "读取或复用。两者独立触发、互不前置；选配与协作细节由插件维护。\n"
            "# 其他规则\n"
        ).encode("utf-8")
        self.agents.write_bytes(original)

        preflight = install_plugin.preflight_default_invocation(self.codex_home)

        def successful_runner(command, **kwargs):
            return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")

        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            installed = install_plugin.install_plugin(
                self.plugin_root,
                marketplace="personal",
                marketplace_path=self.marketplace,
                codex_home=self.codex_home,
                runner=self.with_marketplace_lookup(successful_runner),
            )
        ensured = install_plugin.ensure_default_invocation(self.codex_home)

        self.assertEqual(preflight["action"], "agents_default_present")
        self.assertFalse(installed["agents"]["modified"])
        self.assertFalse(ensured["modified"])
        self.assertEqual(self.agents.read_bytes(), original)
        self.assertNotIn(install_plugin.DEFAULT_INVOCATION_LINE.encode("utf-8"), original)

    def test_line_starting_with_user_plugin_requirement_is_preserved_after_install(self) -> None:
        original = (
            "必须调用已安装的 `codex-lean-stack` 插件，所有模型和思考程度的父代理均须使用本插件。\r\n"
            "# 用户的其他全局规则\r\n"
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
                runner=self.with_marketplace_lookup(successful_runner),
            )

        self.assertEqual(preflight["action"], "agents_default_present")
        self.assertFalse(result["agents"]["modified"])
        self.assertEqual(self.agents.read_bytes(), original)

    def test_quoted_user_plugin_requirement_still_gets_the_precise_default_line(self) -> None:
        original = (
            "文档引用：必须调用已安装的 `codex-lean-stack` 插件，所有模型均适用。\n"
        ).encode("utf-8")
        self.agents.write_bytes(original)

        preflight = install_plugin.preflight_default_invocation(self.codex_home)
        ensured = install_plugin.ensure_default_invocation(self.codex_home)

        self.assertEqual(preflight["action"], "agents_default_ready")
        self.assertTrue(ensured["modified"])
        self.assertEqual(
            self.agents.read_text(encoding="utf-8").splitlines().count(
                install_plugin.DEFAULT_INVOCATION_LINE
            ),
            1,
        )

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
                runner=self.with_marketplace_lookup(successful_runner),
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
                    runner=self.with_marketplace_lookup(failed_runner),
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
                    runner=self.with_marketplace_lookup(broken_runner),
                )
        self.assertEqual(self.agents.read_bytes(), original)
        # A stable empty anchor is retained; actual reacquisition proves release.
        self.assertTrue((self.codex_home / ".AGENTS.md.lean-stack.lock").is_file())
        with install_plugin.update_lock(self.agents):
            pass

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
        # A stable empty anchor is retained; actual reacquisition proves release.
        self.assertTrue((self.codex_home / ".AGENTS.md.lean-stack.lock").is_file())
        with install_plugin.update_lock(self.agents):
            pass

    def test_link_metadata_is_rejected_before_reading_agents(self) -> None:
        self.agents.write_text("不要读取\n", encoding="utf-8")
        real_lstat = install_plugin.os.lstat

        def link_for_agents(path: Path):
            if Path(path) == self.agents:
                return SimpleNamespace(
                    st_mode=install_plugin.stat.S_IFLNK,
                    st_file_attributes=0,
                )
            return real_lstat(path)

        with mock.patch.object(install_plugin.os, "lstat", side_effect=link_for_agents):
            with self.assertRaisesRegex(
                install_plugin.InstallError, "link or reparse point"
            ):
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

    def test_different_same_named_cli_marketplace_prevents_install(self) -> None:
        wrong = {"marketplaces": [{"name": "personal", "root": str(self.root / "elsewhere")}]}
        runner = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(wrong)))
        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(install_plugin.InstallError, "different marketplace"):
                install_plugin.install_plugin(
                    self.plugin_root, marketplace_path=self.marketplace,
                    codex_home=self.codex_home, runner=runner,
                )
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[0][1:], ["plugin", "marketplace", "list", "--json"])
        self.assertFalse(self.agents.exists())

    def test_instruction_growth_limit_is_checked_before_cli(self) -> None:
        original = b"x" * (install_plugin.MAX_AGENTS_BYTES - 1)
        self.agents.write_bytes(original)
        runner = mock.Mock()
        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(install_plugin.InstallError, "updated.*exceeds"):
                install_plugin.install_plugin(
                    self.plugin_root, marketplace_path=self.marketplace,
                    codex_home=self.codex_home, runner=runner,
                )
        runner.assert_not_called()
        self.assertEqual(self.agents.read_bytes(), original)

    def test_literal_html_examples_do_not_hide_a_later_active_instruction(self) -> None:
        line = install_plugin.DEFAULT_INVOCATION_LINE
        examples = [
            f"```html\n<!--\n```\n{line}\n",
            f"See `<!--` and ``x`<!--``.\n{line}\n",
            f"<!-- example\n```\n-->\n{line}\n",
        ]
        for source in examples:
            with self.subTest(source=source):
                original = source.encode("utf-8")
                self.agents.write_bytes(original)
                self.assertFalse(install_plugin.ensure_default_invocation(self.codex_home)["modified"])
                self.assertEqual(self.agents.read_bytes(), original)

    def test_concurrent_first_creation_preserves_the_other_writers_bytes(self) -> None:
        operation = "rename" if install_plugin.os.name == "nt" else "link"
        publish = getattr(install_plugin.os, operation)
        def create_before_publish(temporary, destination):
            destination.write_bytes(b"concurrent user creation")
            publish(temporary, destination)
        with mock.patch.object(install_plugin.os, operation, side_effect=create_before_publish):
            with self.assertRaisesRegex(install_plugin.InstallError, "created after"):
                install_plugin.ensure_default_invocation(self.codex_home)
        self.assertEqual(self.agents.read_bytes(), b"concurrent user creation")

    def test_failed_replace_and_cleanup_report_both_causes(self):
        self.agents.write_bytes(b"original")
        with mock.patch.object(install_plugin.os, "replace", side_effect=OSError("replace failed")), \
             mock.patch.object(Path, "unlink", side_effect=PermissionError("staging locked")):
            with self.assertRaisesRegex(install_plugin.InstallError, "replace failed.*staging locked"):
                install_plugin.ensure_default_invocation(self.codex_home)
        self.assertEqual(self.agents.read_bytes(), b"original")

    def test_marketplace_edit_during_add_blocks_activation_even_with_matching_receipt(self):
        self.agents.write_bytes(b"untouched")
        def redirect(command, **kwargs):
            market = json.loads(self.marketplace.read_text(encoding="utf-8"))
            market["plugins"][0]["source"]["path"] = "./another-plugin"
            self.marketplace.write_text(json.dumps(market), encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
            with self.assertRaisesRegex(install_plugin.InstallError, "add succeeded.*does not match"):
                install_plugin.install_plugin(
                    self.plugin_root, marketplace_path=self.marketplace, codex_home=self.codex_home,
                    runner=self.with_marketplace_lookup(redirect),
                )
        self.assertEqual(self.agents.read_bytes(), b"untouched")

    def test_unconfirmed_installed_version_source_or_enablement_preserves_instructions(self):
        self.agents.write_bytes(b"untouched")
        for difference in ({"version": "1.0.0"}, {"source": {"source": "local", "path": str(self.root)}},
                           {"enabled": False}, {"pluginId": "other@personal"}):
            with self.subTest(difference=difference):
                def runner(command, **kwargs):
                    if command[1:3] == ["plugin", "list"]:
                        entry = {"pluginId": "codex-lean-stack@personal", "installed": True,
                                 "enabled": True, "version": "2.10.0+codex.test",
                                 "source": {"source": "local", "path": str(self.plugin_root)}, **difference}
                        return SimpleNamespace(returncode=0, stdout=json.dumps({"installed": [entry]}))
                    return self.with_marketplace_lookup(
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="{}", stderr="")
                    )(command, **kwargs)
                with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
                    with self.assertRaisesRegex(install_plugin.InstallError, "add succeeded"):
                        install_plugin.install_plugin(
                            self.plugin_root, marketplace_path=self.marketplace, codex_home=self.codex_home,
                            runner=runner,
                        )
                self.assertEqual(self.agents.read_bytes(), b"untouched")

    def test_same_path_edit_during_add_is_preserved_and_partial_install_reported(self) -> None:
        for initial in ("Initial", install_plugin.DEFAULT_INVOCATION_LINE):
            with self.subTest(initial=initial):
                self.agents.write_text(initial, encoding="utf-8")
                def edit_during_add(command, **kwargs):
                    self.agents.write_bytes(b"external replacement")
                    return SimpleNamespace(returncode=0, stdout="{}", stderr="")
                with mock.patch.object(install_plugin.shutil, "which", return_value="codex.exe"):
                    with self.assertRaisesRegex(install_plugin.InstallError, "add succeeded.*changed"):
                        install_plugin.install_plugin(
                            self.plugin_root, marketplace_path=self.marketplace,
                            codex_home=self.codex_home,
                            runner=self.with_marketplace_lookup(edit_during_add),
                        )
                self.assertEqual(self.agents.read_bytes(), b"external replacement")


if __name__ == "__main__":
    unittest.main()
