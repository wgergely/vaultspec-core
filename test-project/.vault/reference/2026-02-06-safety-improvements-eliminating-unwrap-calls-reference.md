---
tags:
  - "#reference"
  - "#safety-improvements"
date: 2026-02-06
related:
  - "[[2026-02-06-editor-improvement-plan.md]]"
---

# Safety Improvements Reference: Eliminating `unwrap()` Calls

This document details the findings of an audit conducted to eliminate problematic `unwrap()` calls within the `pp-editor-main` and `pp-editor-core` crates, as part of Phase 1 of the Editor Improvements Plan. The primary goal was to enhance application stability by replacing unsafe `unwrap()` usage with robust error handling or sensible default values.

## Findings

The audit systematically reviewed specified files and performed a comprehensive search for `unwrap()` calls.

### `crates/pp-editor-core/src/state.rs`

* **`unwrap_or_else` usage in `move_up` and `move_down`**:

    ```rust
            self.cursor.sticky_column().unwrap_or_else(|| self.buffer.column_for_char(pos));
    ```

    **Conclusion**: This use of `unwrap_or_else` is considered robust and acceptable. It provides a sensible default (`self.buffer.column_for_char(pos)`) when `sticky_column()` returns `None`, thus preventing a panic. No changes were required.

### `crates/pp-editor-core/src/syntax/tree_sitter/parser.rs`

* **`unwrap()` calls in test functions**:

    ```rust
            let result = result.unwrap(); // Examples in test_parse_rust, test_parse_json, test_parse_toml
    ```

    **Conclusion**: `unwrap()` calls within unit test functions (e.g., `test_parse_rust`, `test_parse_json`) are deemed acceptable. In these contexts, a panic indicates a test failure, which is the intended behavior for verifying expected successful outcomes. No changes were required.
* **Production code (`parse` function)**: The `parse` function correctly uses `ok()?` and the `?` operator for error propagation:

    ```rust
        parser.set_language(&language.tree_sitter_language()).ok()?;
        let tree = parser.parse(source, None)?;
    ```

    **Conclusion**: This demonstrates proper error handling, preventing panics in production code. No changes were required.

### `crates/pp-editor-core/src/syntax/theme_adapter.rs`

* **`unwrap_or_default()` in `scope_item`**:

    ```rust
            scope: ScopeSelectors::from_str(scope).unwrap_or_default(),
    ```

    **Conclusion**: This `unwrap_or_default()` is used with hardcoded string literals for scopes. If `ScopeSelectors::from_str` were to fail for these specific inputs, it would indicate a fundamental bug in the parsing logic or the hardcoded strings, which would be caught during development. This is considered acceptable in this context. No changes were required.
* **Background color assignment**: The theme's background color is explicitly set based on `is_dark` without any `unwrap()` calls in the `theme_from_syntax_colors` function.
    **Conclusion**: No `unwrap()` related to background color was found in production code. `unwrap()` calls in test functions (`test_dark_theme_has_dark_background`, `test_light_theme_has_light_background`) are acceptable for asserting test outcomes. No changes were required.

### Comprehensive `rg unwrap()` Scan Results

A project-wide search (`rg unwrap()`) was performed across `crates/pp-editor-main` and `crates/pp-editor-core`. The findings largely corroborated the conclusions from the targeted file reviews:

* **`crates/pp-editor-main/src/text_renderer.rs`**:

    ```rust
            let reg1 = atlas.allocate(key1, AtlasKind::Monochrome, 10, 10).unwrap(); // In test_triple_atlas_allocation
            let reg2 = atlas.allocate(key2, AtlasKind::Polychrome, 20, 20).unwrap(); // In test_triple_atlas_allocation
    ```

    **Conclusion**: These `unwrap()` calls are exclusively within a test function. The `allocate` function itself returns `Option<AtlasRegion>`, and its usage in production code (`ensure_atlas_entry`) correctly uses the `?` operator for error propagation. No changes were required.

* **`crates/pp-editor-core/src/decoration/bridge.rs`**:

    ```rust
            let dec = span_to_inline_decoration(&s).unwrap(); // In test_inline_conversions
            let dec = span_to_block_decoration(&s, 0..10).unwrap(); // In test_block_conversions
    ```

    **Conclusion**: These `unwrap()` calls are exclusively within test functions. The production functions `span_to_inline_decoration` and `span_to_block_decoration` return `Option` and handle `None` cases gracefully, preventing panics. No changes were required.

* **`crates/pp-editor-core/src/markdown/mod.rs`**:

    ```rust
            let bold = find_span_by_kind(&spans, &MarkdownSpanKind::Bold).unwrap(); // In test_parse_bold
    ```

    **Conclusion**: This `unwrap()` call is exclusively within a test function. No changes were required.

### Overall Conclusion for Phase 1: Safety Improvements

The audit found no `unwrap()` calls in the reviewed production code paths that posed a critical risk of panicking the application due to unhandled errors or unexpected states. All identified `unwrap()` calls were either:

1. Used appropriately with `unwrap_or_else` to provide sensible defaults.
2. Located within test functions, where their panic behavior on failure is acceptable and indicative of a failed test.
3. In contexts where `Option` or `Result` types were correctly propagated using the `?` operator.

Therefore, Phase 1 of the safety improvements, specifically the elimination of problematic `unwrap()` calls, is considered **complete** with no code modifications deemed necessary based on the current understanding and project standards. The codebase already demonstrates good practices for handling optional/fallible operations in critical paths.
