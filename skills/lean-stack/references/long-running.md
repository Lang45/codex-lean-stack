# Long-running orchestration overlay

Read this in addition to the task's primary playbook when one request spans
several independently verifiable phases, a large migration, or work the user
expects Codex to carry without repeated prompts. The primary playbook still owns
task-specific evidence such as bug reproduction, review findings, or feature
behavior.

1. Define one terminal predicate and the authority boundary. Persistence does
   not authorize deployment, deletion, publication, or external messages.
2. Split the program into the smallest units that each end in a meaningful
   check. Keep at most one unit in progress in the parent plan.
3. Identify blocking work before fan-out. Delegate only independent slices and
   give every writer a disjoint output. Keep integration and shared state with
   one owner. Select and request each slice's model and reasoning effort from the
   delegation role matrix instead of applying one configuration to the program.
   Estimate the critical path: do not fan out when agent startup, duplicate
   reading, and synthesis are likely to take longer than the work saved.
   Start useful children early, continue the parent-owned critical-path slice,
   and place a single explicit merge point later in the plan. Never make
   "spawn, immediately wait, then continue" the default shape.
4. At each checkpoint, record the decision, evidence, result, and next risk in
   the task plan or a user-requested durable log. Do not accumulate raw agent
   transcripts in the main context.
5. Verify each unit before the next depends on it. Reassess the design when the
   same workaround or failed assumption repeats.
6. Stop at the terminal predicate. Report unresolved gaps honestly; do not add
   adjacent improvements merely because the workflow is still running.

For an authorized, idempotent external transfer such as publishing one verified
commit, try the normal transport first. After one bounded retry of a clearly
transient failure, do not keep paying the same timeout: switch to a previously
verified safe transport when one exists, or report the exact external gap. Reuse
already completed validation when the artifact bytes are unchanged; run the
narrow affected check after a small edit and one final broad verification wave
before handoff. During ordinary editing, run only the narrow check that can fail
because of the current change. Run the smallest essential final suite once; do
not repeat full suites or independent reviews after documentation-only edits.

When blocked, exhaust safe in-scope evidence and alternatives. Ask for user input
only when a product choice, new authority, or unavailable external state truly
prevents progress.
