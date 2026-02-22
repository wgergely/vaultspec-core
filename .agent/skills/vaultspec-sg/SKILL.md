---
name: vaultspec-sg
description: Structural search and replace tool (ast-grep). Use for complex code manipulation
  based on abstract syntax trees.
---

# Manipulation Skill (sg)

**Announce at start:** "I'm using `sg` to manipulate code structure for
`{pattern}`."

## Best Practices

- **Structural Patterns**: Matches code based on AST, ignoring whitespace
  and formatting.
- **Rules**: Use YAML rules for complex linting or refactoring logic.
- **In-place**: Use `-r` or `--rewrite` to perform structural replacements.
- **Preview**: Use `--interactive` to review changes before applying.

## When to use

| Tool | Core Strength | Surgical Output Format |
| :--- | :--- | :--- |
| **rg** | Performance & Filter | `--json` (Byte-offsets, column/line) |
| **sd** | Textual Parity | In-place atomic writes |
| **sg** | Logic & Syntax | `--rewrite` (AST transformation) |

## Shell Usage

### Structural Rewrite (PowerShell/Unix)

```bash
# Convert Boolean logic into Optional Chaining
sg run --pattern '$A && $A()' --rewrite '$A?.()' --lang ts -U
```

### Temporal Filtering & Structural Sanitization (PowerShell)

```powershell
#  SCOPE: Find files modified in the last 24h
#  SURGERY: Use ast-grep to block 'eval' usage
# --stdin: tells ast-grep to read the file path from the pipe
fd --changed-within 24h -e js | ForEach-Object {
    sg run -p 'eval($CODE)' -r 'console.error("Blocked eval")' --stdin $_ -U
}
```

### High-Stakes Refactoring Pipeline (PowerShell)

```powershell
#  SCOPE: Find files containing the target pattern quickly
$files = rg "legacyFunc" -l0 --type js

#  SURGERY: Use ast-grep for context-aware rewriting
$files | ForEach-Object {
    # Rewrite calls with 2+ arguments to use an object literal
    sg run -p 'legacyFunc($A, $B)' -r 'legacyFunc({a: $A, b: $B})' --stdin $_ -U
}

#  CLEANUP: Use sd for fixed-string comment updates across those same files
$files | ForEach-Object {
    sd "// TODO: update" "// DEPRECATED: updated via ast-grep" $_
}
```

### Full Migration Pipeline (PowerShell)

```powershell
#  SCOPE: Find files that use the specific library
$targets = fd -e tsx "LegacyComponent"

#  ANALYSIS: Use rg to count occurrences and confirm scope
$targets | xargs rg -c "LegacyComponent"

#  SURGERY: Structural rewrite using ast-grep
$targets | ForEach-Object {
    sg run -p '<LegacyComponent prop={$V} />' \
           -r '<NewComponent data={$V} />' --stdin $_ -U
}

#  FINAL POLISH: Update comments using sd
$targets | ForEach-Object {
    sd "// Legacy implementation" "// Migrated to NewComponent" $_
}
```

## Related Skills

- `rg`: Use for initial text-based reconnaissance before performing
  structural surgery.
- `sd`: Use for simpler, text-based replacements when AST-awareness is not
  required.
