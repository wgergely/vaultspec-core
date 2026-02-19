---
description: >-
  Modern find and replace tool (sd). Use for fast, intuitive text
  manipulation and in-place file modifications.
---

# Search and Displace Skill (sd)

**Announce at start:** "I'm using `sd` to replace `{pattern}` with
`{replacement}`."

---

<!-- Human-readable documentation above | Agent instructions below -->

---

## Best Practices

- **String Mode**: Use `-s` or `--string-mode` for literal substitutions to
  avoid escaping regex special characters.
- **Preview First**: Use `-p` or `--preview` to see changes before they are
  applied in-place.
- **Regex Syntax**: Uses familiar JavaScript/Python flavor; use capture groups
  like `$1`, `$2`.
- **In-place by Default**: `sd` modifies files directly; ensure you have a
  "Pre-flight" check or backup if unsure.

## When to use

| Tool | Core Strength | Surgical Output Format |
| :--- | :--- | :--- |
| **rg** | Performance & Filter | `--json` (Byte-offsets, column/line) |
| **sd** | Textual Parity | In-place atomic writes |
| **sg** | Logic & Syntax | `--rewrite` (AST transformation) |

## Shell Usage

### PowerShell (Validated Pipeline: fd -> sd)

```powershell
# Preferred: Handles quoting and parallelization natively
fd -e ts -x sd "OldAPI" "NewAPI" {}

# Combined with rg for targeted replacement
rg "OldClass" -l0 | ForEach-Object { sd "OldClass" "NewClass" $_ }
```

### Unix/Shell

```bash
# Combined with rg for targeted replacement
rg -l0 'pattern' | xargs -0 sd 'pattern' 'replacement'
```

## Related Skills

- `rg`: Use for high-performance searching and filtering files to be
  processed by `sd`.
