---
tags:
  - '#research'
  - '#flow-bugs'
date: '2026-04-21'
related:
  - '[[2026-03-16-managed-content-blocks-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
  - '[[2026-04-11-mcp-registry-adr]]'
---

# `flow-bugs` research: five install-layer hygiene defects from production

Production use of `vaultspec-core` 0.1.13 on a consuming repo (aeat) surfaced five defects that share the same root: the install/guard layer leaks mutable state into the working tree and fails to update its own git-tracking assumptions on repos that predate current contracts. GitHub issue 80 bundles the five together. Each one is treated here as an isolated problem domain with repro, root cause in source, and candidate remediations.

All line references point at `feature-flow-bugs` worktree head (branch `feature/flow-bugs`).

______________________________________________________________________

## Domain 1 - `providers.json` stays tracked on repos that predate the managed gitignore block

### Repro

A repo committed `.vaultspec/providers.json` before the managed `.gitignore` block landed. `install` rewrites the manifest on every run (serial, timestamps, per-provider `last_synced`), so `git status` always reports `.vaultspec/providers.json` as modified, even though the managed gitignore block lists `.vaultspec/`. Git ignore rules do not retroactively untrack files - an `--assume-unchanged` or `git rm --cached` step is required to stop the drift.

### Root cause

`src/vaultspec_core/core/commands.py` install_run (lines 596-863) persists `ManifestData` via `write_manifest_data` on every execution. The manifest schema is intentionally mutable (`serial`, `installed_at`, `last_synced`). `get_recommended_entries` (`src/vaultspec_core/core/gitignore.py` lines 22-77) already emits `.vaultspec/` when the directory exists. For new repos the entry prevents tracking. For legacy repos where the file is already in the index, the pattern is silently ignored by git.

No code path in the install flow attempts to detect or remediate historically-tracked state files. No user-facing surface explains the quirk.

### Candidate remediations

1. On install, iterate the effective managed gitignore entries and invoke `git rm --cached --ignore-unmatch` on any that are currently tracked. Requires `git` presence and a gated execution (workspace layout already exposes `git` via `WorkspaceLayout.git`).
1. Emit a one-shot warning plus a printed `git rm --cached ...` command - defer the fix to the operator.
1. Scope narrowly: untrack only `.vaultspec/providers.json` and `.mcp.json` (the two known offenders). Lower blast radius, weaker contract.

Option 1 is preferred: it keeps the managed-block contract honest ("if we tell you to ignore it, we also tell git we no longer want it tracked"). It must be bounded to files whose parent directory we own (`.vaultspec/` + any provider directory) to avoid accidentally untracking legitimately-committed paths like `.mcp.json` when the operator wants it committed.

______________________________________________________________________

## Domain 2 - `advisory_lock` emits 0-byte `.lock` sentinels that never get cleaned up

### Repro

After any install or sync, the working tree has new untracked files at:

```
.gitignore.lock
.mcp.json.lock
.pre-commit-config.yaml.lock
.vaultspec/providers.json.lock
.vaultspec/providers.lock    (legacy - included in PROVIDER_ARTIFACT_PATTERNS)
```

None are in the managed block. `git status` stays permanently dirty. CI recreates them on every fresh checkout without cleanup.

### Root cause

`src/vaultspec_core/core/helpers.py` `advisory_lock` (lines 39-88) implements `<path>.lock` as the OS-level lock file via `msvcrt.locking` / `fcntl.flock`. `os.open(..., O_CREAT | O_RDWR)` creates the sentinel; the lock is released via `msvcrt.locking(..., LK_UNLCK)` / `fcntl.flock(..., LOCK_UN)` but the file itself is never removed. This is intentional for concurrency safety - unlinking under lock is racy - but the side effect is permanent sentinels.

### Candidate remediations

1. **Managed gitignore entries.** Extend `get_recommended_entries` to include the five lock sentinels when their companion file exists. Minimal change, preserves existing locking behaviour. Risk: any new file we lock in future will leak again.
1. **Glob pattern in managed block.** Emit `.vaultspec/*.lock` + a narrow glob like `/.*.lock` (dotfiles only, at root). Durable against future lock targets. Risk: `.gitignore.lock` etc must survive any user-edit of the managed block; if a user commits the glob out, the sentinels come back. That matches domain 1's story, so the glob option composes naturally with the untrack-on-install fix.
1. **Centralised lock directory.** Route all advisory locks through `.vaultspec/_locks/<hash>.lock` so the sentinels live in a directory already covered by `.vaultspec/`. Requires `advisory_lock` API change - all callers pass a path, but the lock target is now a hash-keyed sibling. Cleanest long-term but largest blast radius.
1. **Cleanup on exit.** Remove sentinels at process exit via `atexit`. Rejected: racy on concurrent processes, Windows can fail to unlink a file another process has open.

Option 2 (glob) + 3 (centralised) combine cleanly: glob is the immediate fix for 0.1.14; centralised is a follow-up. For this pass, ship option 2 to the `/.gitignore.lock`, `/.mcp.json.lock`, `/.pre-commit-config.yaml.lock` triple plus `.vaultspec/*.lock`.

______________________________________________________________________

## Domain 3 - `.pre-commit-config.yaml` is regenerated even when the project uses `prek`

