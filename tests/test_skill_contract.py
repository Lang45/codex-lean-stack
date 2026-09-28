"""Structural contracts for the public skill surface.

Behavioral safety for persistence, installation, locking, paths, CAS, and rollback
lives in the corresponding executable test modules.  This file deliberately avoids
mirroring release notes or handoff prose as a second source of truth.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "skills" / "lean-stack"
SIMPLIFY = ROOT / "skills" / "lean-simplify"
REFS = STACK / "references"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stack = read(STACK / "SKILL.md")
        cls.simplify = read(SIMPLIFY / "SKILL.md")
        cls.dispatch = read(REFS / "dispatch-start.md")
        cls.results = read(REFS / "agent-results.md")
        cls.memory = read(REFS / "specialist-memory.md")
        cls.cost = read(REFS / "cost-baseline.md")
        cls.collaboration = read(REFS / "collaboration.md")
        cls.write_parallelism = read(REFS / "write-parallelism.md")
        cls.source_results = read(REFS / "source-results.md")
        cls.flowcharts = read(REFS / "flowcharts-zh.md")
        cls.versioning = read(REFS / "versioning.md")
        cls.readme = read(ROOT / "README.md")
        cls.changelog = read(ROOT / "CHANGELOG.md")
        cls.manifest = json.loads(read(ROOT / ".codex-plugin" / "plugin.json"))
        cls.openai_yaml = read(STACK / "agents" / "openai.yaml")

    def test_two_skills_are_independent_public_entries(self) -> None:
        for skill, name in ((self.stack, "lean-stack"), (self.simplify, "lean-simplify")):
            self.assertTrue(skill.startswith("---\n"))
            self.assertIn(f"name: {name}", skill.split("---", 2)[1])
        self.assertIn("平行、独立", self.stack)
        self.assertIn("互不构成前置条件", self.stack)
        self.assertIn("平行", self.simplify)

    def test_dispatch_uses_quality_cost_time_without_call_quota(self) -> None:
        decision = self.stack.split("## 模型与思考程度", 1)[0]
        for term in ("质量", "成本", "时间", "安全", "权限", "数据完整性"):
            self.assertIn(term, decision)
        self.assertIn("调用数量本身不是目标", decision)
        for principle in (
            "高价值工作质量优先，守住正确性；当遇到困难时派遣专家协助。",
            "普通工作可靠性相当后，总成本优先。",
            "总成本处于可接受成本带时，为加快父任务完成速度，增加或并发派遣子代理来节省时间是可取的。",
        ):
            self.assertIn(principle, decision)
        self.assertIn("提速也不是每次委派的必要条件", decision)
        self.assertNotIn("并同时满足以下条件", decision)
        self.assertNotIn("成本或速度有一项实际收益即可委派", decision)
        self.assertNotRegex(decision, r"最多\s*[0-9一二三四五六七八九十]+\s*个子代理")

    def test_same_capability_family_has_one_reuse_order(self) -> None:
        section = self.stack.split("## 同一能力族优先复用", 1)[1].split(
            "## 原生调用与任务卡", 1
        )[0]
        positions = [section.index(term) for term in ("live child", "agent_type", "运行时角色")]
        self.assertEqual(positions, sorted(positions))
        for boundary in ("权限", "安全风险", "证据要求", "完成状态本身不妨碍续用"):
            self.assertIn(boundary, section)
        self.assertIn("只发送新增目标、证据或纠偏", section)

    def test_retained_catalog_type_precedes_generic_runtime_routes(self) -> None:
        section = self.dispatch.split("## 选择同一能力族的执行者", 1)[1].split(
            "## 任务卡、上下文与所有权", 1
        )[0]
        compact = re.sub(r"\s+", "", section)
        for term in ("具名保留`lean_*`类型", "generic`explorer`/`worker`/default", "运行时角色"):
            self.assertIn(re.sub(r"\s+", "", term), compact)
        self.assertLess(compact.index("具名保留`lean_*`类型"), compact.index("generic`explorer`/`worker`/default"))
        for boundary in ("职责", "输入", "交付", "权限", "模型能力", "安全", "证据边界"):
            self.assertIn(boundary, section)
        self.assertIn("不能因项目名不同跳过保留类型", compact)
        self.assertIn("必须先定向`recall`", compact)
        self.assertIn("召回成功后，将该机器身份真实传入`spawn_agent.agent_type`调用", compact)
        self.assertIn("具体边界不兼容", compact)
        self.assertIn("定向召回明确失败", compact)
        for invalid_reason in ("没想到", "名称不同", "未查"):
            self.assertIn(invalid_reason, compact)
        self.assertIn("候选目录及当前切片的职责、权限和证据要求未变化时复用", compact)
        self.assertIn("不重复扫描", compact)
        self.assertIn("真实传入", compact)
        self.assertIn("不能因为generic更顺手而跳过", compact)

    def test_live_child_reuse_is_not_retained_catalog_reuse(self) -> None:
        combined = self.stack + self.dispatch + self.memory
        self.assertIn("台账复用只指", combined)
        self.assertIn("现有 `lean_*` 保留 `agent_type`", combined)
        self.assertIn("`followup_task`", combined)
        self.assertIn("不得计入台账复用", combined)

    def test_runtime_copy_and_variant_keep_their_existing_authoritative_branch(self) -> None:
        groups_path = REFS / "agent-groups.md"
        self.assertTrue(groups_path.exists())
        groups = read(groups_path)
        for behavior in ("## 复制", "## 变体与竞争", "复制只存在于本轮运行", "每个子代理在自己的线程"):
            self.assertIn(behavior, groups)
        self.assertIn("agent-groups.md", self.stack)
        self.assertIn("agent-groups.md", read(REFS / "execution-routing.md"))

    def test_spawn_configuration_is_native_and_bounded(self) -> None:
        combined = self.stack + self.dispatch
        for parameter in ("model", "reasoning_effort", 'fork_turns="none"'):
            self.assertIn(parameter, combined)
        self.assertIn('禁止 `fork_turns="all"`', combined)
        self.assertIn("TOML", combined)
        self.assertIn("不能代替原生参数", combined)

    def test_astra_effort_is_selected_per_task(self) -> None:
        compact = re.sub(r"\s+", "", self.stack + self.dispatch)
        for effort in ("`medium`", "`high`", "`xhigh`"):
            self.assertIn(effort, compact)
        self.assertNotIn("`low`", compact)
        self.assertIn("`xhigh`是上限，不是默认值", compact)
        self.assertIn("不得因为模型是Astra就固定选`xhigh`", compact)
        self.assertIn("`max`和`ultra`不用于Astra子代理", compact)

    def test_new_dispatch_uses_four_current_models_and_checks_legacy_reuse(self) -> None:
        selection = self.stack.split("## 模型与思考程度", 1)[1].split("## 原生调用与任务卡", 1)[0]
        models = ("gpt-5.6-luna", "gpt-6-sol", "gpt-5.6-sol", "gpt-6-astra")
        manifest_surface = (
            self.manifest["interface"]["longDescription"]
            + self.manifest["interface"]["defaultPrompt"][0]
        )
        for model in models:
            self.assertIn(model, selection)
            self.assertIn(model, self.dispatch)
        for surface in (
            selection,
            self.dispatch,
            self.readme,
            self.openai_yaml,
            manifest_surface,
        ):
            positions = [surface.index(model) for model in models]
            self.assertEqual(positions, sorted(positions))
        for historical_model in ("gpt-6-luna", "gpt-5.6-terra"):
            self.assertNotIn(historical_model, selection)
        self.assertIn("真实模型", self.stack)
        self.assertIn("实际模型", self.dispatch)
        for text in (self.stack, self.dispatch):
            self.assertIn("当前宿主已加载", text)
            self.assertIn("新任务验证", text)
        self.assertIn("运行时子代理", self.dispatch)
        self.assertIn("CAS", self.dispatch)

    def test_task_card_has_five_opening_lines_and_three_final_lines(self) -> None:
        block = re.search(r"```text\n(子代理名称：.+?)\n```", self.dispatch, re.S)
        self.assertIsNotNone(block)
        assert block is not None
        lines = block.group(1).splitlines()
        self.assertEqual(lines[:3], [
            "子代理名称：<已按实际路线附（复用）或（新建）的名称>",
            "模型：<具体模型>",
            "思考程度：<具体等级>",
        ])
        self.assertEqual(lines[3:], [
            "存活轮次：<保留召回状态或运行时 0>",
            "经验：<保留召回状态、复用当前线程上下文或本次任务上下文>",
        ])
        self.assertEqual(len(lines), 5)
        self.assertIn("执行句", self.dispatch)
        self.assertIn("第一条用户可见进展说明顶部必须原样展示以上五行，最终回复顶部重复前三行实际配置", self.dispatch)
        self.assertIn("opening_declaration", self.dispatch)
        self.assertIn("opening_status", self.dispatch)
        self.assertNotIn("存活轮次：未核验", self.dispatch + self.stack + self.openai_yaml)
        self.assertNotIn("经验：未核验", self.dispatch + self.stack + self.openai_yaml)
        self.assertNotRegex(
            self.dispatch + self.stack + self.openai_yaml,
            r"(?m)^经验：未核验持久化经验",
        )
        self.assertIn("不得显示“未核验持久化经验”", self.dispatch + self.stack + self.openai_yaml)
        self.assertIn("存活轮次：0", self.dispatch)
        self.assertIn("经验：本次任务上下文", self.dispatch)
        self.assertIn("经验：复用当前线程上下文", self.dispatch + self.stack + self.openai_yaml)
        self.assertIn("召回失败时改派最小合规运行时子代理", self.dispatch)
        self.assertIn("不声称复用了保留类型", self.dispatch)
        self.assertIn("状态无法确认时改派", self.dispatch)
        self.assertIn("五行", self.stack)
        self.assertIn("五行真实开场与 final 三行的唯一详细规则见", self.stack)
        self.assertIn("最终回复顶部重复前三行实际配置", self.dispatch)
        self.assertIn("最终回复顶部保留三行实际配置", self.results)
        self.assertIn("只对该身份做一次有界", self.memory)
        self.assertIn("复用当前 live child 或已选中且召回成功的保留 `agent_type` 用 `（复用）`", self.dispatch)
        self.assertIn("最小运行时新角色用 `（新建）`", self.dispatch)
        self.assertIn("候选匹配但未成功派发不得预标复用", self.dispatch)
        self.assertIn("名称标 `（新建）`", self.memory)
        self.assertIn("最终回复顶部保留三行实际配置，第一行沿用开场的同一名称标记", self.results)
        self.assertIn("缺少实际状态时先向父代理内部报告", self.results)
        self.assertIn("final 保持相同标记", read(REFS / "collaboration.md"))
        self.assertIn("名称标新建", self.flowcharts)
        self.assertIn("第一行名称按实际派发标一次（复用）或（新建）", self.openai_yaml)

    def test_only_astra_is_the_expert_route(self) -> None:
        manifest_surface = (
            self.manifest["interface"]["longDescription"]
            + self.manifest["interface"]["defaultPrompt"][0]
        )
        for surface in (
            self.stack,
            self.dispatch,
            self.readme,
            self.openai_yaml,
            manifest_surface,
        ):
            compact = surface.replace("`", "")
            self.assertIn("前三档都是常规子代理路线", compact)
            self.assertIn("只有 gpt-6-astra 是专家路线", compact)

    def test_user_facing_progress_term_is_chinese(self) -> None:
        active = "\n".join(
            (self.stack, self.dispatch, self.results, self.collaboration, self.flowcharts, self.readme)
        )
        self.assertIn("进展说明", active)
        self.assertNotIn("commentary", active)
        self.assertIn("final", self.results)
        self.assertIn("不构成交付", self.results)

    def test_missing_child_progress_has_evidence_based_fallback(self) -> None:
        section = self.dispatch.split("这条随卡执行句是输出合同", 1)[1].split(
            "独立窄任务优先", 1
        )[0]
        self.assertIn("宿主没有向用户显示", section)
        self.assertIn("原生调用回执", section)
        self.assertIn("已核验召回状态", section)
        self.assertIn("不得猜测", section)

    def test_retention_is_selective_after_adopted_runtime_result_and_not_a_dispatch_gate(self) -> None:
        self.assertIn("结果核验后主任务立即继续", self.stack)
        self.assertIn("普通派发不进行成本、迁移或摘要巡检", self.stack)
        self.assertIn("选中已加载保留类型时，仅对该身份定向召回", self.memory)
        self.assertIn("不能成为派发前置", self.memory)
        self.assertIn("不能延迟主任务动作或交付", re.sub(r"\s+", "", self.memory))
        self.assertIn("需要记录时才生成", self.memory)
        compact = re.sub(r"\s+", "", self.stack + self.memory)
        for condition in (
            "运行时角色首次产生已核验且被父任务实际采用的结果后，执行一次保留判断",
            "职责去除项目、文件和来源身份后仍稳定",
            "有具体跨任务复用价值",
            "权限与证据边界可稳定描述",
            "台账无兼容同族",
            "全部满足时才可执行`ensure`",
        ):
            self.assertIn(re.sub(r"\s+", "", condition), compact)
        retention_sections = (
            self.stack.split("## 执行、结果和保留", 1)[1].split("## 条件路由", 1)[0]
            + self.memory.split("## 创建或重配身份", 1)[1].split("## 按需记录完成与经验", 1)[0]
        )
        self.assertIn("选择性", retention_sections)
        self.assertNotIn("全部满足时必须执行 `ensure`", retention_sections)
        self.assertIn("不把所有成功运行时", retention_sections)

    def test_retention_skip_reasons_are_closed_and_do_not_create_quotas(self) -> None:
        section = self.memory.split("## 创建或重配身份", 1)[1].split(
            "## 按需记录完成与经验", 1
        )[0]
        compact = re.sub(r"\s+", "", section)
        for reason in (
            "未采用或结果未定",
            "失败或中断",
            "一次性数据摘录且无可复用职责",
            "无法安全去敏",
            "已有兼容身份",
            "同族运行时复制",
            "未选胜者的配置变体",
            "权限或身份无法安全核对",
        ):
            self.assertIn(reason, compact)
        combined = self.stack + self.dispatch + self.memory
        self.assertNotRegex(combined, r"(?:保留|复用).{0,12}\d+(?:\.\d+)?%")
        self.assertNotRegex(combined, r"每\s*\d+\s*(?:次|个).{0,12}(?:保留|ensure)")
        self.assertIn("不回填历史运行", self.memory)
        self.assertIn("同族已存在就复用或按 CAS 重配，绝不新建", self.memory)

    def test_retained_failure_record_and_loaded_script_path_contract(self) -> None:
        self.assertIn("全部满足时才可执行 `ensure`", self.stack)
        self.assertIn("无新增经验", self.stack)
        self.assertIn("也无需 `run_id`", self.stack)
        self.assertIn("即便没有新增 `--lesson` 也可选择性 `ensure`", self.memory)
        self.assertIn("保留身份本身无需旧经验、数据库签发收据或`run_id`，不因此执行`complete-run`", re.sub(r"\s+", "", self.memory))
        self.assertIn("跳过完成记账，但不影响符合上述条件的 `ensure`", self.memory)
        self.assertIn("只有新增一条去敏、带适用范围和证据限制的跨任务经验时才调用`complete-run`", re.sub(r"\s+", "", self.memory))
        self.assertIn("`--outcome failure` 且不附 `--lesson`", self.memory)
        self.assertIn("运行中、中断、未采用或结果未定均不算失败", self.memory)
        for part in ("情境", "停止依据", "重开条件"):
            self.assertIn(part, self.memory)
        self.assertIn("从当前已加载的`lean-stack/SKILL.md`的绝对路径取得技能目录", re.sub(r"\s+", "", self.memory))
        self.assertIn("$leanStackScript = Join-Path (Split-Path -Parent $leanStackSkillPath) 'scripts/agents.py'", self.memory)
        self.assertIn("相对脚本路径示例只适用于本插件源码仓库根", self.memory)
        self.assertIn("无新增经验的成功结果不执行 `complete-run`", self.flowcharts)
        self.assertIn("身份权限安全绑定后 ensure，无需旧经验收据或 run_id", self.flowcharts)
        self.assertIn("complete-run failure 不附 lesson", self.flowcharts)

    def test_dispatch_and_ensure_do_not_require_auxiliary_preflight(self) -> None:
        compact_dispatch = re.sub(r"\s+", "", self.dispatch)
        self.assertIn("只对该身份做一次有界`recall`", compact_dispatch)
        compact_memory = re.sub(r"\s+", "", self.memory)
        for phrase in (
            "成功后立即派发",
            "TOML的`developer_instructions`已原生注入经验",
            "任务卡只传五行真实状态，不复制经验正文",
            "子代理读已注入经验一次即开始任务",
            "复用或派发前不核验旧经验签发收据、文件句柄或成本基线到期状态",
        ):
            self.assertIn(phrase, compact_dispatch)
        for phrase in (
            "运行时角色首次产生已核验且被父任务实际采用的结果后",
            "父代理按`ensure`返回的成功或冲突回执记录实际结果",
            "健康结构下新增经验直接按需保存，不等待历史",
            "只有需要声称某版旧经验参与该次并发完成结果时",
            "由`agents.py`执行并以成功、冲突或跳过回执判定",
        ):
            self.assertIn(phrase, compact_memory)
        self.assertIn("普通子代理调用、复用、召回、`ensure` 和 `complete-run` 不触发成本状态查询", self.cost)
        self.assertIn("不阻塞派发或 ensure", self.flowcharts)

    def test_ensure_create_and_reconfigure_have_distinct_safe_triggers(self) -> None:
        section = self.memory.split("## 创建或重配身份", 1)[1].split(
            "## 按需记录完成与经验", 1
        )[0]
        compact = re.sub(r"\s+", "", section)
        for condition in (
            "原生目录无同能力族、权限及证据边界兼容的身份",
            "本轮没有有效台账目录时，先只读一次 `status --for-routing`",
            "定向 `recall` 最相关候选",
            "确认没有兼容身份后，才`ensure`",
            "已有同身份且能力族、权限、证据边界兼容",
            "先核验并采用配置胜者",
            "当前可用SHA执行`--expected-sha256`CAS",
            "权限不扩大",
            "没有新增`--lesson`也可选择性`ensure`",
            "无需旧经验、数据库签发收据或`run_id`",
            "若已有竞争变更，重新判断胜者",
        ):
            self.assertIn(re.sub(r"\s+", "", condition), compact)
        long_running = re.sub(r"\s+", "", read(REFS / "long-running.md"))
        self.assertIn("可按需首次`ensure`，依据脚本的创建或冲突回执判定", long_running)
        self.assertIn("已有身份重配和`complete-run`才要求身份及当前CAS快照", long_running)

    def test_routing_status_is_only_for_first_ensure_without_a_valid_catalog(self) -> None:
        combined = re.sub(r"\s+", "", self.dispatch + self.memory)
        self.assertIn("派发前不执行`status--for-routing`", combined)
        self.assertIn("拟首次`ensure`新身份", combined)
        self.assertIn("本轮没有有效台账目录", combined)
        self.assertIn("只读一次`status--for-routing`", combined)
        self.assertIn("未加载身份不能冒充当前可调用", combined)
        self.assertIn("避免未加载同族重复建档", combined)
        self.assertNotIn("每次派发前执行`status--for-routing`", combined)

    def test_cheap_model_is_limited_to_bounded_fact_work(self) -> None:
        combined = re.sub(r"\s+", "", self.stack + self.dispatch)
        self.assertIn("有界读取、结构化提取和事实总结", combined)
        self.assertIn("建议、取舍、合规判断、审查结论", combined)
        self.assertIn("至少使用合适的Sol", combined)
        self.assertIn("已保留身份也不能绕过", combined)

    def test_machine_identity_and_display_name_are_distinct(self) -> None:
        for term in ("agent_ref", "display_name", "lean_*", "中文展示名"):
            self.assertIn(term, self.memory + self.dispatch)
        self.assertIn("只用于用户界面", self.memory)
        self.assertIn("稳定机器身份", self.memory)

    def test_persistence_safety_boundaries_remain_authoritative(self) -> None:
        compact = re.sub(r"\s+", "", self.memory)
        for boundary in (
            "单硬链接",
            "owner token",
            "SHA-256",
            "CAS",
            "幂等重放",
            "SQLite 事务串行化使用同一台账的写者",
            "恢复不完整须显式报错",
            "Windows 上已覆盖的受管 TOML 重配、删除和跨名称迁移",
            "归档目录整体搬移仍是路径级保护",
            "POSIX 仍依赖合作写者",
            "SQLite 与文件系统不是共同原子事务",
            "进程崩溃后的跨存储恢复仍有缺口",
            "不得依据相同正文",
            "第二次明确失败",
            "format_version",
            "experience_corrections",
        ):
            self.assertIn(re.sub(r"\s+", "", boundary), compact)
        for receipt_boundary in ("机器身份", "同一 `run_id`", "随机收据", "数据库签发"):
            self.assertIn(receipt_boundary, self.memory)
        self.assertIn("global_contract", self.memory)

    def test_source_and_write_ownership_still_have_machine_readable_receipts(self) -> None:
        self.assertIn("SOURCE_ROUTE", self.source_results)
        self.assertIn("SOURCE_COVERAGE", self.source_results)
        self.assertIn("WRITE_ROUTE", self.write_parallelism)
        for boundary in ("唯一完整读取者", "快照变化", "不重读"):
            self.assertIn(boundary, self.source_results)
        for boundary in ("物理目标", "唯一写入者", "精确归因", "禁止整树回退"):
            self.assertIn(boundary, self.write_parallelism)

    def test_flowcharts_use_semantic_sections_without_a_numeric_total(self) -> None:
        blocks = re.findall(r"```mermaid\n(.*?)\n```", self.flowcharts, re.S)
        self.assertGreater(len(blocks), 1)
        self.assertTrue(all(block.startswith("flowchart ") for block in blocks))
        for behavior in (
            "live child",
            "运行时复制",
            "Windows exec",
            "SOURCE_COVERAGE",
            "WRITE_ROUTE",
            "recall run-id",
            "v4 v5 v6 v7",
            "complete-run",
        ):
            self.assertIn(behavior, self.flowcharts)
        self.assertNotRegex(self.flowcharts, r"当前\s*[0-9一二三四五六七八九十]+\s*条")
        self.assertNotRegex(self.flowcharts, r"辅链[一二三四五六七八九十0-9]+")
        self.assertIn("图的数量没有目标或上限", self.flowcharts)
        self.assertIn("不为凑总数拆图", self.flowcharts)

    def test_five_line_opening_is_consistent_in_delegation_documents(self) -> None:
        prompt = self.manifest["interface"]["defaultPrompt"][0]
        documents = (
            self.dispatch,
            read(REFS / "collaboration.md"),
            self.versioning,
            self.openai_yaml,
            self.readme,
            prompt,
        )
        for document in documents:
            self.assertIn("五行", document)
            self.assertIn("final", document)
            self.assertIn("前三行", document)
            self.assertNotRegex(document, r"(?m)^经验：未核验")
            self.assertNotIn("经验：未加载保留经验", document)
            self.assertIn("本次任务上下文", document)

    def test_manifest_and_skill_prompt_publish_current_behavior(self) -> None:
        prompt = self.manifest["interface"]["defaultPrompt"][0]
        for term in ("$lean-stack", "live child", "agent_type", "三行", "进展说明"):
            self.assertIn(term, prompt)
            self.assertIn(term, self.openai_yaml)
        self.assertIn("xhigh 只是上限", prompt)
        for surface in (prompt, self.openai_yaml):
            self.assertIn("保留类型优先", surface)
            self.assertIn("采用后判断保留", surface)
            self.assertIn("运行时经验行写“本次任务上下文”", surface)

    def test_standard_install_does_not_require_global_instruction_edits(self) -> None:
        self.assertIn("Standard plugin installation does not edit global instructions", self.readme)
        self.assertIn("只授权更新插件时使用普通安装命令，不修改全局文件", self.versioning)
        self.assertIn("明确授权修改全局默认调用指令", self.versioning)

    def test_current_release_surfaces_share_one_numeric_version(self) -> None:
        manifest_version = self.manifest["version"].split("+", 1)[0]
        readme_match = re.search(r"Current version: \*\*([^*]+)\*\*", self.readme)
        changelog_match = re.search(r"(?m)^## ([0-9]+\.[0-9]+\.[0-9]+) - ", self.changelog)
        self.assertIsNotNone(readme_match)
        self.assertIsNotNone(changelog_match)
        assert readme_match is not None and changelog_match is not None
        self.assertEqual(
            (readme_match.group(1), changelog_match.group(1)),
            (manifest_version, manifest_version),
        )
        self.assertIn("子代理", self.openai_yaml.splitlines()[2])
        simplify_yaml = read(SIMPLIFY / "agents" / "openai.yaml")
        self.assertIn("精简", simplify_yaml.splitlines()[2])

    def test_formal_host_acceptance_keeps_runtime_evidence_boundaries(self) -> None:
        section = self.versioning.split("## 正式宿主行为验收", 1)[1].split(
            "公共行为确定", 1
        )[0]
        for boundary in ("正式安装", "独立父代理任务", "原生调用记录", "未完成", "不能为满足这条规则自行扩权"):
            self.assertIn(boundary, section)
        self.assertIn("静态合同只能证明公开文字与链接", self.simplify)
        self.assertIn("不能由当前源码读取", self.simplify)

    def test_simplification_preserves_active_work_and_decisive_recheck(self) -> None:
        method = self.simplify.split("## 最小完整方法", 1)[1].split(
            "## 条件路由", 1
        )[0]
        for boundary in ("最早一个尚未完成", "已交付事项退出活动清单", "先修真实根因", "一次能区分修复前后的复验", "目标条件已覆盖就"):
            self.assertIn(boundary, method)

    def test_release_notes_and_handoff_are_not_runtime_authorities(self) -> None:
        public_runtime = self.stack + self.simplify
        self.assertNotIn("CHANGELOG.md", public_runtime)
        self.assertNotIn("Jiao-Jie.md", public_runtime)
        self.assertNotIn("test_current_release_surfaces", read(ROOT / "CHANGELOG.md"))


if __name__ == "__main__":
    unittest.main()
