# Codex Lean Stack

Codex Lean Stack is a skills-only personal plugin for software engineering. It
combines the strongest compatible ideas from Ponytail and pstack:

- A whole-task objective: preserve a quality and safety floor, then reduce
  verified completion time, total tokens/credits, retries, rework, and duplicate
  agent effort instead of optimizing one model call in isolation.

- A minimality ladder that prefers reuse, standard libraries, native platform
  features, deletion, and focused diffs.
- Task-shaped playbooks for investigation, bug fixing, implementation, review,
  and long-running work.
- Evidence on the real surface before a success claim.
- Critical-path native Codex subagents: start independent work early, keep the
  parent moving, and wait only once at a named merge point when the result is
  actually required.
- Terminal-state reconciliation that distinguishes a received final from a
  closed host thread, performs one bounded close/check/interrupt sequence, and
  never reruns completed work merely to clear a stale UI card.
- An adaptive custom-agent lifecycle that inventories existing agents, prefers a
  reusable specialist over a generic built-in, creates a narrow managed agent
  when that specialty is missing, immediately absorbs one bounded high-quality
  experience in rapid mode, records low-score demerits, runs finite single-axis
  resource competitions, and moves confirmed extreme failures to recoverable
  quarantine.
- Evidence-gated route recommendations that strengthen repeatedly weak agents,
  economize consistently strong but slow agents, and keep Fast/Standard as an
  explicit latency-versus-cost decision.
- Bounded AVO-inspired variation sessions with sanitized lineage, fixed
  candidate/wall/tool/token/credit budgets, stagnation-gated supervision,
  multi-objective shadow comparison, and a separate existing promotion gate.

It intentionally does not ship an MCP server, Node lifecycle hooks, a background
watcher, or dozens of always-loaded skills. One Python-standard-library CLI is
the only component allowed to persist custom-agent lifecycle changes. It
requests role-specific model and reasoning pairs in each subagent prompt and
spawn call, so exploration, mechanical work, implementation, and critical
review do not all inherit one parent configuration. Current Codex releases can
delegate after an applicable skill instruction, so the main skill provides the
routing and delegation contract directly.

## Install from this repository

This repository is the plugin source package. It is not a listing in the
universal public Plugins Directory, and another user's Personal marketplace
does not discover it automatically.

1. Clone the source into the default personal plugin-source location:

   ```powershell
   git clone https://github.com/Lang45/codex-lean-stack.git ~/plugins/codex-lean-stack
   ```

2. In Codex, ask the built-in plugin creator to register the existing source:

   ```text
   $plugin-creator Add the existing plugin at ~/plugins/codex-lean-stack to my
   default Personal marketplace. Preserve the plugin source; only create or
   update its marketplace entry.
   ```

3. Restart the ChatGPT desktop app, open the Plugins Directory, select the
   Personal source, and install **Codex Lean Stack**.
4. Start a new task so Codex loads the installed skill index.

If the resulting marketplace is named `personal` and `codex` resolves to a
supported standalone CLI or app-execution alias, the equivalent install command
after registration is:

```powershell
codex plugin add codex-lean-stack@personal
```

On a Windows Store/MSIX installation, prefer the desktop Plugins Directory.
Never invoke `WindowsApps\...\app\resources\codex.exe` directly: that package
resource can grant execute access only to a process carrying the matching package
identity, even though an ordinary shell can read the file. If no registered
`codex.exe` app-execution alias exists outside the package, the internal binary
is not a supported external CLI entry point.

See the official OpenAI documentation for
[plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins).

## Versioning and local refresh

The numeric SemVer base and `+codex.<timestamp>` have different jobs. A
backward-compatible feature bumps minor, a compatible fix bumps patch, and a
breaking public change bumps major. The Codex suffix invalidates the local
installed cache; changing only that suffix does not communicate a new feature.

Use the atomic release writer for a feature, fix, or breaking release:

