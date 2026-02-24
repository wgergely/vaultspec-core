---
tags:
  - "#adr"
  - "#mcp-consolidation"
date: "2026-02-22"
related:
  - "[[2026-02-22-mcp-consolidation-research]]"
  - "[[2026-02-21-packaging-restructure-adr]]"
  - "[[2026-02-22-cli-ecosystem-factoring-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `mcp-consolidation` adr: `merge server.py, subagent_server/, and mcp_tools/ into mcp_server/` | (**status:** `accepted`)

## Problem Statement

The MCP server surface is scattered across three locations that grew
organically and now carry misleading names.

**`subagent_server/` is misnamed.** The package contains 961 lines of general
MCP infrastructure -- `initialize_server()`, `register_tools()`,
`subagent_lifespan()`, `TaskEngine`/`LockManager` wiring, agent file polling,
dynamic resource registration, and 5 tool functions. These are core MCP server
concerns, not subagent-specific concerns. The name `subagent_server` implies a
standalone server dedicated to subagent dispatch, but the module is actually the
infrastructure backbone that the unified server depends on.

**`server.py` at the package root is ambiguous.** It is the MCP server entry
point (`FastMCP` creation, lifespan composition, tool module registration), but
nothing in the filename indicates MCP. It can be confused with the A2A server at
`protocol/a2a/server.py`. At 116 lines it is a thin composition layer that
imports from both `subagent_server` and `mcp_tools`.

**`mcp_tools/` is a grab-bag.** Only one of its three modules is implemented:
`team_tools.py` (857 lines, 10 tools). The other two -- `vault_tools.py` and
`framework_tools.py` -- are no-op stubs awaiting business logic extraction from
`cli.py` (see [[2026-02-22-cli-ecosystem-factoring-adr]] Phase 3). The package
name `mcp_tools` is generic and sits as a peer to `subagent_server` despite
registering tools onto the same `FastMCP` instance.

The fragmentation creates three concrete problems:

- **Disorienting navigation.** A developer looking for "the MCP server code"
  must check three locations. The name `subagent_server` actively misdirects
  them away from infrastructure code that is not subagent-specific.

- **Confused dependency direction.** `server.py` imports from both
  `subagent_server` and `mcp_tools`, but this composition relationship is
  invisible from the package structure. The two tool packages have no knowledge
  of each other and manage their own globals independently.

- **Scattered tests.** MCP test files are split across
  `subagent_server/tests/` (4 files) and `mcp_tools/tests/` (1 file), with
  two additional cross-module test files in `orchestration/tests/` and
  `tests/cli/`. There is no single place to find "all MCP server tests."

## Considerations

### Option C (`mcp/` package) -- rejected due to name shadowing

The research in [[2026-02-22-mcp-consolidation-research]] evaluated creating a
`src/vaultspec/mcp/` package as Option C. This option offers the cleanest name
(`vaultspec.mcp`) but carries a critical defect: the third-party `mcp` PyPI
package (version >=1.20.0, declared in `pyproject.toml`) is imported via bare
`from mcp.server.fastmcp import FastMCP` in at least 16 source and test files.
Inside any module within `src/vaultspec/mcp/`, a bare `import mcp` or
`from mcp import ...` would resolve to the local `vaultspec.mcp` subpackage
rather than the third-party `mcp` package. This would break every file that
imports from `mcp.server.fastmcp`. Workarounds (e.g., `importlib` tricks to
force external resolution) are fragile and non-idiomatic. Option C is rejected.

### Stub readiness

The two stub modules (`vault_tools.py` and `framework_tools.py`) are waiting
on [[2026-02-22-cli-ecosystem-factoring-adr]] Phase 3, which extracts the
business logic from `cli.py` into `vaultspec.core` submodules. Until that
extraction completes, the stubs have no upstream library to call. This
consolidation moves the stubs into `mcp_server/` as-is, preserving their
no-op `register_tools()` signatures so that Phase 3 of the cli-ecosystem
ADR can populate them without a second structural migration.

