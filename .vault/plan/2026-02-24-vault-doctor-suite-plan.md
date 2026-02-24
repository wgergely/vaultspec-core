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
The suite exposes `vaultspec vault doctor` as a dedicated CLI command with registered, individually
addressable checks across five categories: **structure**, **links**, **chain**, **drift**, and
**coverage**. All fix operations support `--dry-run`. The suite complements but does not replace
the existing `vault audit --verify` fast path.

Key outcomes:

- `fix_violations()` gains `dry_run: bool` parameter (safe, non-breaking)
- Broken wikilinks and orphaned documents are wired into a verify-equivalent pipeline
- Chain integrity is checked: exec→plan, plan→ADR, ADR→research gaps are reported
- Frontmatter format drift (date/feature filename drift, CRLF, unquoted dates, BOM, duplicates)
  is detectable and auto-fixable
- Per-feature coverage matrix is available as a report
- A registered check registry enables future extensibility without CLI churn

## Tasks

### Phase 1 — Foundation: Dry-Run Safety and Module Scaffold

**P1-T1: Add `dry_run` parameter to `fix_violations()`**

- Extend `fix_violations(root_dir, dry_run: bool = False)` signature in
  `src/vaultspec/verification/api.py`
- When `dry_run=True`, collect planned `FixResult` objects without writing or renaming any file
- Log planned actions with `[DRY-RUN]` prefix using the existing logger
- Add `--dry-run` flag to `vault audit --fix` in `vault_cli.py`
- Update unit tests in `src/vaultspec/verification/tests/test_verification.py` to cover dry-run
  path for all six existing fix actions

**P1-T2: Create `safe_writer.py` helper**

- Create `src/vaultspec/doctor/fixes/safe_writer.py`
- Implement `atomic_write(path, content, dry_run) -> bool` — writes via temp file + rename, or
  logs and returns False on dry-run
- Implement `atomic_rename(src, dst, dry_run) -> bool` — renames with collision check, or logs
  on dry-run
- Both functions must be idempotent and leave the file system unchanged on dry-run

**P1-T3: Scaffold `doctor/` module**

- Create `src/vaultspec/doctor/__init__.py` with public exports
- Create `src/vaultspec/doctor/models.py` with `Severity` enum, `CheckCategory` enum,
  `DoctorResult` dataclass, `DoctorCheck` dataclass
- Create `src/vaultspec/doctor/registry.py` with `CheckRegistry` class — register, list, and
  run checks by name or category
- Create stub `src/vaultspec/doctor/checks/__init__.py`
- Create stub `src/vaultspec/doctor/fixes/__init__.py`
- Add `src/vaultspec/doctor/tests/__init__.py` and first test file

**P1-T4: Wire `vault doctor` into CLI**

- Add `doctor` subcommand handler `handle_doctor(args)` in `vault_cli.py`
- Register with the `vault` argument parser: `vaultspec vault doctor`
- Flags: `--check`, `--category`, `--severity`, `--fix`, `--dry-run`, `--json`, `--limit`,
  `--feature`
- Handler calls `CheckRegistry.run(...)` and formats `DoctorResult` list as table or JSON
- Write integration smoke test: `vaultspec vault doctor --severity info` exits 0 on an empty vault

### Phase 2 — Structure and Links Checks

**P2-T1: `structure` checks**

- Create `src/vaultspec/doctor/checks/structure.py`
- `check_unsupported_dirs(root_dir) -> list[DoctorResult]` — delegates to existing
  `verify_vault_structure()`, wraps errors as `Severity.ERROR` results
- `check_stray_files(root_dir) -> list[DoctorResult]` — files in `.vault/` root other than
  `README.md`, severity `WARNING`
- Register both checks under `CheckCategory.STRUCTURE`

**P2-T2: `links` checks (broken wikilinks)**

- Create `src/vaultspec/doctor/checks/links.py`
- `check_broken_wikilinks(root_dir) -> list[DoctorResult]` — calls `VaultGraph.get_invalid_links()`
  and wraps each `(source, target)` pair as `Severity.ERROR` DoctorResult on the source path
