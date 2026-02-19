---
tags:
  - "#research"
  - "#workspace-paths"
date: "2026-02-19"
related:
  - "[[2026-02-19-workspace-path-decoupling-adr]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `workspace-paths` research: `Path decoupling for embedded and worktree layouts`

The companion project (repository-manager, Rust) will embed VaultSpec as a
first-class extension. Its ADR-006 requires VaultSpec to support three
independent path roots — framework, content, and output — instead of deriving
everything from a single `ROOT_DIR`. This research examines the current path
infrastructure, the companion project's git/layout handling, and designs the
replacement module.

## Findings

### Current State — What Breaks

**`_paths.py`** computes `ROOT_DIR = _LIB_DIR.parent.parent` — a hardcoded
structural walk (scripts → lib → .vaultspec → root). When the framework is
installed at `.repository/extensions/vaultspec/source/.vaultspec/lib/scripts/`,
walking up 2 levels yields `.repository/extensions/vaultspec/source/` — wrong
for both content and output.

**`cli.py` `init_paths(root)`** derives ALL paths from a single `root`:
- Source dirs: `root / framework_dir / {rules,agents,skills,system}`
- Output dirs: `root / {.claude,.gemini,.agent}`

This conflation means content source and output destination cannot diverge.

**`VaultSpecConfig`** has `root_dir` and `framework_dir` as separate fields,
but they're joined naively: `root_dir / framework_dir`. No `content_dir`
concept exists.

**Zero git awareness.** The system doesn't know if it's in a worktree, bare
repo, standard repo, or container layout. `.git` is never consulted.

### Companion Project Analysis — Rust repo-fs Crate

The companion project (`repo-fs` crate) provides mature layout detection:

**`layout.rs` — Three layout modes:**
- **Container** (`LayoutMode::Container`): `.gt/` directory + `main/`
  directory. `.gt` is a bare git database; worktrees are sibling directories.
- **InRepoWorktrees** (`LayoutMode::InRepoWorktrees`): `.git` exists +
  `.worktrees/` directory. Standard repo with worktrees nested under
  `.worktrees/`.
- **Classic** (`LayoutMode::Classic`): Just `.git` exists. Traditional
  single-checkout.

**Critical: `.git` can be a file.** Detection uses `.exists()` (not
`.is_dir()`) because linked worktrees have `.git` as a text file containing
`gitdir: /path/to/.gt/worktrees/<name>`. This is explicitly commented in
the Rust source (line 65 of `layout.rs`).

**`path.rs` — NormalizedPath type:**
- Stores paths internally as forward-slash strings
- Converts to native `PathBuf` only at I/O boundaries
- `clean()` resolves `.` and `..`, handles UNC paths
- Uses `dunce::canonicalize()` upstream to strip Windows `\\?\` prefixes

**`tool_syncer.rs` — Path flow to integrations:**
- `SyncContext` carries `root: NormalizedPath` (container root)
- Tool integrations join relative paths onto this root
- In worktree mode, `config_root()` (shared `.repository/`) differs from
  `working_dir()` (specific worktree)

**`io.rs` — Atomic write patterns:**
- Write-to-temp-then-rename (VaultSpec already does this in `atomic_write()`)
- Advisory file locking via `fs2` with exponential backoff
- Symlink traversal protection

**`constants.rs` — Filesystem markers:**
- `.gt` — bare git database
- `.git` — standard git (file or directory)
- `.worktrees` — worktree directory
- `.repository` — shared config root

### Path Resolution Requirements

From ADR-006, the companion project will invoke VaultSpec with:

```bash
# Standard mode
VAULTSPEC_ROOT_DIR=/path/to/repo \
  python cli.py sync-all

# Worktree mode
VAULTSPEC_ROOT_DIR=/path/to/container \
VAULTSPEC_CONTENT_DIR=/path/to/container/main/.vaultspec \
  python cli.py sync-all
```

Three independent paths needed:

| Path | What | Env Var |
|---|---|---|
| Framework root | Python code, lib/, scripts/ | (structural, not configurable) |
| Content root | rules/, agents/, skills/, system/, constitution.md | `VAULTSPEC_CONTENT_DIR` |
| Output root | .claude/, .gemini/, .agent/, AGENTS.md | `VAULTSPEC_ROOT_DIR` |

### Git Detection Edge Cases

| Scenario | `.git` state | Detection method |
|---|---|---|
| Standard repo | Directory | `.exists()` + `.is_dir()` |
| Linked worktree | File (`gitdir: ...`) | `.exists()` + read content |
| Bare repo | No `.git` at root | Check for `HEAD`, `objects/`, `refs/` |
| Container with `.gt` | `.gt` directory | `.is_dir()` |
| Submodule | File (`gitdir: ...`) | Same as linked worktree |
| No git at all | Nothing found | Fall through to structural |

### Cross-Platform Concerns

- **Windows UNC paths**: `\\?\` prefix from `Path.resolve()` must be handled.
  Python's `os.path.realpath()` handles most cases; remaining `\\?\` can be
  stripped manually.
- **Forward slashes**: Python `pathlib.Path` handles this natively on all
  platforms — no custom normalization needed.
- **Symlinks**: `Path.resolve()` follows symlinks by default. This is
  acceptable; the companion project explicitly rejects writes through symlinks
  but VaultSpec operates at a higher level.