```powershell
py -3 .\skills\lean-stack\scripts\bump_plugin_version.py . `
  --change feature `
  --expected-version "0.1.0+codex.previous"
```

The exact expected version prevents a retry from bumping twice, and the command
writes one new numeric base plus one cachebuster in a single atomic operation.
For documentation-only or unchanged-base local iteration, the system
plugin-creator cachebuster helper remains appropriate. Do not run that helper
after the semantic release command.

## Use

The `lean-stack` skill can be selected automatically for non-trivial engineering
work that combines architectural, causal, review, or independent-workstream
complexity. Invoke it explicitly when you want the mode to be unambiguous:

```text
$lean-stack fix this bug with the smallest verified change.
$lean-stack review this branch and delegate independent review axes.
$lean-stack explain this subsystem without changing anything.
```

The skill stays single-agent for trivial work and whenever startup, verification,
merge, retry, or write-conflict overhead erases the expected benefit. After the
critical-path gate passes, a medium-or-larger task normally uses one subagent when
a stable non-overlapping read-only slice conservatively saves about 15 seconds
end to end, and normally uses two when two such slices divide cleanly. A third
requires a third independent slice and a non-congested merge. The skill prefers
read-only delegation, prevents
overlapping writes, requires each child to answer in the user's current language,
requests a role-specific model and reasoning effort for every child, requires the
child to disclose requested values at startup, and includes effective model,
reasoning, or speed fields only when the host actually exposes them. Missing
effective fields are omitted completely rather than shown as placeholders. The
parent still inspects and verifies the result.

A tightly sequential task stays with the parent by default, but it is no longer
an unconditional single-agent case. If a specialist child owns the only next
step, it may be used as a sequential route only through an existing selectable
custom agent with at least one comparable high-quality evaluation on its current
revision. A probationary agent may qualify through that precedent; built-ins,
new or unscored, degraded, and pending agents are ineligible. Even then, evidence must support the
same quality floor and show that the complete child route is both faster and
cheaper than the parent route. The estimate counts startup,
result transfer, verification, retries, escalation, and merge work; a failed
cheap call followed by an expensive fallback is not reported as a saving. One
bounded immediate wait is allowed for this route because there is no parent work
to overlap, but it is explicitly not called parallel acceleration.

Default role routing:

| Role | Model | Reasoning effort |
|---|---|---|
| Codebase exploration | `gpt-5.6-terra` | `medium` |
| Integration and test review | `gpt-5.6-terra` | `high` |
| Documentation verification | `gpt-5.6-luna` | `medium` |
| Mechanical isolated work | `gpt-5.6-luna` | `low` |
| Bounded implementation | `gpt-5.6-sol` | `high` |
| Architecture, security, concurrency, data-loss review | `gpt-5.6-sol` | `xhigh` |

An explicit user or project choice overrides this table. Unsupported pairs get
one disclosed fallback attempt; critical review never silently drops below
`high` effort.

