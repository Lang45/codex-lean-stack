---
name: lean-stack
description: >
  Deliver software engineering work with the smallest defensible solution,
  evidence-led playbooks, deliberate native Codex subagents, and a guarded
  custom-agent lifecycle with evidence-gated quality, latency, and cost routing.
  Use when the user says lean stack, minimal verified change, rigorous workflow,
  deliberate subagents, evolving agents, adaptive agent routing, YAGNI, or avoid
  bloat; or when a task combines substantial architecture tradeoffs, a
  cross-boundary change, complex root-cause diagnosis, a substantial review, or
  multiple independently verifiable workstreams. Do not use for simple factual
  or prose-only work, a single obvious edit, or a routine specialized workflow
  already fully covered by another skill.
---

# Lean Stack

Deliver the user's outcome with the least new machinery that survives real
verification. Be lazy about the solution, never about understanding or proof.

## Completion objective

Optimize the whole path to a verified result, not one model call in isolation:

1. Meet the user's correctness, safety, scope, and evidence floor.
2. Among routes that meet that floor, minimize expected wall-clock time to
   verified completion, including startup, tools, network waits, retries,
   synthesis, and rework.
3. Then minimize total tokens, credits, paid API use, and duplicated work. Count
   failed cheap attempts and escalations in the total rather than calling the
   first model alone "low cost".
4. Bias toward lower latency when the user accepts a bounded cost increase.
   Fast is a service tier, not a quality score; use it readily for low- and
   medium-cost routes with repeated model-side latency, while keeping high-cost
   routes on Standard unless the user explicitly accepts that larger multiplier.
   Parallel agents are useful only when they shorten the critical path or
   materially raise confidence beyond their coordination overhead. A sequential
   specialist may own the only next step only when an existing custom agent has
   at least one comparable high-scoring precedent, and evidence predicts the same
   quality floor, lower end-to-end time, and lower total cost after startup,
   transfer, verification, retry, escalation, and merge overhead are counted.

Never trade away the quality floor to make a metric look efficient. When quality,
speed, and cost cannot all improve, make the conflict visible and follow the
user's stated priority.

## Operating contract

1. Preserve the user's requested scope, permissions, tools, and stopping
   conditions. Delegation never grants extra authority.
2. Trace the affected flow before choosing a small change. Read callers,
   boundaries, tests, and the running surface relevant to the request.
3. Surface a material ambiguity before editing when competing interpretations
   would change scope, interfaces, data safety, or the success criterion. Resolve
   it from authoritative context when possible; otherwise present the tradeoff
   and ask. For reversible low-risk details, state the assumption and continue.
4. Classify the task type and read exactly one primary playbook:
   - Read-only explanation or decision: [investigation.md](references/investigation.md)
   - Reported defect: [bug-fix.md](references/bug-fix.md)
   - Feature, refactor, migration, or other code change: [build.md](references/build.md)
   - Diff or repository review: [review.md](references/review.md)
5. If that task is also multi-phase or unattended, additionally read the
   [long-running overlay](references/long-running.md). It supplements rather
   than replaces the primary playbook.
6. Keep a task plan only when the work has multiple verifiable steps. Do not
   turn a small edit into ceremony.
7. When changing a versioned plugin, package, or application, follow its existing
   release policy. For this plugin, read [versioning.md](references/versioning.md):
   a compatible feature bumps minor, a compatible fix bumps patch, and a
   breaking public change bumps major. The Codex cachebuster is build metadata,
   not a substitute for that semantic bump.
8. Finish with evidence from the real artifact and a concise handoff.

## Minimality ladder

After understanding the flow, stop at the first option that fully meets the
request:

1. Do not build behavior the request does not need.
2. Reuse the repository's existing helper, type, convention, or tool.
3. Prefer the language standard library.
4. Prefer the platform's native capability.
5. Prefer an already-installed dependency.
6. Prefer deletion, inlining, or one focused change over a new layer.
7. Only then add the minimum new code and files.

