---
tags:
  - "#adr"
  - "#migration-registry"
date: '2026-05-01'
related:
  - "[[2026-05-01-migration-registry-research]]"
  - "[[2026-04-30-vault-index-folder-adr]]"
superseded_by: '2026-09-06-migration-registry-write-boundary-adr'
modified: '2026-09-06'
body_hash: 'sha256:0ebe68dc1c66679a07c4fcfad95b0ddb68a5ee389face6e809d29af4c49d7dbc'
---

# `migration-registry` adr: versioned schema migration | (**status:** `superseded`)

## Problem Statement

PR #92 ships `_migrate_legacy_root_indexes` as a step inside
`check_structure(... fix=True)`. Because `vault check all --fix` is
the body of the default `vault-fix` pre-commit hook, the migration
re-runs on every markdown commit forever. Future schema changes would
compound this and degrade hook performance. The user has explicitly
ruled out the per-iteration-hook model. We need a versioned migration
mechanism that runs once per upgrade or first-use and never re-runs.

A second problem stems from the same conflation. In a workspace that
has not yet been migrated, `vault feature index -f foo` writes a new
index into `.vault/index/foo.index.md` while leaving the legacy
`foo.index.md` orphaned at the docs root. Two files, one logical
identity, no recovery path that the index generator itself triggers.

## Considerations

The migration mechanism needs to satisfy four user-visible properties.

- **Run once per upgrade.** The next consumer who jumps from 0.1.16 to
  0.1.17 should see migration applied automatically. A consumer who
  has already upgraded should never see migration logic touch their
  workspace again.
- **Run lazily on first use.** Not every consumer runs
  `install --upgrade` immediately. The lazy trigger means the next
  `vault add`, `vault feature index`, or `vault check` makes the
  workspace consistent without operator action.
- **Stay diagnosable.** `spec doctor` must surface migration state.
  An explicit CLI escape hatch (`migrations status`,
  `migrations run`) gives operators who distrust auto-migration a way
  to do it on demand.
- **Stay reversible mentally.** A failed migration must not leave the
  manifest version bumped. The next run must retry exactly the failing
  step.

It also needs to satisfy two implementation properties.

- The first migration entry must keep the on-disk semantics of the
  existing `_migrate_legacy_root_indexes` helper byte-for-byte
  (CRLF-aware, exact-match `#index` tag detection, atomic relocate).
- `check_structure` must stay in the detection business so a no-`--fix`
  `vault check` still tells operators about pending migrations. Only
  the mutation moves out.

Three architectural alternatives were considered.

### Alternative A - run migration only on `install --upgrade`

Simple, easy to reason about. Rejected because it leaves the lazy
path uncovered: a consumer who never runs `install --upgrade` and just
keeps using `vault add` and `vault feature index` would silently
operate against a stale schema. The `vault feature index` split-brain
bug would persist for those users until they happen to run an
upgrade.

### Alternative B - per-command migration annotation

Each command that mutates the vault declares which migrations it
requires; the command runner runs them before dispatch. Rejected
because the surface area is large (every `vault*` command and every
provider would need annotations) and the maintenance burden compounds
linearly with command count. Centralising on `scan_vault` gives the
same coverage with one insertion point.

### Alternative C - chosen: versioned registry with three triggers

A single linear chain of versioned migrations, run by a driver
function, with three trigger sites: `install --upgrade`, `scan_vault`
(lazy auto-trigger), and a `migrations` CLI subcommand for explicit
opt-in. The driver runs entries whose `target_version` exceeds the
manifest's `vaultspec_version` and bumps the manifest version on
success.

This shape mirrors Alembic's append-only chain and Django's
slug-prefixed filenames, scaled down to the linear case we need. PEP
440 version strings give us natural ordering, so we do not need to
invent hash IDs.

## Constraints

- **No mocks / patches / stubs / fakes / skips in tests.** Real
  filesystem fixtures via `WorkspaceFactory` and
  `vaultspec_core.testing.synthetic`.
- **Idempotence per migration.** A migration that has nothing to do
  must be a true no-op (no manifest write, no log noise).
- **Failure preserves version.** A migration that raises must leave
  the manifest version untouched so the next run retries.
- **Append-only.** A released migration is never edited or deleted.
  Bug fixes go into a follow-on entry.
- **Non-recurring contract.** The `vault-fix` hook docstring drops the
  migration claim. Migration is owned by the registry.

## Decision

Adopt the following architecture.

### Package layout

```
src/vaultspec_core/migrations/
  __init__.py          # registry list, MigrationResult, run_pending_migrations
  m_0_1_17_index_subfolder.py   # first entry; ports _migrate_legacy_root_indexes
```

The `m_` prefix on filenames keeps the module name a valid Python
identifier even when the version starts with a digit. The slug after
the version makes the file self-describing.

### Migration entry shape

```python
@dataclass(frozen=True)
class Migration:
    target_version: str
    name: str
    migrate: Callable[[Path], MigrationResult]


@dataclass
class MigrationResult:
    name: str
    target_version: str
    summary: str
    counts: dict[str, int]
```

Each migration module exports a module-level `MIGRATION: Migration`.
`__init__.py` imports each module and assembles `REGISTRY: list[Migration]`
in version order. Adding a new migration is a one-line append.

### Driver

```python
def run_pending_migrations(workspace: Path) -> list[MigrationResult]:
    manifest = read_manifest_data(workspace)
    if manifest.version == "":
        return []
    current = parse_version_tuple(manifest.vaultspec_version)
    pending = [
        m for m in REGISTRY
        if parse_version_tuple(m.target_version) > current
    ]
    if not pending:
        return []
    results: list[MigrationResult] = []
    for migration in pending:
        results.append(migration.migrate(workspace))
    manifest.vaultspec_version = _get_package_version()
    write_manifest_data(workspace, manifest)
    return results
```

