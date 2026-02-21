---
tags:
  - "#adr"
  - "#packaging-restructure"
date: "2026-02-21"
related:
  - "[[2026-02-21-packaging-restructure-research]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `packaging-restructure` adr: `src/vaultspec namespace + uv + unified MCP` | (**status:** `accepted`)

## Problem Statement

The Python codebase lives under `.vaultspec/lib/` -- a dotfile directory. Bare top-level package names (`core`, `orchestration`, `protocol`, `rag`, `vaultcore`, etc.) collide in site-packages with any other project that happens to ship a `core` or `protocol` package. All four CLI scripts bootstrap through `_paths.py`, which performs `sys.path.insert(0, ...)` surgery to make these bare imports work. No proper `[project.scripts]` entry points exist -- the MCP server is launched via raw script path in `mcp.json`. `python -m vaultspec` does not work. The project cannot be cleanly installed, deployed, or consumed as a library.

## Considerations

- **`uv` as package manager**: Fast dependency resolution, PEP 621 native, first-class editable installs via `uv sync --dev`. The current `pyproject.toml` already uses PEP 621 metadata (`[project]` table, `[project.optional-dependencies]`), so adoption is low-friction.
- **`src/vaultspec/` layout**: The Python community consensus for installable packages. Prevents import shadowing (the running directory cannot accidentally shadow the installed package). All 11 bare-name packages become `vaultspec.core`, `vaultspec.orchestration`, `vaultspec.protocol`, etc.
- **Single unified MCP server**: Replace the current `vs-subagent-mcp` (5 tools only) with `vaultspec-mcp` that aggregates subagent, vault, team, and framework tools behind a modular router pattern. This consolidates the MCP surface into one process with one lifespan.
- **`hatchling` vs `setuptools`**: Both work with `uv`. `hatchling` is `uv`'s default and the more idiomatic choice for modern PEP 621 projects. `setuptools` is already configured but requires the `[tool.setuptools.packages.find]` indirection. Decision: switch to `hatchling` for cleaner `[tool.hatch.build.targets.wheel]` configuration.
- **Phased rollout**: The research identified ~149 import rewrites, 66 test files, and significant MCP tool expansion (~30 new tools). A phased approach contains risk by separating the mechanical packaging work (Phase 1) from the MCP tool expansion (Phases 2-5).

## Constraints

- **149 bare-name imports** across production code (38), test code (78), scripts (21), and conftest files (12) must be rewritten mechanically to `vaultspec.*` prefixed forms.
- **66 test files** are affected by the namespace change.
- **`.vaultspec/` must remain** as the framework configuration directory (rules, templates, agents, skills). It does not move -- only the Python source code under `.vaultspec/lib/src/` relocates to `src/vaultspec/`.
- **`core/workspace.py`** contains a `_validate()` check (line 246-253) that asserts `framework_root/lib/` exists as a directory. After restructuring, Python code no longer lives there, so this validation must be updated or removed.
- **MCP tool expansion** (~30 new tools from `cli.py`, `vault.py`, and `team.py`) and **RAG GPU/long-running patterns** are explicitly OUT OF SCOPE for this ADR. They are deferred to future phases to avoid conflating packaging concerns with API design concerns.

## Implementation

Implementation proceeds in phases. This ADR's core scope is **Phase 1** (package layout + `uv`) and **Phase 2** (unified MCP scaffolding). Phases 3-5 are scoped here for sequencing clarity but deferred to future ADRs for detailed design.

### Phase 1: Package layout + `uv`

This phase is entirely mechanical. The research in [[2026-02-21-packaging-restructure-research]] confirmed no circular dependencies in the import graph and that `vaultcore` is the most-depended-on leaf package -- a safe foundation to migrate first.

- Move `.vaultspec/lib/src/*` to `src/vaultspec/*`. All packages become `vaultspec.core`, `vaultspec.orchestration`, `vaultspec.protocol`, `vaultspec.vaultcore`, `vaultspec.rag`, `vaultspec.subagent_server`, `vaultspec.graph`, `vaultspec.metrics`, `vaultspec.verification`, `vaultspec.hooks`. The standalone `logging_config.py` becomes `vaultspec.logging_config`.
- Move `.vaultspec/lib/scripts/` entry points into `src/vaultspec/` as proper modules: `cli.py` becomes `vaultspec.cli`, `vault.py` becomes `vaultspec.vault_cli`, `team.py` becomes `vaultspec.team_cli`, `subagent.py` becomes `vaultspec.subagent_cli`.
- Rewrite all 149 bare-name imports to `vaultspec.*` namespace. This is a mechanical find-and-replace: `from core.workspace import ...` becomes `from vaultspec.core.workspace import ...`, etc.
- Delete `_paths.py` entirely. Workspace resolution already lives in `vaultspec.core.workspace`; scripts no longer need bootstrap path surgery.
- Update `core/workspace.py` `_validate()` to remove the `framework_root/lib/` existence check. The `framework_root` continues to point at `.vaultspec/` for config resolution, but it no longer contains Python source.
- Update `pyproject.toml`:
  - Build backend: switch from `setuptools` to `hatchling`.
  - Package discovery: `[tool.hatch.build.targets.wheel] packages = ["src/vaultspec"]`.
  - Entry points: add `[project.scripts]`.
  - Test config: replace `pythonpath` hack with standard installed-package imports; update `testpaths` to `["tests", "src"]`.
