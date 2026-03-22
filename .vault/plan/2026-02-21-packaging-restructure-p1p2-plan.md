---
tags:
  - '#plan'
  - '#packaging-restructure'
date: '2026-02-21'
related:
  - '[[2026-02-21-packaging-restructure-adr]]'
  - '[[2026-02-21-packaging-restructure-research]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `packaging-restructure` `p1+p2` plan

Migrate the Python codebase from `.vaultspec/lib/` to a proper `src/vaultspec/` namespace package, adopt `uv` + `hatchling` as the build toolchain, rewrite all 149 bare-name imports to `vaultspec.*` prefixed forms, eliminate `_paths.py`, and scaffold a unified `vaultspec-mcp` server that replaces the current `vs-subagent-mcp`.

## Proposed Changes

The current Python source lives inside a dotfile directory (`.vaultspec/lib/src/`) with 11 bare-name packages (`core`, `orchestration`, `protocol`, `rag`, `vaultcore`, etc.) that collide in `site-packages`. Four CLI scripts bootstrap through a `sys.path` hack in `_paths.py`. No `[project.scripts]` entry points exist. The MCP server is launched via a raw script path in `mcp.json`. None of this is installable or deployable.

Per \[[2026-02-21-packaging-restructure-adr]\], the fix is:

- **Move** all library packages from `.vaultspec/lib/src/` to `src/vaultspec/`, giving every module a `vaultspec.*` namespace.
- **Move** CLI scripts from `.vaultspec/lib/scripts/` into the package as proper modules (`vaultspec.cli`, `vaultspec.vault_cli`, `vaultspec.team_cli`, `vaultspec.subagent_cli`).
- **Rewrite** all 149 bare-name imports (38 production, 78 test, 21 script, 12 conftest) to `vaultspec.*` prefixed forms. The import graph documented in \[[2026-02-21-packaging-restructure-research]\] confirms no circular dependencies.
- **Delete** `_paths.py` entirely. Workspace resolution already lives in `vaultspec.core.workspace`.
- **Switch** the build backend from `setuptools` to `hatchling`, add `[project.scripts]` entry points, and update `pyproject.toml` test/lint configuration.
- **Update** `mcp.json` to use `uv run vaultspec-mcp` instead of the raw script path.
- **Scaffold** a unified `vaultspec-mcp` server (`src/vaultspec/server.py`) that aggregates the existing 5 subagent tools and establishes a modular router pattern for future tool expansion (Phases 3-5 per the ADR).

## Tasks

### Phase 1: Package layout + `uv`

#### Stream A -- File moves (sequential, must complete first)

1. **Create `src/vaultspec/` directory structure**

   - Create `src/vaultspec/` and all sub-package directories mirroring the current layout under `.vaultspec/lib/src/`
   - Affected paths: `src/vaultspec/core/`, `src/vaultspec/orchestration/`, `src/vaultspec/protocol/`, `src/vaultspec/rag/`, `src/vaultspec/vaultcore/`, `src/vaultspec/subagent_server/`, `src/vaultspec/graph/`, `src/vaultspec/metrics/`, `src/vaultspec/verification/`, `src/vaultspec/hooks/`
   - Work stream: A (file moves)
   - Dependencies: none
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step01.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-adr]\], \[[2026-02-21-packaging-restructure-research]\]

1. **Move all library packages from `.vaultspec/lib/src/` to `src/vaultspec/`**

   - Move `core/`, `orchestration/`, `protocol/`, `rag/`, `vaultcore/`, `subagent_server/`, `graph/`, `metrics/`, `verification/`, `hooks/`, and standalone `logging_config.py` into `src/vaultspec/`
   - Remove all `__pycache__` directories and `.egg-info` artifacts from the moved tree
   - Affected paths: `.vaultspec/lib/src/*` -> `src/vaultspec/*`
   - Work stream: A (file moves)
   - Dependencies: step 1
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step02.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] section 1.2

