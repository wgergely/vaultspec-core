---
tags:
  - "#adr"
  - "#migration-registry"
date: '2026-09-06'
related:
  - "[[2026-05-01-migration-registry-adr]]"
  - "[[2026-05-01-migration-registry-research]]"
  - "[[2026-09-06-advisory-lock-cycle-adr]]"
supersedes:
  - '2026-05-01-migration-registry-adr'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:c30947f59151f3e90a77cff774b0562ce48ecc60efa66ce3d5e47818b660113a'
---

# `migration-registry` adr: `convergence follows write intent to a schema-decided location` | (**status:** `accepted`)

## Problem Statement

`2026-05-01-migration-registry-adr` chose three trigger sites for the migration driver,
and the second of them was `scan_vault`: "run lazily on first use", so that a consumer
who never runs `install --upgrade` is converged by their next vault command. Every read
shares that function, so every read converged the workspace.

Issue #443 is what that costs. A read-only MCP `find` call ran the `exec_ledger_only`
entry and deleted 47 tracked documents out of a clean worktree, then returned success.
The superseded record anticipated the mechanism and not the blast radius: it reasoned
about coverage - "every `vault*` command and every `VaultGraph` instance lands here" -
and treated the cost as a version compare, which is what the *gate* costs. What runs
after the gate opens is a workspace-wide rewrite.

vaultspec-core#451 has merged and removed the `run_migrations` flag from `scan_vault`
entirely. The code no longer implements the decision the accepted record holds, so the
record has to be replaced rather than amended: the trigger it justified is gone, and
its Alternative A - "run migration only on `install --upgrade`" - was rejected on
reasoning this record has to re-open.

## Considerations

- The registry's entries delete and relocate documents a user authored and a repository
  tracks (`src/vaultspec_core/migrations/m_0_1_74_exec_ledger_only.py`,
  `src/vaultspec_core/migrations/m_0_1_17_index_subfolder.py`). Authorisation, not cost,
  is what the trigger site decides.
- A caller that asked to read has authorised nothing. That much the superseded record
  would have granted. The sharper point is that a caller writing *one* document has no
  more standing to rewrite 47 unrelated documents than a read does: the difference
  between them is one file, not a mandate over the corpus.
- What actually distinguishes the callers that must converge is narrower than "does it
  write". It is whether the *destination* of the write is computed from the schema. A
  verb handed a path by the operator cannot be misplaced by a stale layout elsewhere; a
  verb that asks the schema where a document belongs can.
- The split-brain risk that argument has to answer is smaller than it looks. Of the ten
  registered entries, exactly one - `index_subfolder` (0.1.17) - leaves a second
  document with the same logical identity at a location the current writer no longer
  uses. The rest rewrite in place (`frontmatter_lifecycle`, `modified_stamp_backfill`,
  `body_hash_seed`), fold and delete within their own directory (`exec_ledger_fold`,
  `exec_ledger_only`), or touch something other than `.vault/` altogether
  (`gitignore_reversal`, `codex_agents_dedup`, `framework_flatten`,
  `launch_convergence`).
- Drift that nobody reports is the failure mode of issue #408 one layer up: a workspace
  upgraded by a bare package install would be read through a legacy layout indefinitely
  with nothing saying so.
- The surface a rule is drawn around is not the rule. Drawing this one around CLI verbs
  is what left the MCP `create` tool - the primary authoring surface for agents -
  writing a schema-placed feature index against a legacy layout after the scanner
  trigger came out.

## Considered options

- **Keep the lazy trigger and narrow the registry.** Only admit entries safe to run
  unbidden. Rejected: it makes every future migration's admissibility a judgement call
  at authoring time, and issue #443 shows the judgement is made years before the
  failure it decides.
- **Keep the lazy trigger and gate it on a prompt.** Rejected outright for the MCP
  surface, which has no operator to ask, and for the pre-commit hook, which has no
  terminal. A gate that cannot be answered is either a hang or a silent default.
- **Converge only on `install --upgrade` and `migrations run`** - the superseded
  record's Alternative A. Rejected for the same reason it was rejected in 0.1.17, and
  the reason is still live: `vault feature index` against an unmigrated workspace writes
  a second generated index for one feature. The objection to Alternative A was never
  about coverage in general; it was about that one write.
- **Per-command migration annotation** - the superseded record's Alternative B.
  Rejected there for a maintenance burden compounding with command count, and that
  objection survives. The chosen option is not annotation: it is one hook taken by the
  callers that meet a stated criterion, which a reviewer can apply to a new surface
  without consulting a table.