- `check_orphaned_docs(root_dir) -> list[DoctorResult]` — calls `VaultGraph.get_orphaned()` and
  wraps each orphan as `Severity.WARNING` DoctorResult
- `check_malformed_related(root_dir) -> list[DoctorResult]` — per-file scan for `related` entries
  that are not valid `[[wikilink]]` format; severity `ERROR`, fixable=True
- Register all three under `CheckCategory.LINKS`

**P2-T3: Fix for `malformed-related`**

- Create `src/vaultspec/doctor/fixes/frontmatter.py`
- `fix_malformed_related(path, dry_run) -> DoctorResult` — rewrites `related` field, stripping
  or quoting malformed entries; uses `atomic_write`
- Define "fix" as: remove non-wikilink entries (log them); do not invent links

**P2-T4: Tests for structure and links checks**

- Create `src/vaultspec/doctor/tests/test_links.py`
- Test `check_broken_wikilinks` with a fixture vault containing a doc that links to a non-existent
  target; assert DoctorResult has severity ERROR and correct path/message
- Test `check_orphaned_docs` with a fixture containing an isolated doc; assert WARNING result
- Test `check_malformed_related` with a doc whose `related` contains `"not-a-wikilink"`; assert
  ERROR and fixable=True
- Test dry-run fix: assert no file write, result has `fix_applied=False` and non-empty `fix_detail`

### Phase 3 — Chain Integrity Checks

**P3-T1: `chain` check: exec → plan link**

- Create `src/vaultspec/doctor/checks/chain.py`
- `check_exec_plan_link(root_dir) -> list[DoctorResult]`
  - Walk all `exec/` documents
  - For each exec doc, extract `related` wikilinks
  - Resolve each link against the vault node index (document stems)
  - Classify the linked documents by DocType
  - If no linked document is of type `PLAN`: emit `Severity.ERROR` DoctorResult
  - Message: `"Exec doc '...' has no linked plan in 'related'. Chain break: exec → plan."`
  - `fix_available=False` (cannot auto-generate a plan)

**P3-T2: `chain` check: plan → ADR link**

- `check_plan_adr_link(root_dir) -> list[DoctorResult]`
  - Walk all `plan/` documents
  - For each plan, extract `related` wikilinks and check if any resolve to an `#adr` document
  - If no linked ADR: emit `Severity.WARNING` DoctorResult
  - Message: `"Plan '...' has no linked ADR in 'related'. Chain break: plan → adr."`

**P3-T3: `chain` check: ADR → research link**

- `check_adr_research_link(root_dir) -> list[DoctorResult]`
  - Walk all `adr/` documents
  - For each ADR, check if `related` links resolve to any `#research` document
  - If no linked research: emit `Severity.WARNING` DoctorResult
  - Message: `"ADR '...' has no linked research in 'related'. Chain break: adr → research."`

**P3-T4: Register chain checks and tests**

- Register `check_exec_plan_link`, `check_plan_adr_link`, `check_adr_research_link` under
  `CheckCategory.CHAIN`
- Create `src/vaultspec/doctor/tests/test_chain.py`
- Fixture vault with an exec doc whose `related` has no plan link; assert ERROR from chain check
- Fixture vault with a plan doc whose `related` has no ADR; assert WARNING from chain check
- Fixture vault with an ADR whose `related` has no research; assert WARNING from chain check
- Fixture vault with a fully linked chain (plan→ADR→research, exec→plan); assert zero results

**P3-T5: `feature-plan-coverage` delegation**

- Wrap `verify_vertical_integrity()` as a `CheckCategory.CHAIN` check named `feature-plan-coverage`
- Severity `ERROR` (existing behavior preserved)
- This allows `vault doctor --category chain` to include it

### Phase 4 — Frontmatter Drift Checks

**P4-T1: `drift` check: filename date vs frontmatter date**

- Create `src/vaultspec/doctor/checks/drift.py`
- `check_filename_date_drift(root_dir) -> list[DoctorResult]`
  - For each vault doc, extract date from filename stem (first 10 chars)
  - Compare to `date` field in parsed frontmatter
  - If they differ: emit `Severity.ERROR`, `fix_available=True`
