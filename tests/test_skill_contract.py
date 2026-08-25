from __future__ import annotations

from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "lean-stack"
REFERENCES = SKILL_DIR / "references"


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
        cls.routing = (REFERENCES / "execution-routing.md").read_text(
            encoding="utf-8"
        ).lower()
        cls.flowcharts = (REFERENCES / "flowcharts-zh.md").read_text(
            encoding="utf-8"
        ).lower()
        cls.delegation = (REFERENCES / "delegation.md").read_text(
            encoding="utf-8"
        ).lower()
        cls.long_running = (REFERENCES / "long-running.md").read_text(
            encoding="utf-8"
        ).lower()
        cls.memory = (REFERENCES / "specialist-memory.md").read_text(
            encoding="utf-8"
        ).lower()
        cls.build = (REFERENCES / "build.md").read_text(encoding="utf-8").lower()
        cls.bug_fix = (REFERENCES / "bug-fix.md").read_text(
            encoding="utf-8"
        ).lower()
        cls.investigation = (REFERENCES / "investigation.md").read_text(
            encoding="utf-8"
        ).lower()
        cls.openai_yaml = (SKILL_DIR / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        ).lower()
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        cls.manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

    def test_value_sensitive_priority_replaces_one_fixed_order(self) -> None:
        for content in (self.skill, self.routing, self.readme, self.flowcharts):
            self.assertIn("高价值工作", content)
            self.assertIn("普通工作", content)
        for content in (self.skill, self.readme, self.flowcharts):
            self.assertIn("质量优先", content)
            self.assertIn("速度优先", content)
        self.assertIn("高价值工作：质量优先", self.routing)
        self.assertIn("普通工作：速度优先", self.routing)
        self.assertIn("三项原则不是所有工作的固定排序", self.skill)
        self.assertIn("共同底线", self.readme)
        self.assertNotIn("delegate only when all three are true", self.skill)

    def test_every_new_direction_rechecks_delegation(self) -> None:
        for content in (self.skill, self.delegation, self.routing, self.readme):
            self.assertIn("每条新", content)
            self.assertIn("队列新增", content)
            self.assertIn("阶段", content)
        self.assertIn("不把零个子代理宣布为整轮固定结论", self.delegation)
        self.assertIn("没有完成具体候选", self.skill)

    def test_deterministic_tools_are_considered_before_model_agents(self) -> None:
        for content in (self.skill, self.routing, self.readme):
            self.assertIn("工具", content)
            self.assertIn("短命令", content)
            self.assertIn("后台", content)
        self.assertIn("持续模型语义判断", self.skill)
        self.assertIn("持续模型判断", self.routing + self.readme)
        self.assertIn("十五秒", self.skill)
        self.assertIn("一次工具调用中并发", self.routing)
        self.assertIn("不启动模型子代理", self.skill)

    def test_zero_through_three_are_equal_options_without_default(self) -> None:
        for content in (self.skill, self.delegation, self.long_running, self.readme):
            self.assertRegex(content, r"`?0`?.{0,8}`?1`?.{0,8}`?2`?.{0,8}`?3`?")
        self.assertIn("不默认派一个", self.skill)
        self.assertIn("不能为了显得并行而凑数", self.flowcharts)
        self.assertNotIn("one or two", self.skill)
        self.assertNotIn("1–2", self.skill)

    def test_spawn_requires_real_ready_work_and_parent_keeps_working(self) -> None:
        for content in (self.skill, self.delegation, self.flowcharts):
            self.assertIn("已就绪", content)
            self.assertIn("真实", content)
        self.assertIn("已经就绪", self.routing)
        self.assertIn("真实", self.routing)
        self.assertIn("禁止提前启动后空等", self.skill)
        self.assertIn("父任务立即推进", self.skill)
        self.assertIn("真实依赖点", self.delegation)
        self.assertIn("一个写入者", self.delegation)
        self.assertIn("互不重叠", self.skill)

    def test_context_and_cost_are_complete_route_properties(self) -> None:
        for cost in ("启动", "上下文", "汇合", "验证", "重试", "返工"):
            self.assertIn(cost, self.skill + self.routing)
        self.assertIn("最小上下文", self.skill)
        self.assertIn("不复制完整会话历史", self.skill)
        self.assertIn("不要按模型调用次数比较成本", self.skill)
        self.assertIn("父任务掌握完整上下文不是禁止委派的理由", self.routing)
        self.assertIn("不得声称已经实测省时或省钱", self.skill)

    def test_copies_and_single_axis_variants_keep_one_winner(self) -> None:
        for content in (self.skill, self.delegation, self.readme, self.flowcharts):
            self.assertIn("复制", content)
            self.assertIn("胜出", content)
        for content in (self.skill, self.delegation, self.readme, self.flowcharts):
            self.assertIn("单轴", content)
        self.assertIn("只改变一个轴", self.delegation)
        self.assertIn("最多只持久保留一个", self.skill)
        self.assertIn("每类角色只保留一个", self.memory)
        self.assertIn("reconfiguration_required", self.memory)
        self.assertIn("luna → terra → sol", self.delegation)
        self.assertIn("模型、推理强度和速度档位是三个不同轴", self.skill)

    def test_chinese_output_contract_keeps_identifiers_separate(self) -> None:
        self.assertIn("中文正文不要夹入英文术语", self.skill)
        for term in (
            "任务说明",
            "通用执行子代理",
            "代码探索子代理",
            "运行环境",
            "汇合点",
            "验证子代理",
        ):
            self.assertIn(term, self.skill)
        for identifier in ("worker", "explorer", "source_coverage"):
            self.assertIn(identifier, self.skill + self.flowcharts)
        self.assertNotIn("worker / explorer", self.readme)
        self.assertNotIn("专门 brief", self.readme)

    def test_simple_outcomes_replace_numeric_scoring(self) -> None:
        for result in ("`good`", "`bad`", "`severe_bad`"):
            self.assertIn(result, self.skill)
        self.assertIn("用户明确否定", self.skill)
        for removed in (
            "reputation_score",
            "penalty_points",
            "major_failure_count",
            "recommend-route",
            "lease-acquire",
        ):
            self.assertNotIn(removed, self.skill)

    def test_auxiliary_memory_is_progressively_disclosed_and_nonblocking(self) -> None:
        self.assertLessEqual(len(self.skill.splitlines()), 220)
        self.assertIn("普通分派不运行持久化或数据库操作", self.skill)
        self.assertIn("主结果一旦满足", self.skill)
        for flag in ("--owner-token", "--covered-through", "--source-digest"):
            self.assertNotIn(flag, self.skill)
            self.assertIn(flag, self.memory)
        self.assertIn("只追加", self.memory)
        self.assertIn("永不删除或截断原始事件", self.memory)
        self.assertIn("终止条件满足后不得再启动或等待维护", self.memory)

    def test_reusable_role_can_auto_authorize_non_destructive_memory(self) -> None:
        for content in (self.skill, self.memory, self.flowcharts, self.readme):
            self.assertIn("自动授权", content)
            self.assertIn("值得未来复用", content)
        self.assertIn("非破坏性创建", self.skill)
        self.assertIn("自动授权不覆盖永久删除", self.memory)
        self.assertIn("自动获得非破坏性", self.flowcharts)
        self.assertIn("自动授权并只追加", self.flowcharts)
        self.assertIn("用户已明确否决持久化吗", self.flowcharts)
        self.assertGreaterEqual(self.flowcharts.count("用户已明确否决持久化吗"), 2)

    def test_severe_bad_never_substitutes_for_delete_authorization(self) -> None:
        self.assertRegex(self.skill, r"严重失败本身\s*不是永久删除授权")
        self.assertIn("不能替代删除授权", self.memory)
        self.assertIn("用户当前明确要求", self.flowcharts)
        self.assertIn("但不删除", self.flowcharts)
        self.assertNotIn("用户明确要求或结果属于严重失败", self.flowcharts)

    def test_validation_waits_for_semantic_review_and_code_freeze(self) -> None:
        for content in (self.skill, self.routing, self.readme, self.flowcharts):
            self.assertIn("语义审查", content)
            self.assertIn("冻结", content)
            self.assertIn("最终验证", content)
        self.assertIn("父任务直接调用工具", self.skill)
        self.assertIn("简短输出", self.skill)
        self.assertIn("不得让子代理只运行命令并回报退出状态", self.skill)
        self.assertIn("只重跑可能受影响的检查", self.skill)
        self.assertIn("复用已经通过的证据", self.skill)

    def test_playbooks_follow_value_and_tool_routing(self) -> None:
        self.assertIn("先按工作价值分流", self.build)
        self.assertIn("短命令和确定性工具工作", self.build)
        self.assertIn("迭代测试由父任务直接运行", self.bug_fix)
        self.assertIn("不让多个子代理同时猜修法", self.bug_fix)
        self.assertIn("短查询由父任务直接调用工具", self.investigation)
        self.assertIn("父任务不做常规完整重读", self.investigation)
        self.assertIn("子代理不能提前启动后等待", self.long_running)

    def test_only_three_small_auxiliary_commands_remain(self) -> None:
        script_path = SKILL_DIR / "scripts" / "agents.py"
        spec = importlib.util.spec_from_file_location("contract_agents", script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parser = module.build_parser()
        subparsers_action = next(
            action for action in parser._actions if action.dest == "command"
        )
        self.assertEqual(set(subparsers_action.choices), {"ensure", "improve", "delete"})
        self.assertFalse((SKILL_DIR / "scripts" / "manage_agents.py").exists())
        self.assertFalse((ROOT / "tests" / "test_manage_agents.py").exists())

    def test_manifest_and_ui_are_chinese_and_synchronized(self) -> None:
        self.assertRegex(
            self.manifest["version"],
            r"^1\.\d+\.\d+\+codex\.[a-z0-9.-]+$",
        )
        combined = " ".join(
            [
                self.manifest["description"],
                self.manifest["interface"]["displayName"],
                self.manifest["interface"]["shortDescription"],
                self.manifest["interface"]["longDescription"],
                *self.manifest["interface"]["defaultPrompt"],
            ]
        ).lower()
        for term in ("高价值", "普通工作", "质量", "速度", "零至三个", "最终验证"):
            self.assertIn(term, combined)
        match = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"', self.openai_yaml, re.MULTILINE
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(
            match.group(1), self.manifest["interface"]["defaultPrompt"][0].lower()
        )

    def test_all_fourteen_plain_chinese_flowcharts_exist(self) -> None:
        headings = (
            "总任务主链路",
            "工具与子代理选择链路",
            "子代理数量选择链路",
            "父任务与子代理并行链路",
            "同类复制与单轴变体链路",
            "调查与实现链路",
            "迭代测试链路",
            "语义审查、代码冻结和最终验证链路",
            "失败后的最窄重验链路",
            "专门代理创建与安全重配链路",
            "经验追加与摘要压缩链路",
            "数据库结构拒绝链路",
            "永久删除链路",
            "版本提升、单次重装和新任务加载链路",
        )
        self.assertEqual(self.flowcharts.count("```mermaid"), len(headings))
        for heading in headings:
            self.assertIn(heading, self.flowcharts)
        self.assertIn("全部十四张链路图", self.readme)

    def test_current_gpt56_credit_ratio_is_calculated_not_assumed(self) -> None:
        luna = (Decimal("5"), Decimal("0.5"), Decimal("30"))
        terra = (Decimal("50"), Decimal("5"), Decimal("300"))
        sol = (Decimal("100"), Decimal("10"), Decimal("500"))
        luna_fast = tuple(
            value * Decimal("2.5")
            for value in luna
        )
        ratios = tuple(left / right for left, right in zip(sol, luna_fast))
        self.assertEqual(ratios[0], Decimal("8"))
        self.assertEqual(ratios[1], Decimal("8"))
        self.assertEqual(ratios[2].quantize(Decimal("0.01")), Decimal("6.67"))
        self.assertEqual(tuple(right / left for left, right in zip(luna, terra)), (Decimal("10"),) * 3)
        terra_to_sol = tuple(right / left for left, right in zip(terra, sol))
        self.assertEqual(terra_to_sol[:2], (Decimal("2"), Decimal("2")))
        self.assertEqual(terra_to_sol[2].quantize(Decimal("0.01")), Decimal("1.67"))
        self.assertEqual(
            tuple(value * Decimal("2.5") for value in terra),
            (Decimal("125"), Decimal("12.5"), Decimal("750")),
        )
        for value in ("12.5", "1.25", "75", "6.67", "任务次数兑换率"):
            self.assertIn(value, self.routing)
        self.assertIn("help.openai.com/en/articles/11481834", self.routing)
        self.assertIn("learn.chatgpt.com/docs/agent-configuration/speed", self.routing)
        self.assertIn("当前与未来模型候选", self.routing)
        self.assertIn("不是模型白名单", self.routing)
        self.assertIn("以后出现更强或更合适的模型", self.routing)
        self.assertIn("模型候选不能锁定在 5.6 系列", self.skill)
        for value in (
            "luna → terra",
            "terra → sol",
            "输入：50 ÷ 5 = 10",
            "none → low → medium → high → xhigh → max",
            "luna 快速速度档",
            "terra 快速速度档",
            "sol 快速速度档",
            "不同时升级模型、推理强度和速度",
        ):
            self.assertIn(value, self.routing)
        self.assertIn("luna → sol` 仅用于静态成本对照，不是允许的升级步骤", self.routing)
        self.assertIn("luna → terra` 或 `terra → sol", self.routing)
        self.assertIn("一个实际可用相邻档位", self.routing)


if __name__ == "__main__":
    unittest.main()