### Legacy standalone `main()` in `subagent_server/server.py`

The function at line 905 of `subagent_server/server.py` is explicitly marked
deprecated in its docstring: "Prefer the unified entry point
`vaultspec.server:main` instead." It duplicates the initialization logic that
now lives in `server.py:main()`. The sole consumer is `subagent_cli.py`, which
imports it as `from .subagent_server.server import main as server_main` for
the `vaultspec subagent serve` subcommand. This consolidation removes the
legacy `main()` and rewires `subagent_cli.py` to import from the new location.

### Independent globals

Each module manages its own mutable state independently:

- `subagent_server/server.py` owns 11 module-level globals (`ROOT_DIR`,
  `CONTENT_ROOT`, `AGENTS_DIR`, `lock_manager`, `task_engine`,
  `_agent_cache`, `_background_tasks`, `_active_clients`, `_refresh_fn`,
  `_run_subagent_fn`, `_mcp_ref`), initialized via `initialize_server()`.
- `mcp_tools/team_tools.py` owns 2 module-level globals (`_root_dir`,
  `_team_task_engine`), initialized via `set_root_dir()`.
- `server.py` calls both initialization functions as the composition root.

Moving these modules into a single package does not merge or alter their
globals. Each file retains its own state. The composition pattern in `app.py`
remains the single place where initialization order is coordinated.

## Constraints

- **No behavioral changes.** This is a structural refactoring only. Every MCP
  tool function must produce identical results before and after the migration.
  The test suite is the verification mechanism.

- **No name shadowing.** The third-party `mcp` PyPI package (version >=1.20.0)
  is imported via `from mcp.server.fastmcp import FastMCP` in 16 source and
  test files. The new package name must not shadow it. This rules out `mcp/`
  as a subpackage name.

- **Single-commit migration.** All file moves, import rewrites, and
  `pyproject.toml` changes must land in one commit. Partial migration (some
  files using old paths, some using new) creates import failures.

- **No new dependencies.** The refactoring must not introduce any new
  third-party dependencies.

- **Approximately 20 files affected.** The research identified 9 source files,
  8 test files, 1 configuration file (`pyproject.toml`), and 4 documentation
  files that require updates.

## Implementation

### Target structure

```
src/vaultspec/mcp_server/
  __init__.py           # Public API re-exports
  app.py                # FastMCP creation, lifespan, tool registration, main()
  subagent_tools.py     # 5 subagent tools + infrastructure (from subagent_server/server.py)
  team_tools.py         # 10 team tools (from mcp_tools/team_tools.py)
  vault_tools.py        # Stub (from mcp_tools/vault_tools.py)
  framework_tools.py    # Stub (from mcp_tools/framework_tools.py)
  tests/
    __init__.py
    conftest.py
    test_mcp_tools.py           # (from subagent_server/tests/)
    test_mcp_protocol.py        # (from subagent_server/tests/)
    test_helpers.py             # (from subagent_server/tests/)
    test_task_engine_integration.py  # (from subagent_server/tests/)
    test_team_tools.py          # (from mcp_tools/tests/)
```

### File moves

| Before | After |
|:---|:---|
| `src/vaultspec/server.py` | `src/vaultspec/mcp_server/app.py` |
| `src/vaultspec/subagent_server/server.py` | `src/vaultspec/mcp_server/subagent_tools.py` |
| `src/vaultspec/subagent_server/__init__.py` | deleted |
| `src/vaultspec/mcp_tools/team_tools.py` | `src/vaultspec/mcp_server/team_tools.py` |
| `src/vaultspec/mcp_tools/vault_tools.py` | `src/vaultspec/mcp_server/vault_tools.py` |
| `src/vaultspec/mcp_tools/framework_tools.py` | `src/vaultspec/mcp_server/framework_tools.py` |
| `src/vaultspec/mcp_tools/__init__.py` | deleted |
| `src/vaultspec/subagent_server/tests/*` | `src/vaultspec/mcp_server/tests/*` |
| `src/vaultspec/mcp_tools/tests/*` | `src/vaultspec/mcp_server/tests/*` |

