---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#research"
  - "#mcp-consolidation"
date: "2026-02-22"
related:
  - "[[2026-02-20-team-mcp-integration-research]]"
  - "[[2026-02-21-module-exports-part3-research]]"
  - "[[2026-02-22-cli-ecosystem-factoring-research]]"
  - "[[2026-02-21-packaging-restructure-adr]]"
  - "[[2026-02-21-module-exports-adr]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `mcp-consolidation` research: unifying the three MCP server modules

The vaultspec MCP server surface is split across three locations that have
grown organically. This research maps every import chain, entry point, test
file, and external reference, then evaluates four consolidation options.

## Findings

### 1. Current Module Inventory

**`src/vaultspec/server.py`** (116 lines) -- Unified MCP entry point.

- Creates a single `FastMCP` instance named `"vaultspec-mcp"`.
- Composes a lifespan context from `subagent_lifespan`.
- Calls `register_subagent_tools(mcp)` and `register_team_tools(mcp)`.
- `main()` resolves config, calls `initialize_server()`, `set_team_root_dir()`,
  and `mcp.run()`.
- Registered as the `vaultspec-mcp` console script in `pyproject.toml`.

**`src/vaultspec/subagent_server/`** (2 source files, 4 test files) -- Core MCP
infrastructure.

- `server.py` (961 lines): 5 MCP tools (`list_agents`, `dispatch_agent`,
  `get_task_status`, `cancel_task`, `get_locks`), agent file polling, dynamic
  resource registration, `TaskEngine`/`LockManager` globals,
  `initialize_server()`, `register_tools()`, `subagent_lifespan()`, a legacy
  standalone `main()`.
- `__init__.py`: Re-exports 9 symbols from `server.py`.
- `tests/`: `test_mcp_tools.py`, `test_mcp_protocol.py`, `test_helpers.py`,
  `test_task_engine_integration.py`.

**`src/vaultspec/mcp_tools/`** (4 source files, 1 test file) -- Additional MCP
tool modules.

- `team_tools.py` (857 lines): 10 MCP tools for team coordination, session
  persistence helpers, `set_root_dir()`, `register_tools()`.
- `vault_tools.py` (30 lines): Stub, no-op `register_tools()`.
- `framework_tools.py` (34 lines): Stub, no-op `register_tools()`.
- `__init__.py`: Re-exports all three `register_tools` functions plus 10 team
  tool functions.
- `tests/`: `test_team_tools.py`.

### 2. Import Chain Map

#### Intra-Package Imports into `server.py`

| Importer | Import |
|---|---|
| `__main__.py` | `from .server import main as run` |
| `subagent_server/tests/test_mcp_protocol.py` | `from ...server import create_server` |
| `orchestration/tests/test_team_lifecycle.py` | `from ...server import create_server` |

#### Intra-Package Imports into `subagent_server/`

| Importer | Import |
|---|---|
| `server.py` | `from .subagent_server import initialize_server, subagent_lifespan` |
| `server.py` | `from .subagent_server import register_tools as register_subagent_tools` |
| `subagent_cli.py` | `from .subagent_server.server import main as server_main` |

Note: `subagent_cli.py` reaches through `__init__.py` to import `main`
directly from `server.py` because `main` is not part of the package
`__all__` re-exports.

#### Intra-Package Imports from `subagent_server` tests

| Test File | Imports |
|---|---|
| `tests/test_mcp_tools.py` | `from .. import server as srv`, `from .. import initialize_server`, `from ..server import` (12 private functions) |
| `tests/test_mcp_protocol.py` | `from .. import server as srv`, `from .. import initialize_server`, `from ...server import create_server` |
| `tests/test_helpers.py` | `from ..server import` (4 private functions) |
| `tests/test_task_engine_integration.py` | `from ...orchestration import LockManager, TaskEngine` (no direct subagent_server imports) |

#### Intra-Package Imports into `mcp_tools/`

