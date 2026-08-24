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
3. Identify blocking work before fan-out. Parallelize only independent slices and
   give every writer a disjoint output. Keep integration and shared state with
   one owner. Select and request each slice's model and reasoning effort from the
   delegation role matrix instead of applying one configuration to the program.
   For a medium-or-larger program, normally start one stable non-overlapping
   read-only slice when the conservative end-to-end saving is about 15 seconds
   or more, and normally start two when two clean slices meet that gate. Count
   startup, duplicate reading, transfer, synthesis, verification, retry, and
   escalation; do not fan out when those costs are likely to exceed the saving.
   Start useful children early, continue the parent-owned critical-path slice,
   and place a single explicit merge point later in the plan. Never make
   "spawn, immediately wait, then continue" the default shape.
   A blocking unit whose result is the only next step may instead use sequential
   specialist routing only through an existing selectable custom agent with at
   least one comparable high-scoring precedent, when the quality floor is preserved
   and the complete child route is both faster and cheaper than the parent route.
   In that case one bounded immediate wait is valid, but record it as sequential
   routing rather than fan-out and count any retry or escalation against its
   savings.
4. At each checkpoint, record the decision, evidence, result, and next risk in
   the task plan or a user-requested durable log. Do not accumulate raw agent
   transcripts in the main context. Re-run the delegation gate at each phase
   boundary and after a user continuation adds work; do not inherit a prior
   single-agent decision after the inputs or remaining scope changed.
5. Verify each unit before the next depends on it. Reassess the design when the
   same workaround or failed assumption repeats.
6. Stop at the terminal predicate. Before the final handoff, drain required child
   results and run the terminal-state closeout in `delegation.md`: a child final
   proves result delivery, not host closure. Use one bounded close/check/interrupt
   sequence, record `stale_host_status` when the host still cannot confirm a
   terminal state, and never rerun completed work to clear a stale UI card. Report
   unresolved gaps honestly; do not add adjacent improvements merely because the
   workflow is still running.

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
