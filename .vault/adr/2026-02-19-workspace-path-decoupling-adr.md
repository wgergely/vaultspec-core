---
tags:
  - "#adr"
  - "#workspace-paths"
date: "2026-02-19"
related:
  - "[[2026-02-19-workspace-path-decoupling-research]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `workspace-paths` adr: `Three-path workspace decoupling with git-aware layout detection` | (**status:** `accepted`)

Response to companion project ADR-006 (VaultSpec Directory Placement and Path
Decoupling). Defines VaultSpec's strategy for supporting embedded operation
inside repository-manager managed projects, git worktrees, and container
layouts — while preserving full backwards compatibility for standalone use.

## Problem Statement

VaultSpec derives all filesystem paths from a single `ROOT_DIR` computed by
structural navigation (`_paths.py`: scripts → lib → .vaultspec → root). This
breaks in two scenarios:

1. **Embedded deployment.** When the framework is installed at
   `.repository/extensions/vaultspec/source/`, the structural walk yields the
   wrong root. Content (`.vaultspec/`), output (`.claude/`, `.gemini/`), and
   knowledge base (`.vault/`) all live at the container root — but the
   framework Python code lives elsewhere.

2. **Git worktree layouts.** In container mode (bare repo at `.gt/` with
   sibling worktrees), `.vaultspec/`, `.vault/`, `.claude/`, `.gemini/` are
   all peers at the container root, shared across worktrees. Worktrees
   contain source code only. VaultSpec has zero git awareness and cannot
   locate the container root from a worktree CWD.

The companion project (repository-manager, Rust) requires VaultSpec to accept
three independently configurable path roots via environment variables.

## Considerations

**Companion project requirements (ADR-006):**
- `VAULTSPEC_ROOT_DIR` — output root (where `.claude/`, `.gemini/` are written)
- `VAULTSPEC_CONTENT_DIR` — content source (where rules, agents, skills are read)
- `VAULTSPEC_FRAMEWORK_DIR` — framework directory name (already exists)
- Backwards-compatible defaults for standalone use
- The repo manager passes explicit paths via env vars when invoking CLI/MCP

**Companion project's git handling (repo-fs crate):**
- Three layout modes: Container (`.gt`), InRepoWorktrees (`.worktrees`),
  Classic (`.git`)
- `.git` detected with `.exists()` not `.is_dir()` — linked worktrees use
  `.git` files containing `gitdir: <path>` pointers
- `dunce::canonicalize()` for Windows UNC prefix stripping
- `NormalizedPath` type: forward-slash internal, native at I/O boundary
- `SyncContext` separates `config_root()` (shared) from `working_dir()`
  (per-worktree)

**Existing VaultSpec infrastructure:**
- `VaultSpecConfig` already supports `VAULTSPEC_*` env vars with type parsing
  and validation
- `_paths.py` provides `ROOT_DIR` and `LIB_SRC_DIR` as module-level globals
- `cli.py` `init_paths(root)` sets all global path variables from one root
- All three CLIs (cli.py, subagent.py, docs.py) accept `--root` with
  `ROOT_DIR` fallback
- `atomic_write()` already uses write-to-temp-then-rename

**Alternative approaches considered:**
- **Do nothing, rely on `--root` only.** Rejected: a single root cannot
  address content/output divergence in worktree mode.
- **Symlink content into output root.** Rejected: fragile, OS-dependent,
  breaks on Windows in restricted environments.
- **Config file at output root pointing to content.** Rejected: adds a
  configuration layer the companion project already handles via env vars.

## Constraints

- Must not break standalone VaultSpec usage — zero-config when no env vars set
- Must not require git to be installed or accessible (env vars bypass detection)
- Must work on Windows 11 (primary dev environment) including UNC paths
- Python 3.13+ only (can use modern pathlib APIs)
- No new dependencies — stdlib only for the workspace module
- The companion project controls invocation; VaultSpec responds to the paths
  it receives

## Implementation

### New Module: `core/workspace.py`

A single new module replaces scattered path logic with a validated, git-aware
workspace resolver. Approximately 250 lines of stdlib-only Python.

#### Data Types

