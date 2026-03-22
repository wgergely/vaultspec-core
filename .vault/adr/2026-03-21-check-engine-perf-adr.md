---
tags:
  - '#adr'
  - '#check-engine-perf'
date: '2026-03-21'
related:
  - '[[2026-03-21-check-engine-perf-research]]'
  - '[[2026-03-21-feature-documentation-code-review-audit]]'
---

# check-engine-perf adr: shared-graph and snapshot for check engine | (**status:** `accepted`)

## Problem Statement

`run_all_checks` constructs three independent `VaultGraph` instances and
performs four separate `scan_vault` passes, resulting in 7N file reads for N
vault documents. This redundant I/O scales linearly with vault size and is
entirely avoidable since every checker operates on the same immutable set of
files within a single run.

## Considerations

- All seven checkers read the same vault directory and the same set of files
  during a single `run_all_checks` invocation.
- `VaultGraph` already parses frontmatter and body content - data that the
  non-graph checkers also need.
- No external caching layer or dependency injection framework is warranted for
  this scope.

## Constraints

- No backward compatibility -- checkers receive graph/snapshot as required
  parameters. Standalone callers construct them explicitly.
- No new dependencies; use stdlib data structures only.
- The change must be purely internal - no CLI or user-facing API changes.

## Implementation

Build a single `VaultGraph` at the top of `run_all_checks` and pass it to
`check_orphans`, `check_references`, and `check_schema` as a required `graph`
parameter.

Derive a `VaultSnapshot` (a `dict[Path, VaultDocData]` or similar) from the
graph's parsed node data, then pass it to `check_structure`,
`check_frontmatter`, `check_links`, and `check_features` as a required
`snapshot` parameter.

Refactor `check_features._scan_all` to consume snapshot data instead of
performing its own independent scan. Delete `_scan_all`.

Standalone callers (CLI `vault check frontmatter`, etc.) construct their own
graph/snapshot at the call site. No optional parameters, no dual code paths.

See \[[2026-03-21-check-engine-perf-research]\] for the full I/O analysis.

## Rationale

This approach was chosen because:

- Required parameters make data flow explicit and prevent callers from
  accidentally falling back to redundant I/O.
- It delivers an ~85% reduction in file system operations.
- The snapshot is a plain dict derived from data the graph already computes,
  avoiding any new abstraction layers.
- No dual code paths (optional vs required) to maintain.

## Consequences

- `run_all_checks` gains responsibility for graph/snapshot lifecycle, adding a
  small amount of orchestration logic.
- Standalone CLI commands that invoke individual checkers must construct a
  graph or snapshot at the call site. This is a small amount of boilerplate
  but makes the I/O cost visible.
- Checkers must not mutate the shared data. Enforced by convention (read-only)
  rather than by freezing, to avoid unnecessary copying overhead.
- Future checkers must follow the same pattern: receive graph/snapshot as
  required parameters and avoid redundant scans.
