# Codex Lean Stack

**Focused task execution and model-aware subagent delegation for Codex.**

Current version: **9.2.0**

- Apply everyday code simplification through `$lean-simplify` during implementation and review: validate external inputs at their owning boundary, keep clear one-use logic local, and add exception handling only when it serves the current error contract.
- Explain concrete failure modes, likelihood evidence, and complexity cost before expanding scope for speculative, very unlikely edge cases; preserve necessary security, data integrity, rollback, and resource cleanup.
- Use the existing plugin entrypoints and one [authoritative reference](skills/lean-stack/references/anti-overengineering.md#日常代码精简); no global instruction-file update is required.

Codex Lean Stack provides two independent skills:

| Skill | Purpose |
| --- | --- |
| [`$lean-simplify`](skills/lean-simplify/SKILL.md) | Find the smallest complete path through the main task and match verification to the affected behavior. |
| [`$lean-stack`](skills/lean-stack/SKILL.md) | Delegate useful independent work, choose a model and reasoning effort, and reuse compatible subagents. |

Either skill can be used alone. Both preserve the requested result, permission boundaries, data integrity, and the
evidence required to support a conclusion.

## How delegation works

- **Quality, cost, and time by context.** Use the Astra expert route for difficult high-value work when it has a
  decision-changing quality advantage; compare total cost
  after ordinary options meet the same reliability bar; add parallel help for speed within an acceptable cost range.
  An explicit request for [continued parallel speedup](skills/lean-stack/SKILL.md#用户要求持续并行提速) overrides that default cost gate for the current task, while preserving quality, permissions, real capacity, dependencies, and write ownership.
- **Necessity before model selection.** Apply the [whole-task decision](skills/lean-stack/SKILL.md#先判断是否委派再选模型与复用) before selecting or reusing a child. Means, defined formulas, event aggregation, and file comparisons stay with parent tools; an independent recalculation does not automatically require another model.
- **Parent participation.** Keep suitable implementation, research, or critical-path work with the parent, then delegate the remaining useful slices. Compare end-to-end completion time and combined cost, including handoffs, waiting, integration, and verification. Continued parallel speedup preserves this decision.
- **Tools first.** Deterministic work goes directly to tools; Computer Use keeps its parent-guided Terra execution rule.
- **Reuse one capability family.** Small follow-ups within an unfinished semantic task continue a compatible live child without a new
  model-selection pass. New deterministic calculations stay with parent tools even when a child is already available. For a new capability with no suitable current child, perform one bounded registry lookup. A retained
  role is reused when it is loaded in the current session, belongs to the same capability family, and is quality-compatible.
  Read only that retained role before generic or runtime fallback. A registry-wide lookup failure does not discard an
  already-loaded candidate that clearly meets those three conditions; read that candidate once and reuse it if the
  selected-role read succeeds. Reuse an unchanged lookup result instead
  of querying again. If both a current child and a retained child meet the quality bar, choose the lower combined
  parent-child cost; do not switch threads merely to improve a reuse statistic.
- **Conditional runtime copies.** Use isolated copies for separate ready slices in one capability family, and use
  configuration variants only when comparable evidence can answer a real routing question.
- **Explicit native configuration.** Every `spawn_agent` supplies the actual model, reasoning effort, and bounded
  history. A task card or retained profile does not replace native parameters.
- **Small task cards.** New children receive five verified opening lines, the instruction to display them in
  the first progress note and repeat the first three in the final, one goal, needed evidence, ownership,
  success conditions, and stop conditions. Retained experience stays in the loaded role instructions. A reused
  live child without verified retained recall says only `经验：复用当前线程上下文`; a new runtime role says
  `经验：本次任务上下文`; unverified persistence placeholders are forbidden.
- **Controlled registry growth.** A runtime role is selectively retained when the same kind of task is genuinely
  expected again, expected reuse benefit exceeds maintenance and lookup burden, and no compatible family exists.
  Existing families are reused or CAS-reconfigured. There is no fixed retention rate or quota.
- **Honest metrics.** `retained-spawn share`, opportunity reuse, and qualified retention are observations, not targets.
  They have no fixed percentage. Never create calls, over-retain roles, or duplicate identities to improve a number.
  A low retained-spawn share cannot establish a missed reuse opportunity.

A new child uses `gpt-6.1-terra`, `gpt-6.1-sol`, or `gpt-6-astra` according to task needs, with reasoning effort from `medium` upward.
The first two are ordinary subagent routes; only `gpt-6-astra` is the expert route.
`gpt-6.1-terra` handles simple, speed-prioritized work with clear inputs, low risk, and direct acceptance checks:
bounded reading, structured extraction, factual summaries, text revision, defined screen operations, and small local edits.
Use `medium` normally and `high` for limited local ambiguity. Complex trade-offs, cross-module causality,
compliance or safety judgments, high-risk changes, and final review conclusions use a suitable Sol or higher.
Historical Luna profiles remain readable; new profiles and explicit CAS reconfigurations use the current three models.
For Computer Use, the parent directs and verifies while GPT-6.1 Terra performs the UI operations, including
read-only observation. Complex decisions stay with the parent or a suitable Sol/Astra. One operator owns a shared
desktop, window, or tab; direct tool access and permissions must be valid in the executing child.
Astra is selected only when the strongest suitable `gpt-6.1-sol` option still has a decision-changing quality gap.
Its reasoning effort is chosen per task from `medium`, `high`, or `xhigh`; `xhigh` is the upper bound,
not the default.
Routing is reconsidered only when the task type, quality threshold, authority or evidence boundary, expert necessity,
or expected cost changes materially; a small follow-up on the same task continues directly. If Astra is still required,
a separate second decision chooses the old Astra thread or another
compatible Astra route; low context value ends the old thread but does not downgrade the task. A completed, adopted
Astra whose acceptance criteria are satisfied stops unless new requirements, evidence, an unmet acceptance condition,
or an explicit correction justifies more work; historical Astra use does not lock the next slice to Astra.

## Installation

Install `codex-lean-stack` from a configured Codex marketplace. Cloning this repository does not install it.
Start a new session after installation. See the
[OpenAI plugin documentation](https://learn.chatgpt.com/docs/plugins) for supported surfaces.

Standard plugin installation does not edit global instructions. The optional
[installation helper](skills/lean-stack/scripts/install_plugin.py) is separate and is used only when the user
explicitly asks to configure default invocation. It may only ensure the plugin's single invocation line; it does
not copy delegation rules into the user's global file.

## Usage

```text
Use $lean-simplify to implement this change with the smallest complete solution and the checks it needs.
```

```text
Use $lean-stack to delegate independent work under the quality, total cost, and time principles, reusing the same capability family when possible.
```

## Scope and evidence

This plugin supplies workflow instructions and local maintenance scripts. It does not provide model access,
replace the Codex runtime, intercept native agent calls, or run a background orchestration service. Source edits,
template tests, an installed cache, and live host behavior are separate evidence surfaces.

A child's user-visible progress note is called **进展说明** in the Chinese documentation. It is not a final result.
Children continue to explain meaningful progress, changes, and problems while working. Task cards must not
require default silence or opening-and-final-only reporting. Internal messages to the parent are reserved for
dependencies, corrections, and risks; reducing duplicate messages must not suppress normal progress updates.
The parent adopts a child result only from its final response or an equivalent result receipt.

## 中文说明

### 两个平行入口

- `$lean-simplify` 收窄主任务步骤、修改范围和验证范围；
- `$lean-stack` 判断是否委派、选择模型与思考程度，并复用同一能力族的子代理；
- 两个入口互不前置，也不能互相代替验收。

### 子代理选择

确定性工作直接用工具。高价值难题先守正确性并派专家；普通工作可靠性相当后比较总成本；
总成本可接受时可增派子代理提速。三项无需每次同时获益。决定委派后依次
选择：

1. 同一任务、澄清、纠错或紧密相关的小补充，直接继续使用质量和边界兼容的当前子代理；
2. 新的能力类型没有适合继续使用的当前子代理时，只做一次快速、有界台账查询；当前会话已经
   加载、属于同一能力族且质量兼容的保留子代理会被复用；只读取选中的保留子代理一次。目录查询
   失败但当前会话已加载类型中已有符合三项条件的明确候选时，仍只读取该候选一次；读取成功就复用。
   只有没有可核对候选或读取失败时，本次才新建运行时子代理；查询失败不得当成空台账建档；
3. 查询结果和候选条件未变化时复用本轮结果，不重复查；当前子代理与保留子代理都可用时，在质量
   达标后比较父子合计总成本，选更低成本的一条，不为统计台账复用强制换线程。

同一能力族有多个独立已就绪切片时，可以按各自任务卡创建运行时复制；只有存在真实选配疑问并
且结果可比较时才形成配置变体。两者都只属于当前运行；比较、采用和未来保留仍走原有权威分支。

新调用按任务分工选 `gpt-6.1-terra`、`gpt-6.1-sol`、`gpt-6-astra`，思考程度从 `medium` 起。Terra 承担输入清楚、风险低且验收直接的速度优先简单工作：有界读取、结构化提取、事实总结、文字整理、明确界面操作和局部小修改；通常 `medium`，有限局部歧义可用 `high`。复杂取舍、跨模块因果、合规或安全判断、高风险修改及最终审查结论至少使用合适的 Sol。Astra 仅在最强可行 `gpt-6.1-sol` 仍有决定性质量差距时使用。旧 Luna 资料保持可读，新建或显式重配使用当前三档；兼容身份按 CAS 重配并由新任务验证宿主加载，旧会话的固定 Luna 配置不能冒充 Terra。

Computer Use 类型任务由父代理指导 GPT-6.1 Terra 实际操作，包括只读界面观察。父代理负责目标、授权范围、阶段指导与验收，复杂判断仍交给合适的 Sol/Astra；Terra 依据当前界面执行并反馈。同一桌面、窗口或标签页保持一个操作者，工具须在子代理中真实可用，委派不扩权。详细合同见[父代理指导、Terra 操作](skills/lean-stack/SKILL.md#computer-use父代理指导terra-操作)。
前两档都是常规子代理路线；只有 `gpt-6-astra` 是专家路线。
模型和思考程度分别按任务选择。Astra 可以使用 `medium`、`high`、`xhigh`，不能每次固定
为 `xhigh`。每次 `spawn_agent` 都显式传入真实模型、思考程度和非全量历史。

新子代理任务卡写五行真实配置与状态，名称后按实际派发标一次“（复用）”或“（新建）”，并把
“首条用户可见进展说明展示五行、最终回复顶部重复前三行”的执行句直接交给子代理，再写唯一
目标、必要来源、权限或写入所有权、成功条件和停止
条件。选中已加载保留类型后，只读取该保留子代理一次；保留经验已在角色指令中，任务卡只传五行
状态，子代理读完经验便开始任务。读取失败
就改派运行时子代理，后两行写 0 轮和“经验：本次任务上下文”。每次调用不触发成本核对，健康台账保存
新经验也不等待旧摘要纠错或版本维护；写入失败由父代理保留具名事项并在主任务推进后修复。
复用当前子代理但没有已核验的保留子代理读取状态时，经验行只写“经验：复用当前线程上下文”，不得
显示“未核验持久化经验”或其他占位语。
用户可见说明使用中文展示名，必要代码标识紧邻中文解释；机器名只在命令或核验证据中出现。

只有任务类型、质量门槛、权限或证据边界、专家必要性、预计成本发生实质变化时才重新选路；同一
任务的小补充直接继续，不重复评估。历史使用 Astra 不锁定未来模型。若当前质量仍需 Astra，再独立决定续用旧线程或改派兼容 Astra；旧线程
上下文无边际价值只决定停止旧线程，不能据此降到 Sol/Terra。已完成且采用、验收满足的 Astra
无新增依据时停止。

子代理完成后，父代理核验结果并继续主任务。运行时子代理在以下条件成立时选择性建档：

- 预计以后确实还会遇到同类任务；
- 预计复用收益高于维护和查找负担；
- 没有兼容的现有能力族。

同族已存在就复用或按 CAS 重配；不设固定建档率、配额或强制百分比。
只有新增可复用经验或已采用保留身份的明确失败才按需记录完成。

## Documentation

| Topic | Reference |
| --- | --- |
| Skill entry points | [Task simplification](skills/lean-simplify/SKILL.md) · [Subagent delegation](skills/lean-stack/SKILL.md) |
| First dispatch and reuse | [Dispatch start](skills/lean-stack/references/dispatch-start.md) |
| Sources and results | [Source ownership](skills/lean-stack/references/source-results.md) · [Result convergence](skills/lean-stack/references/agent-results.md) |
| Parallel changes | [Writable parallelism](skills/lean-stack/references/write-parallelism.md) |
| Coordination parents | [Collaboration](skills/lean-stack/references/collaboration.md) |
| Retained identities and experience | [Specialist memory](skills/lean-stack/references/specialist-memory.md) |
| Workflow diagrams | [Chinese flowcharts](skills/lean-stack/references/flowcharts-zh.md) |
| Releases | [Changelog](CHANGELOG.md) · [Versioning](skills/lean-stack/references/versioning.md) |

## Development

Edit this source repository rather than the installed plugin cache. Run the narrow behavior and contract tests
affected by a change, then run the complete suite once when the final code range requires it.

## License

[MIT](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for attribution.
