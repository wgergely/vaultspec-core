---
tags:
  - '#adr'
  - '#migration-convergence-scope'
date: '2026-09-06'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:2bc9eea02794fad36d006718f07e21e9bcd4ac7cec630ff5ca92ffd518d5e7bd'
related:
  - "[[2026-05-01-migration-registry-research]]"
  - "[[2026-05-01-migration-registry-adr]]"
  - "[[2026-04-30-vault-index-folder-adr]]"
---

# `migration-convergence-scope` adr: `Scoped migration convergence for authoring verbs` | (**status:** `accepted`)

## Problem Statement

`ensure_migrated` runs the entire migration registry on behalf of three authoring
callers - `vaultspec-core vault add`, `vaultspec-core vault feature index`, and the MCP
`create` tool. The registry's entries relocate, rewrite, and unlink tracked `.vault/`
documents. So a user who has not opened a workspace for months and types
`vaultspec-core vault add adr --feature auth` receives one new ADR and, on the same
keystroke, the execution-record folds across the whole corpus: per-Step records and
Phase Summaries removed, nothing prompted, nothing previewed, the removals named only in
retrospect.

Two reviews reached opposite conclusions from that asymmetry, and both were right about
something. A code review established that the convergence is load-bearing: an index
regenerated against a pre-0.1.17 layout leaves one feature with two tracked
`generated: true` indexes carrying divergent `related:`, reproduced over a live MCP
transport. A data-safety audit established that the blast radius is unbounded and
unrelated to what the caller asked for, and that
`src/vaultspec_core/cli/_migration_hook.py` already states the governing principle for
`vault edit`, `link`, and `archive`: such a verb has no more standing to rewrite
forty-seven unrelated documents than a read does.

The decision is which of those two facts constrains the other. It could not be deferred
further: the hook is the last unbounded destructive trigger left after
`2026-05-01-migration-registry-adr` moved the trigger out of `scan_vault`.

## Considerations

- Both reviews argue about the same call, and neither disputes the other's evidence. The
  split brain is real and the blast radius is real, so any resolution that denies one of
  them is answering a different question.
- The registry's entries are not one kind of thing. `index_subfolder` (0.1.17) decides
  where a generated index lives; `exec_ledger_fold` (0.1.58) and `exec_ledger_only`
  (0.1.74) unlink documents a human wrote; `framework_flatten` (0.1.35) never touches
  `.vault/` at all. Treating them as one set is what forced the choice to be
  all-or-nothing.
- Exactly one registered entry decides where an authored document lands, verified
  against the registry as it stands: `index_subfolder`. Every other entry rewrites in
  place, folds and deletes, or mutates `.vaultspec/`.
- Pre-deletion snapshots into `.vault/.trash/` now cover every migration removal,
  shipped after this question was raised. They change the severity of the failure, not
  its character - see Rationale.
- The registry declares its entries as `Migration` dataclass instances built in
  `src/vaultspec_core/migrations/__init__.py`, which is the structure a declared
  classification extends.
- `2026-05-01-migration-registry-adr` establishes idempotence as a registry-wide
  requirement, which is what makes a partial run cheap to re-attempt.

## Considered options

- **Scoped convergence (chosen).** The hook runs only entries that decide where a write
  lands, never those that rewrite or remove user content. Closes the split brain and
  authorises zero deletions from an authoring verb. Costs a classification the registry
  must maintain and leaves the content entries pending until an operator converges.
- **Full convergence, made consistent.** Keep the whole registry in the hook and accept
  it on every authoring surface. Restores parity and closes the split brain, but leaves
  the blast radius exactly as the audit described it: one document written, an unbounded
  number rewritten or deleted. Rejected - it answers the split brain by conceding the
  data-safety objection outright, and the objection is correct.
- **No convergence on authoring verbs.** Delete the hook; warn through `warn_if_pending`
  only. Safest for content and the smallest change. Rejected - it reintroduces the
  duplicate-index defect that put the trigger in `scan_vault` originally, and it does so
  on the agent-facing `create` surface where nobody is reading the warning. Safety that
  is bought by writing a knowingly wrong file is not safety.
- **Prompt before the destructive entries.** Keep full convergence and confirm
  interactively. Rejected - `create` has no operator to prompt, and a prompt attached to
  `vault add adr` asks the user to adjudicate a corpus-wide fold they did not invoke and
  cannot evaluate at that moment.
- **Hard-code the eligible entry by name in the hook.** Cheapest expression of the same
  behaviour. Rejected - the safety property then lives in the caller rather than in the
  migration, so a new destructive entry is admitted by default and the omission is
  invisible at the point where it is made.

## Constraints

- The manifest carries one `vaultspec_version` scalar whose meaning is that every entry
  at or below it has run. A partial run must not violate that, or the skipped entries
  read as applied and retire permanently.
- The per-process workspace cache in `run_pending_migrations` is shared by scoped and
  unscoped callers, so a scoped run must not record a workspace as fully converged.
