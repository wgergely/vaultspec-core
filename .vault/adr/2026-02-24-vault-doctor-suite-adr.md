---
tags:
  - "#adr"
  - "#vault-doctor-suite"
date: "2026-02-24"
related:
  - "[[2026-02-24-vault-doctor-suite-research]]"
---

# `vault-doctor-suite` adr: Vault Doctor Suite Architecture | (**status:** `accepted`)

## Problem Statement

The vault verification system has grown organically around a single `vault audit --verify` command.
Several check domains exist in isolation (graph invalid-links, orphan detection) and are not wired
into the verification pipeline. Critical check gaps exist around chain integrity, frontmatter format
drift, and fix safety. The existing `fix_violations()` function modifies files without a dry-run
mode, creating risk. A coherent architecture is needed that can host new check domains, expose them
composably, and maintain commit-hook compatibility.

## Considerations

### Option 1 — Expand `vault audit` Flags

Add more flags to the existing `vault audit` command (`--chain-check`, `--link-check`, etc.) and
expand `fix_violations()` with a `dry_run` parameter.

**Pro:** Minimal surface area change, backward compatible.
**Con:** `audit` is already overloaded (summary, features, verify, fix, graph). Adding more flags
makes the interface unwieldy. The audit command is not structured to register checks dynamically.
Each new domain requires another flag combination.

### Option 2 — New `vault doctor` Subcommand with Registered Checks

Introduce `vaultspec vault doctor` as a dedicated command. Doctor checks are individually
registered and addressable by name or category. The command supports `--dry-run`, `--fix`,
`--check <name>`, `--severity <level>`, and `--json`.

**Pro:** Clean separation of concerns, composable, extensible. Pre-commit hook can target specific
check categories. Severity model is native to the command design.
**Con:** New CLI surface to document and maintain.

### Option 3 — Standalone Doctor Module Called by Both CLI Paths

A `doctor/` module that is invoked by both `vault audit --verify` (for backward compat) and by a
new `vault doctor` command. The module owns check registration and result formatting.

**Pro:** Reuses existing `--verify` integration point while enabling a richer dedicated interface.
**Con:** Two CLI paths to the same logic create documentation confusion about which to use when.

## Implementation

**Adopt Option 2** with a compatibility shim.

`vaultspec vault doctor` is the primary interface for the suite. `vault audit --verify` continues
to call the existing fast path (`get_malformed` + `verify_vertical_integrity`) unchanged — it is
the pre-commit hook target and must remain stable and fast.

The doctor suite introduces a `src/vaultspec/doctor/` module with the following structure:

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

### Check Registry Design

Checks are registered with a category, name, severity, and whether they are fixable:

```python
@dataclass
class DoctorCheck:
    name: str                  # e.g. "exec-plan-chain"
    category: CheckCategory    # LINKS | CHAIN | DRIFT | COVERAGE | STRUCTURE
    severity: Severity         # ERROR | WARNING | INFO
    fixable: bool
    run: Callable[[Path], list[DoctorResult]]
    fix: Callable[[Path, bool], list[DoctorResult]] | None  # dry_run param
```

The suite runner calls all registered checks (or a filtered subset), collects `DoctorResult`
objects, and formats output.

### DoctorResult Model

Extends `VerificationError` to add severity and fix metadata:

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

This is backward-compatible with `VerificationError` (path + message) while adding structured
metadata for filtering and reporting.

### Dry-Run Contract

Every fix function accepts `dry_run: bool`. When `dry_run=True`:

- No filesystem writes occur
- Returned `DoctorResult` has `fix_applied=False`, `fix_detail` describes the planned action
- Log lines are prefixed `[DRY-RUN]`

The `safe_writer.py` helper encapsulates this pattern for atomic frontmatter rewrites and file
renames, preventing duplication across fix functions.

### Severity Model

| Severity | Meaning | Pre-commit behavior |
|---|---|---|
| `ERROR` | Structural violation — breaks parsing or chain integrity | Fail (exit 1) |
| `WARNING` | Advisory drift — valid but inconsistent | Pass by default, configurable |
| `INFO` | Informational — coverage gaps, style suggestions | Pass always |

Pre-commit integration uses `--severity error` by default. Users can opt into `--severity warning`
for stricter hooks.

### CLI Interface

```
vaultspec vault doctor [options]

Options:
  --check <name>       Run only the named check (repeatable)
  --category <cat>     Run only checks in a category: links|chain|drift|coverage|structure
  --severity <level>   Minimum severity to report: error|warning|info  (default: info)
  --fix                Apply available fixes
  --dry-run            Preview fixes without writing (requires --fix)
  --json               Machine-readable JSON output
  --limit <n>          Limit items per check in output (default: 20)
  --feature <name>     Scope checks to a specific feature
```