- Add `src/vaultspec/__main__.py` to enable `python -m vaultspec`.
- Add `[project.scripts]` entry points:
  - `vaultspec = "vaultspec.cli:main"`
  - `vaultspec-mcp = "vaultspec.server:main"`
  - `vaultspec-vault = "vaultspec.vault_cli:main"`
  - `vaultspec-team = "vaultspec.team_cli:main"`
  - `vaultspec-subagent = "vaultspec.subagent_cli:main"`
- Update `.mcp.json` to use `uv run vaultspec-mcp` instead of the raw script path.
- Update all 12 `conftest.py` files and `tests/constants.py` to use namespaced imports. The `tests/constants.py` path derivation (4 levels of `parent`) may need adjustment or replacement with package-metadata-based resolution.
- Verify `uv sync --dev` produces a working editable install where `import vaultspec` resolves correctly.

### Phase 2: Unified MCP server scaffolding

- Create `src/vaultspec/server.py` as the unified `vaultspec-mcp` entry point. This module instantiates a single `FastMCP` instance and aggregates tool routers.
- Migrate the existing 5 subagent tools (`list_agents`, `dispatch_agent`, `get_task_status`, `cancel_task`, `get_locks`) and dynamic agent resources from `subagent_server/server.py` into the unified server.
- Establish a modular tool registration pattern (e.g., `server.include_router(subagent_tools)`) so that future phases can add vault, team, and framework tool modules without modifying the server core.
- Rename the MCP server from `vs-subagent-mcp` to `vaultspec-mcp` in all configuration.

### Phase 3 (future): Vault + Framework CLI tools as MCP tools

~23 new tools derived from `cli.py` and `vault.py` commands. Excludes interactive-only commands (`edit`, `test`). Requires its own ADR for API surface design.

### Phase 4 (future): Team CLI tools as MCP tools

~7 new tools derived from `team.py`. These involve A2A async network operations that need careful error handling and timeout design. Requires its own ADR.

### Phase 5 (future): RAG tools as MCP tools

~4 new tools (`index_vault`, `search_vault`, etc.). These require GPU access and have long-running operation patterns similar to `dispatch_agent`'s background task model. Requires its own ADR.

## Rationale

The research findings in [[2026-02-21-packaging-restructure-research]] provide strong evidence that this migration is safe and mechanical:

- **No circular dependencies** -- the import graph is a clean DAG with `vaultcore` at the bottom, `core` as a leaf, and `orchestration`/`subagent_server` at the top. Migration order is unambiguous.
- **All CLI scripts are production-grade** -- no stubs, no dead code, no throwaway prototypes. Every script handler maps to a real feature. Nothing needs to be discarded.
- **No legacy packaging artifacts** -- no `requirements.txt`, `setup.cfg`, or `setup.py` exist. The starting point is clean PEP 621 metadata.
- **Standard src-layout is community consensus** -- the `src/` directory layout prevents the common pitfall where running tests against the source tree accidentally imports the local directory instead of the installed package.
- **`uv` is the modern standard** -- PEP 621 native, fast resolution, first-class editable installs. The current `pyproject.toml` is already 90% compatible.
- **`_paths.py` is the single point of fragility** -- eliminating it in favor of proper package installation removes a class of "works on my machine" bugs entirely.

## Consequences

**Positive**:
- `python -m vaultspec` works out of the box.
- `uv run vaultspec-mcp` replaces the raw script path in `mcp.json`.
- No `sys.path` hacks anywhere -- `_paths.py` is deleted entirely.
- Proper `vaultspec.*` namespace prevents site-packages collisions.
- The project becomes cleanly `pip install`-able and `uv sync`-able.
- `.vaultspec/` becomes a pure configuration directory -- cleaner separation of concerns.
- Entry points (`[project.scripts]`) are the standard mechanism for console scripts.

**Negative**:
- 149 import rewrites are mechanical but tedious and touch nearly every file. A single missed rewrite causes an `ImportError` at runtime.
- All developers must switch to `uv sync --dev` for local development. The `sys.path` hack no longer works as a fallback.
- `.vaultspec/lib/` loses its scripts directory and becomes config-only. Any tooling or documentation referencing `.vaultspec/lib/scripts/` must be updated.
- The `hatchling` build backend is a new dependency in the build chain, though it is well-maintained and widely adopted.

**Future work**:
- ~30 MCP tools to implement across Phases 3-5, each requiring its own API design ADR.
- RAG tools need background task patterns (GPU-bound, long-running) -- likely extending the existing `dispatch_agent` task model.
- Team tools need A2A async handling with proper timeout and error semantics.
- The unified MCP server's tool count (~35 at full build-out) may eventually warrant tool namespacing or grouping to avoid client-side tool sprawl.