```python
from enum import Enum
from dataclasses import dataclass
from pathlib import Path


class LayoutMode(Enum):
    """How VaultSpec was invoked and where paths point."""
    STANDALONE = "standalone"   # Classic: all paths at one root (incl. container mode)
    EXPLICIT = "explicit"       # Paths provided via env vars (embedded deployment)


@dataclass(frozen=True)
class GitInfo:
    """Discovered git repository metadata."""
    git_dir: Path              # Actual .git directory (resolved from pointer)
    repo_root: Path            # Root of the git repository
    is_worktree: bool          # True if linked worktree (not main working tree)
    is_bare: bool              # True if bare repository (.gt)
    worktree_root: Path | None # This worktree's root, if is_worktree
    container_root: Path | None  # Container root, if container/worktree mode


@dataclass(frozen=True)
class WorkspaceLayout:
    """Fully resolved, validated workspace paths."""
    content_root: Path         # Where rules/, agents/, skills/, system/ live
    output_root: Path          # Where .claude/, .gemini/, .agent/ are written
    vault_root: Path           # Where .vault/ documentation lives
    framework_root: Path       # Where framework Python code lives (lib/, scripts/)
    mode: LayoutMode           # Detected layout mode
    git: GitInfo | None        # Git context, if detected
```

#### Git Detection

```python
def discover_git(start: Path) -> GitInfo | None:
    """Walk up from start to find and classify the git repository.

    Handles: standard repos (.git/ dir), linked worktrees (.git file with
    gitdir pointer), container mode (.gt/ bare repo), bare repos.
    """
```

Key implementation details:
- `.git` checked with `.exists()`, NOT `.is_dir()` — worktrees use files
- `.git` file content parsed for `gitdir: <path>` (absolute or relative)
- `.gt/` checked with `.is_dir()` for container mode
- Walk-up terminates at filesystem root (prevents infinite loops)
- `Path.resolve()` used for canonicalization; manual `\\?\` stripping on
  Windows if needed

#### Resolution Function

```python
def resolve_workspace(
    *,
    root_override: Path | None = None,       # --root / VAULTSPEC_ROOT_DIR
    content_override: Path | None = None,     # --content-dir / VAULTSPEC_CONTENT_DIR
    framework_dir_name: str = ".vaultspec",   # VAULTSPEC_FRAMEWORK_DIR
    framework_root: Path | None = None,       # Structurally known; passed from _paths.py
    cwd: Path | None = None,                  # For testing; defaults to Path.cwd()
) -> WorkspaceLayout:
    """Resolve the complete workspace layout from overrides, git, and structure.

    framework_root is the structurally-known location of the .vaultspec/
    directory containing the Python code. It is always computed from the
    physical script location by _paths.py and passed here directly —
    never derived from env vars or git detection.
    """
```

Resolution priority per path:

| Priority | Source | Applies to |
|---|---|---|
| 1 | Explicit env var / CLI flag | content_root, output_root |
| 2 | Git-aware auto-detection | content_root, output_root |
| 3 | Structural fallback (_paths.py behavior) | all paths |

Resolution matrix:

| Condition | Mode | content_root | output_root | vault_root |
|---|---|---|---|---|
| Both `CONTENT_DIR` + `ROOT_DIR` set | EXPLICIT | env `CONTENT_DIR` | env `ROOT_DIR` | `output_root / .vault` |
| Only `ROOT_DIR` set | STANDALONE | `root / fw_dir` | `root` | `root / .vault` |
| No env vars, classic git | STANDALONE | `repo_root / fw_dir` | `repo_root` | `repo_root / .vault` |
| No env vars, container git (`.gt/`), CWD anywhere | STANDALONE | `container_root / fw_dir` | `container_root` | `container_root / .vault` |
| No env vars, linked worktree (`.git` file) | STANDALONE | `repo_root / fw_dir` | `repo_root` | `repo_root / .vault` |
| No env vars, no git | STANDALONE | structural fallback | structural fallback | structural / .vault |

**Key simplification (per ADR-006 Appendix A):** In container/worktree mode,
`.vaultspec/`, `.vault/`, `.claude/`, `.gemini/`, `.agent/`, and `AGENTS.md`
are ALL peers at the container root, shared across worktrees. Worktrees
contain source code only. This means content and output always share the same
root in container mode — `VAULTSPEC_CONTENT_DIR` is not needed. The repo
manager sets only `VAULTSPEC_ROOT_DIR` to the container root.

**`vault_root` resolution rule:** `.vault/` is project-level shared knowledge
(ADRs, research, plans). It follows `output_root` semantics — it lives at the
same root as `.claude/` and `.vaultspec/`, shared across all worktrees. In
every row of the matrix, `vault_root = output_root / .vault`. A future
`VAULTSPEC_VAULT_DIR` env var can override this if needed.

**Container detection from worktree CWD:** When a standalone user's CWD is
inside a worktree (e.g., `my-project/feature-branch/`), `discover_git()`
finds the `.git` file, parses the gitdir pointer, traces it back to the
`.gt/` bare repo, and resolves the container root as `.gt`'s parent. All
paths then point to the container root, where `.vaultspec/` and `.vault/`
actually live. If CWD is the container root itself, `.gt/` is found directly.

**Linked worktree (non-container):** For standard git repos with linked
worktrees (`.git/worktrees/`), the `.git` file in the worktree points back to
the main repo's `.git/` directory. `discover_git()` resolves to the main repo
root — where `.vaultspec/` and `.vault/` live.

#### Validation

Every resolved `WorkspaceLayout` is validated:
- `content_root` must be a directory (or error with fix suggestion)
- `output_root` parent must exist
- `framework_root / lib` must exist
- Errors include the env var name to set for override

### Changes to Existing Files

**`core/config.py`** — One new field + registry entry:

```python
# In VaultSpecConfig:
content_dir: Path | None = None