### Check Domains and Categories

#### STRUCTURE (fast, delegates to existing)

| Check | Severity | Fixable | Notes |
|---|---|---|---|
| `unsupported-dirs` | ERROR | No | Delegates to `verify_vault_structure` |
| `stray-files` | WARNING | No | Files in `.vault/` root |

#### LINKS (requires graph construction)

| Check | Severity | Fixable | Notes |
|---|---|---|---|
| `broken-wikilinks` | ERROR | No | `get_invalid_links()` wired into doctor |
| `orphaned-docs` | WARNING | No | `get_orphaned()` wired into doctor |
| `malformed-related` | ERROR | Yes | `related` entries not in `[[wikilink]]` format |

#### CHAIN (requires graph + doc-type awareness)

| Check | Severity | Fixable | Notes |
|---|---|---|---|
| `exec-plan-link` | ERROR | No | Exec `related` must contain a valid plan wikilink |
| `plan-adr-link` | WARNING | No | Plan should have at least one linked ADR |
| `adr-research-link` | WARNING | No | ADR should have at least one linked research |
| `feature-plan-coverage` | ERROR | No | Every feature tag must have a plan (existing check) |

#### DRIFT (per-file, no graph needed)

| Check | Severity | Fixable | Notes |
|---|---|---|---|
| `filename-date-drift` | ERROR | Yes | Filename date ≠ frontmatter date field |
| `filename-feature-drift` | ERROR | Yes | Filename feature ≠ feature tag |
| `unquoted-date` | WARNING | Yes | `date: 2026-02-18` (YAML date object) |
| `crlf-endings` | WARNING | Yes | Windows line endings in frontmatter |
| `duplicate-tags` | ERROR | Yes | Same tag appears more than once |
| `bom-detected` | WARNING | Yes | BOM character at file start |
| `extra-fields` | INFO | No | Frontmatter fields outside schema |
| `missing-related-field` | INFO | Yes | `related` absent; normalize to empty list |

#### COVERAGE (aggregate, no graph needed)

| Check | Severity | Fixable | Notes |
|---|---|---|---|
| `feature-coverage-matrix` | INFO | No | Per-feature doc-type presence/absence report |

### Integration with Existing Pre-commit Hook

The `check-naming` pre-commit hook stays unchanged — it calls `vault audit --verify` which runs
the fast existing pipeline. A new optional pre-commit hook `vault-doctor` can be added to call
`vaultspec vault doctor --category chain --category links --severity error` for teams that want
deeper checks on commit. This hook is not mandatory and is opt-in via `.pre-commit-config.yaml`.

### Relationship to `vaultspec doctor`

The existing `vaultspec doctor` (system health check) is in `core/commands.py` and covers Python
version, CUDA, and optional deps. The new `vaultspec vault doctor` is in `vault_cli.py` and covers
vault content health. The namespace distinction (`doctor` vs `vault doctor`) keeps them separate
with no overlap.

## Rationale

Option 2 (dedicated `vault doctor` command) is chosen because:

1. The audit command is already feature-saturated. Adding chain and drift checks behind more flags
   would make the interface unmaintainable.
2. A registered-check architecture allows the suite to grow without modifying the CLI surface.
   New check domains are Python files in `doctor/checks/`, not new flags.
3. The severity model is essential for pre-commit integration. Without it, any WARNING-level check
   would either block all commits or be invisible. A threshold parameter solves this cleanly.
4. Dry-run must be a first-class contract, not an afterthought. Centralizing it in `safe_writer.py`
   ensures every current and future fix respects the pattern.
5. The `vault audit --verify` fast path is preserved unchanged. Teams relying on it for pre-commit
   are not disrupted.

## Consequences

### Positive

- Chain integrity gaps (exec→plan, plan→ADR, ADR→research) become detectable and reportable
- Frontmatter drift classes that previously passed validation are now caught
- Broken wikilinks and orphaned documents are surfaced in the verify pipeline
- Fix operations are safe (dry-run always available)
- Feature coverage gaps are visible as a matrix
- The check registry allows community or project-specific checks to be added

### Negative / Trade-offs

- New `doctor/` module and `vault doctor` CLI add surface area to document and test
- Graph construction is required for LINKS and CHAIN categories — adds ~50–200ms for large vaults
- CHAIN checks produce warnings (not errors) for plan→ADR and ADR→research gaps, which may feel
  lenient. Teams can override to ERROR via `--severity` if desired
- Advisory-only checks (chain breaks without auto-fix) require human action to resolve; the suite
  reports but cannot repair missing documents
