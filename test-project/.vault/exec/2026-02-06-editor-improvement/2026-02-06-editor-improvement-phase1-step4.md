---
tags:
  - "#exec"
  - "#editor-improvement"
date: 2026-02-06
related:
  - "[[2026-02-06-editor-improvement-plan]]"
---

# editor-improvement phase-1 task-4

## Problem

The `Buffer::line_end_char` function in `crates/pp-editor-core/src/buffer.rs` currently only accounts for `
` (LF) as a line ending character when calculating the effective end of a line. This can lead to incorrect character indexing and potential trailing `
` issues in cross-platform scenarios, especially when dealing with files that use `
` (CRLF) line endings. The `Ropey` library, when configured with `LineType::LF`, treats `
` as part of the line's content if it precedes a `
`.

## Solution

Modify the `Buffer::line_end_char` function to correctly identify and exclude both `
` and `
` from the reported line length. This will be achieved by:

1. Iterating the characters of the `RopeSlice` for the given line in reverse.
2. If the last character is `
`, decrement the `content_len`.
3. If, after removing `
`, the next character in reverse is `
`, decrement `content_len` again.

## Proposed Change

```rust
    /// Get the character index for the end of a line (before newline).
    #[must_use]
    pub fn line_end_char(&self, line_idx: usize) -> usize {
        let line = self.line(line_idx);
        let line_start = self.line_to_char(line_idx);
        let mut content_len = line.len_chars();

        if content_len > 0 {
            let mut chars = line.chars().rev();
            if let Some(last_char) = chars.next() {
                if last_char == '
' {
                    content_len -= 1;
                    if let Some(second_last_char) = chars.next() {
                        if second_last_char == '
' {
                            content_len -= 1;
                        }
                    }
                }
            }
        }
        line_start + content_len
    }
```

## Unit Tests

Add unit tests to `crates/pp-editor-core/src/buffer.rs` to cover CRLF handling:

- Test a line ending with `
`.
- Test a line ending with `
`.
- Test a line without any explicit line ending (e.g., the last line of a file).
- Test empty lines with `
` and `
` endings.

This change ensures that `line_end_char` provides accurate character indices for the logical end of a line, regardless of the line ending convention.
