---
tags:
  - '#plan'
  - '#flow-bugs'
date: '2026-04-21'
related:
  - '[[2026-04-21-flow-bugs-adr]]'
  - '[[2026-04-21-flow-bugs-research]]'
---

# `flow-bugs` plan: install-layer hygiene fixes

## scope

Implement the five decisions in `[[2026-04-21-flow-bugs-adr]]`. Single phase; each decision is a separate step record under `.vault/exec/2026-04-21-flow-bugs/`.

## phase 1 - install-layer hygiene

### step 1 - domain 4 - `check-providers` respects deletions

Target: `src/vaultspec_core/core/commands.py` line 221.

- Add `--diff-filter=ACMR` to the `git diff --cached --name-only` command.
- Add `src/vaultspec_core/tests/cli/test_check_providers.py` with two tests: one verifying additions are still flagged, one verifying deletions are not.
- Use a real git repo in `tmp_path` - no mocks.

### step 2 - domain 2 - lock sentinels in managed gitignore

Target: `src/vaultspec_core/core/gitignore.py` `get_recommended_entries`.

- Within the existing try block, after `entries.add(".vaultspec/")`, add `.vaultspec/*.lock`.
- After `(target / ".mcp.json").exists()` branch, add the root-level lock entries for each of the three companion files when they exist:
  - `.gitignore.lock` when `.gitignore` exists.
  - `.mcp.json.lock` when `.mcp.json` exists.
  - `.pre-commit-config.yaml.lock` when `.pre-commit-config.yaml` exists.
- Extend `src/vaultspec_core/tests/cli/test_gitignore.py` with a test that installs, triggers an `advisory_lock` via a no-op call against each companion, asserts `git status --porcelain` is empty.

### step 3 - domain 3 - prek skip

Target: `src/vaultspec_core/core/commands.py` `_scaffold_precommit` at lines 302-420.

- At the top of the function, check `(target / "prek.toml").exists()`. If true, log `logger.info("prek.toml detected; skipping .pre-commit-config.yaml scaffold. Add hooks to prek.toml manually.")` and return `[]`.
- Add a test in `src/vaultspec_core/tests/cli/test_install.py` (or a new `test_precommit_scaffold.py`) that writes `prek.toml` into a factory-built workspace, calls install, asserts `.pre-commit-config.yaml` does not exist post-install, and that the expected log message fired.

### step 4 - domain 1 - untrack historically-tracked managed paths

Target: `src/vaultspec_core/core/commands.py`. Add a helper `_untrack_managed_paths(target, entries)` that:

1. Returns early unless `(target / ".git").is_dir()` (works with worktrees too - detect via `.git` file or dir).
1. Filters `entries` to those strictly under `.vaultspec/` or under a recorded provider directory (read manifest; do not untrack root-level entries like `.mcp.json` / `CLAUDE.md`).
1. Invokes `git ls-files --error-unmatch <path>` per candidate in a single `git ls-files` batch to determine which are tracked.
1. Runs `git rm --cached --ignore-unmatch -- <path>...` for the tracked subset in one call.
1. Logs each untracked path at INFO level.
1. Any subprocess failure is caught and logged as a warning; install continues.

Call the helper from `install_run` after `ensure_gitignore_block` succeeds, both in the first-install and `--upgrade` branches.

Add a test in `src/vaultspec_core/tests/cli/test_install_untrack.py`: initialise a git repo, commit a placeholder `.vaultspec/providers.json`, run install, assert `git ls-files --error-unmatch .vaultspec/providers.json` exits non-zero (= no longer tracked) and `git status --porcelain` reports only the expected un-untracked entries.

### step 5 - domain 5 - rename updates incoming wiki-link references

Target: `src/vaultspec_core/vaultcore/checks/structure.py` `_fix_filename`.

- After the first `doc_path.rename(new_path)` block (suffix rename), call a new module-private `_rewrite_incoming_refs(old_stem, new_stem, snapshot_root)` that:
  - Walks every `*.md` file under `snapshot_root` (via the existing `_base.VaultSnapshot` iteration).
  - For each document, parse its frontmatter via `vaultcore.parser.parse_vault_metadata`, check `related:` entries for `[[<old_stem>]]`, rewrite to `[[<new_stem>]]`.
  - Write changes back via `atomic_write`.
  - Return the count of updated documents.
- Append a diagnostic per updated document to `result.diagnostics` (severity INFO, message `"Updated wiki-link: [[<old>]] -> [[<new>]]"`).
- Apply the same after the date-prefix rename block.
- Add `src/vaultspec_core/vaultcore/checks/tests/test_structure_rename.py` with the rewrite scenario from the ADR's test contract.

## phase 2 - lingering issue audit (domain 6)

Post-execution sweep:

- Run the full test suite (`pytest -xvs`) to verify no regression.
- Inspect `guards.py`, `gitignore.py`, `commands.py` for any similar "compute managed surface but don't reconcile with git" patterns.
- Inspect `advisory_lock` callers for any path that would leak a sentinel outside `.vaultspec/`.
- Check CHANGELOG plus release notes draft entries for each decision.

Findings from phase 2 are captured in the phase summary under `.vault/exec/2026-04-21-flow-bugs/` and, if any surface new code changes, a follow-up step record.

## verification

- All existing tests pass on the `feature/flow-bugs` branch.
- New tests pass.
- Manual dry-run against a throwaway git repo with committed `.vaultspec/providers.json` demonstrates the untrack.
- `vaultspec-code-review` agent audits the final diff before merge.

## out of scope

- Centralised `advisory_lock` redirect to `.vaultspec/_locks/`.
- Writing vaultspec hooks into `prek.toml`.
- Body-link rewriting in `_fix_filename` (only `related:` frontmatter rewrites ship).
- Decoupling `install --upgrade --force` manifest repair from any downstream hook cascade (the cascade lives in the pre-commit hook, not install itself).
