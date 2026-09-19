# Codex Lean Stack

**Focused task execution and model-aware subagent delegation for Codex.**

Codex Lean Stack helps Codex keep engineering tasks focused and delegate independent work deliberately. It provides two skills: `$lean-simplify` for reducing unnecessary steps and implementation complexity, and `$lean-stack` for choosing and coordinating subagents.

Use either skill on its own, or both in the same task. Simplification does not block delegation, and delegating work does not replace validation.

[Usage](#usage) · [Documentation](#documentation) · [Changelog](CHANGELOG.md)

## Two independent skills

| Skill | Purpose |
| --- | --- |
| [`$lean-simplify`](skills/lean-simplify/SKILL.md) | Find the smallest complete approach to the main task. Prefer existing solutions, limit unnecessary changes, and match verification to the affected behavior. |
| [`$lean-stack`](skills/lean-stack/SKILL.md) | Delegate suitable work, select a model and reasoning effort for each task, coordinate parallel execution, and retain useful specialist experience. |

Both skills preserve the requested outcome, permission boundaries, data integrity, and the evidence needed to support a result.

## How it works

- **Quality, cost, then time.** Model and reasoning effort are selected together. A delegated task must meet the required quality, use a proportionate configuration, and help the parent task finish sooner. More agents are not an objective in themselves.
- **Tools before agents.** Deterministic work goes directly to tools. Complex PowerShell and cross-language commands use script files and explicit argument boundaries instead of layers of inline shell escaping.
- **Clear ownership.** Parallel writers need defined scopes and an isolation strategy. Source evidence and verified results are reused rather than independently rediscovered by every agent.
- **Reusable specialists.** Supporting utilities maintain agent profiles, recorded outcomes, and reusable experience. They support delegation; they do not launch agents on their own.

Simplification is not a reason to skip necessary checks. The aim is to remove work that does not contribute to the result, not the safeguards that make the result trustworthy.

## Installation

Install `codex-lean-stack` from a configured Codex marketplace that contains the plugin. Cloning this repository alone does not install it.

In Codex CLI, enter `/plugins`, select the marketplace entry, and install the plugin. Start a new session before using its bundled skills. See the [OpenAI plugin documentation](https://learn.chatgpt.com/docs/plugins) for supported surfaces and marketplace setup.

Standard plugin installation does not edit your global instructions. The repository's [optional installation helper](skills/lean-stack/scripts/install_plugin.py) is separate and should only be used when you explicitly want default usage configured. It uses the selected Codex home and updates the active global instruction file: a non-empty `AGENTS.override.md`, or `AGENTS.md` otherwise.

## Usage

For a focused implementation:

```text
Use $lean-simplify to implement this change with the smallest complete solution and the checks it needs.
```

For work that can benefit from delegation:

```text
Use $lean-stack to delegate independent work where it improves completion time, choosing models and reasoning effort to match each task.
```

Both skills can be named in the same request. Neither is a prerequisite for the other.

## Compatibility and scope

A Codex environment with plugin support is required. Subagent delegation also depends on the models and native agent tools available in that environment.

This plugin supplies workflow instructions and helper scripts. It does not provide model access, replace the Codex runtime, or run a background orchestration service. Updating this source checkout does not automatically update an installed plugin copy or an existing session.

## Documentation

| Topic | Reference |
| --- | --- |
| Skill entry points | [Task simplification](skills/lean-simplify/SKILL.md) · [Subagent delegation](skills/lean-stack/SKILL.md) |
| Execution and coordination | [Execution routing](skills/lean-stack/references/execution-routing.md) · [Delegation](skills/lean-stack/references/delegation.md) · [Coordination parents](skills/lean-stack/references/collaboration.md) |
| Parallel changes | [Writable parallelism](skills/lean-stack/references/write-parallelism.md) |
| Specialist reuse | [Agent profiles and experience](skills/lean-stack/references/specialist-memory.md) |
| Reducing complexity | [Anti-overengineering](skills/lean-stack/references/anti-overengineering.md) · [Ablation loop](skills/lean-stack/references/ablation-loop.md) |
| Releases | [Changelog](CHANGELOG.md) · [Versioning](skills/lean-stack/references/versioning.md) |

Detailed workflow references are currently written primarily in Chinese. The original Chinese README is also preserved in the expandable reference below.

## Development

Make changes in this source repository rather than editing the installed plugin cache. For changes to skill documentation and contracts, run the relevant contract tests:

```sh
python -m unittest discover -s tests -p test_skill_contract.py
```

Choose additional checks according to the behavior affected by the change.

## License

[MIT](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for attribution.

## Technical reference

<details>
<summary>Chinese workflow reference</summary>

# Codex子代理调用与精简流程

插件标识：`codex-lean-stack`

## 当前版本 5.2.16

5.2.16 将两个平行入口改为真正按动作触发：非平凡主任务才读取 `lean-simplify`，首次真实派发或启动新的 `followup_task` 前才读取 `lean-stack`；入口正文收窄为决策、硬门和条件式引用。五行配置只由对应子代理本人在自己的第一条可见 commentary 宣读，父代理只写内部任务卡。源码更新不代表安装缓存或已运行会话已更新。

当前使用取向是主要由 Sol 担任父代理，并把高价的 `gpt-6-astra` 留作可调用的子代理专家；具体任务只按模型与思考程度能否联合达到必要质量、质量充分组合是否成本相称、子代理是否实际加快父任务完成三项原则判断。

1. 主任务精简与四模型子代理调用平行、独立工作。`$lean-simplify` 与 `$lean-stack` 按各自职责触发，可单独使用，也可在同一任务中并行；子代理调用不等待主任务精简，主任务精简也不阻断符合三项原则的调用。两个功能分别验收、互不代证。
2. 两个或更多子代理将修改文件或共享状态时，父代理在首次可写派发前记录 `WRITE_ROUTE`，明确写入者、范围、共同热点、隔离路线、撤销依据和受影响检查；范围不能隔离或撤销不能精确归因时，只允许一个候选直接写目标。
3. 同一卷内只改变路径的移动不再默认建立迁移前后整树长度与 SHA-256 清单；路径与结构验收、实际字节复制以及正式交付清单使用各自相称的验证。
4. 写入安全、用户否定、反 AI 过度工程、消融和条件性验证由插件自身的权威 reference 单一承载，不要求项目文档复制规则。
5. 插件不规定项目交接文件的创建、读取、更新或结构；这些由用户和项目或全局规则决定。新会话不无条件读取两个入口：非平凡主任务触发 `lean-simplify`，首次 `spawn_agent` 或用 `followup_task` 启动新当前子任务前触发 `lean-stack`；已读且未变化的入口直接复用。只读取当前实际动作命中的入口，不预读未触发入口或完整 `references`。入口读取后的下一次工具调用立即开始实际任务；其他技能用途说明合并到唯一启动说明。两入口仍可在同一任务中分别命中，但互不等待、互不代证。
6. 同一长来源由一个所有者完成发现与完整读取；其他子代理复用 `SOURCE_ROUTE` 证据包，只定向补
   具名缺口或必要的高风险事实。
7. 每次原生派发必须同时提交显式模型、思考程度、有限上下文和五行任务卡；缺字段、使用“继承”占位或给普通 UI 选择 Sol `ultra` 时不得调用。父代理只把五行写入内部任务卡，不在自己的用户可见 commentary 或最终回复中代为展示或重复；只有子代理本人在自己的第一条可见 commentary 以“子代理名称、模型、思考程度”三行实际配置开场，随后显示存活轮次和经验状态，仍不显示父侧 `run_id`；经验版本可以
   与后续明确结果关联，旧调用和旧迁移记录继续兼容但不伪造历史复用。
8. 用户已明确要求安装插件的所有项目和新会话保持主动委派；符合三项原则的独立切片立即调用，
   不等待逐次重申，并可为提高父任务完成速度在实际并发容量内同时派发多个子代理。面向用户
   主任务的启动句不适用于子代理；中文会话的可见子代理名称必须使用
   中文，不能照抄技术 `task_name`。
9. 普通派发若此前派发已触发读取且入口未变化就直接复用，否则只读取一次 `lean-stack` 入口；
   命中候选后才读取其完整保留合同。父代理采用新运行时组的结果后，新加入先执行首次 `ensure`，
   仅对 `reconfiguration_required` 或 `global_contract_refresh_required` 响应用返回 SHA 作一次 CAS
   确认，再执行一次 `complete-run`；复用直接走 `complete-run`。明确跳过必须留下原因，`improve`
   不能代替完成收据。

## 中文

### 两个并行功能

1. **共同执行底座。** 两个入口都遵守[Windows exec 稳健性契约](skills/lean-stack/references/execution-routing.md)：确定性短工作直接用工具，独立短命令用一次工具调用并发，复杂或跨语言代码及时转为任务专属脚本，分离参数和数据，不增加多余包装或通用执行层。
2. **子代理调用 `$lean-stack`。** 负责调用判断与模型、成本、时间选配，上下文、来源和结果复用，内部交流与子代理结果收口，子代理、经验和生命周期表面精简，以及迭代测试链。
3. **主任务精简 `$lean-simplify`。** 负责最小完整任务方法，主任务状态与沟通收窄，调查、实现和任务手册，测试、复核和重验范围，反过度工程与维护面，显式消融，发布、安装和文档维护，以及条件性语义复核与最终验证链、失败后的最窄重验链。
4. **互不代证。** 主任务精简不要求先调用子代理；复杂任务可同时使用两个入口，但调用记录不能证明主任务已精简，静态精简规则也不能证明子代理运行成功。
5. **子代理经验归调用功能。** `agents.py` 的子代理、运行、经验与摘要维护是子代理生命周期，不是源码、设计或规则精简，也不会自行启动子代理。

三项原则只决定工具、模型与子代理路线；任务步骤是否必要以及精简候选是否采用，不由模型成本替代，而看用户结果、核心功能、维护面和相称验收。

### 主任务精简

1. **首条说明先到。** 先说明理解、立即动作和必要范围；过程中报告有效进展，最终交付入口、验证对象与剩余问题。
2. **锚点只留剩余要求。** 已交付事项退出；纠正只重开受影响项，“继续”不复活历史待办。
3. **停在首个完整方法。** 依次考虑不实现、复用现有实现、标准库、平台能力、既有依赖、删除/内联/合并，最后才增加最少代码和文件。
4. **调查与实现只读需要的手册。** 测试、复核和重验只覆盖真实受影响范围，不从仓库已有测试文件数、测试函数数、历史全套命令或“发布”标签反推每轮范围；条件性语义复核与最终验证、失败后的最窄重验分别按触发条件进入。
5. **反过度工程与显式消融分开。** 普通任务预防维护面扩大；只有用户明确要求时才执行正式消融。
6. **发布与文档相称。** 只更新不改就会错误承诺的表面；发布、安装、提交和推送仍按当前授权，已有版本收据不重复升版。
7. **运行验收只留一条链。** 同一根因的首次探针失败后先修根因，再做一次决定性复验；目标条件已经覆盖就停止，不因措辞或模型档位变化连续新建验收会话。

### 子代理调用前

1. **工具先行。** 短命令、批量查询和确定性工作直接用工具，不启动只会代跑命令的模型子代理。
2. **复杂 PowerShell 及时落到脚本。** 多层引号、JSON/正则或多行逻辑使用任务专属 `.ps1`；确认转义失败后只修同一脚本，按执行路由检查 Parser、实际结果和退出码，不反复改 one-liner。
3. **三原则决定调用。** 直接判断模型是否适合并守住必要质量、思考程度是否与任务相称、该子代理
   是否实际加快父任务完成。调用数量本身不构成成本错误；上下文、交流、整合和复验按各自执行
   规则收敛，不作为新增调用的第二套判断清单。
4. **新会话按触发开始。** 不在开场通读两个入口。非平凡主任务只触发 `lean-simplify`；首次真实派发或启动新 `followup_task` 前只触发 `lean-stack`。入口已读且未变化时直接复用；未触发入口和完整 `references` 不预读。入口读取后的下一次工具调用立即推进实际任务；本轮其他技能用途说明合并到唯一启动说明，不追加逐技能前言。无关记忆、保留目录、委派或版本解释不能阻塞主任务，也不能预造用户未要求的交付物。
5. **四模型联合选配。** 不设调用数量；父代理按任务类型与任务类型组复用保留子代理或定制新子代理，一次联合选择模型与思考程度，并保留 `MODEL_ROUTE` 收据。Luna 处理清楚易验切片，Terra 处理有限语义歧义，Sol 承担复杂端到端工作；Sol `max` 可按任务需要选用，只有 Sol `ultra` 要求高价值复杂边界及 `xhigh`、`max` 均不足的具体依据。Astra 仅处理 GPT-5.6 仍有决定性质量差距的当前专家问题，最高 `xhigh`，普通视觉任务不触发。任何层级、任何子代理的每次 `spawn_agent` 都显式传入模型和思考程度；保留子代理以 TOML 为实际值来源，但 TOML 不能代替原生调用参数。保留子代理 TOML 的其他宿主预配置由保留子代理生命周期规则维护，不进入本次模型与思考程度选配、任务卡、`MODEL_ROUTE` 或可见声明。
6. **上下文按需。** 独立任务优先 `fork_turns="none"`；同一长来源由一个所有者完整读取，其他
   子代理消费可定位证据包，只为具名缺口或必要高风险事实定向复核。

### 子代理运行中

1. **内部交流只服务真实依赖。** 证据能解锁下一动作、需要纠偏或出现风险时才发消息。
2. **子代理先公开实际配置与保留状态。** 父代理把“子代理名称、模型、思考程度”三行实际配置及
   “存活轮次、经验状态”两行客观状态写进每个新当前任务的内部任务卡，但不得在父代理自己的用户可见 commentary 或最终回复中代为展示或重复。该合同从父到子、从子到孙逐层适用，不假定通用、具名、保留或继承历史会自动取得这些值。只有子代理本人在自己的第一条可见 commentary 严格依此五行开头；保留子代理采用 `recall` 的客观状态，运行时子代理说明 0 轮和未加载保留经验。五行前不出现计划或运行 ID；子代理自己的最终回复只重复当前任务卡前三行。上级保留角色的固定身份、模型和思考程度即使被宿主传播到下游，也不得覆盖下游自己的任务卡。
   面向用户主任务的交接启动句不适用于子代理；普通派发只读一次 `lean-stack` 入口，不通读参考文档。轻量路由目录选中候选后才 `recall` 完整合同；每个新运行时组的结果被采用后，必须完成保留/经验写入或给出明确跳过原因。
3. **关键步骤只为真实依赖。** 只有中间结果会解锁下一动作时才报告一次并继续；不发送定时心跳、纯确认消息或普通过程复述。
4. **父代理不中断主线。** 父代理立即推进，只在真实依赖点等待，不完整重做已核验结果。
5. **持续多工作流任务尽早派发并重判。** 新范围、独立困难或压缩后的多个就绪工作流会使旧的直接处理判断失效；对新切片重新判断模型、思考程度和实际提速。
6. **协作保持所有权。** 变体只为真实改进；子代理可以成为协作父代理；两个或更多子代理将写入时，父代理先用 `WRITE_ROUTE` 明确范围、热点、隔离、撤销依据和受影响检查，结果以 `SOURCE_COVERAGE` 说明来源覆盖。

### 子代理收口与复用

1. **每个子代理独立交付。** commentary 不是最终结果；具体缺口最多补问一次，否则关闭或只改派缺口。
2. **复用和加入保留子代理走同一完成入口。** 父代理在派发前生成稳定 UUID `run_id`；结果核验
   采用后只调用一次 `complete-run`，在同一事务中记录明确结果与可选经验。新加入时先执行一次
   `ensure`，随后使用同一完成入口；任一步失败都不会留下 TOML 与数据库的半完成状态。旧
   `record-run` 和 `improve` 仍兼容。每个能力族只保留一个全局领域子代理，没有项目保留层。
3. **累计两次明确失败后永久移除子代理资料。** 运行中、中断、未采用、用户停止或结果未定不算失败。
4. **迭代测试链归调用功能。** 主任务精简确定检查对象、预期和受影响范围；`$lean-stack` 独立选择直接工具或有收益的验证子代理并收集结果，两者不形成技能加载或调用前置关系。
5. **清理与权限守界。** “精确删除与否定重做”属于子代理生命周期；普通文件进入 Windows 回收站。安全、权限、数据完整性和不可逆损失保留相称保护，委派不增加外部权限。
6. **历史机制不恢复。** 双入口拆分不恢复已删除的多层评分与否决、项目保留层、租约/停滞/晋升/退役恢复或同类中间状态；现实迁移、所有权、CAS 和 SQLite/TOML 保护继续保留。

### 调用流程

```text
收到任务 → 工具能确定完成则直接执行
→ 否则判断有收益的独立切片
→ 复用或定制合适子代理
→ 父代理并行推进并在真实依赖点整合
→ 核验、记录可复用经验、交付主任务
```

### 不调用代理的情况

- 工具更快且足够可靠；
- 输入未就绪或任务严格依赖前一步；
- 写入冲突无法隔离，或缺少所需能力、工具、权限与运行容量；
- 只会重复已有工作；
- 没有能守住质量的合适模型或相称思考程度，或子代理不能实际加快父任务完成。

## 安装与使用 / Install and use

Codex 从 marketplace 安装插件；本仓库是可编辑源码：

```powershell
codex plugin add codex-lean-stack@<marketplace> --json
```

新建 Codex 会话后，可按任务需要单独或同时使用两个入口：

```text
使用 $lean-simplify 独立精简主任务。使用 $lean-stack 独立判断并调用有收益的子代理；任一方不以另一方为前置。
Use $lean-simplify independently for main-task simplification. Use $lean-stack independently for beneficial subagent routing; neither entry is a prerequisite for the other.
```

安装后验证子代理调用时只运行最小探针：从调用收据观察真实启动事件、模型和思考程度后立即
停止并由测试父任务中断子代理，不等待或要求子代理完整做题；该结果不外推为业务质量证明。
只有在正式安装、全新项目目录、独立父任务且只依赖自动加载的全局入口与正式缓存时，这才是
正式新会话调用验收；其他情形只算安装后的调用面探针。

当前加载规则见 [OpenAI 官方插件文档](https://learn.chatgpt.com/docs/plugins)。
See the [official OpenAI plugin documentation](https://learn.chatgpt.com/docs/plugins).

普通 `codex plugin add` 不会修改全局 `AGENTS.md`。Plain `codex plugin add` does not edit global `AGENTS.md`.
只有明确要求默认调用时才运行：

```powershell
py -3 -X utf8 .\skills\lean-stack\scripts\install_plugin.py --marketplace <marketplace>
```

辅助安装器会把用户全局文件中以“所有模型和思考程度的父代理必须使用”或“必须都使用”开头的
展开句式识别为已有调用入口；命中后保持文件字节不变，不重复追加旧式默认行。

## 文档 / Docs

- [子代理调用技能 / Subagent calling skill](skills/lean-stack/SKILL.md)
- [主任务精简技能 / Main-task simplification skill](skills/lean-simplify/SKILL.md)
- [执行路由 / Execution routing](skills/lean-stack/references/execution-routing.md)
- [子代理委派 / Delegation](skills/lean-stack/references/delegation.md)
- [协作父代理 / Coordination parents](skills/lean-stack/references/collaboration.md)
- [全局领域经验 / Global-domain experience](skills/lean-stack/references/specialist-memory.md)
- [可写子代理并行 / Writable parallelism](skills/lean-stack/references/write-parallelism.md)
- [反 AI 过度工程 / Anti-overengineering](skills/lean-stack/references/anti-overengineering.md)
- [消融反馈循环 / Ablation loop](skills/lean-stack/references/ablation-loop.md)
- [本仓库交接记录 / Repository handoff](Jiao-Jie.md)
- [版本说明 / Changelog](CHANGELOG.md)

本仓库是唯一可编辑源码，安装缓存只用于核对。提交前运行当前改动真正影响的最窄约定一致性测试。

## License

[MIT](LICENSE)

</details>
