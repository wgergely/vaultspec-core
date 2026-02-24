---
tags:
  - "#plan"
  - "#vault-doctor-suite"
date: "2026-02-24"
related:
  - "[[2026-02-24-vault-doctor-suite-research]]"
  - "[[2026-02-24-vault-doctor-suite-adr]]"
---

# `vault-doctor-suite` plan

## Proposed Changes

Introduce a programmatic doctor suite for vault content health under `src/vaultspec/doctor/`.
The suite exposes `vaultspec vault doctor` as the dedicated CLI command — `vault audit` is removed
entirely with no backward-compatible shim. Checks are registered individually and addressable by
name or category. All fix operations support `--dry-run`. Files can be scoped via positional
arguments or `--input / -i` for pre-commit hook compatibility.

Key outcomes:

- `vaultspec vault doctor` replaces `vault audit` as the vault health command
- `--input / -i` and positional file args scope any run to specific files (hook-friendly)
- `--dry-run` is a modifier on `--fix` only; default mode is always read-only
- Broken wikilinks and orphaned documents are wired into the doctor pipeline
- Chain integrity is checked: exec→plan, plan→ADR, ADR→research gaps are reported
- Frontmatter format drift (date/feature filename drift, CRLF, unquoted dates, BOM, duplicates)
  is detectable and auto-fixable
- Per-feature coverage matrix is available as a report
- A registered check registry enables future extensibility without CLI churn

## Tasks

### Phase 1 — Foundation: Models, Registry, Safe Writer, and CLI Scaffold

**P1-T1: Create `doctor/` module scaffold**

- Create `src/vaultspec/doctor/__init__.py` with public exports
- Create `src/vaultspec/doctor/models.py` with:
  - `Severity` enum: `ERROR | WARNING | INFO`
  - `CheckCategory` enum: `LINKS | CHAIN | DRIFT | COVERAGE | STRUCTURE`
  - `DoctorResult` dataclass: `path, check, severity, message, fix_available, fix_applied, fix_detail`
  - `DoctorCheck` dataclass: `name, category, severity, fixable, run, fix`
- Create `src/vaultspec/doctor/registry.py` with `CheckRegistry` class:
  - `register(check: DoctorCheck)` — adds a check to the registry
  - `run(root_dir, input_paths, categories, names, min_severity) -> list[DoctorResult]`
  - `list_checks() -> list[DoctorCheck]`
- Create stub `src/vaultspec/doctor/checks/__init__.py`
- Create stub `src/vaultspec/doctor/fixes/__init__.py`
- Add `src/vaultspec/doctor/tests/__init__.py`

**P1-T2: Create `safe_writer.py` helper**

- Create `src/vaultspec/doctor/fixes/safe_writer.py`
- `atomic_write(path, content, dry_run) -> bool`:
  - Writes via temp file + rename, returns True
  - On `dry_run=True`: logs planned action with `[DRY-RUN]` prefix, returns False
- `atomic_rename(src, dst, dry_run) -> bool`:
  - Renames with collision check, returns True
  - On `dry_run=True`: logs and returns False
- Both functions leave the filesystem unchanged on dry-run

**P1-T3: Wire `vault doctor` into CLI**

- Add `doctor` subcommand handler `handle_doctor(args)` in `vault_cli.py`
- Register with the `vault` argument parser: `vaultspec vault doctor`
- Positional argument: `files` (nargs=`*`) — specific files to check
- Flags:
  - `-i / --input <file>` (repeatable) — merged with positional `files`
  - `--check <name>` (repeatable)
  - `--category <cat>` (repeatable): `links|chain|drift|coverage|structure`
  - `--severity <level>`: `error|warning|info` (default: `info`)
  - `--fix` — apply available fixes
  - `--dry-run` — preview only; rejected with error if `--fix` not also present
  - `--json` — machine-readable output
  - `--limit <n>` — items per check in output (default: 20)
  - `--feature <name>` — scope to a specific feature
- Handler calls `CheckRegistry.run(...)` and formats `DoctorResult` list as table or JSON
- Exit codes: 0 = no ERRORs at or above `--severity`; 1 = at least one ERROR
- Smoke test: `vaultspec vault doctor --severity info` exits 0 on an empty vault

**P1-T4: Remove `vault audit` from CLI**

- Remove `audit` subcommand and its handler from `vault_cli.py`
- Remove `verify_vertical_integrity()` direct CLI wiring (it will be re-exposed via the CHAIN
  check `feature-plan-coverage` in Phase 3)