# In CONFIG_REGISTRY:
ConfigVariable(
    env_name="VAULTSPEC_CONTENT_DIR",
    attr_name="content_dir",
    var_type=Path,
    default=None,
    description="Content source directory override.",
)
```

**`_paths.py`** — Becomes a thin shim with preserved bootstrap ordering:

The critical invariant: `_paths.py` must compute `LIB_SRC_DIR` structurally
and add it to `sys.path` BEFORE importing anything from the library. The
framework code physically lives at the script location regardless of where
content or output roots point. Only after `sys.path` is set up can we import
`core.workspace`.

```python
import os
import sys
from pathlib import Path

# Step 1: Structural bootstrap (always correct for framework location)
# This is WHERE THE PYTHON CODE LIVES — not where content lives.
_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPTS_DIR.parent              # .vaultspec/lib/
_FRAMEWORK_ROOT = _LIB_DIR.parent           # .vaultspec/
LIB_SRC_DIR = _LIB_DIR / "src"

if str(LIB_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_SRC_DIR))

# Step 2: Now safe to import from the library
from core.workspace import resolve_workspace

def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw) if raw else None

_layout = resolve_workspace(
    root_override=_env_path("VAULTSPEC_ROOT_DIR"),
    content_override=_env_path("VAULTSPEC_CONTENT_DIR"),
    framework_dir_name=os.environ.get("VAULTSPEC_FRAMEWORK_DIR", ".vaultspec"),
    framework_root=_FRAMEWORK_ROOT,  # pass the structurally-known location
)
ROOT_DIR = _layout.output_root
```

`framework_root` is passed explicitly from the structural computation — it is
never derived from env vars or git detection. The `resolve_workspace()`
function accepts an optional `framework_root` parameter; when provided, it
uses it directly rather than trying to discover it.

The structural fallback for `output_root` and `content_root` (when no env
vars are set and no git is detected) uses `_FRAMEWORK_ROOT.parent` —
equivalent to the old `_LIB_DIR.parent.parent` behavior.

**`cli.py` `init_paths()`** — Signature changes from `init_paths(root: Path)`
to `init_paths(layout: WorkspaceLayout)`:

```python
def init_paths(layout: WorkspaceLayout) -> None:
    global ROOT_DIR, RULES_SRC_DIR, AGENTS_SRC_DIR, ...

    # Source dirs from CONTENT root
    ROOT_DIR = layout.output_root
    RULES_SRC_DIR = layout.content_root / "rules"
    AGENTS_SRC_DIR = layout.content_root / "agents"
    SKILLS_SRC_DIR = layout.content_root / "skills"
    SYSTEM_SRC_DIR = layout.content_root / "system"
    CONSTITUTION_SRC = layout.content_root / "constitution.md"

    # Output dirs from OUTPUT root
    TOOL_CONFIGS = {
        "claude": ToolConfig(
            rules_dir=layout.output_root / cfg.claude_dir / "rules",
            config_file=layout.output_root / cfg.claude_dir / "CLAUDE.md",
            ...
        ),
        ...
    }
