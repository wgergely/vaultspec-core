---
tags:
  - '#adr'
  - '#vault-doctor-suite'
date: '2026-02-24'
related:
  - '[[2026-02-24-vault-doctor-suite-research]]'
  - '[[2026-02-24-vault-doctor-suite-p1-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p2-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p3-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p4-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p5-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p6-plan]]'
  - '[[2026-02-24-vault-doctor-suite-plan]]'
---

# `vault-doctor-suite` adr: Vault Doctor Suite Architecture | (**status:** `accepted`)

## Problem Statement

The vault verification system grew organically around `vault audit`. That command is now
feature-saturated and is removed. Several check domains (graph invalid-links, orphan detection)
exist in isolation and are not wired into any user-facing command. Critical gaps remain around
chain integrity, frontmatter format drift, and fix safety. The existing `fix_violations()` function
modifies files without a dry-run mode. A coherent replacement architecture is needed that can host
new check domains, expose them composably, and work cleanly with pre-commit hooks.

## Considerations

### Option 1 — Expand `vault audit` Flags

Add more flags to the existing `vault audit` command (`--chain-check`, `--link-check`, etc.) and
expand `fix_violations()` with a `dry_run` parameter.

**Pro:** Minimal surface area change.
**Con:** `audit` is already overloaded and is being removed. Adding more flags to a command slated
for removal is counter-productive. The audit command is not structured to register checks dynamically.

### Option 2 — New `vault doctor` Subcommand with Registered Checks

Introduce `vaultspec vault doctor` as the sole dedicated command for vault content health. Doctor
checks are individually registered and addressable by name or category. The command supports
`--dry-run`, `--fix`, `--input`, `--check`, `--severity`, and `--json`.

**Pro:** Clean separation of concerns, composable, extensible. Pre-commit hooks pass staged files
via `--input` or positional args. Severity model is native to the command design. No legacy surface
to maintain.
**Con:** New CLI surface to document and maintain.

### Option 3 — Standalone Doctor Module Called by Both CLI Paths

A `doctor/` module invoked by both `vault audit --verify` (backward compat) and a new
`vault doctor` command.

**Pro:** Reuses existing integration point while enabling a richer interface.
**Con:** `vault audit` is removed — there is no dual-path to support. This option is moot.

## Implementation

**Adopt Option 2.**

`vaultspec vault doctor` is the primary and sole interface for vault content health checks.
`vault audit` is removed entirely — no shim, no deprecation notice, no sunsetting period.

The doctor suite introduces a `src/vaultspec/doctor/` module:

```
src/vaultspec/doctor/
├── __init__.py           — public exports
├── registry.py           — check registration and suite runner
├── models.py             — DoctorResult, Severity, CheckCategory
├── checks/
│   ├── __init__.py
│   ├── links.py          — broken wikilinks, orphan detection
│   ├── chain.py          — plan→adr, adr→research, exec→plan chain integrity
│   ├── drift.py          — frontmatter format drift (dates, features, CRLF, etc.)
│   ├── coverage.py       — per-feature doc-type coverage matrix
│   └── structure.py      — stray files, unsupported dirs (delegates to existing api)
└── fixes/
    ├── __init__.py
    ├── safe_writer.py    — atomic write with dry-run support
    └── frontmatter.py    — frontmatter normalization fixes (dry-run aware)
```

### Three-Mode Contract

| Mode                 | Invocation                     | Reads | Writes | Output                       |
| -------------------- | ------------------------------ | ----- | ------ | ---------------------------- |
| **report** (default) | `vault doctor`                 | yes   | no     | issue list                   |
| **preview**          | `vault doctor --fix --dry-run` | yes   | no     | what *would* change          |
| **modify**           | `vault doctor --fix`           | yes   | yes    | issue list + applied changes |

`--dry-run` is only meaningful with `--fix`. Without `--fix`, `--dry-run` is rejected with an
error. The default mode is always safe — no writes without `--fix`.

### Check Registry Design

