from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
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
            "input_shapes": ["源代码、运行证据和范围说明"],
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
        description: str = "重复完成一个范围清晰、可复核的专门工作。",
        role_instructions: str = "交付直接可消费的结果和必要证据。",
        model: str = "gpt-6-sol",
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

    def mark_legacy_configuration(
        self,
        created: dict[str, object],
        *,
        model: str = "gpt-5.6-terra",
        effort: str = "low",
    ) -> str:
        """Represent an already owned pre-policy role without calling ensure."""
        path = Path(str(created["path"]))
        current = path.read_bytes()
        self.assertIn(b"gpt-6-sol", current)
        self.assertIn(b'model_reasoning_effort = "high"', current)
        legacy = (
            current.replace(b"gpt-6-sol", model.encode("utf-8"))
            .replace(
                b'model_reasoning_effort = "high"',
                f'model_reasoning_effort = "{effort}"'.encode("utf-8"),
            )
            .replace(
                "思考程度：high".encode("utf-8"),
                f"思考程度：{effort}".encode("utf-8"),
            )
        )
        self.assertNotEqual(legacy, current)
        path.write_bytes(legacy)
        legacy_sha256 = agents.sha256_bytes(legacy)
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "UPDATE agents SET expected_sha256 = ? WHERE agent_id = ?",
                (legacy_sha256, created["agent_id"]),
            )
            connection.commit()
        return legacy_sha256

    def remove_canonical_contract_instruction(self, created: dict[str, object]) -> str:
        path = Path(str(created["path"]))
        instruction = agents.global_contract_instruction(self.contract()).encode("utf-8")
        current = path.read_bytes()
        self.assertEqual(current.count(instruction), 1)
        legacy = current.replace(instruction, b"", 1)
        legacy_sha256 = agents.sha256_bytes(legacy)
        path.write_bytes(legacy)
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "UPDATE agents SET expected_sha256=? WHERE agent_id=?",
                (legacy_sha256, created["agent_id"]),
            )
            connection.commit()
        return legacy_sha256

    def add_legacy_visible_speed_declaration(self, created: dict[str, object]) -> str:
        path = Path(str(created["path"]))
        current = path.read_bytes()
        payload = tomllib.loads(current.decode("utf-8"))
        header = agents.parse_header(current.decode("utf-8"))
        developer = payload["developer_instructions"]
        effort_line = f"思考程度：{payload['model_reasoning_effort']}\n"
        self.assertEqual(developer.count(effort_line), 1)
        legacy_developer = developer.replace(
            effort_line,
            effort_line + "速度：快速\n",
        )
        display_name, short_description = payload["description"].split("：", 1)
        legacy = agents.build_agent_bytes(
            agent_id=header["agent_id"],
            role_key=header["role_key"],
            owner_token=header["owner_token"],
            name=payload["name"],
            display_name=display_name,
            description=short_description,
            model=payload["model"],
            effort=payload["model_reasoning_effort"],
            authority=(
                "write" if payload["sandbox_mode"] == "workspace-write" else "read"
            ),
            instruction_base=legacy_developer,
            memory=self.registry._experience_memory(payload),
            speed="fast",
            global_domain_key=header["global_domain_key"],
            global_contract_digest=header["global_contract_digest"],
        )
        legacy_sha256 = agents.sha256_bytes(legacy)
        path.write_bytes(legacy)
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "UPDATE agents SET expected_sha256=? WHERE agent_id=?",
                (legacy_sha256, created["agent_id"]),
            )
            connection.commit()
        return legacy_sha256

    def registry_rows(self) -> dict[str, list[tuple[object, ...]]]:
        with contextlib.closing(self.db()) as connection:
            return {
                table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
                for table in (
                    "agents", "agent_runs", "experience_events", "experience_summaries",
                    "experience_recall_receipts",
                )
            }

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
            connection.execute("DROP TABLE experience_recall_receipts")
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
            else:
                connection.execute(
                    "ALTER TABLE agent_runs DROP COLUMN completion_experience_event_id"
                )
                connection.execute(
                    "ALTER TABLE agent_runs DROP COLUMN completion_receipt_version"
                )
                connection.execute("ALTER TABLE agent_runs DROP COLUMN loaded_experience_digest")
                connection.execute("ALTER TABLE agent_runs DROP COLUMN outcome")
            connection.execute(f"PRAGMA user_version = {version}")
            connection.execute("COMMIT")
        return rows

    def downgrade_attempt_schema(self) -> None:
        with contextlib.closing(self.db()) as connection:
            agent_rows = [dict(row) for row in connection.execute("SELECT * FROM agents")]
            event_rows = [
                tuple(row) for row in connection.execute(
                    "SELECT sequence,agent_id,event_id,event_digest,lesson,retracts_event_id,created_at "
                    "FROM experience_events ORDER BY sequence"
                )
            ]
            summary_rows = [
                tuple(row) for row in connection.execute(
                    "SELECT agent_id,summary,covered_through_sequence,source_digest,updated_at "
                    "FROM experience_summaries"
                )
            ]
            run_rows = [
                tuple(row) for row in connection.execute(
                    "SELECT run_id,agent_id,invocation_kind,completed_at FROM agent_runs"
                )
            ]
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("BEGIN IMMEDIATE")
            for table in (
                "experience_recall_receipts", "experience_summaries",
                "experience_events", "agent_runs", "agents",
            ):
                connection.execute(f"DROP TABLE {table}")
            for statement in agents.SCHEMA_V4_TABLE_SQL.values():
                connection.execute(statement)
            for row in agent_rows:
                connection.execute(
                    "INSERT INTO agents(agent_id,name,role_key,path,owner_token,expected_sha256,"
                    "created_at,updated_at,global_contract_version,global_domain_key,global_contract,"
                    "global_contract_digest) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(row[key] for key in (
                        "agent_id", "name", "role_key", "path", "owner_token",
                        "expected_sha256", "created_at", "updated_at",
                        "global_contract_version", "global_domain_key", "global_contract",
                        "global_contract_digest",
                    )),
                )
            connection.executemany(
                "INSERT INTO experience_events(sequence,agent_id,event_id,event_digest,lesson,"
                "retracts_event_id,created_at) VALUES(?,?,?,?,?,?,?)",
                event_rows,
            )
            connection.executemany(
                "INSERT INTO experience_summaries(agent_id,summary,covered_through_sequence,"
                "source_digest,updated_at) VALUES(?,?,?,?,?)",
                summary_rows,
            )
            connection.executemany(
                "INSERT INTO agent_runs(run_id,agent_id,invocation_kind,completed_at) "
                "VALUES(?,?,?,?)",
                run_rows,
            )
            connection.execute("PRAGMA user_version = 4")
            connection.execute("COMMIT")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                agents.exact_schema(connection),
                agents.expected_schema(agents.SCHEMA_V4_TABLE_SQL),
            )

    def downgrade_experience_schema(self) -> None:
        with contextlib.closing(self.db()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE experience_recall_receipts")
            connection.execute(
                "ALTER TABLE agent_runs DROP COLUMN completion_experience_event_id"
            )
            connection.execute(
                "ALTER TABLE agent_runs DROP COLUMN completion_receipt_version"
            )
            connection.execute("ALTER TABLE agent_runs DROP COLUMN loaded_experience_digest")
            connection.execute("PRAGMA user_version = 5")
            connection.execute("COMMIT")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                agents.exact_schema(connection),
                agents.expected_schema(agents.SCHEMA_V5_TABLE_SQL),
            )

    def downgrade_completion_receipt_schema(self) -> None:
        with contextlib.closing(self.db()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE experience_recall_receipts")
            connection.execute(
                "ALTER TABLE agent_runs DROP COLUMN completion_experience_event_id"
            )
            connection.execute(
                "ALTER TABLE agent_runs DROP COLUMN completion_receipt_version"
            )
            connection.execute("PRAGMA user_version = 6")
            connection.execute("COMMIT")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                agents.exact_schema(connection),
                agents.expected_schema(agents.SCHEMA_V6_TABLE_SQL),
            )

    def downgrade_recall_receipt_schema(self) -> None:
        with contextlib.closing(self.db()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE experience_recall_receipts")
            connection.execute("PRAGMA user_version = 7")
            connection.execute("COMMIT")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                agents.exact_schema(connection),
                agents.expected_schema(agents.SCHEMA_V7_TABLE_SQL),
            )

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
            "子代理名称：QML 绑定诊断员（复用）\n"
            "模型：gpt-6-sol\n"
            "思考程度：high\n"
        )
        self.assertIn(opening, instructions)
        self.assertNotIn("角色名称：", instructions)
        role = instructions.index(role_paragraph)
        communication = instructions.index("首次 spawn_agent 或 followup_task 明确开始新当前子任务时", role)
        declaration = instructions.index(opening, communication)
        status = instructions.index("后两行只采用父代理对本保留身份执行单角色 recall", declaration)
        execution = instructions.index("只完成任务卡分配的当前子任务", status)
        final_result = instructions.index("最终回复顶部原样写当前任务卡前三行实际值", execution)
        final_task = instructions.index("子任务：<当前子任务>", final_result)
        self.assertEqual(instructions.count(opening), 1)
        self.assertLess(role, communication)
        self.assertLess(communication, declaration)
        self.assertLess(declaration, status)
        self.assertLess(status, execution)
        self.assertLess(final_result, final_task)
        for child_contract in (
            "任务卡必须提供五行实际值",
            "第一条可见进展说明必须原样以这五行开头",
            "新任务卡缺少任一状态行时，先通过 collaboration.send_message 向父代理",
            "报告具体缺失字段并暂停该子任务，由父代理补齐或改派运行时子代理",
            "任务卡后两行包含“任务卡未提供”“未核验”或“未核验持久化经验”时同样视为缺失",
            "不得在用户可见进展中展示；先按上述内部消息流程补齐",
            "只发送增量信息，不要求重复任务卡，也不重复开场",
            "该固定配置只约束当前保留身份",
            "下游保留身份按自己的五行实际值开场",
            "继承到下游的上级保留身份固定配置不得覆盖下游任务卡",
            "不可自估或编造",
            "不得声明经验适用性",
            "run_id 即使出现在输入中也不得回显",
            "只按职责和具名缺口有限读取",
            "同一来源已有所有者和完整快照时不重新发现或通读",
            "已加载经验只作有界提示",
            "默认是普通子代理，不自行委派",
            "只有任务卡明确指定协作父代理",
            "只在依赖解锁、必要纠偏、风险或阻断时使用 collaboration.send_message",
            "实现任务须完成授权范围内的运行或测试与失败修补",
            "不代交或隐藏其他子代理结果",
            "状态：完成 | 部分完成 | 受阻",
            "SOURCE_COVERAGE",
        ):
            self.assertIn(child_contract, instructions)
        self.assertLess(
            instructions.index("首次 spawn_agent 或 followup_task 明确开始新当前子任务时"),
            instructions.index(opening),
        )
        self.assertNotIn("commentary", instructions)
        self.assertNotIn("你的第一动作必须", instructions)
        self.assertNotIn("显示前不得读取、分析或调用其他工具", instructions)
        self.assertIn("QML 绑定诊断员", instructions)
        for parent_owned_contract in (
            "MODEL_ROUTE",
            "gpt-6-astra",
            "可接受成本带",
            "migrate-attempts",
            "FAILURE_REMOVAL_THRESHOLD",
            "WRITE_ROUTE",
            "create_thread、read_thread、wait_threads",
            "先选唯一子代理、再维护经验、最后结束其他子代理",
            "普通文件精确送入 Windows 回收站",
        ):
            self.assertNotIn(parent_owned_contract, instructions)

    def test_retained_role_new_task_requires_five_recalled_opening_lines(self) -> None:
        created = self.ensure()
        recalled = self.registry.recall(name=created["name"])
        opening_lines = (
            recalled["opening_declaration"] + recalled["opening_status"]
        ).splitlines()
        self.assertEqual(len(opening_lines), 5)
        self.assertEqual(opening_lines[:3], [
            "子代理名称：QML 绑定诊断员（复用）", "模型：gpt-6-sol", "思考程度：high"
        ])
        self.assertTrue(opening_lines[3].startswith("存活轮次："))
        self.assertTrue(opening_lines[4].startswith("经验："))
        self.assertEqual(
            agents.opening_configuration_declaration(
                display_name="QML 绑定诊断员（复用）",
                model="gpt-6-sol", effort="high",
            ),
            recalled["opening_declaration"],
        )
        with self.assertRaisesRegex(agents.SpecialistError, "cannot use the new-agent"):
            agents.opening_configuration_declaration(
                display_name="QML 绑定诊断员（新建）",
                model="gpt-6-sol", effort="high",
            )

        instructions = tomllib.loads(
            Path(created["path"]).read_text(encoding="utf-8")
        )["developer_instructions"]
        self.assertIn("首次 spawn_agent 或 followup_task 明确开始新当前子任务时", instructions)
        self.assertIn("第一条可见进展说明必须原样以这五行开头", instructions)
        self.assertIn("名称第一行须带真实调用类型标记", instructions)
        self.assertIn("选中本保留身份并经单角色 recall 后使用“（复用）”", instructions)
        self.assertIn("运行时新角色由父代理填写“（新建）”", instructions)
        self.assertIn("同一个 live child 明确开始新子任务时使用“（复用）”", instructions)
        self.assertIn("其中名称标记与首条进展保持一致", instructions)
        self.assertIn("后两行只采用父代理对本保留身份执行单角色 recall", instructions)
        self.assertIn("新任务卡缺少任一状态行时，先通过 collaboration.send_message 向父代理", instructions)
        self.assertIn("报告具体缺失字段并暂停该子任务", instructions)
        self.assertIn(
            "任务卡后两行包含“任务卡未提供”“未核验”或“未核验持久化经验”时同样视为缺失",
            instructions,
        )
        self.assertIn("不得在用户可见进展中展示；先按上述内部消息流程补齐", instructions)
        self.assertIn("同一当前子任务", instructions)
        self.assertIn("最终回复只重复当前任务卡前三行实际值", instructions)
        self.assertNotIn("存活轮次和经验是保留角色的可选状态", instructions)

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

    def test_utf8_memory_window_does_not_impose_a_total_agent_size_limit(self) -> None:
        with self.assertRaisesRegex(
            agents.SpecialistError,
            "summary plus its label must fit",
        ):
            agents.validate_summary("中" * agents.MAX_SUMMARY_CHARS)

        base = agents.base_instructions(
            display_name="长说明核对员",
            role_key="long-instruction-review",
            role_instructions="逐项核对输入范围和决定性证据。" * 55,
            model="gpt-6-luna",
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
            "model": "gpt-6-luna",
            "effort": "medium",
            "authority": "read",
            "instruction_base": base,
            "speed": "standard",
            "global_domain_key": "instruction-review",
            "global_contract_digest": "0" * 64,
        }

        memory = self.registry._memory_for_toml(
            "保留可复用摘要。",
            [{"lesson": "证据充分。" * 500}],
        )
        combined = agents.compose_instructions(base, memory)
        built = agents.build_agent_bytes(**render_args, memory=memory)
        self.assertEqual(
            tomllib.loads(built.decode("utf-8"))["developer_instructions"],
            combined,
        )
        self.assertLessEqual(len(memory.encode("utf-8")), agents.MAX_MEMORY_BYTES)

    def test_single_experience_character_bound_does_not_cap_event_count(self) -> None:
        accepted = agents.validate_lesson("经" * agents.MAX_LESSON_CHARS)
        self.assertEqual(len(accepted), agents.MAX_LESSON_CHARS)
        with self.assertRaisesRegex(
            agents.SpecialistError,
            f"1-{agents.MAX_LESSON_CHARS} characters",
        ):
            agents.validate_lesson("经" * (agents.MAX_LESSON_CHARS + 1))

    def test_memory_window_is_independent_of_serialized_toml_size(self) -> None:
        render_args = {
            "agent_id": "00000000-0000-4000-8000-000000000000",
            "role_key": "capacity-review",
            "owner_token": "0" * 32,
            "name": "lean_capacity_review_00000000",
            "display_name": "容量核对员",
            "description": "核对容量。",
            "model": "gpt-6-luna",
            "effort": "medium",
            "authority": "read",
            "instruction_base": "中" * 20000,
            "speed": "standard",
            "global_domain_key": "capacity-review",
            "global_contract_digest": "0" * 64,
        }

        def render(candidate: str) -> bytes:
            return agents._render_agent_bytes(**render_args, memory=candidate)

        empty = agents.memory_block("", [])
        self.assertGreater(len(render(empty)), 48 * 1024)
        memory = self.registry._memory_for_toml(
            "",
            [{"lesson": "证据充分。" * 100}],
        )
        self.assertNotEqual(memory, empty)
        self.assertIn("证据充分。", memory)
        built = agents.build_agent_bytes(**render_args, memory=memory)
        self.assertEqual(built, render(memory))

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
            "子代理名称：快速来源核对员（复用）\n"
            "模型：gpt-6-sol\n"
            "思考程度：medium\n"
        )
        self.assertEqual(instructions.count(opening), 1)
        self.assertLess(instructions.index("你是专门负责"), instructions.index(opening))
        self.assertLess(
            instructions.index("首次 spawn_agent 或 followup_task 明确开始新当前子任务时"),
            instructions.index("只完成任务卡分配的当前子任务"),
        )
        self.assertLess(
            instructions.index("最终回复顶部原样写当前任务卡前三行实际值"),
            instructions.index("子任务：<当前子任务>"),
        )

    def test_ensure_omitted_speed_defaults_all_models_to_standard(self) -> None:
        luna = self.ensure(
            role_key="luna-default-speed-review",
            global_domain_key="luna-default-speed-review",
            model="gpt-5.6-luna",
            effort="medium",
        )
        terra = self.ensure(
            role_key="terra-default-speed-review",
            global_domain_key="terra-default-speed-review",
            model="gpt-6-sol",
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
        self.assertNotIn("service_tier", luna_payload)
        self.assertNotIn("速度：", luna_payload["developer_instructions"])
        self.assertNotIn("service_tier", terra_payload)
        self.assertNotIn("速度：", terra_payload["developer_instructions"])
        self.assertNotIn("service_tier", standard_payload)

    def test_omitted_standard_does_not_overwrite_explicit_fast_without_cas(self) -> None:
        created = self.ensure(
            role_key="luna-default-reconfiguration",
            global_domain_key="luna-default-reconfiguration",
            model="gpt-5.6-luna",
            effort="medium",
            speed="fast",
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
        self.assertNotIn("service_tier", payload)
        self.assertIn("安全重配必须保留身份", payload["developer_instructions"])

        standard_bytes = path.read_bytes()
        repeated = self.ensure(
            role_key="luna-default-reconfiguration",
            global_domain_key="luna-default-reconfiguration",
            model="gpt-5.6-luna",
            effort="medium",
        )
        self.assertEqual(repeated["action"], "reused")
        self.assertEqual(path.read_bytes(), standard_bytes)

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
        created = self.ensure()
        with contextlib.closing(self.db()) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(
                agents.exact_schema(connection),
                agents.expected_schema(agents.SCHEMA_TABLE_SQL),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO agent_runs("
                    "run_id,agent_id,invocation_kind,completed_at,outcome,"
                    "completion_receipt_version,completion_experience_event_id"
                    ") VALUES(?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), created["agent_id"], "spawn_agent",
                        agents.utc_now(), "success", agents.ORDINARY_RUN_RECEIPT_VERSION,
                        str(uuid.uuid4()),
                    ),
                )
        self.assertEqual(
            tables,
            {
                "agents", "experience_events", "experience_summaries", "agent_runs",
                "experience_recall_receipts",
            },
        )
        self.assertEqual(version, agents.SCHEMA_VERSION)
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
            model="gpt-6-sol",
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
            model="gpt-6-sol",
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
        created = self.ensure(authority="write")
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
        self.assertLess(instructions.index("你是专门负责"), instructions.index("子代理名称：QML 根因核对员"))
        self.assertIn("实际依赖图", instructions)
        self.assertIn(lesson, instructions)
        self.assertIn("任务卡必须提供五行实际值", instructions)
        self.assertIn("只发送增量信息，不要求重复任务卡，也不重复开场", instructions)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )

    def test_ensure_reconfiguration_never_upgrades_read_authority(self) -> None:
        reader = self.ensure()
        path = Path(reader["path"])
        original = path.read_bytes()
        with contextlib.closing(self.db()) as connection:
            original_row = tuple(connection.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (reader["agent_id"],)
            ).fetchone())

        for expected_sha256 in (None, reader["sha256"]):
            with self.subTest(expected_sha256=expected_sha256):
                with self.assertRaisesRegex(
                    agents.SpecialistError, "cannot be reconfigured with write authority"
                ):
                    self.ensure(authority="write", expected_sha256=expected_sha256)
                self.assertEqual(path.read_bytes(), original)
                with contextlib.closing(self.db()) as connection:
                    row = tuple(connection.execute(
                        "SELECT * FROM agents WHERE agent_id = ?", (reader["agent_id"],)
                    ).fetchone())
                self.assertEqual(row, original_row)

        writer = self.ensure(role_key="permission-downgrade", authority="write")
        preview = self.ensure(role_key="permission-downgrade", authority="read")
        self.assertEqual(preview["action"], "reconfiguration_required")
        downgraded = self.ensure(
            role_key="permission-downgrade", authority="read",
            expected_sha256=writer["sha256"],
        )
        self.assertEqual(downgraded["action"], "reconfigured")
        payload = tomllib.loads(Path(writer["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["sandbox_mode"], "read-only")

    def test_current_schema_missing_contract_instruction_requires_cas_refresh_and_preserves_state(self) -> None:
        created = self.ensure(speed="fast")
        current_sha256 = created["sha256"]
        compaction = None
        for index in range(8):
            recorded = self.improve_with_lesson(
                name=created["name"],
                expected_sha256=current_sha256,
                event_id=str(uuid.uuid4()),
                lesson=f"适用情境：旧子代理输入 {index}；做法：保留证据；证据：测试；例外：无。",
            )
            current_sha256 = recorded["sha256"]
            compaction = recorded["compaction"]
        self.assertTrue(compaction["needed"])
        summarized = self.improve_with_summary(
            name=created["name"],
            expected_sha256=current_sha256,
            summary="旧子代理的可复用摘要。",
            covered_through=compaction["covered_through"],
            source_digest=compaction["source_digest"],
        )
        current_sha256 = summarized["sha256"]
        self.registry.record_run(
            name=created["name"],
            expected_sha256=current_sha256,
            run_id=str(uuid.uuid4()),
            invocation_kind="spawn_agent",
            outcome="success",
        )
        legacy_sha256 = self.remove_canonical_contract_instruction(created)
        path = Path(created["path"])
        legacy_bytes = path.read_bytes()
        before = self.registry_rows()
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                agents.SCHEMA_VERSION,
            )

        for operation in (
            lambda: self.registry.recall(name=created["name"]),
            lambda: self.registry.status(),
            lambda: self.registry.status(for_routing=True),
            lambda: self.registry.status(for_dashboard=True),
        ):
            with self.subTest(operation=operation), self.assertRaisesRegex(
                agents.SpecialistError, "canonical global contract"
            ):
                operation()

        ensure_cli = [
            "--codex-home", str(self.codex_home), "ensure",
            "--role-key", "qml-binding-diagnostics",
            "--display-name", "QML 绑定诊断员",
            "--description", "重复完成一个范围清晰、可复核的专门工作。",
            "--instructions", "交付直接可消费的结果和必要证据。",
            "--model", "gpt-6-sol",
            "--reasoning-effort", "high",
            "--speed", "fast",
            "--authority", "read",
            "--global-domain-key", "interface-binding-diagnostics",
            "--global-contract", json.dumps(self.contract(), ensure_ascii=False),
            "--origin-term", "当前任务来源",
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(agents.main(ensure_cli), 0)
        preview = json.loads(output.getvalue())
        self.assertEqual(preview["action"], "global_contract_refresh_required")
        self.assertFalse(preview["compatible"])
        self.assertTrue(preview["contract_refresh_required"])
        self.assertEqual(preview["retry_with_expected_sha256"], legacy_sha256)
        self.assertEqual(path.read_bytes(), legacy_bytes)
        self.assertEqual(self.registry_rows(), before)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                agents.main([*ensure_cli, "--expected-sha256", legacy_sha256]),
                0,
            )
        refreshed = json.loads(output.getvalue())
        self.assertEqual(refreshed["action"], "global_contract_refreshed")
        self.assertTrue(refreshed["compatible"])
        self.assertTrue(refreshed["experience_preserved"])
        self.assertFalse(refreshed["contract_refresh_required"])
        self.assertEqual(refreshed["agent_id"], created["agent_id"])
        self.assertEqual(refreshed["owner_token"], created["owner_token"])
        self.assertEqual(refreshed["path"], created["path"])
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["service_tier"], "fast")
        self.assertNotIn("速度：", payload["developer_instructions"])
        self.assertIn(
            agents.global_contract_instruction(self.contract()),
            payload["developer_instructions"],
        )
        self.assertIn("旧子代理的可复用摘要", payload["developer_instructions"])

        after = self.registry_rows()
        self.assertEqual(after["agent_runs"], before["agent_runs"])
        self.assertEqual(after["experience_events"], before["experience_events"])
        self.assertEqual(after["experience_summaries"], before["experience_summaries"])
        agent_columns = (
            "agent_id", "name", "role_key", "path", "owner_token", "created_at",
            "global_contract_version", "global_domain_key", "global_contract",
            "global_contract_digest", "retired_at",
        )
        with contextlib.closing(self.db()) as connection:
            restored = connection.execute("SELECT * FROM agents").fetchone()
            self.assertEqual(
                tuple(restored[column] for column in agent_columns),
                tuple(dict(zip(restored.keys(), before["agents"][0]))[column] for column in agent_columns),
            )
        recalled = self.registry.recall(
            name=created["name"], expected_sha256=refreshed["sha256"]
        )
        self.assertIn("旧子代理的可复用摘要", recalled["experience"])
        self.assertEqual(recalled["retention_state"]["survival_rounds"], 1)
        self.assertEqual(self.registry.status()["registered_count"], 1)
        self.assertEqual(self.registry.status(for_dashboard=True)["retained_agent_count"], 1)
        self.assertEqual(self.ensure(speed="fast")["action"], "reused")

    def test_legacy_visible_speed_declaration_refresh_preserves_fast_configuration(self) -> None:
        created = self.ensure(
            role_key="legacy-fast-opening",
            global_domain_key="legacy-fast-opening",
            display_name="快速配置核对员",
            model="gpt-5.6-luna",
            effort="medium",
            speed="fast",
        )
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            event_id=str(uuid.uuid4()),
            lesson="迁移可见声明时保留真实会话配置和既有经验。",
        )
        legacy_sha256 = self.add_legacy_visible_speed_declaration(created)
        path = Path(created["path"])
        before = path.read_bytes()

        with self.assertRaisesRegex(
            agents.SpecialistError, "legacy visible speed declaration"
        ):
            self.registry.recall(name=created["name"])
        with self.assertRaisesRegex(
            agents.SpecialistError, "legacy visible speed declaration"
        ):
            self.registry.status(for_routing=True)

        preview = self.ensure(
            role_key="legacy-fast-opening",
            global_domain_key="legacy-fast-opening",
            display_name="快速配置核对员",
            model="gpt-5.6-luna",
            effort="medium",
            speed="fast",
        )
        self.assertEqual(preview["action"], "reconfiguration_required")
        self.assertFalse(preview["contract_refresh_required"])
        self.assertTrue(preview["visible_declaration_refresh_required"])
        self.assertEqual(preview["retry_with_expected_sha256"], legacy_sha256)
        self.assertEqual(path.read_bytes(), before)

        refreshed = self.ensure(
            role_key="legacy-fast-opening",
            global_domain_key="legacy-fast-opening",
            display_name="快速配置核对员",
            model="gpt-5.6-luna",
            effort="medium",
            speed="fast",
            expected_sha256=legacy_sha256,
        )
        self.assertEqual(refreshed["action"], "reconfigured")
        self.assertFalse(refreshed["visible_declaration_refresh_required"])
        self.assertEqual(refreshed["agent_id"], created["agent_id"])
        self.assertEqual(refreshed["owner_token"], created["owner_token"])
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["service_tier"], "fast")
        self.assertNotIn("速度：", payload["developer_instructions"])
        recalled = self.registry.recall(
            name=created["name"], expected_sha256=refreshed["sha256"]
        )
        self.assertEqual(recalled["speed"], "fast")
        self.assertNotIn("速度：", recalled["opening_declaration"])
        self.assertIn("既有经验", recalled["experience"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM experience_events WHERE agent_id=?",
                    (created["agent_id"],),
                ).fetchone()[0],
                1,
            )

    def test_current_schema_contract_refresh_wrong_cas_busy_commit_failure_and_drift_are_zero_write(self) -> None:
        created = self.ensure()
        legacy_sha256 = self.remove_canonical_contract_instruction(created)
        path = Path(created["path"])
        legacy_bytes = path.read_bytes()
        before = self.registry_rows()

        with self.assertRaisesRegex(agents.SpecialistError, "expected SHA-256"):
            self.ensure(expected_sha256="0" * 64)
        self.assertEqual(path.read_bytes(), legacy_bytes)
        self.assertEqual(self.registry_rows(), before)

        blocker = sqlite3.connect(self.registry.db_path, isolation_level=None)
        try:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.ensure(expected_sha256=legacy_sha256)
        finally:
            blocker.close()
        self.assertEqual(path.read_bytes(), legacy_bytes)
        self.assertEqual(self.registry_rows(), before)

        real_connection = self.registry.connect()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced contract refresh commit failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(
            self.registry,
            "connect",
            return_value=FailingCommitConnection(),
        ):
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "forced contract refresh commit failure"
            ):
                self.ensure(expected_sha256=legacy_sha256)
        self.assertEqual(path.read_bytes(), legacy_bytes)
        self.assertEqual(self.registry_rows(), before)

        drifted = legacy_bytes + b"\n"
        path.write_bytes(drifted)
        with self.assertRaisesRegex(agents.SpecialistError, "content drifted"):
            self.ensure(expected_sha256=legacy_sha256)
        self.assertEqual(path.read_bytes(), drifted)
        self.assertEqual(self.registry_rows(), before)

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

    def test_ensure_reports_failed_file_restoration_after_sql_commit_failure(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        original = path.read_bytes()
        real_replace = agents.replace_exact_file
        real_connection = self.registry.connect()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced ensure commit failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        calls = 0

        def fail_restore(target, *, expected, replacement):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("forced TOML restoration failure")
            return real_replace(target, expected=expected, replacement=replacement)

        with mock.patch.object(self.registry, "connect", return_value=FailingCommitConnection()), \
                mock.patch.object(agents, "replace_exact_file", side_effect=fail_restore):
            with self.assertRaisesRegex(
                agents.SpecialistError,
                "managed TOML recovery is incomplete: forced TOML restoration failure",
            ) as caught:
                self.ensure(description="重配后触发提交失败。", expected_sha256=created["sha256"])

        self.assertIsInstance(caught.exception.__cause__, sqlite3.OperationalError)
        self.assertEqual(calls, 2)
        self.assertNotEqual(path.read_bytes(), original)
        with contextlib.closing(self.db()) as connection:
            row = connection.execute(
                "SELECT expected_sha256 FROM agents WHERE agent_id=?", (created["agent_id"],)
            ).fetchone()
        self.assertEqual(row["expected_sha256"], created["sha256"])

    def test_ensure_preserves_external_file_change_during_failed_reconfiguration(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        external = b"external writer data; preserve for manual review"
        real_replace = agents.replace_exact_file
        real_connection = self.registry.connect()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced ensure commit failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        def external_edit(target, *, expected, replacement):
            real_replace(target, expected=expected, replacement=replacement)
            target.write_bytes(external)

        with mock.patch.object(self.registry, "connect", return_value=FailingCommitConnection()), \
                mock.patch.object(agents, "replace_exact_file", side_effect=external_edit):
            with self.assertRaisesRegex(
                agents.SpecialistError, "changed externally; current file was preserved"
            ):
                self.ensure(description="重配遇到外部修改。", expected_sha256=created["sha256"])
        self.assertEqual(path.read_bytes(), external)

    def test_ensure_created_file_cleanup_preserves_external_change(self) -> None:
        real_connection = self.registry.connect()
        changed_path = None
        external = b"external writer data; preserve for manual review"

        class FailingInsertConnection:
            def execute(self, sql, parameters=()):
                nonlocal changed_path
                if sql.startswith("INSERT INTO agents("):
                    changed_path = Path(parameters[3])
                    changed_path.write_bytes(external)
                    raise sqlite3.OperationalError("forced ensure insert failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(self.registry, "connect", return_value=FailingInsertConnection()):
            with self.assertRaisesRegex(
                agents.SpecialistError, "new specialist changed externally; current file was preserved"
            ) as caught:
                self.ensure()
        self.assertIsInstance(caught.exception.__cause__, sqlite3.OperationalError)
        self.assertIsNotNone(changed_path)
        self.assertEqual(changed_path.read_bytes(), external)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0)

    def test_new_file_write_failure_preserves_changed_path_and_cleans_own_bytes(self) -> None:
        path = Path(self.temporary.name) / "failed-new-file.toml"
        data = b"created by this write"
        external = b"external replacement; preserve"

        def overwrite_and_fail(_descriptor):
            if os.name == "nt":
                with self.assertRaises(PermissionError):
                    path.write_bytes(external)
            else:
                path.write_bytes(external)
            raise OSError("forced fsync failure")

        with mock.patch.object(agents.os, "fsync", side_effect=overwrite_and_fail):
            if os.name == "nt":
                with self.assertRaisesRegex(OSError, "forced fsync failure"):
                    agents.write_new_file(path, data)
                self.assertFalse(path.exists())
            else:
                with self.assertRaisesRegex(
                    agents.SpecialistError,
                    "new specialist file changed externally; current file was preserved",
                ) as caught:
                    agents.write_new_file(path, data)
                self.assertIsInstance(caught.exception.__cause__, OSError)
                self.assertEqual(path.read_bytes(), external)
                path.unlink()
        with mock.patch.object(agents.os, "fsync", side_effect=OSError("forced fsync failure")):
            with self.assertRaisesRegex(OSError, "forced fsync failure"):
                agents.write_new_file(path, data)
        self.assertFalse(path.exists())

    def assert_windows_competitor_blocked(self, path: Path) -> None:
        """A real process ignores our SQLite/ Python locks and attacks the path."""
        competitor = """
import json, os, pathlib, sys
p = pathlib.Path(sys.argv[1])
other = p.with_name(p.name + '.competitor')
other.write_bytes(b'external replacement')
results = {}
for name, operation in (
    ('write', lambda: p.write_bytes(b'external write')),
    ('unlink', lambda: p.unlink()),
    ('replace', lambda: os.replace(other, p)),
    ('rename', lambda: p.rename(p.with_name(p.name + '.stolen'))),
    ('parent_rename', lambda: p.parent.rename(p.parent.with_name(p.parent.name + '.stolen'))),
):
    try:
        operation()
    except OSError as error:
        results[name] = error.winerror or -error.errno
    else:
        results[name] = 'UNEXPECTED_SUCCESS'
if other.exists():
    other.unlink()
print(json.dumps(results))
"""
        result = subprocess.run([sys.executable, "-B", "-c", competitor, str(path)],
                                check=True, capture_output=True, text=True, timeout=15)
        outcomes = json.loads(result.stdout)
        self.assertEqual(set(outcomes), {"write", "unlink", "replace", "rename", "parent_rename"})
        # Python's CRT-backed open maps sharing violations to errno EACCES (13)
        # without winerror; native path operations preserve Windows codes.
        self.assertTrue(all(value in {5, 32, -13} for value in outcomes.values()), outcomes)

    @unittest.skipUnless(os.name == "nt", "Windows mandatory sharing semantics")
    def test_windows_fdopen_failure_closes_transferred_handle(self) -> None:
        for create in (False, True):
            with self.subTest(create=create):
                path = self.registry.agents_dir / f"fdopen-failure-{create}.toml"
                if not create:
                    path.write_bytes(b"original")
                with mock.patch.object(agents.os, "fdopen", side_effect=OSError("forced stream failure")), \
                        mock.patch.object(agents.os, "close", wraps=os.close) as close:
                    with self.assertRaisesRegex(OSError, "forced stream failure"):
                        with agents._windows_managed_file(path, create=create):
                            self.fail("failed fdopen must not yield a stream")
                close.assert_called_once()
                with self.assertRaises(OSError):
                    os.fstat(close.call_args.args[0])
                if create:
                    self.assertFalse(path.exists())
                else:
                    self.assertEqual(path.read_bytes(), b"original")
                # Reopening would fail if the exclusive native handle leaked.
                path.write_bytes(b"reopened after failure")

    @unittest.skipUnless(os.name == "nt", "Windows directory handle sharing semantics")
    def test_windows_parent_guard_alone_blocks_directory_replacement(self) -> None:
        directory = Path(self.temporary.name) / "directory-guard-only"
        directory.mkdir()
        path = directory / "plain.txt"
        path.write_bytes(b"before")
        competitor = """
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_bytes(b'child file was writable')
try:
    p.parent.rename(p.parent.with_name('directory-was-stolen'))
except OSError as error:
    print(json.dumps({'blocked': error.winerror or -error.errno}))
else:
    print(json.dumps({'blocked': False}))
"""
        with agents._windows_parent_guard(path):
            result = subprocess.run([sys.executable, "-B", "-c", competitor, str(path)],
                                    check=True, capture_output=True, text=True, timeout=15)
        self.assertIn(json.loads(result.stdout)["blocked"], {5, 32, -13})
        self.assertEqual(path.read_bytes(), b"child file was writable")
        directory.rename(directory.with_name("guard-released"))

    @unittest.skipUnless(os.name == "nt", "Windows mandatory sharing semantics")
    def test_windows_migration_move_rejects_changed_source_and_existing_destination(self) -> None:
        source = self.registry.agents_dir / "source.toml"
        destination = self.registry.state_dir / "moved.toml"
        source.write_bytes(b"owned")
        subprocess.run([sys.executable, "-B", "-c",
                        "import os,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
                        "q=p.with_suffix('.external'); q.write_bytes(b'outside'); os.replace(q,p)",
                        str(source)], check=True, timeout=15)
        with self.assertRaisesRegex(agents.SpecialistError, "source changed immediately"):
            agents.rename_exact_file_no_replace(source, destination, expected=b"owned")
        self.assertEqual(source.read_bytes(), b"outside")
        self.assertFalse(destination.exists())
        source.write_bytes(b"owned")
        destination.write_bytes(b"existing destination")
        with self.assertRaises(OSError):
            agents.rename_exact_file_no_replace(source, destination, expected=b"owned")
        self.assertEqual(source.read_bytes(), b"owned")
        self.assertEqual(destination.read_bytes(), b"existing destination")

    @unittest.skipUnless(os.name == "nt", "Windows mandatory sharing semantics")
    def test_windows_reconfigure_blocks_process_after_final_verification(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        original = path.read_bytes()
        real_rename = agents._windows_rename_file
        attempts = 0

        def compete_then_rename(handle, destination):
            nonlocal attempts
            if attempts == 0:
                attempts += 1
                self.assert_windows_competitor_blocked(path)
            return real_rename(handle, destination)

        with mock.patch.object(agents, "_windows_rename_file", side_effect=compete_then_rename):
            result = self.ensure(description="句柄保护的重配。", expected_sha256=created["sha256"])
        self.assertEqual(attempts, 1)
        self.assertEqual(result["action"], "reconfigured")
        self.assertNotEqual(path.read_bytes(), original)
        self.assertEqual(agents.sha256_bytes(path.read_bytes()), result["sha256"])
        self.assertEqual(list(path.parent.iterdir()), [path])

    @unittest.skipUnless(os.name == "nt", "Windows mandatory sharing semantics")
    def test_windows_removals_block_process_after_final_verification(self) -> None:
        for second_failure in (False, True):
            with self.subTest(second_failure=second_failure):
                created = self.ensure(role_key="second-failure" if second_failure else "manual-removal")
                path = Path(created["path"])
                if second_failure:
                    self.registry.record_run(name=created["name"], expected_sha256=created["sha256"],
                                             run_id=str(uuid.uuid4()), invocation_kind="spawn_agent",
                                             outcome="failure")
                real_delete = agents._windows_delete_file

                def compete_then_delete(handle):
                    self.assert_windows_competitor_blocked(path)
                    return real_delete(handle)

                with mock.patch.object(agents, "_windows_delete_file", side_effect=compete_then_delete) as deletion:
                    if second_failure:
                        result = self.registry.record_run(
                            name=created["name"], expected_sha256=created["sha256"],
                            run_id=str(uuid.uuid4()), invocation_kind="followup_task", outcome="failure")
                    else:
                        result = self.registry.delete(name=created["name"],
                                                      expected_sha256=created["sha256"],
                                                      owner_token=created["owner_token"])
                deletion.assert_called_once()
                self.assertFalse(path.exists())
                self.assertTrue(result["all_persisted_agent_data_removed"])

    @unittest.skipUnless(os.name == "nt", "Windows mandatory sharing semantics")
    def test_windows_create_failure_cleanup_blocks_competing_process(self) -> None:
        path = self.registry.agents_dir / "failed-write.toml"

        def fail_after_competition(_descriptor):
            self.assert_windows_competitor_blocked(path)
            raise OSError("forced write failure")

        with mock.patch.object(agents.os, "fsync", side_effect=fail_after_competition):
            with self.assertRaisesRegex(OSError, "forced write failure"):
                agents.write_new_file(path, b"owned partial creation")
        self.assertFalse(path.exists())

    @unittest.skipUnless(os.name == "nt", "Windows mandatory sharing semantics")
    def test_windows_ensure_failed_insert_cleanup_blocks_competing_process(self) -> None:
        connection = self.registry.connect()
        path = None

        class FailingInsert:
            def execute(inner, sql, parameters=()):
                nonlocal path
                if sql.startswith("INSERT INTO agents("):
                    path = Path(parameters[3])
                    raise sqlite3.OperationalError("forced insert failure")
                return connection.execute(sql, parameters)

            def close(inner):
                connection.close()

        real_delete = agents._windows_delete_file

        def compete_then_delete(handle):
            self.assertIsNotNone(path)
            self.assert_windows_competitor_blocked(path)
            return real_delete(handle)

        with mock.patch.object(self.registry, "connect", return_value=FailingInsert()), \
                mock.patch.object(agents, "_windows_delete_file", side_effect=compete_then_delete):
            with self.assertRaisesRegex(sqlite3.OperationalError, "forced insert failure"):
                self.ensure()
        self.assertFalse(path.exists())

    @unittest.skipUnless(os.name == "nt", "Windows handle rename recovery")
    def test_windows_publication_collision_preserves_both_objects_and_reports_recovery(self) -> None:
        path = self.registry.agents_dir / "owned.toml"
        path.write_bytes(b"original owned data")
        real_rename = agents._windows_rename_file
        calls = 0

        def occupy_publication_name(handle, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                subprocess.run([sys.executable, "-B", "-c",
                                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'external winner')",
                                str(path)], check=True, timeout=15)
            return real_rename(handle, destination)

        with mock.patch.object(agents, "_windows_rename_file", side_effect=occupy_publication_name):
            with self.assertRaisesRegex(agents.SpecialistError, "recovery is incomplete"):
                agents.replace_exact_file(path, expected=b"original owned data", replacement=b"planned")
        self.assertEqual(path.read_bytes(), b"external winner")
        previous = list(path.parent.glob("*.previous"))
        self.assertEqual(len(previous), 1)
        self.assertEqual(previous[0].read_bytes(), b"original owned data")

    @unittest.skipUnless(os.name == "nt", "Windows handle rename recovery")
    def test_windows_old_file_cleanup_failure_restores_original_before_returning_error(self) -> None:
        path = self.registry.agents_dir / "owned.toml"
        path.write_bytes(b"original")
        real_delete = agents._windows_delete_file
        calls = 0

        def fail_old_cleanup(handle):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("forced previous-file cleanup failure")
            return real_delete(handle)

        with mock.patch.object(agents, "_windows_delete_file", side_effect=fail_old_cleanup):
            with self.assertRaisesRegex(OSError, "forced previous-file cleanup failure"):
                agents.replace_exact_file(path, expected=b"original", replacement=b"replacement")
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_ensure_reports_sqlite_rollback_failure_even_when_file_is_restored(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        original = path.read_bytes()
        real_connection = self.registry.connect()

        class FailingCommitAndRollbackConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced ensure commit failure")
                if sql == "ROLLBACK":
                    real_connection.execute(sql)
                    raise sqlite3.OperationalError("forced rollback reporting failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(
            self.registry, "connect", return_value=FailingCommitAndRollbackConnection()
        ):
            with self.assertRaisesRegex(
                agents.SpecialistError,
                "SQLite rollback failed: forced rollback reporting failure",
            ):
                self.ensure(description="回滚报告失败。", expected_sha256=created["sha256"])
        self.assertEqual(path.read_bytes(), original)

    def test_old_lifecycle_database_is_never_opened_migrated_or_deleted(self) -> None:
        old = self.registry.old_db_path
        old.write_bytes(b"opaque-old-lifecycle-data")
        before = old.read_bytes()

        self.ensure()

        self.assertEqual(old.read_bytes(), before)
        self.assertNotEqual(old, self.registry.db_path)

    def test_astra_subagent_effort_is_capped_at_xhigh(self) -> None:
        first = self.ensure(model="gpt-6-astra", effort="xhigh")
        second = self.ensure(model="gpt-6-astra", effort="xhigh")
        path = Path(first["path"])
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["model"], "gpt-6-astra")
        self.assertEqual(payload["model_reasoning_effort"], "xhigh")
        self.assertEqual(second["action"], "reused")
        self.assertEqual(first["sha256"], second["sha256"])
        before = path.read_bytes()

        for effort in ("medium", "high"):
            with self.subTest(effort=effort, route="accepted"):
                accepted = self.ensure(
                    role_key=f"astra-{effort}-accepted",
                    global_domain_key=f"astra-{effort}-accepted",
                    model="gpt-6-astra",
                    effort=effort,
                )
                accepted_payload = tomllib.loads(
                    Path(accepted["path"]).read_text(encoding="utf-8")
                )
                self.assertEqual(accepted_payload["model_reasoning_effort"], effort)

        for effort in ("max", "ultra"):
            with self.subTest(effort=effort, route="create"):
                with self.assertRaisesRegex(
                    agents.SpecialistError,
                    "gpt-6-astra subagents support at most xhigh reasoning effort",
                ):
                    self.ensure(
                        role_key=f"astra-{effort}-rejected",
                        global_domain_key=f"astra-{effort}-rejected",
                        model="gpt-6-astra",
                        effort=effort,
                    )
                self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 3)

            with self.subTest(effort=effort, route="reconfigure"):
                with self.assertRaisesRegex(
                    agents.SpecialistError,
                    "gpt-6-astra subagents support at most xhigh reasoning effort",
                ):
                    self.ensure(
                        model="gpt-6-astra",
                        effort=effort,
                        expected_sha256=first["sha256"],
                    )
                self.assertEqual(path.read_bytes(), before)

    def test_sol_subagents_accept_max_and_ultra_reasoning_effort(self) -> None:
        for model in ("gpt-6-sol", "gpt-5.6-sol"):
            for effort in ("max", "ultra"):
                with self.subTest(model=model, effort=effort):
                    role_key = f"sol-{model.replace('.', '-')}-{effort}-supported"
                    created = self.ensure(
                        role_key=role_key,
                        global_domain_key=role_key,
                        model=model,
                        effort=effort,
                    )
                    payload = tomllib.loads(
                        Path(created["path"]).read_text(encoding="utf-8")
                    )
                    self.assertEqual(payload["model"], model)
                    self.assertEqual(payload["model_reasoning_effort"], effort)

    def test_luna_subagent_accepts_max_and_rejects_ultra_reasoning_effort(self) -> None:
        created = self.ensure(
            role_key="luna-max-supported",
            global_domain_key="luna-max-supported",
            model="gpt-5.6-luna",
            effort="max",
        )
        payload = tomllib.loads(Path(created["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["model_reasoning_effort"], "max")
        with self.assertRaisesRegex(agents.SpecialistError, "at most max"):
            self.ensure(
                role_key="luna-ultra-rejected",
                global_domain_key="luna-ultra-rejected",
                model="gpt-5.6-luna",
                effort="ultra",
            )

    def test_ensure_accepts_only_current_models_with_medium_or_higher_effort(self) -> None:
        current_models = (
            "gpt-5.6-luna",
            "gpt-6-sol",
            "gpt-5.6-sol",
            "gpt-6-astra",
        )
        self.assertEqual(agents.NEW_SUBAGENT_MODELS, current_models)
        for model in current_models:
            with self.subTest(model=model):
                created = self.ensure(
                    role_key=f"current-{model.replace('.', '-')}",
                    global_domain_key=f"current-{model.replace('.', '-')}",
                    model=model,
                    effort="medium",
                )
                self.assertEqual(created["action"], "created")

        for model in ("gpt-6-luna", "gpt-5.6-terra", "gpt-5.5"):
            with self.subTest(model=model, operation="create"):
                with self.assertRaisesRegex(agents.SpecialistError, "require one of") as caught:
                    self.ensure(
                        role_key="rejected-old-model",
                        model=model,
                    )
                positions = [str(caught.exception).index(item) for item in current_models]
                self.assertEqual(positions, sorted(positions))
        for model in current_models:
            with self.subTest(model=model, operation="low"):
                with self.assertRaisesRegex(agents.SpecialistError, "cannot use low"):
                    self.ensure(role_key="rejected-low-effort", model=model, effort="low")
        with self.assertRaisesRegex(agents.SpecialistError, "at most max"):
            self.ensure(
                role_key="rejected-luna-ultra",
                model="gpt-5.6-luna",
                effort="ultra",
            )
        self.assertEqual(len(list(self.registry.agents_dir.glob("*.toml"))), 4)

        existing = self.ensure()
        original = Path(existing["path"]).read_bytes()
        for model, effort, error in (
            ("gpt-6-luna", "high", "require one of"),
            ("gpt-5.6-terra", "high", "require one of"),
            ("gpt-6-sol", "low", "cannot use low"),
        ):
            with self.subTest(model=model, effort=effort, operation="reconfigure"):
                with self.assertRaisesRegex(agents.SpecialistError, error):
                    self.ensure(
                        model=model, effort=effort,
                        expected_sha256=existing["sha256"],
                    )
                self.assertEqual(Path(existing["path"]).read_bytes(), original)

    def test_legacy_owned_role_remains_readable_and_requires_explicit_current_reconfiguration(self) -> None:
        created = self.ensure()
        legacy_sha256 = self.mark_legacy_configuration(created)
        path = Path(created["path"])
        before = path.read_bytes()

        status = self.registry.status()
        self.assertEqual(status["registered_agents"][0]["model"], "gpt-5.6-terra")
        recalled = self.registry.recall(name=created["name"], expected_sha256=legacy_sha256)
        self.assertEqual(recalled["model"], "gpt-5.6-terra")
        self.assertEqual(recalled["reasoning_effort"], "low")

        with self.assertRaisesRegex(agents.SpecialistError, "require one of"):
            self.ensure(model="gpt-5.6-terra", effort="low", expected_sha256=legacy_sha256)
        self.assertEqual(path.read_bytes(), before)
        preview = self.ensure(model="gpt-6-sol", effort="high")
        self.assertEqual(preview["action"], "reconfiguration_required")
        self.assertEqual(path.read_bytes(), before)
        updated = self.ensure(
            model="gpt-6-sol", effort="high", expected_sha256=legacy_sha256
        )
        self.assertEqual(updated["action"], "reconfigured")
        self.assertEqual(updated["agent_id"], created["agent_id"])
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["model"], "gpt-6-sol")
        self.assertEqual(payload["model_reasoning_effort"], "high")

    def test_rejected_current_creation_models_remain_readable_as_historical_roles(self) -> None:
        for index, (model, effort) in enumerate((
            ("gpt-6-luna", "ultra"),
            ("gpt-5.6-terra", "low"),
        )):
            with self.subTest(model=model, effort=effort):
                role_key = f"historical-model-{index}"
                created = self.ensure(
                    role_key=role_key,
                    global_domain_key=role_key,
                )
                legacy_sha256 = self.mark_legacy_configuration(
                    created,
                    model=model,
                    effort=effort,
                )
                status_item = next(
                    item
                    for item in self.registry.status()["registered_agents"]
                    if item["name"] == created["name"]
                )
                recalled = self.registry.recall(
                    name=created["name"],
                    expected_sha256=legacy_sha256,
                )
                self.assertEqual(status_item["model"], model)
                self.assertEqual(status_item["reasoning_effort"], effort)
                self.assertEqual(recalled["model"], model)
                self.assertEqual(recalled["reasoning_effort"], effort)

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
                    self.assertIn("模型：gpt-6-sol", instructions)
                    self.assertIn("思考程度：high", instructions)
                    self.assertIn("任务卡必须提供五行实际值", instructions)
                    self.assertIn("新任务卡缺少任一状态行时，先通过 collaboration.send_message 向父代理", instructions)
                    self.assertNotIn("缺少任一行时父代理不得启动该子任务", instructions)
                    self.assertNotIn("MODEL_ROUTE", instructions)
                    self.assertNotIn("可接受成本带", instructions)
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
        self.assertNotIn("速度：", payload["developer_instructions"])
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
                lesson="启用自动技能目录的窄子代理不能继续写入经验。",
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
        self.mark_legacy_configuration(created)
        rows = self.downgrade_registry(1)
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "explicit migrate-global"):
            self.ensure()
        migrated = self.registry.migrate_global(plan_path=self.write_migration_plan(rows))
        self.assertEqual(migrated["action"], "global_migration_committed")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                agents.SCHEMA_VERSION,
            )
            row = connection.execute(
                "SELECT lesson, retracts_event_id FROM experience_events"
            ).fetchone()
            run_count = connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        self.assertEqual(row["lesson"], lesson)
        self.assertIsNone(row["retracts_event_id"])
        self.assertEqual(run_count, 0)
        retained = self.registry.recall(name=created["name"])
        self.assertEqual(retained["model"], "gpt-5.6-terra")
        self.assertEqual(retained["reasoning_effort"], "low")

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
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                agents.SCHEMA_VERSION,
            )
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
                lesson="新经验只读取一个有限窗口。",
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

    def test_complete_run_atomically_records_result_and_derived_experience(self) -> None:
        created = self.ensure()
        reused = self.ensure()
        self.assertEqual(reused["action"], "reused")
        run_id = str(uuid.uuid4())
        lesson = "适用情境：完成已采用任务；做法：同事务记录结果和经验；证据：原子重放测试。"

        completed = agents.dispatch(
            agents.build_parser().parse_args(
                [
                    "--codex-home", str(self.codex_home), "complete-run",
                    "--name", created["name"],
                    "--expected-sha256", created["sha256"],
                    "--run-id", run_id,
                    "--invocation-kind", "spawn_agent",
                    "--outcome", "success",
                    "--lesson", lesson,
                    "--origin-term", "当前任务来源",
                ]
            )
        )
        replay = self.registry.complete_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=run_id,
            invocation_kind="spawn_agent",
            outcome="success",
            lesson=lesson,
            origin_terms=("当前任务来源",),
        )

        expected_event_id = str(
            uuid.uuid5(
                uuid.UUID(run_id),
                "retained-completion:v2",
            )
        )
        self.assertEqual(completed["action"], "completion_recorded")
        self.assertEqual(completed["run_action"], "survival_round_recorded")
        self.assertEqual(completed["experience_action"], "experience_recorded")
        self.assertEqual(completed["experience_event_id"], expected_event_id)
        self.assertEqual(replay["action"], "completion_already_recorded")
        self.assertEqual(replay["run_action"], "survival_round_already_recorded")
        self.assertEqual(replay["experience_action"], "experience_already_recorded")
        self.assertEqual(replay["sha256"], completed["sha256"])
        self.assertIn(lesson, Path(created["path"]).read_text(encoding="utf-8"))
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 1)
            receipt = connection.execute(
                "SELECT completion_receipt_version,completion_experience_event_id "
                "FROM agent_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            self.assertEqual(
                (receipt["completion_receipt_version"], receipt["completion_experience_event_id"]),
                (agents.COMPLETION_RECEIPT_VERSION, expected_event_id),
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )

    def test_complete_run_prevalidates_identifiers_and_rejects_failure_experience(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        before_rows = self.registry_rows()

        with self.assertRaisesRegex(agents.SpecialistError, "run_id must be a UUID"):
            self.registry.complete_run(
                name=created["name"], expected_sha256=created["sha256"],
                run_id="not-a-uuid", invocation_kind="spawn_agent", outcome="success",
                lesson="有效经验正文。", origin_terms=("当前任务来源",),
            )
        with self.assertRaisesRegex(agents.SpecialistError, "retracts_event_id must be a UUID"):
            self.registry.complete_run(
                name=created["name"], expected_sha256=created["sha256"],
                run_id=str(uuid.uuid4()), invocation_kind="spawn_agent", outcome="success",
                lesson="有效经验正文。", retracts_event_id="not-a-uuid",
                origin_terms=("当前任务来源",),
            )
        with self.assertRaisesRegex(agents.SpecialistError, "adopted successful result"):
            self.registry.complete_run(
                name=created["name"], expected_sha256=created["sha256"],
                run_id=str(uuid.uuid4()), invocation_kind="spawn_agent", outcome="failure",
                lesson="失败结果不能直接写入经验。", origin_terms=("当前任务来源",),
            )

        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.registry_rows(), before_rows)

    def test_complete_run_accepts_unused_origin_terms_without_experience(self) -> None:
        created = self.ensure()
        completed = self.registry.complete_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=str(uuid.uuid4()),
            invocation_kind="spawn_agent",
            outcome="success",
            origin_terms=("当前任务来源",),
        )

        self.assertEqual(completed["action"], "completion_recorded")
        self.assertEqual(completed["experience_action"], "not_requested")
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 1)
            receipt = connection.execute(
                "SELECT completion_receipt_version,completion_experience_event_id "
                "FROM agent_runs"
            ).fetchone()
            self.assertEqual(
                (receipt["completion_receipt_version"], receipt["completion_experience_event_id"]),
                (agents.COMPLETION_RECEIPT_VERSION, None),
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                0,
            )

    def test_complete_run_event_and_commit_failures_restore_exact_state(self) -> None:
        created = self.ensure()
        path = Path(created["path"])
        before = path.read_bytes()
        before_rows = self.registry_rows()
        arguments = {
            "name": created["name"],
            "expected_sha256": created["sha256"],
            "run_id": str(uuid.uuid4()),
            "invocation_kind": "spawn_agent",
            "outcome": "success",
            "lesson": "适用情境：故障恢复；做法：整体回滚；证据：注入失败。",
            "origin_terms": ("当前任务来源",),
        }

        with mock.patch.object(
            self.registry,
            "_append_experience_event",
            side_effect=agents.SpecialistError("forced experience failure"),
        ):
            with self.assertRaisesRegex(agents.SpecialistError, "forced experience failure"):
                self.registry.complete_run(**arguments)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.registry_rows(), before_rows)

        real_connection = self.registry.connect()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced completion commit failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(
            self.registry,
            "connect",
            return_value=FailingCommitConnection(),
        ):
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "forced completion commit failure"
            ):
                self.registry.complete_run(**arguments)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.registry_rows(), before_rows)

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
            self.assertEqual(
                {
                    row[0]
                    for row in connection.execute(
                        "SELECT completion_receipt_version FROM agent_runs"
                    )
                },
                {agents.ORDINARY_RUN_RECEIPT_VERSION},
            )

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
        with self.assertRaisesRegex(agents.SpecialistError, "recorded attempts"):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )
        self.assertEqual(recorded["survival_rounds"], 1)
        self.assertTrue(Path(created["path"]).exists())
        self.assertFalse(self.registry.pending_deletion_dir.exists())

    def test_record_run_links_only_the_verified_loaded_experience_version(self) -> None:
        created = self.ensure()
        improved = self.improve_with_lesson(
            name=created["name"], expected_sha256=created["sha256"],
            event_id=str(uuid.uuid4()),
            lesson="适用情境：已有定位；做法：复用证据包；证据：一次采用结果；例外：来源变化。",
        )
        success_id = str(uuid.uuid4())
        recalled = self.registry.recall(
            name=created["name"], expected_sha256=improved["sha256"],
            run_id=success_id,
        )
        digest = recalled["retention_state"]["experience_digest"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertIn("当前配置 1 条", recalled["opening_status"])
        self.assertIn("尚无关联的后续结果记录", recalled["opening_status"])

        with self.assertRaisesRegex(agents.SpecialistError, "database-issued"):
            self.registry.record_run(
                name=created["name"], expected_sha256=improved["sha256"],
                run_id=str(uuid.uuid4()), invocation_kind="spawn_agent",
                loaded_experience_digest=digest,
            )
        recorded = self.registry.record_run(
            name=created["name"], expected_sha256=improved["sha256"],
            run_id=success_id, invocation_kind="spawn_agent",
            loaded_experience_digest=digest,
            experience_receipt=recalled["experience_receipt"],
        )
        replay = self.registry.record_run(
            name=created["name"], expected_sha256=improved["sha256"],
            run_id=success_id, invocation_kind="spawn_agent",
            loaded_experience_digest=digest,
            experience_receipt=recalled["experience_receipt"],
        )
        self.assertTrue(recorded["experience_outcome_association_persisted"])
        self.assertEqual(replay["action"], "survival_round_already_recorded")
        self.assertEqual(recorded["experience_successful_attempt_count"], 1)

        with self.assertRaisesRegex(agents.SpecialistError, "database-issued"):
            self.registry.record_run(
                name=created["name"], expected_sha256=improved["sha256"],
                run_id=str(uuid.uuid4()), invocation_kind="spawn_agent",
                loaded_experience_digest="0" * 64,
            )

        unlinked = self.registry.record_run(
            name=created["name"], expected_sha256=improved["sha256"],
            run_id=str(uuid.uuid4()), invocation_kind="followup_task",
        )
        self.assertFalse(unlinked["experience_outcome_association_persisted"])
        recalled = self.registry.recall(
            name=created["name"], expected_sha256=improved["sha256"],
        )
        state = recalled["retention_state"]
        self.assertEqual(state["survival_rounds"], 2)
        self.assertEqual(state["experience_successful_attempt_count"], 1)
        self.assertEqual(state["experience_failed_attempt_count"], 0)
        self.assertIn("此版本关联的后续结果 1 成功、0 失败", recalled["opening_status"])

    def test_stale_experience_digest_requires_run_bound_recall_receipt(self) -> None:
        created = self.ensure()
        first = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            event_id=str(uuid.uuid4()),
            lesson="适用情境：并发调用；做法：保留调用时摘要；证据：首次召回。",
        )
        first_run_id = str(uuid.uuid4())
        old_thread_run_id = str(uuid.uuid4())
        first_recall = self.registry.recall(
            name=created["name"], expected_sha256=first["sha256"],
            run_id=first_run_id,
        )
        old_thread_recall = self.registry.recall(
            name=created["name"], expected_sha256=first["sha256"],
            run_id=old_thread_run_id,
        )
        repeated_old_thread_recall = self.registry.recall(
            name=created["name"], expected_sha256=first["sha256"],
            run_id=old_thread_run_id,
        )
        old_digest = first_recall["retention_state"]["experience_digest"]
        self.assertEqual(
            old_thread_recall["retention_state"]["experience_digest"], old_digest
        )
        self.assertRegex(first_recall["experience_receipt"], r"^[0-9a-f]{64}$")
        self.assertRegex(old_thread_recall["experience_receipt"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            repeated_old_thread_recall["experience_receipt"],
            old_thread_recall["experience_receipt"],
        )
        self.assertNotEqual(
            first_recall["experience_receipt"], old_thread_recall["experience_receipt"]
        )

        first_completion = self.registry.complete_run(
            name=created["name"],
            expected_sha256=first["sha256"],
            run_id=first_run_id,
            invocation_kind="spawn_agent",
            outcome="success",
            loaded_experience_digest=old_digest,
            experience_receipt=first_recall["experience_receipt"],
            lesson="适用情境：先完成的并发调用；做法：追加已采用经验；证据：完成收据。",
            origin_terms=("当前任务来源",),
        )
        current_recall = self.registry.recall(
            name=created["name"], expected_sha256=first_completion["sha256"]
        )
        current_digest = current_recall["retention_state"]["experience_digest"]
        self.assertNotEqual(current_digest, old_digest)

        before_stale_cas = self.registry.db_path.read_bytes()
        with self.assertRaisesRegex(agents.SpecialistError, "expected SHA-256"):
            self.registry.complete_run(
                name=created["name"],
                expected_sha256=first["sha256"],
                run_id=old_thread_run_id,
                invocation_kind="followup_task",
                outcome="success",
                loaded_experience_digest=old_digest,
                experience_receipt=old_thread_recall["experience_receipt"],
            )
        self.assertEqual(self.registry.db_path.read_bytes(), before_stale_cas)

        old_thread = self.registry.complete_run(
            name=created["name"],
            expected_sha256=first_completion["sha256"],
            run_id=old_thread_run_id,
            invocation_kind="followup_task",
            outcome="success",
            loaded_experience_digest=old_digest,
            experience_receipt=old_thread_recall["experience_receipt"],
        )
        replay = self.registry.complete_run(
            name=created["name"],
            expected_sha256=first_completion["sha256"],
            run_id=old_thread_run_id,
            invocation_kind="followup_task",
            outcome="success",
            loaded_experience_digest=old_digest,
            experience_receipt=old_thread_recall["experience_receipt"],
        )
        self.assertEqual(old_thread["action"], "completion_recorded")
        self.assertEqual(replay["action"], "completion_already_recorded")
        self.assertEqual(old_thread["loaded_experience_digest"], old_digest)
        self.assertEqual(old_thread["experience_successful_attempt_count"], 2)

        before = self.registry.db_path.read_bytes()
        with self.assertRaisesRegex(
            agents.SpecialistError, "database-issued"
        ):
            self.registry.complete_run(
                name=created["name"],
                expected_sha256=first_completion["sha256"],
                run_id=str(uuid.uuid4()),
                invocation_kind="spawn_agent",
                outcome="success",
                loaded_experience_digest="0" * 64,
            )
        self.assertEqual(self.registry.db_path.read_bytes(), before)

        later_run_id = str(uuid.uuid4())
        later_recall = self.registry.recall(
            name=created["name"], expected_sha256=first_completion["sha256"],
            run_id=later_run_id,
        )
        with self.assertRaisesRegex(
            agents.SpecialistError, "database-issued"
        ):
            self.registry.complete_run(
                name=created["name"],
                expected_sha256=first_completion["sha256"],
                run_id=later_run_id,
                invocation_kind="spawn_agent",
                outcome="success",
                loaded_experience_digest=old_digest,
                experience_receipt=later_recall["experience_receipt"],
            )

        other = self.ensure(
            role_key="other-digest-identity",
            global_domain_key="other-digest-identity",
        )
        with self.assertRaisesRegex(
            agents.SpecialistError, "database-issued"
        ):
            self.registry.record_run(
                name=other["name"],
                expected_sha256=other["sha256"],
                run_id=str(uuid.uuid4()),
                invocation_kind="spawn_agent",
                loaded_experience_digest=old_digest,
                experience_receipt=old_thread_recall["experience_receipt"],
            )

    def test_record_run_rejects_experience_digest_when_no_experience_is_loaded(self) -> None:
        created = self.ensure()
        run_id = str(uuid.uuid4())
        fabricated_digest = "0" * 64
        old_hmac_payload = (
            "codex-lean-stack:experience-recall:v1\0"
            f"{created['agent_id']}\0{run_id}\0{fabricated_digest}"
        ).encode("utf-8")
        forged_with_real_owner_token = hmac.new(
            created["owner_token"].encode("ascii"),
            old_hmac_payload,
            hashlib.sha256,
        ).hexdigest()
        with self.assertRaisesRegex(agents.SpecialistError, "database-issued"):
            self.registry.record_run(
                name=created["name"], expected_sha256=created["sha256"],
                run_id=run_id, invocation_kind="spawn_agent",
                loaded_experience_digest=fabricated_digest,
                experience_receipt=forged_with_real_owner_token,
            )
        self.assertEqual(self.registry.status()["recorded_attempt_count"], 0)
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM experience_recall_receipts"
                ).fetchone()[0],
                0,
            )

    def test_attempts_distinguish_never_invoked_from_success_and_failure(self) -> None:
        created = self.ensure()
        item = self.registry.status()["registered_agents"][0]
        self.assertEqual(item["attempt_count"], 0)
        self.assertEqual(item["successful_attempt_count"], 0)
        self.assertEqual(item["failed_attempt_count"], 0)

        successful = self.registry.record_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=str(uuid.uuid4()),
            invocation_kind="spawn_agent",
        )
        failed = self.registry.record_run(
            name=created["name"],
            expected_sha256=created["sha256"],
            run_id=str(uuid.uuid4()),
            invocation_kind="followup_task",
            outcome="failure",
        )

        self.assertEqual(successful["outcome"], "success")
        self.assertEqual(failed["attempt_count"], 2)
        self.assertEqual(failed["successful_attempt_count"], 1)
        self.assertEqual(failed["failed_attempt_count"], 1)
        self.assertTrue(failed["active"])
        self.assertFalse(failed["permanent_removal_triggered"])

    def test_second_task_failure_permanently_removes_all_agent_data(self) -> None:
        created = self.ensure()
        success_id = str(uuid.uuid4())
        first_failure_id = str(uuid.uuid4())
        second_failure_id = str(uuid.uuid4())
        success = self.registry.record_run(
            name=created["name"], expected_sha256=created["sha256"],
            run_id=success_id, invocation_kind="spawn_agent",
        )
        first_event_id = str(uuid.uuid4())
        first_event = self.improve_with_lesson(
            name=created["name"], expected_sha256=created["sha256"],
            event_id=first_event_id,
            lesson="适用情境：初始结论；做法：保留证据；证据：已验证；例外：待纠正。",
        )
        correction = self.improve_with_lesson(
            name=created["name"], expected_sha256=first_event["sha256"],
            event_id=str(uuid.uuid4()), retracts_event_id=first_event_id,
            lesson="适用情境：初始结论；做法：采用纠正；证据：已验证；例外：无。",
        )
        self.registry.recall(
            name=created["name"], expected_sha256=correction["sha256"],
            run_id=str(uuid.uuid4()),
        )
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "INSERT INTO experience_summaries"
                "(agent_id,summary,covered_through_sequence,source_digest,updated_at) "
                "VALUES(?,?,?,?,?)",
                (created["agent_id"], "旧摘要", 1, "a" * 64, agents.utc_now()),
            )
            connection.commit()
        first_failure = self.registry.record_run(
            name=created["name"], expected_sha256=correction["sha256"],
            run_id=first_failure_id, invocation_kind="followup_task", outcome="failure",
        )
        replay = self.registry.record_run(
            name=created["name"], expected_sha256=correction["sha256"],
            run_id=first_failure_id, invocation_kind="followup_task", outcome="failure",
        )
        self.assertEqual(replay["action"], "task_failure_already_recorded")
        self.assertEqual(replay["attempt_count"], 2)
        with self.assertRaisesRegex(agents.SpecialistError, "outcome"):
            self.registry.record_run(
                name=created["name"], expected_sha256=correction["sha256"],
                run_id=first_failure_id, invocation_kind="followup_task", outcome="success",
            )

        removed = self.registry.record_run(
            name=created["name"], expected_sha256=correction["sha256"],
            run_id=second_failure_id, invocation_kind="spawn_agent", outcome="failure",
        )
        self.assertEqual(
            removed["action"], "task_failure_recorded_and_permanently_removed"
        )
        self.assertFalse(removed["active"])
        self.assertTrue(removed["permanent_removal_triggered"])
        self.assertFalse(removed["recoverable"])
        self.assertEqual(removed["disposition"], "permanently_removed")
        self.assertFalse(removed["retired_identity_recorded"])
        self.assertTrue(removed["all_persisted_agent_data_removed"])
        self.assertFalse(Path(created["path"]).exists())
        self.assertFalse(self.registry.pending_deletion_dir.exists())
        self.assertEqual(self.registry.status()["registered_count"], 0)
        self.assertEqual(self.registry.status(for_routing=True)["registered_count"], 0)
        dashboard = self.registry.status(for_dashboard=True)
        self.assertEqual(dashboard["recorded_attempt_count"], 0)
        self.assertEqual(dashboard["successful_attempt_count"], 0)
        self.assertEqual(dashboard["failed_attempt_count"], 0)
        self.assertEqual(dashboard["active_retained_agent_count"], 0)
        self.assertEqual(dashboard["retired_retained_agent_count"], 0)
        with contextlib.closing(self.db()) as connection:
            for table in (
                "agents", "agent_runs", "experience_events", "experience_summaries",
                "experience_recall_receipts",
            ):
                self.assertEqual(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                    0,
                )
        with self.assertRaisesRegex(agents.SpecialistError, "unknown owned specialist"):
            self.registry.record_run(
                name=created["name"], expected_sha256=correction["sha256"],
                run_id=second_failure_id, invocation_kind="spawn_agent", outcome="failure",
            )
        replacement = self.ensure(role_key="qml-binding-diagnostics")
        self.assertEqual(replacement["action"], "created")
        self.assertNotEqual(replacement["agent_id"], created["agent_id"])

    def test_second_failure_busy_or_cas_failure_is_zero_mutation(self) -> None:
        created = self.ensure()
        first = self.registry.record_run(
            name=created["name"], expected_sha256=created["sha256"],
            run_id=str(uuid.uuid4()), invocation_kind="spawn_agent", outcome="failure",
        )
        path = Path(created["path"])
        original = path.read_bytes()
        second_id = str(uuid.uuid4())
        with self.assertRaises(agents.SpecialistError):
            self.registry.record_run(
                name=created["name"], expected_sha256="0" * 64,
                run_id=second_id, invocation_kind="followup_task", outcome="failure",
            )
        blocker = sqlite3.connect(self.registry.db_path, isolation_level=None)
        try:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.registry.record_run(
                    name=created["name"], expected_sha256=created["sha256"],
                    run_id=second_id, invocation_kind="followup_task", outcome="failure",
                )
        finally:
            blocker.close()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(first["failed_attempt_count"], 1)

    def test_second_failure_commit_failure_restores_all_data_and_exact_file(self) -> None:
        created = self.ensure()
        event = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            event_id=str(uuid.uuid4()),
            lesson="适用情境：事务回滚；做法：保留精确数据；证据：测试；例外：无。",
        )
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "INSERT INTO experience_summaries"
                "(agent_id,summary,covered_through_sequence,source_digest,updated_at) "
                "VALUES(?,?,?,?,?)",
                (created["agent_id"], "回滚摘要", 1, "b" * 64, agents.utc_now()),
            )
            connection.commit()
        self.registry.record_run(
            name=created["name"],
            expected_sha256=event["sha256"],
            run_id=str(uuid.uuid4()),
            invocation_kind="spawn_agent",
            outcome="success",
        )
        self.registry.record_run(
            name=created["name"],
            expected_sha256=event["sha256"],
            run_id=str(uuid.uuid4()),
            invocation_kind="followup_task",
            outcome="failure",
        )
        path = Path(created["path"])
        before = path.read_bytes()
        real_connection = self.registry.connect()

        class FailingCommitConnection:
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("forced removal commit failure")
                return real_connection.execute(sql, parameters)

            def close(self):
                real_connection.close()

        with mock.patch.object(
            self.registry,
            "connect",
            return_value=FailingCommitConnection(),
        ):
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "forced removal commit failure"
            ):
                self.registry.record_run(
                    name=created["name"],
                    expected_sha256=event["sha256"],
                    run_id=str(uuid.uuid4()),
                    invocation_kind="spawn_agent",
                    outcome="failure",
                )

        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.registry.pending_deletion_dir.exists())
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 2)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_summaries").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE outcome='failure'"
                ).fetchone()[0],
                1,
            )

    def test_explicit_v4_attempt_migration_preserves_successes_and_infers_no_failures(self) -> None:
        never_invoked = self.ensure()
        successful = self.ensure(role_key="successful-migration-review")
        run_id = str(uuid.uuid4())
        self.registry.record_run(
            name=successful["name"], expected_sha256=successful["sha256"],
            run_id=run_id, invocation_kind="spawn_agent",
        )
        self.downgrade_attempt_schema()
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "migrate-attempts"):
            self.registry.status()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main(
                ["--codex-home", str(self.codex_home), "migrate-attempts"]
            )
        migrated = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(migrated["action"], "attempt_schema_migrated")
        self.assertEqual(migrated["source_schema_version"], 4)
        self.assertEqual(migrated["migrated_successful_attempt_count"], 1)
        self.assertEqual(migrated["migrated_failure_attempt_count"], 0)
        self.assertFalse(migrated["historical_failure_backfill"])
        self.assertFalse(migrated["historical_experience_reuse_backfill"])
        self.assertTrue(migrated["existing_outcome_semantics_preserved"])
        status = {item["name"]: item for item in self.registry.status()["registered_agents"]}
        self.assertEqual(status[never_invoked["name"]]["attempt_count"], 0)
        self.assertEqual(status[successful["name"]]["successful_attempt_count"], 1)
        with contextlib.closing(self.db()) as connection:
            row = connection.execute(
                "SELECT run_id,outcome,loaded_experience_digest,"
                "completion_receipt_version,completion_experience_event_id "
                "FROM agent_runs"
            ).fetchone()
            self.assertEqual(
                (
                    row["run_id"],
                    row["outcome"],
                    row["loaded_experience_digest"],
                    row["completion_receipt_version"],
                    row["completion_experience_event_id"],
                ),
                (run_id, "success", None, None, None),
            )

    def test_explicit_v5_attempt_migration_preserves_outcomes_without_reuse_backfill(self) -> None:
        created = self.ensure()
        self.registry.record_run(
            name=created["name"], expected_sha256=created["sha256"],
            run_id=str(uuid.uuid4()), invocation_kind="spawn_agent",
        )
        self.registry.record_run(
            name=created["name"], expected_sha256=created["sha256"],
            run_id=str(uuid.uuid4()), invocation_kind="followup_task", outcome="failure",
        )
        self.downgrade_experience_schema()
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "migrate-attempts"):
            self.registry.status()

        migrated = self.registry.migrate_attempts()
        self.assertEqual(migrated["source_schema_version"], 5)
        self.assertEqual(migrated["migrated_successful_attempt_count"], 1)
        self.assertEqual(migrated["migrated_failure_attempt_count"], 1)
        self.assertFalse(migrated["historical_experience_reuse_backfill"])
        self.assertFalse(migrated["historical_completion_receipt_backfill"])
        self.assertTrue(migrated["existing_outcome_semantics_preserved"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE loaded_experience_digest IS NOT NULL"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE "
                    "completion_receipt_version IS NOT NULL OR "
                    "completion_experience_event_id IS NOT NULL"
                ).fetchone()[0],
                0,
            )

    def test_explicit_v6_receipt_migration_keeps_old_runs_unknown_and_fail_closed(self) -> None:
        created = self.ensure()
        ordinary_run_id = str(uuid.uuid4())
        no_experience_run_id = str(uuid.uuid4())
        experience_run_id = str(uuid.uuid4())
        self.registry.record_run(
            name=created["name"], expected_sha256=created["sha256"],
            run_id=ordinary_run_id, invocation_kind="spawn_agent",
        )
        self.registry.complete_run(
            name=created["name"], expected_sha256=created["sha256"],
            run_id=no_experience_run_id, invocation_kind="spawn_agent", outcome="success",
        )
        experience_request = {
            "name": created["name"],
            "expected_sha256": created["sha256"],
            "run_id": experience_run_id,
            "invocation_kind": "followup_task",
            "outcome": "success",
            "lesson": "Preserve a migrated completion experience.",
            "origin_terms": ("fixture-project",),
        }
        completed = self.registry.complete_run(**experience_request)
        self.downgrade_completion_receipt_schema()
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "migrate-attempts"):
            self.registry.status()

        migrated = self.registry.migrate_attempts()
        self.assertEqual(migrated["source_schema_version"], 6)
        self.assertFalse(migrated["historical_completion_receipt_backfill"])
        with contextlib.closing(self.db()) as connection:
            rows = list(connection.execute(
                "SELECT completion_receipt_version,completion_experience_event_id "
                "FROM agent_runs"
            ))
            self.assertEqual([(row[0], row[1]) for row in rows], [(None, None)] * 3)

        for migrated_run_id, invocation_kind in (
            (ordinary_run_id, "spawn_agent"),
            (no_experience_run_id, "spawn_agent"),
            (experience_run_id, "followup_task"),
        ):
            with self.subTest(run_id=migrated_run_id), self.assertRaisesRegex(
                agents.SpecialistError,
                "cannot prove.*ordinary record-run",
            ):
                self.registry.record_run(
                    name=created["name"], expected_sha256=completed["sha256"],
                    run_id=migrated_run_id, invocation_kind=invocation_kind,
                )
        with self.assertRaisesRegex(
            agents.SpecialistError,
            "cannot prove.*recorded by complete-run",
        ):
            self.registry.complete_run(
                **dict(experience_request, expected_sha256=completed["sha256"])
            )
        with self.assertRaisesRegex(
            agents.SpecialistError,
            "cannot prove.*recorded by complete-run",
        ):
            self.registry.complete_run(
                name=created["name"], expected_sha256=completed["sha256"],
                run_id=no_experience_run_id, invocation_kind="spawn_agent", outcome="success",
            )

    def test_explicit_v7_migration_never_backfills_recall_issuance(self) -> None:
        created = self.ensure()
        improved = self.improve_with_lesson(
            name=created["name"], expected_sha256=created["sha256"],
            event_id=str(uuid.uuid4()),
            lesson="适用情境：迁移；做法：保留真实签发边界；证据：v7 行。",
        )
        run_id = str(uuid.uuid4())
        recalled = self.registry.recall(
            name=created["name"], expected_sha256=improved["sha256"], run_id=run_id,
        )
        digest = recalled["retention_state"]["experience_digest"]
        recorded = self.registry.record_run(
            name=created["name"], expected_sha256=improved["sha256"],
            run_id=run_id, invocation_kind="spawn_agent",
            loaded_experience_digest=digest,
            experience_receipt=recalled["experience_receipt"],
        )
        self.downgrade_recall_receipt_schema()
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "migrate-attempts"):
            self.registry.status()

        migrated = self.registry.migrate_attempts()
        self.assertEqual(migrated["source_schema_version"], 7)
        self.assertFalse(migrated["historical_recall_receipt_backfill"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM experience_recall_receipts"
                ).fetchone()[0],
                0,
            )
        with self.assertRaisesRegex(agents.SpecialistError, "database-issued"):
            self.registry.record_run(
                name=created["name"], expected_sha256=improved["sha256"],
                run_id=run_id, invocation_kind="spawn_agent",
                loaded_experience_digest=digest,
                experience_receipt=recalled["experience_receipt"],
            )

    def test_delete_rejects_recorded_experience_without_pending_artifacts(self) -> None:
        created = self.ensure()
        improved = self.improve_with_lesson(
            name=created["name"],
            expected_sha256=created["sha256"],
            lesson="已记录经验的子代理不能进入待删目录。",
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

    def test_delete_rejects_recorded_summary_without_events(self) -> None:
        created = self.ensure()
        with contextlib.closing(self.db()) as connection:
            connection.execute(
                "INSERT INTO experience_summaries"
                "(agent_id,summary,covered_through_sequence,source_digest,updated_at) "
                "VALUES(?,?,?,?,?)",
                (created["agent_id"], "现有摘要", 0, "a" * 64, agents.utc_now()),
            )
            connection.commit()

        with self.assertRaisesRegex(agents.SpecialistError, "recorded summary"):
            self.registry.delete(
                name=created["name"],
                expected_sha256=created["sha256"],
                owner_token=created["owner_token"],
            )

        self.assertTrue(Path(created["path"]).exists())
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM experience_summaries").fetchone()[0],
                1,
            )

    def test_delete_permanently_removes_exact_owned_unused_agent(self) -> None:
        created = self.ensure()
        original_path = Path(created["path"])
        result = self.registry.delete(
            name=created["name"],
            expected_sha256=created["sha256"],
            owner_token=created["owner_token"],
        )
        self.assertTrue(result["deleted"])
        self.assertFalse(result["recoverable"])
        self.assertEqual(result["action"], "permanently_removed")
        self.assertEqual(result["disposition"], "permanently_removed")
        self.assertEqual(result["deleted_from"], "specialist_registry_and_filesystem")
        self.assertEqual(result["agent_id"], created["agent_id"])
        self.assertEqual(result["sha256"], created["sha256"])
        self.assertEqual(result["path"], str(original_path))
        self.assertFalse(result["retired_identity_recorded"])
        self.assertTrue(result["all_persisted_agent_data_removed"])
        self.assertFalse(original_path.exists())
        self.assertFalse(self.registry.pending_deletion_dir.exists())
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
        self.assertFalse(self.registry.pending_deletion_dir.exists())
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 1)

    def test_restore_is_not_a_supported_command(self) -> None:
        parser = agents.build_parser()
        action = next(
            item for item in parser._actions
            if getattr(item, "dest", None) == "command"
        )
        self.assertNotIn("restore", action.choices)

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
            description="复核生命周期身份、事务和恢复范围。",
            authority="write",
        )
        self.ensure(
            role_key="alpha-source-review",
            global_domain_key="alpha-source-review",
            display_name="来源复核员",
            description="复核来源覆盖和证据范围。",
            model="gpt-5.6-luna",
            effort="medium",
        )

        with mock.patch.object(
            self.registry, "connect", wraps=self.registry.connect
        ) as connect:
            catalog = self.registry.status(for_routing=True)

        connect.assert_called_once_with(read_only=True)

        self.assertEqual(
            set(catalog),
            {"ok", "action", "for_routing", "registered_agents", "registered_count"},
        )
        self.assertTrue(catalog["for_routing"])
        self.assertEqual(catalog["registered_count"], 2)
        items = catalog["registered_agents"]
        self.assertEqual(
            [item["name"] for item in items],
            sorted(item["name"] for item in items),
        )
        self.assertEqual(
            set(items[0]),
            {
                "name", "agent_ref", "display_name", "description",
                "model", "reasoning_effort", "authority",
            },
        )
        self.assertEqual(items[0]["agent_ref"], items[0]["name"])
        self.assertEqual(items[0]["display_name"], "来源复核员")
        self.assertEqual(items[0]["description"], "来源复核员：复核来源覆盖和证据范围。")
        self.assertNotIn("global_domain_key", items[0])
        self.assertNotIn("global_contract", items[0])
        self.assertNotIn("speed", items[0])
        self.assertLess(len(json.dumps(catalog, ensure_ascii=False)), 4096)
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
                "name", "agent_ref", "display_name", "description",
                "model", "reasoning_effort", "authority",
            },
        )

    def test_status_for_dashboard_reports_corrected_aggregates_without_writing(self) -> None:
        retained = self.ensure()
        first_event_id = str(uuid.uuid4())
        first = self.improve_with_lesson(
            name=retained["name"],
            expected_sha256=retained["sha256"],
            event_id=first_event_id,
            lesson="适用情境：首个输入；做法：保留原始证据；证据：已复核；例外：无。",
        )
        retracted_event_id = str(uuid.uuid4())
        second = self.improve_with_lesson(
            name=retained["name"],
            expected_sha256=first["sha256"],
            event_id=retracted_event_id,
            lesson="适用情境：旧输入；做法：采用旧结论；证据：待纠正；例外：无。",
        )
        corrected = self.improve_with_lesson(
            name=retained["name"],
            expected_sha256=second["sha256"],
            event_id=str(uuid.uuid4()),
            retracts_event_id=retracted_event_id,
            lesson="适用情境：旧输入；做法：改用纠正结论；证据：已复核；例外：无。",
        )
        other = self.ensure(
            role_key="dashboard-aggregate-review",
            global_domain_key="dashboard-aggregate-review",
        )
        for invocation_kind in ("spawn_agent", "followup_task"):
            self.registry.record_run(
                name=retained["name"],
                expected_sha256=corrected["sha256"],
                run_id=str(uuid.uuid4()),
                invocation_kind=invocation_kind,
            )
        self.registry.record_run(
            name=other["name"],
            expected_sha256=other["sha256"],
            run_id=str(uuid.uuid4()),
            invocation_kind="spawn_agent",
        )

        database_before = self.registry.db_path.read_bytes()
        modified_before = self.registry.db_path.stat().st_mtime_ns
        state_files_before = sorted(path.name for path in self.registry.state_dir.iterdir())
        with mock.patch.object(
            self.registry, "connect", wraps=self.registry.connect
        ) as connect:
            dashboard = self.registry.status(for_dashboard=True)

        connect.assert_called_once_with(read_only=True)
        self.assertEqual(
            set(dashboard),
            {
                "ok", "action", "for_dashboard", "schema_version",
                "retained_agent_count", "active_retained_agent_count",
                "retired_retained_agent_count", "recorded_attempt_count",
                "successful_attempt_count", "failed_attempt_count",
                "verified_survival_round_count",
                "experience_event_count", "raw_experience_count",
                "correction_event_count", "active_experience_count",
                "refreshed_at",
            },
        )
        self.assertTrue(dashboard["for_dashboard"])
        self.assertEqual(dashboard["retained_agent_count"], 2)
        self.assertEqual(dashboard["active_retained_agent_count"], 2)
        self.assertEqual(dashboard["retired_retained_agent_count"], 0)
        self.assertEqual(dashboard["recorded_attempt_count"], 3)
        self.assertEqual(dashboard["successful_attempt_count"], 3)
        self.assertEqual(dashboard["failed_attempt_count"], 0)
        self.assertEqual(dashboard["verified_survival_round_count"], 3)
        self.assertEqual(dashboard["experience_event_count"], 3)
        self.assertEqual(dashboard["raw_experience_count"], 2)
        self.assertEqual(dashboard["correction_event_count"], 1)
        self.assertEqual(dashboard["active_experience_count"], 2)
        refreshed_at = dt.datetime.fromisoformat(dashboard["refreshed_at"])
        self.assertIsNotNone(refreshed_at.tzinfo)
        serialized = json.dumps(dashboard, ensure_ascii=False)
        self.assertNotIn(retained["path"], serialized)
        self.assertNotIn(retained["owner_token"], serialized)
        self.assertNotIn("保留原始证据", serialized)
        self.assertEqual(self.registry.db_path.read_bytes(), database_before)
        self.assertEqual(self.registry.db_path.stat().st_mtime_ns, modified_before)
        self.assertEqual(
            sorted(path.name for path in self.registry.state_dir.iterdir()),
            state_files_before,
        )

    def test_status_for_dashboard_cli_is_bounded_and_preserves_owned_validation(self) -> None:
        created = self.ensure()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main(
                ["--codex-home", str(self.codex_home), "status", "--for-dashboard"]
            )
        dashboard = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(dashboard["retained_agent_count"], 1)
        self.assertNotIn("registered_agents", dashboard)
        self.assertNotIn("path", dashboard)
        self.assertNotIn("owner_token", dashboard)
        self.assertNotIn("experience", dashboard)

        path = Path(created["path"])
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(agents.SpecialistError, "content drifted"):
            self.registry.status(for_dashboard=True)

    def test_status_for_dashboard_does_not_initialize_missing_state(self) -> None:
        missing_home = Path(self.temporary.name) / "missing-dashboard-home"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main(
                ["--codex-home", str(missing_home), "status", "--for-dashboard"]
            )

        self.assertEqual(exit_code, 2)
        self.assertFalse(missing_home.exists())
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_status_for_routing_does_not_initialize_missing_state(self) -> None:
        missing_home = Path(self.temporary.name) / "missing-routing-home"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = agents.main(
                ["--codex-home", str(missing_home), "status", "--for-routing"]
            )

        self.assertEqual(exit_code, 2)
        self.assertFalse(missing_home.exists())
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_status_for_dashboard_watch_repeats_read_only_ndjson_until_interrupt(self) -> None:
        self.ensure()
        database_before = self.registry.db_path.read_bytes()
        modified_before = self.registry.db_path.stat().st_mtime_ns
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            mock.patch.object(
                agents.time,
                "sleep",
                side_effect=[None, KeyboardInterrupt()],
            ) as sleep,
        ):
            exit_code = agents.main([
                "--codex-home", str(self.codex_home),
                "status", "--for-dashboard", "--watch-seconds", "2",
            ])

        self.assertEqual(exit_code, 130)
        sleep.assert_has_calls([mock.call(2), mock.call(2)])
        snapshots = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(snapshots), 2)
        self.assertTrue(all(item["for_dashboard"] for item in snapshots))
        self.assertTrue(all(item["retained_agent_count"] == 1 for item in snapshots))
        self.assertTrue(all("registered_agents" not in item for item in snapshots))
        self.assertEqual(self.registry.db_path.read_bytes(), database_before)
        self.assertEqual(self.registry.db_path.stat().st_mtime_ns, modified_before)

    def test_status_watch_rejects_non_dashboard_and_out_of_range_intervals(self) -> None:
        for arguments, expected_error in (
            (["status", "--watch-seconds", "2"], "requires --for-dashboard"),
            (
                ["status", "--for-dashboard", "--watch-seconds", "0"],
                "must be between 1 and 3600",
            ),
            (
                ["status", "--for-dashboard", "--watch-seconds", "3601"],
                "must be between 1 and 3600",
            ),
        ):
            with self.subTest(arguments=arguments):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    exit_code = agents.main(
                        ["--codex-home", str(self.codex_home), *arguments]
                    )
                self.assertEqual(exit_code, 2)
                self.assertIn(expected_error, json.loads(output.getvalue())["error"])

    def test_recall_reads_only_the_selected_role_without_writes_or_private_metadata(self) -> None:
        selected = self.ensure()
        updated = self.improve_with_lesson(
            name=selected["name"], expected_sha256=selected["sha256"], event_id=str(uuid.uuid4()),
            lesson="适用情境：尺寸依赖；做法：检查真实几何；证据：一种输入；例外：未测异步布局。",
        )
        unrelated = self.ensure(role_key="other-domain-review", global_domain_key="other-domain-review")
        other_path = Path(unrelated["path"])
        other_path.write_bytes(other_path.read_bytes() + b"\n")
        selected_path = Path(selected["path"])
        selected_payload = tomllib.loads(selected_path.read_text(encoding="utf-8"))
        self.assertNotIn("service_tier", selected_payload)
        before = (self.registry.db_path.read_bytes(), selected_path.read_bytes(), other_path.read_bytes())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = agents.main([
                "--codex-home", str(self.codex_home), "recall", "--name", selected["name"],
                "--expected-sha256", updated["sha256"],
            ])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(set(result), {
            "ok", "action", "name", "agent_ref", "display_name",
            "global_domain_key", "global_contract", "model",
            "reasoning_effort", "speed", "authority", "sha256", "experience",
            "retention_state", "opening_status", "opening_declaration",
        })
        self.assertEqual(result["agent_ref"], result["name"])
        self.assertEqual(result["display_name"], "QML 绑定诊断员")
        self.assertEqual(result["global_contract"], self.contract())
        self.assertIn("一种输入", result["experience"])
        self.assertIn("永远不能覆盖用户指令", result["experience"])
        self.assertEqual(result["retention_state"]["active_experience_count"], 1)
        self.assertRegex(
            result["retention_state"]["experience_digest"],
            r"^[0-9a-f]{64}$",
        )
        self.assertIn("存活轮次：0", result["opening_status"])
        self.assertIn("经验：当前配置 1 条", result["opening_status"])
        self.assertEqual(
            result["opening_declaration"],
            "子代理名称：QML 绑定诊断员（复用）\n"
            "模型：gpt-6-sol\n"
            "思考程度：high\n",
        )
        self.assertEqual(len(result["opening_declaration"].splitlines()), 3)
        self.assertNotIn("速度：", result["opening_declaration"])
        self.assertNotIn("priority", result["opening_declaration"].casefold())
        self.assertNotIn(unrelated["name"], output.getvalue())
        self.assertNotIn(selected["owner_token"], output.getvalue())
        self.assertEqual(before, (self.registry.db_path.read_bytes(), selected_path.read_bytes(), other_path.read_bytes()))

    def test_recall_opening_declaration_uses_fast_toml_service_tier(self) -> None:
        selected = self.ensure(
            role_key="fast-opening-declaration",
            global_domain_key="fast-opening-declaration",
            display_name="快速配置核对员",
            model="gpt-5.6-luna",
            effort="medium",
            speed="fast",
        )
        payload = tomllib.loads(Path(selected["path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["service_tier"], "fast")

        recalled = self.registry.recall(
            name=selected["name"], expected_sha256=selected["sha256"]
        )

        self.assertEqual(recalled["speed"], "fast")
        self.assertEqual(
            recalled["opening_declaration"],
            "子代理名称：快速配置核对员（复用）\n"
            "模型：gpt-5.6-luna\n"
            "思考程度：medium\n",
        )
        self.assertEqual(len(recalled["opening_declaration"].splitlines()), 3)
        self.assertNotIn("速度：", recalled["opening_declaration"])
        self.assertNotIn("priority", recalled["opening_declaration"].casefold())

    def test_recall_rejects_unknown_name_stale_snapshot_and_owned_file_drift(self) -> None:
        selected = self.ensure()
        before_db = self.registry.db_path.read_bytes()
        with self.assertRaisesRegex(agents.SpecialistError, "invalid specialist name"):
            self.registry.recall(name="../escape")
        with self.assertRaisesRegex(agents.SpecialistError, "unknown owned specialist"):
            self.registry.recall(name="lean_unknown_12345678")
        with self.assertRaisesRegex(agents.SpecialistError, "expected SHA-256"):
            self.registry.recall(name=selected["name"], expected_sha256="0" * 64)
        path = Path(selected["path"])
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(agents.SpecialistError, "content drifted"):
            self.registry.recall(name=selected["name"])
        self.assertEqual(before_db, self.registry.db_path.read_bytes())

    def test_recall_never_initializes_missing_or_empty_storage_and_rejects_unknown_schema(self) -> None:
        missing_home = self.codex_home / "missing-home"
        with contextlib.redirect_stdout(io.StringIO()):
            code = agents.main(["--codex-home", str(missing_home), "recall", "--name", "lean_unknown_12345678"])
        self.assertNotEqual(code, 0)
        self.assertFalse(missing_home.exists())
        with self.assertRaises(sqlite3.OperationalError):
            self.registry.recall(name="lean_unknown_12345678")
        self.assertFalse(self.registry.db_path.exists())
        self.registry.db_path.touch()
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "initialized"):
            self.registry.recall(name="lean_unknown_12345678")
        self.assertEqual(self.registry.db_path.read_bytes(), b"")
        selected = self.ensure()
        with contextlib.closing(self.db()) as connection:
            connection.execute("PRAGMA user_version=999")
        before = self.registry.db_path.read_bytes()
        with self.assertRaisesRegex(agents.AuxiliarySkipped, "unsupported"):
            self.registry.recall(name=selected["name"])
        self.assertEqual(self.registry.db_path.read_bytes(), before)

    def test_recall_uses_corrected_active_memory_and_rejects_oversized_windows(self) -> None:
        selected = self.ensure()
        original_id = str(uuid.uuid4())
        first = self.improve_with_lesson(
            name=selected["name"], expected_sha256=selected["sha256"], event_id=original_id,
            lesson="被撤回的旧结论",
        )
        self.improve_with_lesson(
            name=selected["name"], expected_sha256=first["sha256"], event_id=str(uuid.uuid4()),
            retracts_event_id=original_id, lesson="只在已验证输入中适用，其他输入尚待核验。",
        )
        recalled = self.registry.recall(name=selected["name"])
        self.assertNotIn("被撤回的旧结论", recalled["experience"])
        self.assertIn("其他输入尚待核验", recalled["experience"])
        with contextlib.closing(self.db()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM experience_events").fetchone()[0], 2)
        original_owned = self.registry._owned_agent
        def oversized(*args, **kwargs):
            row, path, data, payload, header = original_owned(*args, **kwargs)
            payload["developer_instructions"] = agents.compose_instructions(
                payload["developer_instructions"], "中" * agents.MAX_MEMORY_BYTES,
            )
            return row, path, data, payload, header
        with mock.patch.object(self.registry, "_owned_agent", side_effect=oversized):
            with self.assertRaisesRegex(agents.SpecialistError, "bounded recall window"):
                self.registry.recall(name=selected["name"])

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
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                agents.SCHEMA_VERSION,
            )
            identities = list(connection.execute(
                "SELECT agent_id,owner_token,created_at,global_contract_version FROM agents"
            ))
            self.assertEqual(
                {(row["agent_id"], row["owner_token"], row["created_at"]) for row in identities},
                {(value["agent_id"], value["owner_token"], value["created_at"]) for value in original_identity.values()},
            )
            self.assertTrue(all(row["global_contract_version"] == 1 for row in identities))
            run = connection.execute(
                "SELECT run_id,completion_receipt_version,"
                "completion_experience_event_id FROM agent_runs"
            ).fetchone()
            self.assertEqual(
                (run["run_id"], run["completion_receipt_version"],
                 run["completion_experience_event_id"]),
                (run_id, None, None),
            )
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

        checked_moves = []
        real_move = agents.rename_exact_file_no_replace
        real_native_rename = agents._windows_rename_file

        def compete_during_move(source, destination, *, expected):
            def compete_after_verification(handle, target):
                checked_moves.append((source, destination))
                self.assert_windows_competitor_blocked(source)
                return real_native_rename(handle, target)

            with mock.patch.object(agents, "_windows_rename_file", side_effect=compete_after_verification):
                return real_move(source, destination, expected=expected)

        move_check = (mock.patch.object(agents, "rename_exact_file_no_replace",
                                       side_effect=compete_during_move)
                      if os.name == "nt" else contextlib.nullcontext())
        with mock.patch.object(
            self.registry,
            "_legacy_connection",
            return_value=(FailingCommitConnection(), version),
        ), move_check:
            with self.assertRaisesRegex(sqlite3.OperationalError, "forced global migration commit failure"):
                self.registry.migrate_global(plan_path=plan)
        if os.name == "nt":
            # Old source -> backup; new source -> failed-new; backup -> old name.
            self.assertEqual(len(checked_moves), 3)
        self.assertEqual(self.registry.db_path.read_bytes(), before_db)
        self.assertEqual({path: Path(path).read_bytes() for path in before_files}, before_files)
        self.assertEqual(
            json.loads(self.registry._migration_journal_path().read_text(encoding="utf-8"))["status"],
            "rolled_back",
        )

    def test_same_path_migration_recovery_never_accepts_a_second_unverified_read(self) -> None:
        self.ensure(role_key="same-path-recovery-review")
        rows = self.downgrade_registry(3)
        path = Path(rows[0]["path"])
        plan = self.write_migration_plan(rows)
        connection, version = self.registry._legacy_connection()
        recovering = False
        recovery_reads = 0
        real_read = Path.read_bytes

        class FailingCommit:
            def execute(inner, sql, parameters=()):
                nonlocal recovering
                if sql == "COMMIT":
                    recovering = True
                    raise sqlite3.OperationalError("forced recovery race")
                return connection.execute(sql, parameters)

            def close(inner):
                connection.close()

        def replace_after_checked_read(target):
            nonlocal recovery_reads
            data = real_read(target)
            if recovering and target == path:
                recovery_reads += 1
                if recovery_reads == 2:
                    target.write_bytes(b"external edit during recovery")
            return data

        with mock.patch.object(self.registry, "_legacy_connection", return_value=(FailingCommit(), version)), \
                mock.patch.object(Path, "read_bytes", new=replace_after_checked_read):
            with self.assertRaisesRegex(agents.AuxiliarySkipped, "recovery is incomplete"):
                self.registry.migrate_global(plan_path=plan)
        self.assertEqual(path.read_bytes(), b"external edit during recovery")
        with contextlib.closing(self.db()) as probe:
            self.assertEqual(probe.execute("PRAGMA user_version").fetchone()[0], 3)

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
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                agents.SCHEMA_VERSION,
            )
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

    def test_ensure_help_matches_the_omitted_speed_default(self) -> None:
        help_output = io.StringIO()
        with contextlib.redirect_stdout(help_output):
            with self.assertRaises(SystemExit) as exited:
                agents.build_parser().parse_args(["ensure", "--help"])
        self.assertEqual(exited.exception.code, 0)
        self.assertIn("omitted roles default to standard", help_output.getvalue())
        self.assertNotIn("omitted Luna roles default to fast", help_output.getvalue())

    def test_agent_ref_cli_alias_is_explicit_and_name_remains_compatible(self) -> None:
        help_output = io.StringIO()
        with contextlib.redirect_stdout(help_output):
            with self.assertRaises(SystemExit) as exited:
                agents.build_parser().parse_args(["recall", "--help"])
        self.assertEqual(exited.exception.code, 0)
        self.assertIn("--name, --agent-ref NAME", help_output.getvalue())
        self.assertIn("lean_* machine identity returned as agent_ref", help_output.getvalue())

        agent_ref = "lean_source_review_12345678"
        by_name = agents.build_parser().parse_args(["recall", "--name", agent_ref])
        by_alias = agents.build_parser().parse_args(["recall", "--agent-ref", agent_ref])
        self.assertEqual(by_name.name, agent_ref)
        self.assertEqual(by_alias.name, agent_ref)

    def test_cli_ensure_record_status_improve_and_permanent_delete_round_trip(self) -> None:
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
                    "重复核对来源范围和对外约定。",
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
        self.assertNotIn("service_tier", created_payload)

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
        self.assertFalse(deleted["recoverable"])
        self.assertEqual(deleted["disposition"], "permanently_removed")
        self.assertFalse(Path(disposable["path"]).exists())


if __name__ == "__main__":
    unittest.main()