- Remove `fix_violations()` direct CLI wiring (fix operations move to `doctor --fix`)
- Update `AGENTS.md` and any CLI reference docs to remove `vault audit` mentions

### Phase 2 — Structure and Links Checks

**P2-T1: `structure` checks**

- Create `src/vaultspec/doctor/checks/structure.py`
- `check_unsupported_dirs(root_dir, input_paths) -> list[DoctorResult]`
  - Delegates to existing `verify_vault_structure()`
  - Wraps errors as `Severity.ERROR` results
- `check_stray_files(root_dir, input_paths) -> list[DoctorResult]`
  - Files in `.vault/` root other than `README.md`, severity `WARNING`
  - If `input_paths` provided, filter to only those in `.vault/` root
- Register both under `CheckCategory.STRUCTURE`

**P2-T2: `links` checks**

- Create `src/vaultspec/doctor/checks/links.py`
- `check_broken_wikilinks(root_dir, input_paths) -> list[DoctorResult]`
  - Calls `VaultGraph.get_invalid_links()`, wraps each `(source, target)` pair as `Severity.ERROR`
  - If `input_paths` provided, filter results to sources in `input_paths`
- `check_orphaned_docs(root_dir, input_paths) -> list[DoctorResult]`
  - Calls `VaultGraph.get_orphaned()`, wraps each orphan as `Severity.WARNING`
  - Filter to `input_paths` if provided
- `check_malformed_related(root_dir, input_paths) -> list[DoctorResult]`
  - Per-file scan for `related` entries not in valid `[[wikilink]]` format
  - Severity `ERROR`, `fixable=True`
  - If `input_paths` provided, scan only those files
- Register all three under `CheckCategory.LINKS`

**P2-T3: Fix for `malformed-related`**

- Create `src/vaultspec/doctor/fixes/frontmatter.py`
- `fix_malformed_related(path, dry_run) -> DoctorResult`
  - Rewrites `related` field, removing non-wikilink entries (logs removals)
  - Does not invent links
  - Uses `atomic_write`

**P2-T4: Tests for structure and links checks**

- Create `src/vaultspec/doctor/tests/test_links.py`
- Test `check_broken_wikilinks` with fixture vault containing a doc linking to non-existent target
- Test `check_orphaned_docs` with fixture containing an isolated doc; assert WARNING result
- Test `check_malformed_related` with doc whose `related` contains `"not-a-wikilink"`; assert
  ERROR and `fixable=True`
- Test `--input` scoping: broken link in file A, but `input_paths=[file_B]` → zero results
- Test dry-run fix: no file write, result has `fix_applied=False` and non-empty `fix_detail`

### Phase 3 — Chain Integrity Checks

**P3-T1: `chain` check: exec → plan link**

- Create `src/vaultspec/doctor/checks/chain.py`
- `check_exec_plan_link(root_dir, input_paths) -> list[DoctorResult]`
  - Walk all `exec/` documents (filter to `input_paths` if provided)
  - For each exec doc, check if any `related` wikilink resolves to a `PLAN` document
  - If none: emit `Severity.ERROR`, `fix_available=False`
  - Message: `"Exec doc '...' has no linked plan in 'related'. Chain break: exec → plan."`

**P3-T2: `chain` check: plan → ADR link**

- `check_plan_adr_link(root_dir, input_paths) -> list[DoctorResult]`
  - Walk all `plan/` documents, check if any `related` link resolves to an `#adr` document
  - If none: emit `Severity.WARNING`
  - Message: `"Plan '...' has no linked ADR in 'related'. Chain break: plan → adr."`

**P3-T3: `chain` check: ADR → research link**

- `check_adr_research_link(root_dir, input_paths) -> list[DoctorResult]`
  - Walk all `adr/` documents, check if any `related` link resolves to a `#research` document
  - If none: emit `Severity.WARNING`
  - Message: `"ADR '...' has no linked research in 'related'. Chain break: adr → research."`

**P3-T4: `feature-plan-coverage` delegation**

- Wrap `verify_vertical_integrity()` as `CheckCategory.CHAIN` check named `feature-plan-coverage`
- Severity `ERROR` (existing behavior preserved)
- This allows `vault doctor --category chain` to include it

**P3-T5: Register chain checks and tests**

