# Review or audit

Use for a diff, branch, file set, or repository review. This playbook is
read-only unless the user separately asks for fixes.

1. Establish the intended behavior and review boundary. Compare against the
   correct base, not an assumed branch name.
2. For a trivial diff, review locally. For an ordinary non-trivial diff, use at
   least one independent read-only subagent on the highest-risk axis. For a
   substantial or cross-cutting diff, use two or three with distinct axes:
   - Correctness, security, concurrency, and data-loss risk. Request
     `gpt-5.6-sol` with `xhigh` effort.
   - Integration boundaries, tests, and behavior regressions. Request
     `gpt-5.6-terra` with `high` effort.
   - Minimality, dependencies, dead flexibility, and reader load. Request
     `gpt-5.6-terra` with `medium` effort.
3. Require every finding to include a location, causal mechanism, impact,
   evidence or reproduction path, and the smallest credible mitigation.
4. Deduplicate results and verify high-impact claims against the code or runtime.
   Consensus is useful signal; it is not proof. Reject style-only preferences and
   findings that depend on invented requirements.
5. Lead with actionable findings ordered by severity. Then list assumptions,
   test gaps, and a brief verdict. If there are no material findings, say so
   plainly and name any validation boundary.

Do not apply fixes, post comments, or create external issues unless the user
explicitly expands the request.
