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
- Eager but bounded native Codex subagents: one useful independent slice by
  default for non-trivial work, and two or three when workstreams divide cleanly.
- A guarded custom-agent lifecycle that inventories existing agents, prefers a
  reusable specialist over a generic built-in, creates a narrow managed agent
  when that specialty is missing, records evidence, promotes tested experience,
  and moves confirmed extreme failures to recoverable quarantine.
- Evidence-gated route recommendations that strengthen repeatedly weak agents,
  economize consistently strong but slow agents, and keep Fast/Standard as an
  explicit latency-versus-cost decision.

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

If the resulting marketplace is named `personal`, the equivalent Codex CLI
install command after registration is:

```powershell
codex plugin add codex-lean-stack@personal
```

See the official OpenAI documentation for
[plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins).

## Use

The `lean-stack` skill can be selected automatically for non-trivial engineering
work that combines architectural, causal, review, or independent-workstream
complexity. Invoke it explicitly when you want the mode to be unambiguous:

```text
$lean-stack fix this bug with the smallest verified change.
$lean-stack review this branch and delegate independent review axes.
$lean-stack explain this subsystem without changing anything.
```

The skill stays single-agent only for trivial or tightly sequential work with no
useful independent verification slice. It normally uses one subagent for an
ordinary non-trivial task and no more than two or three for clearly separable
workstreams, prefers read-only delegation, prevents
overlapping writes, requires each child to answer in the user's current language,
requests a role-specific model and reasoning effort for every child, requires the
child to disclose both the requested and runtime-effective values at startup
without guessing missing metadata, and requires the parent to inspect and verify
the result.

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

Standard is the default speed mode. Fast is not a quality upgrade: current
[OpenAI Speed guidance](https://learn.chatgpt.com/docs/agent-configuration/speed)
describes roughly 1.5x model speed at a higher credit or API rate. The plugin
therefore keeps high-cost configurations on Standard and only
proposes Fast for a low-cost configuration after repeated high-quality but slow
runs with low observed total-token buckets. A cheap model that needs many tokens,
retries, or escalation is not treated as a cheap completed task. A speed proposal
is never applied automatically.

The same accounting applies to delegation and releases. Parallel work must save
critical-path time or add independent evidence worth its startup and synthesis
cost. Authorized idempotent publishing uses the normal transport first, retries
one clearly transient failure once, and then switches to a previously verified
safe transport instead of repeatedly waiting on the same broken path.

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
- Successful experience is first an observation, then a challenger. Three
  repeated high-quality observations and an independent shadow comparison are
  required before one narrow rule can be promoted into a versioned external
  playbook. Promotion never overwrites the stable agent TOML; future briefs
  receive the validated rules from catalog.
- Ordinary failure never deletes an agent. A deterministically confirmed
  critical violation, or repeated independently confirmed extreme failure, can
  move one managed TOML out of the active directory into recoverable quarantine.
- Permanent purge is not implemented.

### Adaptive route recommendations

Task-end evaluations can optionally record bounded routing facts: requested and
effective model, reasoning effort, service tier, execution mode, and a fixed
cause code. Unexposed effective values remain `unknown`; old evaluations are not
backfilled with guesses.

Before the next comparable task, `recommend-route` separates quality from
efficiency and returns one of:

- `watch`: one or two low-quality signals; gather more evidence.
- `hold`: keep the incumbent configuration.
- `strengthen`: shadow one higher model or reasoning step after repeated low
  quality.
- `economize`: shadow one lower effort or model step after sustained high
  quality with slow execution.
- `speed_up` / `standardize_speed`: consider Fast for low-cost slow work or
  Standard for high-cost work.

Recommendations compare only the same agent revision, task class, risk tier,
execution mode, and requested configuration. They require high-confidence,
evidence-backed evaluations and change one axis at a time. They do not edit the
agent TOML, global `config.toml`, or the current session. Named custom agents
must use an explicit-role fallback to shadow a different model or effort because
their TOML values take precedence. Fast remains recommendation-only when the
host does not expose a per-agent service-tier field.

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
|   |-- scripts/manage_agents.py
|   `-- references/
|       |-- delegation.md
|       |-- agent-lifecycle.md
|       |-- investigation.md
|       |-- bug-fix.md
|       |-- build.md
|       |-- review.md
|       `-- long-running.md
|-- tests/test_manage_agents.py
|-- LICENSE
`-- THIRD_PARTY_NOTICES.md
```

## Validate

From the plugin root:

```powershell
py -3 "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" ".\skills\lean-stack"
py -3 "$env:USERPROFILE\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py" "."
py -3 -m unittest discover -s ".\tests" -v
```

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