| Importer | Import |
|---|---|
| `server.py` | `from .mcp_tools import register_team_tools` |
| `server.py` | `from .mcp_tools.team_tools import set_root_dir as set_team_root_dir` |
| `tests/cli/test_team_cli.py` | `from ...mcp_tools.team_tools import _delete_session, _load_session, _save_session, _session_path` |
| `orchestration/tests/test_team_lifecycle.py` | `from ...mcp_tools.team_tools import _load_session, _save_session, list_teams, set_root_dir, team_status` |

#### Cross-Module Imports (between the three)

- `server.py` imports from both `subagent_server` and `mcp_tools`. This is the
  single composition point.
- `subagent_server` does NOT import from `mcp_tools`.
- `mcp_tools` does NOT import from `subagent_server`.
- There are NO circular dependencies between any pair.

### 3. Entry Points

| Entry Point | Location | Mechanism |
|---|---|---|
| `vaultspec-mcp` console script | `vaultspec.server:main` | `pyproject.toml [project.scripts]` |
| `vaultspec mcp` namespace | `__main__.py` -> `from .server import main` | CLI namespace router |
| `vaultspec subagent serve` | `subagent_cli.py` -> `server_main()` | Calls `subagent_server.server.main()` (legacy standalone) |
| `__main__.py` guarded import | `server.py` line 114 | `if __name__ == "__main__": main()` |
| `subagent_server/server.py` guarded | `server.py` line 960 | `if __name__ == "__main__": main()` (legacy) |

### 4. Test File Map

| Module | Test Files | Markers |
|---|---|---|
| `subagent_server/` | `tests/test_mcp_tools.py` | `@pytest.mark.unit` |
| `subagent_server/` | `tests/test_mcp_protocol.py` | `@pytest.mark.api` |
| `subagent_server/` | `tests/test_helpers.py` | `@pytest.mark.unit` |
| `subagent_server/` | `tests/test_task_engine_integration.py` | `@pytest.mark.api` |
| `mcp_tools/` | `tests/test_team_tools.py` | `@pytest.mark.integration` |
| Cross-module | `orchestration/tests/test_team_lifecycle.py` | (imports `create_server`, `mcp_tools.team_tools`) |
| Cross-module | `tests/cli/test_team_cli.py` | (imports `mcp_tools.team_tools` private helpers) |

### 5. External References

| Location | Reference |
|---|---|
| `.vaultspec/rules/rules/vaultspec-subagents.builtin.md` | Mentions `vaultspec-mcp` MCP server configured in `.mcp.json` |
| `.vaultspec/docs/concepts.md` | Documents `vaultspec-mcp` server and its 5 subagent tools |
| `.vaultspec/docs/cli-reference.md` | Documents `serve` subcommand for MCP server, references `mcp.json` |
| `.claude/rules/vaultspec-subagents.builtin.md` | Loaded into session, references `vaultspec-mcp` |
| `.vault/adr/2026-02-21-packaging-restructure-adr.md` | Describes `subagent_server` as top of dependency graph |
| `.vault/adr/2026-02-20-team-mcp-integration-p1-adr.md` | Documents tool registration pattern from `subagent_server` |
| `.vault/plan/2026-02-21-module-exports-plan.md` | Details import restructuring for both packages |
| `.vault/research/2026-02-22-cli-ecosystem-factoring-research.md` | References `subagent_server.server.main` |

### 6. Responsibility Split Analysis

**`server.py` owns:**
- `FastMCP` instance creation and naming
- Lifespan composition
- Tool module registration calls
- Config resolution for `root_dir` and passing it to both modules
- The `vaultspec-mcp` console script entry point
- Windows event loop policy

**`subagent_server/server.py` owns:**
- All MCP infrastructure: `initialize_server()`, `register_tools()`,
  `subagent_lifespan()`
