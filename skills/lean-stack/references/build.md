# Build or refactor

Use for features, behavior changes, refactors, and migrations.

1. Describe the user-visible outcome and name the authoritative data shape or
   contract before writing logic.
2. Trace the existing ownership and search for reusable code, standard-library
   support, native platform behavior, and installed dependencies.
3. Apply the minimality ladder and write down the first rung that fully satisfies
   the request. Remove dead weight before adding a replacement when safe.
4. If the change crosses a public boundary, changes shared state, or has no local
   precedent, compare two genuinely different shapes. Prefer established patterns
   when they already answer the question; do not create design theater. Request
   `gpt-5.6-sol` with `xhigh` effort for an architecture candidate only when this
   design branch is necessary.
5. Apply the delegation gate. Parallelize disjoint exploration, validation, or
   independent files. Keep one owner for coupled code and shared writes. Use
   `gpt-5.6-terra` / `medium` for exploration, `gpt-5.6-luna` / `low` for
   mechanical isolated work, and `gpt-5.6-sol` / `high` for implementation.
6. Implement the smallest coherent slice. Migrate real callers and remove a
   superseded internal API in the same verified wave when compatibility is not a
   requirement.
7. Verify the user-visible outcome on the matching surface, run relevant tests,
   and audit the diff for added dependencies, files, configuration, and public
   surface that did not earn their place.

Done means the requested behavior works, existing behavior remains supported by
relevant checks, and every new layer or dependency has a present caller and a
specific reason.