### Repro

Project has `prek.toml`. `install --upgrade` re-runs `_scaffold_precommit`, which writes `.pre-commit-config.yaml` unconditionally. `prek` warns `Multiple configuration files`; neither tool executes the hooks.

### Root cause

`src/vaultspec_core/core/commands.py` `_scaffold_precommit` (lines 302-420) unconditionally writes `.pre-commit-config.yaml`. `install_run` (line 725) calls it on every `--upgrade` run. The managed gitignore block does not list `.pre-commit-config.yaml` (domain 2 kinship) and there is no probe for `prek.toml`.

### Candidate remediations

1. Detect `prek.toml` and short-circuit `_scaffold_precommit`. Simplest fix. Cost: prek users get no vaultspec-provided hooks and must wire them manually. Acceptable because prek is opt-in.
1. Detect `prek.toml` and scaffold the hooks into it (prek supports the same `[[repos]]` layout in TOML). Larger change, requires a second renderer; prek schema is still evolving.
1. Leave `_scaffold_precommit` as-is but add `.pre-commit-config.yaml` to the managed gitignore block so commits are clean. Does not fix the "warning in prek" complaint, only the "tracked churn" one.

Option 1 is preferred. Pair it with a one-shot notice pointing the operator at prek's config format; do not attempt to write TOML hooks in this release.

______________________________________________________________________

## Domain 4 - `check-providers` hook blocks staged **deletions**

### Repro

Operator runs `git rm --cached .vaultspec/providers.json` to fix domain 1. The pre-commit hook `check-providers` inspects the staging area and blocks the commit because the file matches a provider-artifact pattern, even though it is being removed.

### Root cause

`src/vaultspec_core/core/commands.py` `check_staged_provider_artifacts` (lines 212-245) runs `git diff --cached --name-only` with no `--diff-filter`. `git diff` reports every staged path including deletions; the pattern match does not discriminate between "added" and "deleted".

### Candidate remediation

Pass `--diff-filter=ACMR` (added / copied / modified / renamed). Deletions fall outside the filter and the hook stops punishing the remediation path. The fix is a three-character change plus an integration test.

______________________________________________________________________

## Domain 5 - `install --upgrade --force` cascades into `vault check all --fix` renames that break wiki-links

### Repro

Repo has pre-existing `.vault/` that predates the current structure-check rules (files like `2026-03-01-xyz-review.md`). Operator runs `install --upgrade --force` to reset a corrupted manifest. A later pre-commit hook (`vault-fix`) runs `vault check all --fix`, which renames the file to `2026-03-01-xyz-review-audit.md` via `_fix_filename`. Incoming `[[2026-03-01-xyz-review]]` references in other documents are left pointing at a filename that no longer exists, producing dozens of dangling links.

### Root cause

`src/vaultspec_core/vaultcore/checks/structure.py` `_fix_filename` (lines 31-100) renames the on-disk file but never updates incoming wiki-link references. The graph already exposes reverse-adjacency data (`VaultGraph` can enumerate all documents that link to a given stem) but the rename path does not consult it.

Install itself does not invoke `vault check --fix`. The cascade enters via the pre-commit hook after the install-era changes are staged. The user-perceived bundle ("install triggers the rename") is accurate from their vantage point: the hook fires on the next commit, and the rename is invisible until they `git status`.

### Candidate remediations

1. **Rewrite references during rename.** In `_fix_filename`, after `doc_path.rename(new_path)`, walk every document whose `related:` frontmatter or body contains the old stem and rewrite the reference to the new stem. Uses existing `VaultGraph` or a direct scan.
1. **Gate the rename behind an opt-in flag.** Split `vault check structure --fix` into "report" and "rewrite" modes; the rewrite mode is the only one that renames. Pre-commit hook uses report-only by default.
1. **Decouple manifest repair from the fix cascade.** Give `install --upgrade --force` a dedicated path that repairs the manifest and nothing else; do not rely on downstream hooks.

Option 1 is the correct long-term fix - a rename that does not update its references is broken by definition. Option 3 is a valid orthogonal concern (`install --upgrade --force` should not need to pass through the vault check path at all; it already does not in the current code, so no change needed there - the cascade is entirely in the pre-commit hook).

The minimal shipping fix: option 1 (rewrite references during rename) plus an integration test that verifies `[[stem]]` references survive a rename. Option 2 can be a follow-up if the operator pool wants more control.

______________________________________________________________________

## Test & quality gate gaps exposed

- No test covers "legacy repo with pre-existing tracked `providers.json`".
- No test covers "advisory_lock does not leave untracked files in the managed tree".
- No test covers "`_scaffold_precommit` respects `prek.toml`".
- No test covers "`check-providers` allows staged deletions".
- No test covers "vault structure rename updates incoming references".

The existing `WorkspaceFactory` test fixture already supports install/uninstall lifecycle composition; all five gaps can be filled without mocks by adding factory states and assertions over real filesystem output.

## Next step

Produce a companion ADR (`2026-04-21-flow-bugs-adr.md`) that ratifies the five candidate remediations (Option 1 for D1, Option 2 for D2, Option 1 for D3, the diff-filter fix for D4, Option 1 for D5), then a single combined plan to execute the lot.