- Module-level mutable globals: `ROOT_DIR`, `CONTENT_ROOT`, `AGENTS_DIR`,
  `lock_manager`, `task_engine`, `_agent_cache`, `_background_tasks`,
  `_active_clients`, `_refresh_fn`, `_run_subagent_fn`, `_mcp_ref`
- Agent file parsing, polling, and dynamic resource registration
- 5 tool functions + private helpers
- Legacy standalone `main()`

**`mcp_tools/` owns:**
- `team_tools.py`: 10 team tool functions, session persistence, module-level
  `_root_dir` and `_team_task_engine` globals
- `vault_tools.py`: Future vault audit/management tools (stub)
- `framework_tools.py`: Future framework CLI tools (stub)

**Shared state concerns:**
- `subagent_server` manages its own globals, initialized via
  `initialize_server()`.
- `mcp_tools.team_tools` manages its own globals, initialized via
  `set_root_dir()`.
- `server.py` calls both initialization functions, acting as the composition
  root.
- The two tool modules have no knowledge of each other.

**Naming problems:**
- `subagent_server/` is misleading: it is not just about subagents. It contains
  the core MCP infrastructure (`initialize_server`, `register_tools`,
  `subagent_lifespan`, `TaskEngine`, `LockManager` wiring, agent file polling,
  dynamic resource registration). These are general MCP server concerns.
- `server.py` at the package root does not indicate it is MCP-specific. It
  could be confused with the A2A server (`protocol/a2a/server.py`).
- `mcp_tools/` is a peer package that registers tools onto the same `FastMCP`
  instance but has no connection to the "core" MCP infrastructure in
  `subagent_server/`.

### 7. Consolidation Options

#### Option A: Rename `server.py` to `mcp_server.py` (minimal)

**Changes:**
- Rename `src/vaultspec/server.py` -> `src/vaultspec/mcp_server.py`
- Update `pyproject.toml`: `vaultspec-mcp = "vaultspec.mcp_server:main"`
- Update `__main__.py`: `from .mcp_server import main as run`
- Update 2 test files that import `create_server` from `...server`

**Blast radius:** 4 files changed (source) + 2 test files + `pyproject.toml` +
documentation references.

**Pros:**
- Minimal disruption, quick to execute.
- Disambiguates the MCP entry point from `protocol/a2a/server.py`.

**Cons:**
- Does NOT fix the `subagent_server/` misnaming.
- Does NOT consolidate the fragmented structure.
- The naming confusion between `mcp_server.py`, `subagent_server/`, and
  `mcp_tools/` persists.

#### Option B: Move `server.py` into `mcp_tools/server.py`

**Changes:**
- Move `src/vaultspec/server.py` -> `src/vaultspec/mcp_tools/server.py`
- Update `pyproject.toml`: `vaultspec-mcp = "vaultspec.mcp_tools.server:main"`
- Update `__main__.py`: `from .mcp_tools.server import main as run`
- Update `mcp_tools/__init__.py` to re-export `create_server`, `main`
- Update 2 test files

**Blast radius:** 5 files changed + 2 test files + `pyproject.toml` +
documentation.

**Pros:**
- Groups the entry point with its tool registration modules.
- `mcp_tools/` becomes a more self-contained package.

**Cons:**
- `subagent_server/` remains separately named and disjointed.
- `mcp_tools/server.py` would import from `subagent_server/`, making the
  dependency direction confusing (why does `mcp_tools` depend on
  `subagent_server`?).
- Name `mcp_tools` becomes inaccurate when it also contains the server entry
  point.

#### Option C: Create new `mcp/` package, consolidate all three

**Changes:**
- Create `src/vaultspec/mcp/` package.
- Move `server.py` -> `mcp/__init__.py` or `mcp/server.py`.
- Move `subagent_server/server.py` -> `mcp/subagent_tools.py` (tool functions
  + infrastructure).
- Move `mcp_tools/team_tools.py` -> `mcp/team_tools.py`.
- Move stubs: `mcp_tools/vault_tools.py` -> `mcp/vault_tools.py`,
  `mcp_tools/framework_tools.py` -> `mcp/framework_tools.py`.