Fast is not a quality upgrade: current
[OpenAI Speed guidance](https://learn.chatgpt.com/docs/agent-configuration/speed)
describes roughly 1.5x model speed at a higher credit or API rate. The plugin
therefore uses a bounded speed bias: three high-quality slow runs can propose
Fast for low- or medium-cost configurations when the user accepts some extra
cost. High-cost configurations remain on Standard unless the user explicitly
accepts the larger multiplier. A speed proposal is never applied automatically.

The same accounting applies to delegation and releases. After spawning, the
parent immediately continues independent work and waits only at a predeclared
merge point. A late non-essential child is dropped; an essential child gets one
finish-now request and then becomes an explicit gap instead of blocking forever.
Every brief declares whether the route is parallel or sequential, its criticality
and deadline, and either the concurrent parent slice and merge point or the
evidence supporting the sequential quality/time/cost gate.
At closeout, a child `FINAL_ANSWER` means the result arrived; it does not prove
the host thread closed. The parent verifies the result, checks terminal state
once, asks once to stop and close any completed-but-active child, then uses the
available interrupt/stop control. If the UI still cannot confirm closure, the
parent records `stale_host_status`, stops waiting, and never reruns that work just
to clear the card. Managed-agent leases are released only after confirmed
terminal state; otherwise the bounded lease is allowed to expire.
Authorized idempotent publishing uses the normal transport first, retries
one clearly transient failure once, and then switches to a previously verified
safe transport instead of repeatedly waiting on the same broken path.

The gate is evaluated again on every continuation, scope expansion, grouped bug
report, and long-running phase transition. Existing tasks created before the
plugin refresh may not hot-load the skill, and an older Multi-Agent runtime may
provide no native collaboration tool at all. In those cases the plugin records a
capability miss and keeps the parent productive; it does not fabricate a
subagent or create a user-owned peer task as a substitute. A fresh task is the
verification boundary for newly installed delegation behavior.

## Managed agent lifecycle

When delegation is justified, the skill first catalogs the built-in agents and
personal/project custom agents. Existing suitable specialists are reused. If a
non-trivial delegated slice has a reusable specialty but no specialized custom
agent matches it, the lifecycle CLI creates a collision-resistant `lean_*`
personal agent before using a generic built-in fallback. A broadly capable
`worker` or `explorer` no longer suppresses customization by itself. The default
is at most one new persistent specialist per top-level task; a second requires a
distinct recurring specialty or an explicit request for more frequent
customization, and the same top-level task never creates a third. One-off roles,
capacity/conflict cases, and agents awaiting reload still use an explicit-role
fallback.

Each managed agent has a narrow role, explicit model and reasoning effort,
Chinese reporting, a Chinese user-visible name, a startup name/model/effort
disclosure, and a bounded sandbox. The stable internal ID remains an ASCII slug
because native spawn and filesystem interfaces may restrict identifiers; that
technical ID is not presented as the conversational name.

Persistent mutation is fail-closed:

- Only agents created and registered by the CLI may evolve or retire.
- Built-ins, project agents, pre-existing user agents, and externally edited
  agents are immutable.
- Hash drift, links, path changes, name conflicts, active leases, or unknown
  report fields stop the operation.
- A `run_id` names one real run for that managed agent across logical revisions.
  Identical retries return the original result; changed content under that ID is
  rejected, so neither rapid nor guarded retries can double-apply state.
- The installed skill records `evolution_mode=rapid`. A high-quality run must
  contribute one sanitized experience, which is immediately added to the
  versioned external playbook for future briefs. A score below 90 immediately
  records a demerit and lowers reputation. Routed high and low runs share one
  project-scoped configuration history. The first attributable major failure
  marks an exact configuration `watch`; the second marks it `failing` and may
  stage one causal single-axis challenger. Quality failures strengthen model or
  reasoning; model-compute latency/timeout can try a faster axis; cost overrun
  with a known high token or credit bucket can try a cheaper axis. Tool, role,
  stale-host, unproven timeout, missing reason, unknown cost, and unknown failures
  are penalized without being misclassified as configuration weakness.
- Existing callers remain compatible: omitted or explicit `guarded` mode keeps
  the three-observation plus independent-shadow promotion workflow.
- Rapid high performers retain the incumbent and stage at most one logical
  resource challenger per project/task/risk class. Each challenger changes exactly one
  finite neighboring model, reasoning, or host-confirmed speed tier, and every
  configuration is visited at most once in the agent/project/task/risk search, including
  former champions, so a winner cannot recreate the previous incumbent. Once every
  neighbor loses, the route is converged and high scores no longer produce
  copies. A winning route starts a new finite search from the new champion.
  Another neighbor is not staged until a comparable run actually uses that
  preferred champion configuration; an older named-TOML run may absorb experience
  but cannot masquerade as the new baseline.
  Neither path overwrites stable agent TOML; future briefs receive the validated
  rules and preferred route from catalog.
- Ordinary failure never deletes an agent. A deterministically confirmed
  critical violation, or repeated independently confirmed extreme failure, can
  move one managed TOML out of the active directory into recoverable quarantine.
- Permanent purge is not implemented.

### Adaptive route recommendations

Task-end evaluations can optionally record bounded routing facts: requested and
effective model, reasoning effort, service tier, execution mode, and a fixed
cause code. Unexposed effective values remain `unknown`; old evaluations are not
backfilled with guesses. `catalog --project-root` returns an opaque `project_key`
that new reports and `recommend-route --project-key` reuse; the lifecycle never
stores the repository path. Reports that omit the key remain in the compatible
`global` pool.

Rapid competition judges quality, speed, and cost together with task-specific
weights. Architecture uses `75/15/10`; implementation `65/25/10`; review
`65/20/15`; test `55/30/15`; exploration `45/35/20`; documentation `45/30/25`;
other tasks `55/25/20`. Workspace-write and external-effect risk shift another
5 or 10 points toward quality. Correctness, evidence, scope, clarity, and safety
form the quality component; duration is speed; token and credit buckets are
cost. Unknown resource values are neutral and never prove an improvement, while
the high-quality and safety floors remain mandatory regardless of weights.

Before the next comparable task, `recommend-route` separates quality from
efficiency and returns one of:

- `compete`: run the one open rapid single-axis challenger through an explicit
  fallback while retaining the incumbent.
- `watch`: one or two low-quality signals; gather more evidence.
- `hold`: keep the incumbent configuration.
- `strengthen`: shadow one higher model or reasoning step after repeated low
  quality.
- `economize`: shadow one lower effort or model step after sustained high
  quality with slow execution.
- `speed_up` / `standardize_speed`: consider Fast for low- or medium-cost slow
  work, or Standard for high-cost work.

Recommendations compare only the same agent revision, task class, risk tier,
execution mode, and requested configuration. They require high-confidence,
evidence-backed evaluations and change one axis at a time. They do not edit the
agent TOML, global `config.toml`, or the current session. Named custom agents
must use an explicit-role fallback to shadow a different model or effort because
their TOML values take precedence. Fast remains recommendation-only when the
host does not expose a per-agent service-tier field.

### Bounded variation and stagnation supervision

Schema v6 retains v5 credits, retries, rework, reputation, and finite challenger
lineage, then adds project-scoped routes and a single shared high/low
configuration-observation pool. It migrates v5 atomically without fabricating
historical configuration facts; old rapid digests replay only through the
compatible global path. `stagnation-status` authorizes a supervisor only
after a comparable no-improvement streak or the same high-confidence failure
reason repeats three times. A single poor or slow run never starts self-editing.
An explicit user can still request a manual variation session.

The variation sequence is deliberately split:

1. `variation-plan` snapshots sanitized lineage and fixes one to four candidates,
   a 60–3,600 second end-to-end wall budget, up to 32 total tool calls, and total
   token/credit buckets covering generation plus shadow verification.
2. `variation-stage` accepts exactly that count only before the deadline and
   within every budget. It stores staged challengers and changes no TOML.
3. `variation-verify` requires at least three identical shadow cases, an
   independent high-confidence judge, strong evidence, no critical regression,
   and a separate wall/token/credit/retry/rework comparison.
4. The existing `promote` command must still run separately. Only then does the
   logical playbook revision advance; the stable TOML remains unchanged.

Quality and safety are hard gates. With less than a three-point quality gain, a
challenger must have no known resource regression and strictly improve at least
one resource or rework objective. A larger quality gain may trade resources only
when that tradeoff was explicitly accepted. Unknown credits remain unknown and
cannot be counted as savings. The supervisor can propose a direction; it cannot
change global configuration, promote a candidate, or bypass revision/hash/lease
checks. Full JSON contracts and commands are in
[`agent-lifecycle.md`](skills/lean-stack/references/agent-lifecycle.md).

The lifecycle database and quarantine live under
`~/.codex/lean-stack/`. They do not retain user prompts, repository content,
task/repository paths, URLs, raw traces, terminal logs, credentials, or model
reasoning. The database necessarily retains canonical paths for the exact
plugin-managed agent TOML and quarantine file it owns.

Codex's documentation does not promise that a newly created or restored custom
agent is hot-loaded into the current task. The plugin therefore marks those file
operations as waiting for visibility/reload, uses an explicit-role fallback when
necessary, and verifies them from a new task before claiming they are active.
Experience promotion changes only the lifecycle playbook injected into future
briefs, so it does not depend on TOML hot reload.

## Structure

```text
codex-lean-stack/
|-- .codex-plugin/plugin.json
|-- skills/lean-stack/
|   |-- SKILL.md
|   |-- agents/openai.yaml
|   |-- scripts/bump_plugin_version.py
|   |-- scripts/manage_agents.py
|   `-- references/
|       |-- delegation.md
|       |-- agent-lifecycle.md
|       |-- investigation.md
|       |-- bug-fix.md
|       |-- build.md
|       |-- review.md
|       |-- versioning.md
|       `-- long-running.md
|-- tests/test_bump_plugin_version.py
|-- tests/test_manage_agents.py
|-- LICENSE
`-- THIRD_PARTY_NOTICES.md
```

## Validate

From the plugin root:

```powershell
py -3 "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" ".\skills\lean-stack"
py -3 "$env:USERPROFILE\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py" "."
py -3 ".\tests\test_bump_plugin_version.py" -v
py -3 -m unittest discover -s ".\tests" -v
```

During development, run only checks that can fail because of the current change,
an explicit contract, or a material boundary risk. Run the narrow affected test
first and one essential broader suite at most once before release unless relevant
code or environment changes again. Do not run code suites after documentation-only
edits. Keep one focused aggregate test for each independent risk boundary rather
than preserving every historical edge-case test or repeatedly running unrelated
test groups.

## Design sources

- [Ponytail](https://github.com/DietrichGebert/ponytail) supplies the disciplined
  minimality bias and the boundary that small code must not remove safety or
  verification.
- [pstack](https://github.com/cursor/plugins/tree/main/pstack) supplies
  task-shaped rigor, independent review, evidence-oriented completion, and
  context-preserving delegation.
- [Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=app)
  defines the native delegation model used here.
- [GEPA](https://github.com/gepa-ai/gepa),
  [DGM](https://github.com/jennyzzt/dgm),
  [LangMem](https://github.com/langchain-ai/langmem), and
  [Darwin Agents](https://github.com/studiomeyer-io/darwin-agents) inform the
  candidate, evidence, lineage, A/B gate, and rollback/quarantine lifecycle.
  The last project is new and is treated as an engineering pattern rather than
  proof of broad production maturity.
- [AVO](https://arxiv.org/abs/2603.24517) informs the bounded variation-session,
  stagnation-supervisor, and multi-objective candidate-generation additions. The
  plugin intentionally does not copy its long-running autonomous loop: every
  candidate remains budgeted, staged, independently verified, and separately
  promoted.
- [RouteLLM](https://github.com/lm-sys/RouteLLM) informs calibrated,
  task-distribution-specific strong/weak model thresholds instead of single-run
  switching.
- [FrugalGPT](https://arxiv.org/abs/2305.05176) informs quality-gated cascades;
  its benchmark gains are treated as workload-specific research results, not as
  guarantees for Codex subagents.
- [LLMRouter](https://github.com/ulab-uiuc/LLMRouter) reinforces task-aware,
  quality-and-cost evaluation across multiple routing strategies. Its breadth is
  evidence for benchmarking routes, not a reason to add a learned router before
  this plugin has representative task data.
- The third-party
  [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
  repository was reviewed for assumption surfacing and surgical-change ideas.
  Its text was not copied; it is not an Andrej Karpathy-authored or endorsed
  Codex skill, has no repository test suite, and currently lacks a standalone
  `LICENSE` file despite README/frontmatter MIT labels.

See `THIRD_PARTY_NOTICES.md` for license attribution.