```python
@dataclass
class DoctorCheck:
    name: str                  # e.g. "exec-plan-chain"
    category: CheckCategory    # LINKS | CHAIN | DRIFT | COVERAGE | STRUCTURE
    severity: Severity         # ERROR | WARNING | INFO
    fixable: bool
    run: Callable[[Path, list[Path] | None], list[DoctorResult]]
    fix: Callable[[Path, bool], list[DoctorResult]] | None  # dry_run param
```

The `run` callable accepts an optional `input_paths` argument. When provided, checks scope their
results to those paths only. Aggregate checks (chain, coverage) that require a full vault graph
still build the full graph but filter results to input paths.

### DoctorResult Model

```python
@dataclass
class DoctorResult:
    path: Path
    check: str          # check name
    severity: Severity  # ERROR | WARNING | INFO
    message: str
    fix_available: bool
    fix_applied: bool = False
    fix_detail: str = ""
```

### Dry-Run Contract

Every fix function accepts `dry_run: bool`. When `dry_run=True`:

- No filesystem writes occur
- Returned `DoctorResult` has `fix_applied=False`, `fix_detail` describes the planned action
- Log lines are prefixed `[DRY-RUN]`

`safe_writer.py` centralises this pattern for atomic frontmatter rewrites and file renames.

### Severity Model

| Severity  | Meaning                                                  | Pre-commit behavior           |
| --------- | -------------------------------------------------------- | ----------------------------- |
| `ERROR`   | Structural violation — breaks parsing or chain integrity | Fail (exit 1)                 |
| `WARNING` | Advisory drift — valid but inconsistent                  | Pass by default, configurable |
| `INFO`    | Informational — coverage gaps, style suggestions         | Pass always                   |

Pre-commit integration uses `--severity error` by default.

### CLI Interface

```
vaultspec vault doctor [FILES...] [options]

Arguments:
  FILES                Specific files to check. If omitted, the full vault is scanned.

Options:
  -i, --input <file>   Additional file to include (repeatable; merged with positional FILES)
  --check <name>       Run only the named check (repeatable)
  --category <cat>     Run only checks in a category: links|chain|drift|coverage|structure
  --severity <level>   Minimum severity to report: error|warning|info  (default: info)
  --fix                Apply available fixes
  --dry-run            Preview fixes without writing (requires --fix)
  --json               Machine-readable JSON output
  --limit <n>          Limit items per check in output (default: 20)
  --feature <name>     Scope checks to a specific feature
```

`FILES` and `--input` are equivalent and merged. Positional args are the natural form for
pre-commit hooks (`pass_filenames: true`). `--input` / `-i` is useful for scripting.

### Check Domains and Categories

#### STRUCTURE (fast, delegates to existing)

| Check              | Severity | Fixable | Notes                                 |
| ------------------ | -------- | ------- | ------------------------------------- |
| `unsupported-dirs` | ERROR    | No      | Delegates to `verify_vault_structure` |
| `stray-files`      | WARNING  | No      | Files in `.vault/` root               |

#### LINKS (requires graph construction)

| Check               | Severity | Fixable | Notes                                      |
| ------------------- | -------- | ------- | ------------------------------------------ |
| `broken-wikilinks`  | ERROR    | No      | `get_invalid_links()` wired into doctor    |
| `orphaned-docs`     | WARNING  | No      | `get_orphaned()` wired into doctor         |
| `malformed-related` | ERROR    | Yes     | `related` entries not in `wikilink` format |

#### CHAIN (requires graph + doc-type awareness)

| Check                   | Severity | Fixable | Notes                                               |
| ----------------------- | -------- | ------- | --------------------------------------------------- |
| `exec-plan-link`        | ERROR    | No      | Exec `related` must contain a valid plan wikilink   |
| `plan-adr-link`         | WARNING  | No      | Plan should have at least one linked ADR            |
| `adr-research-link`     | WARNING  | No      | ADR should have at least one linked research        |
| `feature-plan-coverage` | ERROR    | No      | Every feature tag must have a plan (existing check) |

#### DRIFT (per-file, no graph needed)

