# Plan for CRLF Handling in `pp-editor-core/src/buffer.rs`

## 1. Problem Statement

The current `Buffer::line_end_char` implementation might not correctly handle CRLF (`
`) line endings, leading to potential issues in cross-platform scenarios and incorrect display or manipulation of text. Specifically, it needs to accurately distinguish between LF and CRLF and prevent problems with trailing `
` characters.

## 2. Proposed Solution

The solution involves modifying the `Buffer::line_end_char` function to correctly identify and differentiate between LF and CRLF line endings. This will likely entail checking for both `
` and `
` patterns. Additionally, comprehensive unit tests will be added to ensure robust handling of various line ending scenarios.

## 3. Detailed Steps

### Phase 1: Planning and Research

1. **Create Plan Document (Done):** Generate this plan document `2026-02-06-crlf-handling-buffer-plan.md`.
2. **Initial Code Scan:** Use `rg` to locate `Buffer::line_end_char` and other relevant code snippets within `crates/pp-editor-core/src/buffer.rs` to understand its current implementation and how line endings are currently handled.
3. **Review existing tests:** Check for any existing tests related to line endings in `pp-editor-core` to understand the current testing approach.

### Phase 2: Implementation

1. **Modify `Buffer::line_end_char`:** Update the `line_end_char` function to correctly identify and differentiate between `
` (LF) and `
` (CRLF) line endings. This will likely involve checking for `
` followed by `
`.
2. **Address trailing `
`:** Ensure that the logic correctly handles cases where a `
` might appear at the end of a line without a subsequent `
`, preventing misinterpretation or data corruption.

### Phase 3: Testing and Verification

1. **Develop Unit Tests:** Write new, comprehensive unit tests specifically targeting CRLF handling. These tests will cover:
    * Files with only LF endings.
    * Files with only CRLF endings.
    * Files with mixed LF and CRLF endings.
    * Files with `
` at the end of lines.
    * Empty files and files with a single line.
2. **Execute Unit Tests:** Run `cargo test --package pp-editor-core` to validate the changes and ensure no regressions are introduced.
3. **Run Clippy:** Execute `cargo clippy --package pp-editor-core` to maintain code quality and adherence to Rust best practices.

### Phase 4: Documentation

1. **Create Reference Document:** Generate the reference document `2026-02-06-crlf-handling-buffer-reference.md`, detailing the problem, the solution implemented, and the impact of the changes.

## 4. Dependencies and Context

* **`crates/pp-editor-core/src/buffer.rs`**: The primary file to be modified.
* **`[[2026-02-06-editor-audit-reference]]`**: Provides context for editor-related audits.

## 5. Success Criteria

* `Buffer::line_end_char` correctly identifies and handles both LF and CRLF line endings.
* Trailing `
` characters are handled without issues.
* All new unit tests pass.
* `cargo clippy` runs without warnings for `pp-editor-core`.
* The `2026-02-06-crlf-handling-buffer-reference.md` document is created and accurately reflects the changes.
