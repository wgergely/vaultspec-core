---
tags:
  - '#plan'
  - '#check-engine-perf'
date: '2026-03-21'
related:
  - '[[2026-03-21-check-engine-perf-adr]]'
  - '[[2026-03-21-check-engine-perf-research]]'
---

# check-engine-perf plan

Reduce redundant file system I/O in `run_all_checks` by sharing a single
`VaultGraph` and a derived `VaultSnapshot` across all checkers, as decided in
\[[2026-03-21-check-engine-perf-adr]\].

## Proposed Changes

Currently seven checkers perform independent directory scans and file reads,
totaling 7N reads per run. This plan introduces two shared data structures -
a `VaultGraph` for graph-consuming checkers and a `VaultSnapshot` dict for
the remaining checkers - built once and passed via optional parameters. See
\[[2026-03-21-check-engine-perf-research]\] for the full I/O analysis.

## Tasks

- [x] **Task 1:** Change `check_orphans`, `check_references`, and
  `check_schema` signatures to accept a required `graph: VaultGraph` parameter.
  Remove internal graph construction from each.
- [x] **Task 2:** Define a `VaultSnapshot` type (`dict[Path, VaultDocData]` or
  equivalent) and add a method to extract it from a `VaultGraph`.
- [x] **Task 3:** Change `check_structure`, `check_frontmatter`, `check_links`,
  and `check_features` signatures to accept a required `snapshot: VaultSnapshot`
  parameter. Remove internal `scan_vault` + `read_text` calls from each.
  Delete `check_features._scan_all`.
- [x] **Task 4:** Update `run_all_checks` to build a single `VaultGraph` and
  derive a `VaultSnapshot`, then pass them to all checkers.
- [x] **Task 5:** Update standalone CLI call sites (`vault check frontmatter`,
  etc.) to construct graph/snapshot at the call site before invoking checkers.

## Parallelization

Tasks 1 and 2 are independent and can be worked in parallel. Task 3 depends on
Task 2. Tasks 4 and 5 depend on Tasks 1-3.

## Verification

- All existing check tests must pass with identical results before and after
  the change.
- Add a test that verifies `run_all_checks` constructs exactly one
  `VaultGraph`.
- Measure file read count reduction by instrumenting `Path.read_text`
  calls during a `run_all_checks` invocation on a test vault. Target: from 7N
  down to 1N reads.
- Standalone CLI commands must produce identical output to `run_all_checks`
  for the same check.
- Run the full test suite and pre-commit hooks to confirm no regressions.