| Check                    | Severity | Fixable | Notes                                     |
| ------------------------ | -------- | ------- | ----------------------------------------- |
| `filename-date-drift`    | ERROR    | Yes     | Filename date ≠ frontmatter date field    |
| `filename-feature-drift` | ERROR    | Yes     | Filename feature ≠ feature tag            |
| `unquoted-date`          | WARNING  | Yes     | `date: 2026-02-18` (YAML date object)     |
| `crlf-endings`           | WARNING  | Yes     | Windows line endings in frontmatter       |
| `duplicate-tags`         | ERROR    | Yes     | Same tag appears more than once           |
| `bom-detected`           | WARNING  | Yes     | BOM character at file start               |
| `extra-fields`           | INFO     | No      | Frontmatter fields outside schema         |
| `missing-related-field`  | INFO     | Yes     | `related` absent; normalize to empty list |

#### COVERAGE (aggregate, no graph needed)

| Check                     | Severity | Fixable | Notes                                        |
| ------------------------- | -------- | ------- | -------------------------------------------- |
| `feature-coverage-matrix` | INFO     | No      | Per-feature doc-type presence/absence report |

### Pre-commit Hook Integration

`vault doctor` is the pre-commit hook entry point. With `pass_filenames: true`, pre-commit appends
staged filenames as positional args and doctor scopes all checks to those files only:

```yaml

- id: vault-doctor
  name: Vault Doctor
  entry: uv run python -m vaultspec vault doctor --severity error
  language: system
  types: [markdown]
  pass_filenames: true
```

For the heavier chain and link checks (opt-in):

```yaml

- id: vault-doctor-deep
  name: Vault Doctor (chain + links)
  entry: uv run python -m vaultspec vault doctor --category chain --category links --severity error
  language: system
  types: [markdown]
  pass_filenames: true
```

Both hooks are opt-in via the consuming project's `.pre-commit-config.yaml`.

### Why No Special Category Flags (e.g. `--filenames`)

A `--filenames` shortcut flag was considered for the hook use case. It is not added because:

1. `--category drift` already covers all filename-related checks (date drift, feature drift).

1. The hook scoping problem is solved by `--input` / positional file args — the hook passes exactly
   the changed files and doctor restricts results to those files regardless of check category.

1. Adding check-type aliases (`--filenames`, `--links`) would duplicate `--category` with worse
   naming and fragment the interface.

### Relationship to `vaultspec doctor`

The existing `vaultspec doctor` (system health check) is in `core/commands.py` and covers Python
version, CUDA, and optional deps. The new `vaultspec vault doctor` is in `vault_cli.py` and covers
vault content health. The namespace distinction (`doctor` vs `vault doctor`) keeps them separate.

## Rationale

Option 2 (dedicated `vault doctor` command) is chosen because:

1. `vault audit` is removed — there is no legacy interface to preserve or be compatible with.

1. A registered-check architecture allows the suite to grow without modifying the CLI surface.
   New check domains are Python files in `doctor/checks/`, not new flags.

1. The severity model is essential for pre-commit integration. A threshold parameter solves the
   WARNING-blocks-all-commits vs WARNING-is-invisible problem cleanly.

1. Dry-run must be a first-class contract. Centralising it in `safe_writer.py` ensures every
   current and future fix respects the pattern.

1. `--input` / positional file args replace the need for a separate fast hook command or special
   category shortcut flags. One command, scoped by the caller.

## Consequences

### Positive

- Chain integrity gaps (exec→plan, plan→ADR, ADR→research) become detectable and reportable
- Frontmatter drift classes that previously passed validation are now caught
- Broken wikilinks and orphaned documents are surfaced in a unified command
- Fix operations are safe (dry-run always available, always a modifier on `--fix`)
- Feature coverage gaps are visible as a matrix
- Pre-commit hooks receive only changed files and run only relevant checks
- The check registry allows project-specific checks to be added as Python files

### Negative / Trade-offs

- New `doctor/` module and `vault doctor` CLI add surface area to document and test

- Graph construction is required for LINKS and CHAIN categories — adds ~50–200ms for large vaults

- Advisory-only checks (chain breaks without auto-fix) require human action; the suite reports
  but cannot repair missing documents

- `--input` scoping for aggregate checks (chain, coverage) still builds the full graph — file
  scoping filters results, not graph construction
