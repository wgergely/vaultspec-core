---
tags: ["#plan", "#vault-doctor-suite"]
date: "2026-02-24"
related:
  - "[[2026-02-24-vault-doctor-suite-research]]"
  - "[[2026-02-24-vault-doctor-suite-adr]]"
  - "[[2026-02-24-vault-doctor-suite-plan]]"
  - "[[2026-02-24-vault-doctor-suite-p1-plan]]"
---
# `vault-doctor-suite` P4 plan: Frontmatter Drift Checks

This phase implements the `DRIFT` check category — eight checks that detect
frontmatter format deviations. Six of the eight are fixable; all are per-file
and require no graph construction. The phase also introduces a batched fix
runner that applies all applicable drift fixes to a single file in one atomic
write, preventing partial-state corruption.

Phase 4 is fully independent of Phases 2 (links) and 3 (chain). It can be
executed in parallel with those phases once Phase 1 is complete.

## Proposed Changes

**`src/vaultspec/doctor/checks/drift.py`** — eight check functions:

| Check name | Severity | Fixable | Detection method |
|---|---|---|---|
| `filename-date-drift` | ERROR | Yes | Filename stem first 10 chars vs `date` frontmatter field |
| `filename-feature-drift` | ERROR | Yes | Filename feature slug vs non-doctype tag |
| `unquoted-date` | WARNING | Yes | Regex `date:\s+\d{4}-\d{2}-\d{2}` on raw YAML (no quotes) |
| `crlf-endings` | WARNING | Yes | Raw bytes contain `\r\n` in frontmatter block |
| `duplicate-tags` | ERROR | Yes | Case-insensitive duplicate detection in `tags` list |
| `bom-detected` | WARNING | Yes | UTF-8 BOM (`\xef\xbb\xbf`) at file start |
| `extra-fields` | INFO | No | Frontmatter keys outside `{tags, date, related}` |
| `missing-related-field` | INFO | Yes | `related` key absent from frontmatter |

For `filename-date-drift` and `filename-feature-drift`, the filename is
authoritative. Fixes update frontmatter to match the filename, never the
reverse. For multi-segment feature slugs (e.g. `editor-demo` from
`2026-02-05-editor-demo-plan.md`), the feature slug is everything between the
date prefix and the doc-type suffix.

**`src/vaultspec/doctor/fixes/frontmatter.py`** — extended from P2:
- `fix_drift(path, checks, dry_run) -> list[DoctorResult]` — batched fix
  runner; applies all applicable drift fixes for a path in one atomic write.
  Application order:
  1. BOM strip
  2. CRLF → LF normalisation
  3. Duplicate tag deduplication (preserve first occurrence)
  4. Unquoted date quoting
  5. Missing `related` insertion (`related: []`)
  6. Filename date drift correction
  7. Filename feature drift correction

The ordered application ensures that each fix sees a clean state from the
previous step. A single `atomic_write` call at the end of the batch commits all
changes together.

All eight checks accept `input_paths: list[Path] | None`. When provided, only
files in `input_paths` are scanned (no graph build needed — pure per-file
logic).

## Tasks

- P4-S1: Implement `filename-date-drift` and `filename-feature-drift` checks in `drift.py`
- P4-S2: Implement `unquoted-date`, `crlf-endings`, and `bom-detected` checks
- P4-S3: Implement `duplicate-tags`, `extra-fields`, and `missing-related-field` checks
- P4-S4: Implement batched `fix_drift` runner in `doctor/fixes/frontmatter.py`
- P4-S5: Register all drift checks in `CheckRegistry`
- P4-S6: Unit tests for all eight drift checks and `fix_drift` batch runner

## Steps

- Name: Implement `filename-date-drift` and `filename-feature-drift` checks in `drift.py`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p4-s1-exec.md`
- Executing sub-agent: vaultspec-complex-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p1-plan]], [[2026-02-24-vault-doctor-suite-plan]]

---

- Name: Implement `unquoted-date`, `crlf-endings`, and `bom-detected` drift checks
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p4-s2-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p4-s1-exec]]

---

- Name: Implement `duplicate-tags`, `extra-fields`, and `missing-related-field` drift checks
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p4-s3-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p4-s2-exec]]

---

- Name: Implement `fix_drift` batched fix runner in `doctor/fixes/frontmatter.py`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p4-s4-exec.md`
- Executing sub-agent: vaultspec-complex-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p1-plan]], [[2026-02-24-vault-doctor-suite-p4-s3-exec]]

---

- Name: Register all eight drift checks in `CheckRegistry`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p4-s5-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p4-s4-exec]]

---

- Name: Unit tests — all eight drift checks, `fix_drift` batch runner, `--input` scoping, wet/dry runs
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p4-s6-exec.md`
- Executing sub-agent: vaultspec-code-reviewer
- References: [[2026-02-24-vault-doctor-suite-adr]], [[2026-02-24-vault-doctor-suite-p4-s1-exec]], [[2026-02-24-vault-doctor-suite-p4-s2-exec]], [[2026-02-24-vault-doctor-suite-p4-s3-exec]], [[2026-02-24-vault-doctor-suite-p4-s4-exec]], [[2026-02-24-vault-doctor-suite-p4-s5-exec]]

## Parallelization

S1 and S2 can run in parallel (both create independent check functions in the
same file — coordinate to avoid merge conflicts by having S1 write the file
first, then S2 appends). S3 is independent of S2 (same coordination caveat).
In practice, execute S1 → S2 → S3 sequentially for clean file ownership. S4
depends on S1–S3 being complete (fix_drift references all drift check names).
S5 depends on S4. S6 depends on S5.

## Verification

- Parametrised fixture tests cover each of the eight drift types individually:
  each fixture file is crafted to trigger exactly one check type.
- For each of the six fixable checks: dry-run run produces `fix_applied = False`
  and a non-empty `fix_detail`; wet-run (`dry_run = False`) produces
  `fix_applied = True` and modifies the file correctly (verified by re-parsing).
- `fix_drift` applied to a file with three simultaneous drift types (e.g. BOM +
  CRLF + unquoted date) produces `fix_applied = True` for all three in a
  single file write (stat shows mtime changed exactly once).
- `--input` scoping: drift in file A, `--input file_B` → zero results.
- `extra-fields` and `missing-related-field` return `fix_available = False` and
  `True` respectively (correct per ADR table).
- After `fix_drift` for `filename-date-drift`, the frontmatter `date` field
  matches the filename prefix (filename is authoritative).
- After `fix_drift` for `filename-feature-drift`, the feature tag in `tags`
  matches the feature slug extracted from the filename.
- All drift checks return `list[DoctorResult]` (no exceptions) even on
  binary files or files with no frontmatter.
