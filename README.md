# Codex Lean Stack

**Focused task execution and model-aware subagent delegation for Codex.**

Current version: **7.0.1**

This patch restores the five-line opening for subagents: name, model, reasoning effort, retained
success count, and experience status. A reused retained type receives its verified single-role
status; if that read fails, a runtime subagent continues with truthful runtime values. On Windows,
managed role file changes now keep handles to the checked file and its parent directories through
replacement or deletion, preventing an external process from swapping the checked path in between.

Codex Lean Stack provides two independent skills:

| Skill | Purpose |
| --- | --- |
| [`$lean-simplify`](skills/lean-simplify/SKILL.md) | Find the smallest complete path through the main task and match verification to the affected behavior. |
| [`$lean-stack`](skills/lean-stack/SKILL.md) | Delegate useful independent work, choose a model and reasoning effort, and reuse compatible subagents. |

Either skill can be used alone. Both preserve the requested result, permission boundaries, data integrity, and the
evidence required to support a conclusion.

## How delegation works

- **Quality, cost, then time.** A delegated slice must meet the required quality, use a proportionate model and
  reasoning effort, and help the parent task finish sooner.
- **Tools first.** Deterministic work goes directly to tools.
- **Reuse one capability family.** Continue a compatible live child with a supported actual configuration when its context remains useful; otherwise use
  a compatible loaded `agent_type`; create a runtime role when neither fits.
- **Conditional runtime copies.** Use isolated copies for separate ready slices in one capability family, and use
  configuration variants only when comparable evidence can answer a real routing question.
- **Explicit native configuration.** Every `spawn_agent` supplies the actual model, reasoning effort, and bounded
  history. A task card or retained profile does not replace native parameters.
- **Small task cards.** New children receive their visible name, actual model, actual reasoning effort, the
  instruction to show those values in their first progress note and final, one goal, the needed evidence,
  ownership, success conditions, and stop conditions.
- **Optional retention.** Profiles and experience are recorded only when a result is reusable across tasks. The
  local registry does not launch agents or keep live threads running.

A new child uses `gpt-6-luna`, `gpt-6-sol`, or `gpt-6-astra`, with reasoning effort from `medium` upward.
Astra is selected only when the strongest suitable `gpt-6-sol` option still has a decision-changing quality gap.
Its reasoning effort is chosen per task from `medium`, `high`, or `xhigh`; `xhigh` is the upper bound,
not the default.

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
Use $lean-stack to delegate independent work where it improves completion time, reusing the same capability family when possible.
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

确定性工作直接用工具。需要持续模型判断时，按质量、成本、时间决定是否委派。决定委派后依次
选择：

1. 同一能力族、实际模型和思考程度合规、权限和证据边界兼容，且上下文仍有价值的 live child；
2. 当前原生工具目录中配置兼容的 `agent_type`；
3. 满足当前切片的最小运行时子代理。

同一能力族有多个独立已就绪切片时，可以按各自任务卡创建运行时复制；只有存在真实选配疑问并
且结果可比较时才形成配置变体。两者都只属于当前运行；比较、采用和未来保留仍走原有权威分支。

新调用只选 `gpt-6-luna`、`gpt-6-sol`、`gpt-6-astra`，思考程度从 `medium` 起。旧保留类型配置不合规时，本次调用可用运行时角色；确需跨任务复用时才按 CAS 重配，新任务验证宿主加载。
模型和思考程度分别按任务选择。Astra 可以使用 `medium`、`high`、`xhigh`，不能每次固定
为 `xhigh`。每次 `spawn_agent` 都显式传入真实模型、思考程度和非全量历史。

新子代理任务卡写五行真实配置与状态，名称后按实际派发标一次“（复用）”或“（新建）”，并把
“首条用户可见进展说明展示五行、最终回复顶部重复前三行”的执行句直接交给子代理，再写唯一
目标、必要来源、权限或写入所有权、成功条件和停止
条件。选中已加载保留类型后，只对该身份召回一次，子代理读完已有经验便开始任务；召回失败
就改派运行时子代理，后两行写 0 轮和未加载保留经验。每次调用不触发成本核对，健康台账保存
新经验也不等待旧摘要纠错或版本维护；写入失败由父代理保留具名事项并在主任务推进后修复。

子代理完成后，父代理核验结果并继续主任务。只有形成跨任务可复用能力或经验时才按需记录保留
身份和完成收据；普通调用不进入额外的角色维护流程。

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
