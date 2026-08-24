---
name: lean-stack
description: >
  Deliver software engineering work with the smallest defensible solution,
  evidence-led playbooks, deliberate native Codex subagents, and a guarded
  custom-agent lifecycle. Use when the user says lean stack, minimal verified
  change, rigorous workflow, deliberate subagents, evolving agents, YAGNI, or
  avoid bloat; or when a task combines substantial architecture tradeoffs, a
  cross-boundary change, complex root-cause diagnosis, a substantial review, or
  multiple independently verifiable workstreams. Do not use for simple factual
  or prose-only work, a single obvious edit, or a routine specialized workflow
  already fully covered by another skill.
---

# Lean Stack

Deliver the user's outcome with the least new machinery that survives real
verification. Be lazy about the solution, never about understanding or proof.

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
7. Finish with evidence from the real artifact and a concise handoff.

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
child slice that can independently improve evidence, speed, or review quality
while the parent continues useful work. Delegate one such slice by default;
delegate two or three when distinct workstreams divide cleanly. Before spawning
any subagent, read [delegation.md](references/delegation.md) and the
[managed custom-agent lifecycle](references/agent-lifecycle.md) in full.

At the delegation checkpoint, inventory built-in, personal, project, and
plugin-managed agents before choosing. Reuse the narrowest suitable existing
agent. Create a managed personal agent only when no existing agent fits, and use
the lifecycle script as the sole writer; never edit or remove an agent TOML
directly. A newly created or restored TOML is not proof of current-session
visibility, so use an explicit-role fallback until the real Codex surface
confirms it. Promoted experience stays in the versioned lifecycle playbook and
is injected into future briefs; promotion never overwrites the stable TOML.

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

Stay single-agent only for a trivial task, a tightly sequential chain with no
independent verification slice, or work whose overlapping writes and startup
cost clearly exceed the expected benefit. Increased delegation frequency does
not authorize redundant agents, duplicated scopes, or shared-file races.

After every managed-agent run, release its lifecycle lease and submit an
evidence-scored report. High-quality and efficient runs may contribute one
generic experience observation, but only a repeated rule that beats the
incumbent in an independent shadow comparison may be promoted. A confirmed
extreme failure can retire only a plugin-owned, hash-matching, inactive agent by
moving its single TOML to recoverable quarantine. Built-in, project, user-owned,
externally edited, or currently running agents are never automatically modified
or deleted. Tell the user whenever this skill causes a persistent create,
promotion, quarantine, or restore action.

## Proof contract

- Define what observable result would prove success before editing.
- Prefer a failing-then-passing reproduction for defects when a cheap path exists.
- Run the narrowest meaningful check first, then the broader relevant check.
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
