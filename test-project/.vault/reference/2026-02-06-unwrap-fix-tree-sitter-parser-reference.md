---
feature: unwrap-fix-tree-sitter-parser
date: 2026-02-06
related: [[2026-02-06-editor-audit-reference]]
---

# `unwrap()` Audit and Fix for `crates/pp-editor-core/src/syntax/tree_sitter/parser.rs`

## 1. Objective

This document details the audit and (if necessary) fix of `unwrap()` calls within the `crates/pp-editor-core/src/syntax/tree_sitter/parser.rs` file. The primary goal is to ensure memory safety, crash resistance, and adherence to the project's "No-Crash" mandate by replacing `unwrap()` with robust error handling mechanisms (e.g., `Result` propagation, `?` operator, or appropriate fallbacks) and defining clear error types.

## 2. Audit Findings

A thorough review of `crates/pp-editor-core/src/syntax/tree_sitter/parser.rs` was conducted to identify all instances of `.unwrap()`, `.expect()`, `panic!`, `todo!`, and `unimplemented!` in production code paths.

The audit revealed **no direct `.unwrap()` or `.expect()` calls in the production code** within this file.

The `parse` function, which is the primary public interface for parsing, correctly utilizes `ok()?` and the `?` operator for error propagation:

```rust
pub fn parse(source: &str, language: Language) -> Option<ParseResult> {
    let mut parser = Parser::new();
    parser.set_language(&language.tree_sitter_language()).ok()?;

    let tree = parser.parse(source, None)?;

    Some(ParseResult { tree, language })
}
```

This ensures that any failure in setting the Tree-sitter language or parsing the source code results in `None` being returned, rather than a panic.

Similarly, the `impl FromStr for Language` correctly returns `Result<Self, Self::Err>`, preventing panics when an unknown language string is encountered.

```rust
impl FromStr for Language {
    type Err = ParseLanguageError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        // ... match statement ...
        _ => Err(ParseLanguageError(s.to_string())),
    }
}
```

## 3. Test Code Review

The only instances of `panic!` were found within the `#[cfg(test)]` module, specifically in assertions like `panic!("Expected parse result to be Some");`. In unit test contexts, `panic!` is an acceptable mechanism for signaling test failures and does not violate the "No-Crash" mandate for production code.

## 4. Error Types

The file already defines a specific error type for parsing language strings:

```rust
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseLanguageError(String);
```

This adheres to the standard of providing contextual error information.

## 5. Conclusion and Fixes Applied

No `unwrap()`, `expect()`, `todo!`, or `unimplemented!` calls were found in the production logic of `crates/pp-editor-core/src/syntax/tree_sitter/parser.rs`. The existing code correctly handles potential failures through `Option` and `Result` types, utilizing `?` for ergonomic error propagation.

Therefore, **no code changes were necessary** as part of this audit. The file already adheres to the project's safety standards regarding panic prevention.

## 6. Verification

To verify the existing codebase and ensure no new issues are introduced, `cargo clippy --package pp-editor-core` will be run.

```bash
cargo clippy --package pp-editor-core
```

This will confirm the absence of common linter warnings and adherence to Rust best practices.
