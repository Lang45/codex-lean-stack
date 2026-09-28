# Codex Lean Stack

**Focused task execution and model-aware subagent delegation for Codex.**

Current version: **7.4.0**

Delegation follows three priorities: protect quality on high-value work, prefer lower total cost
when ordinary options are equally reliable, and add parallel help for speed when the total cost is
acceptable. A compatible loaded `lean_*` retained type is recalled and used before generic or runtime roles;
after an adopted runtime result, every independently reusable new capability family that passes the retention
criteria must make one safe `ensure` attempt.

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
- **Tools first.** Deterministic work goes directly to tools.
- **Reuse one capability family.** Continue a compatible live child when its context remains useful; otherwise a
  compatible loaded `lean_*` `agent_type` must be recalled and used before generic `explorer`/`worker`/default or
  a runtime role. Runtime fallback records the concrete incompatibility.
- **Conditional runtime copies.** Use isolated copies for separate ready slices in one capability family, and use
  configuration variants only when comparable evidence can answer a real routing question.
- **Explicit native configuration.** Every `spawn_agent` supplies the actual model, reasoning effort, and bounded
  history. A task card or retained profile does not replace native parameters.
- **Small task cards.** New children receive five verified opening lines, the instruction to display them in
  the first progress note and repeat the first three in the final, one goal, needed evidence, ownership,
  success conditions, and stop conditions. Retained experience stays in the loaded role instructions. A reused
  live child without verified retained recall says only `经验：复用当前线程上下文`; a new runtime role says
  `经验：本次任务上下文`; unverified persistence placeholders are forbidden.
- **Controlled registry growth.** An adopted runtime result is evaluated once. If it has a stable
  cross-task role, safely describable authority and evidence boundaries, and no compatible family, one `ensure`
  attempt is mandatory; otherwise the concrete exclusion is recorded. Existing families are reused or
  CAS-reconfigured; one-off, duplicate, and project-bound roles are not retained. The local registry does not launch
  agents or keep live threads running.
- **Honest metrics.** `retained-spawn share` is descriptive only. Opportunity reuse and qualified retention each use
  their own evidence-backed denominators and target 100%; ensure attempts and persistence successes are reported
  separately. Every necessary spawn has a candidate assessment; unverified opportunities remain unknown rather than
  disappearing from the denominator. Qualified retention is deduplicated by capability family, and reuse or CAS
  reconfiguration is not a newly created identity. A low retained-spawn share cannot establish a missed reuse opportunity.

A new child uses `gpt-5.6-luna`, `gpt-6-sol`, `gpt-5.6-sol`, or `gpt-6-astra`, in that order of capability, with reasoning effort from `medium` upward.
The first three are ordinary subagent routes; only `gpt-6-astra` is the expert route.
`gpt-5.6-luna` is limited to bounded reading, structured extraction, and factual summaries. Recommendations,
trade-offs, compliance judgments, review conclusions, and other sustained judgment use a suitable Sol or higher.
Astra is selected only when the strongest suitable `gpt-5.6-sol` option still has a decision-changing quality gap.
Its reasoning effort is chosen per task from `medium`, `high`, or `xhigh`; `xhigh` is the upper bound,
not the default.
Every new `followup_task` slice first reselects the minimum sufficient capability from current quality, marginal total
cost, and time. If Astra is still required, a separate second decision chooses the old Astra thread or another
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

1. 同一能力族、实际模型和思考程度合规、权限和证据边界兼容，且上下文仍有价值的 live child；
2. 当前原生工具目录中职责、输入、交付、权限、模型能力、安全与证据边界兼容的具名保留
   `lean_*` `agent_type`；兼容时必须定向召回并真实调用；
3. 没有兼容保留类型时，写明具体不兼容点后再选 generic 或满足当前切片的最小运行时子代理。

同一能力族有多个独立已就绪切片时，可以按各自任务卡创建运行时复制；只有存在真实选配疑问并
且结果可比较时才形成配置变体。两者都只属于当前运行；比较、采用和未来保留仍走原有权威分支。

新调用按能力顺序选 `gpt-5.6-luna`、`gpt-6-sol`、`gpt-5.6-sol`、`gpt-6-astra`，思考程度从 `medium` 起。Luna 只做有界读取、结构化提取和事实总结；建议、取舍、合规判断、审查结论及其他持续判断至少使用合适的 Sol。Astra 仅在最强可行 `gpt-5.6-sol` 仍有决定性质量差距时使用。旧保留类型配置不合规时，本次调用可用运行时角色；兼容身份需更新时才按 CAS 重配，新任务验证宿主加载。
前三档都是常规子代理路线；只有 `gpt-6-astra` 是专家路线。
模型和思考程度分别按任务选择。Astra 可以使用 `medium`、`high`、`xhigh`，不能每次固定
为 `xhigh`。每次 `spawn_agent` 都显式传入真实模型、思考程度和非全量历史。

新子代理任务卡写五行真实配置与状态，名称后按实际派发标一次“（复用）”或“（新建）”，并把
“首条用户可见进展说明展示五行、最终回复顶部重复前三行”的执行句直接交给子代理，再写唯一
目标、必要来源、权限或写入所有权、成功条件和停止
条件。选中已加载保留类型后，只对该身份召回一次；保留经验已在角色指令中，任务卡只传五行
状态，子代理读完经验便开始任务。召回失败
就改派运行时子代理，后两行写 0 轮和“经验：本次任务上下文”。每次调用不触发成本核对，健康台账保存
新经验也不等待旧摘要纠错或版本维护；写入失败由父代理保留具名事项并在主任务推进后修复。
复用当前子代理但没有已核验的保留召回状态时，经验行只写“经验：复用当前线程上下文”，不得
显示“未核验持久化经验”或其他占位语。

每个新的 `followup_task` 增量切片都按当前最小能力重新比较质量、总边际成本和时间；历史使用
Astra 不锁定未来模型。若当前质量仍需 Astra，再独立决定续用旧线程或改派兼容 Astra；旧线程
上下文无边际价值只决定停止旧线程，不能据此降到 Sol/Luna。已完成且采用、验收满足的 Astra
无新增依据时停止。

子代理完成后，父代理核验结果并继续主任务。运行时新角色首次被采用后逐项收口；稳定、具备明确
跨任务价值、权限和证据边界可安全描述且台账无兼容能力族时，必须尝试一次 `ensure`。同族已存在
就复用或按 CAS 重配，一次性、重复和项目绑定角色不保留，并记录具体排除原因。
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