1. **Move CLI scripts as proper modules**

   - Move `.vaultspec/lib/scripts/cli.py` to `src/vaultspec/cli.py`
   - Move `.vaultspec/lib/scripts/vault.py` to `src/vaultspec/vault_cli.py`
   - Move `.vaultspec/lib/scripts/team.py` to `src/vaultspec/team_cli.py`
   - Move `.vaultspec/lib/scripts/subagent.py` to `src/vaultspec/subagent_cli.py`
   - Delete `.vaultspec/lib/scripts/_paths.py` entirely
   - Remove all `_paths` imports and `sys.path` hacks from moved CLI modules
   - Affected paths: `.vaultspec/lib/scripts/*.py` -> `src/vaultspec/*_cli.py`
   - Work stream: A (file moves)
   - Dependencies: step 2
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step03.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] sections 1.4, 4.1

1. **Move test directories to top-level and adjust structure**

   - Move `.vaultspec/lib/tests/` to top-level `tests/`
   - Move `.vaultspec/lib/conftest.py` to top-level `conftest.py`
   - In-package tests (`src/vaultspec/*/tests/`) remain with their parent packages (they moved in step 2)
   - Update `tests/constants.py` path derivation -- the `Path(__file__).resolve().parent.parent.parent.parent` traversal semantics change from `tests/ -> lib/ -> .vaultspec/ -> repo` to `tests/ -> repo` (only 1 level up), or replace with package-metadata-based resolution
   - Affected paths: `.vaultspec/lib/tests/` -> `tests/`, `.vaultspec/lib/conftest.py` -> `conftest.py`
   - Work stream: A (file moves)
   - Dependencies: step 2
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step04.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] sections 5.1-5.4

#### Stream B -- Import rewrite (depends on Stream A, parallelizable across sub-agents)

1. **Rewrite imports in leaf packages: `src/vaultspec/core/` and `src/vaultspec/vaultcore/`**

   - Replace all bare-name imports (`from core.`, `from vaultcore.`, `from logging_config`) with `vaultspec.*` prefixed forms
   - These are leaf packages with no internal cross-dependencies, so they can be rewritten first
   - Affected files: all `.py` files in `src/vaultspec/core/` and `src/vaultspec/vaultcore/` (production code only, not tests)
   - Work stream: B (import rewrite)
   - Dependencies: steps 1-4
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step05.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] section 1.3

1. **Rewrite imports in mid-tier packages: `src/vaultspec/orchestration/`, `src/vaultspec/protocol/`, `src/vaultspec/hooks/`**

   - Replace all bare-name imports with `vaultspec.*` prefixed forms
   - These packages depend on `core` and `vaultcore`, which are rewritten in step 5
   - Affected files: all `.py` files in `src/vaultspec/orchestration/`, `src/vaultspec/protocol/` (including `acp/` and `a2a/` sub-packages), and `src/vaultspec/hooks/`
   - Work stream: B (import rewrite)
   - Dependencies: steps 1-4
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step06.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] section 1.3

1. **Rewrite imports in analytics/RAG packages: `src/vaultspec/graph/`, `src/vaultspec/metrics/`, `src/vaultspec/verification/`, `src/vaultspec/rag/`**

   - Replace all bare-name imports with `vaultspec.*` prefixed forms
   - These packages primarily depend on `vaultcore` (rewritten in step 5)
   - Affected files: all `.py` files in the four packages
   - Work stream: B (import rewrite)
   - Dependencies: steps 1-4
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step07.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] section 1.3