The version bump is unconditional once any migration runs. We do not
attempt to record per-migration applied state in the manifest; the
single `vaultspec_version` field carries enough information for
linear ordered registries. This matches the existing manifest schema
without changes.

The empty-`version` early return is the no-vault-installed case: a
freshly-resolved path with no manifest must not trigger migration.

`parse_version_tuple` is promoted from the private
`_parse_version_tuple` already in `core/resolver.py`. It is the same
function with the leading underscore removed and re-exported from
`core/helpers.py` so both the resolver and the registry can use it
without circular imports.

### Trigger sites

Three call sites, in order of explicitness.

- `install_run` upgrade branch in
  `src/vaultspec_core/core/commands.py`. Before
  `write_manifest_data`. Replaces the existing
  `mdata.vaultspec_version = _get_package_version()` line with a
  `run_pending_migrations(path)` call. The driver writes the manifest
  itself, so the surrounding code does not need to.

- `scan_vault` in
  `src/vaultspec_core/vaultcore/scanner.py`. The lazy
  trigger. Every `vault*` command and every `VaultGraph` instance
  lands here on its way to disk. The check is a single
  `parse_version_tuple` comparison; cheap when up-to-date, automatic
  when behind. To avoid running migrations on every tree-walk inside
  one process invocation, the trigger guards on a per-workspace flag
  stored in module state. Subsequent calls within the same process
  short-circuit.

- `migrations status` and `migrations run` CLI. A new top-level
  sub-app at the root command level. `status` prints the current
  manifest version and the list of pending entries. `run` invokes
  the driver explicitly and prints the per-entry summaries.

### Drop migration mutation from `check_structure`

`_migrate_legacy_root_indexes` moves to the registry as
`m_0_1_17_index_subfolder.py`. The function's body is preserved
intact: same `rglob`, same exact-match `#index` tag insertion, same
CRLF-aware `_ensure_index_directory_tag`, same `atomic_write` and
`legacy.replace(target)` logic. Only the diagnostic-emitting wrapper
that reported into `CheckResult` is dropped; the registry uses
`MigrationResult` instead.

`check_structure` keeps the detection branch
(`fix=False`) as a non-mutating warning: when legacy-shaped index
files exist, the checker emits a `WARN`-severity diagnostic
("pending migration"; advises the user to run
`vaultspec-core migrations run`). The `--fix` branch no longer calls
the helper; the registry handles mutation.

The aggregate `validate_vault_structure` "Legacy feature index"
message stays in place for non-`--fix` runs because it remains a
useful structural complaint. Its language is updated to point at
`migrations run` rather than `vault check structure --fix`.

### Doctor integration

`WorkspaceDiagnosis` gains one field:

```python
migration_status: MigrationStatus = MigrationStatus.UP_TO_DATE
pending_migrations: list[str] = field(default_factory=list)
```

`MigrationStatus` is a new enum
(`UP_TO_DATE`, `PENDING`, `UNKNOWN`). The collector reads the
manifest and walks the registry the same way the driver does. The
JSON-mode `spec doctor` output is additive: existing keys stay,
`migration_status` and `pending_migrations` are new.

### Pre-commit hook contract

`.pre-commit-hooks.yaml` documentation block changes: drop the claim
that `vault-fix` performs migration. Migration is owned exclusively
by the registry.

## Idempotence and version-gating semantics

- **Idempotence.** A migration's `migrate` body must be safe to run on
  a workspace that has already been migrated. The driver's
  version-gate prevents this in normal operation, but a migration that
  is run via `migrations run` after the version has already been
  bumped to a higher value must still be a no-op. The first migration
  achieves idempotence by design: `rglob` returns no legacy files in
  a migrated workspace.
- **Version-gating.** Strict greater-than comparison. A migration with
  `target_version == manifest.vaultspec_version` does not run.
- **Failure handling.** If any migration in the pending list raises,
  the driver re-raises and does not bump the manifest version.
  The next invocation re-attempts from the same starting version.
  The driver does not catch and continue: a failing migration is a
  hard stop because subsequent migrations may depend on its
  completion.
- **Logging.** The driver logs one `INFO` line per migration summary
  via the standard `vaultspec_core.migrations` logger. No
  per-file noise.

## Tests

The acceptance tests live alongside the registry as
`src/vaultspec_core/migrations/tests/`. Mechanics tests
(idempotence, ordering, failure semantics) use synthetic
single-purpose migration entries built ad-hoc in fixtures, exercising
the driver against a real on-disk manifest. The first-entry tests
re-use the existing legacy-index test corpus moved out of
`vaultcore/checks/tests/test_index_migration.py` (the
`_ensure_index_directory_tag` tests stay where they are because the
helper itself stays in `vaultcore/checks/structure.py` for the
warning branch).

Trigger-site tests use `WorkspaceFactory` to plant a stale
`vaultspec_version` and a legacy index, then invoke the relevant
command (`install --upgrade`, `vault add`, `vault feature index`)
through the CLI runner and assert post-state.

## Migration entries

| Version | Slug            | Purpose                                                                                               |
| ------- | --------------- | ----------------------------------------------------------------------------------------------------- |
| 0.1.17  | index_subfolder | Relocate root-level `<feature>.index.md` files into `.vault/index/` and ensure `#index` directory tag |

Future entries follow the same shape.