- **Chosen: converge where write intent meets a schema-decided location.**
  `install --upgrade`, `migrations run` and `vault repair` converge because converging
  is what the operator invoked them for. `vault add`, `vault feature index` and the MCP
  `create` tool converge because the schema decides where they write. Everything else -
  reads, and writes to a path the caller named - observes the corpus as found and
  reports the drift.

## Constraints

The boundary is a property of the *write*, never of the surface. `vault add`,
`vault feature index` and MCP `create` take the same hook
(`src/vaultspec_core/cli/_migration_hook.py`) because they share the property, not
because two of them are CLI verbs. Any future surface that scaffolds a document or
regenerates an index takes it too.

The hook propagates rather than degrading. A failed migration means the verb is about to
write into a layout the schema no longer describes, so the caller surfaces the failure
instead of writing anyway. On the MCP surface that makes a convergence failure a
whole-call protocol error rather than a per-item result - the envelope changes shape,
which is a fact client authors need stated rather than left to be discovered
(vaultspec-core#463).

vaultspec-core#458 is an open maintainer decision on whether an authoring verb may run
*destructive* migrations at all. This record does not answer it and must not be read as
answering it. It can only narrow the converging set below what is recorded here, never
widen it, so this boundary is an upper bound that #458 may tighten.

`2026-05-01-migration-registry-research` was written under the same lazy-trigger premise
and its "runs once per upgrade (or lazily on first use of a vault command)" framing is
historical. It stays as the record of what was known in May 2026; it is not evidence for
the current boundary and should not be cited as such.

The three converging authoring call sites all sit outside every advisory lock, which
`2026-09-06-advisory-lock-cycle-adr` covers. That containment is a separate property with
its own enforcement and is not re-argued here.

## Implementation

The architecture is not introduced by this record; it arrived with vaultspec-core#451.
What the record settles is which of the two shapes now in the history is the intended
one, because both are documented and only one is built.

`scan_vault` no longer takes a `run_migrations` parameter. There is no flag to pass, so
there is no read path that can be talked into converging by a caller who believes it
knows better. Reads call `warn_if_pending` instead, which reads the manifest, reports
pending entries once per workspace per process, and writes nothing. It never raises: a
diagnostic that can break a read is worse than a diagnostic that is occasionally absent.

Convergence is reached through one hook, `ensure_migrated`, whose module docstring
carries the criterion rather than a list of blessed verbs, so the rule can be applied to
a surface that does not exist yet. The operator-facing triggers - `install --upgrade`,
`migrations run`, `vault repair` - call the driver directly, because for them
convergence is the request rather than a precondition of it.

## Rationale

The knockout criterion is what the caller authorised, and it separates the two shapes
cleanly where "is this a vault command" does not. A read authorised nothing; a write to
a named path authorised that path; a write to a schema-decided location authorised the
schema to place it, which is the only authorisation that reaches the layout. Coverage,
which is what the superseded record optimised for, is a property the chosen boundary
still has for the one write that needed it and deliberately gives up everywhere else.

The evidence that the give-up is affordable is the registry itself. `index_subfolder` is
the sole entry whose non-application misplaces a later write, so the coverage the lazy
trigger bought was, in practice, coverage of one entry's interaction with one verb.
Paying for that with a workspace-wide rewrite behind every read is a trade that only
looks reasonable while the entries are additive, and the registry stopped being additive
at 0.1.58.

The honest weakness is that convergence now depends on the operator reaching one of six
callers. A workspace read exclusively through `find` and `vault list` stays unmigrated
indefinitely. That is the intended outcome rather than a residual: it is what "observe
the corpus as found" means, and `warn_if_pending` exists so the state is visible rather
than silent.

## Consequences

A read is a read. The class of failure issue #443 demonstrated - a query deleting
tracked documents and reporting success - is not narrowed but removed, because the
capability is gone from the call path rather than gated on it.

Unmigrated workspaces become ordinary and long-lived, which they were not before. Every
consumer of `.vault/` has to tolerate a legacy layout rather than assume the scanner
converged one, and `warn_if_pending` becomes the only thing standing between a stale
workspace and a silent one. That places real weight on a diagnostic deliberately built
never to fail loudly.

The cost of that diagnostic is a manifest read per `scan_vault` call for a workspace
with nothing pending, because the notice latches on the warning emitted rather than on
the observation - a latch on the observation would silence a workspace forever on a
first reading that might have been transient. Measured on a 7,362-file corpus that read
is 0.55 ms against a 159 ms scan and a 4.1 s graph build (vaultspec-core#464), so the
weight is on the diagnostic's design and not on its cost.

The pitfall is reading the boundary as "writes converge". Most writes do not. `edit`,
`link`, `archive`, `exec log` and `plan step check` all write and none of them
converges, because each was handed its destination. A contributor who generalises from
"this verb writes, so it takes the hook" reintroduces exactly the over-broad trigger
this record removes.