1. **Rewrite imports in server and CLI modules**

   - Replace all bare-name imports in `src/vaultspec/subagent_server/` (the top of the dependency graph)
   - Replace all bare-name imports in `src/vaultspec/cli.py`, `src/vaultspec/vault_cli.py`, `src/vaultspec/team_cli.py`, `src/vaultspec/subagent_cli.py`
   - Remove all `_paths` imports and `ROOT_DIR` references; replace with `vaultspec.core.workspace.resolve_workspace()` calls or equivalent
   - Affected files: `src/vaultspec/subagent_server/*.py`, `src/vaultspec/cli.py`, `src/vaultspec/vault_cli.py`, `src/vaultspec/team_cli.py`, `src/vaultspec/subagent_cli.py`
   - Work stream: B (import rewrite)
   - Dependencies: steps 1-4
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step08.md`
   - Executing sub-agent: vaultspec-complex-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] sections 1.4, 4.1

1. **Rewrite imports in all test files and conftest files**

   - Replace all bare-name imports in `tests/` (top-level integration tests) and `src/vaultspec/*/tests/` (in-package unit tests)
   - Update all `conftest.py` files (12 total) to use `vaultspec.*` imports
   - Replace `import cli` (6 occurrences in `tests/cli/`) with `import vaultspec.cli` or equivalent
   - Replace `from tests.constants import ...` (3 occurrences) with updated import path
   - Affected files: all 66 test files plus 12 conftest.py files
   - Work stream: B (import rewrite)
   - Dependencies: steps 1-4
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step09.md`
   - Executing sub-agent: vaultspec-complex-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] sections 5.2-5.4

#### Stream C -- Packaging config (independent of Stream B, depends on Stream A)

1. **Update `pyproject.toml` for hatchling + uv**
   - Switch `[build-system]` from `setuptools` to `hatchling`

- Add `[tool.hatch.build.targets.wheel] packages = ["src/vaultspec"]`
- Add `[project.scripts]` entry points: `vaultspec = "vaultspec.cli:main"`, `vaultspec-mcp = "vaultspec.server:main"`, `vaultspec-vault = "vaultspec.vault_cli:main"`, `vaultspec-team = "vaultspec.team_cli:main"`, `vaultspec-subagent = "vaultspec.subagent_cli:main"`
- Update `[tool.pytest.ini_options]`: remove `pythonpath` entirely, change `testpaths` to `["tests", "src"]`
- Update `[tool.ruff.lint.isort] known-first-party` to `["vaultspec"]`
- Remove `[tool.setuptools.packages.find]` section entirely
- Update `[tool.ty.environment] root` to remove old paths
- Affected files: `pyproject.toml`
- Work stream: C (packaging config)
- Dependencies: steps 1-4
- Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step10.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-21-packaging-restructure-adr]\] Phase 1, \[[2026-02-21-packaging-restructure-research]\] sections 6.1-6.4

1. **Add root package `__init__.py` and `__main__.py`**

   - Create `src/vaultspec/__init__.py` as root package init (version metadata, minimal public API surface)
   - Create `src/vaultspec/__main__.py` to enable `python -m vaultspec` (delegates to `vaultspec.cli:main`)
   - Affected files: `src/vaultspec/__init__.py`, `src/vaultspec/__main__.py`
   - Work stream: C (packaging config)
   - Dependencies: step 1
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step11.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-adr]\] Phase 1

1. **Fix `core/workspace.py` `_validate()` — remove `framework_root/lib/` check**

   - Remove lines 246-253 of `src/vaultspec/core/workspace.py` (the `lib_dir = layout.framework_root / "lib"` validation block)
   - After restructuring, Python code no longer lives under `framework_root/lib/`, so this check would always fail
   - Affected files: `src/vaultspec/core/workspace.py`
   - Work stream: C (packaging config)
   - Dependencies: step 2
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step12.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] section 4.2

1. **Update `mcp.json` to use `uv run vaultspec-mcp`**

   - Change the server entry from `vs-subagent-mcp` / raw `python` command to `vaultspec-mcp` / `uv run vaultspec-mcp`
   - Affected files: `mcp.json`
   - Work stream: C (packaging config)
   - Dependencies: step 10
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step13.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] sections 8.1-8.2

#### Stream D -- Verification (depends on ALL above)

1. **Run `uv sync --dev` to verify editable install**
   - Execute `uv sync --dev` and confirm it completes without errors

- Verify `import vaultspec` resolves correctly in the installed environment
- Affected files: none (verification only)
- Work stream: D (verification)
- Dependencies: steps 1-13
- Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step14.md`
- Executing sub-agent: vaultspec-code-reviewer
- References: \[[2026-02-21-packaging-restructure-adr]\]

1. **Run `uv run pytest` — all tests must pass**

   - Execute the full test suite and confirm all existing tests pass with namespaced imports
   - Affected files: none (verification only)
   - Work stream: D (verification)
   - Dependencies: step 14
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step15.md`
   - Executing sub-agent: vaultspec-code-reviewer
   - References: \[[2026-02-21-packaging-restructure-adr]\]

1. **Run `uv run python -m vaultspec --help` — CLI must work**

   - Verify the `__main__.py` entry point works and prints CLI help
   - Affected files: none (verification only)
   - Work stream: D (verification)
   - Dependencies: step 14
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step16.md`
   - Executing sub-agent: vaultspec-code-reviewer
   - References: \[[2026-02-21-packaging-restructure-adr]\]

1. **Smoke test `uv run vaultspec-mcp`**

   - Verify the MCP server starts via `[project.scripts]` entry point
   - Confirm the existing 5 tools (`list_agents`, `dispatch_agent`, `get_task_status`, `cancel_task`, `get_locks`) are registered
   - Affected files: none (verification only)
   - Work stream: D (verification)
   - Dependencies: step 14
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p1-step17.md`
   - Executing sub-agent: vaultspec-code-reviewer
   - References: \[[2026-02-21-packaging-restructure-research]\] section 3.3

### Phase 2: Unified MCP server scaffolding

1. **Create `src/vaultspec/server.py` — unified FastMCP entry point**
   - Create a new `server.py` module with a `FastMCP` instance named `vaultspec-mcp`

- Implement a lifespan handler that starts the existing agent-file polling background task
- Establish a modular tool registration pattern (e.g., `server.include_router(subagent_tools)`) so future phases can add tool modules without modifying the server core
- Define a `main()` function that serves as the `[project.scripts]` entry point
- Affected files: `src/vaultspec/server.py`
- Work stream: Phase 2
- Dependencies: Phase 1 complete (all 17 steps)
- Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p2-step18.md`
- Executing sub-agent: vaultspec-complex-executor
- References: \[[2026-02-21-packaging-restructure-adr]\] Phase 2, \[[2026-02-21-packaging-restructure-research]\] sections 3.1-3.5

1. **Refactor existing 5 tools from `subagent_server/server.py` into the unified server**

   - Extract the 5 existing tool functions and agent resource registration from `subagent_server/server.py` into a tool module that registers with the unified server
   - The `subagent_server` package becomes a tool module that exposes a registration function (not a standalone server)
   - Preserve all existing tool signatures, docstrings, and behavior exactly
   - Affected files: `src/vaultspec/subagent_server/server.py`, `src/vaultspec/server.py`
   - Work stream: Phase 2
   - Dependencies: step 18
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p2-step19.md`
   - Executing sub-agent: vaultspec-complex-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] section 3.2-3.4

1. **Add stub tool router modules for future phases**

   - Create `src/vaultspec/mcp_tools/` package with `__init__.py`
   - Create `src/vaultspec/mcp_tools/vault_tools.py` — empty router with TODO comments for Phase 3 vault/framework tools
   - Create `src/vaultspec/mcp_tools/team_tools.py` — empty router with TODO comments for Phase 4 team tools
   - Create `src/vaultspec/mcp_tools/framework_tools.py` — empty router with TODO comments for Phase 3 framework CLI tools
   - Affected files: `src/vaultspec/mcp_tools/__init__.py`, `src/vaultspec/mcp_tools/vault_tools.py`, `src/vaultspec/mcp_tools/team_tools.py`, `src/vaultspec/mcp_tools/framework_tools.py`
   - Work stream: Phase 2
   - Dependencies: step 18
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p2-step20.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-adr]\] Phases 3-5

1. **Update all references from `vs-subagent-mcp` to `vaultspec-mcp`**

   - Rename the MCP server name in `mcp.json` (already partly done in step 13, verify consistency)
   - Update server name string in `src/vaultspec/server.py` and any remaining references in `src/vaultspec/subagent_server/server.py`
   - Search entire codebase for `vs-subagent-mcp` and replace with `vaultspec-mcp`
   - Affected files: `mcp.json`, `src/vaultspec/server.py`, `src/vaultspec/subagent_server/server.py`, any documentation or config files referencing the old name
   - Work stream: Phase 2
   - Dependencies: steps 18-19
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p2-step21.md`
   - Executing sub-agent: vaultspec-standard-executor
   - References: \[[2026-02-21-packaging-restructure-research]\] section 8.2

1. **Verify unified MCP server**

   - Run `uv run vaultspec-mcp` and confirm startup
   - Verify all 5 existing tools respond correctly (`list_agents`, `dispatch_agent`, `get_task_status`, `cancel_task`, `get_locks`)
   - Verify dynamic agent resources are still registered and polled
   - Affected files: none (verification only)
   - Work stream: Phase 2
   - Dependencies: steps 18-21
   - Step summary: `.vault/exec/2026-02-21-packaging-restructure/2026-02-21-packaging-restructure-p2-step22.md`
   - Executing sub-agent: vaultspec-code-reviewer
   - References: \[[2026-02-21-packaging-restructure-research]\] section 3.3

## Parallelization

Execution is organized into 5 waves that balance parallelism against dependency constraints.

```
Wave 1 (sequential): Stream A — steps 1-4 (file moves, one agent)
  All file moves must complete atomically before any import rewriting begins.
  A single agent avoids race conditions on directory creation and git operations.

Wave 2 (parallel, 3 agents):

  - Agent 1: Stream B steps 5-6 (leaf + mid-tier import rewrites)
    Covers core/, vaultcore/, orchestration/, protocol/, hooks/

  - Agent 2: Stream B steps 7-8 (analytics/RAG/server/CLI import rewrites)
    Covers graph/, metrics/, verification/, rag/, subagent_server/, CLI modules

  - Agent 3: Stream C steps 10-13 (packaging config)
    Covers pyproject.toml, __init__.py, __main__.py, workspace.py fix, mcp.json

Wave 3 (sequential, 1 agent):

  - Agent 4: Stream B step 9 (test import rewrites)
    Depends on Wave 2 completing so production imports are stable references.
    Covers all 66 test files and 12 conftest.py files.

Wave 4 (sequential, 1 agent):

  - Agent 5: Stream D — steps 14-17 (verification)
    Runs uv sync, pytest, CLI smoke test, MCP smoke test.
    Must run after all code changes are complete.

Wave 5 (sequential, 1 agent):

  - Agent 6: Phase 2 — steps 18-22 (unified MCP server scaffolding)
    Creates server.py, refactors subagent tools, adds stub routers, verifies.
    Depends on Phase 1 being fully verified.
```

## Verification

Success criteria (all must pass for the plan to be considered complete):

- **`uv sync --dev`** completes without errors and produces a working editable install where `import vaultspec` resolves correctly
- **`uv run pytest`** passes all existing tests with namespaced `vaultspec.*` imports (zero regressions against current test suite)
- **`uv run python -m vaultspec --help`** prints CLI help text (verifies `__main__.py` and entry point wiring)
- **`uv run vaultspec-mcp`** starts the unified MCP server and the existing 5 tools (`list_agents`, `dispatch_agent`, `get_task_status`, `cancel_task`, `get_locks`) respond to requests
- **No bare-name imports remain** — `grep -r "from core\.\|from orchestration\.\|from protocol\.\|from rag\.\|from vaultcore\.\|from subagent_server\.\|from graph\.\|from metrics\.\|from verification\.\|from hooks\.\|from logging_config" src/ tests/` returns zero results
- **`_paths.py` is deleted** — the file no longer exists anywhere in the repository
- **`.vaultspec/lib/src/` and `.vaultspec/lib/scripts/` are empty or removed** — all Python source code lives under `src/vaultspec/`
- **`mcp.json`** references `vaultspec-mcp` (not `vs-subagent-mcp`) and uses `uv run` (not raw `python` with script path)
- **`pyproject.toml`** uses `hatchling` build backend, has no `pythonpath` hack, and contains `[project.scripts]` entry points

Verification methodology beyond automated tests: the import rewrite is mechanical but a single missed import causes a runtime `ImportError`. The grep-based bare-import scan is the safety net. Additionally, the MCP server smoke test exercises the full initialization path (lifespan, config loading, tool registration, resource polling), which is the highest-risk integration surface.
