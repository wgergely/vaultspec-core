---
tags:
  - '#adr'
  - '#advisory-lock-cycle'
date: '2026-09-06'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:52ced8c4baf835d489c867723d95f2deefed22547aa3bdeb0ce2c64b55b29de9'
related:
  - "[[2026-09-06-advisory-lock-cycle-research]]"
  - "[[2026-08-13-plan-mutation-concurrency-adr]]"
---

# `advisory-lock-cycle` adr: `break the docs/index/manifest advisory-lock cycle by construction` | (**status:** `proposed`)

## Problem Statement

`advisory_lock` is not reentrant: a caller that reaches the same sentinel twice on one
thread waits on itself, and until now waited forever. Three edges between the docs,
feature-index and manifest sentinel families close such a cycle, and the composition
hangs indefinitely when executed
(`2026-09-06-advisory-lock-cycle-research`). The sentinel taken twice is the docs
domain, `.vault/data/.vault.lock`, re-entered by a migration body running underneath a
`RenameTransaction` that already holds it.

What keeps the cycle off the live paths is not an invariant. It is the per-process
workspace memo at `src/vaultspec_core/migrations/__init__.py:389-393`, which rename
planning happens to populate before the transaction opens
(`2026-09-06-advisory-lock-cycle-research`). The short-circuit is sound; the objection is
to its status. It is documented under "Performance", its invalidator is exported in
`__all__`, and one public call re-arms a permanent hang with nothing anywhere saying so.

A decision is needed now because the cycle's most important edge is being moved for
unrelated reasons in vaultspec-core#451, and because the same registry entry is the
subject of vaultspec-core#458. This record settles only how the cycle is broken. It does
not settle whether authoring verbs may run destructive migrations at all, which is
vaultspec-core#458's question.

## Considerations

- The cycle is reproducible and its re-entered sentinel is the docs domain, not the
  manifest (`2026-09-06-advisory-lock-cycle-research`).
- The property that prevents it is a performance memo whose invalidator is public API
  (`src/vaultspec_core/migrations/__init__.py:389-393`).
- vaultspec-core#451 removes the index-to-manifest edge, verified by executing the same
  composition against its branch rather than by reading it
  (`2026-09-06-advisory-lock-cycle-research`).
- vaultspec-core#451 does not remove the manifest-to-docs edge, and should not:
  `exec_ledger_only` rewrites vault documents (`src/vaultspec_core/vaultcore/exec_fold.py:405`).
- vaultspec-core#451's three convergence call sites all sit outside every advisory lock,
  by their author's placement rather than by any enforced property
  (`2026-09-06-advisory-lock-cycle-research`).
- The rename path takes no convergence hook on either branch, so with the edge cut a
  feature rename against a stale workspace proceeds under a legacy layout rather than
  deadlocking (`src/vaultspec_core/vaultcore/query_rename_apply.py:296`).
- `advisory_lock` now bounds both layers on one shared budget
  (`src/vaultspec_core/core/helpers.py`), so a surviving or future cycle reports rather
  than hangs. That is a diagnostic, not a fix: it converts an unbounded hang into a
  failed command.

## Considered options

- **Hoist the migration trigger out of `VaultGraph`/`scan_vault`.** Cuts the
  `index to manifest` edge, so no lock-holding caller can transitively reach the
  registry. Already implemented by vaultspec-core#451 for a different reason, and
  verified above to close the cycle as a side effect. Cost: the safety is positional,
  so it holds only while every future convergence call site stays outside every lock,
  and nothing enforces that.
- **Make `advisory_lock` reentrant per (thread, sentinel).** Removes the deadlock for
  every cycle at once, present and future, rather than for this one. Rejected as the
  primary remedy: reentrancy does not make the re-entered critical section correct. The
  inner `apply_fold` would proceed believing it holds the docs domain exclusively while
  the outer `RenameTransaction` holds a snapshot taken before the fold, and the
  transaction's rollback journal would be reversing a tree the migration had rewritten
  underneath it. Deadlock at least fails loudly; a reentrant lock would turn this into
  silent corruption of a rename rollback.
- **Add a bounded timeout and nothing else.** Rejected as a resolution, adopted as a
  floor. It makes the cycle diagnosable but leaves a `vault feature rename` against a
  stale workspace failing rather than working, which is a worse user-facing outcome
  than the cache currently delivers.
- **Assert the absence of the edge in a test.** Rejected on its own, kept as a
  complement to the first option: a test that fails when a convergence call appears
  under a lock is what converts positional safety into enforced safety.
