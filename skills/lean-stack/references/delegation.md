# Native Codex delegation

Use this reference only after the delegation gate in `SKILL.md` passes. This
skill instruction is an explicit trigger for Codex's native subagent workflow;
it does not require a custom agent runtime, a hook, or an external orchestrator.

## Gate

Delegate only when all are true:

1. The task is non-trivial and has at least one bounded exploration,
   documentation, test, analysis, or review slice with a clear done predicate.
2. That slice is large enough to repay startup and synthesis overhead and can
   proceed while the parent does different useful work, or can provide genuinely
   independent verification of the parent's result.
3. The work can use separate outputs, or one agent remains the sole writer.
4. The parent can verify the returned evidence without replaying all raw work.

Good first uses are codebase mapping, documentation checks, log or test analysis,
independent review axes, and tests that can run without competing for the same
state. For a typical non-trivial change, one read-only explorer or reviewer is
enough to satisfy the eager gate while the parent owns implementation. Avoid
delegation for a one-function edit, a single linear debugging chain with no
independent check, or several agents writing the same files.

## Shape

- After the gate passes, default to one subagent and use two or three only for
  genuinely distinct workstreams. Respect the runtime limit and never create
  more agents than useful, non-overlapping slices.
- Prefer read-only exploration and review agents. Keep one implementation owner
  unless writable targets are disjoint by construction.
- When the host exposes specialized roles, use an explorer for read-heavy work
  and a worker for bounded implementation. Otherwise state the role in the brief.
- Do not allow recursive delegation unless the parent assigns a real orchestration
  subproblem with its own bounded fan-out.

## Critical-path parallelism

Subagents must overlap useful work instead of turning parallelism into a serial
queue. Before spawning, estimate:

```text
parallel_time = startup + max(parent_slice, child_slice) + merge
serial_time   = parent_slice + child_slice
```

Delegate only when `parallel_time` is plausibly lower, or when independent
evidence is worth the bounded delay. Then follow these rules:

1. Spawn as soon as the child's inputs are stable, and immediately continue the
   parent-owned slice that does not depend on the child. Do not call `wait`
   directly after spawning merely because the child exists.
2. Name the merge point in advance. Wait only when the parent reaches that point
   and the result is genuinely needed for integration or the final claim.
3. Prefer one result-ready notification or one bounded wait at the merge point;
   do not repeatedly poll unchanged status. Keep child output compact so result
   transfer and synthesis do not erase the parallel gain.
4. If a non-essential child is late, continue with available evidence and mark
   it dropped. If an essential child is late, send one narrow finish-now request;
   if it still misses the budget, interrupt it and report the verification gap.
5. Never spawn a child whose result is the only possible next step while the
   parent has no independent work. That is a sequential call with agent startup
   overhead and should stay in the parent.

## Model and reasoning requests

Select the role before spawning. Every subagent prompt must explicitly request a
model and reasoning effort. When the spawn tool exposes `model` and
`reasoning_effort` fields, pass the same pair there; the prose request is not a
substitute for supported tool parameters.

An explicit user choice or applicable project instruction overrides this table.
Otherwise use these defaults:

| Role | Requested model | Requested effort | Use |
|---|---|---|---|
| Codebase explorer | `gpt-5.6-terra` | `medium` | Read-heavy mapping, large-file scans, call graphs |
| Integration or test reviewer | `gpt-5.6-terra` | `high` | Cross-boundary behavior, tests, edge cases |
| Documentation verifier | `gpt-5.6-luna` | `medium` | Narrow source checks and supporting documents |
| Mechanical worker | `gpt-5.6-luna` | `low` | Clear repetitive checks, generated lists, simple isolated edits |
| Implementation worker | `gpt-5.6-sol` | `high` | Bounded feature or root-cause fix after the design is settled |
| Architect or critical reviewer | `gpt-5.6-sol` | `xhigh` | Ambiguous design, security, concurrency, data-loss, adversarial review |

Reserve `max` for the hardest quality-first architecture, security, or migration
work when the selected model supports it and the expected gain justifies the
extra time and tokens. Do not request `max` or `ultra` routinely.

## Speed and adaptive route requests

Treat model, reasoning effort, and service tier as independent axes. Fast mode
does not make a model more capable; it trades higher credits or API price for
lower service latency. Current OpenAI guidance describes roughly 1.5x speed and,
for GPT-5.6 in ChatGPT-credit mode, 2.5x Standard credit consumption. Recheck the
official Speed page before publishing fixed pricing claims.

Use these speed-biased, bounded-cost defaults:

- High-cost model/effort combinations stay on Standard.
- Three high-quality slow runs can propose Fast for low- or medium-cost
  combinations when the user accepts some extra cost.
- A single low score or slow run never changes any axis.
- Change one axis per shadow comparison so the cause remains identifiable.
- A named custom-agent file that pins model or effort cannot be tested with a
  conflicting spawn override; use an explicit-role fallback or the incumbent.
- If the current spawn schema omits `service_tier`, Fast is recommendation-only.
  Never toggle `/fast`, edit global `config.toml`, or claim an effective tier on
  the user's behalf.

For a managed agent with comparable evaluation history, run the lifecycle
`recommend-route` command before briefing the next task. A `watch` or `hold`
result preserves the incumbent. A model or reasoning proposal requests two
focused shadow cases. A service-tier proposal needs no duplicate quality run
because Fast does not change the model; it still requires a current host
capability check, cost notice, and user confirmation. No proposal edits the
managed TOML.

Include this block in every brief, localized to the user's language:

```text
User-visible agent name: <localized role name>
Requested model: <exact model>
Requested reasoning effort: <exact effort>
Role: <bounded role>
```

Use a concise localized role name in conversation, progress, and the final
report. If the spawn API restricts its internal `task_name` to ASCII slugs, use a
stable technical slug there and keep the localized name in the brief; never
claim that the host UI itself accepted a localized identifier when it did not.

If the exact pair is rejected or unavailable, retry at most once with the
closest supported model in the same GPT-5.6 family and a supported effort that
preserves the role's quality floor. Do not reduce a critical reviewer below
`high`. Report the fallback to the user. If only parent inheritance is possible,
state that limitation before treating the child result as equivalent.

## Startup disclosure

Require each subagent's first progress update to begin with:

- `子代理名称`: the user-visible role name localized to the user's current
  language.
- `请求模型`: the exact model requested in the brief and spawn call.
- `请求推理强度`: the exact requested reasoning-effort value.
- `生效模型`: the actual model identifier exposed by the spawn result, runtime,
  or agent metadata.
- `生效推理强度`: the actual reasoning-effort value exposed by the same source.

When a service tier was explicitly requested or recommended, also require
`请求速度档位` and `生效速度档位`. Use `Standard`/`Fast` for the user-facing
mode and retain raw values such as `priority` when the runtime exposes them.
Unexposed values follow the same no-guessing rule.

Localize these labels to the user's current language. If a value is not exposed,
the agent must say `未暴露（已请求 <value>）` or the equivalent in that language.
If the spawn actually fell back to parent inheritance, say so explicitly. Never
infer an effective model or effort from writing style, capability, a generic
identity prompt, or a configured default that was not confirmed for the child.

## Brief every agent

Give each subagent a self-contained brief with:

- Goal and exact slice.
- Read and write boundaries, including named paths when known.
- Relevant constraints and authority limits.
- Evidence to collect or checks to run.
- A done predicate, time budget, and stopping condition.
- The user's current response language. Require the entire report in that
  language unless the user explicitly requests another one; code, paths,
  identifiers, quoted source text, and raw errors may stay in their original form.
- The role-specific requested model and reasoning effort, repeated exactly from
  the spawn call.
- A compact return shape: `AGENT_NAME`, `REQUESTED_MODEL`, `REQUESTED_REASONING`,
  `EFFECTIVE_MODEL`, `EFFECTIVE_REASONING`, `STATUS`, `SCOPE`, `EVIDENCE`,
  `FINDINGS`, `GAPS`.

Pass file pointers instead of copying large payloads into every brief. If agents
must write, give them naturally disjoint files or separate worktrees. A branch
isolates writes only when it has its own worktree. Shared writes are serialized
under one owner.

## Parent responsibilities

The parent owns requirements, architecture, integration, and the final claim.
At the named merge point, collect every still-required slice, note dropouts,
deduplicate findings, inspect any diff, and rerun the decisive check. Agreement
raises confidence but does not turn an unsupported claim into evidence. Stop
fan-out once the required coverage is complete.

Do not wait indefinitely. If a child exceeds its stated budget or stops making
progress, steer it once with a narrow finish-now request. If it still does not
return, interrupt it, mark that slice `DROPPED`, and finish with the available
evidence. A non-essential slice must never block the parent handoff; a missing
essential slice becomes an explicit verification gap rather than a fabricated
pass.

Subagents inherit the current permission boundary. A child that needs new
authority returns `BLOCKED` instead of broadening scope.

Current behavior and role guidance are documented in [Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=app).
