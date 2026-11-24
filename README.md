# Codex Lean Stack

**Focused task execution and model-aware subagent delegation for Codex.**

Current version: **10.1.2**

Read the complete section needed for the next action. New conversations use creation rather than
history forks unless requested, and handoffs preserve the scope of temporary instructions. UI control
includes the user's ownership and precise undo; delivered capabilities verify the public entry,
actual backend calls, and visible results rather than startup or lower-level tests alone.

Delegation continues after the first batch. When a remaining assigned package becomes the delivery bottleneck,
the owner checks for independent core work that additional agents can advance. The original owner retains
acceptance and delivery responsibility; shared files keep one writer. Result adoption, waiting, stage recovery,
and group coordination use the same rule, without creating idle agents or repeated reviews to maintain a count.

Large projects that already have a native ongoing goal can use [group conversations](skills/lean-simplify/SKILL.md#大型目标项目的分组会话).
The project owner checks whether several related workstreams need independent long-running contexts, explains a
concrete grouping, and asks whether to adopt the mode. No conversation is created before explicit consent;
ordinary tasks and projects without a goal stay in the current conversation. Approved groups each establish a
scoped goal, own their files, adopt prior results, and return usable outcomes to the original coordinator for acceptance.
No hook setup is required.
Related workstreams finish the research needed for their joint change before implementing together; independent
workstreams advance when ready, then integrate and verify. Reuse adopted research and connect new findings to an actual consumer.

Explicit delegation and continued workstream coverage go directly to execution. Initial dispatch, result adoption,
dependency resolution, and released capacity reuse that decision; only unspecified delegation goes through the
default necessity and benefit check. Before waiting or ending, fill ready but unassigned work in the requested
undelivered goals. Cost optimization chooses executors without cancelling explicit coverage; real safety,
permission, budget, and capacity limits still apply.

- Continue necessary diagnosis, fixes, builds, and narrow acceptance checks within the authorized repair scope, even when they take longer. Ask before optional lengthy backups, scans, repeat readbacks, or other marginal work; skip that added work without a reply. Necessity comes from the requested outcome, a real blocker or concrete risk, and existing evidence; duration or a tool default does not establish it. Actual permission gaps and scope expansion still require authorization. Necessary project component upgrades retain the standing ask-then-upgrade default.
- Respond promptly to priority changes and preserve the latest effective requirements across context compression, including withdrawn temporary speedup modes. Reuse valid evidence; ten minutes without material change requires diagnosis and a changed next action at a safe boundary.

- Child-task opening and final replies keep all five configuration/status fields, including verified counts and experience. New-task openings precede business tools; continuing the same task reuses its confirmed status.

Ordinary child tasks start from their current task card and named evidence. Root-project bootstrap and handoff stay with the project parent; a local coordinating parent only manages its authorized subtree. New tasks reset to their current assignment, while continuation preserves that task's scope. Explicit evidence reads and required operational skills remain available.

Codex Lean Stack provides two independent skills:

| Skill | Purpose |
| --- | --- |
| [`$lean-simplify`](skills/lean-simplify/SKILL.md) | Find the smallest complete path through the main task and match verification to the affected behavior. |
| [`$lean-stack`](skills/lean-stack/SKILL.md) | Delegate useful independent work, choose a model and reasoning effort, and reuse compatible subagents. |

Either skill can be used alone. Both preserve the requested result, permission boundaries, data integrity, and the
evidence required to support a conclusion.

For [multiple goals](skills/lean-simplify/SKILL.md#多目标推进与逐项交付), keep each undelivered outcome, its evidence,
owner, authorization, and next action or dependency in the existing task snapshot. Research can require running,
debugging, reverse engineering, or changing an isolated research tool within the authorized scope. Adopt each result
into the next operation, implementation, or acceptance check; continue requested delegation beyond the first wave,
and deliver accepted slices while other goals proceed. Compression restores every remaining goal and the latest
effective scope, rather than restarting completed work or treating one blocked goal as a project-wide stop.

For 6.2, the [calling safeguards](skills/lean-stack/references/dispatch-start.md#62-调用防错) address missing facts, omitted blockers, and unproductive loops. They reduce risk and do not guarantee error-free output. User instructions and permission boundaries still apply.

## How delegation works

The defaults below fill only decisions the user has not explicitly made, including model, reasoning effort, tool, operator, and reuse choices. Actual permissions, available tool parameters, fixed-role configurations, and data protections still apply.

- **Explicit instructions first.** Apply [user priority](skills/lean-stack/SKILL.md#用户明确指令优先) to requested agent counts and collaboration arrangements, including an instruction not to delegate. Default cost, tool-first, parent-participation, and reuse rules fill only the remaining decisions.
- **Quality, cost, and time by context.** Use the Astra expert route for difficult high-value work when it has a
  decision-changing quality advantage; compare total cost
  after ordinary options meet the same reliability bar; add parallel help for speed within an acceptable cost range.
  The default has no fixed headcount. At initial assignment, new input, dependency completion, or released capacity, assign useful ready work under the same quality, combined-cost, and completion-time principles. [Explicit parallel arrangements](skills/lean-stack/SKILL.md#用户要求持续并行提速) change only what the user specified: more agents or unlimited headcount does not waive cost constraints or require saturation; ignoring cost and keeping capacity full are separate instructions. Quality, permissions, real capacity, dependencies, and write ownership still apply.
- **Necessity before model selection.** Apply the [whole-task decision](skills/lean-stack/SKILL.md#先判断是否委派再选模型与复用) before selecting or reusing a child. Means, defined formulas, event aggregation, and file comparisons stay with parent tools; an independent recalculation does not automatically require another model.
- **Parent participation.** Keep suitable implementation, research, or critical-path work with the parent, then delegate the remaining useful slices. By default, compare end-to-end completion time and combined cost, including handoffs, waiting, integration, and verification. Explicit cost relaxation alone removes the default cost gate; dynamic parallel work keeps parent participation.
- **Tools first by default.** Deterministic work goes directly to tools; explicit user assignments take priority. Computer Use keeps parent-guided execution: Terra for routine low-risk operations and Sol for complex or high-risk operations when the user has not specified another available operator or tool.
- **Reuse one capability family by default.** Explicit user choices of a new or available executor take priority. Small follow-ups within an unfinished semantic task continue a compatible live child without a new
  model-selection pass. New deterministic calculations stay with parent tools even when a child is already available. For a new capability with no suitable current child, perform one bounded registry lookup. A retained
  role is reused when it is loaded in the current session, belongs to the same capability family, and is quality-compatible.
  Read only that retained role before generic or runtime fallback. A registry-wide lookup failure does not discard an
  already-loaded candidate that clearly meets those three conditions; read that candidate once and reuse it if the
  selected-role read succeeds. Reuse an unchanged lookup result instead
  of querying again. If both a current child and a retained child meet the quality bar, choose the lower combined
  parent-child cost by default; continued parallel speedup instead dispatches independent ready slices without serializing them for reuse. Do not switch threads merely to improve a reuse statistic.
- **Conditional runtime copies.** Use isolated copies for separate ready slices in one capability family, and use
  configuration variants only when comparable evidence can answer a real routing question.
- **Explicit native configuration.** Every `spawn_agent` supplies `fork_turns="none"`. Runtime roles also supply the actual model and reasoning effort; fixed retained roles use their loaded configuration and omit unsupported overrides. Verify the actual configuration in the task card.
- **Small task cards.** New children receive five verified opening lines, the instruction to display them in
  the first progress note and repeat all five in the final, one complete work package tied to an active outcome or dependency, needed evidence, ownership,
  success conditions, and stop conditions. Retained experience stays in the loaded role instructions. A reused
  live child without verified retained recall says only `经验：复用当前线程上下文`; a new runtime role says
  `经验：本次任务上下文`; unverified persistence placeholders are forbidden.
- **Controlled registry growth.** A runtime role is selectively retained when the same kind of task is genuinely
  expected again, expected reuse benefit exceeds maintenance and lookup burden, and no compatible family exists.
  Existing families are reused or CAS-reconfigured. There is no fixed retention rate or quota.
- **Honest metrics.** `retained-spawn share`, opportunity reuse, and qualified retention are observations, not targets.
  They have no fixed percentage. Never create calls, over-retain roles, or duplicate identities to improve a number.
  A low retained-spawn share cannot establish a missed reuse opportunity.

A new child uses `gpt-6.1-terra`, `gpt-6.2-sol`, or `gpt-6.2-astra` according to task needs, with reasoning effort from `medium` upward.
The first two are ordinary subagent routes; only `gpt-6.2-astra` is the expert route.
`gpt-6.1-terra` handles simple, speed-prioritized work with clear inputs, low risk, and direct acceptance checks:
bounded reading, structured extraction, factual summaries, text revision, and small local edits.
Use `medium` normally and `high` for limited local ambiguity. Complex trade-offs, cross-module causality,
compliance or safety judgments, high-risk changes, and final review conclusions use a suitable Sol or higher.
Historical profiles remain readable. Old Sol/Astra requests normalize to their 6.2 replacements before creating or CAS-reconfiguring the same family.
For Computer Use, the parent directs and verifies while GPT-6.1 Terra handles routine low-risk UI operations, including
read-only observation. Complex UI state, difficult dependencies, or high-risk changes use GPT-6.2 Sol or higher. Complex business decisions stay with the parent or a suitable Sol/Astra. One operator owns a shared
desktop, window, or tab; direct tool access and permissions must be valid in the executing child.
Read `$lean-stack` before the first Computer Use operation, including an application listing or UI tree query.
When the user has not specified an expert, Astra is selected only when the strongest suitable `gpt-6.2-sol` option still has a decision-changing quality gap. An explicit expert assignment takes priority.
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

Existing-file updates retain the actual displaced object and return `previous_path`. A late external edit produces
an explicit publication conflict with its recovery location, and interrupted instruction updates require recovery
before another activation. See the [maintenance and recovery contract](skills/lean-stack/references/versioning.md).
Current native recovery paths are verified on local Windows NTFS and Linux filesystems; unsupported capture
operations fail without falling back to an overwrite. Normal plugin installation still leaves global instructions alone.

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
总成本可接受时可增派子代理提速。三项无需每次同时获益。

默认三原则没有固定人数；首派、新输入就绪、依赖解除或容量释放时，对未分配的独立工作一次快判并及时增派，不冻结首批队伍。[用户特殊安排](skills/lean-stack/SKILL.md#用户要求持续并行提速)分别生效：多开或不限数量不等于不计成本或顶满；明确不计成本才放宽成本比较，明确高负载持续顶满才要求占满真实可用容量。任务交付或对应安排撤回后退出该项；安全、权限、依赖和写入边界继续适用。

决定委派后按当前优先级选择：

1. 同一任务、澄清、纠错或紧密相关的小补充，直接继续使用质量和边界兼容的当前子代理；
2. 新的能力类型没有适合继续使用的当前子代理时，只做一次快速、有界台账查询；当前会话已经
   加载、属于同一能力族且质量兼容的保留子代理会被复用；只读取选中的保留子代理一次。目录查询
   失败但当前会话已加载类型中已有符合三项条件的明确候选时，仍只读取该候选一次；读取成功就复用。
   只有没有可核对候选或读取失败时，本次才新建运行时子代理；查询失败不得当成空台账建档；
3. 查询结果和候选条件未变化时复用本轮结果，不重复查；当前子代理与保留子代理都可用时，在质量
   达标后默认比较父子合计总成本，选更低成本的一条；默认也按进度派发有收益的独立就绪切片，不为复用串行排队；成本优先级按用户对成本的明确要求。不为统计台账复用强制换线程。

同一能力族有多个独立已就绪切片时，可以按各自任务卡创建运行时复制；只有存在真实选配疑问并
且结果可比较时才形成配置变体。两者都只属于当前运行；比较、采用和未来保留仍走原有权威分支。

新调用按任务分工选 `gpt-6.1-terra`、`gpt-6.2-sol`、`gpt-6.2-astra`，思考程度从 `medium` 起。Terra 承担输入清楚、风险低且验收直接的速度优先简单工作：有界读取、结构化提取、事实总结、文字整理和局部小修改；通常 `medium`，有限局部歧义可用 `high`。复杂取舍、跨模块因果、合规或安全判断、高风险修改及最终审查结论至少使用合适的 Sol。用户未明确指定专家时，Astra 仅在最强可行 `gpt-6.2-sol` 仍有决定性质量差距时使用。历史资料保持可读，旧 Sol/Astra 请求自动规范化为对应 6.2 后继续新建或显式重配；兼容身份按 CAS 重配并由新任务验证宿主加载，旧会话的固定 Luna 配置不能冒充 Terra。

Computer Use 由父代理指导：常规、输入清楚、低风险操作默认 GPT-6.1 Terra，包括只读界面观察；复杂界面状态、难判断的多步依赖或高风险变更至少用 GPT-6.2 Sol。父代理负责目标、授权范围、阶段指导与验收，复杂业务判断仍交给合适的 Sol/Astra；执行者依据当前界面执行并反馈。同一桌面、窗口或标签页保持一个操作者，工具须在子代理中真实可用，委派不扩权。详细合同见[父代理指导、按任务选配](skills/lean-stack/SKILL.md#computer-use父代理指导按任务选配)。
前两档都是常规子代理路线；只有 `gpt-6.2-astra` 是专家路线。
模型和思考程度分别按任务选择。Astra 可以使用 `medium`、`high`、`xhigh`，不能每次固定
为 `xhigh`。每次 `spawn_agent` 显式传入 `fork_turns="none"`；运行时角色另传真实模型和思考程度，固定保留角色沿用已加载配置并省略宿主禁止的覆盖参数。用户明确指定专家时优先落实，未指定部分才按默认质量差距选配。

6.2 的任务卡与结果采用按[调用防错](skills/lean-stack/references/dispatch-start.md#62-调用防错)核对关键要求、完成条件与证据，减少例行停等，分别验收审查发现和视觉细节，如实报告阻断，无新增证据时停止原样循环；这降低风险，不保证零错误。专属附加指令只对实际 6.2 型号生效，随最后一款 6.2 退出同步清理入口、任务卡、结果采用与提示，不自动继承给后继型号；通用证据和安全要求保留，详见[型号更新与专属纠错退出](skills/lean-stack/references/versioning.md#型号更新与专属纠错退出)。旧 Sol/Astra 资料仍可读取并按 CAS 迁至 6.2，已加载旧角色须在新任务核验实际型号。

新子代理任务卡写五行真实配置与状态，名称后按实际派发标一次“（复用）”或“（新建）”，并把
通用任务卡的完整执行身份句，以及“首条用户可见进展说明展示五行、最终回复顶部完整展示五行”的执行句直接交给子代理，再写唯一
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