```

This is the core decoupling — sources read from `content_root`, outputs
written to `output_root`.

**All three CLIs** — Gain `--content-dir` flag:

```python
parser.add_argument(
    "--content-dir", type=Path, default=None,
    help="Content source directory (rules, agents, skills)",
)
```

And in `main()`:

```python
layout = resolve_workspace(
    root_override=args.root,
    content_override=getattr(args, "content_dir", None),
)
init_paths(layout)
```

### Test Coverage: `core/tests/test_workspace.py`

Unit tests for all detection modes using `tmp_path` fixtures:
- Standard git repo (`.git/` directory) — all paths at repo root
- Linked worktree (`.git` file with gitdir pointer) — resolves to repo root
- Container mode (`.gt/`), CWD inside a worktree — resolves to container root
- Container mode (`.gt/`), CWD at container root — resolves to container root
- No git context (structural fallback)
- Explicit env vars override everything (EXPLICIT mode)
- `--content-dir` flag with `--root` flag
- vault_root always follows output_root (`output_root / .vault`)
- Validation errors (missing content_root, missing framework lib/)
- Bootstrap ordering: framework_root from structural, not from env vars
- Windows path handling (UNC prefix stripping)

## Rationale

**Why a new module rather than extending `_paths.py`:**
`_paths.py` is a bootstrap script that runs at import time before the full
library is available. Git detection and layout resolution require non-trivial
logic that belongs in the library (`core/`), not in a bootstrap shim. The
shim remains but delegates to the module.

**Why git detection is built-in rather than relying solely on env vars:**
The companion project will always set env vars when invoking VaultSpec. But
VaultSpec also needs to work standalone — developers running `cli.py` directly
inside a worktree should get correct behavior without setting anything. Git
detection provides zero-config correctness for standalone use.

**Why `WorkspaceLayout` is a frozen dataclass:**
Paths must not change after resolution. A mutable layout would allow
inconsistent states where some code sees old paths and some sees new ones.
Frozen ensures resolve-once-use-everywhere semantics.

**Why LayoutMode exists:**
Diagnostic and logging value. When something goes wrong with path resolution,
knowing the detected mode immediately narrows the problem space. It also
enables mode-specific behavior in the future (e.g., worktree mode might skip
certain output files that are shared).

## Consequences

**Positive:**
- VaultSpec can run embedded inside repository-manager without structural
  assumptions about its own location
- Git worktree/container layouts work correctly: `.vaultspec/`, `.vault/`,
  and all output directories are peers at the container root, shared across
  worktrees
- Standalone use is completely unaffected — all new paths have
  backwards-compatible defaults
- Validation catches misconfigured paths early with actionable error messages
- The `WorkspaceLayout` type provides a single source of truth, replacing
  scattered global variables

**Negative:**
- Adds ~250 lines of new code in `core/workspace.py`
- `init_paths()` signature change requires updating all call sites (3 CLIs +
  tests)
- Git detection adds ~50ms on first invocation (directory walk, file reads);
  negligible for CLI usage but measurable
- Test fixtures need to create mock `.git` files/directories

**Migration path:**
- No user-facing migration needed for standalone users
- The companion project sets env vars; no VaultSpec config file changes
- Existing `--root` flag semantics preserved (becomes output root override)
- `VAULTSPEC_ROOT_DIR` env var semantics preserved (already existed)

**Deliverables summary:**

| # | Change | Scope |
|---|---|---|
| 1 | `core/workspace.py` — WorkspaceLayout, GitInfo, LayoutMode, resolve_workspace(), discover_git() | New file (~250 lines) |
| 2 | `core/config.py` — Add `content_dir` field + VAULTSPEC_CONTENT_DIR registry entry | Small edit |
| 3 | `_paths.py` — Delegate to resolve_workspace(), structural fallback inside resolver | Small edit |
| 4 | `cli.py` — init_paths() takes WorkspaceLayout; add --content-dir flag | Medium edit |
| 5 | `subagent.py`, `docs.py` — Add --content-dir flag, use resolve_workspace() | Small edits |
| 6 | `core/tests/test_workspace.py` — Unit tests for all layout modes | New file (~200 lines) |
| 7 | `requirements.txt` — Fix stale dependency list (ADR-006 item 4) | Small edit |
| 8 | `extension.toml` — New file for companion project discovery (ADR-006 item 5) | New file (~20 lines) |
