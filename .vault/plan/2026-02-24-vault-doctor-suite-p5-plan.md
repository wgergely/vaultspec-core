---
tags: ['#plan', '#vault-doctor-suite']
date: '2026-02-24'
related:
  - '[[2026-02-24-vault-doctor-suite-adr]]'
  - '[[2026-02-24-vault-doctor-suite-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p1-plan]]'
---

# `vault-doctor-suite` P5 plan: Coverage Matrix and Reporting

This phase implements the `COVERAGE` check category — a per-feature doc-type
presence/absence matrix that is informational only (no fixes). It also
implements the two output formatters required by the ADR: a human-readable
table and a structured JSON representation. Both formatters must correctly
handle the matrix, the plain issue list, and the `--json` flag in the CLI
handler introduced in Phase 1.

Phase 5 depends only on Phase 1 (models, registry, and the `list_features()`
function from `src/vaultspec/verification/api.py`). It is independent of
Phases 2, 3, and 4 and can be executed in parallel with them.

## Proposed Changes

**`src/vaultspec/doctor/checks/coverage.py`**

`check_feature_coverage(root_dir, input_paths) -> list[DoctorResult]`:

- Calls `list_features(root_dir)` from `src/vaultspec/verification/api.py` to
  get the full feature set.

- For each feature, scans all vault documents tagged with that feature and
  records which `DocType` values have at least one document.

- Emits one `Severity.INFO` `DoctorResult` per feature with a `message`
  summarising presence/absence across `DocType` values (`plan`, `research`,
  `adr`, `exec`, `audit`, `reference`).

- `input_paths` is intentionally ignored for this aggregate check — coverage is
  always computed across the full vault. This matches the ADR note: "file
  scoping filters results, not graph construction."

- `fix_available = False` (no auto-fix for missing document types).

**Output formatting in `vault_cli.py` handler**

Text output: renders a fixed-width table matching the ADR example:

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

JSON output: a dict per feature keyed by doc-type value, each value a boolean.

The table formatter is implemented as a helper function in the CLI handler (or
a dedicated `doctor/reporter.py` module if the formatter grows beyond ~50
lines). The formatter receives `list[DoctorResult]` and produces the table by
parsing the coverage data out of each result's `message` or by accepting a
structured payload in `fix_detail`.

**Design note on result payload**: the `DoctorResult.fix_detail` field (a free
string) is re-purposed in coverage results to carry a JSON-serialisable summary
of presence flags per doc-type. This allows the CLI handler to parse it for
table rendering without introducing a subclass. If this feels fragile after
implementation, the executor may introduce a `metadata: dict` field on
`DoctorResult` — but that decision is deferred to the executor.

## Tasks

- P5-S1: Implement `check_feature_coverage` in `doctor/checks/coverage.py`
- P5-S2: Implement text-table and JSON output for coverage results in the CLI handler
- P5-S3: Unit tests for coverage check and both output formats

## Steps

- Name: Implement `check_feature_coverage` in `doctor/checks/coverage.py`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p5-s1-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-plan]\], \[[2026-02-24-vault-doctor-suite-plan]\]

______________________________________________________________________

- Name: Implement coverage matrix text-table and JSON output formatters in `vault_cli.py`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p5-s2-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p5-s1-exec]\]

______________________________________________________________________

- Name: Unit tests — coverage check, text-table format, JSON format, fixture vaults
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p5-s3-exec.md`
- Executing sub-agent: vaultspec-code-reviewer
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p5-s1-exec]\], \[[2026-02-24-vault-doctor-suite-p5-s2-exec]\]

## Parallelization

S1 must complete before S2 (the formatter depends on the result structure
produced by the check). S3 depends on both S1 and S2. No internal parallelism.

## Verification

- Fixture vault with two features: `editor-demo` (plan + research + ADR) and
  `rag` (plan only):

  - `check_feature_coverage` returns two INFO results, one per feature.
  - Each result's payload correctly flags `plan = True`, `adr = False` for
    `rag`; `plan = True`, `adr = True` for `editor-demo`.

- `vaultspec vault doctor --category coverage` renders a correctly formatted
  table with `✓` / `✗` symbols and right-aligned columns.

- `vaultspec vault doctor --category coverage --json` returns valid JSON where
  each feature key maps to a dict of doc-type booleans.

- The check is not scoped by `--input` (aggregate result always covers the full
  vault — verified by providing a specific file path and confirming the full
  matrix is still returned).

- `fix_available = False` on all coverage results.

- `Severity.INFO` on all coverage results.

- `list_features()` returning an empty set produces an empty result list
  (no panic or empty-table crash).