- Fix: update frontmatter `date` to match filename date (filename is authoritative)

**P4-T2: `drift` check: filename feature vs feature tag**

- `check_filename_feature_drift(root_dir) -> list[DoctorResult]`
  - Extract feature slug from filename (segment between date and type suffix)
  - Compare to the feature tag (non-directory tag after stripping `#`)
  - If they differ: emit `Severity.ERROR`, `fix_available=True`
- Fix: update feature tag to match filename feature slug (filename is authoritative)
- Note: filename feature extraction must account for multi-segment features
  (e.g. `editor-demo` from `2026-02-05-editor-demo-plan.md`)

**P4-T3: `drift` check: unquoted date**

- `check_unquoted_date(root_dir) -> list[DoctorResult]`
  - Read raw frontmatter YAML text (before parsing)
  - Regex match `date:\s+\d{4}-\d{2}-\d{2}` (without surrounding quotes)
  - If match: emit `Severity.WARNING`, `fix_available=True`
- Fix: rewrite `date:` line to add double quotes around value

**P4-T4: `drift` check: CRLF line endings**

- `check_crlf_endings(root_dir) -> list[DoctorResult]`
  - Read raw file bytes; check for `\r\n` occurrences in frontmatter block
  - If found: emit `Severity.WARNING`, `fix_available=True`
- Fix: replace all `\r\n` with `\n` via `atomic_write`

**P4-T5: `drift` check: duplicate tags**

- `check_duplicate_tags(root_dir) -> list[DoctorResult]`
  - After parsing `tags` list, check for duplicates (case-insensitive comparison)
  - If duplicates found: emit `Severity.ERROR`, `fix_available=True`
- Fix: deduplicate preserving first occurrence

**P4-T6: `drift` check: BOM detection**

- `check_bom(root_dir) -> list[DoctorResult]`
  - Read file as bytes, check for UTF-8 BOM (`\xef\xbb\xbf`)
  - If found: emit `Severity.WARNING`, `fix_available=True`
- Fix: strip BOM from file start via `atomic_write` (delegates to existing BOM logic in
  `fix_violations`)

**P4-T7: `drift` check: extra/unknown frontmatter fields**

- `check_extra_fields(root_dir) -> list[DoctorResult]`
  - Parse frontmatter dict; check for keys outside `{tags, date, related}`
  - If any extra keys: emit `Severity.INFO`, `fix_available=False`
- No auto-fix: extra fields may be intentional (e.g. Obsidian properties)

**P4-T8: `drift` check: missing `related` field normalization**

- `check_missing_related(root_dir) -> list[DoctorResult]`
  - If `related` key is absent from parsed frontmatter: emit `Severity.INFO`, `fix_available=True`
- Fix: insert `related: []` after `date:` line via `atomic_write`

**P4-T9: Fix runner for drift checks**

- `fix_drift(path, checks, dry_run) -> list[DoctorResult]` in `doctor/fixes/frontmatter.py`
- Applies all fixable drift fixes in a single atomic write per file (batch to avoid multiple
  rewrites of the same file)
- Order of application: BOM strip → CRLF normalize → duplicate tag dedup → unquoted date →
  missing related → date drift → feature drift

**P4-T10: Tests for drift checks**

- Create `src/vaultspec/doctor/tests/test_drift.py`
- Parametrized test for each drift type with a crafted fixture file
- For each fixable drift: test that dry-run produces result with `fix_applied=False` and that
  wet-run produces result with `fix_applied=True` and modifies the file correctly
- Edge cases: file with multiple drift types applied in one pass

### Phase 5 — Coverage Matrix and Reporting

**P5-T1: Feature coverage matrix check**

- Create `src/vaultspec/doctor/checks/coverage.py`
- `check_feature_coverage(root_dir) -> list[DoctorResult]`
  - For each feature in `list_features(root_dir)`, query which DocTypes have documents tagged
    with that feature
  - Emit one `Severity.INFO` DoctorResult per feature per missing DocType (or one summary result
    per feature with a `message` listing present/absent types)
- The INFO level means this check never blocks commits — it is a reporting-only check

