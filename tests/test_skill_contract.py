from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "lean-stack"
REFERENCES = SKILL_DIR / "references"


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        cls.routing = (REFERENCES / "execution-routing.md").read_text(encoding="utf-8")
        cls.delegation = (REFERENCES / "delegation.md").read_text(encoding="utf-8")
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
        cls.handoff = (ROOT / "Jiao-Jie.md").read_text(encoding="utf-8")
        cls.build = (REFERENCES / "build.md").read_text(encoding="utf-8")
        cls.bug_fix = (REFERENCES / "bug-fix.md").read_text(encoding="utf-8")
        cls.investigation = (REFERENCES / "investigation.md").read_text(encoding="utf-8")
        cls.review = (REFERENCES / "review.md").read_text(encoding="utf-8")
        cls.long_running = (REFERENCES / "long-running.md").read_text(encoding="utf-8")
        cls.project_handoff = (REFERENCES / "project-handoff.md").read_text(
            encoding="utf-8"
        )
        cls.versioning = (REFERENCES / "versioning.md").read_text(encoding="utf-8")
        cls.openai_yaml = (SKILL_DIR / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        cls.manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        cls.chinese_docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "CHANGELOG.md",
                ROOT / "Jiao-Jie.md",
                SKILL_DIR / "SKILL.md",
                *REFERENCES.glob("*.md"),
            )
        )

    def test_entry_and_verification_nodes_are_distinct_in_main_flow(self) -> None:
        main = self.flowcharts.split("```mermaid", 1)[1].split("```", 1)[0]
        labels = (
            r"(\w+)\{新会话开始",
            r"(\w+)\[父代理只读 Jiao-Jie\.md 当前要求和重要片段",
            r"(\w+)\[修复真实发现并运行必要验证",
            r"(\w+)\{必要验证通过吗",
        )
        nodes = []
        for label in labels:
            match = re.search(label, main)
            self.assertIsNotNone(match, label)
            nodes.append(match.group(1))
        self.assertEqual(len(nodes), len(set(nodes)), "entry and validation nodes must not merge")

    def test_quality_floor_then_total_cost_priority_and_safety_remain(self) -> None:
        self.assertIn("高价值工作质量优先", self.skill)
        for content in (self.skill, self.routing, self.flowcharts):
            self.assertIn("总成本", content)
        for readme_term in ("必要质量", "成本相近", "总成本"):
            self.assertIn(readme_term, self.readme)
        for floor in ("安全", "权限", "数据完整性", "诚实证据"):
            self.assertIn(floor, self.skill + self.readme)
        for principle in (
            "高价值工作质量优先",
            "质量达标后总成本优先",
            "成本相近时再比速度",
        ):
            self.assertIn(principle, self.skill)
        self.assertNotIn("普通工作速度优先", self.skill)

    def test_quality_floor_allows_cost_first_then_speed_routing(self) -> None:
        for content in (self.skill, self.routing, self.readme, self.flowcharts):
            self.assertIn("总成本", content)
        self.assertIn("质量达标后：先比较", self.routing)
        self.assertIn("成本相近时：再比较总完成时间", self.routing)
        self.assertIn("父代理仍核对关键差异、接口和安全限制", self.routing)
        self.assertIn("用户要求全文或必要核验不受精简限制", self.delegation)
        main = self.flowcharts.split("```mermaid", 1)[1].split("```", 1)[0]
        decision = re.search(r"H\{([^}]+)\}", main)
        self.assertIsNotNone(decision)
        self.assertIn("预计达到必要质量且能替代父代理实际工作的", decision.group(1))
        self.assertIn("低成本 GPT-5.6 模型任务", decision.group(1))
        combined = self.skill + self.routing + self.readme + self.flowcharts
        for stale_priority in (
            "普通工作速度优先",
            "质量与总完成时间相当",
            "成本优势不覆盖前两项",
            "二者相当时总成本更低",
        ):
            self.assertNotIn(stale_priority, combined)

    def test_plugin_rule_is_mandatory_and_default_trigger_is_not_used(
        self,
    ) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.readme
            + self.handoff
            + self.flowcharts
        )
        for term in (
            "必须使用插件规则",
            "官方默认调用触发规则",
            "不等待用户重复",
            "一次正向判断",
            "立即调用",
            "都不是当前调用前置条件",
        ):
            self.assertIn(term, combined)
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
        for required in ("最早一个尚未完成", "尚未通过用户可见回复交付", "完成且已交付的要求立即退出"):
            self.assertIn(required, self.skill)
        self.assertIn("不建后台状态机", self.skill)

    def test_parent_gives_a_fast_first_explanation_then_keeps_working(self) -> None:
        combined = self.skill + self.routing + self.readme + self.handoff + self.flowcharts
        compact = re.sub(r"\s+", "", combined)
        for boundary in (
            "每条新用户要求",
            "首条快速说明",
            "当前理解",
            "立即动作",
            "必要限制",
            "不等待用户确认",
            "能够一次直接答完",
            "最终答案本身就是首条快速说明",
            "不额外发送重复前言",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact)
        main = self.flowcharts.split("## 一、主任务链路", 1)[1].split(
            "## 二、工具、子代理与安全并行链路", 1
        )[0]
        received = main.index("收到新消息")
        first_explanation = main.index("首条快速说明", received)
        main_chain = main.index("有未完成，或已完成", first_explanation)
        self.assertLess(received, first_explanation)
        self.assertLess(first_explanation, main_chain)

    def test_main_flow_is_primary_and_locates_every_auxiliary_entry(self) -> None:
        main = self.flowcharts.split("## 一、主任务链路", 1)[1].split(
            "## 二、工具、子代理与安全并行链路", 1
        )[0]
        group_close = main.index("本组当前已就绪结果已核验")
        unique = main.index("竞争并选出", group_close)
        retention = main.index("默认只尝试一次 ensure", unique)
        experience = main.index("一次 improve 合并追加一条经验", retention)
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
        for required in ("按“同一种活”确定任务类型组", "任务类型组确定前禁止复用或定制子代理", "定制运行时新子代理"):
            self.assertIn(required, self.delegation)
        self.assertIn("有则复用", self.skill)
        self.assertIn("运行时定制不等于持久创建", self.skill)

    def test_first_verified_reusable_group_can_persist_without_extending_runtime_threads(
        self,
    ) -> None:
        combined = self.skill + self.routing + self.delegation + self.memory + self.readme + self.handoff
        for required in (
            "第一次成功",
            "不要求重复",
            "不同任务类型组",
            "同时保留多个",
            "休眠",
            "进入 Done",
            "不持续调用模型",
            "只尝试一次",
            "父代理同时继续测试",
            "测试失败或用户否定",
            "丢弃候选",
            "默认",
            "明确排除项",
        ):
            self.assertIn(required, combined)

        group_flow = self.flowcharts.split(
            "## 五、任务类型组、复制、变体与保留子代理链路", 1
        )[1].split("## 六、调查与实现链路", 1)[0]
        final_reply = group_flow.index("最终回复顶部再次写实际配置")
        persisted = group_flow.index("默认只尝试一次 ensure", final_reply)
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
        self.assertIn("父代理先判定具体任务类型", self.skill)
        self.assertIn("任务类型组确定前禁止复用或定制子代理", self.routing)
        self.assertIn("不得选择具体配置", self.routing)

    def test_tools_are_used_before_model_subagents(self) -> None:
        for content in (self.skill, self.routing):
            self.assertIn("工具", content)
            self.assertIn("短命令", content)
            self.assertIn("后台", content)
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

        self.assertIn("复杂 PowerShell 转义", self.skill)
        for readme_term in (
            "复杂 PowerShell 及时落到脚本",
            "Move complex PowerShell into a script",
        ):
            self.assertIn(readme_term, self.readme)

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

    def test_sustained_multi_workflow_work_dispatches_all_qualifying_slices_early(self) -> None:
        """Protect qualitative early routing without introducing a mechanical quota."""
        detailed_authority = self.delegation
        for required in (
            "持续多工作流任务",
            "能替代父代理实际研究、实现或验收",
            "当前有收益且互不冲突的 GPT-5.6 切片分别编写任务卡并尽早派发",
            "调用数量随真实工作流、边际收益与运行容量变化",
            "不设最低数量",
            "各切片直接沿用维护后的模型价格",
            "直接取得正向总成本收益判定",
            "只在后期增加一次复核不能替代前面的实际工作",
            "新要求改变工作流时立即重新判断",
        ):
            self.assertIn(required, detailed_authority)

        for exception in (
            "属于确定性短工具工作",
            "多个互不依赖、已就绪",
            "严格依赖",
            "写入冲突无法隔离",
            "显著增费且没有必要质量收益",
        ):
            self.assertIn(exception, detailed_authority)

        for rejected_quota in (
            "同类长任务的早期双派发",
            "至少两个互不依赖",
            "早期至少启动两个",
            "所有任务至少派发两个子代理",
            "不顾成本和安全凑足两个",
        ):
            self.assertNotIn(rejected_quota, detailed_authority)

    def test_routing_rechecks_changed_work_and_requires_adoptable_results(self) -> None:
        """Keep re-routing, cost, expert escalation, and closeout behavior coupled."""
        routing_decision = self.routing.split("## 四、", 1)[0]
        early_dispatch = self.delegation.split("### 持续多工作流任务的早期派发", 1)[1].split(
            "###", 1
        )[0]
        direct_parent_cost = routing_decision.split("判断“不派发”时", 1)[1].split(
            "收益只需", 1
        )[0]
        total_cost = self.routing.split("总成本包含", 1)[1].split("\n\n", 1)[0]
        expert_route = self.delegation.split("当 Sol 本身担任父代理时", 1)[1].split(
            "### 持续多工作流任务的早期派发", 1
        )[0]
        closeout = self.delegation.split("每个子代理达到成功条件", 1)[1].split(
            "最终回复使用：", 1
        )[0]

        # A changed request re-opens the positive delegation judgment; it must not
        # preserve an earlier direct-parent decision after the work shape changes.
        self.assertIn("重新判断受影响的任务形状", routing_decision)
        self.assertIn(
            "新要求改变工作流时立即重新判断",
            re.sub(r"\s+", "", early_dispatch),
        )
        self.assertIn("全部当前有收益且互不冲突", early_dispatch)

        # Total cost includes the expensive parent's continued independent work,
        # rather than treating only child startup or a parent-token reduction as cost.
        compact_direct_parent_cost = re.sub(r"\s+", "", direct_parent_cost)
        for cost_part in ("父代理接下来独立承担", "上下文", "生成", "调试", "验证", "总成本"):
            self.assertIn(cost_part, compact_direct_parent_cost)
        for cost_part in ("token", "时间", "返工"):
            self.assertIn(cost_part, total_cost)
        self.assertNotIn("只算子代理启动成本", total_cost)

        # A bounded expert question can be sent directly; neither a cheap-model
        # failure nor a batch-wide escalation is a prerequisite.
        compact_expert_route = re.sub(r"\s+", "", expert_route)
        for expert_boundary in ("具体困难", "需要专家协助", "范围明确的子任务", "gpt-6-astra"):
            self.assertIn(expert_boundary, compact_expert_route)
        for forced_ladder in (
            "先让 Sol 或较低价模型实际失败",
            "只路由当前困难",
            "不升级已经通过的切片或无关批次",
            "更不批量升级",
        ):
            self.assertIn(re.sub(r"\s+", "", forced_ladder), compact_expert_route)

        # Progress commentary is not an adoptable result: adoption comes from a
        # child's final result/receipt, with one bounded retry per named gap.
        compact_closeout = re.sub(r"\s+", "", closeout)
        for closeout_boundary in (
            "commentary-only",
            "不能登记为已采用",
            "最终回复",
            "轻量结果收据",
            "同一来源快照和同一决定性缺口只发送一次范围明确的增量请求",
            "仍不足时直接补齐、如实报告缺口或等待新证据",
        ):
            self.assertIn(re.sub(r"\s+", "", closeout_boundary), compact_closeout)

        # Dispatch remains shaped by benefit and capacity, never by a preset count,
        # elapsed-time gate, or indiscriminate "send everything" rule.
        self.assertIn("调用数量随真实工作流、边际收益与运行容量变化", early_dispatch)
        self.assertIn(
            "不按固定时间、文件数量或轮次机械重判",
            re.sub(r"\s+", "", early_dispatch),
        )
        for mechanical_rule in ("固定委派数量", "固定时间阈值", "强制全部派发"):
            self.assertNotIn(mechanical_rule, self.skill + self.routing + self.delegation)

    def test_expensive_parent_defaults_to_low_cost_ready_slice_dispatch(self) -> None:
        """Use maintained price evidence to dispatch a qualified low-cost slice."""
        routing_decision = self.routing.split("## 四、", 1)[0]
        early_dispatch = self.delegation.split("### 持续多工作流任务的早期派发", 1)[1].split(
            "###", 1
        )[0]
        compact_decision = re.sub(r"\s+", "", routing_decision)

        # A low-cost GPT-5.6 slice that replaces expensive parent reasoning has a
        # positive benefit determination from the maintained price baseline and
        # both counterfactual routes.
        for required in (
            "昂贵父代理",
            "低成本GPT-5.6",
            "已就绪",
            "范围明确",
            "可安全独立",
            "持续模型判断",
            "替代父代理实际阅读、实现、诊断或验收",
            "维护后的模型价格/收益基线",
            "明显价差",
            "完整反事实路线",
            "正向收益判定",
            "总成本收益",
            "真实派发",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_decision)
        self.assertNotIn("收益不确定", routing_decision)

        # A new independent slice must be considered before the parent resumes
        # large work, while deterministic short tools and quotas remain excluded.
        for changed_shape in ("新要求", "具体困难", "上下文切换", "新的已就绪切片"):
            self.assertIn(changed_shape, routing_decision)
        self.assertIn("继续大规模读取、实现或长链诊断前", routing_decision)
        self.assertIn("多个合格", early_dispatch)
        self.assertIn("尽早派发", early_dispatch)
        self.assertIn("不设最低数量", early_dispatch)
        self.assertIn("确定性短工具", early_dispatch)

    def test_direct_parent_route_needs_concrete_blockers_and_two_full_cost_routes(self) -> None:
        """Keep direct handling evidence-based and compare both counterfactual routes."""
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
            "交接加增量核验明显超过切片",
        ):
            self.assertIn(re.sub(r"\s+", "", blocker), compact_decision)
        self.assertNotIn("只在明确质量、速度或总成本有收益时", compact_decision)
        self.assertNotIn("首次用户可见", routing_decision)

        # Compare the parent's complete independent route with the child route;
        # lower model price is evidence, not merely an uncounted child add-on.
        for parent_cost in ("父代理独立", "阅读", "生成", "上下文膨胀", "调试", "等待", "返工"):
            self.assertIn(re.sub(r"\s+", "", parent_cost), compact_decision)
        for child_cost in ("子代理输入输出", "整合", "增量核验"):
            self.assertIn(re.sub(r"\s+", "", child_cost), compact_decision)
        self.assertIn("模型价差", compact_decision)
        self.assertIn("合理推定依据", compact_decision)
        self.assertIn("不能只计子代理新增成本", compact_decision)

    def test_fresh_session_claim_requires_installed_isolated_behavioral_acceptance(self) -> None:
        """A hand-loaded candidate in this task is not evidence of a fresh session."""
        section = re.search(
            r"(?ms)^### 安装后新会话(?:行为|生效)验收\r?\n(.*?)(?=^### |\Z)",
            self.routing,
        )
        self.assertIsNotNone(section, "fresh-session acceptance needs its own authority")
        fresh_session = section.group(1)
        compact_fresh_session = re.sub(r"\s+", "", fresh_session).replace("`", "")
        entry = re.search(
            r"(?s)若要证明插件在安装后的新会话实际生效，.*?(?=\n本插件不承载)",
            self.skill,
        )
        self.assertIsNotNone(entry, "SKILL entry must retain fresh-session evidence boundary")
        compact_entry = re.sub(r"\s+", "", entry.group(0)).replace("`", "")

        # The claimed behavior must come from a new parent task in a separate
        # project after formal installation, using only its auto-loaded entry and
        # installed cache. Both the entry and the detailed authority must say so.
        for required in (
            "正式安装后",
            "新建独立父代理任务",
            "全新项目目录",
            "自动加载的全局入口",
            "正式安装缓存",
        ):
            compact_required = re.sub(r"\s+", "", required)
            self.assertIn(compact_required, compact_fresh_session)
            self.assertIn(compact_required, compact_entry)
        for forbidden in (
            "本项目Jiao-Jie",
            "当前会话摘要",
            "源码候选文本",
            "人工摘录策略",
            "当前会话手工加载候选文本",
        ):
            compact_forbidden = re.sub(r"\s+", "", forbidden)
            self.assertIn(compact_forbidden, compact_fresh_session)
            self.assertIn(compact_forbidden, compact_entry)
        for content in (compact_fresh_session, compact_entry):
            self.assertIn("不得读取", content)
            self.assertIn("不能宣称", content)
            self.assertIn("新会话生效", content)

        # The clean task must demonstrate the routing transition itself: direct
        # short deterministic work first, then real child activity and an
        # adoptable result when later requirements create independent model work.
        for required in (
            "短确定性工具",
            "父代理直接用工具且不委派",
            "新要求改变任务形状",
            "多个互不依赖",
            "需要持续模型判断",
            "真实subAgentActivity",
            "可采用结果",
            "硬阻断使测试未完成",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_fresh_session)
        self.assertNotIn("可核验具体阻断", compact_fresh_session)

        compact_versioning = re.sub(r"\s+", "", self.versioning).replace("`", "")
        for required in (
            "正式安装",
            "全新项目目录创建独立父代理任务",
            "自动加载的全局入口和正式安装缓存",
            "真实subAgentActivity",
            "至少一个可采用结果",
            "行为验收记为未完成",
            "不能用阻断说明",
            "不能为满足这条规则自行扩权",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact_versioning)

    def test_long_context_is_not_replicated_across_parent_child_or_nested_agents(self) -> None:
        detailed = self.skill + self.routing + self.delegation + self.cost
        compact_detailed = re.sub(r"\s+", "", detailed)
        compact_generated = re.sub(r"\s+", "", self.agents_source)
        for boundary in (
            "最小上下文原则沿代理树逐层适用",
            "Astra 对这些上下文读取、传播、结果复用和增量补缺规则没有例外",
            "`fork_turns=\"none\"` 的合适 GPT-5.6",
            "无法由有限摘录或来源快照保留",
            "长来源只筛选一次并沿代理树复用",
            "完整线程、完整工具输出、完整父历史或完整子树结果不得作为默认输入",
            "轻量结果收据",
            "已交付最终结果视为已经收取",
            "同一来源快照和同一决定性缺口只发送一次范围明确的增量请求",
            "不能以“再确认”“更全面”循环追问或完整重做",
            "必要的接口、安全、权限与数据完整性核验仍保留",
            "Astra 子任务同样只接收最小充分输入",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact_detailed)

        for generated_boundary in (
            "最小上下文原则沿代理树逐层适用",
            "Astra 没有例外",
            "fork_turns=none",
            "fork_turns=all",
            "轻量收据",
            "已交付最终结果不再等待",
            "重读或要求重发",
            "不循环追问",
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
            "只读角色",
            "范围放宽",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact)
        for rejected_narrowing in (
            "不同项目必须新建角色",
            "每个动作动词建立一个任务类型组",
            "成功条件不同就建立不同组",
        ):
            self.assertNotIn(rejected_narrowing, combined)
        compact_generated = re.sub(r"\s+", "", self.agents_source)
        for generated_boundary in (
            "同一可复用能力族",
            "项目、框架、动作动词、交付名称",
            "工具、写入权限、安全风险和决定性证据形状",
            "范围放宽不授予只读角色写权限",
        ):
            self.assertIn(re.sub(r"\s+", "", generated_boundary), compact_generated)

    def test_context_reset_reads_only_handoff_requirements_and_one_skill_entry(self) -> None:
        combined = self.skill + self.routing + self.handoff + self.project_handoff
        compact_combined = re.sub(r"\s+", "", combined)
        for boundary in (
            "只读当前用户要求",
            "会改变当前下一动作的重要片段",
            "最新快照",
            "最早活动项",
            "最后可信状态",
            "相关稳定决定",
            "来源定位",
            "授权范围",
            "只读取一次本 `SKILL.md` 入口",
            "实际调用子代理时不得再为“调用插件”重读一次",
            "不重读已交付历史",
            "只有重要片段标明缺口、冲突或来源变化时",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact_combined)
        self.assertNotIn("工作上下文重置后（包括压缩或切换上下文窗口）实际完整重读", combined)

    def test_runtime_capacity_replaces_plugin_numeric_caps(self) -> None:
        combined = self.skill + self.routing + self.delegation + self.readme
        self.assertIn("不另外设置插件调用次数限制", self.skill)
        self.assertIn("不设置同时调用数字", self.routing)
        self.assertIn("不设置主任务累计调用数字", combined)
        self.assertIn("容量是上限，不是调用目标", combined)
        self.assertIn("实际可用的全部并发槽位", combined)
        self.assertIn("容量不是调用目标", combined)
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
        self.assertIn("每个任务", self.skill)
        self.assertIn("不逐任务联网查价", self.skill)
        self.assertIn("不要求父代理在运行时重新计算令牌", self.cost)
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertIn(model, self.cost)
        self.assertIn("只升级或重做该子任务", self.cost)
        self.assertNotIn("父代理的默认比较基线", self.cost)
        self.assertNotIn("推理强度：max", self.cost)
        self.assertIn("标准速度", self.cost)

    def test_low_cost_models_are_the_positive_route_for_ordinary_parallel_work(self) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.cost
            + self.readme
            + self.handoff
            + self.flowcharts
        )
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertIn(model, combined)
        for boundary in (
            "范围清楚",
            "多个独立普通子任务",
            "更倾向",
            "第二个及后续调用",
            "只升级",
            "标准速度",
            "关键路径",
            "不是永久白名单",
        ):
            self.assertIn(boundary, combined)

    def test_sol_parent_can_call_astra_for_expert_and_visual_judgment(self) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.cost
            + self.readme
            + self.flowcharts
        )
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "Sol为父代理",
            "需要专家协助",
            "UI设计",
            "图片",
            "三维建模",
            "渲染",
            "视觉效果",
            "范围明确的子任务",
            "主要判断",
            "最终评审或验收核对只是辅助",
            "不是前置门槛",
            "视觉任务本身",
            "不要求先",
            "不升级整批",
        ):
            self.assertIn(required, compact)
        self.assertIn("gpt-5.6-sol", combined)
        self.assertIn("gpt-6-astra", combined)
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
        self.assertIn("`instance` 译为“子任务”", self.skill)

    def test_copy_subtasks_and_variant_semantics_are_unambiguous(self) -> None:
        combined = self.skill + self.delegation + self.flowcharts
        self.assertIn("复制的是任务类型组里的子代理", self.delegation)
        self.assertIn("复制的是任务类型组里的子代理，不是任务类型组", self.delegation)
        self.assertIn("第二个同一任务类型的子任务", self.delegation)
        self.assertIn("第三个同一任务类型的子任务", self.delegation)
        self.assertIn("复制前确认改进空间", combined)
        self.assertIn("确有进步空间", combined)
        self.assertIn("父代理根据", combined)
        self.assertIn("完整可行的替代方案", self.delegation)
        compact_delegation = re.sub(r"\s+", "", self.delegation)
        self.assertIn(
            "模型、思考程度和速度是互相制约的联合配置",
            compact_delegation,
        )
        self.assertIn("可以同时变化", self.delegation)
        self.assertIn("单轴变化只在明确需要识别因果时", self.delegation)
        self.assertNotIn("不能一次改变多个轴", self.delegation)
        self.assertIn("在自己的线程用最终回复提交自己的精炼结果", combined)
        self.assertIn("不由子代理预先合并", combined)
        self.assertIn("父代理为每个子任务分别", combined)
        self.assertIn("一个子代理", combined)
        self.assertIn("合并一条", combined)
        self.assertIn("不兼容时才拆分", combined)
        self.assertNotIn("复制用于同一种活", combined)
        self.assertNotIn("只采用最佳结果", combined)
        self.assertNotIn("同一种活并使用同一成功条件", combined)
        self.assertNotIn("复制这个已有组", combined)
        self.assertNotIn("合并所有通过核验", combined)

        closeout = self.delegation.split("### 竞争收口", 1)[1].split(
            "### 保留与安全重配", 1
        )[0]
        unique = closeout.index("确定它是组内唯一留下的子代理")
        experience = closeout.index("默认把胜出方法", unique)
        removal = closeout.index("移出组、结束并从运行时候选中消除", experience)
        self.assertLess(unique, experience)
        self.assertLess(experience, removal)
        self.assertIn("没有复制或变体的任务类型组不竞争", closeout)
        compact_closeout = re.sub(r"\s+", "", closeout)
        self.assertIn("也对原本唯一子代理执行相同的跨任务保留与经验判断", compact_closeout)

    def test_model_effort_and_speed_are_jointly_selected_for_each_task_type(
        self,
    ) -> None:
        joint_documents = {
            "skill": self.skill,
            "delegation": self.delegation,
            "routing": self.routing,
            "cost": self.cost,
            "collaboration": self.collaboration,
            "write_parallelism": self.write_parallelism,
            "memory": self.memory,
            "readme": self.readme,
            "handoff": self.handoff,
            "flowcharts": self.flowcharts,
            "generated_prompt": self.agents_source,
        }
        for name, content in joint_documents.items():
            with self.subTest(document=name):
                self.assertIn("模型", content)
                self.assertIn("思考程度", content)
                self.assertIn("速度", content)
                self.assertIn("联合", content)
                self.assertIn("任务类型", content)

        combined = "\n".join(joint_documents.values())
        for required in (
            "完整配置",
            "可以因相互制约而同时变化",
            "单轴变化只在明确需要识别因果时",
            "不能取代联合选配",
        ):
            self.assertIn(required, combined)
        for removed_hard_rule in (
            "父代理只选择一个改变轴",
            "父代理才选择一个改变轴形成变体",
            "不能一次改变多个轴",
        ):
            self.assertNotIn(removed_hard_rule, combined)

        # Candidate selection must not regress into a one-axis experiment recipe.
        self.assertIn("允许三个字段同时变化", self.cost)
        self.assertIn("普通配置选择不强制实验或穷举", self.cost)
        self.assertNotIn("缺推理深度才提高档位，能力不足才换模型", self.cost)

    def test_cross_project_reuse_discovery_and_handoff_receipt_are_actionable(self) -> None:
        for content in (self.skill, self.memory):
            compact = re.sub(r"\s+", "", content)
            self.assertIn("status--for-routing", compact)
            self.assertIn("绝对目录", content)
        self.assertIn("recall --name", self.memory)
        self.assertIn("必要经验", self.memory)
        self.assertIn("不例行遍历台账", self.skill)
        self.assertIn("临时调用不记作原保留身份的成功运行", self.memory)
        self.assertIn("不以“已调用”或过程记录代替结果", self.skill)
        self.assertIn("只读当前用户要求", self.skill)
        self.assertIn("插件规则只读取一次本 `SKILL.md` 入口", self.skill)
        self.assertIn("实际调用子代理时不得再为“调用插件”重读一次", self.skill)
        self.assertIn("不为补通知重复读取", self.skill)
        self.assertNotIn("实际完整重读", self.skill)

    def test_retention_and_experience_are_default_nonblocking_side_chain(self) -> None:
        combined = (
            self.skill
            + self.memory
            + self.delegation
            + self.readme
            + self.flowcharts
        )
        self.assertIn("专门代理记忆就是经验", combined)
        self.assertIn("不是提交前置条件", self.skill)
        self.assertIn("立即跳过", combined)
        self.assertIn("主任务不依赖任何持久写入成功", self.memory)
        self.assertIn("SQLite", combined)
        self.assertIn("原始经验", self.memory)
        self.assertIn("经验摘要压缩", combined)
        self.assertIn("不删除原始经验", combined)
        compact = re.sub(r"\s+", "", combined)
        for boundary in (
            "结果通过必要核验并被父代理采用",
            "默认各尝试一次 `ensure` 和 `improve`",
            "不要求主任务接近结束",
            "稳定 `event_id`",
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

    def test_explicit_exclusions_are_the_only_default_persistence_skip_reasons(self) -> None:
        combined = (
            self.skill
            + self.memory
            + self.delegation
            + self.routing
            + self.readme
            + self.handoff
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
        for summary in (self.skill, self.flowcharts, self.readme, self.handoff):
            self.assertIn("全局领域", summary)
        combined = self.skill + self.memory + self.delegation + self.routing
        self.assertIn("默认只尝试一次 `improve`", combined)
        self.assertIn("稳定 `event_id`", combined)
        self.assertIn("保存回执", combined)
        self.assertNotIn("只有主任务已经大致完成、接近结束", combined)
        self.assertNotIn("角色可泛化且有未来用途", combined)

    def test_copy_variant_winner_and_transfer_drive_sqlite_without_candidate_state(self) -> None:
        combined = self.skill + self.memory + self.delegation
        self.assertIn("复制和变体本身不写入 SQLite", combined)
        self.assertIn("在自己的线程用最终回复", self.memory)
        self.assertIn("父代理才根据任务类型联合选择完整的模型", self.memory)
        self.assertIn("三个字段可以因相互制约而同时变化", self.memory)
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
            + self.handoff
        )
        for required in (
            "立即停止该子代理",
            "移出任务类型组",
            "不采用、不合并、不引用",
            "不写入经验",
            "从最后可信状态重做",
            "独立检出目录直接丢弃",
            "不能整树回退",
        ):
            self.assertIn(required, combined)
        self.assertIn("git reset --hard", self.write_parallelism)
        self.assertIn("禁止", self.write_parallelism)

    def test_no_numeric_scoring_or_fixed_lifecycle_contract(self) -> None:
        combined = self.skill + self.delegation + self.memory + self.readme
        self.assertIn("不做评分表", self.skill)
        self.assertIn("不是固定顺序、固定数量或固定生命周期", self.memory)
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

    def test_semantic_review_is_conditional_not_a_universal_main_chain(self) -> None:
        self.assertIn("只验证当前改动、公共约定和风险可能影响的对象", self.skill)
        self.assertIn("只重跑受影响检查", self.routing)
        self.assertIn("Run only affected checks", self.readme)
        self.assertIn("测试只覆盖受影响范围", self.readme)

    def test_parent_parallelism_permissions_and_source_coverage_remain(self) -> None:
        combined = self.skill + self.delegation + self.write_parallelism + self.readme
        self.assertIn("父代理立即推进", combined)
        self.assertIn("多个可写子代理可以并行", combined)
        self.assertNotIn("一个写入者", combined)
        self.assertIn("这不是“单写入者”规则", self.write_parallelism)
        self.assertIn("不重叠写入范围", combined)
        self.assertIn("独立检出目录", combined)
        self.assertIn("其他候选只返回方案、补丁或证据", combined)
        self.assertIn("共同热点", combined)
        for retained_absence in ("认领数据库", "心跳", "后台协调器"):
            self.assertIn(retained_absence, combined)
        self.assertIn("委派不增加权限", self.skill)
        self.assertIn("SOURCE_COVERAGE", combined)
        self.assertIn("完整覆盖且来源未变化", self.review)

    def test_coordination_parents_and_parent_tasks_use_bounded_standing_authority(
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
            "协作角色: 协作父代理",
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
            "当前用户已为本插件建立持续协作授权",
            "不再重复询问",
            "未获明确要求的永久删除",
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
            "复用可见保留子代理时由它自读已有配置",
            "运行时新子代理",
            "具体模型、思考程度和标准或快速速度",
            "具体模型、思考程度和标准或快速速度",
        ):
            self.assertIn(concrete_config_boundary, combined)

        self.assertIn(
            "只有新父代理任务能带来必要质量或质量达标后的总成本收益时才调用 `create_thread`",
            self.collaboration,
        )
        self.assertIn("只有任务卡明确写", self.agents_source)
        self.assertIn(
            "允许调用其他或新建 Codex 父代理为是并给出跨任务范围",
            self.agents_source,
        )
        generated_prompt = re.sub(r'"\s*"', "", self.agents_source)
        generated_prompt = re.sub(r"\s+", "", generated_prompt)
        self.assertIn(
            "create_thread、read_thread、wait_threads或send_message_to_thread",
            generated_prompt,
        )
        self.assertIn("工具缺失、", self.agents_source)
        self.assertIn(
            "直接调用失败、容量不足、范围不清或写入无法隔离时",
            self.agents_source,
        )
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
            + self.handoff
        )
        for required in (
            "普通文件进入 Windows 回收站",
            "重要文件进入任务或插件专属 `待删文件`",
            "累计第二次明确失败",
            "永久移除",
            "身份",
            "运行记录",
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
        self.assertIn("委派不增加权限", self.skill)
        self.assertIn("持续实现、调试与等待中", self.skill)
        self.assertIn(
            "](skills/lean-stack/references/delegation.md)",
            self.readme,
        )
        self.assertIn("只有中间结果会解锁下一动作时才报告一次并继续", self.readme)

    def test_retained_self_reads_and_declares_while_parent_configures_new_or_variant(self) -> None:
        combined = self.skill + self.delegation + self.readme + self.handoff + self.collaboration
        for required in (
            "父代理",
            "具体模型",
            "思考程度",
            "标准或快速",
            "开场声明",
            "自己的配置",
            "自行声明",
            "定制运行时新子代理",
            "联合选择",
            "完整配置",
        ):
            self.assertIn(required, combined)
        self.assertNotIn("未提供的字段完全省略", combined)
        self.assertNotIn("只有父代理明确指定并知道精确值时", combined)
        self.assertNotIn("未暴露（继承父级）", combined)
        responsibility_docs = combined + self.cost
        self.assertIn("父代理不重复注入经验", self.delegation)
        self.assertIn("不强制重写已有配置", self.delegation)
        self.assertIn("复用保留子代理及普通复制时沿用其已有具体配置", self.cost)
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

    def test_configuration_declarations_use_real_channels_without_order_gate(
        self,
    ) -> None:
        combined = "\n".join((self.skill, self.delegation, self.collaboration, self.agents_source))
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "父代理规范任务名",
            "collaboration.send_message",
            "spawn_agent",
            "followup_task",
            "完整四行",
            "自己的任务界面",
            "commentary",
            "公开完整四行",
            "最终回复顶部",
            "实际模型、思考程度和速度",
            "不计入关键步骤",
            "不设固定先后顺序",
            "reasoning",
        ):
            self.assertIn(re.sub(r"\s+", "", required), compact)

        for obsolete_order_contract in (
            "声明作为第一动作",
            "第一动作通过内部",
            "第二动作在自己的任务界面",
            "第二动作必须",
            "公开后才开始",
            "声明必须先于",
            "第一条可见commentary",
        ):
            self.assertNotIn(re.sub(r"\s+", "", obsolete_order_contract), compact)

        for boundary in (
            "send_message_to_thread",
            "跨任务操作冒充内部消息",
            "工具缺失或直接调用失败",
            "自包含任务可继续",
            "实际能力仍以真实调用为准",
        ):
            self.assertIn(boundary, self.delegation + self.agents_source)

        for boundary in (
            "只有真实依赖解锁、必要纠偏、风险或阻断才使用内部消息",
            "不为证明工具存在发送探针",
        ):
            self.assertIn(boundary, self.agents_source)
        self.assertNotIn("向父代理发送以下四行", self.agents_source)
        detailed_declaration_docs = combined + self.routing
        for stale_internal_copy in (
            "子代理在当前子任务中通过内部消息发送完整四行",
            "发送完整四行声明",
            "成功路线必须同时存在父代理收到的内部副本",
        ):
            self.assertNotIn(stale_internal_copy, detailed_declaration_docs)
        self.assertNotIn("完整四行", self.handoff)

        final_template = self.delegation.split("最终回复使用：", 1)[1]
        for field in ("模型：<具体模型>", "速度：<标准或快速>"):
            self.assertLess(final_template.index(field), final_template.index("子任务：<当前子任务>"))

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
        self.assertNotIn("def memory_budget", script)
        self.assertIn("def _render_agent_bytes", script)
        self.assertIn("fits: Callable[[str], bool]", script)
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
            "完整提示不再有独立的 6 KiB 硬门槛",
            "经验窗口最多 4 KiB",
            "完整角色文件不超过 16 KiB",
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
        self.assertIn("全部不使用", self.memory)

    def test_playbooks_keep_real_task_and_permission_boundaries(self) -> None:
        self.assertIn("证明根因", self.bug_fix)
        self.assertIn("真实表面", self.bug_fix)
        self.assertIn("最小完整切片", self.build)
        self.assertIn("对外约定", self.build)
        self.assertIn("anti-overengineering.md", self.build)
        self.assertIn("只读", self.investigation + self.review)
        self.assertIn("来源覆盖完整", self.investigation)
        self.assertIn("停止条件", self.long_running)
        self.assertIn("不授权部署", self.long_running)

    def test_anti_overengineering_uses_evidence_and_one_authoritative_surface(self) -> None:
        for content in (self.skill, self.build, self.routing, self.readme):
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
        ):
            self.assertIn(required, self.anti_overengineering)
        self.assertIn("只有四类负向限制值得最小测试", self.anti_overengineering)
        self.assertIn("只更新会作出错误承诺的表面", self.flowcharts)
        self.assertIn("不留桩、注释或假想测试", self.flowcharts)

    def test_ablation_is_an_explicit_independent_feedback_loop(self) -> None:
        compact_ablation = re.sub(r"\s+", "", self.ablation)
        for content in (
            self.skill,
            self.anti_overengineering,
            self.build,
            self.routing,
            self.readme,
        ):
            self.assertIn("ablation-loop.md", content)
        for trigger in (
            "进行消融实验",
            "精简代码",
            "精简设计",
            "去掉不必要抽象",
        ):
            self.assertIn(trigger, self.skill + self.ablation)
        for boundary in (
            "只有用户明确要求",
            "不含原作者推理历史",
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
        self.assertIn("不例行", self.routing)

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
            self.assertNotIn(removed_scale, self.ablation + self.readme + self.handoff)

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
        self.assertTrue(self.readme.startswith(f"# {visible_name}\n"))
        self.assertIn(f"# {visible_name}", self.skill)
        self.assertIn(visible_name, self.flowcharts)
        for content in (self.readme, self.skill, self.flowcharts, self.manifest["interface"]["displayName"]):
            self.assertNotIn("精益任务栈", content)

        self.assertEqual(self.manifest["name"], "codex-lean-stack")
        self.assertIn("name: lean-stack", self.skill)
        self.assertIn("$lean-stack", self.readme)
        self.assertIn("skills/lean-stack/", self.readme)

    def test_manifest_and_ui_are_synchronized_without_old_caps(self) -> None:
        self.assertRegex(
            self.manifest["version"],
            r"^\d+\.\d+\.\d+\+codex\.[a-z0-9.-]+$",
        )
        combined = " ".join(
            [
                self.manifest["description"],
                self.manifest["interface"]["shortDescription"],
                self.manifest["interface"]["longDescription"],
                *self.manifest["interface"]["defaultPrompt"],
            ]
        )
        for term in (
            "高价值",
            "普通工作",
            "质量",
            "速度",
            "任务类型",
            "现实消费者",
            "兼容",
            "全局领域",
        ):
            self.assertIn(term, combined)
        self.assertNotIn("零至三个", combined)
        match = re.search(
            r'^\s*default_prompt:\s*"([^"]+)"', self.openai_yaml, re.MULTILINE
        )
        self.assertIsNotNone(match)
        assert match is not None
        default_prompt = match.group(1)
        self.assertEqual(default_prompt, self.manifest["interface"]["defaultPrompt"][0])
        self.assertLessEqual(len(default_prompt), 128)
        for entry_term in (
            "$lean-stack",
            "按任务类型联合选模型/思考/速度与工具/代理",
            "按三原则协调下游和跨任务父代理",
            "唯一整合父代理收口",
            "先证据后回迁",
            "只维护真实兼容与必要表面",
            "无未授权永久删除",
            "不重复询问",
        ):
            self.assertIn(entry_term, default_prompt)
        full_contract = (
            combined
            + self.skill
            + self.routing
            + self.delegation
            + self.memory
        )
        for contract_term in (
            "未完成要求锚点",
            "只重新打开真正受影响",
            "为每个子任务分别指定",
            "父代理规范任务名",
            "自定义角色 TOML",
            "ALL_TOOLS",
            "跨任务 API",
            "全局领域规则",
            "在自己的线程用最终回复",
            "存活轮次",
        ):
            self.assertIn(contract_term, full_contract)
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertIn(model, full_contract)
        self.assertNotIn("实" + "例", full_contract)

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

        descriptions = " ".join(
            (
                self.manifest["description"],
                self.manifest["interface"]["shortDescription"],
                self.manifest["interface"]["longDescription"],
            )
        )
        self.assertIn(f"当前版本 {base_version}", descriptions)

        next_release = self.changelog.find("\n## ", first_release.end())
        current_notes = self.changelog[
            first_release.end() : next_release if next_release >= 0 else None
        ]
        visible_summary = self.readme + descriptions + current_notes
        for behavior_term in (
            "低成本 GPT-5.6",
            "模型价差",
            "正向总成本",
            "内部硬条件",
            "独立父任务",
            "真实",
            "可采用结果",
        ):
            self.assertIn(behavior_term, visible_summary)

        short_match = re.search(
            r'^\s*short_description:\s*"([^"]+)"',
            self.openai_yaml,
            re.MULTILINE,
        )
        self.assertIsNotNone(short_match)
        assert short_match is not None
        self.assertEqual(
            short_match.group(1),
            self.manifest["interface"]["shortDescription"],
        )

        for required_surface in (
            "CHANGELOG.md",
            "README.md",
            "description",
            "interface.shortDescription",
            "interface.longDescription",
            "新增或改变的用户可见行为",
        ):
            self.assertIn(required_surface, self.versioning)
        for flow_step in (
            "同步 README、CHANGELOG 和插件说明",
            "核对说明中的当前版本与 manifest 一致",
        ):
            self.assertIn(flow_step, self.flowcharts)

    def test_flowcharts_are_auxiliary_and_not_frozen_to_a_count(self) -> None:
        self.assertGreaterEqual(self.flowcharts.count("```mermaid"), 4)
        self.assertIn("只是代码和规则的辅助说明", self.flowcharts)
        self.assertNotRegex(self.readme, r"全部[一二三四五六七八九十百\d]+张")
        self.assertNotIn("八张", self.flowcharts + self.readme)
        self.assertNotIn("十四张", self.flowcharts + self.readme)

    def test_requested_flowcharts_are_merged_without_dropping_their_boundaries(
        self,
    ) -> None:
        headings = set(re.findall(r"(?m)^##\s+([^\r\n]+)$", self.flowcharts))
        for merged in (
            "二、工具、子代理与安全并行链路",
            "五、任务类型组、复制、变体与保留子代理链路",
            "十二、任务类型组收口、精确删除与否定重做链路",
        ):
            self.assertIn(merged, headings)
        for removed in (
            "二、工具与子代理选择链路",
            "五、父代理与子代理并行链路",
            "六、任务类型组、复制与变体链路",
            "七、多个可写子代理防覆盖链路",
            "十二、保留子代理创建与安全重配链路",
            "十五、任务类型组清理与精确删除链路",
            "十六、用户不满意时立即移除与重做链路",
        ):
            self.assertNotIn(removed, headings)
        for retained_boundary in (
            "多个可写子代理可以并行",
            "最近的协作授权不改变删除、删减或候选清理尺度",
            "精确送入 Windows 回收站",
            "永久删除 TOML 与身份行",
            "定制运行时新子代理不等于持久创建",
            "父代理按任务类型联合选择",
            "保留子代理读取自己的",
            "复制任务类型组里的基准子代理",
            "每个子代理在自己的线程",
            "提交自己的精炼结果",
            "选出同一任务类型组",
            "结束位置执行同一经验维护判断",
            "其他子代理移出组、结束",
            "用当前哈希比较并交换",
            "结果核验采用",
            "保存回执",
            "稳定 event_id",
        ):
            self.assertIn(
                re.sub(r"\s+", "", retained_boundary),
                re.sub(r"\s+", "", self.flowcharts),
            )

    def test_diagram_rendering_is_owned_by_architecture_viewer(self) -> None:
        combined = self.skill + self.readme + self.flowcharts + self.handoff
        blocks = re.findall(
            r"(?ms)^##\s+([^\r\n]+)\r?\n+```mermaid\r?\n(.*?)\r?\n```",
            self.flowcharts,
        )
        self.assertEqual(len(blocks), 13)
        for term in (
            "architecture-viewer",
            "$architecture-viewer",
            "$archify",
            "13 条 Mermaid",
            "Viewer Runtime",
            "路径",
            "透镜",
            "故事",
            "导出",
            "loopback",
            "zh-CN",
        ):
            self.assertIn(term, combined)
        self.assertFalse((SKILL_DIR / "scripts" / "render_flowcharts.mjs").exists())
        self.assertFalse((REFERENCES / "flowcharts-zh.page.json").exists())
        self.assertFalse((REFERENCES / "flowcharts-zh.html").exists())
        self.assertEqual(
            list((REFERENCES / "flowcharts-zh-assets").glob("diagram-*.svg")), []
        )
        for stale_route in (
            "已验证带内部通道的路线",
            "承载路线复用同一保留身份",
            "[features] multi_agent = true",
            "[agents] enabled = true",
        ):
            self.assertNotIn(stale_route, self.skill + self.routing + self.delegation + self.flowcharts + self.handoff)

    def test_handoff_contains_only_the_current_drift_guards(self) -> None:
        compact_handoff = re.sub(r"\s+", "", self.handoff)
        for term in (
            "只有全局领域保留，没有项目保留层",
            "跨任务、跨项目、跨会话",
            "每个全局领域任务类型组各保留一个休眠配置",
            "模型+思考程度+速度",
            "migrate-global",
            "来源词只用于",
            "不写入SQLite、TOML、规则或完成收据",
            "anti-overengineering.md",
            "现实消费者",
            "已经决定不实现的假想功能",
            "第二事实源",
            "schema v5",
            "agents.py status",
            "只追加原始经验和纠正事件",
            "经验数量不封顶",
            "经验摘要压缩",
            "这不是单写入者规则",
            "不设置同时调用数字",
            "不在每个任务重新搜索费率",
            "链路图只是辅助说明",
            "未完成要求锚点",
            "此前已经交付的完成项不重复总结",
            "Windows回收站",
            "待删文件",
        ):
            self.assertIn(re.sub(r"\s+", "", term), compact_handoff)
        self.assertNotIn("schema仍为v3", compact_handoff)
        self.assertNotIn("当前插件正式保留子代理总数", compact_handoff)
        self.assertNotIn("当前SHA-256", compact_handoff)
        default_line = (
            "默认调用已安装的 `codex-lean-stack` 插件；"
            "是否启动子代理仍由插件自身规则决定。"
        )
        for document in (self.versioning, self.installer):
            self.assertIn(default_line, document)
        self.assertIn("普通 `codex plugin add` 不会修改全局 `AGENTS.md`", self.readme)
        self.assertIn("通用项目交接规则", self.handoff)
        self.assertIn("未经用户当次明确同意", self.handoff)
        self.assertIn("不能复制插件的子代理加速规则", self.handoff)
        self.assertIn("正式安装成功后才幂等确保", self.handoff)
        self.assertIn("新会话开始或工作上下文重置后", self.handoff)
        self.assertIn("子代理摘要或读取不能替代父代理这次按限定范围恢复", self.handoff)
        self.assertIn("会改变下一动作的重要片段", self.handoff)
        self.assertIn("实际调用子代理不重复读取入口或未变细则", self.handoff)
        self.assertIn("普通后续轮次复用", self.handoff)
        self.assertIn("每轮项目迭代", self.handoff)
        self.assertIn("收口前更新本文件", self.handoff)
        self.assertIn("Jiao-Jie.md", self.skill + self.readme + self.flowcharts)
        self.assertNotIn("PROJECT-HANDOFF", self.chinese_docs)

    def test_handoff_keeps_stable_rules_before_per_round_state(self) -> None:
        headings = re.findall(r"(?m)^##\s+([^\r\n]+)$", self.handoff)
        self.assertGreater(len(headings), 0)
        self.assertEqual(headings[0], "根本准则")
        ordered = (
            "根本准则",
            "项目级父代理跨会话记忆",
            "用户全局文件的修改范围",
            "未完成要求锚点与当前交付",
            "任务类型与任务类型组",
            "主任务链与辅助链入口",
            "工具、子代理与调用规则",
            "子代理开场声明与范围明确的交流",
            "任务类型组、复制、变体与收口",
            "写入安全与用户不满意",
            "反 AI 过度工程",
            "条件性验证",
            "经验、SQLite、成本与生命周期侧链",
            "统一术语",
            "权威路径与代码修改范围",
            "运行环境状态快照",
            "本轮实际变化",
            "本轮验证证据",
            "工作树与剩余事项",
            "后续代理开始方式",
        )
        indexes = [headings.index(heading) for heading in ordered]
        self.assertEqual(indexes, sorted(indexes))
        dynamic = headings.index("运行环境状态快照")
        self.assertGreater(dynamic, headings.index("权威路径与代码修改范围"))
        for heading in ("本轮实际变化", "本轮验证证据", "工作树与剩余事项"):
            self.assertGreater(headings.index(heading), dynamic)
            self.assertEqual(headings.count(heading), 1)
        self.assertIn("以下部分是每轮都会变化的状态", self.handoff)

    def test_subagent_acceleration_stays_in_the_plugin_not_global_agents(self) -> None:
        combined = self.skill + self.readme
        self.assertIn("详细子代理规则由本插件维护", self.skill)
        self.assertIn(
            "](skills/lean-stack/SKILL.md)",
            self.readme,
        )
        self.assertIn("Plain `codex plugin add` does not edit", self.readme)
        self.assertIn("普通 `codex plugin add` 不会修改", self.readme)
        self.assertIn("未获用户当次明确同意不得修改", self.skill)

    def test_readme_is_a_concrete_bilingual_agent_calling_guide(self) -> None:
        self.assertLessEqual(len(self.readme.splitlines()), 190)
        for term in (
            "# Codex子代理调用与精简流程",
            "插件标识：`codex-lean-stack`",
            "## 中文",
            "### 调用前",
            "首条说明先到",
            "### 运行中",
            "### 收口与复用",
            "### 精简与安全",
            "### 调用流程",
            "### 不调用代理的情况",
            "## English",
            "### Before delegation",
            "A fast first explanation",
            "### While agents run",
            "### Closing and reuse",
            "### Process removal and safety",
            "## 安装与使用 / Install and use",
            "## 文档 / Docs",
            "official OpenAI plugin documentation",
            "OpenAI 官方插件文档",
            "内部交流只服务真实依赖",
            "子代理公开实际配置",
            "新选配全部默认标准速度",
            "普通任务不再向父代理重复发送相同四行",
            "父代理不中断主线",
            "持续多工作流任务尽早派发",
            "变体只为真实改进",
            "子代理可以成为协作父代理",
            "SOURCE_COVERAGE",
            "子代理会积累经过采用的经验",
            "UUID `run_id`",
            "`ensure` 和 `improve`",
            "没有项目保留层",
            "没有后台编排系统",
            "Internal messages serve real dependencies",
            "Agents disclose configuration visibly",
            "New selections default to Standard speed",
            "Accepted work becomes experience",
            "No background orchestrator",
            "普通文件进入 Windows 回收站",
        ):
            self.assertIn(term, self.readme)
        for linked_authority in (
            "skills/lean-stack/SKILL.md",
            "skills/lean-stack/references/delegation.md",
            "skills/lean-stack/references/specialist-memory.md",
            "skills/lean-stack/references/write-parallelism.md",
            "skills/lean-stack/references/anti-overengineering.md",
            "skills/lean-stack/references/ablation-loop.md",
            "Jiao-Jie.md",
        ):
            self.assertIn(linked_authority, self.readme)
        for mirrored_detail in (
            '<div align="center">',
            "img.shields.io",
            "我做这个插件，是因为",
            "I built this because",
            "Keep Codex focused on the work",
            "## 一眼看懂 / At a glance",
            "关键步骤：<",
            "完整角色文件不超过 16 KiB",
            "--expected-state-sha256",
            "migrate-global --plan",
        ):
            self.assertNotIn(mirrored_detail, self.readme)

    def test_bounded_progress_does_not_replace_each_subagent_final_result(self) -> None:
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.memory
            + self.write_parallelism
            + self.readme
            + self.handoff
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

    def test_chinese_docs_use_plain_agreement_terms(self) -> None:
        self.assertNotIn("契" + "约", self.chinese_docs)
        self.assertIn("对外约定", self.chinese_docs)
        self.assertIn("约定一致性测试", self.readme + self.handoff)

    def test_windows_python_commands_force_utf8_for_chinese_skill_validation(self) -> None:
        combined = self.versioning + self.readme + self.handoff
        for required in ("py -3 -X utf8", "PYTHONUTF8=1", "GBK", "SKILL.md"):
            self.assertIn(required, combined)

    def test_all_relative_markdown_links_resolve(self) -> None:
        markdown_files = [
            ROOT / "README.md",
            ROOT / "Jiao-Jie.md",
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