### `mcp_server/__init__.py` public API

The `__init__.py` re-exports the symbols that external consumers and internal
modules currently import:

```python
from .app import create_server, main
from .subagent_tools import (
    cancel_task,
    dispatch_agent,
    get_locks,
    get_task_status,
    initialize_server,
    list_agents,
    register_tools as register_subagent_tools,
    subagent_lifespan,
)
from .team_tools import (
    register_tools as register_team_tools,
    set_root_dir as set_team_root_dir,
)
```

### `mcp_server/app.py` changes

The module is essentially the current `server.py` with updated imports:

- `from .subagent_server import ...` becomes `from .subagent_tools import ...`
- `from .mcp_tools import ...` becomes `from .team_tools import ...`
- `from .mcp_tools.team_tools import ...` becomes
  `from .team_tools import ...`

No logic changes.

### `mcp_server/subagent_tools.py` changes

The legacy standalone `main()` function (lines 905-960 of
`subagent_server/server.py`) is deleted. All other code moves unchanged.

### Import rewrites

| File | Old import | New import |
|:---|:---|:---|
| `src/vaultspec/__main__.py` | `from .server import main as run` | `from .mcp_server.app import main as run` |
| `src/vaultspec/subagent_cli.py` | `from .subagent_server.server import main as server_main` | `from .mcp_server.app import main as server_main` |
| `mcp_server/tests/test_mcp_tools.py` | `from .. import server as srv` | `from .. import subagent_tools as srv` |
| `mcp_server/tests/test_mcp_protocol.py` | `from ...server import create_server` | `from ..app import create_server` |
| `orchestration/tests/test_team_lifecycle.py` | `from ...server import create_server` | `from ...mcp_server.app import create_server` |
| `orchestration/tests/test_team_lifecycle.py` | `from ...mcp_tools.team_tools import ...` | `from ...mcp_server.team_tools import ...` |
| `tests/cli/test_team_cli.py` | `from ...mcp_tools.team_tools import ...` | `from ...mcp_server.team_tools import ...` |

### `pyproject.toml` changes

```toml
# Before:
vaultspec-mcp = "vaultspec.server:main"

# After:
vaultspec-mcp = "vaultspec.mcp_server.app:main"
```

### `subagent_cli.py` rewire

The `vaultspec subagent serve` subcommand currently calls the deprecated
`subagent_server.server.main()`. After consolidation, it calls
`mcp_server.app.main()` -- the same unified entry point used by the
`vaultspec-mcp` console script. This eliminates the behavioral divergence
between the two entry paths.

### Documentation updates

The following documentation files reference module paths or package names that
change:

- `.vaultspec/docs/cli-reference.md`
- `.vaultspec/docs/concepts.md`
- `.vaultspec/rules/rules/vaultspec-subagents.builtin.md`
- `.claude/rules/vaultspec-subagents.builtin.md`

These require updating `subagent_server` and `mcp_tools` references to
`mcp_server`.

### Packages deleted

- `src/vaultspec/subagent_server/` (entire directory)
- `src/vaultspec/mcp_tools/` (entire directory)

No backward-compatibility shims are provided for these packages. They are
internal implementation details with no external consumers. All first-party
imports are rewritten in the same commit.

## Rationale

Option D (`mcp_server/`) was chosen over the three alternatives evaluated in
[[2026-02-22-mcp-consolidation-research]] for the following reasons:

**Option A (rename `server.py` to `mcp_server.py`) is insufficient.** It
disambiguates the entry point but does not address the `subagent_server`
misnomer or the fragmented package structure. The three-module confusion
persists.

**Option B (move `server.py` into `mcp_tools/`) inverts the dependency.**
The entry point (`server.py`) imports from `subagent_server`, so placing it
inside `mcp_tools` creates a confusing dependency where `mcp_tools.server`
depends on a sibling package `subagent_server`. The name `mcp_tools` becomes
inaccurate when it also contains the server entry point.

