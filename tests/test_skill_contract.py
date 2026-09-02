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
        cls.handoff = (ROOT / "Jiao-Jie.md").read_text(encoding="utf-8")
        cls.build = (REFERENCES / "build.md").read_text(encoding="utf-8")
        cls.bug_fix = (REFERENCES / "bug-fix.md").read_text(encoding="utf-8")
        cls.investigation = (REFERENCES / "investigation.md").read_text(encoding="utf-8")
        cls.review = (REFERENCES / "review.md").read_text(encoding="utf-8")
        cls.long_running = (REFERENCES / "long-running.md").read_text(encoding="utf-8")
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
                ROOT / "Jiao-Jie.md",
                SKILL_DIR / "SKILL.md",
                *REFERENCES.glob("*.md"),
            )
        )

    def test_value_sensitive_priority_and_safety_floor_remain(self) -> None:
        for content in (self.skill, self.routing, self.flowcharts):
            self.assertIn("高价值工作", content)
            self.assertIn("普通工作", content)
            self.assertIn("质量优先", content)
            self.assertIn("速度优先", content)
        for readme_term in ("质量或速度收益", "风险", "成本"):
            self.assertIn(readme_term, self.readme)
        for floor in ("安全", "权限", "数据完整性", "诚实证据"):
            self.assertIn(floor, self.skill + self.readme)
        for principle in (
            "高价值工作质量优先",
            "普通工作速度优先",
            "总成本不得无收益地大幅增加",
        ):
            self.assertIn(principle, self.skill)

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

    def test_active_main_task_chain_survives_adjustments_and_drives_final_summary(
        self,
    ) -> None:
        metadata = " ".join(
            [
                self.manifest["interface"]["longDescription"],
                *self.manifest["interface"]["defaultPrompt"],
                self.openai_yaml,
            ]
        )
        combined = (
            self.skill
            + self.routing
            + self.readme
            + self.handoff
            + self.flowcharts
            + metadata
        )
        for required in (
            "主任务链锚点",
            "上一次已经明确确认完成",
            "第一个要求",
            "明确取消、停止、放弃或替换",
            "追加调整",
            "不得丢弃",
            "自动恢复并继续",
            "不得只回答最新调整",
            "从锚点",
            "逐项",
            "调整前已经完成",
            "不建立数据库、后台队列或持久状态机",
        ):
            self.assertIn(required, combined)

        flow = self.flowcharts.split("## 一、主任务链路", 1)[1].split(
            "## 二、工具、子代理与安全并行链路", 1
        )[0]
        active_chain = flow.index("已有尚未完整交付并确认完成的")
        replacement = flow.index("用户明确取消、停止、放弃", active_chain)
        additive = flow.index("作为追加调整", replacement)
        resume = flow.index("自动恢复", additive)
        full_review = flow.index("从主任务链锚点到最新消息", resume)
        final_summary = flow.index("完整总结整条主任务链", full_review)
        self.assertLess(active_chain, replacement)
        self.assertLess(replacement, additive)
        self.assertLess(additive, resume)
        self.assertLess(resume, full_review)
        self.assertLess(full_review, final_summary)

    def test_main_flow_is_primary_and_locates_every_auxiliary_entry(self) -> None:
        main = self.flowcharts.split("## 一、主任务链路", 1)[1].split(
            "## 二、工具、子代理与安全并行链路", 1
        )[0]
        group_close = main.index("本组当前已就绪结果已核验")
        unique = main.index("竞争并选出", group_close)
        retention = main.index("默认只尝试一次 ensure", unique)
        experience = main.index("一次 improve 合并追加一条经验", retention)
        removal = main.index("其他子代理移出组、结束", experience)
        completion = main.index("主任务完成条件满足吗", removal)
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
        combined = (
            self.skill
            + self.routing
            + self.delegation
            + self.readme
            + self.handoff
            + self.flowcharts
        )
        flow = self.flowcharts.split(
            "## 五、任务类型组、复制、变体与保留子代理链路", 1
        )[1].split("## 六、调查与实现链路", 1)[0]
        task_type = flow.index("父代理已判定具体任务类型")
        decided = flow.index("确认应该调用", task_type)
        fits_group = flow.index("具体任务类型适合", decided)
        reuse_group = flow.index("立即复用已有任务类型组", fits_group)
        visible_retained = flow.index("有可见的保留子代理吗", reuse_group)
        reuse_retained = flow.index("立即复用保留子代理", visible_retained)
        self_read = flow.index("保留子代理读取自己的", reuse_retained)
        customize = flow.index("定制运行时新子代理", visible_retained)
        new_group = flow.index("开新的运行时任务类型组", fits_group)
        brief = flow.index("父代理为每个子任务分别给出规范任务名", self_read)
        declaration = flow.index("发送内部四行", brief)
        group_close = flow.index("本组当前已就绪结果", declaration)
        unique = flow.index("唯一留下的子代理", group_close)
        retention = flow.index("第一次成功默认只尝试一次 ensure", unique)
        experience = flow.index("一次 improve 合并追加一条经验", retention)
        removal = flow.index("其他子代理移出组、结束", experience)

        self.assertLess(task_type, decided)
        self.assertLess(decided, fits_group)
        self.assertLess(fits_group, reuse_group)
        self.assertLess(reuse_group, visible_retained)
        self.assertLess(visible_retained, reuse_retained)
        self.assertLess(reuse_retained, self_read)
        self.assertLess(self_read, brief)
        self.assertLess(visible_retained, customize)
        self.assertLess(fits_group, new_group)
        self.assertLess(group_close, unique)
        self.assertLess(unique, retention)
        self.assertLess(retention, experience)
        self.assertLess(unique, experience)
        self.assertLess(experience, removal)
        for required in (
            "同一种活就是同一任务类型",
            "核心职责、主要来源或工具、证据形状都相同",
            "决定性边界不同",
            "成功条件不参与任务类型归类",
            "为每个子任务分别指定",
            "立即复用组",
            "有可见的保留子代理",
            "读取自己配置中已有的",
            "经验、模型、思考程度和速度",
            "不要求父代理重新注入经验或强制",
            "重写已有配置",
            "定制运行时新子代理",
            "开一个新的运行时任务类型组",
            "不是持久创建",
            "真实结果出来后",
            "核验采用后先泛化，再全局保留",
            "每个全局领域任务类型组",
            "不存在全局只能保留一个",
            "休眠的自定义代理配置",
            "父代理仍要运行测试或集成",
            "准备子代理不写 SQLite",
            "主任务绝不等待",
            "保存回执",
        ):
            self.assertIn(required, combined)
        self.assertNotIn("通用子代理", combined)
        for opening_line in (
            "我是<本地化子代理名称>。",
            "模型：<具体模型>",
            "思考程度：<具体等级>",
            "速度：<标准或快速>",
        ):
            self.assertIn(opening_line, combined)

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
            "不排队、不轮询、不重试",
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
        combined = self.skill + self.routing + self.delegation + self.readme
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "先判定当前工作的具体任务类型",
            "只有具体任务类型和任务类型组都已确定",
            "任务类型组确定前禁止定制子代理",
            "此前不得选择子代理的模型、思考程度、速度或权限配置",
            "只有任务类型和任务类型组都确定后",
        ):
            self.assertIn(required, compact)

        main_flow = self.flowcharts.split("## 一、主任务链路", 1)[1].split(
            "## 二、工具、子代理与安全并行链路", 1
        )[0]
        task_type = main_flow.index("父代理判定具体任务类型")
        model_route = main_flow.index("模型任务吗", task_type)
        self.assertLess(task_type, model_route)

        group_flow = self.flowcharts.split(
            "## 五、任务类型组、复制、变体与保留子代理链路", 1
        )[1].split("## 六、调查与实现链路", 1)[0]
        self.assertIn("父代理已判定具体任务类型", group_flow)
        self.assertIn("B -->|适合| C[立即复用已有任务类型组]", group_flow)
        self.assertIn("B -->|不适合| H[开新的运行时任务类型组]", group_flow)
        self.assertIn("D -->|没有| G[父代理为当前任务", group_flow)
        self.assertIn("H --> G", group_flow)

        tool_flow = self.flowcharts.split(
            "## 二、工具、子代理与安全并行链路", 1
        )[1].split("## 三、调用容量与成本快判链路", 1)[0]
        self.assertIn("父代理定制运行时新子代理", tool_flow)
        self.assertNotIn("运行时新子代理或变体", tool_flow)

    def test_tools_are_used_before_model_subagents(self) -> None:
        for content in (self.skill, self.routing):
            self.assertIn("工具", content)
            self.assertIn("短命令", content)
            self.assertIn("后台", content)
        for readme_term in ("工具先行", "短命令", "模型子代理"):
            self.assertIn(readme_term, self.readme)
        self.assertIn("不启动模型子代理", self.skill)
        self.assertIn("一次工具调用并发运行", self.flowcharts)

    def test_runtime_capacity_replaces_plugin_numeric_caps(self) -> None:
        combined = self.skill + self.routing + self.delegation + self.readme
        self.assertIn("不另设同时调用数字", self.skill)
        self.assertIn("不设置同时调用数字", self.routing)
        self.assertIn("不设置主任务累计调用数字", combined)
        self.assertIn("实现安全边界不属于调用数量限制", combined)
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
        self.assertIn("重新查费率", self.skill)
        self.assertIn("运行时不重新搜索费率", self.routing)
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
            "边界清楚",
            "多个独立普通子任务",
            "更倾向",
            "第二个及后续调用",
            "只升级",
            "标准速度",
            "真实关键路径",
            "不是永久白名单",
        ):
            self.assertIn(boundary, combined)

    def test_task_type_groups_replace_work_block_language(self) -> None:
        for content in (self.skill, self.delegation, self.readme, self.flowcharts):
            self.assertIn("任务类型", content)
            self.assertIn("任务类型组", content)
            self.assertIn("保留子代理", content)
        for removed in ("工作块", "父任务", "宿主"):
            self.assertNotIn(removed, self.chinese_docs)
        self.assertNotIn("实" + "例", self.chinese_docs)
        self.assertIn("英文 `instance` 在中文正文中强制翻译为“子任务”", self.skill)

    def test_copy_subtasks_and_variant_semantics_are_unambiguous(self) -> None:
        combined = self.skill + self.delegation + self.flowcharts
        self.assertIn("复制组内子代理，只处理同一任务类型并用于加速", self.skill)
        self.assertIn("复制的是任务类型组里的子代理，不是任务类型组", self.delegation)
        self.assertIn("第二个同一任务类型的子任务", self.delegation)
        self.assertIn("第三个同一任务类型的子任务", self.delegation)
        self.assertIn("每次复制前先判断保留子代理", combined)
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
        self.assertIn("同一任务类型组收口后只能有", combined)
        self.assertIn("一个子代理", combined)
        self.assertIn("合并一条", combined)
        self.assertIn("任一决定性边界不同", combined)
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

    def test_retention_and_experience_are_default_nonblocking_side_chain(self) -> None:
        combined = (
            self.skill
            + self.memory
            + self.delegation
            + self.readme
            + self.flowcharts
        )
        self.assertIn("专门代理记忆就是经验", combined)
        self.assertIn("只保留一条快速侧链", self.skill)
        self.assertIn("立即跳过", combined)
        self.assertIn("主任务不依赖任何持久写入成功", self.memory)
        self.assertIn("SQLite", combined)
        self.assertIn("只追加原始经验", combined)
        self.assertIn("经验摘要压缩", combined)
        self.assertIn("不删除原始经验", combined)
        compact = re.sub(r"\s+", "", combined)
        for boundary in (
            "结果通过必要核验并被父代理采用",
            "默认依次做一次有界 `ensure` 和一次有界 `improve`",
            "不要求主任务接近结束",
            "稳定 `event_id`",
            "只有明确排除项",
            "不排队、不轮询、不重试、不等待",
            "摘要压缩仍只在能与真实工作并行且不争用时执行",
            "没有复制或变体的组不竞争",
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
        self.assertIn("准备只是优化", combined)
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
            "不能删除已经显示在 Codex",
        ):
            self.assertIn(required, combined)
        self.assertIn("git reset --hard", self.write_parallelism)
        self.assertIn("禁止", self.write_parallelism)

    def test_no_numeric_scoring_or_fixed_lifecycle_contract(self) -> None:
        combined = self.skill + self.delegation + self.memory + self.readme
        self.assertIn("没有数值评分", combined)
        self.assertIn("不是固定顺序、固定数量或固定生命周期", self.memory)
        self.assertIn("没有固定顺序或固定数量", self.skill)
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
        for content in (self.skill, self.routing, self.flowcharts):
            self.assertIn("代码、配置、公共行为或高风险边界", content)
        self.assertIn("语义审查不是所有主任务", self.skill)
        self.assertIn("调查、解释、简单工具工作和纯只读任务", self.skill)
        self.assertIn("只重跑受影响检查", self.skill)
        self.assertIn("Run only affected checks", self.readme)
        self.assertIn("测试只覆盖受影响边界", self.readme)

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
        self.assertIn("完整覆盖且来源未变化", combined)

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
            "默认保持平面委派",
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
            "<CODEX_HOME>/lean-stack/待删文件",
            "不是不可恢复的物理清除",
        ):
            self.assertIn(required, combined)
        for concrete_config_boundary in (
            "复用可见保留子代理时由它自读已有配置",
            "运行时新子代理",
            "具体模型、思考程度和标准或快速速度",
            "不能使用“继承”或“未暴露”",
        ):
            self.assertIn(concrete_config_boundary, combined)

        self.assertIn(
            "只有新父代理任务能带来真实速度或质量收益时才调用 `create_thread`",
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
            "直接调用失败、容量不足、边界不清或写入无法隔离时",
            self.agents_source,
        )
        self.assertNotIn("无人否决即同意", combined)
        self.assertNotIn("用户明确要求调用其他或新建 Codex 父代理任务时", combined)

    def test_recoverable_retirement_changes_destination_without_changing_scale(
        self,
    ) -> None:
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
            "原规则判定应删的目标仍处理",
            "原规则不允许删的目标仍不处理",
            "普通文件进入 Windows 回收站",
            "重要文件进入任务或插件专属 `待删文件`",
            "<CODEX_HOME>/lean-stack/待删文件",
            "直接普通文件",
            "单一硬链接",
            "所有权令牌",
            "经验与存活轮次都必须为零",
            "`delete` 和 `restore`",
            "--receipt",
            "--expected-sha256",
            "--owner-token",
            "已恢复收据",
            "不能借恢复接管用户文件或替换活跃角色",
        ):
            self.assertIn(required, combined)

        delete_body = re.search(
            r"(?ms)^    def delete\(.*?(?=^    def restore\()",
            self.agents_source,
        )
        self.assertIsNotNone(delete_body)
        assert delete_body is not None
        delete_text = delete_body.group(0)
        for retained_guard in (
            "_owned_agent",
            "experience_events",
            "agent_runs",
            "validate_direct_agent_file",
            "expected_sha256",
            "owner_token",
            "rename_no_replace",
            "retired_to_pending_deletion",
        ):
            self.assertIn(retained_guard, delete_text)
        self.assertNotIn(".unlink(", delete_text)

        for restore_guard in (
            "def restore(",
            "retirement receipt must not contain owner_token",
            "active registry has an agent_id, name, role_key, or path conflict",
            "restored_from_pending_deletion",
            'restore_identity.add_argument("--receipt", type=Path)',
            'restore.add_argument("--expected-sha256", required=True)',
            'restore.add_argument("--owner-token", required=True)',
        ):
            self.assertIn(restore_guard, self.agents_source)

    def test_bounded_key_step_messages_continue_without_ack_or_scope_expansion(
        self,
    ) -> None:
        core = (
            self.skill,
            self.routing,
            self.delegation,
            self.long_running,
            self.flowcharts,
        )
        for content in core:
            self.assertIn("关键步骤", content)
            self.assertIn("停止条件", content)
            self.assertIn("立即继续", content)

        combined = "\n".join(core)
        for required in (
            "有限关键步骤清单",
            "每个关键步骤最多一条常规进度",
            "不等待父代理",
            "不发送定时心跳",
            "纯确认",
            "沉默或只回一行",
            "立即发送一条精简纠偏或任务目标更新",
            "不能扩大权限",
            "移除停止条件",
            "不得在执行中自行追加无界步骤",
            "关键步骤：",
            "情况：",
            "下一步：",
        ):
            self.assertIn(required, combined)
        self.assertRegex(
            self.skill,
            r"同一方向风险只有\s+状态实质变化后才能再次报告",
        )
        self.assertIn("不得用新增关键步骤续期", self.delegation)
        self.assertIn(
            "](skills/lean-stack/references/delegation.md)",
            self.readme,
        )
        self.assertIn("ready, bounded, independently verifiable task", self.readme)

    def test_retained_self_reads_and_declares_while_parent_configures_new_or_variant(self) -> None:
        combined = self.skill + self.delegation + self.readme + self.handoff
        for required in (
            "父代理",
            "具体模型",
            "思考程度",
            "标准或快速速度",
            "开场声明",
            "三个配置字段一个都不能省略",
            "报告实际差异",
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
        self.assertIn("不要求父代理强制重写", self.handoff)
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
        core = (
            self.skill,
            self.routing,
            self.delegation,
            self.readme,
            self.flowcharts,
            self.handoff,
        )
        combined = "\n".join(core)
        compact = re.sub(r"\s+", "", combined)
        for required in (
            "父代理规范任务名",
            "不是 Codex 线程 ID",
            "内部父子消息",
            "collaboration.send_message",
            "spawn_agent",
            "followup_task",
            "list_threads",
            "send_message_to_thread",
            "跨任务",
            "内部父子消息的替代",
            "直接授权的父代理跨任务协作",
            "完整四行",
            "自己的任务界面",
            "commentary",
            "公开同一四行",
            "内部副本和用户可见副本",
            "公开副本不能冒充内部父子消息",
            "最终回复顶部",
            "实际模型、思考程度和速度",
            "声明不是关键步骤",
            "不占关键步骤消息数量",
            "不规定具体先后",
            "reasoning",
            "不比较",
            "不重复声明",
            "不自动丢弃",
            "不能作为“配置声明已验证”的证据",
            "父代理自己的工具表",
            "agent_message",
            "中途纠偏是成功条件",
            "停止真实任务",
            "完全自包含",
            "不能冒充内部父子消息",
            "没有逐个工具授予参数",
            "第一段",
            "角色、职责和权限",
            "multi_agent_version=v2",
            "include_instructions=false",
            "ALL_TOOLS",
            "status",
            "角色TOML不能",
            "不能仅为通信提高模型",
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
            self.assertNotIn(
                re.sub(r"\s+", "", obsolete_order_contract),
                compact,
            )

        tools_flow = self.flowcharts.split(
            "## 二、工具、子代理与安全并行链路", 1
        )[1].split("## 三、调用容量与成本快判链路", 1)[0]
        tools_brief = tools_flow.index("任务说明含父代理规范任务名")
        tools_capability = tools_flow.index("子代理实际有", tools_brief)
        tools_declaration = tools_flow.index("发送内部四行", tools_capability)
        tools_stop = tools_flow.index("停止真实任务", tools_capability)
        tools_self_contained = tools_flow.index("只做完全自包含的有限任务", tools_capability)
        tools_work = tools_flow.index("子代理开始真实任务", tools_capability)
        self.assertLess(tools_brief, tools_capability)
        self.assertLess(tools_capability, tools_declaration)
        self.assertLess(tools_capability, tools_work)
        self.assertLess(tools_capability, tools_stop)
        self.assertLess(tools_capability, tools_self_contained)
        self.assertIn("当前子任务中完成，不限顺序", tools_flow)

        group_flow = self.flowcharts.split(
            "## 五、任务类型组、复制、变体与保留子代理链路", 1
        )[1].split("## 六、调查与实现链路", 1)[0]
        group_brief = group_flow.index("父代理为每个子任务分别给出规范任务名")
        group_capability = group_flow.index("子代理实际有", group_brief)
        group_declaration = group_flow.index("发送内部四行", group_capability)
        group_stop = group_flow.index("停止真实任务", group_capability)
        group_self_contained = group_flow.index("仅做完全自包含的有限任务", group_capability)
        group_work = group_flow.index("组内子代理开始执行第一个子任务", group_capability)
        self.assertLess(group_brief, group_capability)
        self.assertLess(group_capability, group_declaration)
        self.assertLess(group_capability, group_work)
        self.assertLess(group_capability, group_stop)
        self.assertLess(group_capability, group_self_contained)
        self.assertIn("当前子任务中完成，不限顺序", group_flow)

        skill_final = self.skill.split("子代理完成当前子任务后的最终回复固定为：", 1)[1]
        delegation_final = self.delegation.split("最终回复使用：", 1)[1]
        for final_template in (skill_final, delegation_final):
            self.assertLess(
                final_template.index("模型：<具体模型>"),
                final_template.index("子任务：<当前子任务>"),
            )
            self.assertLess(
                final_template.index("速度：<标准或快速>"),
                final_template.index("子任务：<当前子任务>"),
            )

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
        self.assertIn("recorded experience cannot be retired", script)
        self.assertIn("recorded survival rounds cannot be retired", script)
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
            "原始经验事件总数量不封顶",
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
                "ensure",
                "record-run",
                "improve",
                "delete",
                "restore",
                "migrate-global",
            },
        )
        improve_parser = action.choices["improve"]
        ensure_parser = action.choices["ensure"]
        record_parser = action.choices["record-run"]
        restore_parser = action.choices["restore"]
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
        restore_options = {
            option
            for parser_action in restore_parser._actions
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
        self.assertEqual(
            restore_options,
            {"-h", "--help", "--name", "--receipt", "--expected-sha256", "--owner-token"},
        )
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
            "只有四类负向边界值得最小测试",
            "哈希按风险计算一次",
            "一个权威源，四类变更表面",
            "可再生展示面",
            "发布/缓存面",
            "交接文件",
            "第二事实源",
        ):
            self.assertIn(required, self.anti_overengineering)
        self.assertIn("负向测试只保护", self.skill)
        self.assertIn("只更新会作出错误承诺的表面", self.flowcharts)
        self.assertIn("不留桩、注释或假想测试", self.flowcharts)

    def test_explicit_global_only_boundary_has_one_minimal_negative_guard(self) -> None:
        # The user explicitly prohibited project-scoped retained agents. This is a public
        # boundary, so a narrow absence guard is justified; hypothetical non-features do
        # not each get their own scaffold or test.
        for forbidden in ("project_scope", "project_id", "merge-global", "dual_write"):
            self.assertNotIn(forbidden, self.agents_source)
        self.assertIn("global_domain_key", self.agents_source)
        self.assertIn("migrate-global", self.agents_source)
        self.assertIn("只有四类负向边界值得最小测试", self.anti_overengineering)

    def test_versioning_preserves_one_version_update_and_external_authority(self) -> None:
        self.assertIn("只运行一次版本写入器", self.versioning)
        self.assertIn("完整旧版本", self.versioning)
        self.assertIn("只重装一次", self.versioning)
        for boundary in ("提交", "推送", "公开发布", "外部消息"):
            self.assertIn(boundary, self.versioning)

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
            "主任务链锚点",
            "追加调整",
            "为每个子任务分别指定",
            "父代理规范任务名",
            "multi_agent_version=v2",
            "自定义角色 TOML",
            "不能替父会话启用多代理",
            "ALL_TOOLS",
            "跨任务 API",
            "第一次成功就默认只尝试一次",
            "每个全局领域任务类型组各保留一个休眠配置",
            "在自己的线程用最终回复",
            "存活轮次",
        ):
            self.assertIn(contract_term, full_contract)
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertIn(model, full_contract)
        self.assertNotIn("实" + "例", full_contract)

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
            "TOML 与收据移入插件专属待删文件",
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
        combined = self.skill + self.readme + self.flowcharts
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
            "离线静态 SVG/HTML",
            "Viewer Runtime",
            "路径",
            "透镜",
            "故事",
            "导出",
            "loopback",
            "zh-CN",
            "不在本插件中建立第二条静态或动态生成路线",
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
            "不写入SQLite、TOML、合同或完成收据",
            "anti-overengineering.md",
            "现实消费者",
            "已经决定不实现的假想功能",
            "第二事实源",
            "schema v4",
            "17名全局领域保留子代理",
            "只追加原始经验和纠正事件",
            "经验数量不封顶",
            "经验摘要压缩",
            "这不是单写入者规则",
            "不设置同时调用数字",
            "不在每个任务重新搜索费率",
            "链路图只是辅助说明",
            "主任务链锚点",
            "不能只总结最后一条消息",
            "multi_agent_version=v2",
            "include_instructions=false",
            "ALL_TOOLS",
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
        for document in (self.skill, self.versioning, self.installer):
            self.assertIn(default_line, document)
        self.assertIn("普通 `codex plugin add` 不会修改全局 `AGENTS.md`", self.readme)
        self.assertIn("通用项目交接规则", self.handoff)
        self.assertIn("未经用户当次明确同意", self.handoff)
        self.assertIn("不能复制插件的子代理加速规则", self.handoff)
        self.assertIn("正式安装成功后才幂等确保", self.handoff)
        self.assertIn("只在新会话开始或上下文压缩后亲自完整读取", self.handoff)
        self.assertIn("子代理摘要或子代理读取不能替代", self.handoff)
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
            "用户全局文件边界",
            "主任务链连续性与最终说明",
            "任务类型与任务类型组",
            "主任务链与辅助链入口",
            "工具、子代理与调用规则",
            "子代理开场声明与有界交流",
            "任务类型组、复制、变体与收口",
            "写入安全与用户不满意",
            "反 AI 过度工程",
            "条件性验证",
            "经验、SQLite、成本与生命周期侧链",
            "统一术语",
            "权威路径与代码边界",
            "运行环境状态快照",
            "本轮实际变化",
            "本轮验证证据",
            "工作树与剩余边界",
            "后续代理开始方式",
        )
        indexes = [headings.index(heading) for heading in ordered]
        self.assertEqual(indexes, sorted(indexes))
        dynamic = headings.index("运行环境状态快照")
        self.assertGreater(dynamic, headings.index("权威路径与代码边界"))
        for heading in ("本轮实际变化", "本轮验证证据", "工作树与剩余边界"):
            self.assertGreater(headings.index(heading), dynamic)
            self.assertEqual(headings.count(heading), 1)
        self.assertIn("以下部分是每轮都会变化的状态", self.handoff)

    def test_subagent_acceleration_stays_in_the_plugin_not_global_agents(self) -> None:
        combined = self.skill + self.readme
        self.assertIn("子代理加速规则由本技能自身承载", self.skill)
        self.assertIn(
            "](skills/lean-stack/SKILL.md)",
            self.readme,
        )
        self.assertIn("Plain `codex plugin add` does not edit", self.readme)
        self.assertIn("普通 `codex plugin add` 不会修改", self.readme)
        self.assertIn("只有用户当次明确同意时才能修改", combined)

    def test_readme_is_a_concrete_bilingual_agent_calling_guide(self) -> None:
        self.assertLessEqual(len(self.readme.splitlines()), 190)
        for term in (
            "# 代理调用和精简流程",
            "插件标识：`codex-lean-stack`",
            "原版 Codex 已经提供并行子代理",
            "本插件不重复实现这些底层能力",
            "Stock Codex already provides parallel subagents",
            "## 中文",
            "### 调用前",
            "### 运行中",
            "### 收口与复用",
            "### 精简与安全",
            "### 调用流程",
            "### 不调用代理的情况",
            "## English",
            "### Before delegation",
            "### While agents run",
            "### Closing and reuse",
            "### Process removal and safety",
            "## 安装与使用 / Install and use",
            "## 文档 / Docs",
            "official OpenAI plugin documentation",
            "OpenAI 官方插件文档",
            "Luna 使用真实内部交流",
            "multi_agent_version=v2",
            "agent_message",
            "子代理开头主动声明自己",
            "父代理不中断主线",
            "同类子任务可以复制加速",
            "变体只为真实改进",
            "子代理可以成为协作父代理",
            "SOURCE_COVERAGE",
            "子代理会积累经过采用的经验",
            "UUID `run_id`",
            "`ensure` 和 `improve`",
            "没有项目保留层",
            "没有后台编排系统",
            "Verified Luna messaging",
            "Copies accelerate repeated work",
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
            "不建立共享中转文件",
            "不由一个子代理汇总其他子代理",
            "不主动反复轮询",
            "不为统一收齐而等待全部",
            "统一收口确实依赖全部必要结果时才等待全部",
            "状态：完成 | 部分完成 | 受阻",
            "证据或缺口：",
        ):
            self.assertIn(required, combined)
        self.assertIn(
            "开场声明的内部副本与用户可见副本、关键步骤消息和最终回复相互独立",
            self.skill,
        )
        self.assertRegex(
            self.skill,
            r"短任务没有中途关键\s+步骤时仍发送两个开场副本",
        )
        self.assertNotIn("交付父代理", self.chinese_docs)

    def test_chinese_docs_use_plain_agreement_terms(self) -> None:
        self.assertNotIn("契约", self.chinese_docs)
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
