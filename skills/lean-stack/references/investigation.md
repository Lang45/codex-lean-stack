# Investigation

Use for read-only questions about behavior, ownership, rationale, risk, or a
choice between approaches.

1. State the exact question and what evidence would answer it.
2. Trace the runtime path, data flow, callers, configuration, and tests that own
   the behavior. Use history and external documentation only when the question
   depends on them.
3. Apply the eager delegation gate whenever one independent module, evidence
   source, or verification pass can be checked while the parent traces the main
   path. Give each subagent a distinct source category or subsystem. Request
   `gpt-5.6-terra` with `medium` effort for codebase exploration and
   `gpt-5.6-luna` with `medium` effort for narrow documentation verification.
4. Reconcile conflicts against primary evidence. Do not treat search snippets,
   comments, or old docs as more authoritative than current code and behavior.
5. Return the answer or recommendation with exact locations or links. Separate
   confirmed facts, inference, and unknowns.

Do not edit, launch a mutating workflow, or quietly turn the investigation into
an implementation. If the conclusion suggests a change, hand it back as an
option unless the user's request already authorized that change.