**Option C (`mcp/` package) shadows the third-party `mcp` dependency.** As
documented in the research, any module inside `src/vaultspec/mcp/` that
writes `from mcp.server.fastmcp import FastMCP` would resolve to the local
subpackage rather than the PyPI dependency. This is a critical defect that
would break 16 import sites. The fix would require non-idiomatic `importlib`
workarounds. Option C is rejected.

**Option D (`mcp_server/` package) resolves both naming problems without name
shadowing.** The name `mcp_server` is unambiguous -- it is the MCP server
package. It does not collide with the third-party `mcp` package. The internal
file naming is descriptive: `app.py` for FastMCP creation and composition,
`subagent_tools.py` for dispatch/task tools, `team_tools.py` for team
coordination tools. The package structure mirrors the functional domains:
entry point, subagent tools, team tools, and future vault/framework tools.

The migration scope (~20 files) is comparable to Option C but avoids its
critical defect. The single-commit approach and absence of backward-compat
shims are justified by the fact that all three modules are internal -- no
external package or script imports from `vaultspec.subagent_server` or
`vaultspec.mcp_tools`.

## Consequences

### Positive

- **Single location for all MCP server code.** Developers looking for MCP
  tools, infrastructure, or the server entry point find everything under
  `mcp_server/`.

- **Accurate naming.** `mcp_server/subagent_tools.py` describes what the
  module does (provides subagent dispatch tools), not what it was historically
  called. `mcp_server/app.py` clearly identifies the FastMCP application
  entry point.

- **Consolidated test directory.** All MCP server tests live under
  `mcp_server/tests/`, making test discovery and maintenance straightforward.

- **Legacy code removed.** The deprecated standalone `main()` in
  `subagent_server/server.py` is deleted, eliminating a code path that
  duplicated the unified entry point's initialization logic.

- **Stub placement is forward-compatible.** The `vault_tools.py` and
  `framework_tools.py` stubs are already in their final location within
  `mcp_server/`. When [[2026-02-22-cli-ecosystem-factoring-adr]] Phase 3
  completes the business logic extraction, the stubs can be populated
  in-place without another structural migration.

### Negative

- **~20 files modified in a single commit.** The blast radius is significant
  for a structural refactoring. A missed import rewrite will cause an
  `ImportError` at runtime. Mitigation: scripted find-and-replace followed
  by full test suite execution.

- **No backward-compatibility shims.** If any external tooling or script
  imports from `vaultspec.subagent_server` or `vaultspec.mcp_tools`, it will
  break. This is accepted because these packages are internal and the project
  has no published API guarantees.

- **`subagent_cli.py` behavior change.** The `vaultspec subagent serve`
  command now calls the unified `mcp_server.app.main()` instead of the
  deprecated standalone entry point. This changes the initialization path
  (the unified entry point uses `get_config()` for root directory resolution
  rather than the legacy env-var fallback). This is a desirable behavioral
  alignment, not a regression, but it should be verified in testing.

### Future work

- **Phase 3 of [[2026-02-22-cli-ecosystem-factoring-adr]]**: Once the
  business logic is extracted from `cli.py` into `vaultspec.core`, the
  `vault_tools.py` and `framework_tools.py` stubs in `mcp_server/` can be
  populated with real tool implementations. This is tracked by the
  cli-ecosystem ADR and does not require a separate structural migration.

- **Phase 3 of [[2026-02-21-packaging-restructure-adr]]**: The packaging
  restructure ADR's Phase 3 (vault + framework CLI tools as MCP tools)
  originally targeted `mcp_tools/vault_tools.py` and
  `mcp_tools/framework_tools.py`. After this consolidation, the target
  becomes `mcp_server/vault_tools.py` and `mcp_server/framework_tools.py`.
  The scope and intent are unchanged; only the file paths differ.

- **Tool count growth.** The unified `mcp_server/` package will eventually
  host ~35 tools across 4-5 modules. If client-side tool sprawl becomes a
  concern, tool namespacing or grouping can be introduced at the FastMCP
  registration layer without changing the package structure.
