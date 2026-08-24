# Plugin versioning and cache refresh

Use this reference when a task changes a versioned plugin or prepares a plugin
release. A numeric SemVer base communicates change compatibility; a Codex build
suffix only invalidates the installed cache. They are different decisions.

## Change classification

| Change | SemVer axis | Example |
|---|---|---|
| Backward-compatible feature, new skill behavior, command, or public field | minor | `0.1.0` to `0.2.0` |
| Backward-compatible defect fix with no new public capability | patch | `0.1.0` to `0.1.1` |
| Removed, renamed, or incompatible public behavior | major | `0.1.0` to `1.0.0` |

Documentation, tests, formatting, and internal refactors do not bump the base by
default. If their unchanged base still needs a local cache refresh, use the
system plugin-creator cachebuster helper. Do not use that helper as a substitute
for a feature, fix, or breaking release: it intentionally preserves everything
before `+`.

## Atomic release command

For a semantic release, use this skill's standard-library writer as the only
manifest-version mutation in that release wave:

```powershell
py -3 .\skills\lean-stack\scripts\bump_plugin_version.py <plugin-root> `
  --change feature `
  --expected-version "0.1.0+codex.previous"
```

`feature`, `fix`, and `breaking` map to minor, patch, and major. The command:

1. Requires the exact old full version as a compare-and-swap guard.
2. Rejects invalid SemVer, foreign build metadata, links, non-regular manifests,
   invalid plugin names, invalid cachebuster tokens, and concurrent release locks.
3. Bumps exactly one numeric axis, clears prerelease metadata, and creates one
   `+codex.<UTC timestamp>` suffix.
4. Writes a validated temporary JSON file, fsyncs it, confirms the source bytes
   did not change, and atomically replaces the manifest.
5. Leaves the old manifest intact on any failure before atomic replacement.
   Failure of the post-replace directory durability check explicitly reports
   that the new version may already be present and requires inspection before
   retrying. Repeating the same command after a success fails because
   `--expected-version` no longer matches.

Use `--dry-run` to preview and `--cachebuster <token>` only for a deterministic
test or an explicitly coordinated release. Do not run the system cachebuster
helper after this command; the semantic writer already produced the one suffix
for the release.

## Minimal release sequence

1. Classify the user-visible change before editing the manifest.
2. Finish the coherent feature or fix and its narrow affected checks.
3. Run `bump_plugin_version.py` once with the exact old version.
4. Run the version script's focused test and the plugin/skill validators.
5. Commit and publish the changed artifact.
6. Install or refresh it from the configured local marketplace in the desktop
   app, then verify the new cache version from a new task.

Project policy and an explicit user version override this default. Never bump a
numeric version merely to rerun an unchanged local install.
