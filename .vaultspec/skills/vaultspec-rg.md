---
description: "High-performance search tool (ripgrep). Use for finding patterns across the codebase and feeding matches into manipulation tools like `sd`."
---

# Search Skill (rg)

**Announce at start:** "I'm using `rg` to search for <pattern>."

---
<!-- Human-readable documentation above | Agent instructions below -->
---

## Best Practices

- **Pre-flight Check**: Always run `rg --files` first to verify which files your script will target.
- **Testing Surgery**: Use `rg -r "replacement" --passthru` to preview changes in the terminal without modifying files.
- **Fixed Strings**: Use `-F` for literal searches to improve speed and avoid regex character interpretation.
- **Language Detection**: Use `--type` (e.g., `-t py`, `-t rust`) instead of globs to include all relevant file extensions.
- **Precision Flags**:
  - `-l`: List files only (essential for piping).
  - `-0`: Use NUL byte as separator (safest for filenames with spaces).

## When to use

| Tool | Core Strength | Surgical Output Format |
| :--- | :--- | :--- |
| **rg** | Performance & Filter | `--json` (Byte-offsets, column/line) |
| **sd** | Textual Parity | In-place atomic writes |
| **sg** | Logic & Syntax | `--rewrite` (AST transformation) |

## Shell Usage

### PowerShell (High-Stakes Refactoring)

```powershell
#  Identify files with specific language types
rg "DeprecatedAPI" -l0 --type ts | ForEach-Object { 
    #  Perform atomic replacement
    sd 'DeprecatedAPI' 'NewAPI' $_ 
}

# Standard replacement pipe
rg 'OldClass' -l0 | ForEach-Object { sd 'OldClass' 'NewClass' $_ }
```

### Unix/Shell

```bash
# Feed matches into sd for replacement
rg -l0 'pattern' | xargs -0 sd 'pattern' 'replacement'
```

## Related Skills

- `sd`: Use for performing the actual "displace" (find and replace) operation.
