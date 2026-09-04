from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import tomllib
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "lean-stack" / "scripts" / "agents.py"
SPEC = importlib.util.spec_from_file_location("lean_stack_agents", SCRIPT)
assert SPEC and SPEC.loader
agents = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agents)


class SpecialistRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.codex_home = Path(self.temporary.name) / "codex-home"
        self.registry = agents.SpecialistRegistry(self.codex_home)

    @staticmethod
    def contract(domain: str = "界面绑定诊断") -> dict[str, object]:
        return {
            "domain": domain,
            "input_shapes": ["源代码、运行证据和边界说明"],
            "responsibilities": ["重复核对根因并给出可验证结论"],
            "deliverables": ["精炼结论、证据和剩余缺口"],
            "hard_boundaries": ["不扩大权限，不修改未分配文件"],
        }

    def ensure(
        self,
        *,
        role_key: str = "qml-binding-diagnostics",
        authority: str = "read",
        display_name: str | None = None,
        description: str = "重复完成一个边界清晰、可复核的专门工作。",
        role_instructions: str = "交付直接可消费的结果和必要证据。",
        model: str = "gpt-5.6-terra",
        effort: str = "high",
        speed: str | None = None,
        expected_sha256: str | None = None,
        global_domain_key: str = "interface-binding-diagnostics",
        global_contract: dict[str, object] | None = None,
        origin_terms: tuple[str, ...] = ("当前任务来源",),
    ):
        return self.registry.ensure(
            role_key=role_key,
            display_name=display_name
            or ("QML 绑定诊断员" if role_key.startswith("qml") else "回归测试执行员"),
            description=description,
            role_instructions=role_instructions,
            model=model,
            effort=effort,
            authority=authority,
            speed=speed,
            expected_sha256=expected_sha256,
            global_domain_key=global_domain_key,
            global_contract=global_contract or self.contract(),
            origin_terms=origin_terms,
        )

    def db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.registry.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def improve_with_lesson(self, **kwargs):
        kwargs.setdefault("origin_terms", ("当前任务来源",))
        return self.registry.improve_with_lesson(**kwargs)

    def improve_with_summary(self, **kwargs):
        kwargs.setdefault("origin_terms", ("当前任务来源",))
        return self.registry.improve_with_summary(**kwargs)

    def downgrade_registry(self, version: int) -> list[dict[str, str]]:
        if version not in (1, 2, 3):
            raise AssertionError(version)
        with contextlib.closing(self.db()) as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM agents")]
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE agents")
            connection.execute(agents.SCHEMA_V2_TABLE_SQL["agents"])
            for row in rows:
                path = Path(row["path"])
                legacy_lines = [
                    line for line in path.read_text(encoding="utf-8").splitlines()
                    if not line.startswith((
                        agents.GLOBAL_SCOPE_PREFIX,
                        agents.GLOBAL_DOMAIN_KEY_PREFIX,
                        agents.GLOBAL_CONTRACT_DIGEST_PREFIX,
                    ))
                ]
                legacy_data = ("\n".join(legacy_lines) + "\n").encode("utf-8")
                path.write_bytes(legacy_data)
                row["expected_sha256"] = agents.sha256_bytes(legacy_data)
                connection.execute(
                    "INSERT INTO agents(agent_id,name,role_key,path,owner_token,expected_sha256,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    tuple(row[key] for key in (
                        "agent_id", "name", "role_key", "path", "owner_token",
                        "expected_sha256", "created_at", "updated_at",
                    )),
                )
            if version == 1:
                connection.execute("ALTER TABLE experience_events RENAME TO experience_events_v2")
                connection.execute(agents.SCHEMA_V1_TABLE_SQL["experience_events"])
                connection.execute(
                    "INSERT INTO experience_events(sequence,agent_id,event_id,event_digest,lesson,created_at) "
                    "SELECT sequence,agent_id,event_id,event_digest,lesson,created_at FROM experience_events_v2"
                )
                connection.execute("DROP TABLE experience_events_v2")
                connection.execute("DROP TABLE agent_runs")
            elif version == 2:
                connection.execute("DROP TABLE agent_runs")
            connection.execute(f"PRAGMA user_version = {version}")
            connection.execute("COMMIT")
        return rows

    def write_migration_plan(
        self,
        rows: list[dict[str, str]],
        *,
        corrections: dict[str, list[dict[str, str]]] | None = None,
    ) -> Path:
        roles = []
        for row in rows:
            roles.append({
                "old_name": row["name"],
                "old_role_key": row["role_key"],
                "expected_sha256": row["expected_sha256"],
                "new_role_key": row["role_key"],
                "display_name": "领域复用核对员",
                "description": "跨任务、跨项目、跨会话重复核对同类输入。",
                "instructions": "核对输入形状，返回证据充分的领域结论。",
                "global_domain_key": "reusable-domain-review",
                "global_contract": self.contract("可复用领域审核"),
                "origin_terms": ["当前项目专属来源"],
                "experience_corrections": (corrections or {}).get(row["name"], []),
            })
        plan = Path(self.temporary.name) / f"migration-{uuid.uuid4().hex}.json"
        plan.write_text(
            json.dumps({"format_version": 1, "roles": roles}, ensure_ascii=False),
            encoding="utf-8",
        )
        return plan

    def test_ensure_creates_one_specialist_and_reuses_the_same_role(self) -> None:
        first = self.ensure()
        second = self.ensure()

        self.assertEqual(first["action"], "created")
        self.assertEqual(first["host_visibility"], "requires_new_task")
        self.assertEqual(
            first["current_task_fallback"],
            agents.INTERNAL_MESSAGE_RUNTIME_ROUTE,
        )
        self.assertEqual(second["action"], "reused")
        self.assertTrue(second["compatible"])
        self.assertEqual(first["name"], second["name"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)

        payload = tomllib.loads(Path(first["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], first["name"])
        self.assertEqual(payload["sandbox_mode"], "read-only")
        self.assertNotIn("service_tier", payload)
        self.assertNotIn("features", payload)
        self.assertNotIn("agents", payload)
        self.assertIs(payload["skills"]["include_instructions"], False)
        instructions = payload["developer_instructions"]
        role_paragraph = (
            "你是专门负责“QML 绑定诊断员”的子代理，"
            "可复用专长标识为 qml-binding-diagnostics。"
        )
        self.assertTrue(instructions.startswith(role_paragraph))
        first_paragraph = instructions.split("\n\n", 1)[0]
        self.assertIn("交付直接可消费的结果和必要证据", first_paragraph)
        self.assertIn("保持只读", first_paragraph)
        opening = (
            "我是QML 绑定诊断员。\n"
            "模型：gpt-5.6-terra\n"
            "思考程度：high\n"
            "速度：标准\n"
        )
        self.assertIn(opening, instructions)
        role = instructions.index(role_paragraph)
        communication = instructions.index(
            "需要在这个子任务中分别向父代理和用户声明实际配置",
            role,
        )
        direct_channel = instructions.index("collaboration.send_message", communication)
        declaration = instructions.index(opening, direct_channel)
        visible = instructions.index(
            "自己的代理线程（用户可见任务界面）以 commentary",
            declaration,
        )
        final_result = instructions.index("最终回复固定写", visible)
        final_declaration = instructions.index(opening, final_result)
        final_task = instructions.index("子任务：<当前子任务>", final_declaration)
        self.assertEqual(instructions.count(opening), 2)
        self.assertLess(role, communication)
        self.assertLess(direct_channel, declaration)
        self.assertLess(final_result, final_declaration)
        self.assertLess(final_declaration, final_task)
        for opening_contract in (
            "父代理规范任务名作为消息目标（例如 /root）",
            "这个目标不是 Codex threadId",
            "multi_agent_version=v2",
            "角色 TOML 不能替父会话授予协作工具",
            "collaboration.send_message 故意不在 functions.exec 的 ALL_TOOLS 中",
            "必须直接用 collaboration.send_message",
            "list_threads 搜索父任务",
            "send_message_to_thread 等跨任务 API 替代内部消息",
            "按当前任务卡和三项原则直接授权的父代理跨任务协作不受影响",
            "直接调用不存在或报错时",
            "自己的代理线程（用户可见任务界面）以 commentary",
            "reasoning、文件读取、分析、其他工具调用和真实工作之间不设固定先后顺序",
            "不能因为这些事件出现在声明前后就判定通信失败",
            "成功路线的内部副本和用户可见副本缺一不可",
            "公开副本不能冒充内部消息",
            "在最终回复报告缺口",
            "内部交流是成功条件就停止",
            "无需中途纠偏的自包含任务",
            "不能宣称内部交流可用",
            "不能省略或只留到关键步骤、最终回复",
            "最终回复顶部再次写实际模型、思考程度和速度",
            "声明不要求父代理确认",
            "声明不要求父代理确认，不计入关键步骤",
            "父代理用 send_message 纠偏不算启动新子任务，不重复开场声明",
            "三个字段不能省略",
        ):
            self.assertIn(opening_contract, instructions)
        for obsolete_order_contract in (
            "你的第一动作必须",
            "第二动作必须紧接着",
            "显示前不得读取、分析或调用其他工具",
        ):
            self.assertNotIn(obsolete_order_contract, instructions)
        self.assertIn("QML 绑定诊断员", instructions)
        self.assertIn(
            "先读取本配置末尾的可复用经验",
            instructions,
        )
        self.assertIn(
            "父代理无需重复注入经验或强制重写已有配置",
            instructions,
        )
        for coordination_contract in (
            "默认协作角色是普通子代理，不自行再委派",
            "协作角色: 协作父代理",
            "允许下游委派: 是",
            "有限下游范围",
            "真实拥有顶层 collaboration.spawn_agent",
            "不得用 functions.exec 的 ALL_TOOLS、角色 TOML、模型目录或历史任务猜测能力",
            "停止下游委派并向父代理报告",
            "协作父代理对每个下游切片继续应用三项原则",
            "高价值工作质量优先",
            "普通工作达到质量底线后速度优先",
            "没有相应质量或速度收益时不让总成本大幅增加",
            "安全、权限、数据完整性、明确验收条件和诚实证据始终是底线",
            "给每个下游子代理单独写完整任务卡",
            "task_id",
            "协作角色",
            "目标",
            "任务类型与任务类型组",
            "子代理来源与运行配置",
            "权威来源或输入快照",
            "依赖与已就绪切片",
            "写入所有权",
            "是否允许下游委派及下游范围",
            "是否允许调用其他或新建 Codex 父代理及跨任务范围",
            "父代理规范任务名",
            "成功条件",
            "停止条件",
            "有限关键步骤",
            "证据与返回格式",
            "先确定下游任务类型和任务类型组",
            "复用可见保留子代理时由它自读已有配置",
            "定制运行时新子代理时由你根据任务类型、价值、风险、证据、时延和成本",
            "联合选择并写出具体模型、思考程度和标准或快速速度组成的完整配置",
            "不能分列独立选择",
            "不得使用继承、未揭露或未暴露",
            "默认把下游的允许下游委派写为否",
            "下游子代理仍在自己的线程提交自己的最终结果",
            "不能压掉、改写或冒充这些结果",
            "只有任务卡明确写允许调用其他或新建 Codex 父代理为是并给出跨任务范围",
            "create_thread、read_thread、wait_threads 或 send_message_to_thread",
            "不需要再向用户询问",
            "所有跨任务动作还必须同时满足当前工具合同",
            "create_thread 要求用户明确提出新建任务",
            "任务卡或插件默认授权不能替代",
            "不能为内部委派创建用户可见新任务",
            "已有用户授权无需重复询问",
            "跨任务工具不能冒充内部消息",
            "不得建立非授权留言板、缓存或日志暗渠",
            "不得共享凭据或私密数据",
            "不得以集体利益、未回复或无人否决扩大权限",
            "不得伪造、删除、编辑或隐藏消息、工具调用、测试、日志、文件变更、身份、权限和来源",
            "最近的协作授权不改变原有删除、删减或候选清理的资格与尺度",
            "原规则判定应删的目标仍处理",
            "原规则不允许删的目标仍不处理",
            "普通删除不得物理销毁",
            "普通文件精确送入 Windows 回收站",
            "重要文件精确移入任务专属待删文件",
            "直接普通文件、单一硬链接、零经验和零存活轮次资格判断",
            "合格 TOML与收据移入插件专属待删文件",
            "不合格目标保持原位并报告",
        ):
            self.assertIn(coordination_contract, instructions)
        self.assertIn(
            "先选唯一子代理、再维护经验、最后结束其他子代理",
            instructions,
        )
        for task_contract in (
            "组内复制或变体",
            "父代理分配的当前子任务",
            "为该子任务单独指定的成功条件",
            "有限关键步骤清单",
            "没有预设关键步骤时不自行追加",
            "每完成一个预设关键步骤，只发送一条短消息并立即继续，不等待父代理",
            "每个关键步骤最多一条常规进度",
            "同一方向风险只有状态实质变化后才能再次报告",
            "不发送定时心跳或纯确认消息",
            "父代理无异议时可沉默",
            "收到纠偏或任务目标更新后直接应用并继续",
            "不得扩大用户授权、移除停止条件或让任务无限延伸",
            "关键步骤：",
            "情况：",
            "下一步：",
            "在自己的线程用最终回复提交自己的精炼结果",
            "不建立共享中转文件",
            "不代交、等待或汇总其他子代理的结果",
            "任务卡明确指定的协作父代理只整合自己下游子代理已经独立提交的结果",
            "不预先合并结果",
            "状态：完成 | 部分完成 | 受阻",
            "证据或缺口：",
            "SOURCE_COVERAGE",
        ):
            self.assertIn(task_contract, instructions)
        self.assertIn("不决定胜者", instructions)
        self.assertIn(
            "禁止用未揭露、继承父级等占位文字",
            instructions,
        )

    def test_role_instructions_cannot_collide_with_internal_memory_heading(self) -> None:
        with self.assertRaisesRegex(
            agents.SpecialistError,
            "cannot contain the internal memory heading",
        ):
            self.ensure(
                role_instructions=(
                    "先核对输入。" + agents.MEMORY_HEADER.strip() + "不得截断后续说明。"
                )
            )

    def test_utf8_memory_window_uses_exact_agent_capacity_without_6k_cap(self) -> None:
        with self.assertRaisesRegex(
            agents.SpecialistError,
            "summary plus its label must fit",
        ):
            agents.validate_summary("中" * agents.MAX_SUMMARY_CHARS)

        base = agents.base_instructions(
            display_name="长说明核对员",
            role_key="long-instruction-review",
            role_instructions="逐项核对输入边界和决定性证据。" * 55,
            model="gpt-5.6-luna",
            effort="medium",
            authority="read",
            global_contract=self.contract(),
            speed="standard",
        )
        render_args = {
            "agent_id": "00000000-0000-4000-8000-000000000000",
            "role_key": "long-instruction-review",
            "owner_token": "0" * 32,
            "name": "lean_long_instruction_review_00000000",
            "display_name": "长说明核对员",
            "description": "重复审查长说明。",
            "model": "gpt-5.6-luna",
            "effort": "medium",
            "authority": "read",
            "instruction_base": base,
            "speed": "standard",
            "global_domain_key": "instruction-review",
            "global_contract_digest": "0" * 64,
        }

        def render(candidate: str) -> bytes:
            return agents._render_agent_bytes(**render_args, memory=candidate)

        memory = self.registry._memory_for_toml(
            "保留可复用摘要。",
            [{"lesson": "证据充分。" * 500}],
            fits=lambda candidate: len(render(candidate)) <= agents.MAX_AGENT_BYTES,
        )
        combined = agents.compose_instructions(base, memory)
        built = agents.build_agent_bytes(**render_args, memory=memory)
        self.assertGreater(len(combined.encode("utf-8")), 6 * 1024)
        self.assertLessEqual(len(memory.encode("utf-8")), agents.MAX_MEMORY_BYTES)
        self.assertLessEqual(len(built), agents.MAX_AGENT_BYTES)

    def test_single_experience_character_bound_does_not_cap_event_count(self) -> None:
        accepted = agents.validate_lesson("经" * agents.MAX_LESSON_CHARS)
        self.assertEqual(len(accepted), agents.MAX_LESSON_CHARS)
        with self.assertRaisesRegex(
            agents.SpecialistError,
            f"1-{agents.MAX_LESSON_CHARS} characters",
        ):
            agents.validate_lesson("经" * (agents.MAX_LESSON_CHARS + 1))

    def test_memory_window_checks_exact_serialized_toml_size(self) -> None:
        render_args = {
            "agent_id": "00000000-0000-4000-8000-000000000000",
            "role_key": "capacity-review",
            "owner_token": "0" * 32,
            "name": "lean_capacity_review_00000000",
            "display_name": "容量核对员",
            "description": "核对容量。",
            "model": "gpt-5.6-luna",
            "effort": "medium",
            "authority": "read",
            "instruction_base": "中" * 4800,
            "speed": "standard",
            "global_domain_key": "capacity-review",
            "global_contract_digest": "0" * 64,
        }

        def render(candidate: str) -> bytes:
            return agents._render_agent_bytes(**render_args, memory=candidate)

        empty = agents.memory_block("", [])
        self.assertLessEqual(len(render(empty)), agents.MAX_AGENT_BYTES)
        memory = self.registry._memory_for_toml(
            "",
            [{"lesson": "证据充分。" * 100}],
            fits=lambda candidate: len(render(candidate)) <= agents.MAX_AGENT_BYTES,
        )
        self.assertEqual(memory, empty)
        with self.assertRaisesRegex(
            agents.SpecialistError,
            "generated agent exceeds 16 KiB",
        ):
            agents.build_agent_bytes(
                **render_args,
                memory=agents.memory_block("", ["证据充分。" * 100]),
            )

    def test_fast_speed_writes_official_config_and_three_field_opening(self) -> None:
        created = self.ensure(
            role_key="fast-source-review",
            display_name="快速来源核对员",
            effort="medium",
            speed="fast",
        )

        payload = tomllib.loads(Path(created["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["service_tier"], "fast")
        self.assertNotIn("features", payload)
        self.assertNotIn("agents", payload)
        self.assertIs(payload["skills"]["include_instructions"], False)
        instructions = payload["developer_instructions"]
        self.assertTrue(instructions.startswith("你是专门负责“快速来源核对员”的子代理"))
        opening = (
            "我是快速来源核对员。\n"
            "模型：gpt-5.6-terra\n"
            "思考程度：medium\n"
            "速度：快速\n"
        )
        self.assertEqual(instructions.count(opening), 2)
        self.assertLess(instructions.index("你是专门负责"), instructions.index(opening))
        self.assertLess(
            instructions.index("自己的代理线程（用户可见任务界面）以 commentary"),
            instructions.index("只完成父代理分配的当前子任务"),
        )
        self.assertLess(
            instructions.index("最终回复固定写"),
            instructions.rindex(opening),
        )

    def test_ensure_omitted_speed_defaults_luna_fast_and_other_models_standard(self) -> None:
        luna = self.ensure(
            role_key="luna-default-speed-review",
            global_domain_key="luna-default-speed-review",
            model="gpt-5.6-luna",
            effort="medium",
        )
        terra = self.ensure(
            role_key="terra-default-speed-review",
            global_domain_key="terra-default-speed-review",
            model="gpt-5.6-terra",
            effort="medium",
        )
        explicit_standard = self.ensure(
            role_key="luna-explicit-standard-review",
            global_domain_key="luna-explicit-standard-review",
            model="gpt-5.6-luna",
            effort="medium",
            speed="standard",
        )

        luna_payload = tomllib.loads(Path(luna["path"]).read_text(encoding="utf-8"))
        terra_payload = tomllib.loads(Path(terra["path"]).read_text(encoding="utf-8"))
        standard_payload = tomllib.loads(
            Path(explicit_standard["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(luna_payload["service_tier"], "fast")
        self.assertIn("速度：快速", luna_payload["developer_instructions"])
        self.assertNotIn("service_tier", terra_payload)
        self.assertIn("速度：标准", terra_payload["developer_instructions"])
        self.assertNotIn("service_tier", standard_payload)

    def test_luna_default_fast_reconfiguration_requires_cas_and_preserves_identity(self) -> None:
        created = self.ensure(
            role_key="luna-default-reconfiguration",
            global_domain_key="luna-default-reconfiguration",
            model="gpt-5.6-luna",
            effort="medium",
            speed="standard",
        )
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson="安全重配必须保留身份、所有权和既有经验。",
            event_id=str(uuid.uuid4()),
        )
        path = Path(created["path"])
        before = path.read_bytes()

        preview = self.ensure(
            role_key="luna-default-reconfiguration",
            global_domain_key="luna-default-reconfiguration",
            model="gpt-5.6-luna",
            effort="medium",
        )
        self.assertEqual(preview["action"], "reconfiguration_required")
        self.assertEqual(path.read_bytes(), before)

        reconfigured = self.ensure(
            role_key="luna-default-reconfiguration",
            global_domain_key="luna-default-reconfiguration",
            model="gpt-5.6-luna",
            effort="medium",
            expected_sha256=improved["sha256"],
        )
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(reconfigured["action"], "reconfigured")
        self.assertEqual(reconfigured["agent_id"], created["agent_id"])
        self.assertEqual(reconfigured["owner_token"], created["owner_token"])
        self.assertEqual(reconfigured["path"], created["path"])
        self.assertEqual(payload["service_tier"], "fast")
        self.assertIn("安全重配必须保留身份", payload["developer_instructions"])

        fast_bytes = path.read_bytes()
        explicit_standard = self.ensure(
            role_key="luna-default-reconfiguration",
            global_domain_key="luna-default-reconfiguration",
            model="gpt-5.6-luna",
            effort="medium",
            speed="standard",
        )
        self.assertEqual(explicit_standard["action"], "reconfiguration_required")
        self.assertEqual(path.read_bytes(), fast_bytes)

    def test_distinct_reusable_work_gets_distinct_writable_or_read_specialists(self) -> None:
        reader = self.ensure(role_key="qml-binding-diagnostics", authority="read")
        writer = self.ensure(role_key="python-regression-implementation", authority="write")

        reader_payload = tomllib.loads(Path(reader["path"]).read_text(encoding="utf-8"))
        writer_payload = tomllib.loads(Path(writer["path"]).read_text(encoding="utf-8"))
        self.assertEqual(reader_payload["sandbox_mode"], "read-only")
        self.assertEqual(writer_payload["sandbox_mode"], "workspace-write")
        self.assertNotEqual(reader["name"], writer["name"])
        self.assertNotIn("唯一工程执行员", writer_payload["developer_instructions"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 2)

    def test_new_database_has_only_owned_specialist_memory_and_run_tables(self) -> None:
        self.ensure()
        with contextlib.closing(self.db()) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(
            tables,
            {"agents", "experience_events", "experience_summaries", "agent_runs"},
        )
        self.assertEqual(version, 4)
        for removed in (
            "leases",
            "evaluations",
            "project_routes",
            "candidates",
            "operations",
            "variation_sessions",
        ):
            self.assertNotIn(removed, tables)

    def test_unversioned_unknown_database_is_never_initialized_or_migrated(self) -> None:
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            connection.execute("CREATE TABLE legacy_data(value TEXT)")
            connection.execute("INSERT INTO legacy_data(value) VALUES('keep-me')")
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            objects = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            value = connection.execute("SELECT value FROM legacy_data").fetchone()[0]
        self.assertEqual(objects, {"legacy_data"})
        self.assertEqual(version, 0)
        self.assertEqual(value, "keep-me")

    def test_versioned_database_with_wrong_columns_is_rejected_before_use(self) -> None:
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE agents(agent_id TEXT PRIMARY KEY);
                CREATE TABLE experience_events(sequence INTEGER PRIMARY KEY);
                CREATE TABLE experience_summaries(agent_id TEXT PRIMARY KEY);
                PRAGMA user_version = 1;
                """
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            columns = [
                row[1] for row in connection.execute("PRAGMA table_info(agents)")
            ]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(columns, ["agent_id"])
        self.assertEqual(version, 1)

    def test_versioned_database_with_missing_constraints_is_rejected(self) -> None:
        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role_key TEXT NOT NULL,
                    path TEXT NOT NULL,
                    owner_token TEXT NOT NULL,
                    expected_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE experience_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE experience_summaries (
                    agent_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    covered_through_sequence INTEGER NOT NULL,
                    source_digest TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                PRAGMA user_version = 1;
                """
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        with contextlib.closing(sqlite3.connect(self.registry.db_path)) as connection:
            unique_indexes = [
                row for row in connection.execute("PRAGMA index_list(agents)")
            ]
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)
        self.assertEqual(len(unique_indexes), 1)

    def test_versioned_database_with_extra_trigger_is_rejected(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                """
                CREATE TRIGGER unexpected_agent_update
                BEFORE UPDATE ON agents
                BEGIN
                    SELECT RAISE(IGNORE);
                END
                """
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        self.assertEqual(path.read_bytes(), before)

    def test_versioned_database_with_extra_named_index_is_rejected(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "CREATE INDEX unexpected_agent_timestamp ON agents(updated_at)"
            )
            connection.commit()

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        self.assertEqual(path.read_bytes(), before)

    def test_unowned_managed_role_file_blocks_duplicate_creation(self) -> None:
        role_key = "qml-binding-diagnostics"
        agent_id = str(uuid.uuid4())
        owner_token = uuid.uuid4().hex
        name = agents.specialist_name(role_key, agent_id)
        base = agents.base_instructions(
            display_name="QML 绑定诊断员",
            role_key=role_key,
            role_instructions="交付直接可消费的结果和必要证据。",
            model="gpt-5.6-terra",
            effort="high",
            authority="read",
        )
        data = agents.build_agent_bytes(
            agent_id=agent_id,
            role_key=role_key,
            owner_token=owner_token,
            name=name,
            display_name="QML 绑定诊断员",
            description="模拟文件落盘后、ledger 提交前的进程崩溃。",
            model="gpt-5.6-terra",
            effort="high",
            authority="read",
            instruction_base=base,
            memory=agents.memory_block("", []),
            global_domain_key="interface-binding-diagnostics",
            global_contract_digest=agents.normalize_global_contract(
                self.contract(), domain_key="interface-binding-diagnostics"
            )[1],
        )
        orphan_path = self.registry.agents_dir / "lean_renamed_orphan.toml"
        agents.write_new_file(orphan_path, data)

        with self.assertRaises(agents.AuxiliarySkipped):
            self.ensure()

        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)

    def test_ensure_reconfigures_one_role_with_cas_and_preserves_experience(self) -> None:
        created = self.ensure()
        lesson = "验证后的联合胜出配置必须保留已有经验。"
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=str(uuid.uuid4()),
        )
        path = Path(created["path"])
        before = path.read_bytes()

        preview = self.ensure(
            display_name="QML 根因核对员",
            description="采用验证后胜出的配置重复诊断 QML 根因。",
            role_instructions="先核对实际依赖图，再返回最小可复核修法。",
            model="gpt-5.6-luna",
            effort="medium",
            speed="fast",
            authority="write",
        )
        self.assertEqual(preview["action"], "reconfiguration_required")
        self.assertFalse(preview["compatible"])
        self.assertEqual(path.read_bytes(), before)

        reconfigured = self.ensure(
            display_name="QML 根因核对员",
            description="采用验证后胜出的配置重复诊断 QML 根因。",
            role_instructions="先核对实际依赖图，再返回最小可复核修法。",
            model="gpt-5.6-luna",
            effort="medium",
            speed="fast",
            authority="write",
            expected_sha256=improved["sha256"],
        )
        self.assertEqual(reconfigured["action"], "reconfigured")
        self.assertTrue(reconfigured["experience_preserved"])
        self.assertEqual(reconfigured["agent_id"], created["agent_id"])
        self.assertEqual(reconfigured["owner_token"], created["owner_token"])
        self.assertEqual(reconfigured["path"], created["path"])
        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["model_reasoning_effort"], "medium")
        self.assertEqual(payload["service_tier"], "fast")
        self.assertNotIn("features", payload)
        self.assertNotIn("agents", payload)
        self.assertIs(payload["skills"]["include_instructions"], False)
        self.assertEqual(payload["sandbox_mode"], "workspace-write")
        self.assertIn("QML 根因核对员", payload["description"])
        instructions = payload["developer_instructions"]
        self.assertTrue(instructions.startswith("你是专门负责“QML 根因核对员”的子代理"))
        self.assertLess(instructions.index("你是专门负责"), instructions.index("我是QML 根因核对员。"))
        self.assertIn("实际依赖图", instructions)
        self.assertIn(lesson, instructions)
        self.assertIn("由你自行声明", instructions)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )

    def test_ensure_reconfiguration_rejects_stale_cas_without_mutation(self) -> None:
        created = self.ensure()
        before = Path(created["path"]).read_bytes()
        with self.assertRaises(agents.SpecialistError):
            self.ensure(
                description="不同配置。",
                expected_sha256="0" * 64,
            )
        self.assertEqual(Path(created["path"]).read_bytes(), before)
        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 1)

    def test_old_lifecycle_database_is_never_opened_migrated_or_deleted(self) -> None:
        old = self.registry.old_db_path
        old.write_bytes(b"opaque-old-lifecycle-data")
        before = old.read_bytes()

        self.ensure()

        self.assertEqual(old.read_bytes(), before)
        self.assertNotEqual(old, self.registry.db_path)

    def test_astra_ultra_configuration_is_preserved_and_idempotent(self) -> None:
        first = self.ensure(model="gpt-6-astra", effort="ultra")
        second = self.ensure(model="gpt-6-astra", effort="ultra")
        payload = tomllib.loads(Path(first["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["model"], "gpt-6-astra")
        self.assertEqual(payload["model_reasoning_effort"], "ultra")
        self.assertEqual(second["action"], "reused")
        self.assertEqual(first["sha256"], second["sha256"])

    def test_configuration_evidence_boundary_survives_experience_rewrite(self) -> None:
        for speed in ("standard", "fast"):
            with self.subTest(speed=speed):
                created = self.ensure(
                    role_key=f"configuration-evidence-{speed}",
                    global_domain_key=f"configuration-evidence-{speed}",
                    speed=speed,
                )
                before = tomllib.loads(Path(created["path"]).read_text(encoding="utf-8"))
                self.improve_with_lesson(
                    name=created["name"], expected_sha256=created["sha256"],
                    lesson="区分配置请求和实际生效证据，避免错误报告运行状态。",
                    event_id=str(uuid.uuid4()),
                )
                after = tomllib.loads(Path(created["path"]).read_text(encoding="utf-8"))
                for payload in (before, after):
                    instructions = payload["developer_instructions"]
                    for boundary in ("不附请求值", "配置声明不等于实测速度", "无法选择所需档位", "修改全局配置"):
                        self.assertIn(boundary, instructions)
                self.assertEqual(before.get("service_tier"), after.get("service_tier"))
                self.assertEqual(after.get("service_tier"), "fast" if speed == "fast" else None)
                self.assertEqual(before["model"], after["model"])
                self.assertEqual(before["model_reasoning_effort"], after["model_reasoning_effort"])

    def test_experience_rewrite_preserves_fast_speed_configuration(self) -> None:
        created = self.ensure(role_key="fast-regression-review", speed="fast")
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson="快速配置下的经验重写必须保留速度设置。",
            event_id=str(uuid.uuid4()),
        )

        payload = tomllib.loads(Path(created["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["service_tier"], "fast")
        self.assertNotIn("features", payload)
        self.assertNotIn("agents", payload)
        self.assertIs(payload["skills"]["include_instructions"], False)
        self.assertIn("速度：快速", payload["developer_instructions"])
        self.assertEqual(improved["action"], "experience_recorded")

    def test_experience_rewrite_rejects_inconsistent_speed_configuration(self) -> None:
        created = self.ensure(role_key="inconsistent-speed-review")
        path = Path(created["path"])
        inconsistent = path.read_text(encoding="utf-8").replace(
            "[skills]\ninclude_instructions = false\n",
            "[features]\nfast_mode = false\n[skills]\ninclude_instructions = false\n",
            1,
        ).encode("utf-8")
        path.write_bytes(inconsistent)
        inconsistent_sha256 = agents.sha256_bytes(inconsistent)
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "UPDATE agents SET expected_sha256 = ? WHERE agent_id = ?",
                (inconsistent_sha256, created["agent_id"]),
            )
            connection.commit()

        with self.assertRaisesRegex(
            agents.SpecialistError,
            "speed configuration is incomplete or inconsistent",
        ):
            self.improve_with_lesson(
                name=created["name"],
                expected_sha256=inconsistent_sha256,
                lesson="这条经验不能写入矛盾速度配置。",
                event_id=str(uuid.uuid4()),
            )

        self.assertEqual(path.read_bytes(), inconsistent)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                0,
            )

    def test_experience_rewrite_rejects_enabled_automatic_skill_instructions(self) -> None:
        created = self.ensure(role_key="enabled-skill-catalog-review")
        path = Path(created["path"])
        invalid = path.read_text(encoding="utf-8").replace(
            "[skills]\ninclude_instructions = false\n",
            "[skills]\ninclude_instructions = true\n",
            1,
        ).encode("utf-8")
        path.write_bytes(invalid)
        invalid_sha256 = agents.sha256_bytes(invalid)
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "UPDATE agents SET expected_sha256 = ? WHERE agent_id = ?",
                (invalid_sha256, created["agent_id"]),
            )
            connection.commit()

        with self.assertRaisesRegex(
            agents.SpecialistError,
            "automatic skill instructions must be disabled",
        ):
            self.improve_with_lesson(
                name=created["name"],
                expected_sha256=invalid_sha256,
                lesson="启用自动技能目录的窄角色不能继续写入经验。",
                event_id=str(uuid.uuid4()),
            )

        self.assertEqual(path.read_bytes(), invalid)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                0,
            )

    def test_good_experience_is_idempotent_and_updates_the_agent_memory(self) -> None:
        created = self.ensure()
        event_id = str(uuid.uuid4())
        lesson = "先核对真实运行时依赖，再修改共享绑定。"

        first = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=event_id,
        )
        replay = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=first["sha256"],
            lesson=lesson,
            event_id=event_id,
        )

        self.assertEqual(first["action"], "experience_recorded")
        self.assertEqual(replay["action"], "experience_already_recorded")
        self.assertEqual(replay["experience_count"], 1)
        text = (self.registry.agents_dir / f"{created['name']}.toml").read_text(encoding="utf-8")
        self.assertIn(lesson, text)

        with self.assertRaises(agents.SpecialistError):
            self.improve_with_lesson(
                name=created["name"],
                expected_sha256=replay["sha256"],
                lesson="同一个事件不能改写成另一条经验。",
                event_id=event_id,
            )

    def test_correction_preserves_raw_events_and_removes_bad_lesson_from_active_memory(self) -> None:
        created = self.ensure()
        bad_event_id = str(uuid.uuid4())
        bad_lesson = "错误经验：跳过证据并直接覆盖共享文件。"
        bad = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=bad_lesson,
            event_id=bad_event_id,
        )
        correction_event_id = str(uuid.uuid4())
        corrected_lesson = "纠正经验：先核对证据，并只修改明确分配的写入范围。"
        corrected = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=bad["sha256"],
            lesson=corrected_lesson,
            event_id=correction_event_id,
            retracts_event_id=bad_event_id,
        )
        replay = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=corrected["sha256"],
            lesson=corrected_lesson,
            event_id=correction_event_id,
            retracts_event_id=bad_event_id,
        )

        text = Path(created["path"]).read_text(encoding="utf-8")
        self.assertEqual(corrected["action"], "experience_corrected")
        self.assertEqual(replay["action"], "experience_correction_already_recorded")
        self.assertTrue(corrected["raw_experience_preserved"])
        self.assertEqual(corrected["experience_count"], 2)
        self.assertNotIn(bad_lesson, text)
        self.assertIn(corrected_lesson, text)
        with contextlib.closing(self.db()) as connection:
            rows = list(
                connection.execute(
                    "SELECT event_id, lesson, retracts_event_id "
                    "FROM experience_events ORDER BY sequence"
                )
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_id"], bad_event_id)
        self.assertEqual(rows[1]["retracts_event_id"], bad_event_id)

        with self.assertRaisesRegex(agents.SpecialistError, "different correction"):
            self.improve_with_lesson(
                name=created["name"],
                expected_sha256=replay["sha256"],
                lesson="另一条纠正不能重复覆盖同一事件。",
                event_id=str(uuid.uuid4()),
                retracts_event_id=bad_event_id,
            )

    def test_correction_resets_a_summary_that_may_contain_the_rejected_event(self) -> None:
        created = self.ensure()
        current_hash = created["sha256"]
        bad_event_id = str(uuid.uuid4())
        compaction = None
        for index in range(8):
            event_id = bad_event_id if index == 2 else str(uuid.uuid4())
            result = self.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"待压缩经验 {index}",
                event_id=event_id,
            )
            current_hash = result["sha256"]
            compaction = result["compaction"]
        assert compaction and compaction["needed"]
        compacted = self.improve_with_summary(
            name=created["name"],
            expected_sha256=current_hash,
            summary="受污染摘要：待压缩经验 2。",
            covered_through=compaction["covered_through"],
            source_digest=compaction["source_digest"],
        )
        corrected = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=compacted["sha256"],
            lesson="纠正后只保留经过核验的压缩经验。",
            event_id=str(uuid.uuid4()),
            retracts_event_id=bad_event_id,
        )

        text = Path(created["path"]).read_text(encoding="utf-8")
        self.assertTrue(corrected["summary_reset"])
        self.assertTrue(corrected["compaction"]["needed"])
        self.assertNotIn("受污染摘要", text)
        self.assertNotIn("待压缩经验 2", text)
        self.assertIn("纠正后只保留", text)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                9,
            )
            self.assertIsNone(
                connection.execute("SELECT * FROM experience_summaries").fetchone()
            )

    def test_exact_schema_one_requires_explicit_global_migration_without_losing_experience(self) -> None:
        created = self.ensure()
        lesson = "旧结构中的原始经验必须完整保留。"
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=str(uuid.uuid4()),
        )
        rows = self.downgrade_registry(1)
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "explicit migrate-global"):
            self.ensure()
        migrated = self.registry.migrate_global(plan_path=self.write_migration_plan(rows))
        self.assertEqual(migrated["action"], "global_migration_committed")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)
            row = connection.execute(
                "SELECT lesson, retracts_event_id FROM experience_events"
            ).fetchone()
            run_count = connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        self.assertEqual(row["lesson"], lesson)
        self.assertIsNone(row["retracts_event_id"])
        self.assertEqual(run_count, 0)

    def test_exact_schema_two_requires_explicit_global_migration_without_backfilling_runs(self) -> None:
        created = self.ensure()
        lesson = "第二版经验与代理身份必须保留，历史存活轮次不猜测。"
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=str(uuid.uuid4()),
        )
        rows = self.downgrade_registry(2)
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "explicit migrate-global"):
            self.ensure()
        self.registry.migrate_global(plan_path=self.write_migration_plan(rows))
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(
                connection.execute("SELECT lesson FROM experience_events").fetchone()[0],
                lesson,
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 0)

    def test_raw_experience_is_unlimited_and_compaction_never_deletes_it(self) -> None:
        created = self.ensure()
        current_hash = created["sha256"]
        compaction = None
        lessons = []
        for index in range(20):
            lesson = f"经验 {index}：保留可复核证据并避免重复读取。"
            lessons.append(lesson)
            result = self.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=lesson,
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            if result["compaction"]["needed"]:
                compaction = result["compaction"]

        self.assertIsNotNone(compaction)
        assert compaction is not None
        with contextlib.closing(self.db()) as connection:
            before = list(
                connection.execute(
                    "SELECT sequence, lesson FROM experience_events ORDER BY sequence"
                )
            )
        self.assertEqual(len(before), 20)
        self.assertEqual([row["lesson"] for row in before], lessons)

        summary = "保留证据、复用完整来源覆盖，并避免重复读取和返工。"
        with mock.patch.object(
            self.registry,
            "_pending_events",
            wraps=self.registry._pending_events,
        ) as pending:
            compacted = self.improve_with_summary(
                name=created["name"],
                expected_sha256=current_hash,
                summary=summary,
                covered_through=compaction["covered_through"],
                source_digest=compaction["source_digest"],
            )
        self.assertEqual(pending.call_count, 1)
        self.assertTrue(compacted["raw_experience_preserved"])
        with contextlib.closing(self.db()) as connection:
            after = list(
                connection.execute(
                    "SELECT sequence, lesson FROM experience_events ORDER BY sequence"
                )
            )
            summary_row = connection.execute(
                "SELECT * FROM experience_summaries"
            ).fetchone()
        self.assertEqual([(row["sequence"], row["lesson"]) for row in before], [(row["sequence"], row["lesson"]) for row in after])
        self.assertEqual(summary_row["covered_through_sequence"], compaction["covered_through"])
        self.assertIn(summary, Path(created["path"]).read_text(encoding="utf-8"))

    def test_compaction_triggers_at_eight_pending_events(self) -> None:
        created = self.ensure()
        current_hash = created["sha256"]
        for index in range(7):
            result = self.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"短经验 {index}",
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            self.assertFalse(result["compaction"]["needed"])
        eighth = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=current_hash,
            lesson="短经验 7",
            event_id=str(uuid.uuid4()),
        )
        self.assertTrue(eighth["compaction"]["needed"])

    def test_improve_reads_one_bounded_pending_window(self) -> None:
        created = self.ensure()
        with contextlib.closing(self.db()) as connection:
            for index in range(100):
                lesson = f"历史经验 {index}"
                connection.execute(
                    "INSERT INTO experience_events(agent_id,event_id,event_digest,lesson,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (
                        created["agent_id"],
                        str(uuid.uuid4()),
                        agents.sha256_bytes(lesson.encode("utf-8")),
                        lesson,
                        agents.utc_now(),
                    ),
                )
            connection.commit()

        with mock.patch.object(
            self.registry,
            "_pending_events",
            wraps=self.registry._pending_events,
        ) as pending:
            result = self.improve_with_lesson(
                name=created["name"],
                expected_sha256=created["sha256"],
                lesson="新经验只读取一个有界窗口。",
                event_id=str(uuid.uuid4()),
            )

        self.assertEqual(pending.call_count, 1)
        self.assertTrue(result["compaction"]["needed"])
        self.assertLessEqual(
            len(result["compaction"]["events"]), agents.COMPACT_BATCH_EVENTS
        )
        self.assertEqual(result["experience_count"], 101)

    def test_stale_compaction_cannot_overwrite_a_newer_summary(self) -> None:
        created = self.ensure()
        current_hash = created["sha256"]
        compaction = None
        for index in range(8):
            result = self.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"并发经验 {index}",
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            compaction = result["compaction"]
        assert compaction and compaction["needed"]
        refreshed = self.improve_with_summary(
            name=created["name"],
            expected_sha256=current_hash,
            summary="最新压缩摘要。",
            covered_through=compaction["covered_through"],
            source_digest=compaction["source_digest"],
        )
        with self.assertRaises(agents.SpecialistError):
            self.improve_with_summary(
                name=created["name"],
                expected_sha256=refreshed["sha256"],
                summary="迟到旧摘要。",
                covered_through=compaction["covered_through"] - 1,
                source_digest=compaction["source_digest"],
            )

    def test_survival_rounds_are_idempotent_auditable_and_reported_by_status(self) -> None:
        created = self.ensure()
        first_run = str(uuid.uuid4())
        first = self.registry.record_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=first_run,
            invocation_kind="spawn_agent",
        )
        replay = self.registry.record_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=first_run,
            invocation_kind="spawn_agent",
        )
        second = self.registry.record_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=str(uuid.uuid4()),
            invocation_kind="followup_task",
        )

        self.assertEqual(first["action"], "survival_round_recorded")
        self.assertEqual(first["survival_rounds"], 1)
        self.assertEqual(replay["action"], "survival_round_already_recorded")
        self.assertEqual(replay["completed_at"], first["completed_at"])
        self.assertEqual(replay["survival_rounds"], 1)
        self.assertEqual(second["survival_rounds"], 2)
        self.assertFalse(second["historical_backfill"])

        legacy = self.registry.agents_dir / "lean_legacy_agent_12345678.toml"
        legacy.write_text('name = "lean_legacy_agent_12345678"\n', encoding="utf-8")
        status = self.registry.status()
        self.assertEqual(status["registered_count"], 1)
        self.assertEqual(status["lean_agent_files_total"], 2)
        self.assertEqual(status["unregistered_lean_agent_files"], [legacy.name])
        self.assertFalse(status["historical_backfill"])
        self.assertEqual(status["registered_agents"][0]["survival_rounds"], 2)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 2)

    def test_survival_round_rejects_hash_drift_reuse_collision_and_deletion(self) -> None:
        created = self.ensure()
        run_id = str(uuid.uuid4())
        with self.assertRaises(agents.SpecialistError):
            self.registry.record_run(
                name=created["name"],
                expected_sha256="0" * 64,
                run_id=run_id,
                invocation_kind="spawn_agent",
            )
        recorded = self.registry.record_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=run_id,
            invocation_kind="spawn_agent",
        )
        other = self.ensure(role_key="python-regression-implementation")
        with self.assertRaisesRegex(agents.SpecialistError, "different specialist"):
            self.registry.record_run(
                name=other["name"],
                expected_sha256=other["sha256"],
                run_id=run_id,
                invocation_kind="spawn_agent",
            )
        with self.assertRaisesRegex(agents.SpecialistError, "recorded survival rounds"):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertEqual(recorded["survival_rounds"], 1)
        self.assertTrue(Path(created["path"]).exists())
        self.assertFalse(self.registry.pending_deletion_dir.exists())

    def test_delete_rejects_recorded_experience_without_pending_artifacts(self) -> None:
        created = self.ensure()
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson="已记录经验的角色不能进入待删目录。",
            event_id=str(uuid.uuid4()),
        )

        with self.assertRaisesRegex(agents.SpecialistError, "recorded experience"):
            self.registry.delete(
                name=created["name"],
                expected_sha256=improved["sha256"],
                owner_token=created["owner_token"],
            )

        self.assertTrue(Path(created["path"]).exists())
        self.assertFalse(self.registry.pending_deletion_dir.exists())
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )

    def test_delete_retires_exact_bytes_with_a_token_free_receipt(self) -> None:
        created = self.ensure()
        original_path = Path(created["path"])
        original = original_path.read_bytes()
        result = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )
        self.assertTrue(result["deleted"])
        self.assertTrue(result["recoverable"])
        self.assertEqual(result["action"], "retired_to_pending_deletion")
        self.assertEqual(result["disposition"], "plugin_pending_deletion")
        self.assertEqual(result["deleted_from"], "active_specialist_registry")
        self.assertEqual(result["agent_id"], created["agent_id"])
        self.assertEqual(result["sha256"], created["sha256"])
        self.assertEqual(result["original_path"], str(original_path))
        pending_path = Path(result["pending_path"])
        receipt_path = Path(result["receipt_path"])
        self.assertFalse(original_path.exists())
        self.assertEqual(pending_path.read_bytes(), original)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["format_version"], 2)
        self.assertEqual(receipt["agent_id"], created["agent_id"])
        self.assertEqual(receipt["name"], created["name"])
        self.assertEqual(receipt["role_key"], "qml-binding-diagnostics")
        self.assertEqual(receipt["original_path"], str(original_path))
        self.assertEqual(receipt["pending_path"], str(pending_path))
        self.assertEqual(receipt["sha256"], created["sha256"])
        self.assertTrue(receipt["created_at"])
        self.assertTrue(receipt["updated_at"])
        self.assertTrue(receipt["retired_at"])
        self.assertEqual(receipt["global_contract_version"], 1)
        self.assertEqual(receipt["global_domain_key"], "interface-binding-diagnostics")
        self.assertEqual(
            agents.sha256_bytes(receipt["global_contract"].encode("utf-8")),
            receipt["global_contract_digest"],
        )
        self.assertNotIn("owner_token", receipt)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)

    def test_delete_rejects_wrong_token_hash_drift_and_external_files(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        external = self.registry.agents_dir / "user_agent.toml"
        external.write_text('name = "user_agent"\n', encoding="utf-8")
        external_before = external.read_bytes()

        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token="0" * 32,
            )
        self.assertTrue(path.exists())

        path.write_bytes(path.read_bytes() + b"\n# external edit\n")
        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertTrue(path.exists())
        self.assertEqual(external.read_bytes(), external_before)
        self.assertFalse(self.registry.pending_deletion_dir.exists())

    def test_delete_rejects_existing_pending_target_without_overwrite(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        pending_dir = agents.ensure_plain_directory(
            self.registry.pending_deletion_dir, create=True
        )
        pending_path = pending_dir / f"{created['agent_id']}.{created['sha256']}.toml"
        pending_path.write_bytes(b"concurrent evidence")

        with self.assertRaisesRegex(agents.SpecialistError, "target already exists"):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )

        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(pending_path.read_bytes(), b"concurrent evidence")
        self.assertFalse(
            (pending_dir / f"{created['agent_id']}.{created['sha256']}.receipt.json").exists()
        )
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)

        second = self.ensure(role_key="receipt-target-conflict")
        second_pending, second_receipt = self.registry._receipt_paths(
            second["agent_id"], second["sha256"]
        )
        second_receipt.write_bytes(b"concurrent receipt evidence")
        with self.assertRaisesRegex(agents.SpecialistError, "receipt target already exists"):
            self.registry.delete(
                name=second["name"],
                expected_sha256=second["sha256"],
                owner_token=second["owner_token"],
            )
        self.assertFalse(second_pending.exists())
        self.assertEqual(second_receipt.read_bytes(), b"concurrent receipt evidence")
        self.assertTrue(Path(second["path"]).exists())

    def test_delete_commit_failure_rolls_back_ledger_and_restores_exact_file(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        real_connection = self.registry.connect()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced commit failure after retirement")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(
            self.registry,
            "connect",
            return_value=FailingCommitConnection(),
        ):
            with self.assertRaisesRegex(sqlite3.OperationalError, "forced commit failure"):
                self.registry.delete(
                    name=created["name"],
                    expected_sha256=created["sha256"],
                    owner_token=created["owner_token"],
                )

        self.assertEqual(path.read_bytes(), before)
        pending_path, receipt_path = self.registry._receipt_paths(
            created["agent_id"], created["sha256"]
        )
        self.assertFalse(pending_path.exists())
        self.assertTrue(receipt_path.exists())
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)

    def test_delete_rejects_hard_linked_agent(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        linked = path.with_name(path.stem + "_link.toml")
        try:
            os.link(path, linked)
        except OSError as exc:
            self.skipTest(f"hard links unavailable: {exc}")
        self.addCleanup(lambda: linked.exists() and linked.unlink())

        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertTrue(path.exists())
        self.assertFalse(self.registry.pending_deletion_dir.exists())

    def test_missing_unused_file_removes_only_the_orphan_row_without_receipt(self) -> None:
        created = self.ensure()
        Path(created["path"]).unlink()

        removed = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )
        absent = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )

        self.assertEqual(removed["action"], "stale_registry_row_removed")
        self.assertFalse(removed["deleted"])
        self.assertEqual(absent["action"], "already_absent")
        self.assertFalse(absent["deleted"])
        self.assertFalse(self.registry.pending_deletion_dir.exists())

    def test_missing_file_with_experience_cannot_delete_the_append_only_ledger(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        first = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson="孤儿账本清理也必须验证所有权凭据。",
            event_id=str(uuid.uuid4()),
        )
        path.unlink()

        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256="0" * 64,
                owner_token=created["owner_token"],
            )
        with self.assertRaises(agents.SpecialistError):
            self.registry.delete(
                name=created["name"],
                expected_sha256=first["sha256"],
                owner_token="0" * 32,
            )

        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )
        self.assertFalse(self.registry.pending_deletion_dir.exists())

        with self.assertRaisesRegex(agents.SpecialistError, "recorded experience"):
            self.registry.delete(
                name=created["name"],
                expected_sha256=first["sha256"],
                owner_token=created["owner_token"],
            )
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )

    def test_restore_succeeds_and_archives_receipt_without_replay(self) -> None:
        created = self.ensure()
        original_path = Path(created["path"])
        original = original_path.read_bytes()
        retired = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )

        restored = self.registry.restore(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )

        self.assertEqual(restored["action"], "restored_from_pending_deletion")
        self.assertTrue(restored["restored"])
        self.assertFalse(restored["receipt_replayable"])
        self.assertEqual(restored["receipt_disposition"], "archived_after_restore")
        self.assertEqual(original_path.read_bytes(), original)
        self.assertFalse(Path(retired["pending_path"]).exists())
        self.assertFalse(Path(retired["receipt_path"]).exists())
        archived_receipt = Path(restored["receipt_path"])
        self.assertEqual(archived_receipt.read_bytes(), json.dumps(
            json.loads(archived_receipt.read_text(encoding="utf-8")),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n")
        with contextlib.closing(self.db()) as connection:
            row = connection.execute("SELECT * FROM agents").fetchone()
        self.assertEqual(row["agent_id"], created["agent_id"])
        self.assertEqual(row["owner_token"], created["owner_token"])
        with self.assertRaisesRegex(agents.SpecialistError, "exactly one"):
            self.registry.restore(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )

    def test_restore_rejects_wrong_token_hash_and_receipt_path(self) -> None:
        created = self.ensure()
        retired = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )
        pending_path = Path(retired["pending_path"])

        with self.assertRaisesRegex(agents.SpecialistError, "owner token"):
            self.registry.restore(
                receipt=Path(retired["receipt_path"]),
                expected_sha256=created["sha256"],
                owner_token="0" * 32,
            )
        with self.assertRaisesRegex(agents.SpecialistError, "does not match"):
            self.registry.restore(
                receipt=Path(retired["receipt_path"]),
                expected_sha256="0" * 64,
                owner_token=created["owner_token"],
            )
        with self.assertRaisesRegex(agents.SpecialistError, "receipt"):
            self.registry.restore(
                receipt=pending_path,
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        receipt_path = Path(retired["receipt_path"])
        corrupted_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        corrupted_receipt["role_key"] = "different-role"
        receipt_path.write_text(
            json.dumps(corrupted_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(agents.SpecialistError, "identity"):
            self.registry.restore(
                receipt=receipt_path,
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertTrue(pending_path.exists())
        self.assertFalse(Path(created["path"]).exists())

    def test_restore_rejects_role_conflict_and_hard_linked_pending_file(self) -> None:
        created = self.ensure()
        retired = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )
        conflict = self.ensure(role_key="qml-binding-diagnostics")
        with self.assertRaisesRegex(agents.SpecialistError, "conflict"):
            self.registry.restore(
                receipt=Path(retired["receipt_path"]),
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertTrue(Path(retired["pending_path"]).exists())
        self.assertTrue(Path(conflict["path"]).exists())

        Path(conflict["path"]).unlink()
        with contextlib.closing(self.db()) as connection:
            connection.execute("DELETE FROM agents WHERE agent_id = ?", (conflict["agent_id"],))
            connection.commit()
        hard_link = Path(retired["pending_path"]).with_suffix(".hardlink.toml")
        try:
            os.link(Path(retired["pending_path"]), hard_link)
        except OSError as exc:
            self.skipTest(f"hard links unavailable: {exc}")
        self.addCleanup(lambda: hard_link.exists() and hard_link.unlink())
        with self.assertRaisesRegex(agents.SpecialistError, "multiple hard links"):
            self.registry.restore(
                receipt=Path(retired["receipt_path"]),
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )

    def test_restore_commit_failure_rolls_back_to_pending_exactly(self) -> None:
        created = self.ensure()
        retired = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )
        pending_path = Path(retired["pending_path"])
        before = pending_path.read_bytes()
        real_connection = self.registry.connect()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced restore commit failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(
            self.registry,
            "connect",
            return_value=FailingCommitConnection(),
        ):
            with self.assertRaisesRegex(sqlite3.OperationalError, "forced restore commit failure"):
                self.registry.restore(
                    receipt=Path(retired["receipt_path"]),
                    expected_sha256=created["sha256"],
                    owner_token=created["owner_token"],
                )

        self.assertFalse(Path(created["path"]).exists())
        self.assertEqual(pending_path.read_bytes(), before)
        self.assertTrue(Path(retired["receipt_path"]).exists())
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)

    def test_locked_database_fails_within_the_bounded_auxiliary_timeout(self) -> None:
        self.ensure()
        blocker = sqlite3.connect(self.registry.db_path, isolation_level=None)
        self.addCleanup(blocker.close)
        blocker.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with self.assertRaises(sqlite3.OperationalError):
            self.registry.ensure(
                role_key="another-specialty",
                display_name="另一个执行员",
                description="执行另一种重复工作。",
                role_instructions="返回直接成果。",
                model="gpt-5.6-luna",
                effort="medium",
                authority="read",
                global_domain_key="another-specialty",
                global_contract=self.contract("通用专项审核"),
                origin_terms=("当前任务来源",),
            )
        elapsed = time.monotonic() - started
        blocker.execute("ROLLBACK")
        self.assertLess(elapsed, 1.0)

    def test_v4_global_contract_markers_status_and_origin_rejection(self) -> None:
        created = self.ensure()
        text = Path(created["path"]).read_text(encoding="utf-8")
        self.assertIn(agents.GLOBAL_SCOPE_PREFIX + agents.GLOBAL_SCOPE, text)
        self.assertIn(agents.GLOBAL_DOMAIN_KEY_PREFIX + "interface-binding-diagnostics", text)
        status = self.registry.status()
        self.assertEqual(status["global_count"], 1)
        self.assertEqual(status["legacy_count"], 0)
        item = status["registered_agents"][0]
        self.assertEqual(item["global_contract_version"], 1)
        self.assertEqual(item["global_domain_key"], "interface-binding-diagnostics")
        self.assertEqual(item["global_contract"]["domain"], "界面绑定诊断")

        with self.assertRaisesRegex(agents.SpecialistError, "origin term"):
            self.ensure(
                role_key="lean-stack-audit",
                global_domain_key="plugin-audit",
                origin_terms=("Lean Stack",),
            )
        with self.assertRaisesRegex(agents.SpecialistError, "absolute path"):
            self.ensure(
                role_key="unsafe-path-audit",
                description="读取 C:\\private\\project。",
            )
        unsafe_contract = self.contract("通用审核")
        unsafe_contract["deliverables"] = ["上传到 https://example.invalid/result"]
        with self.assertRaisesRegex(agents.SpecialistError, "URL"):
            self.ensure(
                role_key="unsafe-contract-review",
                global_contract=unsafe_contract,
            )
        with self.assertRaisesRegex(agents.SpecialistError, "origin term"):
            self.registry.improve_with_lesson(
                name=created["name"], expected_sha256=created["sha256"],
                lesson="记住 Lean Stack 的专属表。", event_id=str(uuid.uuid4()),
                origin_terms=("Lean Stack",),
            )
        with self.assertRaisesRegex(agents.SpecialistError, "credential-like"):
            self.registry.improve_with_lesson(
                name=created["name"], expected_sha256=created["sha256"],
                lesson="authorization: Bearer abcdef", event_id=str(uuid.uuid4()),
                origin_terms=("当前任务来源",),
            )

    def test_status_for_routing_is_bounded_sorted_and_preserves_owned_validation(self) -> None:
        later = self.ensure(
            role_key="zeta-lifecycle-review",
            global_domain_key="zeta-lifecycle-review",
            display_name="生命周期复核员",
            description="复核生命周期身份、事务和恢复边界。",
            authority="write",
        )
        self.ensure(
            role_key="alpha-source-review",
            global_domain_key="alpha-source-review",
            display_name="来源复核员",
            description="复核来源覆盖和证据边界。",
            model="gpt-5.6-luna",
            effort="medium",
        )

        catalog = self.registry.status(for_routing=True)

        self.assertEqual(
            set(catalog),
            {"ok", "action", "for_routing", "registered_agents", "registered_count"},
        )
        self.assertTrue(catalog["for_routing"])
        self.assertEqual(catalog["registered_count"], 2)
        items = catalog["registered_agents"]
        self.assertEqual(
            [item["global_domain_key"] for item in items],
            ["alpha-source-review", "zeta-lifecycle-review"],
        )
        self.assertEqual(
            set(items[0]),
            {
                "name", "description", "global_domain_key", "global_contract",
                "model", "reasoning_effort", "speed", "authority",
            },
        )
        self.assertEqual(items[0]["description"], "来源复核员：复核来源覆盖和证据边界。")
        self.assertEqual(items[0]["speed"], "fast")
        self.assertEqual(items[1]["authority"], "write")

        path = Path(later["path"])
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(agents.SpecialistError, "content drifted"):
            self.registry.status(for_routing=True)

    def test_status_for_routing_cli_passthrough_and_ordinary_status_compatibility(self) -> None:
        self.ensure()
        ordinary = self.registry.status()
        self.assertNotIn("for_routing", ordinary)
        self.assertIn("lean_agent_files_total", ordinary)
        self.assertIn("survival_rounds", ordinary["registered_agents"][0])
        self.assertIn("path", ordinary["registered_agents"][0])
        self.assertIn("sha256", ordinary["registered_agents"][0])

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main(
                ["--codex-home", str(self.codex_home), "status", "--for-routing"]
            )
        catalog = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(catalog["for_routing"])
        self.assertEqual(
            set(catalog["registered_agents"][0]),
            {
                "name", "description", "global_domain_key", "global_contract",
                "model", "reasoning_effort", "speed", "authority",
            },
        )

    def test_semantic_persistence_requires_current_origin_terms_in_api_cli_and_plan(self) -> None:
        kwargs = {
            "role_key": "missing-origin-review",
            "display_name": "来源核对员",
            "description": "重复核对通用领域输入。",
            "role_instructions": "返回通用证据和结论。",
            "model": "gpt-5.6-luna",
            "effort": "medium",
            "authority": "read",
            "global_domain_key": "generic-origin-review",
            "global_contract": self.contract("通用来源审核"),
        }
        with self.assertRaisesRegex(agents.SpecialistError, "at least one"):
            self.registry.ensure(**kwargs)
        created = self.ensure(role_key="origin-required-experience")
        with self.assertRaisesRegex(agents.SpecialistError, "at least one"):
            self.registry.improve_with_lesson(
                name=created["name"], expected_sha256=created["sha256"],
                lesson="这条经验缺少当前来源护栏。", event_id=str(uuid.uuid4()),
            )
        with self.assertRaisesRegex(agents.SpecialistError, "at least one"):
            self.registry.improve_with_summary(
                name=created["name"], expected_sha256=created["sha256"],
                summary="缺少来源护栏的摘要。", covered_through=1,
                source_digest="0" * 64,
            )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main([
                "--codex-home", str(self.codex_home), "ensure",
                "--role-key", "cli-missing-origin", "--display-name", "CLI 来源核对员",
                "--description", "核对通用输入。", "--instructions", "返回通用证据。",
                "--model", "gpt-5.6-luna", "--reasoning-effort", "medium",
                "--authority", "read", "--global-domain-key", "cli-origin-review",
                "--global-contract", json.dumps(self.contract("CLI 通用审核"), ensure_ascii=False),
            ])
        self.assertEqual(exit_code, 2)
        self.assertIn("at least one", json.loads(output.getvalue())["error"])
        for mode_args in (
            ["--lesson", "CLI 缺少来源护栏的经验。", "--event-id", str(uuid.uuid4())],
            ["--summary", "CLI 缺少来源护栏的摘要。", "--covered-through", "1", "--source-digest", "0" * 64],
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = agents.main([
                    "--codex-home", str(self.codex_home), "improve",
                    "--name", created["name"], "--expected-sha256", created["sha256"],
                    *mode_args,
                ])
            self.assertEqual(exit_code, 2)
            self.assertIn("at least one", json.loads(output.getvalue())["error"])

        rows = self.downgrade_registry(3)
        plan = self.write_migration_plan(rows)
        payload = json.loads(plan.read_text(encoding="utf-8"))
        payload["roles"][0]["origin_terms"] = []
        plan.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(agents.SpecialistError, "at least one"):
            self.registry.migrate_global(plan_path=plan)

    def test_explicit_v3_multi_role_migration_preserves_identity_runs_events_and_corrects_memory(self) -> None:
        first = self.ensure(role_key="plugin-specific-review")
        second = self.ensure(role_key="hevc-export-review", global_domain_key="media-export-review")
        run_id = str(uuid.uuid4())
        self.registry.record_run(
            name=first["name"], expected_sha256=first["sha256"],
            run_id=run_id, invocation_kind="spawn_agent",
        )
        bad_event = str(uuid.uuid4())
        improved = self.improve_with_lesson(
            name=first["name"], expected_sha256=first["sha256"],
            lesson="旧插件专属经验。", event_id=bad_event,
        )
        original_identity = {}
        with contextlib.closing(self.db()) as connection:
            for row in connection.execute("SELECT agent_id,name,owner_token,created_at FROM agents"):
                original_identity[row["name"]] = dict(row)
            original_events = [tuple(row) for row in connection.execute(
                "SELECT sequence,event_id,event_digest,lesson,retracts_event_id FROM experience_events ORDER BY sequence"
            )]
        rows = self.downgrade_registry(3)
        plan_path = self.write_migration_plan(
            rows,
            corrections={first["name"]: [{"event_id": bad_event, "lesson": "跨插件复用时只保留通用核验步骤。"}]},
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["roles"][0]["new_role_key"] = "domain-consistency-review"
        plan["roles"][0]["origin_terms"] = ["旧插件"]
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

        migrated = self.registry.migrate_global(plan_path=plan_path)
        self.assertEqual(migrated["migrated_count"], 2)
        self.assertEqual(migrated["correction_count"], 1)
        real_ensure_directory = agents.ensure_plain_directory
        def forbid_pending_backup_read(path: Path, *, create: bool):
            if agents.GLOBAL_MIGRATION_PENDING_BACKUP_DIR in Path(path).parts:
                raise AssertionError("idempotent replay must not depend on pending backups")
            return real_ensure_directory(path, create=create)
        with mock.patch.object(
            agents, "ensure_plain_directory", side_effect=forbid_pending_backup_read
        ):
            replay = self.registry.migrate_global(plan_path=plan_path)
        self.assertEqual(replay["action"], "global_migration_already_committed")
        active_archive_root = self.registry.state_dir / agents.GLOBAL_MIGRATION_ARCHIVE_DIR
        self.assertEqual(list(active_archive_root.rglob("*.legacy.toml")), [])
        backup_root = (
            self.registry.pending_deletion_dir
            / agents.GLOBAL_MIGRATION_PENDING_BACKUP_DIR
        )
        pending_legacy = list(backup_root.rglob("*.legacy.toml"))
        self.assertEqual(len(pending_legacy), 2)
        completion = json.loads(
            self.registry._migration_journal_path().read_text(encoding="utf-8")
        )
        completion_text = json.dumps(completion, ensure_ascii=False)
        self.assertEqual(completion["receipt_kind"], agents.GLOBAL_MIGRATION_COMPLETION_KIND)
        self.assertNotIn("owner_token", completion_text)
        self.assertNotIn("lesson", completion_text)
        self.assertNotRegex(completion_text, r"[A-Za-z]:[\\/]")
        self.assertNotIn("old_path", completion)
        self.assertNotIn("new_path", completion)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)
            identities = list(connection.execute(
                "SELECT agent_id,owner_token,created_at,global_contract_version FROM agents"
            ))
            self.assertEqual(
                {(row["agent_id"], row["owner_token"], row["created_at"]) for row in identities},
                {(value["agent_id"], value["owner_token"], value["created_at"]) for value in original_identity.values()},
            )
            self.assertTrue(all(row["global_contract_version"] == 1 for row in identities))
            self.assertEqual(connection.execute("SELECT run_id FROM agent_runs").fetchone()[0], run_id)
            events = list(connection.execute(
                "SELECT sequence,event_id,event_digest,lesson,retracts_event_id FROM experience_events ORDER BY sequence"
            ))
            self.assertEqual([tuple(row) for row in events[:len(original_events)]], original_events)
            self.assertEqual(events[-1]["retracts_event_id"], bad_event)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM experience_summaries").fetchone()[0], 0)
        self.assertFalse(Path(rows[0]["path"]).exists())
        migrated_names = {item["role_key"]: item for item in self.registry.status()["registered_agents"]}
        self.assertIn("domain-consistency-review", migrated_names)
        self.assertIn("跨插件复用时只保留通用核验步骤", Path(migrated_names["domain-consistency-review"]["path"]).read_text(encoding="utf-8"))
        self.assertNotIn("旧插件专属经验", Path(migrated_names["domain-consistency-review"]["path"]).read_text(encoding="utf-8"))

    def test_migration_conflict_is_zero_write_and_file_failure_recovers_exactly(self) -> None:
        first = self.ensure(role_key="first-project-review")
        second = self.ensure(role_key="second-project-review")
        rows = self.downgrade_registry(3)
        before_db = self.registry.db_path.read_bytes()
        before_files = {row["path"]: Path(row["path"]).read_bytes() for row in rows}
        conflict_plan = self.write_migration_plan(rows)
        payload = json.loads(conflict_plan.read_text(encoding="utf-8"))
        payload["roles"][0]["new_role_key"] = "shared-domain-review"
        payload["roles"][1]["new_role_key"] = "shared-domain-review"
        conflict_plan.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(agents.SpecialistError, "conflict"):
            self.registry.migrate_global(plan_path=conflict_plan)
        self.assertEqual(self.registry.db_path.read_bytes(), before_db)
        self.assertEqual({path: Path(path).read_bytes() for path in before_files}, before_files)

        recovery_plan = self.write_migration_plan(rows)
        payload = json.loads(recovery_plan.read_text(encoding="utf-8"))
        payload["roles"][0]["new_role_key"] = "first-global-review"
        payload["roles"][1]["new_role_key"] = "second-global-review"
        recovery_plan.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        real_write = agents.write_new_file
        calls = 0
        def fail_one_new_agent(path: Path, data: bytes) -> None:
            nonlocal calls
            if path.parent == self.registry.agents_dir and path.name.startswith("lean_first_global_review"):
                calls += 1
                raise OSError("forced migrated file failure")
            real_write(path, data)
        with mock.patch.object(agents, "write_new_file", side_effect=fail_one_new_agent):
            with self.assertRaisesRegex(OSError, "forced migrated file failure"):
                self.registry.migrate_global(plan_path=recovery_plan)
        self.assertEqual(calls, 1)
        self.assertEqual(self.registry.db_path.read_bytes(), before_db)
        self.assertEqual({path: Path(path).read_bytes() for path in before_files}, before_files)
        journal = json.loads(self.registry._migration_journal_path().read_text(encoding="utf-8"))
        self.assertEqual(journal["status"], "rolled_back")
        self.assertNotIn("owner_token", json.dumps(journal))
        self.assertNotIn("旧插件专属经验", json.dumps(journal, ensure_ascii=False))

    def test_migration_commit_failure_restores_all_legacy_files_and_database(self) -> None:
        self.ensure(role_key="commit-failure-review")
        rows = self.downgrade_registry(3)
        before_db = self.registry.db_path.read_bytes()
        before_files = {row["path"]: Path(row["path"]).read_bytes() for row in rows}
        plan = self.write_migration_plan(rows)
        payload = json.loads(plan.read_text(encoding="utf-8"))
        payload["roles"][0]["new_role_key"] = "global-commit-review"
        plan.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        real_connection, version = self.registry._legacy_connection()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced global migration commit failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(
            self.registry,
            "_legacy_connection",
            return_value=(FailingCommitConnection(), version),
        ):
            with self.assertRaisesRegex(sqlite3.OperationalError, "forced global migration commit failure"):
                self.registry.migrate_global(plan_path=plan)
        self.assertEqual(self.registry.db_path.read_bytes(), before_db)
        self.assertEqual({path: Path(path).read_bytes() for path in before_files}, before_files)
        self.assertEqual(
            json.loads(self.registry._migration_journal_path().read_text(encoding="utf-8"))["status"],
            "rolled_back",
        )

    def test_committed_migration_recovers_interrupted_backup_receipt_finalization(self) -> None:
        self.ensure(role_key="cleanup-interruption-review")
        rows = self.downgrade_registry(3)
        plan = self.write_migration_plan(rows)
        payload = json.loads(plan.read_text(encoding="utf-8"))
        payload["roles"][0]["new_role_key"] = "global-cleanup-review"
        plan.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        real_write_json = agents.write_json_atomic
        failed = False

        def interrupt_completion(path: Path, value: dict[str, object]) -> None:
            nonlocal failed
            if (
                not failed
                and path == self.registry._migration_journal_path()
                and value.get("receipt_kind") == agents.GLOBAL_MIGRATION_COMPLETION_KIND
            ):
                failed = True
                raise OSError("forced completion receipt interruption")
            real_write_json(path, value)

        with mock.patch.object(agents, "write_json_atomic", side_effect=interrupt_completion):
            with self.assertRaisesRegex(
                agents.AuxiliarySkipped,
                "committed but pending-backup finalization is incomplete",
            ):
                self.registry.migrate_global(plan_path=plan)
        self.assertTrue(failed)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)
        detailed = json.loads(
            self.registry._migration_journal_path().read_text(encoding="utf-8")
        )
        self.assertEqual(detailed["status"], "commit_verified_cleanup_pending")
        self.assertFalse(Path(detailed["archive_dir"]).exists())
        self.assertTrue(Path(detailed["backup_target"]).exists())

        recovered = self.registry.migrate_global(plan_path=plan)
        self.assertEqual(recovered["action"], "global_migration_already_committed")
        completion = json.loads(
            self.registry._migration_journal_path().read_text(encoding="utf-8")
        )
        self.assertEqual(completion["receipt_kind"], agents.GLOBAL_MIGRATION_COMPLETION_KIND)
        self.assertNotIn("backup_target", completion)
        self.assertNotRegex(json.dumps(completion), r"[A-Za-z]:[\\/]")

    def test_global_contract_sqlite_toml_and_duties_are_bidirectionally_verified(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        original = path.read_bytes()
        tampered = original.replace(
            (agents.GLOBAL_DOMAIN_KEY_PREFIX + "interface-binding-diagnostics").encode("utf-8"),
            (agents.GLOBAL_DOMAIN_KEY_PREFIX + "different-domain").encode("utf-8"),
            1,
        )
        path.write_bytes(tampered)
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "UPDATE agents SET expected_sha256=? WHERE agent_id=?",
                (agents.sha256_bytes(tampered), created["agent_id"]),
            )
            connection.commit()
        with self.assertRaisesRegex(agents.SpecialistError, "domain marker"):
            self.registry.status()

    def test_migration_hashes_source_once_then_pending_backup_once(self) -> None:
        self.ensure(role_key="digest-budget-review")
        rows = self.downgrade_registry(3)
        source = Path(rows[0]["path"]).read_bytes()
        plan = self.write_migration_plan(rows)
        payload = json.loads(plan.read_text(encoding="utf-8"))
        payload["roles"][0]["new_role_key"] = "global-digest-review"
        plan.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        real_hash = agents.sha256_bytes
        source_hash_calls = 0

        def count_hash(data: bytes) -> str:
            nonlocal source_hash_calls
            if data == source:
                source_hash_calls += 1
            return real_hash(data)

        with mock.patch.object(agents, "sha256_bytes", side_effect=count_hash):
            self.registry.migrate_global(plan_path=plan)
        # One preflight ownership/CAS hash and one post-move pending-backup integrity hash.
        # Journal, receipt, and SQLite reuse those digests instead of hashing again.
        self.assertEqual(source_hash_calls, 2)

    def test_cli_error_is_auxiliary_skipped(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "ensure",
                    "--role-key",
                    "Invalid Role",
                    "--display-name",
                    "执行员",
                    "--description",
                    "说明",
                    "--instructions",
                    "完成任务",
                    "--model",
                    "gpt-5.6-luna",
                    "--reasoning-effort",
                    "medium",
                    "--authority",
                    "read",
                    "--global-domain-key",
                    "generic-review",
                    "--global-contract",
                    json.dumps(self.contract("通用审核"), ensure_ascii=False),
                    "--origin-term",
                    "当前任务来源",
                ]
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(output.getvalue())["action"], "auxiliary_skipped")

    def test_cli_ensure_record_status_improve_delete_restore_round_trip(self) -> None:
        ensure_output = io.StringIO()
        with contextlib.redirect_stdout(ensure_output):
            ensure_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "ensure",
                    "--role-key",
                    "source-contract-verification",
                    "--display-name",
                    "来源约定核对员",
                    "--description",
                    "重复核对来源边界和对外约定。",
                    "--instructions",
                    "返回精确来源覆盖和证据缺口。",
                    "--model",
                    "gpt-5.6-luna",
                    "--reasoning-effort",
                    "medium",
                    "--authority",
                    "read",
                    "--global-domain-key",
                    "source-contract-verification",
                    "--global-contract",
                    json.dumps(self.contract("来源约定核对"), ensure_ascii=False),
                    "--origin-term",
                    "当前任务来源",
                ]
            )
        created = json.loads(ensure_output.getvalue())
        self.assertEqual(ensure_exit, 0)
        self.assertEqual(created["action"], "created")
        created_payload = tomllib.loads(
            Path(created["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(created_payload["service_tier"], "fast")

        record_output = io.StringIO()
        with contextlib.redirect_stdout(record_output):
            record_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "record-run",
                    "--name",
                    created["name"],
                    "--expected-sha256",
                    created["sha256"],
                    "--run-id",
                    str(uuid.uuid4()),
                    "--invocation-kind",
                    "spawn_agent",
                ]
            )
        recorded = json.loads(record_output.getvalue())
        self.assertEqual(record_exit, 0)
        self.assertEqual(recorded["survival_rounds"], 1)

        improve_output = io.StringIO()
        with contextlib.redirect_stdout(improve_output):
            improve_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "improve",
                    "--name",
                    created["name"],
                    "--expected-sha256",
                    created["sha256"],
                    "--event-id",
                    str(uuid.uuid4()),
                    "--lesson",
                    "完整来源覆盖可替代父代理的重复语义读取。",
                    "--origin-term",
                    "当前任务来源",
                ]
            )
        improved = json.loads(improve_output.getvalue())
        self.assertEqual(improve_exit, 0)
        self.assertEqual(improved["action"], "experience_recorded")

        status_output = io.StringIO()
        with contextlib.redirect_stdout(status_output):
            status_exit = agents.main(
                ["--codex-home", str(self.codex_home), "status"]
            )
        status = json.loads(status_output.getvalue())
        self.assertEqual(status_exit, 0)
        self.assertEqual(status["registered_count"], 1)
        self.assertEqual(status["registered_agents"][0]["survival_rounds"], 1)

        disposable = self.ensure(role_key="disposable-owned-agent")
        delete_output = io.StringIO()
        with contextlib.redirect_stdout(delete_output):
            delete_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "delete",
                    "--name",
                    disposable["name"],
                    "--expected-sha256",
                    disposable["sha256"],
                    "--owner-token",
                    disposable["owner_token"],
                ]
            )
        deleted = json.loads(delete_output.getvalue())
        self.assertEqual(delete_exit, 0)
        self.assertTrue(deleted["deleted"])

        restore_output = io.StringIO()
        with contextlib.redirect_stdout(restore_output):
            restore_exit = agents.main(
                [
                    "--codex-home",
                    str(self.codex_home),
                    "restore",
                    "--receipt",
                    deleted["receipt_path"],
                    "--expected-sha256",
                    disposable["sha256"],
                    "--owner-token",
                    disposable["owner_token"],
                ]
            )
        restored = json.loads(restore_output.getvalue())
        self.assertEqual(restore_exit, 0)
        self.assertEqual(restored["action"], "restored_from_pending_deletion")
        self.assertTrue(Path(disposable["path"]).exists())


if __name__ == "__main__":
    unittest.main()