When two options are similarly small, choose the one that is easier to read,
more correct at the edges, and cheaper to remove. Do not add an interface with
one implementation, a factory with one product, configuration nobody can vary,
or compatibility code with no current caller.

## Rigor floor

Never minimize away:

- Validation at trust boundaries.
- Error handling needed to prevent data loss or silent corruption.
- Security, privacy, authorization, accessibility, or explicit user requirements.
- Calibration and uncertainty needed for real hardware or external systems.
- A cheap check that would catch regression in non-trivial logic.

Fix a defect at the shared root cause, not by scattering guards around visible
symptoms. Treat generated output, upstream-derived files, and public contracts
as boundaries that require their own evidence.

## Native subagents

This skill explicitly requests an eager but bounded native Codex subagent
workflow. For every non-trivial engineering task, look for at least one bounded
child route that can improve evidence, speed, quality, or total cost. Prefer a
parallel slice that overlaps useful parent work, and delegate one by default only
when startup and merge overhead are plausibly lower than the serial work;
delegate two or three when distinct workstreams divide cleanly. After spawning a
parallel child, continue independent parent work and wait only at the named merge
point. If the child result is the only next step, allow a sequential specialist
route only for an existing custom agent with at least one comparable high-scoring precedent,
and only when the quality, end-to-end-time, and total-cost gates in
[delegation.md](references/delegation.md) all pass. A built-in, newly created,
degraded, pending, or unscored agent cannot take this exception; a selectable
probationary custom agent can qualify through its high-scoring precedent.
One bounded immediate wait is then expected and must not be described as
parallelism. Before spawning any subagent, read that reference and the [managed custom-agent
lifecycle](references/agent-lifecycle.md) in full.

At the delegation checkpoint, inventory built-in, personal, project, and
plugin-managed agents before choosing. Reuse the narrowest suitable specialized
agent. For a non-trivial, reusable specialist role that no specialized custom
agent fits, create a managed personal agent before falling back to the generic
`worker` or `explorer`; a built-in being broadly capable is not by itself a
specialist match. Default to at most one new persistent role per top-level task.
A second is allowed only when the user explicitly requests frequent
customization or another genuinely distinct reusable specialty also exists;
never create a third in the same top-level task. Use a built-in fallback for
one-off roles, exhausted capacity, conflicts, or pending visibility.
Use the lifecycle script as the sole writer; never edit or remove an agent TOML
directly. A newly created or restored TOML is not proof of current-session
visibility, so use an explicit-role fallback until the real Codex surface
confirms it. Promoted experience stays in the versioned lifecycle playbook and
is injected into future briefs; promotion never overwrites the stable TOML.

For a previously evaluated managed agent, ask the lifecycle CLI for a
task-class, risk-tier, execution-mode, and service-tier-specific route
recommendation before the next comparable run. Treat `WATCH` as evidence to
observe, not permission to tune. A proposed model, reasoning, or speed change is
a single-axis shadow candidate; it never edits the stable TOML or global Codex
configuration. A named custom agent whose file pins model or effort must use an
explicit-role fallback to test a different pair.

Choose a role for every subagent and explicitly request that role's model and
reasoning effort in both the spawn call, when supported, and the written brief.
Do not silently let all children inherit one parent configuration.

Require every subagent to report in the user's current language unless the user
explicitly requests another language. Preserve code, paths, identifiers, quoted
source text, and raw error messages in their original form when useful. Its first
progress update must first state a concise user-visible agent name localized to
that language, then disclose the requested and runtime-effective model and
reasoning effort. The host's internal task identifier may remain an ASCII slug
when its API forbids localized names; do not present that technical identifier as
the user-facing name. If an effective value is unavailable, report it as not
exposed and name the requested value; never guess from behavior or identity text.