**P5-T2: Coverage matrix CLI output**

- When `vault doctor --category coverage` is run, format output as a table:
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
- JSON output includes a structured dict per feature

**P5-T3: Tests for coverage check**

- Create `src/vaultspec/doctor/tests/test_coverage.py`
- Fixture vault with two features, one complete and one incomplete
- Assert INFO results for the incomplete feature only
- Assert correct matrix content in both text and JSON format

### Phase 6 — Integration, CLI, and Pre-commit

**P6-T1: Full suite integration test**

- Create `src/vaultspec/doctor/tests/test_suite.py`
- Run `CheckRegistry.run(root_dir)` against `test-project/.vault/`
- Assert the runner completes without exception
- Assert result is a `list[DoctorResult]`
- Assert no false positives in the reference test-project vault (all checks pass on a valid vault)

**P6-T2: Pre-commit hook definition**

- Add to `.pre-commit-config.yaml` an opt-in `vault-doctor` hook:
  ```yaml
  - id: vault-doctor
    name: Vault Doctor (chain and link checks)
    entry: uv run python -m vaultspec vault doctor --category chain --category links --severity error
    language: system
    types: [markdown]
    pass_filenames: false
  ```
- Mark as `enabled: false` (opt-in only) — teams enable in their own config

**P6-T3: MCP tool integration**

- In `src/vaultspec/mcp_server/vault_tools.py`, expose `vault_doctor` as an MCP tool
- Accepts: `categories` (list), `severity` (str), `fix` (bool), `dry_run` (bool), `feature` (str)
- Returns: structured JSON matching the `DoctorResult` list schema
- This allows Claude and Gemini agents to query vault health programmatically

**P6-T4: `vault audit --fix` dry-run wiring**

- Ensure `vault audit --fix --dry-run` calls the updated `fix_violations(dry_run=True)`
- Update help text to document `--dry-run` flag interaction with `--fix`
- Add regression test: `vault audit --fix --dry-run` does not modify any files

**P6-T5: Documentation updates**

- Update `.vaultspec/docs/cli-reference.md` with `vault doctor` command documentation
- Update `.vaultspec/docs/concepts.md` to describe the doctor suite and check categories
- Add a `vault-doctor-hook` example to `.vaultspec/rules/hooks/`
- Update `AGENTS.md` to note the `vault doctor` command in the toolkit

## Parallelization

The following phase groups can be worked in parallel once Phase 1 is complete:

- **Phase 2 (links)** and **Phase 3 (chain)** are independent — both depend only on Phase 1
  scaffold and the existing `VaultGraph` API
- **Phase 4 (drift)** is fully independent of Phases 2 and 3 — it operates per-file with no
  graph dependency
- **Phase 5 (coverage)** depends only on `list_features()` and the scanner, independent of
  Phases 2–4
- **Phase 6** depends on all prior phases being complete (integration test, documentation)

Recommended parallel execution for a two-agent team:
- Agent A: Phase 1 → Phase 2 → Phase 3
- Agent B: Phase 1 (shared scaffold) → Phase 4 → Phase 5

## Verification

- All new checks produce `list[DoctorResult]` (not exceptions) on any valid or invalid vault
- `--dry-run` flag never modifies the filesystem (verified by stat-checking files before/after)
- `vault audit --verify` (existing pre-commit hook) is unmodified and continues to pass on all
  existing test fixtures
- `vault doctor --severity error` exits 0 on `test-project/.vault/` with no injected violations
- `vault doctor --fix --dry-run` on a vault with known violations produces non-empty results
  without modifying files
- `vault doctor --category chain` catches exec-without-plan, plan-without-adr, and
  adr-without-research in crafted fixture vaults
- `vault doctor --category drift` catches all eight drift types in parametrized fixture tests
- `vault doctor --category coverage` renders a matrix with correct ✓/✗ for each feature/doctype
- Pre-commit hook `vault-doctor` (when enabled) exits 1 on a vault with ERROR-level violations
- MCP `vault_doctor` tool returns valid JSON on both clean and dirty vaults
- No regressions in existing `verification/` and `graph/` test suites
