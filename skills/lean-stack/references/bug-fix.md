# Bug fix

Use for a reported defect whose requested outcome includes a fix.

1. Reproduce the symptom on the matching surface. Record the smallest reliable
   trigger and the failing observation. If reproduction is unavailable, add
   targeted instrumentation or state why the result cannot be proved.
2. Trace the responsible flow and every relevant caller. Form a small set of
   competing causal hypotheses and eliminate them with evidence.
3. Confirm the surviving mechanism before designing the fix. For a non-trivial
   defect, delegate at least one independent evidence or verification slice when
   available, such as runtime reproduction, code-path mapping, or regression-test
   review; do not let several agents guess fixes concurrently. Request a
   `gpt-5.6-terra` / `medium` explorer for mapping, a `gpt-5.6-sol` / `xhigh`
   reviewer for a genuinely complex causal mechanism, and one
   `gpt-5.6-sol` / `high` implementation worker only after the cause is proven.
4. Apply the minimality ladder. Fix the shared cause once. Avoid speculative
   guards, fallback layers, and unrelated cleanup.
5. Add a cheap regression check first when it can represent the failure without
   a large harness. Otherwise preserve a precise manual or integration repro.
6. Re-run the original repro on the same surface, then run the broader relevant
   tests and inspect the final diff.

Done means the original failure is observed before the change, absent after it,
and the mechanism is explained by the evidence. A unit test alone is not a
substitute for the original surface when that surface is available.