- `TestAuthoringVerbTrigger` in
  `src/vaultspec_core/tests/cli/test_migration_triggers.py` and
  `src/vaultspec_core/tests/cli/test_readonly_migration_boundary.py` pin the existing
  boundary from both sides. The relocation half must survive unchanged.
- The classification must be declared by each migration and default to the safe reading,
  so an entry added without thought is excluded rather than admitted.

## Implementation

Each registry entry declares a `MigrationScope`: `WRITE_PLACEMENT` for an entry that
decides where a newly authored document lands, `DOCUMENT_CONTENT` for one that rewrites
or removes documents a human wrote, `ENVIRONMENT` for one that mutates `.vaultspec/` or
host configuration and no `.vault/` document. The field lives on the `Migration`
dataclass and defaults to `DOCUMENT_CONTENT`, so silence excludes an entry from the
authoring hook rather than admitting it. Declaring the permissive value is a deliberate
act at the call site, and a test reads each entry's defining source to require the
keyword rather than accept the default.

`run_pending_migrations` takes a `scopes` entitlement. `None` runs the whole registry
and is what the three operator-facing convergence verbs pass. `ensure_migrated` passes
`WRITE_PLACEMENT_SCOPES`, so an authoring write converges the placement of its own
document and nothing else.

Version bookkeeping preserves the manifest's invariant by bumping only through the
unbroken prefix of pending entries actually run, stopping at the first skip. An in-scope
entry above a skipped one still runs - the entitlement is per entry, not a ceiling - it
simply does not advance the recorded version. Re-running it next invocation is free
under the registry's idempotence requirement. The cache short-circuit reads the tail of
the caller's eligible subset rather than of the whole registry, so a workspace that is
permanently short of up to date still costs a warm authoring verb one dictionary lookup.

The residue is announced, not deferred in silence: after a successful scoped run the
hook calls `warn_if_pending`, which names the outstanding entries and the command that
applies them, sharing its once-per-workspace latch with the read path. The warning's
wording moves from read-specific to surface-neutral.

## Rationale

The two reviews are only in conflict while the registry is one undifferentiated set.
Split it by what each entry does and both hold at once: the split brain exists because a
write lands where the schema says, so fixing placement is the verb's own business; the
deletions are unbounded because they concern documents the verb never named, which is
someone else's business entirely. The scoped hook is the smallest boundary that grants
the first and refuses the second, and it makes the authoring verbs consistent with
`vault edit`, `link`, and `archive`, which the hook module already governs by exactly
this reasoning.

The registry as it stands makes the trade almost free: one entry is eligible, and it is
confined to documents the schema itself placed. Its single deletion - a legacy duplicate
of an index that already exists at the canonical path - is a generated artifact, and it
is snapshotted before it goes.

On the snapshots. Pre-deletion capture into `.vault/.trash/` landed after this question
was raised, and it genuinely lowers the stakes: the pre-snapshot failure was
unrecoverable for anything uncommitted, and it is now recoverable by copying files back.
That moved this decision out of the data-loss class. It did not move it far enough to
change the answer, for three reasons. Recovery is manual, per file, and only begins once
the user notices - and the whole complaint is that nothing told them. The user is left
holding a corpus they did not ask to have restructured, which is a real cost even when
every byte survives. And a safety net is a reason to be less afraid of a mistake, not a
reason to keep making it: the argument that an authoring verb may delete forty-seven
documents because they can be dug out of `.trash/` afterwards is not one this project
should accept. The honest effect of the snapshots is that this ADR is a
correctness-and-consent decision rather than an incident response, which is why it is
being decided on its merits rather than in a hurry.

Declaring the classification on the migration rather than listing names in the hook is
what makes the property durable. The question a new entry has to answer - does an
authoring write depend on this having run - is answerable only by its author, at the
moment they write it, and a default that fails safe means forgetting to answer costs a
deferred convergence rather than an unauthorised deletion.

## Consequences

An authoring verb can no longer remove or rewrite a document its caller did not name, on
any surface, however stale the workspace. The duplicate-index defect stays closed. The
three operator verbs are unchanged, and `migrations run` still previews every removal
and asks before proceeding.

A stale workspace now stays partially migrated across authoring commands, indefinitely,
until someone converges it. That is the deliberate cost, and it is the reason the
pending notice matters more than it used to: a deferral nobody is told about is just a
slower version of the drift issue #408 described. The `warn_if_pending` latch fires once
per workspace per process, which in the long-lived MCP server means one notice rather
than one per call - adequate, but worth revisiting if operators report missing it.

The classification is a new obligation on every future migration. The default protects
against forgetting it, and the guard test against leaning on the default, but a
migration mis-declared as `WRITE_PLACEMENT` would restore the old blast radius silently.
That is the sharp edge this design deliberately concentrates in one reviewable keyword.

The value of this decision drops if the destructive entries stop being lossy, and rises
while they remain so. Nothing here forecloses either direction: the scope is a statement
about authority, not about how much a migration costs when it runs.
