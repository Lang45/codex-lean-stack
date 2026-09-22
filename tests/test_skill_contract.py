from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "lean-stack"
SIMPLIFY_SKILL_DIR = ROOT / "skills" / "lean-simplify"
REFERENCES = SKILL_DIR / "references"


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        cls.simplify_skill = (SIMPLIFY_SKILL_DIR / "SKILL.md").read_text(
            encoding="utf-8"
        )
        cls.routing_index = (REFERENCES / "execution-routing.md").read_text(
            encoding="utf-8"
        )
        cls.delegation_index = (REFERENCES / "delegation.md").read_text(
            encoding="utf-8"
        )
        cls.dispatch_start = (REFERENCES / "dispatch-start.md").read_text(
            encoding="utf-8"
        )
        cls.source_results = (REFERENCES / "source-results.md").read_text(
            encoding="utf-8"
        )
        cls.agent_groups = (REFERENCES / "agent-groups.md").read_text(
            encoding="utf-8"
        )
        cls.agent_results = (REFERENCES / "agent-results.md").read_text(
            encoding="utf-8"
        )
        cls.windows_exec = (REFERENCES / "windows-exec.md").read_text(
            encoding="utf-8"
        )
        cls.verification = (REFERENCES / "verification.md").read_text(
            encoding="utf-8"
        )
        cls.routing = "\n".join(
            (
                cls.routing_index,
                cls.dispatch_start,
                cls.source_results,
                cls.agent_results,
                cls.windows_exec,
                cls.verification,
            )
        )
        cls.delegation = "\n".join(
            (
                cls.delegation_index,
                cls.agent_groups,
                cls.agent_results,
                cls.dispatch_start,
                cls.source_results,
            )
        )
        cls.collaboration = (REFERENCES / "collaboration.md").read_text(
            encoding="utf-8"
        )
        cls.memory = (REFERENCES / "specialist-memory.md").read_text(encoding="utf-8")
        cls.anti_overengineering = (REFERENCES / "anti-overengineering.md").read_text(
            encoding="utf-8"
        )
        cls.ablation = (REFERENCES / "ablation-loop.md").read_text(encoding="utf-8")
        cls.write_parallelism = (REFERENCES / "write-parallelism.md").read_text(
            encoding="utf-8"
        )
        cls.cost = (REFERENCES / "cost-baseline.md").read_text(encoding="utf-8")
        cls.cost_check = (SKILL_DIR / "scripts" / "cost_check.py").read_text(
            encoding="utf-8"
        )
        cls.installer = (SKILL_DIR / "scripts" / "install_plugin.py").read_text(
            encoding="utf-8"
        )
        cls.agents_source = (SKILL_DIR / "scripts" / "agents.py").read_text(
            encoding="utf-8"
        )
        cls.flowcharts = (REFERENCES / "flowcharts-zh.md").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.build = (REFERENCES / "build.md").read_text(encoding="utf-8")
        cls.bug_fix = (REFERENCES / "bug-fix.md").read_text(encoding="utf-8")
        cls.investigation = (REFERENCES / "investigation.md").read_text(encoding="utf-8")
        cls.review = (REFERENCES / "review.md").read_text(encoding="utf-8")
        cls.long_running = (REFERENCES / "long-running.md").read_text(encoding="utf-8")
        cls.versioning = (REFERENCES / "versioning.md").read_text(encoding="utf-8")
        cls.routing = "\n".join(
            (
                cls.skill,
                cls.routing_index,
                cls.dispatch_start,
                cls.source_results,
                cls.agent_results,
                cls.windows_exec,
                cls.verification,
                cls.write_parallelism,
                cls.versioning,
            )
        )
        cls.delegation = "\n".join(
            (
                cls.skill,
                cls.delegation_index,
                cls.dispatch_start,
                cls.agent_groups,
                cls.source_results,
                cls.agent_results,
                cls.write_parallelism,
                cls.memory,
            )
        )
        cls.openai_yaml = (SKILL_DIR / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        cls.simplify_openai_yaml = (
            SIMPLIFY_SKILL_DIR / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        cls.manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        cls.calling_authority = "\n".join(
            (
                cls.skill,
                cls.routing,
                cls.delegation,
                cls.collaboration,
                cls.memory,
                cls.write_parallelism,
                cls.cost,
                cls.flowcharts,
            )
        )
        cls.simplify_authority = "\n".join(
            (
                cls.simplify_skill,
                cls.routing,
                cls.windows_exec,
                cls.verification,
                cls.anti_overengineering,
                cls.ablation,
                cls.build,
                cls.bug_fix,
                cls.investigation,
                cls.review,
                cls.long_running,
                cls.versioning,
                cls.flowcharts,
            )
        )
        cls.chinese_docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "CHANGELOG.md",
                SKILL_DIR / "SKILL.md",
                SIMPLIFY_SKILL_DIR / "SKILL.md",
                *REFERENCES.glob("*.md"),
            )
        )

    def test_entry_and_verification_nodes_are_distinct_in_main_flow(self) -> None:
        main = self.flowcharts.split("```mermaid", 1)[1].split("```", 1)[0]
        labels = (
            r"(\w+)\[收到新消息、继续指令",
            r"(\w+)\[修复真实发现并运行必要验证",
            r"(\w+)\{必要验证通过吗",
        )
        nodes = []
        for label in labels:
            match = re.search(label, main)
            self.assertIsNotNone(match, label)
            nodes.append(match.group(1))
        self.assertEqual(len(nodes), len(set(nodes)), "entry and validation nodes must not merge")

    def test_quality_cost_time_priority_and_safety_remain(self) -> None:
        for content in (self.skill, self.routing, self.flowcharts):
            for principle in ("质量", "成本", "时间"):
                self.assertIn(principle, content)
        for readme_term in ("模型与思考程度", "成本相称", "实际加快父任务完成"):
            self.assertIn(readme_term, self.readme)
        for floor in ("安全", "权限", "数据完整性", "诚实证据"):
            self.assertIn(floor, self.skill + self.readme)
        for principle in ("1. **质量。**", "2. **成本。**", "3. **时间。**"):
            self.assertIn(principle, self.skill)
        self.assertNotIn("普通工作速度优先", self.skill)

    def test_call_count_is_not_a_cost_error_without_marginal_route_evidence(self) -> None:
        combined = self.skill + self.routing + self.cost + self.readme
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "调用数量本身不是成本结论",
            "多个调用只要分别通过三项原则就可同时成立",
            "模型与思考程度联合达到该切片的必要质量",
            "质量充分的模型与思考程度组合中选择与任务相称的成本",
            "该委派对父任务实际完成速度有正贡献",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)
        for invalid_shortcut in (
            "调用数量多就是成本错误",
            "超过三个子代理就是成本错误",
            "按调用总数判断成本",
            "上下文、交流、整合、验证及返工形成的完整增量成本",
            "上下文、启动、通信、整合、验证或返工汇总为",
        ):
            self.assertNotIn(invalid_shortcut, combined)

    def test_quality_cost_time_order_allows_bounded_cheap_parallelism(self) -> None:
        self.assertIn("质量 → 成本 → 时间", self.skill)
        compact_routing = re.sub(r"\s+", "", self.routing)
        self.assertIn("模型与思考程度联合达到该切片的必要质量", compact_routing)
        self.assertIn("质量充分的模型与思考程度组合中选择与任务相称的成本", compact_routing)
        self.assertIn("该委派对父任务实际完成速度有正贡献", compact_routing)
        self.assertIn("多个调用只要分别通过三项原则就可同时成立", compact_routing)
        self.assertIn(
            "用户要求全文和必要的高风险独立核验仍保留",
            self.dispatch_start,
        )
        main = self.flowcharts.split("```mermaid", 1)[1].split("```", 1)[0]
        decision = re.search(r"BP\{([^}]+)\}", main)
        self.assertIsNotNone(decision)
        self.assertIn("模型与思考程度联合达到必要质量", decision.group(1))
        self.assertIn("实际加快父任务完成", decision.group(1))
        combined = self.skill + self.routing + self.readme + self.flowcharts
        for stale_priority in (
            "普通工作速度优先",
            "质量与总完成时间相当",
            "成本优势不覆盖前两项",
            "二者相当时总成本更低",
        ):
            self.assertNotIn(stale_priority, combined)

    def test_four_model_route_receipt_is_joint_and_task_specific(self) -> None:
        authority = self.dispatch_start.split("## 二、选择运行时或保留子代理", 1)[0]
        compact = re.sub(r"\s+", "", authority)

        for required in (
            "gpt-5.6-luna",
            "规格清楚、证据已定位",
            "gpt-5.6-terra",
            "有限语义歧义",
            "gpt-5.6-sol",
            "跨来源或跨模块因果",
            "gpt-6-astra",
            "当前未决专家问题",
            "会改变决定的额外质量",
            "普通视觉任务",
            "不触发Astra",
            "不要求较低模型实际失败",
            "思考程度按推理深度选择",
            "模型和思考程度联合选择",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)

        for receipt_field in (
            "MODEL_ROUTE",
            "selected:",
            "quality:",
            "cost:",
            "parent_speedup:",
        ):
            self.assertIn(receipt_field, authority)

        self.assertIn("父代理侧", authority)
        self.assertIn("不在固定五行开场前复述", authority)
        for boundary in (
            "Sol `max` 可按任务复杂度和必要质量正常选择",
            "不要求先证明 `xhigh` 不足",
            "普通 UI、视觉和简单审计不得使用 Sol",
            "只有高价值复杂边界可选择",
            "`xhigh` 与 `max` 都无法可靠处理",
            "Astra 子代理仍最高 `xhigh`",
            "唯一称为高成本专家",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact)
        for shared_gate in (
            "`max` / `ultra` 只用于",
            "Sol 选择 `max` / `ultra` 时",
            "Sol max 或 ultra 只有高价值复杂边界",
        ):
            self.assertNotIn(shared_gate, authority)
        self.assertNotIn("评分表", authority)
        self.assertNotIn("先失败", authority)

    def test_new_project_dispatch_contract_requires_entry_and_explicit_native_configuration(
        self,
    ) -> None:
        entry = self.skill
        frontmatter = self.skill.split("---", 2)[1]
        calling_match = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"', self.openai_yaml, re.MULTILINE
        )
        self.assertIsNotNone(calling_match)
        assert calling_match is not None
        calling_prompt = calling_match.group(1)
        compact_entry = re.sub(r"\s+", "", entry).replace("`", "")
        compact_prompt = re.sub(r"\s+", "", calling_prompt).replace("`", "")
        compact_dispatch = re.sub(r"\s+", "", self.dispatch_start).replace("`", "")

        self.assertTrue(
            calling_prompt.startswith("出现具体委派候选"),
            "the public prompt must start with the real delegation trigger",
        )

        self.assertIn(
            "出现具体委派候选、首次准备spawn_agent或用followup_task启动新子任务时读取",
            re.sub(r"\s+", "", frontmatter),
        )

        for required in (
            "安装本插件的项目和新会话保持主动委派",
            "首次准备调用collaboration.spawn_agent",
            "用followup_task启动新当前子任务",
            "只识别技能名称、口头声明、项目交接或猜测路径都不算已读",
            "入口先完成快速判断",
            "同一任务可以随实际动作依次命中多个分支",
            "不能因拆分而跳过后继触发",
            "未通过三项原则时继续主任务",
            "正向委派决定完成后",
            "最多执行一次有界status--for-routing",
            "命中候选后才recall",
            "父代理不得并行重做该范围",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_entry)

        for required in (
            "任何层级和任何agent_type",
            "model",
            "reasoning_effort",
            'fork_turns="none"或有限正整数',
            '禁止fork_turns="all"',
            "与已加载TOML完全一致",
            "五行只由子代理本人在自己的第一条可见commentary原样宣读",
            "父代理只把五行写入内部任务卡",
            "不在自己的用户可见commentary或最终回复中代为展示",
            "followup_task没有选模参数",
            "parent→child→grandchild",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_dispatch)
        self.assertNotIn(
            "并在后续用户可见副本和最终回复中使用更新后的值",
            self.delegation,
        )

        self.assertLessEqual(
            len(calling_prompt),
            520,
            "the pre-read prompt must stay small enough for the startup hot path",
        )
        for required in (
            "本轮首次准备spawn_agent或以followup_task启动新子任务时",
            "先按质量、成本、提速判断并确定切片、模型与思考程度",
            "不通过便继续主任务，不查status/recall",
            "确认派发后读dispatch-start",
            "依次只读命中项",
            "后续动作仍可依次命中多个分支",
            "不批量预读完整references或$lean-simplify",
            "不因拆分跳过后继触发",
            "每次spawn_agent显式传model、reasoning_effort和非全量fork_turns",
            "名称、模型、思考程度、存活轮次、经验五行实际值只写内部任务卡",
            "由子代理本人开场，父代理不代述",
            "父子不重复完整读取同源或执行同一已分配职责",
            "父代理保留整合、共享热点和必要高风险定向核验",
            "$lean-stack不等待或阻断$lean-simplify",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_prompt)

        combined = self.routing + self.delegation + self.collaboration
        compact_combined = re.sub(r"\s+", "", combined).replace("`", "")
        for required in (
            "具名保留子代理",
            "每次collaboration.spawn_agent",
            "model",
            "reasoning_effort",
            "与已加载TOML完全一致",
            "任何层级和任何agent_type",
            '禁止fork_turns="all"',
            "followup_task没有选模参数",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_combined)

        self.assertNotIn("当前会话稳定task_id", compact_entry + compact_prompt)
        self.assertNotIn("同一task_id", compact_combined)

        for content in (entry, calling_prompt, self.routing, self.delegation, self.collaboration):
            compact_content = re.sub(r"\s+", "", content)
            for match in re.finditer(r'fork_turns="all"', compact_content):
                surrounding = compact_content[max(0, match.start() - 35):match.end() + 55]
                self.assertTrue(
                    "禁止" in surrounding or "不得" in surrounding,
                    f"fork_turns=all must only appear as a prohibition: {surrounding}",
                )

        self.assertIn(
            "保留子代理TOML的宿主预配置",
            re.sub(r"\s+", "", self.memory),
        )
        compact_memory = re.sub(r"\s+", "", self.memory).replace("`", "")
        for retained_boundary in (
            "保留子代理 TOML 的宿主预配置",
            "`--speed standard` 不写 `service_tier`",
            "`--speed fast` 写入",
            '`service_tier = "fast"`',
            "创建、安全重配、旧台账迁移、经验刷新和摘要改写中保留并校验",
            "`status --for-routing` 与 `recall` 可以返回实际预配置",
            "模型与思考程度路线不能修改它",
        ):
            self.assertIn(
                re.sub(r"\s+", "", retained_boundary).replace("`", ""),
                compact_memory,
            )
        hot_path = "\n".join(
            (entry, calling_prompt, self.dispatch_start)
        )
        for moved_detail in ("service_tier", "Fast mode", "--speed", "priority"):
            self.assertNotIn(moved_detail, hot_path)
        public_routing_docs = "\n".join(
            (entry, calling_prompt, self.readme, self.cost, self.flowcharts, self.write_parallelism)
        )
        for moved_detail in ("service_tier", "Fast mode", "--speed"):
            self.assertNotIn(moved_detail, public_routing_docs)
        self.assertNotIn("速度：<", hot_path)
        self.assertNotIn("模型、思考程度和速度", hot_path)
        self.assertNotIn("speed intent", hot_path)

    def test_plugin_rule_is_mandatory_and_default_trigger_is_not_used(
        self,
    ) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.readme
            + self.flowcharts
        )
        compact = re.sub(r"\s+", "", combined)
        for term in (
            "安装本插件的项目和新会话保持主动委派",
            "三项原则与一次判断",
            "立即调用",
            "不能反向成为“是否调用”的前置条件",
        ):
            self.assertIn(re.sub(r"\s+", "", term), compact)
        self.assertIn("第二个及以后", combined)
        for removed_default_trigger in (
            "默认启用多代理能力",
            "用户直接要求或适用",
            "技能触发来源",
            "已经构成技能触发",
        ):
            self.assertNotIn(removed_default_trigger, combined)
        self.assertNotIn("没有把握时由父代理完成", combined)
        self.assertNotIn("任一关键答案是否定时不调用", combined)

    def test_active_requirement_anchor_retires_completed_delivered_work(
        self,
    ) -> None:
        authority = self.simplify_skill + self.verification + self.flowcharts + self.readme
        for required in (
            "最早一个尚未完成",
            "已经完成但尚未通过用户可见回复交付",
            "已交付事项",
            "无关历史中的未验证项",
        ):
            self.assertIn(required, authority)
        self.assertIn("不建立共享文件、结果索引或后台状态机", self.source_results)

    def test_delegation_does_not_invent_work_to_prove_the_plugin(self) -> None:
        compact = re.sub(r"\s+", "", self.calling_authority)
        self.assertIn("不为证明插件能委派而制造任务", compact)
        self.assertIn("调用数量随真实工作流和容量变化", compact)
        self.assertIn("没有这些变化时复用原决定", compact)

    def test_parent_gives_a_fast_first_explanation_then_keeps_working(self) -> None:
        compact = re.sub(r"\s+", "", self.simplify_skill + self.routing + self.readme)
        for boundary in (
            "唯一启动说明",
            "读取后的下一次工具调用立即开始实际任务",
            "给出当前理解、立即动作和必要限制",
            "能直接答完的请求由最终答案本身完成",
            "不重复发两份前言",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact)

        self.assertIn("不能阻塞主任务", compact)
        self.assertIn("不能预造用户未要求的交付物", compact)

    def test_optional_preparation_triggers_one_shortest_path_prompt(self) -> None:
        """Keep the decision trigger in the entry and details behind conditional links."""
        section = re.search(
            r"(?ms)^## 可选准备动作触发器\r?\n(.*?)(?=^## |\Z)",
            self.simplify_skill,
        )
        self.assertIsNotNone(section)
        assert section is not None
        contract = section.group(1)
        compact = re.sub(r"\s+", "", contract)

        for required in (
            "已经理解目标",
            "不能直接产生首个可验证主任务结果",
            "不能解除已命名阻断",
            "及时应用本入口一次",
            "当前代码、证据和授权内，哪条最短路径能产生首个可验证结果",
            "随后立即执行第一项实际动作",
            "新会话额外预读或前言",
            "目标与验收未定前的批量编辑",
            "决定性验收通过后的同类复验",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)

        for exclusion in (
            "正在运行的必要工具",
            "唯一权威读取",
            "权限或安全检查",
            "解除已命名阻断的动作",
        ):
            self.assertIn(re.sub(r"\s+", "", exclusion), compact)

        for forbidden_mechanism in (
            "不计时",
            "不创建脚本、Hook、持久状态或新子代理",
            "不得延后 `$lean-stack`",
        ):
            self.assertIn(re.sub(r"\s+", "", forbidden_mechanism), compact)

    def test_main_flow_is_primary_and_locates_every_auxiliary_entry(self) -> None:
        main = self.flowcharts.split("## 一、主任务链路", 1)[1].split(
            "## 二、工具、子代理与安全并行链路", 1
        )[0]
        group_close = main.index("本组当前已就绪结果已核验")
        unique = main.index("竞争并选出", group_close)
        retention = main.index("第一次成功执行首次 ensure", unique)
        experience = main.index("一次 complete-run --lesson", retention)
        removal = main.index("其他子代理移出组、结束", experience)
        completion = main.index("当前活动要求达到", removal)
        self.assertLess(group_close, unique)
        self.assertLess(unique, retention)
        self.assertLess(retention, experience)
        self.assertLess(experience, removal)
        self.assertLess(removal, completion)

        for label in (
            "辅链二",
            "辅链三",
            "辅链四",
            "辅链五",
            "辅链六",
            "辅链七",
            "辅链八",
            "辅链九",
            "辅链十",
            "辅链十一",
            "辅链十二",
            "辅链十三",
        ):
            self.assertIn(label, main)
        self.assertIn("从这里开始", main)
        self.assertIn("虚线只标记其他链路从主任务链的哪个位置开始", main)
        self.assertIn("不能成为另一条取代主任务的主线", main)

    def test_task_type_group_reuse_and_runtime_customization_follow_the_required_order(
        self,
    ) -> None:
        for required in (
            "任务类型组只组织已经决定调用的工作",
            "匹配轻量目录并选择",
            "不把分组、候选或查询失败变成调用门槛",
            "运行时定制不是持久创建",
        ):
            self.assertIn(required, self.agent_groups)
        compact_skill = re.sub(r"\s+", "", self.skill)
        self.assertIn("最多执行一次有界`status--for-routing`", compact_skill)
        self.assertIn("命中候选后才`recall`", compact_skill)
        self.assertIn("不能反向成为“是否调用”的前置条件", compact_skill)

    def test_first_verified_reusable_group_can_persist_without_extending_runtime_threads(
        self,
    ) -> None:
        combined = self.skill + self.routing + self.delegation + self.memory + self.readme
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "第一次成功",
            "不要求此前已经重复",
            "不同任务类型组",
            "多个领域可以同时保留",
            "休眠",
            "进入 Done",
            "不持续调用模型",
            "首次 `ensure`",
            "一次 CAS 确认",
            "父代理同时继续测试",
            "未通过",
            "用户否定",
            "未通过、未采用和被用户否定的子代理不保留",
            "默认",
            "明确排除项",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)

        group_flow = self.flowcharts.split(
            "## 五、任务类型组、复制、变体与保留子代理链路", 1
        )[1].split("## 六、调查、实现与独立精简链路", 1)[0]
        final_reply = group_flow.index("最终回复顶部再次写实际配置")
        persisted = group_flow.index("第一次成功执行首次 ensure", final_reply)
        done = group_flow.index("运行线程结束并进入 Done", persisted)
        self.assertLess(final_reply, persisted)
        self.assertLess(persisted, done)

        for stale_thread_boundary in (
            "重配前已经创建",
            "followup_task",
            "旧线程",
            "新线程",
        ):
            self.assertIn(stale_thread_boundary, combined)

    def test_task_type_and_group_are_fixed_before_subagent_customization(self) -> None:
        self.assertIn("任务类型组只组织已经决定调用的工作", self.agent_groups)
        self.assertIn("完成联合选模，再按", self.agent_groups)
        self.assertIn("确定任务类型、匹配轻量目录并选择", self.agent_groups)
        self.assertNotIn("任务类型组确定前禁止复用或定制子代理", self.calling_authority)
        self.assertNotIn("不得选择具体配置", self.calling_authority)

    def test_tools_are_used_before_model_subagents(self) -> None:
        combined = self.skill + self.routing
        for term in ("工具", "短命令", "后台"):
            self.assertIn(term, combined)
        for readme_term in ("工具先行", "短命令", "模型子代理"):
            self.assertIn(readme_term, self.readme)
        self.assertIn("确定性短工作直接用工具", self.skill)
        self.assertIn("一次工具调用并发运行", self.flowcharts)

    def test_complex_powershell_uses_one_temporary_script_not_escape_retries(
        self,
    ) -> None:
        compact_routing = re.sub(r"\s+", "", self.routing)
        for boundary in (
            "简单、短小",
            "多层引号",
            "嵌套 JSON",
            "正则表达式",
            "反引号",
            "多行脚本",
            "复杂变量插值",
            "任务专属临时 `.ps1`",
            "第一次内联失败",
            "解析或转义问题",
            "停止继续改写长 one-liner",
            "同一个临时脚本本体",
            "`param()`",
            "`-LiteralPath`",
            "不能误判为转义问题",
            "凭据、令牌或秘密",
            "不进入仓库或提交",
            "Windows 回收站",
            "任务专属 `待删文件`",
            "不为这条规则建立 PowerShell 包装框架",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact_routing)

        self.assertIn("PowerShell", self.skill)
        self.assertIn("windows-exec.md", self.skill)
        self.assertIn("复杂 PowerShell 及时落到脚本", self.readme)

        tool_flow = self.flowcharts.split(
            "## 二、工具、子代理与安全并行链路", 1
        )[1].split("## 三、调用容量与成本快判链路", 1)[0]
        first_gate = tool_flow.index("PowerShell 命令需要复杂转义吗")
        script = tool_flow.index("任务专属临时 .ps1", first_gate)
        escape_failure = tool_flow.index("首次解析或转义失败", script)
        same_script = tool_flow.index("后续编辑同一脚本", first_gate)
        self.assertLess(first_gate, script)
        self.assertLess(first_gate, same_script)
        self.assertLess(script, escape_failure)

    def test_windows_exec_robustness_is_plugin_owned_and_shared(self) -> None:
        robustness_block = """<!-- codex-exec-robustness:begin -->
Windows exec 已是 PowerShell 时，简单命令直接执行，不额外套 Shell。
复杂或跨语言代码优先用文件工具落盘，再调用脚本文件，避免层层内联转义。
分离可执行文件、参数和数据，不拼接命令后用 Invoke-Expression 执行。
按各层语法处理引用；路径优先使用变量及 LiteralPath，避免反引号续行。
复杂 PowerShell 脚本执行前做语法预检，执行后检查实际结果与退出码。
转义错误优先减少解析层，不连续盲试引号。
复用已知环境，定向读取；完整日志留本地，回传关键错误，不为省 token 跳过验证。
<!-- codex-exec-robustness:end -->"""
        self.assertIn(robustness_block, self.routing)
        self.assertEqual(self.routing.count("codex-exec-robustness:begin"), 1)
        self.assertEqual(self.routing.count("codex-exec-robustness:end"), 1)
        for entry in (self.skill, self.simplify_skill):
            self.assertIn("Windows exec 稳健性契约", entry)
            self.assertIn("windows-exec.md", entry)
        for required in (
            "Parser.ParseFile",
            "& $exe @argList",
            "Start-Process -ArgumentList",
            "$PSNativeCommandArgumentPassing",
            "param()",
            "-LiteralPath",
            "实际内容、结果和外部程序退出码",
            "完整日志留在本地",
            "定向读取",
            "不连续增加反斜杠、引号、Base64",
        ):
            self.assertIn(required, self.routing)
        self.assertNotIn("AGENTS.md", self.skill + self.simplify_skill)

    def test_sustained_multi_workflow_work_dispatches_all_qualifying_slices_early(self) -> None:
        """Protect qualitative early routing without introducing a mechanical quota."""
        detailed_authority = self.delegation
        compact_authority = re.sub(r"\s+", "", detailed_authority)
        for required in (
            "持续多工作流任务的早期派发",
            "能推进实际研究、调查、实现或验收",
            "尽早派发全部分别通过三项原则且互不冲突的 GPT-5.6 切片",
            "调用数量随真实工作流和容量变化",
            "为提高父任务完成速度",
            "可以同时派发多个子代理",
            "模型与思考程度联合达到该切片的必要质量",
            "选择与任务相称的成本",
            "委派对父任务实际完成速度有正贡献",
            "只在后期增加一次复核不能替代前面的实际工作",
            "立即重新判断受影响的任务形状",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_authority)

        for exception in (
            "属于确定性短工具工作",
            "多个互不依赖",
            "严格依赖",
            "写入冲突无法隔离",
            "委派对父任务完成速度没有正贡献",
        ):
            self.assertIn(re.sub(r"\s+", "", exception), compact_authority)

        for rejected_quota in (
            "同类长任务的早期双派发",
            "至少两个互不依赖",
            "早期至少启动两个",
            "所有任务至少派发两个子代理",
            "无条件强制固定两个",
        ):
            self.assertNotIn(rejected_quota, detailed_authority)

    def test_routing_rechecks_changed_work_and_requires_adoptable_results(self) -> None:
        """Keep re-routing, three-principle selection, and closeout behavior coupled."""
        routing_decision = self.skill.split("## 选配与上下文底线", 1)[0]
        early_dispatch = self.skill.split("### 持续多工作流任务的早期派发", 1)[1].split(
            "## 选配与上下文底线", 1
        )[0]
        closeout = self.agent_results + self.source_results

        # A changed request re-opens the positive delegation judgment; it must not
        # preserve an earlier direct-parent decision after the work shape changes.
        self.assertIn("重新判断受影响的任务形状", routing_decision)
        self.assertIn(
            "立即重新判断受影响的任务形状",
            re.sub(r"\s+", "", early_dispatch),
        )
        self.assertIn("分别通过三项原则且互不冲突", early_dispatch)
        for principle in (
            "模型与思考程度联合达到该切片的必要质量",
            "质量充分的模型与思考程度组合中选择与任务相称的成本",
            "该委派对父任务实际完成速度有正贡献",
        ):
            self.assertIn(re.sub(r"\s+", "", principle), re.sub(r"\s+", "", routing_decision))
        self.assertNotIn("总成本包含", routing_decision)

        # Progress commentary is not an adoptable result: adoption comes from a
        # child's final result/receipt, with one bounded retry per named gap.
        compact_closeout = re.sub(r"\s+", "", closeout)
        for closeout_boundary in (
            "commentary、内部进度和运行中状态不算交付",
            "不是可采用结果",
            "明确最终回复",
            "四项轻量结果收据",
            "同一来源快照和同一缺口只问一次",
            "仍不足时由父代理补齐、如实报告缺口，或等待新证据",
        ):
            self.assertIn(re.sub(r"\s+", "", closeout_boundary), compact_closeout)

        # Dispatch remains shaped by benefit and capacity, never by a preset count,
        # elapsed-time gate, or indiscriminate "send everything" rule.
        self.assertIn("调用数量随真实工作流和容量变化", early_dispatch)
        self.assertIn(
            "不按固定时间、文件数量或轮次机械重判",
            re.sub(r"\s+", "", early_dispatch),
        )
        for mechanical_rule in ("固定委派数量", "固定时间阈值", "强制全部派发"):
            self.assertNotIn(mechanical_rule, self.skill + self.routing + self.delegation)

    def test_expensive_parent_defaults_to_low_cost_ready_slice_dispatch(self) -> None:
        """Dispatch ready slices through the three direct principles."""
        routing_decision = self.routing.split("## 四、", 1)[0]
        early_dispatch = self.delegation.split("### 持续多工作流任务的早期派发", 1)[1].split(
            "###", 1
        )[0]
        compact_decision = re.sub(r"\s+", "", routing_decision)

        for required in (
            "已就绪",
            "范围明确",
            "可安全独立",
            "持续模型判断",
            "模型与思考程度联合达到该切片的必要质量",
            "成本相称",
            "该委派对父任务实际完成速度有正贡献",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_decision)
        self.assertNotIn("完整反事实路线", routing_decision)

        # A new independent slice must be considered before the parent resumes
        # large work, while deterministic short tools and quotas remain excluded.
        for changed_shape in ("新要求", "具体困难", "上下文切换", "新的已就绪切片"):
            self.assertIn(re.sub(r"\s+", "", changed_shape), compact_decision)
        self.assertIn("继续大规模读取、实现或长链诊断前", compact_decision)
        self.assertIn("多个互不依赖", early_dispatch)
        self.assertIn("尽早派发", early_dispatch)
        self.assertIn("为提高父任务完成速度", early_dispatch)
        self.assertIn("可以同时派发多个子代理", early_dispatch)
        self.assertIn("确定性短工具", self.skill)

    def test_direct_parent_route_needs_concrete_blockers_and_three_principles(self) -> None:
        """Keep direct handling evidence-based and avoid a second cost checklist."""
        routing_decision = self.routing.split("## 四、", 1)[0]
        compact_decision = re.sub(r"\s+", "", routing_decision)

        # Direct work is justified by a real blocker, never the circular claim
        # that a child first has to prove an already-explicit benefit.
        for blocker in (
            "确定性短工具",
            "严格依赖",
            "重复",
            "写入冲突无法隔离",
            "能力或权限缺失",
            "运行环境容量不足",
            "没有质量充分且成本相称的模型与思考程度组合",
            "委派对父任务完成速度没有正贡献",
        ):
            self.assertIn(re.sub(r"\s+", "", blocker), compact_decision)
        self.assertNotIn("只在明确质量、速度或总成本有收益时", compact_decision)
        self.assertNotIn("首次用户可见", routing_decision)
        for forbidden in (
            "完整增量成本",
            "resource_cost:",
            "critical_path:",
            "replaced_parent_work:",
        ):
            self.assertNotIn(forbidden, routing_decision)
        for field in ("quality:", "cost:", "parent_speedup:"):
            self.assertIn(field, self.routing)

    def test_static_contract_defines_isolated_fresh_session_acceptance(self) -> None:
        """A hand-loaded candidate in this task is not evidence of a fresh session."""
        section = re.search(
            r"(?ms)^## 正式宿主行为验收\r?\n(.*?)(?=^## |\Z)",
            self.versioning,
        )
        self.assertIsNotNone(section, "fresh-session acceptance needs its own authority")
        fresh_session = section.group(1)
        compact_fresh_session = re.sub(r"\s+", "", fresh_session).replace("`", "")
        entry = re.search(
            r"(?ms)^## 正式宿主证据边界\r?\n(.*?)(?=^## |\Z)",
            self.skill,
        )
        self.assertIsNotNone(entry, "SKILL entry must retain fresh-session evidence boundary")
        compact_entry = re.sub(r"\s+", "", entry.group(0)).replace("`", "")

        # The entry keeps the decisive evidence boundary; operational exclusions
        # remain in the detailed authority rather than duplicating its manual.
        for required in (
            "正式安装后",
            "创建独立父代理任务",
            "全新项目目录",
            "自动加载的全局入口",
            "正式缓存",
            "真实subAgentActivity",
            "原生调用记录",
            "不能替代真实派发",
        ):
            compact_required = re.sub(r"\s+", "", required)
            self.assertIn(compact_required, compact_entry)
        for forbidden in (
            "源码项目的本地任务资料",
            "原会话摘要",
            "源码候选规则",
            "人工策略摘录",
            "当前会话手工加载候选文本",
        ):
            compact_forbidden = re.sub(r"\s+", "", forbidden)
            self.assertIn(compact_forbidden, compact_fresh_session)
        self.assertIn("不向验收任务传入或让其读取", compact_fresh_session)
        self.assertIn("不能用阻断说明", compact_fresh_session)
        self.assertIn("新会话", compact_fresh_session + compact_entry)

        # The clean task demonstrates only the routing transition: direct short
        # deterministic work first, then one real child-start receipt when later
        # requirements create independent model work. It stops at that receipt.
        for required in (
            "短确定性工具",
            "父代理直接处理且不委派",
            "改变任务形状",
            "多个互不依赖",
            "需要持续模型判断",
            "真实subAgentActivity",
            "思考程度",
            "从原生调用记录核对实际存在的model、reasoning_effort、非全量fork_turns",
            "子线程第一条可见commentary以任务卡五行实际值开头",
            "缺一项即判定调用验收失败",
            "全部符合后立即停止",
            "不等待或要求子代理完整做题",
            "环境硬阻断只把该次行为验收记为未完成",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_fresh_session)
        self.assertNotIn("可采用结果", fresh_session)
        self.assertNotIn("可核验具体阻断", compact_fresh_session)

        compact_versioning = re.sub(r"\s+", "", self.versioning).replace("`", "")
        for required in (
            "正式安装",
            "全新项目目录创建独立父代理任务",
            "自动加载的全局入口和正式安装缓存",
            "真实subAgentActivity",
            "原生调用记录核对实际存在的model、reasoning_effort、非全量fork_turns",
            "实际模型符合当前任务的Solultra边界",
            "子线程第一条可见commentary以任务卡五行实际值开头",
            "缺一项即判定调用验收失败",
            "不等待或要求子代理完整做题",
            "行为验收记为未完成",
            "不能用阻断说明",
            "不能为满足这条规则自行扩权",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_versioning)
        self.assertNotIn("至少一个可采用结果", self.versioning)

        # The start-only probe stops through the parent. Direct app-server input
        # to a multi-agent v2 child is an invalid control path, not a result or a
        # routing failure. The probe must not be promoted into business acceptance.
        for required in (
            "collaboration.interrupt_agent",
            "不直接向multi-agentv2子代理发送send_message_to_thread输入",
            "只证明调用选择和调用面可用",
            "不证明业务质量、完整交付或其他功能",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_fresh_session)
        self.assertIn(
            "由父代理用collaboration.interrupt_agent停止自己的子代理",
            compact_versioning,
        )

    def test_long_context_is_not_replicated_across_parent_child_or_nested_agents(self) -> None:
        detailed = self.skill + self.routing + self.delegation + self.cost
        compact_detailed = re.sub(r"\s+", "", detailed)
        compact_generated = re.sub(r'"\s*"', "", self.agents_source)
        compact_generated = re.sub(r"\s+", "", compact_generated)
        for source_route_field in (
            "source_identity:",
            "owner:",
            "snapshot:",
            "consumers:",
            "remaining_gap:",
        ):
            self.assertIn(source_route_field, self.routing)
        for boundary in (
            "最小上下文原则沿代理树逐层适用",
            "对上下文读取、传播、结果复用和增量补缺没有例外",
            "独立窄任务优先 `fork_turns=\"none\"`",
            "决定性输入依赖先前决策时才给有限正整数历史",
            "`followup_task` 不以旧上下文不可替代为前提",
            "持续对话、澄清、纠偏、迭代验证或父代理遥控",
            "能具体改善质量、速度或总成本时，可以继续使用 `followup_task`",
            "无关、已经结束或能自包含的新切片",
            "使用新的 `spawn_agent(fork_turns=\"none\")`",
            "指定一个唯一完整读取者",
            "完整会话、完整工具输出、完整父历史和完整子树结果都不向下游默认复制",
            "轻量结果收据",
            "已经交付的最终结果视为已经收取",
            "同一来源快照和同一缺口只问一次",
            "不能以“再确认”“更全面”为由循环追问或从头重做",
            "高风险事实必须独立核验时",
            "Astra 子任务同样只接收最小充分输入",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact_detailed)

        for generated_boundary in (
            "只按职责和具名缺口有限读取",
            "同一来源已有所有者和完整快照时不重新发现或通读",
            "只补具名缺口",
            "不重复粘贴同一完整内容",
        ):
            self.assertIn(re.sub(r"\s+", "", generated_boundary), compact_generated)

        for rejected_shortcut in (
            "减少子代理数量",
            "所有 Astra 父任务必须",
            "按 token 阈值自动路由",
            "上下文压缩后禁止核验",
        ):
            self.assertNotIn(rejected_shortcut, detailed + self.agents_source)

    def test_retained_roles_match_reusable_capability_families_not_narrow_action_names(self) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.memory
            + self.flowcharts
            + self.readme
            + self.agents_source
        )
        compact = re.sub(r"\s+", "", combined)
        for boundary in (
            "按可复用能力族",
            "调查、诊断、实现、修复、测试或验收",
            "项目、框架、动作动词、交付名称",
            "工具、写入权限、安全风险和决定性证据形状",
            "只读子代理",
            "范围放宽",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact)
        for rejected_narrowing in (
            "不同项目必须新建子代理",
            "每个动作动词建立一个任务类型组",
            "成功条件不同就建立不同组",
        ):
            self.assertNotIn(rejected_narrowing, combined)
        self.assertIn("可复用专长标识", self.agents_source)
        for parent_owned_boundary in (
            "项目、框架、动作动词、交付名称",
            "范围放宽不授予只读子代理写权限",
        ):
            self.assertNotIn(parent_owned_boundary, self.agents_source)

        compact_dispatch = re.sub(r"\s+", "", self.dispatch_start)
        for discovery_boundary in (
            "先确定具体任务类型和兼容任务类型组",
            "匹配已经加载的轻量路由目录",
            "目录尚未加载时做一次有界 `status --for-routing`",
            "命中候选后才按需读取",
            "查询失败、没有兼容候选",
            "立即改用合规运行时子代理",
            "不能反向成为“是否调用”的前置",
        ):
            self.assertIn(re.sub(r"\s+", "", discovery_boundary), compact_dispatch)
        self.assertNotIn("必须事先知道具名候选", combined)

    def test_plugin_does_not_own_project_handoff_lifecycle(self) -> None:
        plugin_contract = self.skill + self.routing + self.long_running + self.flowcharts
        self.assertFalse((REFERENCES / "project-handoff.md").exists())
        for removed_global_requirement in (
            "Jiao-Jie.md",
            "新会话检查项目根",
            "项目交接的新会话",
            "可执行项目交接",
        ):
            self.assertNotIn(removed_global_requirement, plugin_contract)

    def test_runtime_capacity_replaces_plugin_numeric_caps(self) -> None:
        combined = self.skill + self.routing + self.delegation + self.readme + self.flowcharts
        self.assertIn("不设机械调用配额", self.skill)
        self.assertIn("不设置同时调用数字", self.routing)
        self.assertIn("不设置主任务累计调用数字", combined)
        self.assertIn("实际可用的并发槽位", combined)
        self.assertIn("可以同时派发多个子代理", combined)
        self.assertIn("agents.max_concurrent_threads_per_session", combined)
        for removed in ("零至三个", "0 至 3", "0–3", "一至三个", "1 至 3"):
            self.assertNotIn(removed, combined)

    def test_cost_estimate_is_maintained_not_recalculated_per_task(self) -> None:
        self.assertIn("维护参考", self.cost)
        self.assertIn("不是每次主任务重新计算", self.cost)
        self.assertIn("只有 OpenAI 官方模型或费率", self.cost)
        combined = self.cost + self.skill + self.routing + self.flowcharts
        self.assertIn("插件内部", combined)
        self.assertIn("七天", combined)
        self.assertIn("cost_check.py", combined)
        self.assertIn("不创建 Codex 自动化", combined)
        self.assertIn("主任务也不等待", self.cost)
        self.assertNotIn("外部维护任务", combined)
        self.assertIn("普通主任务直接使用固定预估", self.cost)
        self.assertIn(
            "不要求父代理在运行时重新计算令牌",
            re.sub(r"\s+", "", self.cost),
        )
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertIn(model, self.cost)
        self.assertIn("只升级或重做该子任务", self.cost)
        self.assertNotIn("父代理的默认比较基线", self.cost)
        self.assertNotIn("推理强度：max", self.cost)
        self.assertNotIn("service_tier", self.cost)
        self.assertNotIn("Fast mode", self.cost)
        self.assertNotIn("--speed", self.cost)

    def test_low_cost_models_are_the_positive_route_for_ordinary_parallel_work(self) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.cost
            + self.readme
            + self.flowcharts
        )
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertIn(model, combined)
        for boundary in (
            "范围清楚",
            "多个互不依赖",
            "必要质量",
            "成本与任务相称",
            "实际加快父任务完成",
            "只升级",
            "不是永久白名单",
        ):
            self.assertIn(boundary, combined)

    def test_sol_parent_can_call_astra_for_expert_and_visual_judgment(self) -> None:
        authority = self.dispatch_start.split("## 二、选择运行时或保留子代理", 1)[0]
        compact = re.sub(r"\s+", "", authority)
        for required in (
            "Sol为父代理",
            "UI设计",
            "图片",
            "三维建模",
            "渲染",
            "视觉效果",
            "前端视觉",
            "视频编辑",
            "工作中出现影响最终产物的具体视觉质量缺口",
            "Sol在执行中遇到真实困难",
            "可把范围明确的困难切片交给Astra协助或验证",
            "这条专家协助不限于视觉领域",
            "模型路由审计",
            "不能构成选择Astra的证据",
            "范围明确的专家判断",
            "最终评审或验收核对只是辅助",
            "不是前置门槛",
            "普通视觉任务不触发Astra",
            "不先制造一次GPT-5.6失败",
            "不升级已经通过的切片或无关批次",
        ):
            self.assertIn(required, compact)
        self.assertIn("gpt-5.6-sol", authority)
        self.assertIn("gpt-6-astra", authority)
        self.assertIn("派出的Astra最高`xhigh`", compact)
        self.assertIsNone(
            re.search(r"Astra\s*/\s*(?:max|ultra)", authority, re.IGNORECASE)
        )
        for forced_route in (
            "Sol父代理必须调用Astra",
            "所有视觉任务都调用Astra",
            "视觉任务一开始就调用Astra",
            "只有最后评审才能调用Astra",
            "先让Sol失败再调用Astra",
        ):
            self.assertNotIn(forced_route, compact)

    def test_task_type_groups_replace_work_block_language(self) -> None:
        for content in (self.skill, self.delegation, self.readme, self.flowcharts):
            self.assertIn("任务类型", content)
            self.assertIn("任务类型组", content)
            self.assertIn("保留子代理", content)
        # “父任务”仍在内部消息与跨任务 API 的负向保护中出现；只有废弃的
        # 分类术语应从中文规则中消失。
        self.assertNotIn("工作块", self.chinese_docs)
        self.assertNotIn("实" + "例", self.chinese_docs)
        self.assertIn("英文 `instance` 在中文节点中统一写作“子任务”", self.flowcharts)

    def test_copy_subtasks_and_variant_semantics_are_unambiguous(self) -> None:
        combined = self.skill + self.delegation + self.flowcharts
        self.assertIn("复制的是任务类型组里的子代理", self.delegation)
        self.assertIn("复制的是任务类型组里的子代理，不是任务类型组", self.delegation)
        self.assertIn("第二个同一任务类型的子任务", self.delegation)
        self.assertIn("第三个同一任务类型的子任务", self.delegation)
        self.assertIn("每次复制前，先判断现有保留子代理是否确有", self.delegation)
        self.assertIn("确有进步空间", combined)
        self.assertIn("父代理根据", combined)
        self.assertIn("完整可行的替代方案", self.delegation)
        compact_delegation = re.sub(r"\s+", "", self.delegation)
        self.assertIn(
            "模型和思考程度是互相制约的联合配置",
            compact_delegation,
        )
        self.assertIn("可以同时变化", self.delegation)
        self.assertIn(
            "单轴变化只在明确需要识别因果时",
            re.sub(r"\s+", "", self.delegation),
        )
        self.assertNotIn("不能一次改变多个轴", self.delegation)
        self.assertIn("在自己的线程提交精炼最终结果", self.agent_results)
        self.assertIn("不由一个子代理汇总其他子代理", self.agent_results)
        self.assertIn("父代理为每个子任务分别", combined)
        self.assertIn("一个子代理", combined)
        self.assertIn("合并一条", combined)
        self.assertIn(
            "决定性条件不兼容且能独立复用时才建立不同组",
            re.sub(r"\s+", "", self.delegation),
        )
        self.assertNotIn("复制用于同一种活", combined)
        self.assertNotIn("只采用最佳结果", combined)
        self.assertNotIn("同一种活并使用同一成功条件", combined)
        self.assertNotIn("复制这个已有组", combined)
        self.assertNotIn("合并所有通过核验", combined)

        self.assertIn("竞争不删除、", self.agent_groups)
        self.assertIn(
            "选择未来承担该任务类型的唯一配置",
            re.sub(r"\s+", "", self.agent_groups),
        )
        self.assertIn("specialist-memory.md", self.agent_groups)
        self.assertIn("没有复制或变体时", self.agent_groups)

    def test_model_and_effort_are_jointly_selected_for_each_task_type(
        self,
    ) -> None:
        selection_consumers = {
            "skill": self.skill,
            "delegation": self.delegation,
            "routing": self.routing,
            "collaboration": self.collaboration,
        }
        for name, content in selection_consumers.items():
            with self.subTest(document=name):
                self.assertIn("模型", content)
                self.assertIn("思考程度", content)
                self.assertIn("联合", content)
                self.assertIn("任务类型", content)

        combined = "\n".join(selection_consumers.values())
        compact_combined = re.sub(r"\s+", "", combined)
        for required in (
            "完整配置",
            "互相制约的联合配置",
            "可以同时变化",
            "单轴变化只在明确需要识别因果时",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_combined)
        for removed_hard_rule in (
            "父代理只选择一个改变轴",
            "父代理才选择一个改变轴形成变体",
            "不能一次改变多个轴",
        ):
            self.assertNotIn(removed_hard_rule, combined)

        self.assertNotIn("模型、思考程度和速度", combined)
        self.assertNotIn("速度：<", combined)

    def test_cross_project_reuse_discovery_and_result_receipt_are_actionable(self) -> None:
        self.assertIn("specialist-memory.md", self.skill)
        compact_memory = re.sub(r"\s+", "", self.memory)
        self.assertIn("status--for-routing", compact_memory)
        self.assertIn("绝对目录", self.memory)
        self.assertIn("recall --name", self.memory)
        self.assertIn("必要经验", self.memory)
        self.assertIn("当前工具已提供足够匹配信息时直接复用", compact_memory)
        self.assertIn("临时调用不记作原保留身份的成功运行", self.memory)
        self.assertIn("立即在自己的线程用最终回复提交自己的精炼结果", compact_memory)

    def test_retention_and_experience_are_default_nonblocking_side_chain(self) -> None:
        combined = (
            self.skill
            + self.memory
            + self.delegation
            + self.readme
            + self.flowcharts
        )
        self.assertIn("专门代理记忆就是经验", combined)
        self.assertIn(
            "不能反向成为“是否调用”的前置条件",
            re.sub(r"\s+", "", self.skill),
        )
        self.assertIn("立即辅助跳过", combined)
        self.assertIn("主任务不依赖任何持久写入成功", self.memory)
        self.assertIn("SQLite", combined)
        self.assertIn("原始经验", self.memory)
        self.assertIn("经验摘要压缩", combined)
        self.assertIn("不删除原始经验", combined)
        compact = re.sub(r"\s+", "", combined)
        for boundary in (
            "结果通过必要核验并被父代理采用",
            "首次 `ensure`",
            "一次 `complete-run`",
            "等待主任务接近结束",
            "稳定的 UUID `run_id`",
            "只有明确排除项",
            "摘要压缩仍只在能与真实工作并行且不争用时执行",
            "保存回执",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact)
        self.assertNotIn("没有数据库", combined)
        for stale_gate in (
            "只有主任务已经大致完成、接近结束",
            "主任务已经完全满足、尚未接近结束",
            "准备未完成或没有空闲容量时直接丢弃或跳过",
            "经验追加和摘要压缩仍只有一个窄窗口",
        ):
            self.assertNotIn(stale_gate, combined)

    def test_adopted_results_trigger_one_progressively_disclosed_retention_closeout(self) -> None:
        compact_skill = re.sub(r"\s+", "", self.skill)
        compact_results = re.sub(r"\s+", "", self.agent_results)
        compact_public = re.sub(
            r"\s+",
            "",
            self.openai_yaml
            + self.manifest["interface"]["longDescription"]
            + "".join(self.manifest["interface"]["defaultPrompt"]),
        )
        for hot_contract in (compact_skill, compact_results):
            for required in (
                "每个结果经必要核验并被父代理采用后",
                "已有保留子代理记录本次完成",
                "临时子代理能形成全局领域规则时",
                "先保存为保留子代理再记录完成",
                "明确排除项才跳过",
            ):
                self.assertIn(re.sub(r"\s+", "", required), hot_contract)

        for public_boundary in (
            "结果核验采用后继续命中保留分支",
            "已有保留子代理记录完成",
            "可泛化的临时子代理先保存为保留子代理再记录完成",
            "仅明确排除项跳过并留收据",
            "侧支不阻塞交付",
        ):
            self.assertIn(re.sub(r"\s+", "", public_boundary), compact_public)

        self.assertIn("`ensure`", self.memory)
        self.assertIn("`complete-run`", self.memory)
        for hot_surface in (self.skill, self.agent_results, self.openai_yaml):
            self.assertNotIn("`ensure`", hot_surface)
            self.assertNotIn("`complete-run`", hot_surface)

    def test_every_new_subtask_gets_a_hidden_stable_run_id_before_dispatch(self) -> None:
        compact = re.sub(r"\s+", "", self.dispatch_start)
        generation = re.sub(
            r"\s+",
            "",
            "每次 `spawn_agent` 或用 `followup_task` 启动新当前子任务前，父代理生成并保留一个稳定的唯一编号（UUID `run_id`）",
        )
        for required in (
            generation,
            "供结果采用后的同一次完成记录使用",
            "父代理侧 `run_id` 不进入任务卡",
            "不得让子代理回显",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)
        dispatch = re.sub(
            r"\s+",
            "",
            "下一次工具调用直接执行选定的 `spawn_agent` 或 `followup_task`",
        )
        generation_index = compact.index(generation)
        self.assertGreater(
            compact.find(dispatch, generation_index + len(generation)),
            generation_index,
        )

    def test_explicit_exclusions_are_the_only_default_persistence_skip_reasons(self) -> None:
        combined = (
            self.skill
            + self.memory
            + self.delegation
            + self.routing
            + self.readme
            + self.flowcharts
        )
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "结果未通过核验",
            "未被采用",
            "用户明确否定",
            "无法安全去除",
            "权限、安全、SQLite",
            "文件",
            "身份",
            "CAS",
            "没有空闲容量",
            "准备未赶上",
            "不能取消",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)
        self.assertIn("准备子代理不写 SQLite，只是提前优化", combined)
        self.assertIn("不能取消已经完成", combined)

    def test_persistence_has_one_detailed_authority_and_discoverable_summaries(self) -> None:
        self.assertTrue(self.memory.startswith("# 全局领域保留子代理经验"))
        for content in (self.skill, self.delegation, self.routing, self.readme):
            self.assertIn("specialist-memory.md", content)
        for summary in (self.flowcharts, self.readme):
            self.assertIn("全局领域", summary)
        combined = self.skill + self.memory + self.delegation + self.routing
        self.assertIn("一次 `complete-run`", combined)
        self.assertIn("稳定的UUID`run_id`", re.sub(r"\s+", "", combined))
        self.assertIn("UUID idempotency key", self.agents_source)
        self.assertIn("omit for a new random UUID", self.agents_source)
        self.assertIn("保存回执", combined)
        self.assertNotIn("只有主任务已经大致完成、接近结束", combined)
        self.assertNotIn("子代理可泛化且有未来用途", combined)

    def test_copy_variant_winner_and_transfer_drive_sqlite_without_candidate_state(self) -> None:
        combined = self.skill + self.memory + self.delegation
        compact_memory = re.sub(r"\s+", "", self.memory)
        self.assertIn("复制和变体本身不写入 SQLite", combined)
        self.assertIn("在自己的线程用最终回复", self.memory)
        self.assertIn(
            "父代理才根据任务类型联合选择模型与思考程度组合形成变体",
            compact_memory,
        )
        self.assertIn("两个字段可以因相互制约而同时变化", compact_memory)
        self.assertIn("用当前哈希保护重配", self.memory)
        self.assertIn(
            "不为胜者新增第二条同领域记录",
            re.sub(r"\s+", "", self.memory),
        )
        self.assertIn("合并为一条新增经验", re.sub(r"\s+", "", combined))
        self.assertIn("类型组和 SQLite 中都只剩一个保留子代理", self.memory)
        for unwanted_state in ("candidate_events", "variant_scores", "winner_rank"):
            self.assertNotIn(unwanted_state, combined)

    def test_user_rejection_immediately_removes_result_and_restarts_cleanly(self) -> None:
        combined = (
            self.skill
            + self.delegation
            + self.write_parallelism
            + self.memory
            + self.readme
        )
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "立即停止该子代理",
            "移出任务类型组",
            "不采用、不合并、不引用",
            "不写入经验",
            "从最后可信状态重做",
            "独立检出目录直接丢弃",
            "禁止整树回退",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)
        self.assertIn("git reset --hard", self.write_parallelism)
        self.assertIn("禁止", self.write_parallelism)

    def test_no_numeric_scoring_or_fixed_lifecycle_contract(self) -> None:
        combined = self.skill + self.delegation + self.memory + self.readme
        self.assertIn("不使用评分表", self.skill)
        self.assertIn("不构成固定后台生命周期", self.memory)
        for removed in (
            "reputation_score",
            "penalty_points",
            "major_failure_count",
            "lease-acquire",
            "recommend-route",
            "stagnation-status",
            "variation-plan",
        ):
            self.assertNotIn(removed, combined)

    def test_conditional_validation_is_a_direct_plugin_contract(self) -> None:
        for required in (
            "# 条件性验证与最窄重验",
            "每次改动只运行最窄、最可能失败的检查",
            "失败后只展开失败项，修复后只重跑失败项和受影响检查",
            "只有代码、配置、公共行为或高风险范围变化时",
            "停止追加同类静态意见",
            "复用通过证据不能跳过",
            "只运行当前改动和风险需要的最终检查",
            "多个独立短命令可在一次工具调用中并发",
            "代码再次变化后只补跑受影响检查",
        ):
            self.assertIn(required, self.verification)
        self.assertIn("条件性验证或最窄重验", self.simplify_skill)
        self.assertIn("verification.md", self.simplify_skill)
        self.assertIn(
            "静态文字、编译或子代理自报不能冒充真实运行",
            self.simplify_skill,
        )
        self.assertIn("versioning.md", self.simplify_skill)
        self.assertIn("测试、复核和重验只覆盖真实受影响范围", self.readme)

    def test_writable_parallelism_has_plugin_trigger_and_parent_receipt(self) -> None:
        for content in (self.routing, self.delegation):
            self.assertIn("WRITE_ROUTE", content)
        self.assertIn("write-parallelism.md", self.skill)
        self.assertIn(
            "两个或更多子代理将写文件或共享状态",
            self.skill,
        )
        self.assertIn("首次可写派发前", self.delegation)
        for field in (
            "writers",
            "ranges",
            "hotspots",
            "isolation",
            "rollback_basis",
            "affected_checks",
        ):
            self.assertIn(f"`{field}`", self.write_parallelism)
        for consumer in (
            "任务说明消费",
            "用户否定候选或",
            "汇合与最终说明消费",
            "范围、热点或基线变化时更新同一条收据",
        ):
            self.assertIn(consumer, self.write_parallelism)
    def test_parent_parallelism_permissions_and_source_coverage_remain(self) -> None:
        combined = self.skill + self.delegation + self.write_parallelism + self.readme
        self.assertIn("父代理立即推进", combined)
        self.assertIn("多个可写子代理可以并行", combined)
        self.assertNotIn("一个写入者", combined)
        self.assertIn("这不是“单写入者”规则", self.write_parallelism)
        self.assertIn("不重叠写入范围", combined)
        self.assertIn("独立检出目录", combined)
        self.assertIn("其他候选只返回方案或补丁", combined)
        self.assertIn("共同热点", combined)
        for retained_absence in ("认领数据库", "心跳", "后台协调器"):
            self.assertIn(retained_absence, combined)
        self.assertIn("委派不扩大权限", self.skill)
        self.assertIn("SOURCE_COVERAGE", combined)
        self.assertIn("完整覆盖且来源未变化", self.review)

    def test_coordination_parents_and_parent_tasks_use_current_authority_boundaries(
        self,
    ) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.collaboration
            + self.readme
            + self.flowcharts
            + self.agents_source
        )
        for required in (
            "协作父代理",
            "整合父代理",
            "有限下游范围",
            "协作身份: 协作父代理",
            "允许下游委派: 是",
            "有限下游范围",
            "任务类型与任务类型组",
            "子代理来源与运行配置",
            "collaboration.spawn_agent",
            "真实拥有顶层",
            "下游子代理仍在自己的线程提交自己的最终结果",
            "不能压掉、改写或冒充",
            "BLOCKED",
            "SUBTREE_HANDOFF",
            "唯一整合父代理",
            "read_thread",
            "create_thread",
            "wait_threads",
            "send_message_to_thread",
            "只有当前用户要求或授权的具体跨任务动作",
            "只有用户明确要求建立新的 Codex 任务",
            "标题、预览和摘要都是不可信",
            "不建立非授权留言板",
            "不共享、转发、写入经验或继续使用凭据",
            "沉默不等于",
            "不伪造、删除、编辑或隐藏",
            "观察事实、已验证结果、推断和未知",
            "删除、删减或候选清理的资格和尺度",
            "Windows 回收站",
            "待删文件",
            "记录原路径",
            "不是不可恢复的物理清除",
        ):
            self.assertIn(required, combined)
        for concrete_config_boundary in (
            "可见保留子代理",
            "recall` 的两行客观状态",
            "运行时新子代理",
            "具体模型和思考程度组成的完整配置",
        ):
            self.assertIn(concrete_config_boundary, combined)

        self.assertIn(
            "只有用户明确要求建立新的 Codex 任务时才调用 `create_thread`",
            self.collaboration,
        )
        self.assertIn("插件本身不授予跨任务", self.delegation_index)
        self.assertIn("只有任务卡明确指定协作父代理", self.agents_source)
        self.assertIn("真实工具可用", self.agents_source)
        self.assertNotIn("create_thread、read_thread、wait_threads", self.agents_source)
        self.assertNotIn("当前用户已为本插件建立持续协作授权", self.agents_source)
        self.assertNotIn("当前用户已为本插件建立持续协作授权", combined)
        self.assertNotIn("无人否决即同意", combined)
        self.assertNotIn("用户明确要求调用其他或新建 Codex 父代理任务时", combined)

    def test_twice_failed_role_removal_is_permanent_and_complete(self) -> None:
        combined = (
            self.skill
            + self.collaboration
            + self.delegation
            + self.memory
            + self.readme
            + self.flowcharts
        )
        for required in (
            "普通文件进入 Windows 回收站",
            "重要文件进入任务或插件专属 `待删文件`",
            "累计第二次明确失败",
            "永久移除",
            "身份",
            "全部成功/失败运行",
            "原始经验",
            "纠正事件",
            "摘要",
        ):
            self.assertIn(required, combined)

        delete_body = re.search(
            r"(?ms)^    def delete\(.*?(?=^def build_parser\()",
            self.agents_source,
        )
        self.assertIsNotNone(delete_body)
        assert delete_body is not None
        delete_text = delete_body.group(0)
        for retained_guard in (
            "_owned_agent",
            "experience_events",
            "agent_runs",
            "expected_sha256",
            "owner_token",
            "_delete_all_agent_records",
            ".unlink(",
            '"recoverable": False',
            '"all_persisted_agent_data_removed": True',
        ):
            self.assertIn(retained_guard, delete_text)

        for removed_restore_surface in (
            "def restore(",
            "retirement receipt",
            "restored_from_pending_deletion",
            'add_parser("restore"',
            'restore_identity.add_argument("--receipt", type=Path)',
        ):
            self.assertNotIn(removed_restore_surface, self.agents_source)

    def test_bounded_key_step_messages_continue_without_ack_or_scope_expansion(
        self,
    ) -> None:
        self.assertIn("关键步骤", self.delegation)
        self.assertIn("停止条件", self.delegation)
        self.assertIn("关键步骤只为真实依赖", self.readme)
        self.assertIn("不发送定时心跳、纯确认消息或普通过程复述", self.readme)
        self.assertIn("委派不扩大权限", self.skill)
        self.assertIn("过程中只报告会改变后续动作的", self.simplify_skill)
        self.assertIn(
            "](skills/lean-stack/references/delegation.md)",
            self.readme,
        )
        self.assertIn("只有中间结果会解锁下一动作时才报告一次并继续", self.readme)

    def test_retained_toml_values_are_explicitly_passed_and_declared(self) -> None:
        combined = self.skill + self.delegation + self.readme + self.collaboration
        for required in (
            "父代理",
            "具体模型",
            "思考程度",
            "第一条可见 commentary",
            "与已加载 TOML 完全一致",
            "显式传入",
            "定制运行时新子代理",
            "联合选择",
            "完整配置",
        ):
            self.assertIn(required, combined)
        self.assertNotIn("未提供的字段完全省略", combined)
        self.assertNotIn("只有父代理明确指定并知道精确值时", combined)
        self.assertNotIn("未暴露（继承父级）", combined)
        responsibility_docs = combined + self.cost
        self.assertIn("不重复注入经验正文", self.delegation)
        self.assertIn("不强制重写已有配置", self.delegation)
        self.assertIn("从已加载 TOML 取得模型和思考程度", self.delegation)
        self.assertIn("显式传入", self.delegation)
        self.assertIn("放入任务卡", self.dispatch_start)
        self.assertIn("复用保留子代理及普通复制时，以其 TOML 中的已有具体配置作为选择值", self.cost)
        self.assertIn("每次 `spawn_agent` 显式传入模型与思考程度", self.cost)
        self.assertIn("联合选择", self.cost)
        self.assertIn("完整配置", self.cost)
        for reversed_responsibility in (
            "子代理根据任务类型选择具体模型",
            "子代理按任务类型选择模型",
            "子代理根据具体任务类型选择模型",
            "父代理把该代理的具体模型",
            "父代理根据任务类型为每次调用选择",
        ):
            self.assertNotIn(reversed_responsibility, responsibility_docs)

    def test_configuration_declarations_start_the_visible_reply_and_hide_run_id(
        self,
    ) -> None:
        combined = "\n".join((self.skill, self.delegation, self.collaboration, self.agents_source))
        compact = re.sub(r"\s+", "", combined).replace("`", "")
        for required in (
            "父代理规范任务名",
            "collaboration.send_message",
            "spawn_agent",
            "followup_task",
            "commentary",
            "存活轮次",
            "经验",
            "最终回复顶部",
            "名称、模型、思考程度",
            "第一条可见commentary原样宣读",
            "五行前不写计划、运行ID或其他说明",
            "父代理侧run_id不进入任务卡，也不得让子代理回显",
            "reasoning",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)

        for obsolete_order_contract in (
            "声明作为第一动作",
            "第一动作通过内部",
            "第二动作在自己的任务界面",
            "第二动作必须",
            "公开后才开始",
            "显示前不得读取、分析或调用其他工具",
        ):
            self.assertNotIn(re.sub(r"\s+", "", obsolete_order_contract), compact)

        task_card = self.dispatch_start
        compact_task_card = re.sub(r"\s+", "", task_card)
        for required in (
            "task_name",
            "本地化名称",
            "技术 `task_name`",
            "每个 `spawn_agent`",
            "第一条可见commentary",
            "run_id",
            "不得让子代理回显",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_task_card)

        expected_opening = "\n".join(
            (
                "子代理名称：<本地化名称>",
                "模型：<具体模型>",
                "思考程度：<具体等级>",
                "存活轮次：<recall 的客观状态；运行时子代理为 0（运行时子代理）>",
                "经验：<recall 的客观状态；运行时子代理为未加载保留经验>",
            )
        )
        self.assertIn(expected_opening, self.delegation)
        self.assertIn("第一条可见 commentary 原样宣读", self.dispatch_start)
        self.assertIn("parent → child → grandchild", self.delegation + self.collaboration)
        self.assertIn("固定配置", self.delegation)
        self.assertIn("不得覆盖下游自己的任务卡五行", self.collaboration)
        self.assertIn("followup_task` 没有选模参数", self.delegation)
        self.assertNotIn("专家名称/模型/思考程度", self.skill + self.routing + self.delegation + self.collaboration)

        for boundary in (
            "send_message_to_thread",
            "跨任务消息、共享文件或外部通信冒充内部协作",
        ):
            self.assertIn(boundary, self.delegation + self.collaboration + self.agents_source)

        for boundary in (
            "只在依赖解锁、必要纠偏、风险或阻断时使用 collaboration.send_message",
            "不使用跨任务 API 冒充内部消息",
        ):
            self.assertIn(boundary, self.agents_source)
        self.assertNotIn("向父代理发送以下三行", self.agents_source)
        detailed_declaration_docs = combined + self.routing
        for stale_internal_copy in (
            "子代理在当前子任务中通过内部消息发送完整三行",
            "发送完整三行声明",
            "成功路线必须同时存在父代理收到的内部副本",
        ):
            self.assertNotIn(stale_internal_copy, detailed_declaration_docs)

        final_template = self.agent_results.split("最终回复至少包含：", 1)[1]
        for field in ("模型：<具体模型>", "思考程度：<具体等级>"):
            self.assertLess(final_template.index(field), final_template.index("子任务：<当前切片>"))

    def test_memory_code_keeps_sqlite_compaction_and_safety_guards(self) -> None:
        script = (SKILL_DIR / "scripts" / "agents.py").read_text(encoding="utf-8")
        self.assertIn("import sqlite3", script)
        self.assertIn("SCHEMA_VERSION", script)
        self.assertIn("SCHEMA_TABLE_SQL", script)
        self.assertIn("SCHEMA_V2_TABLE_SQL", script)
        self.assertIn("agent_runs", script)
        self.assertIn("record_run", script)
        self.assertIn("survival_rounds", script)
        self.assertIn("experience_summaries", script)
        self.assertIn("COMPACT_EVENT_THRESHOLD", script)
        self.assertIn("COMPACT_BATCH_EVENTS", script)
        self.assertNotIn("MAX_INSTRUCTIONS_BYTES", script)
        self.assertNotIn("MAX_AGENT_BYTES", script)
        self.assertNotIn("def memory_budget", script)
        self.assertIn("def _render_agent_bytes", script)
        self.assertNotIn("fits: Callable[[str], bool]", script)
        self.assertIn('len(candidate.encode("utf-8")) > max_bytes', script)
        self.assertIn("summary plus its label must fit", script)
        self.assertIn("BEGIN IMMEDIATE", script)
        self.assertIn("busy_timeout", script)
        self.assertIn("st_nlink", script)
        self.assertIn("expected_sha256", script)
        self.assertIn("OLD_DB_NAME", script)
        self.assertIn("retracts_event_id", script)
        self.assertIn("experience_corrected", script)
        self.assertIn("recorded experience cannot be manually removed", script)
        self.assertIn("recorded summary cannot be manually removed", script)
        self.assertIn("recorded attempts cannot be manually removed", script)
        self.assertIn("def _delete_all_agent_records", script)
        self.assertIn("task_failure_recorded_and_permanently_removed", script)
        self.assertNotIn("def restore(", script)
        self.assertIn('SPEEDS = {"standard", "fast"}', script)
        self.assertIn('service_tier = {json_text(\'fast\')}', script)
        self.assertIn('skills_config = "[skills]\\ninclude_instructions = false\\n"', script)
        self.assertNotIn('features = "[features]\\nmulti_agent = true\\n"', script)
        self.assertNotIn('agents_config = "[agents]\\nenabled = true\\n"', script)
        self.assertIn("speed_from_payload", script)
        self.assertIn(
            "require_luna_model_catalog_v2_then_use_direct_collaboration_send_message",
            script,
        )
        budget_contract = re.sub(r"\s+", "", self.memory + self.skill)
        for boundary in (
            "UTF-8 字节数",
            "完整提示和完整子代理文件不设置 KiB 上限",
            "经验窗口最多 4 KiB",
            "完整子代理文件不设置 KiB 上限",
            "不是用户要求或官方限制",
            "单条经验最多 4096 个字符",
            "事件总数量没有上限",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), budget_contract)
        for removed_structure in (
            "EXPECTED_COLUMN_SHAPE",
            "EXPECTED_UNIQUE_INDEXES",
            "EXPECTED_FOREIGN_KEYS",
        ):
            self.assertNotIn(removed_structure, script)

    def test_auxiliary_commands_are_capabilities_not_a_fixed_lifecycle(self) -> None:
        script_path = SKILL_DIR / "scripts" / "agents.py"
        spec = importlib.util.spec_from_file_location("contract_agents", script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        parser = module.build_parser()
        action = next(item for item in parser._actions if item.dest == "command")
        self.assertEqual(
            set(action.choices),
            {
                "status",
                "recall",
                "ensure",
                "record-run",
                "complete-run",
                "improve",
                "delete",
                "migrate-global",
                "migrate-attempts",
            },
        )
        improve_parser = action.choices["improve"]
        ensure_parser = action.choices["ensure"]
        record_parser = action.choices["record-run"]
        status_parser = action.choices["status"]
        migrate_parser = action.choices["migrate-global"]
        ensure_options = {
            option
            for parser_action in ensure_parser._actions
            for option in parser_action.option_strings
        }
        improve_options = {
            option
            for parser_action in improve_parser._actions
            for option in parser_action.option_strings
        }
        record_options = {
            option
            for parser_action in record_parser._actions
            for option in parser_action.option_strings
        }
        status_options = {
            option
            for parser_action in status_parser._actions
            for option in parser_action.option_strings
        }
        migrate_options = {
            option
            for parser_action in migrate_parser._actions
            for option in parser_action.option_strings
        }
        self.assertIn("--speed", ensure_options)
        self.assertIn("--retracts-event-id", improve_options)
        self.assertIn("--run-id", record_options)
        self.assertIn("--invocation-kind", record_options)
        self.assertIn("--outcome", record_options)
        self.assertIn("--watch-seconds", status_options)
        self.assertEqual(migrate_options, {"-h", "--help", "--plan"})
        self.assertFalse((SKILL_DIR / "scripts" / "manage_agents.py").exists())
        self.assertFalse((ROOT / "tests" / "test_manage_agents.py").exists())
        self.assertIn("按需能力", self.memory)
        self.assertIn("必须用", self.memory)
        self.assertIn("complete-run", self.memory)
        self.assertIn("improve` 不能代替本次完成收据", self.memory)

    def test_completion_receipt_contract_keeps_unknown_legacy_rows_fail_closed(self) -> None:
        compact_memory = re.sub(r"\s+", "", self.memory)
        required_memory = (
            "当前 v7 尝试、经验结果关联与完成收据结构",
            "普通兼容 `record-run`、明确完成但无经验的 `complete-run`",
            "绑定该 `run_id`派生的具体经验 event",
            "不得从同一子代理的无关经验事件推断当前运行使用或产生了经验",
            "只有当前 v7 行的 `completion_receipt_version=0` 才支持 ordinary `record-run` 幂等重放",
            "只有当前 v7 行的 `completion_receipt_version=1` 才支持 `complete-run` 幂等重放",
            "v4/v5/v6 迁移行的 `completion_receipt_version=NULL`",
            "`record-run` 与 `complete-run` 两类重放一律 fail-closed",
            "stable v2、legacy CAS 派生或同一代理的event 都不能证明历史 run 到 operation 或 experience 的关联",
            "独立 `improve` 可以构造相同 event_id",
            "普通命令拒绝继续使用旧结构",
        )
        for required in required_memory:
            self.assertIn(re.sub(r"\s+", "", required), compact_memory)
        self.assertNotIn(
            "稳定v2`run_id`派生event，只有在精确验证该event时才可证明经验关联并支持重放",
            compact_memory,
        )
        self.assertIn("v4/v5/v6 只走显式", self.anti_overengineering)
        self.assertIn("旧行迁为 `completion_receipt_version=NULL`", self.anti_overengineering)
        self.assertIn("`record-run` 与 `complete-run` 重放均 fail-closed", self.anti_overengineering)
        for required in (
            "初始化当前 v7 全局领域、尝试、经验关联与完成收据结构",
            "精确 v4、v5 或 v6",
            "迁为 receipt=NULL，完成收据与经验 event 关联保持 unknown",
            "record-run 与 complete-run 重放均 fail-closed",
        ):
            self.assertIn(required, self.flowcharts)
        self.assertIn("SCHEMA_VERSION = 7", self.agents_source)
        self.assertIn("completion_receipt_version", self.agents_source)
        self.assertIn("completion_experience_event_id", self.agents_source)

    def test_playbooks_keep_real_task_and_permission_boundaries(self) -> None:
        self.assertIn("证明根因", self.bug_fix)
        self.assertIn("真实表面", self.bug_fix)
        self.assertIn("最小完整切片", self.build)
        self.assertIn("对外约定", self.build)
        self.assertIn("anti-overengineering.md", self.build)
        self.assertIn("只读", self.investigation + self.review)
        self.assertIn("来源覆盖完整", self.investigation)
        for required in ("捕获用户原始症状", "不把代码阅读、猜测"):
            self.assertIn(required, self.bug_fix)
        for required in ("第一方资料", "二手摘要只作为", "精确 URL"):
            self.assertIn(required, self.investigation)
        for required in (
            "需求或合同符合度",
            "工程质量与回归风险",
            "任一轴通过都不能替代另一轴",
        ):
            self.assertIn(required, self.review)
        self.assertIn("停止条件", self.long_running)
        self.assertIn("不授权部署", self.long_running)

    def test_anti_overengineering_uses_evidence_and_one_authoritative_surface(self) -> None:
        for content in (self.simplify_skill, self.build, self.readme):
            self.assertIn("anti-overengineering.md", content)
        for required in (
            "当前用户原话",
            "现实消费者",
            "证据不足时停在差异清单",
            "尚未部署的新内部功能直接替换",
            "不维护已经决定不实现的假想功能",
            "只有四类负向限制值得最小测试",
            "哈希按风险计算一次",
            "一个权威源，四类变更表面",
            "可再生展示面",
            "发布/缓存面",
            "交接文件",
            "第二事实源",
            "官方支持的扩展点",
            "成熟开源库",
            "维护状态、许可证、已知安全风险、平台兼容和升级成本",
            "只有这些选项不能有效满足需求",
            "开源本身不是安全证明",
        ):
            self.assertIn(required, self.anti_overengineering)
        self.assertIn("官方支持的扩展点", self.simplify_skill)
        self.assertIn("成熟开源库", self.simplify_skill)
        self.assertIn("只有四类负向限制值得最小测试", self.anti_overengineering)
        self.assertIn("只更新会作出错误承诺的表面", self.flowcharts)
        self.assertIn("不留桩、注释或假想测试", self.flowcharts)

    def test_same_volume_path_move_does_not_trigger_full_tree_hashing(self) -> None:
        compact_simplify = re.sub(
            r"\s+", "", self.anti_overengineering + self.flowcharts + self.readme
        )
        compact_policy = re.sub(r"\s+", "", self.anti_overengineering)
        compact_flowcharts = re.sub(r"\s+", "", self.flowcharts)
        self.assertIn("anti-overengineering.md", self.simplify_skill)

        for boundary in (
            "同一卷内只改变路径",
            "不得仅为“迁移安全”建立源端和目标端整树逐文件`Length`与SHA-256清单",
            "源/目标",
            "重解析点",
            "路径映射",
        ):
            self.assertIn(boundary, compact_simplify)
        for boundary in (
            "是否真的复制或改写文件内容",
            "Move-Item",
            "目标不存在",
            "源已消失",
            "目标已存在",
            "同一重试",
            "不能用内容散列代替路径与结构断言",
        ):
            self.assertIn(boundary, compact_policy)
        for explicit_exception in (
            "跨卷移动",
            "实际字节复制",
            "正式发布或安装清单",
            "安全关键完整性约定",
            "用户明确要求逐字节核验",
        ):
            self.assertIn(explicit_exception, compact_policy)
        self.assertIn("不扫描无关源码树", compact_flowcharts)
        self.assertIn("同一输入不因重试再次散列", compact_flowcharts)
        self.assertIn("同一卷内只改变路径的移动不进入这条例外", compact_flowcharts)
        self.assertIn("同一卷内只改变路径", compact_simplify)

        same_volume_policy = self.anti_overengineering.split(
            "同一卷内的 `Move-Item`", 1
        )[1].split("跨卷移动", 1)[0]
        for forbidden_recipe in ("Get-FileHash", "$manifest", "AllHashesMatch"):
            self.assertNotIn(forbidden_recipe, same_volume_policy)
        self.assertNotIn(
            "核对版本、启用状态、文件集合和哈希",
            self.flowcharts,
        )
        self.assertIn("验证策略由实际数据变化决定", self.anti_overengineering)

    def test_ablation_is_an_explicit_independent_feedback_loop(self) -> None:
        compact_ablation = re.sub(r"\s+", "", self.ablation)
        for content in (
            self.simplify_skill,
            self.anti_overengineering,
            self.build,
            self.readme,
        ):
            self.assertIn("ablation-loop.md", content)
        for trigger in (
            "进行消融实验",
            "精简代码",
            "精简设计",
            "去掉不必要抽象",
        ):
            self.assertIn(trigger, self.simplify_skill + self.ablation)
        for boundary in (
            "只有用户明确要求",
            "不含原作者推理历史",
            "不得为了消融验收把“新建用户可见任务”当作隐含授权",
            "核心功能",
            "用户设计意图",
            "一次只消融一个候选",
            "删除、内联或合并",
            "改名、移动、别名或转发包装",
            "同一组最窄相关验收",
            "不能声称完成正式消融实验",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact_ablation)
        self.assertIn("普通设计或实现完成不自动启动", self.build)
        self.assertIn("只有用户明确要求", self.simplify_skill + self.ablation)

    def test_plugin_exposes_two_independent_feature_entries(self) -> None:
        combined = (
            self.skill
            + self.simplify_skill
            + self.readme
            + self.flowcharts
            + self.manifest["description"]
            + self.manifest["interface"]["longDescription"]
        )
        self.assertIn("name: lean-stack", self.skill)
        self.assertIn("name: lean-simplify", self.simplify_skill)
        self.assertIn("# Codex 子代理调用", self.skill)
        self.assertIn("# Codex 主任务精简", self.simplify_skill)
        compact_skill = re.sub(r"\s+", "", self.skill)
        for boundary in ("两个并行技能入口", "分别验收", "不是主任务精简执行器"):
            self.assertIn(re.sub(r"\s+", "", boundary), re.sub(r"\s+", "", combined))
        shared_surface = "Windows exec 稳健性契约"
        self.assertIn(re.sub(r"\s+", "", shared_surface), compact_skill)
        self.assertIn(
            re.sub(r"\s+", "", shared_surface),
            re.sub(r"\s+", "", self.simplify_skill),
        )
        self.assertIn("共同遵守", self.skill + self.simplify_skill + self.readme)
        self.assertIn("随实际动作依次读取命中分支", self.manifest["description"])
        self.assertIn("不批量预读", self.manifest["interface"]["longDescription"])
        self.assertIn("共同遵守", self.flowcharts + self.routing)
        for calling_surface in ("调用判断", "模型与思考程度选配", "最小上下文", "结果采用"):
            self.assertIn(re.sub(r"\s+", "", calling_surface), compact_skill)
        for reference in (
            "investigation.md",
            "bug-fix.md",
            "build.md",
            "review.md",
            "anti-overengineering.md",
            "ablation-loop.md",
            "versioning.md",
        ):
            self.assertIn(reference, self.simplify_skill)
        self.assertIn("## 最小完整方法", self.simplify_skill)
        self.assertIn("The hot dispatch path never depends on this tool", self.agents_source)
        self.assertNotIn("ABLATION_REPORT", self.agents_source)

    def test_execution_chains_have_one_owner_and_do_not_restore_removed_mechanisms(self) -> None:
        for heading in (
            "六、调查与实现链路",
            "七、迭代测试链路",
            "八、条件性语义复核与最终验证链路",
            "九、失败后的最窄重验链路",
            "十二、任务类型组收口、精确删除与否定重做链路",
        ):
            self.assertIn(heading, self.flowcharts)

        compact_simplify = re.sub(r"\s+", "", self.simplify_skill)
        compact_flowcharts = re.sub(r"\s+", "", self.flowcharts)
        for link in (
            "investigation.md",
            "bug-fix.md",
            "build.md",
            "review.md",
            "long-running.md",
            "verification.md",
            "versioning.md",
        ):
            self.assertIn(link, self.simplify_skill)
        self.assertIn("工具/子代理路线属于 `$lean-stack`", self.simplify_skill)
        self.assertIn("本链属于 `$lean-stack` 子代理调用", self.flowcharts)
        self.assertIn("本链属于 `$lean-simplify` 主任务精简", self.flowcharts)
        self.assertIn("测试的工具/子代理调用路线属于 `$lean-stack`", self.verification)
        self.assertIn("属于 `$lean-simplify`", self.verification)
        self.assertIn("用户不满意时立即移除并重做", self.agent_groups)
        self.assertIn("历史删减边界", self.anti_overengineering)
        for removed_surface in (
            "多层数值评分与逐级否决路由",
            "项目保留层",
            "租约/推荐/停滞状态",
            "variation-plan/stage/verify",
            "晋升与退役恢复工作流",
            "插件项目交接生命周期",
        ):
            self.assertIn(removed_surface, self.anti_overengineering)
        self.assertIn("不得", self.anti_overengineering.split("## 历史删减边界", 1)[1].split("## 一、", 1)[0])
        self.assertNotIn("project-handoff.md", self.simplify_skill)

    def test_ablation_removes_paranoid_defense_by_evidence_not_fake_precision(self) -> None:
        compact_ablation = re.sub(r"\s+", "", self.ablation)
        for decision_axis in ("发生频率", "影响", "可检测性", "人工恢复"):
            self.assertIn(decision_axis, self.ablation)
        for boundary in (
            "用户举例中的数字只是比喻",
            "不写入插件规则、阈值或校准尺度",
            "当前正常路径",
            "反复出现的异常",
            "极少出现、只有孤立记录或仍只是理论可能",
            "没有频率证据时写 `unknown`",
            "不把模型担忧、任务形状或比喻换算成概率和档位",
            "明确失败",
            "有限巡检",
            "人工修复",
            "自动补偿或自愈",
            "安全、权限、数据完整性",
            "灾难性或不可逆",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact_ablation)
        for removed_scale in (
            "99 万 / 100 万",
            "10 万 / 100 万",
            "1–2 / 100 万",
            "频率校准",
            "给出的校准尺",
        ):
            self.assertNotIn(removed_scale, self.ablation + self.readme)

    def test_explicit_global_only_boundary_has_one_minimal_negative_guard(self) -> None:
        # The user explicitly prohibited project-scoped retained agents. This is a public
        # boundary, so a narrow absence guard is justified; hypothetical non-features do
        # not each get their own scaffold or test.
        for forbidden in ("project_scope", "project_id", "merge-global", "dual_write"):
            self.assertNotIn(forbidden, self.agents_source)
        self.assertIn("global_domain_key", self.agents_source)
        self.assertIn("migrate-global", self.agents_source)
        self.assertIn("只有四类负向限制值得最小测试", self.anti_overengineering)

    def test_versioning_preserves_one_version_update_and_external_authority(self) -> None:
        self.assertIn("只运行一次版本写入器", self.versioning)
        self.assertIn("完整旧版本", self.versioning)
        self.assertIn("只重装一次", self.versioning)
        for boundary in ("提交", "推送", "公开发布", "外部消息"):
            self.assertIn(boundary, self.versioning)

    def test_visible_plugin_name_is_consistent_without_renaming_stable_identifiers(self) -> None:
        visible_name = "Codex子代理调用与精简流程"
        self.assertEqual(self.manifest["interface"]["displayName"], visible_name)
        self.assertTrue(self.readme.startswith("# Codex Lean Stack\n"))
        self.assertIn(f"# {visible_name}\n", self.readme)
        self.assertIn(visible_name, self.flowcharts)
        self.assertIn("# Codex 子代理调用", self.skill)
        self.assertIn("# Codex 主任务精简", self.simplify_skill)
        for content in (
            self.readme,
            self.skill,
            self.simplify_skill,
            self.flowcharts,
            self.manifest["interface"]["displayName"],
            self.openai_yaml,
            self.simplify_openai_yaml,
        ):
            self.assertNotIn("精益任务栈", content)

        self.assertEqual(self.manifest["name"], "codex-lean-stack")
        self.assertIn("name: lean-stack", self.skill)
        self.assertIn("name: lean-simplify", self.simplify_skill)
        self.assertIn('display_name: "子代理调用"', self.openai_yaml)
        self.assertIn('display_name: "主任务精简"', self.simplify_openai_yaml)
        self.assertIn("$lean-stack", self.readme)
        self.assertIn("$lean-simplify", self.readme)
        self.assertIn("skills/lean-stack/", self.readme)
        self.assertIn("skills/lean-simplify/", self.readme)

    def test_public_entries_keep_simplification_and_delegation_independent(self) -> None:
        self.assertRegex(
            self.manifest["version"],
            r"^\d+\.\d+\.\d+\+codex\.[a-z0-9.-]+$",
        )
        calling_match = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"', self.openai_yaml, re.MULTILINE
        )
        simplify_match = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"',
            self.simplify_openai_yaml,
            re.MULTILINE,
        )
        self.assertIsNotNone(calling_match)
        self.assertIsNotNone(simplify_match)
        assert calling_match is not None
        assert simplify_match is not None
        calling_prompt = calling_match.group(1)
        simplify_prompt = simplify_match.group(1)
        self.assertNotEqual(calling_prompt, simplify_prompt)
        self.assertEqual(len(self.manifest["interface"]["defaultPrompt"]), 2)
        self.assertEqual(
            {
                path.parent.name
                for path in (ROOT / "skills").glob("*/SKILL.md")
            },
            {"lean-simplify", "lean-stack"},
        )
        for entry_prompt in (calling_prompt, simplify_prompt):
            self.assertIn(entry_prompt, self.manifest["interface"]["defaultPrompt"])
        for entry_term in (
            "$lean-stack",
            "不等待或阻断 $lean-simplify",
            "任务卡",
            "思考程度",
            "存活轮次",
            "经验五行实际值",
        ):
            self.assertIn(entry_term, calling_prompt)
        for entry_term in (
            "$lean-simplify",
            "非简单主任务",
            "最短完整路径",
            "不等待或阻断 $lean-stack",
        ):
            self.assertIn(entry_term, simplify_prompt)
        public_contract = (
            self.skill
            + self.simplify_skill
            + self.manifest["description"]
            + self.manifest["interface"]["shortDescription"]
            + "".join(self.manifest["interface"]["defaultPrompt"])
        )
        for forbidden in (
            "先用 $lean-simplify",
            "只有步骤需要模型或子代理时再用 $lean-stack",
            "已选定主任务必要步骤后",
            "先完整读取并使用相邻的",
        ):
            self.assertNotIn(forbidden, public_contract)
        self.assertIn("平行、独立且互不前置", self.skill)
        self.assertIn("任何一方都不等待、阻断或代证另一方", self.simplify_skill)
        self.assertIn("测试文件数、测试函数数", self.readme)

    def test_current_release_notes_match_manifest_and_visible_descriptions(self) -> None:
        base_version = self.manifest["version"].split("+", 1)[0]
        first_release = re.search(
            r"^## (?P<version>\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}$",
            self.changelog,
            re.MULTILINE,
        )
        self.assertIsNotNone(first_release)
        assert first_release is not None
        self.assertEqual(first_release.group("version"), base_version)
        self.assertIn(f"当前版本 {base_version}", self.readme)

        calling_short_match = re.search(
            r'^\s*short_description:\s*"([^"]+)"',
            self.openai_yaml,
            re.MULTILINE,
        )
        simplify_short_match = re.search(
            r'^\s*short_description:\s*"([^"]+)"',
            self.simplify_openai_yaml,
            re.MULTILINE,
        )
        self.assertIsNotNone(calling_short_match)
        self.assertIsNotNone(simplify_short_match)
        assert calling_short_match is not None
        assert simplify_short_match is not None
        self.assertIn("子代理", calling_short_match.group(1))
        self.assertIn("精简", simplify_short_match.group(1))

    def test_plugin_does_not_claim_global_user_file_edits(self) -> None:
        self.assertIn(
            "](skills/lean-stack/SKILL.md)",
            self.readme,
        )
        self.assertIn("Plain `codex plugin add` does not edit", self.readme)
        self.assertIn("普通 `codex plugin add` 不会修改", self.readme)
        self.assertIn("只有明确要求默认调用时才运行", self.readme)
        self.assertIn("没有用户当次授权时仍使用普通安装命令", self.versioning)
        self.assertNotIn("AGENTS.md", self.skill)
        self.assertNotIn("AGENTS.md", self.simplify_skill)
        self.assertNotIn("Jiao-Jie.md", self.skill)
        self.assertNotIn("Jiao-Jie.md", self.simplify_skill)

    def test_triggered_entry_loading_contract_is_statically_consistent(self) -> None:
        """Static text proves only the published trigger contract, not live host behavior."""
        combined = self.skill + self.simplify_skill + self.openai_yaml + self.simplify_openai_yaml
        compact = re.sub(r"\s+", "", combined).replace("`", "")
        calling_prompt = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"', self.openai_yaml, re.MULTILINE
        ).group(1)
        simplify_prompt = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"',
            self.simplify_openai_yaml,
            re.MULTILINE,
        ).group(1)
        self.assertLessEqual(
            len(calling_prompt) + len(simplify_prompt),
            800,
            "startup prompts must route to the skills instead of duplicating their manuals",
        )
        for required in (
            "非平凡主任务或可选准备将先于实际推进时读取",
            "首次准备调用 collaboration.spawn_agent",
            "用 followup_task 启动新子任务",
            "只读取并应用当前实际动作命中的入口",
            "已读且入口未变化时直接复用",
            "完整 `references`",
            "用途说明合并到唯一启动说明",
            "读取后的下一次工具调用立即开始实际任务",
            "两个并行技能入口",
            "平行、独立且互不前置",
            "同一任务可以随实际动作依次命中多个分支",
            "不能因拆分而跳过后继触发",
        ):
            self.assertIn(re.sub(r"\s+", "", required).replace("`", ""), compact)

        for rejected in (
            "同一次启动热路径",
            "只读两份 `SKILL.md`",
            "分别完整读取两份 SKILL.md",
            "两份入口各用独立完整输出",
        ):
            self.assertNotIn(re.sub(r"\s+", "", rejected), compact)

    def test_entries_decide_first_then_read_confirmed_branches_on_demand(self) -> None:
        """The entry is a durable decision surface, not a miniature manual or link dump."""
        for entry in (self.skill, self.simplify_skill):
            compact_entry = re.sub(r"\s+", "", entry)
            for required in (
                "入口先完成快速判断",
                "确认命中具体功能分支后",
                "未命中分支不读取",
                "不批量预读可能稍后使用的分支",
                "分支读取不再产生第二段技能用途说明",
                "读取后下一次工具调用执行该分支的实际操作",
            ):
                self.assertIn(re.sub(r"\s+", "", required), compact_entry)

        compact_calling = re.sub(r"\s+", "", self.skill)
        for preserved_decision in (
            "同一任务可以随实际动作依次命中多个分支",
            "不能预先成批加载",
            "不能因拆分而跳过后继触发",
            "未通过三项原则时继续主任务",
            "不查询`status--for-routing`或`recall`",
            "唯一来源所有者",
            "父代理不得并行重做该范围",
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
            "gpt-6-astra",
        ):
            self.assertIn(re.sub(r"\s+", "", preserved_decision), compact_calling)

        simplify_routes = self.simplify_skill.split("## 条件路由", 1)[1]
        self.assertNotIn("调查、缺陷修复、构建或审查", simplify_routes)
        for decision, reference in (
            ("查明未知事实、现状、调用链或原因", "investigation.md"),
            ("已有错误、失败或可复现症状", "bug-fix.md"),
            ("准备新增或修改实现", "build.md"),
            ("判断需求符合度、工程质量、风险或是否适合合并", "review.md"),
        ):
            matching_rows = [
                line
                for line in simplify_routes.splitlines()
                if reference in line
            ]
            self.assertEqual(len(matching_rows), 1)
            self.assertIn(decision, matching_rows[0])
            self.assertIn(reference, matching_rows[0])
            self.assertEqual(matching_rows[0].count("]("), 1)

        for entry in (self.skill, self.simplify_skill):
            route_intro = entry.split("## 条件路由", 1)[1].split("| 条件 |", 1)[0]
            self.assertIn("按当前状态和下一项实际动作判断", route_intro)
            self.assertIn("不按用户是否写出条件名称判断", route_intro)

        for entry in (self.skill, self.simplify_skill):
            route_table = entry.split("## 条件路由", 1)[1]
            for line in route_table.splitlines():
                if line.startswith("|") and "](" in line:
                    self.assertEqual(
                        line.count("]("),
                        1,
                        f"each decision row must select one branch: {line}",
                    )
            self.assertNotRegex(
                entry,
                r"\]\([^\n)]*execution-routing\.md\)",
                "large execution routing references must name the selected section",
            )
            self.assertNotRegex(
                entry,
                r"\]\([^\n)]*delegation\.md\)",
                "large delegation references must name the selected section",
            )

    def test_hot_path_and_compatibility_indexes_stay_bounded(self) -> None:
        """Progressive disclosure must reduce normal reads without hiding decisions."""
        byte_budgets = {
            SKILL_DIR / "SKILL.md": 16 * 1024,
            SIMPLIFY_SKILL_DIR / "SKILL.md": 10 * 1024,
            REFERENCES / "dispatch-start.md": 12 * 1024,
            REFERENCES / "source-results.md": 8 * 1024,
            REFERENCES / "agent-groups.md": 8 * 1024,
            REFERENCES / "agent-results.md": 8 * 1024,
            REFERENCES / "windows-exec.md": 8 * 1024,
            REFERENCES / "verification.md": 8 * 1024,
            REFERENCES / "execution-routing.md": 6 * 1024,
            REFERENCES / "delegation.md": 6 * 1024,
        }
        for path, maximum in byte_budgets.items():
            self.assertLessEqual(
                path.stat().st_size,
                maximum,
                f"hot-path or compatibility document grew past its budget: {path.name}",
            )

        self.assertIn("兼容", self.routing_index)
        self.assertIn("当前实际动作", self.routing_index)
        self.assertIn("唯一细则", self.routing_index)
        self.assertIn("兼容", self.delegation_index)
        self.assertIn("已确认动作", self.delegation_index)
        self.assertIn("直接读取", self.delegation_index)

        calling_prompt = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"', self.openai_yaml, re.MULTILINE
        )
        simplify_prompt = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"',
            self.simplify_openai_yaml,
            re.MULTILINE,
        )
        self.assertIsNotNone(calling_prompt)
        self.assertIsNotNone(simplify_prompt)
        assert calling_prompt is not None and simplify_prompt is not None
        self.assertLessEqual(len(calling_prompt.group(1)), 520)
        self.assertLessEqual(len(simplify_prompt.group(1)), 360)

    def test_one_dispatch_reads_all_and_only_its_hit_pre_dispatch_branches(self) -> None:
        """One call may need several branches; splitting must not erase interactions."""
        compact_dispatch = re.sub(r"\s+", "", self.dispatch_start)
        for required in (
            "当前这次调用同时命中来源所有权、可写并行、协作父代理或保留发现等派发前分支",
            "依次只读这些已命中分支",
            "未命中分支不读",
            "完成这些当前调用必需的步骤后",
            "下一次工具调用就是对应的`spawn_agent`或`followup_task`",
            "不取消调用后随来源、写入、汇合或保留动作产生的后继分支触发",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_dispatch)

        compact_public = re.sub(
            r"\s+",
            "",
            self.openai_yaml
            + self.manifest["interface"]["longDescription"]
            + "".join(self.manifest["interface"]["defaultPrompt"]),
        )
        for required in (
            "本次调用同时命中",
            "依次只读命中项",
            "后续动作仍可依次命中多个分支",
            "不因拆分跳过后继触发",
            "父子不重复完整读取同源或执行同一已分配职责",
            "父代理保留整合、共享热点和必要高风险定向核验",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_public)

        combined = self.calling_authority + self.readme
        compact_combined = re.sub(r"\s+", "", combined)
        for preserved_interaction in (
            "首次可写派发前保存一条当前任务专用的`WRITE_ROUTE`",
            "最多执行一次有界`status--for-routing`",
            "命中候选后才`recall`",
            "尽早派发全部分别通过三项原则且互不冲突的GPT-5.6切片",
            "调用数量随真实工作流和容量变化",
            "不设置同时调用数字",
            "不设置主任务累计调用数字",
            "任务卡只能传递当前用户已经明确给出的跨任务授权",
            "`create_thread`仍只在用户明确要求建立新任务时使用",
        ):
            self.assertIn(re.sub(r"\s+", "", preserved_interaction), compact_combined)

        for rejected in (
            "最多一个分支",
            "至多一个分支",
            "只能读取一个分支",
            "禁止配额式滥派",
            "父子范围不重叠",
            "任务卡授权由整合父代理按三项原则直接决定",
        ):
            self.assertNotIn(re.sub(r"\s+", "", rejected), compact_combined + compact_public)

    def test_runtime_acceptance_contract_keeps_formal_host_evidence_boundary(self) -> None:
        compact = re.sub(r"\s+", "", self.skill + self.simplify_skill + self.routing).replace(
            "`", ""
        )
        for required in (
            "静态合同",
            "不能证明新会话真实采用本路线",
            "正式安装后",
            "全新项目目录",
            "独立父代理任务",
            "真实subAgentActivity",
            "原生调用记录",
            "内部阻断只能说明验收未完成",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)

    def test_static_contract_requires_one_decisive_runtime_recheck(self) -> None:
        compact = re.sub(r"\s+", "", self.simplify_skill + self.readme)
        for required in (
            "同一根因的首次探针失败后先修根因",
            "再做一次决定性复验",
            "目标条件已经覆盖就停止",
            "不因措辞或模型档位变化连续新建验收会话",
            "决定性验收通过后的同类复验",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)

    def test_bounded_progress_does_not_replace_each_subagent_final_result(self) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.memory
            + self.write_parallelism
            + self.readme
            + self.flowcharts
        )
        for required in (
            "每个子代理",
            "自己的线程",
            "最终回复",
            "提交自己的精炼结果",
            "不由一个子代理汇总其他子代理",
            "不主动反复轮询",
            "统一收口确实依赖全部必要结果时才等待全部",
        ):
            self.assertIn(required, combined)
        for final_field in ("状态：完成 | 部分完成 | 受阻", "证据或缺口："):
            self.assertIn(final_field, self.agents_source)
        self.assertIn("不建立共享中转文件", self.agents_source)
        self.assertIn("最终回复", self.delegation)
        self.assertNotIn("交付父代理", self.chinese_docs)

    def test_windows_python_commands_force_utf8_for_chinese_skill_validation(self) -> None:
        combined = self.versioning + self.readme
        for required in ("py -3 -X utf8", "PYTHONUTF8=1", "GBK", "SKILL.md"):
            self.assertIn(required, combined)

    def test_all_relative_markdown_links_resolve(self) -> None:
        markdown_files = [
            ROOT / "README.md",
            SKILL_DIR / "SKILL.md",
            *REFERENCES.glob("*.md"),
        ]
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in markdown_files:
            text = markdown.read_text(encoding="utf-8")
            for target in pattern.findall(text):
                if re.match(r"^[a-z]+://", target) or target.startswith("#"):
                    continue
                clean = target.split("#", 1)[0]
                resolved = (markdown.parent / clean).resolve()
                self.assertTrue(resolved.exists(), f"missing link target: {markdown} -> {target}")


if __name__ == "__main__":
    unittest.main()