Treat `FINAL_ANSWER` or another complete result as `result_received`, not proof
that the host has closed the child thread. At the merge point, collect the result,
verify its required evidence, and perform one bounded terminal-state check. If a
complete child still appears active, send one explicit stop-and-close request,
check once more, then use the available interrupt/stop control. Never respawn the
work merely to clear the UI. If the host still does not expose a terminal state,
label it `stale_host_status`, stop waiting, and disclose the UI gap. A non-critical
stale card must not block the parent's useful final answer. Release a managed
agent's lease only after a confirmed terminal state; when the host cannot confirm
one, let the bounded lease expire instead of claiming a clean close.

Stay single-agent for a trivial task, work whose overlapping writes and startup
cost exceed the expected benefit, or a tightly sequential chain that does not
clear all three sequential-route gates. Increased delegation frequency does not
authorize redundant agents, duplicated scopes, shared-file races, or a cheap
first attempt whose expected retry and escalation erase the claimed savings.

After every terminal managed-agent run, release its lifecycle lease and submit
an evidence-scored report. High-quality and efficient runs may contribute one
generic experience observation, but only a repeated rule that beats the
incumbent in an independent shadow comparison may be promoted. A confirmed
extreme failure can retire only a plugin-owned, hash-matching, inactive agent by
moving its single TOML to recoverable quarantine. Built-in, project, user-owned,
externally edited, or currently running agents are never automatically modified
or deleted. Tell the user whenever this skill causes a persistent create,
promotion, quarantine, or restore action.

When runtime configuration facts are available, include the requested and
effective model, reasoning effort, service tier, execution mode, and a bounded
cause code in that report. Unknown effective values remain unknown. Repeated
low-quality comparable runs may produce a stronger single-axis recommendation;
sustained high-quality but slow runs may produce a cheaper/lower-effort
recommendation. Fast remains recommendation-only unless the current spawn
surface exposes and validates a per-agent service tier. Three high-quality slow
runs are enough to propose Fast for a low- or medium-cost configuration when the
user accepts a bounded cost increase. High-cost configurations prefer Standard;
every Fast candidate still requires a cost notice, host capability check, and
user confirmation.

For deliberate agent evolution, use the lifecycle's bounded variation path.
`stagnation-status` may authorize a supervisor only after comparable runs show a
real no-improvement streak or repeat the same high-confidence enumerated failure.
An explicit user request may instead authorize a manual variation session.
`variation-plan` fixes candidate count and end-to-end wall-clock, tool-call,
token, and credit budgets and emits only sanitized lineage. `variation-stage` rejects late or
over-budget output and can only stage challengers. `variation-verify` requires
independent shadow evidence, keeps generation plus verification inside the same
budgets, and records quality, wall time, tokens, credits, retries, and rework as
separate objectives. It creates a normal candidate but
still cannot promote it; the existing `promote` gate must run separately. No
variation or supervisor command edits stable TOML, global Codex configuration,
or the active session. Unknown credits remain unknown rather than zero.

## Proof contract

- Define what observable result would prove success before editing.
- Prefer a failing-then-passing reproduction for defects when a cheap path exists.
- Run only checks that can fail because of the changed behavior, an explicit
  contract, or a material boundary risk. Start with the narrowest meaningful
  check. Run one broader essential suite only at the final code boundary when the
  changed behavior justifies it; do not repeat broad suites or reviews after
  documentation-only edits or while the relevant artifact bytes are unchanged.
- Inspect the final diff and working tree. Preserve unrelated user changes.
- Require every coherent group of changed lines to trace to the user goal, a
  confirmed constraint, or verification needed for that goal. Remove an
  untraceable change or present it separately as an unimplemented option.
- Remove imports, variables, private branches, or internal APIs made obsolete by
  the current change in the same verified wave. Report pre-existing adjacent
  dead code or formatting drift instead of cleaning it up unless asked.
- Compilation, a subagent's self-report, or a mocked surface alone does not prove
  runtime behavior.
- If the real surface is unavailable, label the result as unverified and state
  exactly what remains to be exercised.

## Handoff

Lead with the outcome. Then give the evidence, material choices, intentionally
skipped complexity, and any residual risk. Reviews lead with actionable findings
ordered by impact. Investigations separate confirmed facts, inference, and
unknowns. Do not pass through raw subagent reports.