- **Keep relying on the workspace cache and document it as load-bearing.** Rejected.
  Re-labelling `reset_workspace_cache` as correctness-critical would make a
  performance memo a public invariant and forbid clearing it in tests, which is what it
  exists for.

## Constraints

vaultspec-core#451 is open, not merged. Everything this record recommends is
conditional on it landing; if it is closed unmerged, the `index to manifest` edge
returns and the first option has to be implemented independently.

vaultspec-core#458 is an open maintainer decision on whether authoring verbs may run
destructive migrations at all. It can only narrow the set of callers that reach
`run_pending_migrations`, never widen it, so it cannot re-open an edge this record
closes. The two are orthogonal and this record does not pre-empt it.

The `manifest to docs` edge is structural and is not addressed here. `exec_ledger_only`
rewrites vault documents, so it must take the docs-domain sentinel; the edge is correct
and stays.

`advisory_lock`'s skip when a sentinel's parent directory is absent is left in place. It
is relied on by `_apply_rename_plan`, which documents never creating `.vault/data`, and
by every preview path; the callers that must not skip create the parent first
(`src/vaultspec_core/vaultcore/edit_engine.py:705-706`,
`src/vaultspec_core/vaultcore/index.py:142-143`). It now logs a warning rather than
skipping silently, but the residual - a feature rename running unprotected on a
workspace with no `.vault/data` - is a live gap this record notes and does not fix.

## Implementation

Nothing is implemented by this record. The recommendation is to adopt vaultspec-core#451
as the resolution of this cycle and to add the enforcement it lacks.

The enforcement is a lock-graph containment test in the spirit of the existing sentinel
policy suite: acquire each sentinel family in turn, run the authoring surfaces under it,
and fail if any of them reaches `run_pending_migrations`. Stated as a property rather
than as a list of call sites, so a convergence hook added to a future surface is caught
by the same assertion instead of needing to be remembered.

The bounded acquisition budget stays as the backstop underneath both. It is what turns
the next cycle - in a call graph nobody has walked yet - into a report naming the
sentinel and the likely cause, rather than a process that has to be killed to be
understood.

The rename path's missing convergence is recorded as a separate question for
vaultspec-core#458 rather than answered here. With the edge cut, a stale workspace makes
`vault feature rename` write against a legacy layout instead of hanging; whether that is
acceptable is exactly the write-intent boundary vaultspec-core#458 owns.

## Rationale

The knockout criterion is what happens to the critical section, not what happens to the
wait. Both candidate options stop the hang, and only one of them leaves the invariant
the lock exists to hold. Reentrancy would let `apply_fold` mutate the docs tree inside a
`RenameTransaction` that has already snapshotted it, so the transaction's reverse
journal would restore a pre-migration tree over post-migration state on any subsequent
failure - the lock would be doing nothing where it currently does something, and doing
it silently. Cutting the edge removes the re-entry instead of permitting it, and leaves
every sentinel meaning what it says.

The evidence favours the same option for a second reason: the work is done. The
composition that hangs on `origin/main` completes on vaultspec-core#451's branch
(`2026-09-06-advisory-lock-cycle-research`), so the recommended change has been executed
and observed rather than designed. Choosing reentrancy would mean re-opening a resolved
edge in order to permit it.

The honest weakness is that the resulting safety is positional. Nothing in
vaultspec-core#451 stops a future caller putting `ensure_migrated` inside a lock; the
three current call sites are outside every lock because their author put them there.
That is why the recommendation is vaultspec-core#451 plus a containment test, not
vaultspec-core#451 alone. A property that holds by inspection today is one refactor away
from not holding, and this cycle is the demonstration of how long such a property can be
wrong before anyone notices.

## Consequences

The cycle stops depending on a cache. `reset_workspace_cache` returns to being what its
docstring says it is, and a test that clears it stops silently re-arming a hang.

The `manifest to docs` edge survives and should be expected to appear in future
analyses. It is correct: a migration that rewrites vault documents must hold the
docs-domain sentinel. What must not recur is a lock holder reaching the registry, which
is the single property the containment test would pin.

`vault feature rename` against a stale workspace changes failure mode rather than
becoming correct. It stops hanging and starts writing against whatever layout is on
disk. That is an improvement over a permanent hang and a regression against the accident
that the cache was producing, and it is left open deliberately for vaultspec-core#458
rather than being settled by implication here.

The pitfall is reading the bounded budget as the fix. It is not. A command that reports
`Timed out after 120s waiting for the advisory lock on .vault/data/.vault.lock (thread layer)` has still failed to do what the operator asked; the budget only ensures they can
find out why in one run instead of by attaching a debugger to a wedged process.
