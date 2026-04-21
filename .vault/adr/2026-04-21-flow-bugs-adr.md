---
tags:
  - '#adr'
  - '#flow-bugs'
date: '2026-04-21'
related:
  - '[[2026-04-21-flow-bugs-research]]'
  - '[[2026-03-16-managed-content-blocks-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
---

# `flow-bugs` adr: install-layer hygiene contract

Status: Accepted
Supersedes: n/a
Superseded by: n/a

## context

Issue 80 bundles five install-layer defects. Research (`[[2026-04-21-flow-bugs-research]]`) documented each as a distinct problem domain with repro, root cause, and candidate remediations. This ADR ratifies the five decisions and the cross-cutting hygiene contract they imply.

## decision

The install/guard layer owns a **hygiene contract** with three invariants:

1. **The managed gitignore block is authoritative.** If a path appears in the managed entries, no part of the install flow may leave that path dirty in the working tree. This applies to previously-tracked state files and to ephemeral sentinels produced by our own code.
1. **Tool-specific scaffolding respects the project's active toolchain.** `_scaffold_precommit` must not write files that conflict with a detected alternative (`prek.toml`).
1. **Pre-commit hooks distinguish operator intent from accidental commits.** `check-providers` treats staged deletions as remediation, not violation.

Concretely, the five decisions are:

### d1 - untrack previously-tracked managed paths on install

On `install` and `install --upgrade`, iterate the effective managed gitignore entries and invoke `git rm --cached --ignore-unmatch` on any path that is (a) tracked by git and (b) under a directory owned by vaultspec (`.vaultspec/`, or any provider directory whose presence is recorded in the manifest). The set must exclude root-level managed files that operators may legitimately commit (e.g. `.mcp.json`, `CLAUDE.md`, `.pre-commit-config.yaml`) - those are covered by other decisions or by operator choice.

The effective allow-list for untracking is:

- Everything under `.vaultspec/` (internal state, never user content).
- Each provider's scope directory recorded in the manifest (`.claude/`, `.gemini/`, `.agents/`, `.codex/`), only for files that match the managed gitignore entries.

Operation is a no-op when the target is not a git repo. Failures from the subprocess call are logged and do not abort install.

### d2 - extend managed gitignore entries to cover advisory-lock sentinels

Augment `get_recommended_entries` with:

- `/.gitignore.lock`
- `/.mcp.json.lock`
- `/.pre-commit-config.yaml.lock`
- `.vaultspec/*.lock`

Entries are emitted only when their parent context exists (the root-level triple conditional on the companion file; the `.vaultspec/` glob conditional on the directory). A broader `*.lock` is rejected because `uv.lock`, `Cargo.lock`, `bun.lock`, and friends are legitimately tracked.

The advisory-lock implementation itself is unchanged in this release. A centralised lock directory is left as follow-up.

### d3 - skip `.pre-commit-config.yaml` generation when `prek.toml` is present

`_scaffold_precommit` returns early with a one-shot info log pointing the operator at the prek config format when `prek.toml` exists at the target root. The existing `_scaffold_precommit` return contract (list of `(relpath, label)` tuples) returns an empty list in that branch. No hooks are transplanted into `prek.toml`; that is out of scope for this release.

The `_ALL_MANAGED_HOOK_IDS` uninstall path is unaffected - if a legacy `.pre-commit-config.yaml` exists alongside `prek.toml`, uninstall still strips vaultspec hooks from it.

### d4 - `check-providers` uses `--diff-filter=ACMR`

`check_staged_provider_artifacts` invokes `git diff --cached --name-only --diff-filter=ACMR`. Deletions and type changes fall outside the filter; additions, copies, modifications, and renames continue to be guarded.

### d5 - `_fix_filename` rewrites incoming wiki-link references atomically with the rename

When `_fix_filename` renames `OLD-STEM.md` to `NEW-STEM.md`, it walks the surviving vault snapshot and rewrites any wiki-link tokens carrying `OLD-STEM` to the new stem. Scope for this release:

- Tokens of the form `- "wiki-link-pointing-at-OLD-STEM"` inside frontmatter `related:` lists are rewritten to point at `NEW-STEM`.
- Body prose wiki-link rewriting is deferred to a follow-up so that free-text mentions of the old stem do not mutate unexpectedly. This matches how `check_dangling --fix` already scopes its rewrites to frontmatter only.