- Delete `subagent_server/` and `mcp_tools/` packages.
- Add backward-compatibility shims or update all imports.
- Update `pyproject.toml`: `vaultspec-mcp = "vaultspec.mcp.server:main"`.
- Update all test files, fixtures, documentation.

**Blast radius:** ~25+ files changed. Full rewrite of import chains.

**Pros:**
- Single coherent package for all MCP concerns.
- Clear naming: `vaultspec.mcp` is the MCP package.
- Eliminates the confusing `subagent_server` name entirely.
- Clean separation: `mcp/server.py` (entry point + composition),
  `mcp/subagent_tools.py` (5 subagent tools + infrastructure),
  `mcp/team_tools.py` (10 team tools), `mcp/vault_tools.py` (stubs),
  `mcp/framework_tools.py` (stubs).

**Cons:**
- Largest migration, most breakage potential.
- `mcp/` as a package name conflicts with the third-party `mcp` PyPI package
  (`from mcp.server.fastmcp import FastMCP`). Python will resolve
  `import mcp` to `vaultspec.mcp` when running from within the `vaultspec`
  package ONLY if relative imports are used, but any absolute `import mcp`
  would be ambiguous. This is a CRITICAL naming hazard. The third-party
  package is imported as `from mcp.server.fastmcp import FastMCP` in at
  least 5 source files. Using `mcp/` as a subpackage name would shadow
  the third-party dependency.
- Consolidating `subagent_server/server.py` (961 lines) with the entry point
  creates a very large file unless further decomposed.
- Test file restructuring is extensive.

**CRITICAL RISK: Name shadowing.** The `mcp` name is already taken by the
`mcp` PyPI package (version >=1.20.0 in `pyproject.toml`). Creating
`vaultspec.mcp` would not shadow the top-level `mcp` package in normal
circumstances (since `vaultspec.mcp` is accessed as `vaultspec.mcp`, not
bare `mcp`). However, within any module inside `src/vaultspec/mcp/`, a bare
`import mcp` or `from mcp import ...` would resolve to `vaultspec.mcp`
(the local package) rather than the third-party `mcp` package. This would
break every file that imports from `mcp.server.fastmcp`. The fix would
require either:
  - Renaming the package to something other than `mcp/` (e.g., `mcp_server/`).
  - Using `from __future__ import annotations` plus fully-qualified absolute
    imports with `importlib` tricks to force resolution to the external
    package. This is fragile and non-idiomatic.

#### Option D: Merge `subagent_server/` into `mcp_tools/`, rename to `mcp_server/`

**Changes:**
- Create `src/vaultspec/mcp_server/` package.
- Move `server.py` -> `mcp_server/app.py` (entry point + composition).
- Move `subagent_server/server.py` -> `mcp_server/subagent_tools.py`.
- Move `mcp_tools/team_tools.py` -> `mcp_server/team_tools.py`.
- Move stubs: `mcp_tools/vault_tools.py` -> `mcp_server/vault_tools.py`,
  `mcp_tools/framework_tools.py` -> `mcp_server/framework_tools.py`.
- Delete `subagent_server/` and `mcp_tools/` packages.
- Create `mcp_server/__init__.py` re-exporting public symbols.
- Update `pyproject.toml`: `vaultspec-mcp = "vaultspec.mcp_server.app:main"`.
- Update `__main__.py`, `subagent_cli.py`, all test files, documentation.
- Merge test directories: `mcp_server/tests/`.

**Blast radius:** ~20+ files changed. Similar to Option C but avoids the
name-shadowing hazard.

**Pros:**
- Single coherent package for all MCP concerns.
- `mcp_server/` is unambiguous -- it is the MCP server package.
- No name collision with the third-party `mcp` package.
- Internal file naming is descriptive: `app.py` (FastMCP creation),
  `subagent_tools.py` (dispatch/task tools), `team_tools.py` (team tools).
