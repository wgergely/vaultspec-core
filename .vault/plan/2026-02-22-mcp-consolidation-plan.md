---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#plan"
  - "#mcp-consolidation"
date: "2026-02-22"
related:
  - "[[2026-02-22-mcp-consolidation-adr]]"
  - "[[2026-02-22-mcp-consolidation-research]]"
  - "[[2026-02-21-packaging-restructure-adr]]"
  - "[[2026-02-22-cli-ecosystem-factoring-adr]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `mcp-consolidation` plan

Consolidate `server.py`, `subagent_server/`, and `mcp_tools/` into a single
`mcp_server/` package per [[2026-02-22-mcp-consolidation-adr]] (Option D).

## Proposed Changes

Merge three scattered MCP modules into one coherent package. This is a
structural refactoring — no behavioral changes. The ADR specifies exact file
moves, import rewrites, and the target directory structure. The legacy
standalone `main()` in `subagent_server/server.py` is removed.

## Tasks

- Phase 1: scaffold and move source files
    1. Create `src/vaultspec/mcp_server/` directory with `__init__.py`
    2. Move `src/vaultspec/subagent_server/server.py` →
       `src/vaultspec/mcp_server/subagent_tools.py`
       - Remove the deprecated legacy `main()` function (lines 905-960)
       - Remove the `if __name__ == "__main__"` guard
       - Keep all other code unchanged
    3. Move `src/vaultspec/mcp_tools/team_tools.py` →
       `src/vaultspec/mcp_server/team_tools.py`
       - No content changes needed
    4. Move `src/vaultspec/mcp_tools/vault_tools.py` →
       `src/vaultspec/mcp_server/vault_tools.py`
    5. Move `src/vaultspec/mcp_tools/framework_tools.py` →
       `src/vaultspec/mcp_server/framework_tools.py`
    6. Move `src/vaultspec/server.py` →
       `src/vaultspec/mcp_server/app.py`
       - Update imports:
         `from .subagent_server import ...` → `from .subagent_tools import ...`
         `from .mcp_tools import ...` → `from .team_tools import ...`
         `from .mcp_tools.team_tools import ...` → `from .team_tools import ...`
    7. Write `src/vaultspec/mcp_server/__init__.py` with public re-exports
       (see ADR for exact symbols)

- Phase 2: move test files
    1. Create `src/vaultspec/mcp_server/tests/` with `__init__.py`
    2. Move `src/vaultspec/subagent_server/tests/conftest.py` →
       `src/vaultspec/mcp_server/tests/conftest.py`
    3. Move `src/vaultspec/subagent_server/tests/test_mcp_tools.py` →
       `src/vaultspec/mcp_server/tests/test_mcp_tools.py`
       - Update: `from .. import server as srv` → `from .. import subagent_tools as srv`
       - Update: `from .. import initialize_server` → `from ..subagent_tools import initialize_server`
       - Update all `from ..server import ...` → `from ..subagent_tools import ...`
    4. Move `src/vaultspec/subagent_server/tests/test_mcp_protocol.py` →
       `src/vaultspec/mcp_server/tests/test_mcp_protocol.py`
       - Update: `from .. import server as srv` → `from .. import subagent_tools as srv`
       - Update: `from ...server import create_server` → `from ..app import create_server`
    5. Move `src/vaultspec/subagent_server/tests/test_helpers.py` →
       `src/vaultspec/mcp_server/tests/test_helpers.py`
       - Update: `from ..server import ...` → `from ..subagent_tools import ...`
    6. Move `src/vaultspec/subagent_server/tests/test_task_engine_integration.py` →
       `src/vaultspec/mcp_server/tests/test_task_engine_integration.py`
    7. Move `src/vaultspec/mcp_tools/tests/test_team_tools.py` →
       `src/vaultspec/mcp_server/tests/test_team_tools.py`
       - Update any relative imports from `..team_tools` (already correct)

- Phase 3: update external references
    1. `src/vaultspec/__main__.py`:
       `from .server import main as run` → `from .mcp_server.app import main as run`
    2. `src/vaultspec/subagent_cli.py`:
       `from .subagent_server.server import main as server_main` →
       `from .mcp_server.app import main as server_main`
    3. `src/vaultspec/__init__.py`:
       Update any re-exports referencing `server` or `subagent_server`
    4. `src/vaultspec/orchestration/tests/test_team_lifecycle.py`:
       `from ...server import create_server` →
       `from ...mcp_server.app import create_server`
       `from ...mcp_tools.team_tools import ...` →
       `from ...mcp_server.team_tools import ...`
    5. `src/vaultspec/tests/cli/test_team_cli.py`:
       `from ...mcp_tools.team_tools import ...` →
       `from ...mcp_server.team_tools import ...`
    6. `pyproject.toml`:
       `vaultspec-mcp = "vaultspec.server:main"` →
       `vaultspec-mcp = "vaultspec.mcp_server.app:main"`

- Phase 4: update documentation
    1. `.vaultspec/docs/cli-reference.md` — update module path references
    2. `.vaultspec/docs/concepts.md` — update module path references
    3. `.claude/rules/vaultspec-subagents.builtin.md` — update references

- Phase 5: delete old packages
    1. Delete `src/vaultspec/subagent_server/` entirely
    2. Delete `src/vaultspec/mcp_tools/` entirely
    3. Delete `src/vaultspec/server.py`

- Phase 6: verify
    1. Run `uv run pytest src/vaultspec/mcp_server/tests/ -x -q`
    2. Run `uv run pytest src/vaultspec/orchestration/tests/test_team_lifecycle.py -x -q`
    3. Run `uv run pytest src/vaultspec/tests/cli/test_team_cli.py -x -q`
    4. Run `uv run python -c "from vaultspec.mcp_server import create_server, initialize_server"`
    5. Run full test suite: `uv run pytest src/ tests/ -x -q`

## Parallelization

- Phases 1-2 must be sequential (tests depend on source files existing)
- Phase 3 and Phase 4 can run in parallel (external refs and docs are independent)
- Phase 5 depends on all prior phases
- Phase 6 depends on Phase 5

Team structure:
- **Agent A (complex-executor)**: Phases 1 + 2 + 5 (file moves, core refactoring)
- **Agent B (standard-executor)**: Phase 3 (external import rewrites)
- **Agent C (simple-executor)**: Phase 4 (documentation updates)
- Agents B and C start after Agent A completes Phases 1-2, run in parallel
- Agent A deletes old packages (Phase 5) after B and C complete
- **Agent D (code-reviewer)**: Phase 6 verification + review

## Verification

- All existing tests pass with zero failures
- `from vaultspec.mcp_server import create_server` resolves correctly
- `from vaultspec.mcp_server import initialize_server` resolves correctly
- No remaining imports from `vaultspec.server`, `vaultspec.subagent_server`,
  or `vaultspec.mcp_tools` exist in the codebase (verified via grep)
- `pyproject.toml` entry point references `vaultspec.mcp_server.app:main`
- No `subagent_server/` or `mcp_tools/` directories remain
- The deprecated legacy `main()` is removed from `subagent_tools.py`
