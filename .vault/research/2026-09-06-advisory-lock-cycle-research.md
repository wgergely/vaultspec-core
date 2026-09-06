---
tags:
  - '#research'
  - '#advisory-lock-cycle'
date: '2026-09-06'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:48f78b0306a3582cd7e7160e7e5e9ecc836686da288c022343af03aac6399a1c'
related: []
---

# `advisory-lock-cycle` research: `the docs/index/manifest lock cycle, reproduced and traced`

Whether the advisory-lock cycle reported in vaultspec-core#457 is real, whether it
survives vaultspec-core#451, and what actually prevents it today. It matters because the
reported cycle is not guarded by any invariant: the only thing between it and a
permanent hang is a per-process memo documented as a performance optimisation. Both
questions were settled by execution rather than by reading. The cycle closes and hangs
indefinitely on `origin/main`; the identical composition completes in one second against
vaultspec-core#451's source.

## Findings

### The cycle closes, and the re-entered sentinel is the docs domain

Composing the three reported edges against a real workspace hangs. Setup: a workspace
installed by the test factory with its manifest version forced to `0.1.73`, one plan
document and one per-Step execution record under `.vault/exec/2026-05-17-demo/` so that
`exec_ledger_only` has something to fold, and `.vault/data/` present so the docs-domain
sentinel is a real lock rather than a skipped one. `list_pending` confirms
`exec_ledger_only` is pending. `reset_workspace_cache()` is then called, and
`generate_feature_index_result(root, "demo")` is invoked while
`advisory_lock(docs_lock_target(docs_dir))` is held - which is what step (7) of a feature
rename does inside its transaction.

On `origin/main` this never returns; the probe was killed after 90 seconds having
printed only that the docs sentinel was held. With a bounded acquisition budget in place
the same probe raises, and the traceback names every hop:
`vaultcore/scanner.py:64 scan_vault` to `migrations/__init__.py:433 run_pending_migrations` to `m_0_1_74_exec_ledger_only.py:134 migrate` to
`vaultcore/exec_fold.py:405 apply_fold` to `advisory_lock`, arriving at
`.vault/data/.vault.lock` with that same sentinel already held on the same thread.

The re-entered sentinel is therefore the docs domain, not the manifest. The manifest and
feature-index sentinels are both held at the moment of the hang, but neither is the one
taken twice.

### vaultspec-core#451 removes the index-to-manifest edge

Verified against that branch's source at commit `bb2d7cef`, before it merged; the
finding is unchanged on main, where the same code now sits. Its `scan_vault` imports
and calls `warn_if_pending` rather than `run_pending_migrations`
(`vaultcore/scanner.py:62-64`), and `warn_if_pending` resolves the workspace, reads the
manifest through `migration_status`, and returns names - it takes no advisory lock and
invokes no migration body. The only `advisory_lock` call remaining anywhere in the
migrations package on that branch is inside `run_pending_migrations` itself
(`migrations/__init__.py:502`).

The probe above, run unchanged against that source, completes in 1.0 seconds. It emits
the pending-migration warning and writes `.vault/index/demo.index.md`. The edge is gone
in fact, not only by inspection.

### The convergence hook vaultspec-core#451 introduces does not re-open the edge

`ensure_migrated` calls `run_pending_migrations` directly, so any caller that takes it
under a lock re-creates the edge. All three call sites on that branch are outside every
advisory lock and ahead of the write they protect: `cli/vault_cmd.py:294` before
`vault add` resolves anything, `cli/vault_feature_cmd.py:221` before
`_run_feature_index` builds its graph, and `mcp_server/tools/documents.py:1101` before
the MCP `create` tool's first write.

That is a property of where the author put them, not a property anything enforces. No
test on that branch asserted it.

### The manifest-to-docs edge is untouched and correct

`run_pending_migrations` still takes the manifest sentinel and still calls a migration
body that takes the docs-domain one (`migrations/__init__.py:433`,
`vaultcore/exec_fold.py:405`). This is not a defect: `exec_ledger_only` rewrites vault
documents, so holding the docs-domain sentinel is what it should do. It means one edge
of the reported cycle persists on every branch examined.

### What prevents the cycle today is a performance memo

`migrations/__init__.py:389-393` short-circuits `run_pending_migrations` when the cached
workspace version already covers the registry tail. `vaultcore/query_rename.py:619`
builds an uncached `VaultGraph` during rename planning, which runs the migration and
populates that cache, so step (7)'s inner `scan_vault` never reaches the manifest. The
short-circuit logic is sound. Its status is not: the cache is per-process, is documented
under "Performance", and `reset_workspace_cache` is exported in `__all__`, so any caller
may clear it. The probe above defeats the cycle guard with one public call.

### Not investigated

Whether any path other than a feature rename holds the docs-domain sentinel while
reaching the feature-index sentinel. Whether the per-document sentinel family
participates in any cycle. Whether the same composition is reachable on POSIX with the
same timings - every measurement here is from Windows, where
`msvcrt.locking(LK_LOCK)` adds up to ten seconds of internal retry per acquire attempt.

## Sources

- `src/vaultspec_core/core/helpers.py` - `advisory_lock`, both layers.
- `src/vaultspec_core/vaultcore/query_rename_apply.py:145-175` - the transaction's hold
  of the docs-domain sentinel.
- `src/vaultspec_core/vaultcore/query_rename_apply.py:296` - step (7).
- `src/vaultspec_core/vaultcore/query_rename.py:619` - the uncached planning graph.
- `src/vaultspec_core/vaultcore/index.py:141-165` - the feature-index sentinel and the
  graph build inside it.
- `src/vaultspec_core/graph/api.py:211` - the `scan_vault` call.
- `src/vaultspec_core/migrations/__init__.py:389-393` - the workspace-cache
  short-circuit.
- `src/vaultspec_core/migrations/__init__.py:402` - the manifest sentinel on
  `origin/main`.
- `src/vaultspec_core/migrations/__init__.py:433` - the migration-body invocation.
- `src/vaultspec_core/vaultcore/exec_fold.py:405` - the docs-domain sentinel taken again.
- `src/vaultspec_core/vaultcore/edit_engine.py:705-706` - the parent-directory discipline
  a caller needs for the lock not to be skipped.
- vaultspec-core#451 at commit `bb2d7cef`, files `vaultcore/scanner.py:62-64`,
  `migrations/__init__.py:502`, `cli/_migration_hook.py`, `cli/vault_cmd.py:294`,
  `cli/vault_feature_cmd.py:221`, `mcp_server/tools/documents.py:1101`.
- https://github.com/nevenincs/vaultspec-core/issues/457
- https://github.com/nevenincs/vaultspec-core/pull/451