- Eliminates both naming problems (`subagent_server` misnomer and generic
  `server.py`).

**Cons:**
- Still a significant migration (similar scope to Option C).
- Backward-compatibility shims needed for external consumers (if any).
- `subagent_cli.py` references `subagent_server.server.main` which would
  become `mcp_server.subagent_tools.main` (or the legacy entry point could
  be dropped).

### 8. Evaluation Summary

| Criterion | A (rename) | B (move into mcp_tools) | C (new mcp/) | D (merge into mcp_server/) |
|---|---|---|---|---|
| Naming clarity | Partial | Partial | Best (but shadowed) | Best |
| Blast radius | ~7 files | ~8 files | ~25+ files | ~20+ files |
| Name-shadow risk | None | None | **CRITICAL** | None |
| Eliminates `subagent_server` misnomer | No | No | Yes | Yes |
| Single package for all MCP | No | No | Yes | Yes |
| Migration complexity | Trivial | Low | High | High |
| Backward compat risk | Low | Low | High | Medium-High |
| Future extensibility | Poor | Medium | Good | Good |

### 9. Recommendation

**Option D (`mcp_server/`)** is the recommended approach if the goal is a clean,
consolidated architecture. It resolves both naming problems, avoids the critical
`mcp` name-shadowing hazard of Option C, and produces a coherent single
package.

**Option A (rename `server.py`)** is the recommended approach if the goal is a
quick, low-risk improvement. It is the only option that can be executed in a
single commit with near-zero breakage risk.

A phased approach may be appropriate:

- **Phase 1:** Execute Option A (rename `server.py` to `mcp_server.py`). This
  is immediately beneficial and low-risk.
- **Phase 2:** Execute Option D (full consolidation into `mcp_server/`). This
  subsumes Phase 1 and should be planned as a dedicated refactoring effort
  with its own ADR, plan, and execution tracking.

The legacy standalone `main()` in `subagent_server/server.py` should be
removed regardless of which option is chosen. It duplicates functionality
from the unified entry point and is marked deprecated in its docstring.

### 10. Files That Would Need Changes (Option D)

For planning purposes, the following is the complete list of files that import
from any of the three modules:

**Source files:**
- `src/vaultspec/server.py` (becomes `mcp_server/app.py`)
- `src/vaultspec/__main__.py`
- `src/vaultspec/subagent_cli.py`
- `src/vaultspec/subagent_server/__init__.py` (deleted)
- `src/vaultspec/subagent_server/server.py` (becomes `mcp_server/subagent_tools.py`)
- `src/vaultspec/mcp_tools/__init__.py` (deleted)
- `src/vaultspec/mcp_tools/team_tools.py` (becomes `mcp_server/team_tools.py`)
- `src/vaultspec/mcp_tools/vault_tools.py` (becomes `mcp_server/vault_tools.py`)
- `src/vaultspec/mcp_tools/framework_tools.py` (becomes `mcp_server/framework_tools.py`)

**Test files:**
- `src/vaultspec/subagent_server/tests/test_mcp_tools.py`
- `src/vaultspec/subagent_server/tests/test_mcp_protocol.py`
- `src/vaultspec/subagent_server/tests/test_helpers.py`
- `src/vaultspec/subagent_server/tests/test_task_engine_integration.py`
- `src/vaultspec/subagent_server/tests/conftest.py`
- `src/vaultspec/mcp_tools/tests/test_team_tools.py`
- `src/vaultspec/orchestration/tests/test_team_lifecycle.py`
- `src/vaultspec/tests/cli/test_team_cli.py`

**Configuration:**
- `pyproject.toml` (`[project.scripts]` entry)

**Documentation:**
- `.vaultspec/docs/cli-reference.md`
- `.vaultspec/docs/concepts.md`
- `.vaultspec/rules/rules/vaultspec-subagents.builtin.md`
- `.claude/rules/vaultspec-subagents.builtin.md`
