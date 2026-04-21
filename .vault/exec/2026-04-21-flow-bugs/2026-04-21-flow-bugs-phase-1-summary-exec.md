---
tags:
  - '#exec'
  - '#flow-bugs'
date: '2026-04-21'
related:
  - '[[2026-04-21-flow-bugs-plan]]'
  - '[[2026-04-21-flow-bugs-adr]]'
  - '[[2026-04-21-flow-bugs-research]]'
---

# `flow-bugs` phase-1 summary

Five install-layer defects from GH issue 80 plus a round of audit-driven hardening are implemented, tested, and green on the `feature/flow-bugs` branch.

## changes landed

- `src/vaultspec_core/core/commands.py`

  - `check_staged_provider_artifacts` accepts an optional `cwd` parameter and runs `git diff --cached --name-only --diff-filter=ACMR`; staged deletions no longer block remediation commits (domain 4).
  - `_scaffold_precommit` short-circuits when `prek.toml` is present, logs a skip notice, and returns an empty manifest (domain 3).
  - New helpers `_is_git_repo`, `_untrack_managed_paths`, and constants `_UNTRACK_PREFIXES` reconcile the git index with the managed gitignore block on install: historically-committed `.vaultspec/providers.json` and orphan `.lock` sentinels get `git rm --cached`-ed (domain 1). Called from both the first-install branch and the `--upgrade --force` branch of `install_run`.

- `src/vaultspec_core/core/gitignore.py`

  - `get_recommended_entries` emits `.vaultspec/*.lock` and anchored root-level entries (`/.gitignore.lock`, `/.mcp.json.lock`, `/.pre-commit-config.yaml.lock`) when the framework is installed and the companion file exists (domain 2). The root-level entries are gated behind `framework_installed` so that bare workspaces do not accumulate spurious recommendations.

- `src/vaultspec_core/vaultcore/checks/structure.py`

  - `_fix_filename` now returns the `(old_stem, new_stem)` pair for each rename it performs.
  - New `_rewrite_incoming_refs` walks `.vault/**/*.md` and rewrites matching `[[old_stem]]` references inside `related:` frontmatter (body prose is untouched to avoid churn). Each rewrite emits an INFO diagnostic and bumps `fixed_count` (domain 5).
  - `check_structure` collects renames across the run and invokes the rewrite pass once after all renames complete, which keeps cross-file rename sequences consistent.

## tests

- New `src/vaultspec_core/tests/cli/test_flow_bugs.py` covers every domain end-to-end against a real filesystem and real `git` subprocess. Nineteen tests after audit-loop expansion (BOM, CRLF, collision, chain, cycle, and frontmatter-budget-overflow scenarios). Zero mocks, patches, stubs, skips.
- Extensions to `src/vaultspec_core/tests/cli/test_gitignore.py::TestRecommendedEntries` for the new lock-sentinel managed entries.
- Full adjacent suite (install, collectors, gitignore, vault-core checks) green.
- Default `pytest src/vaultspec_core` pass (unit + integration; excludes the `live` marker) is green after cleaning the pre-existing `test_resolver.py::TestContentRules::test_clean_content_no_steps` flake (`_make_diagnosis` now defaults `precommit=PrecommitSignal.COMPLETE`).

## audit follow-ups

From the lingering-issue sweep (phase 2 of the plan):

- `.bak` restore path in `check_dangling._remove_related_entries` and siblings is structurally sound - failure of `bak.replace(path)` intentionally preserves the backup as the only safe copy. No change made.
- `install_run` post_errors path reports errors in the return dict but does not escalate to a non-zero exit. Intentional product behaviour (partial installs succeed); out of scope for issue 80.
- Refactored `check_staged_provider_artifacts` API as part of the fix to keep the regression test free of any `monkeypatch.chdir` calls - test now passes an explicit `cwd` and touches no global process state.

## quality gates

- `ruff check src/vaultspec_core` - all checks passed.
- `ty check` on every modified module - all checks passed.
- No new `# type: ignore`, `# noqa`, `pytest.mark.skip`, or mock/patch surface was introduced.

## out of scope / deferred

- Centralised advisory-lock directory (`.vaultspec/_locks/<hash>.lock`): left as follow-up.
- Writing vaultspec hooks directly into `prek.toml`: left to operators.
- Body-link rewriting inside `_fix_filename` (only `related:` frontmatter is rewritten in this release): deferred until operator demand emerges.
- Decoupling `install --upgrade --force` from downstream `vault-fix` pre-commit behaviour: the cascade lives entirely in the pre-commit hook and is now defused by the D5 rewrite pass.

## code review

Post-implementation review by `vaultspec-code-reviewer` flagged one HIGH finding plus three MEDIUM items, all addressed:

- **HIGH** - `_untrack_managed_paths` ownership gate used a bare `stem.endswith(".lock")` tail-match. Even though only our three sentinels could reach the helper via `get_recommended_entries`, the contract was a data-loss footgun one refactor away (e.g. a future caller passing `["uv.lock"]`). Fixed by introducing a named `_MANAGED_LOCK_SENTINELS` allowlist (`.gitignore.lock`, `.mcp.json.lock`, `.pre-commit-config.yaml.lock`) and keying the gate against the basename of the candidate. Two regression tests added (`test_does_not_untrack_uv_lock`, `test_does_not_untrack_arbitrary_lock_file`) to pin the invariant.
- **MEDIUM** - `_rewrite_incoming_refs` uses a block-sequence regex rather than `vaultcore.parser.parse_vault_metadata`. Accepted and documented in the docstring: the vault template enforces block style, `vault check frontmatter` enforces it, and rewriting through the parser would re-serialise unrelated frontmatter keys (higher churn, more places to go wrong). Flow-style lists are left to `vault check frontmatter` to normalise first.
- **MEDIUM** - `_rewrite_incoming_refs` walks `.vault/**/*.md` directly rather than consuming the `VaultSnapshot` parameter. Intentional: the snapshot is stale once renames have landed. Documented in the updated docstring.
- **MEDIUM** - D4 test narrative thin. Strengthened with a sanity-check assertion that `git diff --cached --diff-filter=D` sees the deletion before the hook proves it ignores it.

No further blockers.

## next steps

- Manual smoke test against the original reporter's repro scenario.
- Open PR referencing issue 80; include the five repro items and their verification steps.
- Cut a 0.1.14 release once the PR merges.
