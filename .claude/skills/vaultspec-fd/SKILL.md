---
name: vaultspec-fd
description: Simple, fast and user-friendly alternative to `find`. Use for discovering
  files and feeding them into other tools.
---

# Discovery Skill (fd)

**Announce at start:** "I'm using `fd` to find files matching <pattern>."

## Best Practices

- **Smart Defaults**: `fd` ignores hidden files and directories, and respects `.gitignore` by default.
- **Extension Filtering**: Use `-e` (e.g., `-e ts`) for faster filtering by file extension.
- **Execution**: Use `-x` or `--exec` to run a command on every search result. Use `-X` (exec-batch) to run the command once with all results as arguments. These are **preferred over manual pipes** in PowerShell as they handle quoting and parallelization natively.
- **Path Placeholders**:
  - `{}`: Full path (e.g., `src/main.js`)
  - `{/}`: Basename only (e.g., `main.js`)
  - `{//}`: Parent directory (e.g., `src`)
  - `{.}`: Path without extension (e.g., `src/main`)
- **Case Sensitivity**: Use `-i` for case-insensitive or `-s` for case-sensitive (defaults to smart case).

## When to use

| Tool | Core Strength | Surgical Output Format |
| :--- | :--- | :--- |
| **fd** | Discovery & Speed | File paths / `--exec` |
| **rg** | Performance & Filter | `--json` (Byte-offsets, column/line) |
| **sd** | Textual Parity | In-place atomic writes |
| **sg** | Logic & Syntax | `--rewrite` (AST transformation) |

## Shell Usage

### PowerShell

```powershell
# Find all python files in cwd and run a command
fd -e py | ForEach-Object { <command> $_ }
```

### Unix/Shell

```bash
# Find all python files and run a command
fd -e py -x <command>
```

## Related Skills

- `rg`: Use for searching *inside* the files found by `fd`.
- `sd`: Use for replacing text in the files found by `fd`.
