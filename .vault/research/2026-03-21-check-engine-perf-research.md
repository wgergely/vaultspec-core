---
tags:
  - '#research'
  - '#check-engine-perf'
date: '2026-03-21'
related:
  - '[[2026-03-21-feature-documentation-code-review-audit]]'
---

# check-engine-perf research: redundant I/O in run_all_checks

The code review (\[[2026-03-21-feature-documentation-code-review-audit]\], finding
VC-M4) identified that `run_all_checks` performs redundant file system I/O.
Each checker independently scans the vault directory and reads every document,
resulting in linear growth of wasted reads as vault size increases.

## Findings

### Current I/O profile

`run_all_checks` invokes seven checkers. Three of them construct their own
`VaultGraph` instance:

- `check_orphans` - builds VaultGraph (1N reads after the earlier pass-2
  optimization)
- `check_references` - builds VaultGraph (1N reads)
- `check_schema` - builds VaultGraph (1N reads)

Four additional checkers each call `scan_vault` and read all files
independently:

- `check_structure` - scan + N reads
- `check_frontmatter` - scan + N reads
- `check_links` - scan + N reads
- `check_features` - uses its own `_scan_all` helper, scan + N reads

**Total per invocation:** 7 directory scans + at minimum 7N file reads for N
vault documents. For a vault with 50 documents this means ~350 file reads per
check run.

### VaultGraph construction cost

Each `VaultGraph` construction performs:

- One directory walk to discover `.md` files
- One read pass per file to extract frontmatter and body/links (optimized from
  the original two-pass design)

Three independent constructions therefore triple the graph-building cost with
no benefit - the resulting graphs are identical.

### Shared-graph approach

A single `VaultGraph` built once in `run_all_checks` and passed to all three
graph-consuming checkers eliminates two redundant constructions. This yields an
immediate ~30% I/O reduction with minimal code change.

Backward compatibility is preserved by adding an optional `graph` parameter
(`graph: VaultGraph | None = None`) to each checker. When `None`, the checker
builds its own graph as before; when provided, it reuses the shared instance.

### Shared scan/parse for non-graph checkers

The four non-graph checkers each perform their own `scan_vault` call and file
reads. A lightweight `VaultSnapshot` - a dict mapping file paths to parsed
metadata (frontmatter dict + body text) - can be built once from the shared
`VaultGraph` or from a single scan pass, then handed to all four checkers.

`check_features` currently uses a private `_scan_all` helper that duplicates
work already done by graph construction. It can be refactored to consume
snapshot data directly.

### Expected improvement

- Before: 7 scans + 7N reads
- After: 1 scan + 1N reads (+ in-memory dict lookups)
- Reduction: ~85% fewer file system operations