- Register all chain checks under `CheckCategory.CHAIN`
- Create `src/vaultspec/doctor/tests/test_chain.py`
- Fixture vault with exec doc whose `related` has no plan link → assert ERROR
- Fixture vault with plan doc whose `related` has no ADR → assert WARNING
- Fixture vault with ADR whose `related` has no research → assert WARNING
- Fixture vault with fully linked chain → assert zero results
- `--input` scoping: chain break in file A, `input_paths=[file_B]` → zero results

### Phase 4 — Frontmatter Drift Checks

**P4-T1: `drift` check: filename date vs frontmatter date**

- Create `src/vaultspec/doctor/checks/drift.py`
- `check_filename_date_drift(root_dir, input_paths) -> list[DoctorResult]`
  - Extract date from filename stem (first 10 chars), compare to `date` frontmatter field
  - If different: `Severity.ERROR`, `fix_available=True`
- Fix: update frontmatter `date` to match filename date (filename is authoritative)

**P4-T2: `drift` check: filename feature vs feature tag**

- `check_filename_feature_drift(root_dir, input_paths) -> list[DoctorResult]`
  - Extract feature slug from filename, compare to feature tag
  - If different: `Severity.ERROR`, `fix_available=True`
- Fix: update feature tag to match filename slug (filename is authoritative)
- Handle multi-segment features (e.g. `editor-demo` from `2026-02-05-editor-demo-plan.md`)

**P4-T3: `drift` check: unquoted date**

- `check_unquoted_date(root_dir, input_paths) -> list[DoctorResult]`
  - Regex `date:\s+\d{4}-\d{2}-\d{2}` on raw YAML text (unquoted = YAML date object)
  - `Severity.WARNING`, `fix_available=True`
- Fix: add double quotes around date value

**P4-T4: `drift` check: CRLF line endings**

- `check_crlf_endings(root_dir, input_paths) -> list[DoctorResult]`
  - Read raw bytes; check for `\r\n` in frontmatter block
  - `Severity.WARNING`, `fix_available=True`
- Fix: replace all `\r\n` with `\n` via `atomic_write`

**P4-T5: `drift` check: duplicate tags**

- `check_duplicate_tags(root_dir, input_paths) -> list[DoctorResult]`
  - Parse `tags` list; check for duplicates (case-insensitive)
  - `Severity.ERROR`, `fix_available=True`
- Fix: deduplicate preserving first occurrence

**P4-T6: `drift` check: BOM detection**

- `check_bom(root_dir, input_paths) -> list[DoctorResult]`
  - Read bytes, check for UTF-8 BOM (`\xef\xbb\xbf`)
  - `Severity.WARNING`, `fix_available=True`
- Fix: strip BOM via `atomic_write`

**P4-T7: `drift` check: extra frontmatter fields**

- `check_extra_fields(root_dir, input_paths) -> list[DoctorResult]`
  - Keys outside `{tags, date, related}`: `Severity.INFO`, `fix_available=False`
- No auto-fix: extra fields may be intentional

**P4-T8: `drift` check: missing `related` field**

- `check_missing_related(root_dir, input_paths) -> list[DoctorResult]`
  - `related` key absent: `Severity.INFO`, `fix_available=True`
- Fix: insert `related: []` after `date:` line via `atomic_write`

**P4-T9: Batched fix runner**

- `fix_drift(path, checks, dry_run) -> list[DoctorResult]` in `doctor/fixes/frontmatter.py`
- Applies all fixable drift fixes in a single atomic write per file
- Application order: BOM strip → CRLF normalize → duplicate tag dedup → unquoted date →
  missing related → date drift → feature drift

**P4-T10: Tests for drift checks**

- Create `src/vaultspec/doctor/tests/test_drift.py`
- Parametrized test for each drift type with a crafted fixture file
- For each fixable drift: dry-run produces `fix_applied=False`; wet-run produces `fix_applied=True`
  and modifies the file correctly
- Test `--input` scoping: drift in file A, `input_paths=[file_B]` → zero results
- Edge case: file with multiple drift types applied in one pass

### Phase 5 — Coverage Matrix and Reporting

**P5-T1: Feature coverage matrix check**

- Create `src/vaultspec/doctor/checks/coverage.py`
- `check_feature_coverage(root_dir, input_paths) -> list[DoctorResult]`
  - For each feature in `list_features(root_dir)`, query which DocTypes have documents
  - Emit one `Severity.INFO` DoctorResult per feature with presence/absence summary
  - `input_paths` is ignored for this aggregate check (full vault always scanned)

