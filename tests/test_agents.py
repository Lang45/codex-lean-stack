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
        speed: str = "standard",
        expected_sha256: str | None = None,
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
        )

    def db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.registry.db_path)
        connection.row_factory = sqlite3.Row
        return connection

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
        self.assertEqual(version, 3)
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
        improved = self.registry.improve_with_lesson(
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

    def test_experience_rewrite_preserves_fast_speed_configuration(self) -> None:
        created = self.ensure(role_key="fast-regression-review", speed="fast")
        improved = self.registry.improve_with_lesson(
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
            self.registry.improve_with_lesson(
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
            self.registry.improve_with_lesson(
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

        first = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=event_id,
        )
        replay = self.registry.improve_with_lesson(
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
            self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=replay["sha256"],
                lesson="同一个事件不能改写成另一条经验。",
                event_id=event_id,
            )

    def test_correction_preserves_raw_events_and_removes_bad_lesson_from_active_memory(self) -> None:
        created = self.ensure()
        bad_event_id = str(uuid.uuid4())
        bad_lesson = "错误经验：跳过证据并直接覆盖共享文件。"
        bad = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=bad_lesson,
            event_id=bad_event_id,
        )
        correction_event_id = str(uuid.uuid4())
        corrected_lesson = "纠正经验：先核对证据，并只修改明确分配的写入范围。"
        corrected = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=bad["sha256"],
            lesson=corrected_lesson,
            event_id=correction_event_id,
            retracts_event_id=bad_event_id,
        )
        replay = self.registry.improve_with_lesson(
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
            self.registry.improve_with_lesson(
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
            result = self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"待压缩经验 {index}",
                event_id=event_id,
            )
            current_hash = result["sha256"]
            compaction = result["compaction"]
        assert compaction and compaction["needed"]
        compacted = self.registry.improve_with_summary(
            name=created["name"],
            expected_sha256=current_hash,
            summary="受污染摘要：待压缩经验 2。",
            covered_through=compaction["covered_through"],
            source_digest=compaction["source_digest"],
        )
        corrected = self.registry.improve_with_lesson(
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

    def test_exact_schema_one_migrates_to_three_without_losing_experience(self) -> None:
        created = self.ensure()
        lesson = "旧结构中的原始经验必须完整保留。"
        improved = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=str(uuid.uuid4()),
        )
        with contextlib.closing(self.db()) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                "ALTER TABLE experience_events RENAME TO experience_events_v2;\n"
                + agents.SCHEMA_V1_TABLE_SQL["experience_events"]
                + ";\n"
                "INSERT INTO experience_events("
                "sequence,agent_id,event_id,event_digest,lesson,created_at"
                ") SELECT sequence,agent_id,event_id,event_digest,lesson,created_at "
                "FROM experience_events_v2;\n"
                "DROP TABLE experience_events_v2;\n"
                "DROP TABLE agent_runs;\n"
                "PRAGMA user_version = 1;\n"
                "COMMIT;"
            )

        reused = self.ensure()
        self.assertEqual(reused["action"], "reused")
        self.assertEqual(reused["sha256"], improved["sha256"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
            row = connection.execute(
                "SELECT lesson, retracts_event_id FROM experience_events"
            ).fetchone()
            run_count = connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        self.assertEqual(row["lesson"], lesson)
        self.assertIsNone(row["retracts_event_id"])
        self.assertEqual(run_count, 0)

    def test_exact_schema_two_migrates_to_three_without_backfilling_runs(self) -> None:
        created = self.ensure()
        lesson = "第二版经验与代理身份必须保留，历史存活轮次不猜测。"
        improved = self.registry.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson=lesson,
            event_id=str(uuid.uuid4()),
        )
        with contextlib.closing(self.db()) as connection:
            connection.execute("DROP TABLE agent_runs")
            connection.execute("PRAGMA user_version = 2")
            connection.commit()

        reused = self.ensure()
        self.assertEqual(reused["action"], "reused")
        self.assertEqual(reused["sha256"], improved["sha256"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
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
            result = self.registry.improve_with_lesson(
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
            compacted = self.registry.improve_with_summary(
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
            result = self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"短经验 {index}",
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            self.assertFalse(result["compaction"]["needed"])
        eighth = self.registry.improve_with_lesson(
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
            result = self.registry.improve_with_lesson(
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
            result = self.registry.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_hash,
                lesson=f"并发经验 {index}",
                event_id=str(uuid.uuid4()),
            )
            current_hash = result["sha256"]
            compaction = result["compaction"]
        assert compaction and compaction["needed"]
        refreshed = self.registry.improve_with_summary(
            name=created["name"],
            expected_sha256=current_hash,
            summary="最新压缩摘要。",
            covered_through=compaction["covered_through"],
            source_digest=compaction["source_digest"],
        )
        with self.assertRaises(agents.SpecialistError):
            self.registry.improve_with_summary(
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
        improved = self.registry.improve_with_lesson(
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
        self.assertEqual(receipt["format_version"], 1)
        self.assertEqual(receipt["agent_id"], created["agent_id"])
        self.assertEqual(receipt["name"], created["name"])
        self.assertEqual(receipt["role_key"], "qml-binding-diagnostics")
        self.assertEqual(receipt["original_path"], str(original_path))
        self.assertEqual(receipt["pending_path"], str(pending_path))
        self.assertEqual(receipt["sha256"], created["sha256"])
        self.assertTrue(receipt["created_at"])
        self.assertTrue(receipt["updated_at"])
        self.assertTrue(receipt["retired_at"])
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
        first = self.registry.improve_with_lesson(
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
            )
        elapsed = time.monotonic() - started
        blocker.execute("ROLLBACK")
        self.assertLess(elapsed, 1.0)

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
                ]
            )
        created = json.loads(ensure_output.getvalue())
        self.assertEqual(ensure_exit, 0)
        self.assertEqual(created["action"], "created")

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
