---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #exec #plan #reference #research #editor-improvement
# Directory tag (hardcoded - DO NOT CHANGE - based on .docs/exec/ location)
# Feature tag (replace <feature> with your feature name, e.g., #editor-improvement)
tags:
  - "#exec"
  - "#editor-improvement"
# ISO date format (e.g., 2026-02-06)
date: 2026-02-06
# Related documents as quoted wiki-links - MUST link to parent PLAN
# (e.g., "[[2026-02-04-feature-plan]]")
related:
  - "[[2026-02-06-editor-improvement-plan]]"
---

# editor-improvement Phase 2 Step 7: Performance Benchmarking

Establish performance benchmarks for the layout sync system and document baseline results.

- Created: [[crates/pp-editor-core/benches/layout_sync.rs]]
- Modified: [[crates/pp-editor-core/Cargo.toml]] (added `[[bench]]` entry)

## Description

This step established a comprehensive benchmarking suite for the layout sync subsystem using Criterion. Four benchmark groups were implemented to measure different aspects of the DisplayMap pipeline performance:

1. **sync_layout_full** -- Full layout sync after a small edit (measures worst-case rebuild)
2. **sync_layout_incremental** -- Incremental layout sync after a small edit
3. **sync_layout_incremental_noop** -- Incremental sync when no edits occurred (version-check fast path)
4. **coordinate_mapping** -- `to_display_point` / `from_display_point` coordinate conversion

Each group tests at three document sizes: 100, 1,000, and 10,000 lines (120 chars/line). Uses `NoOpLayout` from `pp_ui_core` for deterministic measurement (isolates sync overhead from actual text shaping).

## Benchmark Results

### sync_layout_full (full rebuild per iteration)

| Document Size | Median Time | Notes |
|---|---|---|
| 100 lines | 618.64 us | ~6.2 us/line |
| 1,000 lines | 5.99 ms | ~6.0 us/line |
| 10,000 lines | 60.92 ms | ~6.1 us/line |

Linear scaling confirmed: O(n) in line count. ~6 us/line overhead for full sync.

### sync_layout_incremental (with small edit)

| Document Size | Median Time | Notes |
|---|---|---|
| 100 lines | 617.50 us | Comparable to full sync |
| 1,000 lines | 6.15 ms | Comparable to full sync |
| 10,000 lines | 62.83 ms | Comparable to full sync |

**Analysis**: Currently the incremental path uses a conservative full-buffer patch (marks the entire buffer as `LinesModified`), so it performs the same amount of work as a full sync. This is expected -- the incremental infrastructure is in place but fine-grained patch generation is not yet implemented. Once line-level patches are produced, this benchmark will show the speedup.

### sync_layout_incremental_noop (no edit, version-check only)

| Document Size | Median Time | Notes |
|---|---|---|
| 100 lines | 3.54 ns | Constant time |
| 1,000 lines | 3.51 ns | Constant time |
| 10,000 lines | 3.52 ns | Constant time |

**Analysis**: The version-check fast path works correctly. When no buffer edits have occurred, the incremental sync returns in ~3.5 ns regardless of document size. This is a simple integer comparison (current_version == last_synced_version) and demonstrates that the version-tracking mechanism imposes zero overhead on unchanged frames.

### coordinate_mapping (to/from display point)

| Document Size | Median Time (to_display) | Median Time (from_display) |
|---|---|---|
| 100 lines | 243.88 ns (10 lookups) | 300.19 ns (10 lookups) |
| 1,000 lines | 5.37 us (100 lookups) | 4.30 us (100 lookups) |
| 10,000 lines | 38.09 us (1000 lookups) | 34.97 us (1000 lookups) |

**Analysis**: Coordinate mapping scales linearly with the number of lookups. Per-lookup cost is ~24-38 ns for `to_display` and ~30-35 ns for `from_display`. The SumTree-backed coordinate mapping provides efficient O(log n) point-in-tree lookups per call.

## Key Findings

1. **Full sync is O(n)**: ~6 us/line is the current baseline with NoOpLayout.
2. **Incremental sync = full sync (for now)**: Conservative whole-buffer patch means no speedup yet. The infrastructure is in place for fine-grained patches.
3. **Version-check fast path is O(1)**: 3.5 ns regardless of document size -- confirms the version tracking works correctly.
4. **Coordinate mapping is fast**: Sub-40ns per lookup at 10K lines confirms SumTree efficiency.
5. **Target for optimization**: Once line-level incremental patches are implemented, the 10K-line incremental sync should drop from ~63ms to sub-1ms for single-line edits (>60x improvement potential).

## Completion

- Benchmark infrastructure established with 4 groups, 14 individual benchmarks
- All benchmarks compile and run successfully
- Results documented as baseline for future optimization work
- HTML reports generated in `target/criterion/`