**P5-T2: Coverage matrix CLI output**

```
Feature Coverage Matrix
──────────────────────────────────────────────────────────
feature            plan  research  adr  exec  audit  ref
──────────────────────────────────────────────────────────
editor-demo        ✓     ✓         ✓    ✓     ✗      ✗
vault-doctor-suite ✓     ✓         ✓    ✗     ✗      ✗
rag                ✓     ✓         ✗    ✗     ✗      ✗
──────────────────────────────────────────────────────────
```

JSON output includes a structured dict per feature.

**P5-T3: Tests for coverage check**

- Create `src/vaultspec/doctor/tests/test_coverage.py`
- Fixture vault with two features (one complete, one incomplete)
- Assert INFO results for incomplete feature only
- Assert correct matrix content in both text and JSON format

### Phase 6 — Integration and Pre-commit

**P6-T1: Full suite integration test**

- Create `src/vaultspec/doctor/tests/test_suite.py`
- Run `CheckRegistry.run(root_dir)` against `test-project/.vault/`
- Assert the runner completes without exception
- Assert result is `list[DoctorResult]`
- Assert no false positives on the reference test-project vault

**P6-T2: Pre-commit hook definitions**

- Add to `.pre-commit-config.yaml` opt-in hooks:

```yaml
# Default: drift + structure checks on staged files only
- id: vault-doctor
  name: Vault Doctor
  entry: uv run python -m vaultspec vault doctor --severity error
  language: system
  types: [markdown]
  pass_filenames: true

# Deep: chain + link checks (slower, requires graph build)
- id: vault-doctor-deep
  name: Vault Doctor (chain + links)
  entry: uv run python -m vaultspec vault doctor --category chain --category links --severity error
  language: system
  types: [markdown]
  pass_filenames: true
```

Both hooks are opt-in — teams enable them in their own `.pre-commit-config.yaml`.
`pass_filenames: true` means pre-commit appends staged files as positional args; doctor
restricts all results to those files.

**P6-T3: MCP tool integration**

- In `src/vaultspec/mcp_server/vault_tools.py`, expose `vault_doctor` as an MCP tool
- Accepts: `categories` (list), `severity` (str), `fix` (bool), `dry_run` (bool),
  `feature` (str), `input_paths` (list[str])
- Returns: structured JSON matching the `DoctorResult` list schema

**P6-T4: Documentation updates**

- Update `.vaultspec/docs/cli-reference.md`: remove `vault audit`, add `vault doctor` docs
- Update `.vaultspec/docs/concepts.md`: describe the doctor suite and check categories
- Update `AGENTS.md`: note `vault doctor` in the toolkit, remove `vault audit` references

## Parallelization

Once Phase 1 is complete:

- **Phase 2 (links)** and **Phase 3 (chain)** are independent
- **Phase 4 (drift)** is fully independent of Phases 2 and 3 (no graph dependency)
- **Phase 5 (coverage)** depends only on `list_features()`, independent of Phases 2–4
- **Phase 6** depends on all prior phases (integration test, documentation)

Recommended parallel execution for a two-agent team:
- Agent A: Phase 1 → Phase 2 → Phase 3
- Agent B: Phase 1 (shared scaffold) → Phase 4 → Phase 5

## Verification

- All new checks produce `list[DoctorResult]` (not exceptions) on any valid or invalid vault
- `--dry-run` without `--fix` is rejected with a clear error message
- `--dry-run` with `--fix` never modifies the filesystem (verified by stat-checking before/after)
- `vault doctor --severity error` exits 0 on `test-project/.vault/` with no injected violations
- `vault doctor --fix --dry-run` on a vault with known violations produces non-empty results
  without modifying files
- `vault doctor --category chain` catches exec-without-plan, plan-without-adr, and
  adr-without-research in crafted fixture vaults
- `vault doctor --category drift` catches all eight drift types in parametrized fixture tests
- `vault doctor --category coverage` renders a matrix with correct ✓/✗ for each feature/doctype
- `vault doctor staged_file.md --severity error` produces results scoped to that file only
- Pre-commit hook `vault-doctor` (when enabled) exits 1 on a vault with ERROR-level violations
- MCP `vault_doctor` tool returns valid JSON on both clean and dirty vaults
- No regressions in existing `verification/` and `graph/` test suites
- `vault audit` no longer exists as a CLI command (verified by checking argparse registration)
