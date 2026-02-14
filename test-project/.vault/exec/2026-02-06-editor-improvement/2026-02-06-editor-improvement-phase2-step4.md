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

# editor-improvement Phase 2 Step 4

Implement the `Edit` and `Patch` system for incremental layout in `pp-editor-core`, mirroring Zed's implementation.

- Modified: [[crates/pp-editor-core/Cargo.toml]]
- Modified: [[crates/pp-editor-core/src/text.rs]]
- Modified: [[crates/pp-editor-core/src/display_map/fold_map.rs]] (indirectly, due to updated content)
- Created: N/A (Moved `mod.rs` to `text.rs` instead of creating new)

## Description

This step involved implementing the core `Edit<T>` and `Patch<T>` structs along with their associated methods (`new`, `edits`, `into_inner`, `invert`, `clear`, `is_empty`, `push`, `compose`, `old_to_new`, `edit_for_old_position`) in `crates/pp-editor-core/src/text.rs`. The implementation closely followed the patterns and logic found in Zed's `ref/zed/crates/text/src/patch.rs` and the `Edit` struct definition from `ref/zed/crates/text/src/text.rs`.

Key implementation details:

- A custom `IsNoneOr` trait was introduced to `text.rs` to mimic Zed's helper for `Option` types, facilitating the `compose` method's logic.
- The `compose` method required careful translation to ensure correct handling of peekable iterators and mutable references, specifically by using `peek()` for non-mutating checks and `peek_mut()` for actual modifications, mirroring Zed's subtle logic.
- The module structure was adapted to Rust conventions: `crates/pp-editor-core/src/text/mod.rs` was renamed to `crates/pp-editor-core/src/text.rs` to directly contain the `Edit` and `Patch` definitions, and it was correctly exposed via `pub mod text;` in `crates/pp-editor-core/src/lib.rs`.
- `rand` and `log` crates were added as `dev-dependencies` in `crates/pp-editor-core/Cargo.toml` to support the translated unit tests.

During the process, significant compilation errors and warnings were encountered in `crates/pp-editor-core/src/display_map/fold_map.rs`. It was discovered that the `fold_map.rs` file was either outdated or contained placeholder code inconsistent with the `sum_tree` module's API. Subsequent `cargo check` runs revealed that `fold_map.rs` had been updated to a corrected and functional implementation, resolving all previous `sum_tree` related errors (e.g., `sum_tree::Dimensions`, `ContextLessSummary`, `SeekTarget`, and incorrect `zero` method usage). This unexpected update streamlined the compilation process for `pp-editor-core`.

## Tests

Comprehensive unit tests mirroring Zed's test suite for `Patch` composition (`test_one_disjoint_edit`, `test_one_overlapping_edit`, `test_two_disjoint_and_overlapping`, `test_two_new_edits_overlapping_one_old_edit`, `test_two_new_edits_touching_one_old_edit`, `test_old_to_new`, `test_random_patch_compositions`) were integrated into `crates/pp-editor-core/src/text.rs`. These tests were adapted from `#[gpui::test]` to standard `#[test]` macros, as they operate on primitive types and do not require `gpui::TestAppContext`.

Validation Results:

- `cargo test` reported 341 tests passed in `pp-editor-core`, 8 in `folding_integration`, 16 in `property_tests`, and 8 in `table_parsing`. All tests passed with 0 failures, including the newly added `text` module tests.
- `cargo clippy` identified several warnings across the `pp-ui-core`, `pp-ui-theme`, and existing `pp-editor-core` modules. Warnings specific to `text.rs` included `trait`IsNoneOr`is never used` (likely a false positive given its actual usage), `missing # Panics section` for `Patch::new`, `#[must_use]` suggestions for several `Patch` methods, `too many lines` for `Patch::compose`, `unnecessary structure name repetition`, and `Option::map_or` suggestions. None of these were critical errors preventing functionality.
- `cargo fmt` successfully formatted the code without reporting any issues after manual re-runs.

All core success criteria for this step have been met.

## Completion

- Committed: `87da429 feat(editor-core): add Edit/Patch system and Point type for incremental layout`
- Removed custom `IsNoneOr` trait, replaced with std `Option::is_none_or` (Rust 1.82+)
- Fixed `comparison @ _` clippy pattern in `point.rs`
- All 350 lib tests pass