The rewrite uses the same graph and parser infrastructure already imported by `check_structure`. Each rewrite increments `result.fixed_count` with a dedicated diagnostic so operators can audit the change in `--verbose` output. Rewrite failures (read/parse errors) log a warning and do not abort the rename - the rename itself has already succeeded.

#### d5 - implementation notes ratified in audit loop

The first two review iterations surfaced edge cases that shipped inside D5 rather than as separate decisions. They are ratified here so future reviewers can verify against spec:

- **Transitive rename chains.** If the same check run renames `A -> B` and `B -> C`, the rewrite map collapses into `{A: C}` so that incoming references to `A` land on `C` directly. Cycles (`A -> B`, `B -> A`) are detected by step-limit plus a terminal-equals-source filter, and the affected entries are dropped from the rewrite map entirely - no phantom self-rewrites are emitted.
- **Collision on rename target.** If `_fix_filename` computes a target path that already exists on disk, the rename is skipped and the attempt is surfaced as a `Severity.ERROR` diagnostic on the `CheckResult` so the overall run does not claim success with a broken file still present.
- **UTF-8 BOM.** `_rewrite_incoming_refs` reads bytes, strips a leading UTF-8 BOM before scanning, and restores the BOM on write so BOM-authored docs (Obsidian on Windows, VS Code Git) keep their byte prefix.
- **CRLF preservation.** The same function detects `\r\n` dominance in the source, scans via `splitlines`, and rejoins on the detected newline; trailing newline is preserved when present. Mixed endings are not introduced.
- **Missing closing fence.** A fixed line-budget (`_FRONTMATTER_LINE_BUDGET = 200`) caps the scan, and a `fence_closed` flag gates the write - documents whose opening fence was never followed by a closing fence are skipped with a warning rather than risking a rewrite of prose that was mis-read as frontmatter.

## consequences

### positive

- The managed gitignore block becomes self-sufficient: clean clone or legacy clone, install leaves the working tree clean.
- CI fresh checkouts no longer surface lock sentinels as dirty state.
- prek-based projects no longer have a permanent "duplicate config" warning.
- Operators can act on our own hook's advice (`git rm --cached`) without the hook vetoing the remediation.
- Auto-fix renames stop shipping dangling links to downstream readers.

### negative

- `install` now invokes `git` via subprocess. This is acceptable - the install flow already probes git repo state via `WorkspaceLayout.git`, and failures are logged not raised.
- Skipping `_scaffold_precommit` in prek projects shifts responsibility to the operator. Mitigated by a one-shot informational log.
- The rewrite pass in `_fix_filename` costs one additional snapshot traversal per rename. With typical vault sizes (\<500 docs) the cost is negligible; the operation is bounded and not recursive.

### neutral

- The advisory-lock implementation is unchanged. If the centralised lock directory idea is pursued later, this ADR's gitignore entries become redundant but harmless.
- `.pre-commit-config.yaml` in prek projects is not added to the managed gitignore - it is simply not generated, so it will not appear in the working tree unless pre-existing.

## test contract

Every decision ships with a factory-based integration test against the real filesystem and real `git` subprocess (where applicable):

- **d1** - legacy-tracked `providers.json` scenario: stage the file via `git add`, run install, assert `git status --porcelain` reports no modifications and the file is no longer in `git ls-files`.
- **d2** - post-install assertion: after install, `git status --porcelain` is empty (no untracked `.lock` sentinels).
- **d3** - prek presence scenario: write `prek.toml` before install, assert `.pre-commit-config.yaml` is not created and the log contains the skip notice.
- **d4** - staged deletion scenario: track `.mcp.json`, stage a `git rm --cached .mcp.json`, invoke `check_staged_provider_artifacts`, assert empty result.
- **d5** - rename-with-backref scenario: seed `docA-review.md` plus `docB.md` whose `related:` list points at the stem `docA-review`, run `check_structure(fix=True)`, assert `docA-review.md` becomes `docA-review-audit.md` and `docB.md`'s `related:` list now points at the stem `docA-review-audit`.

All tests use `WorkspaceFactory` for setup; zero mocks, patches, or stubs.

## plan reference

The phased implementation is recorded in the companion plan document (linked via the `related:` frontmatter above).
