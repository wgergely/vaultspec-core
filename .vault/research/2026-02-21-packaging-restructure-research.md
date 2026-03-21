---
tags:
  - '#research'
  - '#packaging-restructure'
date: '2026-02-21'
related:
  - '[[2026-02-21-packaging-restructure-adr]]'
---

# `packaging-restructure` research: `uv + unified MCP server`

Exhaustive audit of the Python codebase under `.vaultspec/lib/` to inform
restructuring from the current layout to a proper `src/vaultspec/` namespace
package with a single unified MCP server (`vaultspec-mcp`), using `uv` as
the package manager.

______________________________________________________________________

## 1. Import Graph

### 1.1 Current sys.path hack

All four CLI scripts (`cli.py`, `subagent.py`, `vault.py`, `team.py`) in
`.vaultspec/lib/scripts/` share a common bootstrap module `_paths.py`
(`.vaultspec/lib/scripts/_paths.py`) that performs:

```python

# line 22-25

LIB_SRC_DIR: Path = _LIB_DIR / "src"
if str(LIB_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_SRC_DIR))
```

This injects `.vaultspec/lib/src/` onto `sys.path`, enabling bare-name
imports like `from core.workspace import ...`, `from orchestration.subagent import ...`, etc. The `pyproject.toml` mirrors this for pytest:

```toml

# pyproject.toml lines 68-69

testpaths = [".vaultspec/lib/tests", ".vaultspec/lib/src"]
pythonpath = [".vaultspec/lib/src", ".vaultspec/lib/scripts", ".vaultspec/lib"]
```

### 1.2 Bare-name packages (top-level under `.vaultspec/lib/src/`)

| Package             | Purpose                                                                                                                                         |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/`             | `config.py` (singleton VaultSpecConfig), `workspace.py` (layout resolution)                                                                     |
| `orchestration/`    | `subagent.py` (run_subagent), `task_engine.py`, `team.py` (TeamCoordinator), `session_logger.py`, `utils.py`, `constants.py`                    |
| `protocol/`         | `sandbox.py`, `providers/` (base, claude, gemini), `acp/` (client, bridge, types), `a2a/` (server, discovery, executors, agent_card, state_map) |
| `rag/`              | `api.py`, `embeddings.py`, `indexer.py`, `search.py`, `store.py`                                                                                |
| `subagent_server/`  | `server.py` (the FastMCP server)                                                                                                                |
| `vaultcore/`        | `models.py`, `parser.py`, `scanner.py`, `links.py`, `hydration.py`                                                                              |
| `verification/`     | `api.py`                                                                                                                                        |
| `graph/`            | `api.py`                                                                                                                                        |
| `metrics/`          | `api.py`                                                                                                                                        |
| `hooks/`            | `engine.py`                                                                                                                                     |
| `logging_config.py` | Standalone module (not a package)                                                                                                               |

### 1.3 Inter-module dependency graph (production code only)

```
subagent_server/server.py
  -> logging_config
  -> vaultcore.parser
  -> orchestration.constants
  -> orchestration.subagent
  -> orchestration.task_engine
  -> orchestration.utils
  -> protocol.acp.types
  -> core.config (via initialize_server)

orchestration/subagent.py
  -> vaultcore.parser
  -> orchestration.utils
  -> protocol.acp.client
  -> protocol.acp.types
  -> protocol.providers.claude
  -> protocol.providers.gemini

orchestration/team.py
  -> (a2a-sdk types, httpx)

orchestration/session_logger.py
  -> core.config

protocol/acp/claude_bridge.py
  -> logging_config
  -> protocol.providers.base
  -> protocol.sandbox

protocol/a2a/executors/base.py
  -> protocol.sandbox

protocol/a2a/executors/claude_executor.py
  -> protocol.a2a.executors.base

protocol/a2a/executors/gemini_executor.py
  -> orchestration.subagent
  -> protocol.providers.base

graph/api.py
  -> vaultcore.links
  -> vaultcore.models
  -> vaultcore.parser
  -> vaultcore.scanner

metrics/api.py
  -> vaultcore.models
  -> vaultcore.scanner

verification/api.py
  -> vaultcore.models
  -> vaultcore.parser
  -> vaultcore.scanner

rag/indexer.py
  -> rag.store
  -> vaultcore.models
  -> vaultcore.parser
  -> vaultcore.scanner

vaultcore/parser.py
  -> vaultcore.models

vaultcore/scanner.py
  -> vaultcore.models

vaultcore/hydration.py
  -> vaultcore.models
```

**Leaf packages** (no internal deps): `core`, `logging_config`
**Most-depended-on**: `vaultcore` (used by graph, metrics, verification,
rag, orchestration, subagent_server), `core.config` (used by
orchestration, subagent_server, protocol, cli.py, vault.py)

### 1.4 Script-level imports (from `_paths.py` + bare-name)

| Script        | Bare-name imports                                                                                                                                                                   |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cli.py`      | `_paths`, `core.workspace`, `core.config`, `logging_config`, `protocol.providers.claude`, `protocol.providers.gemini`, `vaultcore.parser`, `hooks.engine`                           |
| `subagent.py` | `_paths`, `core.workspace`, `logging_config`, `subagent_server.server`, `orchestration.subagent`, `protocol.acp.client`, `protocol.providers.base`                                  |
| `vault.py`    | `_paths`, `core.workspace`, `logging_config`, `graph.api`, `metrics.api`, `vaultcore.hydration`, `vaultcore.models`, `verification.api`, `rag.api`, `rag.embeddings`, `core.config` |
| `team.py`     | `_paths`, `core.workspace`, `logging_config`, `orchestration.team`                                                                                                                  |

### 1.5 Circular dependency analysis

No circular dependencies found. The dependency graph is a DAG. `vaultcore`
is at the bottom (leaf), followed by `core`, with `orchestration` and
`subagent_server` at the top.

### 1.6 What breaks under `vaultspec.*` namespace

Every bare-name import must be rewritten. Counts:

- **Production code**: 38 bare-name `from X import Y` statements across
  non-test `.py` files in `lib/src/`

- **Test code**: 78 bare-name imports across test files in `lib/src/*/tests/`
  and `lib/tests/`

- **Scripts**: 21 bare-name imports across the four CLI scripts

- **conftest.py files**: 12 bare-name imports across 11 conftest files

Total: ~149 import statements that reference bare package names and must
be prefixed with `vaultspec.`.

Additionally:

- `from _paths import ROOT_DIR` in all scripts (4 occurrences) -- `_paths.py`
  would be eliminated entirely; workspace resolution moves to library code

- `import cli` in 6 test files (`tests/cli/`) -- `cli` module would become
  `vaultspec.cli` or similar

- `from tests.constants import ...` in conftest files (3 occurrences) --
  test constants path would change

______________________________________________________________________

## 2. CLI-to-MCP Mapping

### 2.1 `cli.py` -- Framework Config Manager

**Total lines**: 2360. **Status**: Fully functional, production-grade.

**Subcommands (argparse hierarchy)**:

| Resource    | Command    | Handler             | Status | MCP mapping                                        |
| ----------- | ---------- | ------------------- | ------ | -------------------------------------------------- |
| `rules`     | `list`     | `rules_list()`      | Real   | `list_rules` tool (read-only)                      |
| `rules`     | `add`      | `rules_add()`       | Real   | `create_rule` tool                                 |
| `rules`     | `show`     | `resource_show()`   | Real   | Resource `rules://{name}`                          |
| `rules`     | `edit`     | `resource_edit()`   | Real   | N/A (interactive editor)                           |
| `rules`     | `remove`   | `resource_remove()` | Real   | `remove_rule` tool                                 |
| `rules`     | `rename`   | `resource_rename()` | Real   | `rename_rule` tool                                 |
| `rules`     | `sync`     | `rules_sync()`      | Real   | `sync_rules` tool                                  |
| `agents`    | `list`     | `agents_list()`     | Real   | Already MCP-exposed via `list_agents`              |
| `agents`    | `add`      | `agents_add()`      | Real   | `create_agent` tool                                |
| `agents`    | `show`     | `resource_show()`   | Real   | Already MCP-exposed via `agents://{name}` resource |
| `agents`    | `edit`     | `resource_edit()`   | Real   | N/A (interactive editor)                           |
| `agents`    | `remove`   | `resource_remove()` | Real   | `remove_agent` tool                                |
| `agents`    | `rename`   | `resource_rename()` | Real   | `rename_agent` tool                                |
| `agents`    | `sync`     | `agents_sync()`     | Real   | `sync_agents` tool                                 |
| `agents`    | `set-tier` | `agents_set_tier()` | Real   | `set_agent_tier` tool                              |
| `skills`    | `list`     | `skills_list()`     | Real   | `list_skills` tool                                 |
| `skills`    | `add`      | `skills_add()`      | Real   | `create_skill` tool                                |
| `skills`    | `show`     | `resource_show()`   | Real   | Resource `skills://{name}`                         |
| `skills`    | `edit`     | `resource_edit()`   | Real   | N/A (interactive)                                  |
| `skills`    | `remove`   | `resource_remove()` | Real   | `remove_skill` tool                                |
| `skills`    | `rename`   | `resource_rename()` | Real   | `rename_skill` tool                                |
| `skills`    | `sync`     | `skills_sync()`     | Real   | `sync_skills` tool                                 |
| `config`    | `show`     | `config_show()`     | Real   | `show_config` tool                                 |
| `config`    | `sync`     | `config_sync()`     | Real   | `sync_config` tool                                 |
| `system`    | `show`     | `system_show()`     | Real   | `show_system` tool                                 |
| `system`    | `sync`     | `system_sync()`     | Real   | `sync_system` tool                                 |
| `sync-all`  | --         | (calls all syncs)   | Real   | `sync_all` tool                                    |
| `test`      | --         | `test_run()`        | Real   | N/A (developer tooling)                            |
| `doctor`    | --         | `doctor_run()`      | Real   | `doctor` tool (read-only)                          |
| `init`      | --         | `init_run()`        | Real   | `init` tool                                        |
| `readiness` | --         | `readiness_run()`   | Real   | `readiness` tool (read-only)                       |
| `hooks`     | `list`     | `hooks_list()`      | Real   | `list_hooks` tool                                  |
| `hooks`     | `run`      | `hooks_run()`       | Real   | `trigger_hook` tool                                |

**Overlap**: `agents list` duplicates functionality already in the MCP
server's `list_agents` tool. `agents show` duplicates `agents://{name}`
resource.

**MCP-incompatible commands**: `edit` (all resources) -- requires
interactive terminal editor. `test` -- subprocess pytest invocation.

### 2.2 `subagent.py` -- Sub-agent CLI

**Total lines**: 366. **Status**: Fully functional, production-grade.

| Command     | Handler               | Status | MCP mapping                                    |
| ----------- | --------------------- | ------ | ---------------------------------------------- |
| `run`       | `command_run()`       | Real   | Already MCP-exposed as `dispatch_agent`        |
| `serve`     | `command_serve()`     | Real   | Entry point for MCP server (not a tool itself) |
| `a2a-serve` | `command_a2a_serve()` | Real   | Separate HTTP server launcher                  |
| `list`      | `command_list()`      | Real   | Already MCP-exposed as `list_agents`           |

**Overlap**: `list` duplicates `cli.py agents list` and the MCP
`list_agents` tool. `run` is the CLI equivalent of `dispatch_agent`.

### 2.3 `vault.py` -- Vault Audit & Management

**Total lines**: 464. **Status**: Fully functional, production-grade.

| Command            | Handler           | Status | MCP mapping                            |
| ------------------ | ----------------- | ------ | -------------------------------------- |
| `audit --summary`  | `handle_audit()`  | Real   | `vault_audit` tool (with summary flag) |
| `audit --features` | `handle_audit()`  | Real   | `list_features` tool                   |
| `audit --verify`   | `handle_audit()`  | Real   | `verify_vault` tool                    |
| `audit --graph`    | `handle_audit()`  | Real   | `vault_graph` tool                     |
| `audit --fix`      | `handle_audit()`  | Real   | `fix_vault` tool                       |
| `create`           | `handle_create()` | Real   | `create_document` tool                 |
| `index`            | `handle_index()`  | Real   | `index_vault` tool (GPU required)      |
| `search`           | `handle_search()` | Real   | `search_vault` tool                    |

**No overlap** with other scripts. All vault.py functionality is currently
CLI-only with no MCP exposure.

### 2.4 `team.py` -- Multi-Agent Team CLI

**Total lines**: 499. **Status**: Functional but dependent on A2A server
availability.

| Command     | Handler               | Status | MCP mapping              |
| ----------- | --------------------- | ------ | ------------------------ |
| `create`    | `command_create()`    | Real   | `create_team` tool       |
| `status`    | `command_status()`    | Real   | `team_status` tool       |
| `list`      | `command_list()`      | Real   | `list_teams` tool        |
| `assign`    | `command_assign()`    | Real   | `assign_task` tool       |
| `broadcast` | `command_broadcast()` | Real   | `broadcast_message` tool |
| `message`   | `command_message()`   | Real   | `send_message` tool      |
| `dissolve`  | `command_dissolve()`  | Real   | `dissolve_team` tool     |

**No overlap** with other scripts. All team.py functionality is currently
CLI-only with no MCP exposure.

______________________________________________________________________

## 3. Existing MCP Server Audit

**File**: `.vaultspec/lib/src/subagent_server/server.py` (690 lines)

### 3.1 FastMCP Initialization

```python

# line 58-67

mcp = FastMCP(
    name="vs-subagent-mcp",
    instructions="MCP server for running sub-agents via ACP. ...",
    lifespan=_server_lifespan,
)
```

### 3.2 Lifespan

`_server_lifespan()` (line 44-55): Starts an agent-file polling background
task that watches `AGENTS_DIR` for `.md` file changes and re-registers
resources. Polling interval comes from `core.config.mcp_poll_interval`.

### 3.3 Registered `@mcp.tool()` endpoints

| Tool                | Line    | Title                   | Read-only | Destructive | Purpose                                  |
| ------------------- | ------- | ----------------------- | --------- | ----------- | ---------------------------------------- |
| `list_agents()`     | 362-390 | "List Available Agents" | Yes       | No          | Return JSON list of agents with tiers    |
| `dispatch_agent()`  | 393-551 | "Dispatch Sub-Agent"    | No        | No          | Async subagent execution, returns taskId |
| `get_task_status()` | 554-593 | "Get Task Status"       | Yes       | No          | Poll task status + result                |
| `cancel_task()`     | 596-629 | "Cancel Task"           | No        | Yes         | Cancel running task                      |
| `get_locks()`       | 632-656 | "Get Active Locks"      | Yes       | No          | List advisory file locks                 |

### 3.4 Registered `@mcp.resource()` endpoints

Resources are dynamically registered via `_register_agent_resources()`
(line 303-331). For each agent `.md` file in `AGENTS_DIR`:

```
agents://{name}  ->  JSON metadata (name, tier, description, tools, etc.)
```

Resources are re-registered when agent files change on disk (polled).

### 3.5 Server entry point

`main()` (line 659-685): Called from `subagent.py serve`. Takes
`root_dir` and `content_root` kwargs. Falls back to
`VAULTSPEC_MCP_ROOT_DIR` env var. Calls `initialize_server()` then
`mcp.run()`.

### 3.6 Functionality NOT currently MCP-exposed

- All of `cli.py` (rules/agents/skills CRUD, sync, config, system,
  readiness, hooks, init, doctor, test)

- All of `vault.py` (audit, create, index, search)

- All of `team.py` (create, status, list, assign, broadcast, message,
  dissolve)

The current MCP server is purely a subagent dispatch + management API.

______________________________________________________________________

## 4. Workspace Resolution

### 4.1 `_paths.py` resolution chain

**File**: `.vaultspec/lib/scripts/_paths.py` (45 lines)

**Step 1 -- Structural bootstrap** (lines 19-25):

```python
_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPTS_DIR.parent           # .vaultspec/lib/
_FRAMEWORK_ROOT = _LIB_DIR.parent        # .vaultspec/
LIB_SRC_DIR = _LIB_DIR / "src"
sys.path.insert(0, str(LIB_SRC_DIR))     # The sys.path hack
```

**Step 2 -- Workspace layout resolution** (lines 35-44):

```python
from core.workspace import resolve_workspace
_layout = resolve_workspace(
    root_override=_env_path("VAULTSPEC_ROOT_DIR"),
    content_override=_env_path("VAULTSPEC_CONTENT_DIR"),
    framework_dir_name=os.environ.get("VAULTSPEC_FRAMEWORK_DIR", ".vaultspec"),
    framework_root=_FRAMEWORK_ROOT,
)
ROOT_DIR: Path = _layout.output_root
```

### 4.2 `core/workspace.py` -- `WorkspaceLayout` dataclass

**File**: `.vaultspec/lib/src/core/workspace.py` (406 lines)

```python
@dataclass(frozen=True)
class WorkspaceLayout:
    content_root: Path     # Where rules/agents/skills live
    output_root: Path      # Where .vault/ output goes (project root)
    vault_root: Path       # output_root / ".vault"
    framework_root: Path   # Where the Python code lives (.vaultspec/)
    mode: LayoutMode       # STANDALONE or EXPLICIT
    git: GitInfo | None    # Discovered git metadata
```

**Resolution priority** (line 261-405):

1. Both `root_override` + `content_override` explicit -> EXPLICIT mode
1. Only `content_override` -> derive output_root from git or framework_root
1. Only `root_override` -> STANDALONE mode, content = root / framework_dir
1. No overrides -> git detection -> structural fallback from framework_root
   -> cwd-based last resort

**Validation** (line 227-254): Checks `content_root` exists as dir,
`output_root.parent` exists, `framework_root/lib/` exists.

### 4.3 Path semantics

| Symbol            | Current value         | Meaning                                                 |
| ----------------- | --------------------- | ------------------------------------------------------- |
| `_FRAMEWORK_ROOT` | `.vaultspec/`         | Where framework config lives (rules, agents, templates) |
| `LIB_SRC_DIR`     | `.vaultspec/lib/src/` | Where Python source code lives                          |
| `content_root`    | `.vaultspec/`         | Where rules/agents/skills content lives                 |
| `output_root`     | repo root             | Where `.vault/` output goes                             |
| `vault_root`      | repo root / `.vault/` | Documentation vault                                     |
| `framework_root`  | `.vaultspec/`         | Structural root of the framework                        |

### 4.4 What changes with `src/vaultspec/` move

**Before**: `framework_root` == directory containing Python code AND config
**After**: `framework_root` == `.vaultspec/` (config only), Python code
lives at `src/vaultspec/` (completely separate)

The critical change is the **validation in `_validate()`** at line 246-253:

```python
lib_dir = layout.framework_root / "lib"
if not lib_dir.is_dir():
    raise WorkspaceError(...)
```

This validation assumes Python code lives under `framework_root/lib/`.
After restructuring, this check must be removed or changed, since the
Python package lives at `src/vaultspec/` (a sibling of `.vaultspec/`, not
under it).

### 4.5 MCP server root path

In `mcp.json` (line 4):

```json
"args": [".vaultspec/lib/scripts/subagent.py", "serve", "--root", "."]
```

The `--root .` argument passes the CWD as the workspace root. After
restructuring, this becomes `uv run vaultspec-mcp` (or similar), and root
detection can use git discovery or CWD, eliminating the `--root` flag.

______________________________________________________________________

## 5. Test Infrastructure

### 5.1 pyproject.toml test config

```toml
[tool.pytest.ini_options]
testpaths = [".vaultspec/lib/tests", ".vaultspec/lib/src"]
pythonpath = [".vaultspec/lib/src", ".vaultspec/lib/scripts", ".vaultspec/lib"]
asyncio_mode = "auto"
markers = [
    "unit", "api", "search", "index", "quality",
    "integration", "gemini", "claude", "timeout",
    "a2a", "e2e", "benchmark", "team"
]
```

The `pythonpath` config adds 3 paths to `sys.path` for pytest, enabling
the same bare-name imports used by `_paths.py`.

### 5.2 conftest.py path manipulation

**Root conftest** (`.vaultspec/lib/conftest.py`, line 10):

```python
from tests.constants import PROJECT_ROOT, TEST_PROJECT, TEST_VAULT
```

This works because `.vaultspec/lib/` is on `pythonpath`. The `tests`
package is imported as a bare name.

**`tests/constants.py`** (line 20-22): Derives `PROJECT_ROOT` via
relative path traversal:

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```

This is `tests/ -> lib/ -> .vaultspec/ -> repo root` (4 levels up).
After restructuring, this becomes `tests/ -> vaultspec/ -> src/ -> repo root` (still 4 levels, but different semantics -- or it uses the package
metadata).

**Module conftest files**: `graph/tests/conftest.py`,
`metrics/tests/conftest.py`, `verification/tests/conftest.py` all import
`from core.config import reset_config` and `from tests.constants import TEST_PROJECT` -- both bare-name imports.

**CLI conftest** (`tests/cli/conftest.py`, line 9):

```python
import cli
```

Imports `cli.py` from scripts as a bare module -- only works because
`.vaultspec/lib/scripts` is on `pythonpath`.

### 5.3 Test file counts by module

| Module area            | Location                     | Test files                                                                                                                                                                                          |
| ---------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| core                   | `src/core/tests/`            | 2 (`test_config.py`, `test_workspace.py`)                                                                                                                                                           |
| vaultcore              | `src/vaultcore/tests/`       | 5 (`test_core.py`, `test_hydration.py`, `test_links.py`, `test_scanner.py`, `test_types.py`)                                                                                                        |
| orchestration          | `src/orchestration/tests/`   | 5 (`test_load_agent.py`, `test_session_logger.py`, `test_task_engine.py`, `test_team.py`, `test_utils.py`)                                                                                          |
| protocol               | `src/protocol/tests/`        | 5 (`test_client.py`, `test_fileio.py`, `test_permissions.py`, `test_providers.py`, `test_sandbox.py`)                                                                                               |
| protocol/acp           | `src/protocol/acp/tests/`    | 6 (`test_bridge_lifecycle.py`, `test_bridge_resilience.py`, `test_bridge_sandbox.py`, `test_bridge_streaming.py`, `test_client_terminal.py`, `test_e2e_bridge.py`)                                  |
| protocol/a2a           | `src/protocol/a2a/tests/`    | 8 (`test_agent_card.py`, `test_claude_executor.py`, `test_discovery.py`, `test_e2e_a2a.py`, `test_french_novel_relay.py`, `test_gemini_executor.py`, `test_integration_a2a.py`, `test_unit_a2a.py`) |
| rag                    | `src/rag/tests/`             | 5 (`test_embeddings.py`, `test_indexer_unit.py`, `test_query.py`, `test_search_unit.py`, `test_store.py`)                                                                                           |
| subagent_server        | `src/subagent_server/tests/` | 2 (`test_helpers.py`, `test_mcp_tools.py`)                                                                                                                                                          |
| graph                  | `src/graph/tests/`           | 1 (`test_graph.py`)                                                                                                                                                                                 |
| metrics                | `src/metrics/tests/`         | 1 (`test_metrics.py`)                                                                                                                                                                               |
| verification           | `src/verification/tests/`    | 1 (`test_verification.py`)                                                                                                                                                                          |
| hooks                  | `src/hooks/tests/`           | 1 (`test_hooks.py`)                                                                                                                                                                                 |
| cli (integration)      | `tests/cli/`                 | 7 (`test_integration.py`, `test_sync_collect.py`, `test_sync_incremental.py`, `test_sync_operations.py`, `test_sync_parse.py`, `test_team_cli.py`, `test_vault_cli.py`)                             |
| rag (integration)      | `tests/rag/`                 | 7 (`test_api.py`, `test_indexer.py`, `test_performance.py`, `test_quality.py`, `test_robustness.py`, `test_search.py`, `test_store.py`)                                                             |
| subagent (integration) | `tests/subagent/`            | 2 (`test_mcp_protocol.py`, `test_subagent.py`)                                                                                                                                                      |
| e2e                    | `tests/e2e/`                 | 5 (`test_claude.py`, `test_full_cycle.py`, `test_gemini.py`, `test_mcp_e2e.py`, `test_provider_parity.py`)                                                                                          |
| top-level              | `tests/`                     | 3 (`test_config.py`, `test_logging_config.py`, `test_mcp_config.py`)                                                                                                                                |
| benchmarks             | `tests/benchmarks/`          | 1 (`bench_rag.py`)                                                                                                                                                                                  |

**Total**: 66 test files across 2 test trees (`lib/src/*/tests/` and
`lib/tests/`).

### 5.4 Import compatibility

Every test file uses bare-name imports. **All 66 test files** would need
import rewrites under the `vaultspec.*` namespace. Additionally, 6 CLI test
files import `cli` as a bare module.

______________________________________________________________________

## 6. uv Compatibility

### 6.1 Current `pyproject.toml` status

The current `pyproject.toml` uses **setuptools** as the build backend:

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
```

Package discovery:

```toml
[tool.setuptools.packages.find]
where = [".vaultspec/lib/src"]
```

This is a valid PEP 517 configuration but has no `[project.scripts]`
entry points defined.

### 6.2 uv readiness assessment

**Compatible as-is**:

- PEP 621 `[project]` metadata (name, version, dependencies, etc.)
- `[project.optional-dependencies]` groups (dev, rag, dev-rag)
- `requires-python = ">=3.13"`

**Requires changes for uv**:

- Build backend: `setuptools` works with `uv`, but `hatchling` is the
  more idiomatic choice for modern Python projects and is `uv`'s default.
  Either works.

- Package discovery: `where = [".vaultspec/lib/src"]` must change to
  `where = ["src"]` (standard src-layout)

- Entry points: None defined currently; need `[project.scripts]`

- The `pythonpath` hack in `[tool.pytest.ini_options]` would be replaced
  by the installed package being importable

### 6.3 Legacy packaging artifacts

**None found**. No `requirements.txt`, `setup.cfg`, or `setup.py` files
exist at the project root or under `.vaultspec/`.

### 6.4 uv-specific configuration

After restructuring, the `pyproject.toml` would use:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/vaultspec"]
```

Or with setuptools:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

`uv sync --dev` would install the package in editable mode, making
`import vaultspec` work everywhere without `sys.path` hacks.

______________________________________________________________________

## 7. Entry Points Design

### 7.1 Required entry points

| Entry point          | Purpose                                              | Current implementation                                       |
| -------------------- | ---------------------------------------------------- | ------------------------------------------------------------ |
| `vaultspec`          | Main CLI (rules, agents, skills, config, sync, etc.) | `cli.py:main()`                                              |
| `vaultspec-mcp`      | Unified MCP server                                   | `subagent_server/server.py:main()` (currently subagent-only) |
| `vaultspec-vault`    | Vault management CLI                                 | `vault.py:main()`                                            |
| `vaultspec-team`     | Team management CLI                                  | `team.py:main()`                                             |
| `vaultspec-subagent` | Subagent runner CLI                                  | `subagent.py:main()`                                         |

Alternatively, all CLIs could be subcommands of a single `vaultspec`
entry point (e.g., `vaultspec vault audit`, `vaultspec team create`,
`vaultspec subagent run`).

### 7.2 FastMCP server startup

Currently (`subagent_server/server.py` line 659-685):

```python
def main(root_dir=None, content_root=None):
    ...
    initialize_server(root_dir=root_dir, ...)
    mcp.run()
```

Called via `subagent.py serve` which passes `args.root` and
`args.content_root`. The MCP server itself uses `mcp.run()` which
handles stdio transport.

### 7.3 Proposed `[project.scripts]`

```toml
[project.scripts]
vaultspec = "vaultspec.cli:main"
vaultspec-mcp = "vaultspec.server:main"
```

Where `vaultspec.server` is the unified MCP server that aggregates
subagent, vault, and team tools. Individual CLI scripts could be:

```toml
vaultspec-vault = "vaultspec.vault_cli:main"
vaultspec-team = "vaultspec.team_cli:main"
vaultspec-subagent = "vaultspec.subagent_cli:main"
```

______________________________________________________________________

## 8. mcp.json Design

### 8.1 Current `mcp.json`

```json
{
  "mcpServers": {
    "vs-subagent-mcp": {
      "command": "python",
      "args": [".vaultspec/lib/scripts/subagent.py", "serve", "--root", "."],
      "env": {}
    }
  }
}
```

This launches a raw Python process with the script path. It relies on
the system Python having the package installed or `sys.path` hacking.

### 8.2 Proposed `mcp.json` with `uv run`

```json
{
  "mcpServers": {
    "vaultspec-mcp": {
      "command": "uv",
      "args": ["run", "vaultspec-mcp"],
      "env": {}
    }
  }
}
```

This uses the `[project.scripts]` entry point. `uv run` automatically
resolves the project's virtual environment and runs the registered console
script. No `--root` flag is needed because the server can detect the
workspace root via git discovery from `$CWD`.

**Alternative** (if the server needs explicit root):

```json
{
  "mcpServers": {
    "vaultspec-mcp": {
      "command": "uv",
      "args": ["run", "vaultspec-mcp", "--root", "."],
      "env": {}
    }
  }
}
```

### 8.3 Unified server scope

The current `vs-subagent-mcp` server exposes only 5 tools (list_agents,
dispatch_agent, get_task_status, cancel_task, get_locks). The unified
`vaultspec-mcp` server would aggregate:

- **Subagent tools** (5 existing): list_agents, dispatch_agent,
  get_task_status, cancel_task, get_locks

- **Vault tools** (~8 new): vault_audit, list_features, verify_vault,
  vault_graph, fix_vault, create_document, index_vault, search_vault

- **Team tools** (~7 new): create_team, team_status, list_teams,
  assign_task, broadcast_message, send_message, dissolve_team

- **Framework tools** (~15 new from cli.py): sync_all, list_rules,
  create_rule, list_skills, create_skill, show_config, sync_config,
  doctor, readiness, etc.

- **Agent resources** (existing): agents://{name} dynamic resources

Total: approximately 35 MCP tools and dynamic agent resources.

______________________________________________________________________

## 9. Summary of Key Findings

### 9.1 Scale of the migration

- **~149 import statements** must be rewritten (bare-name -> namespaced)

- **66 test files** affected

- **4 CLI scripts** to refactor into proper package entry points

- **1 MCP server** to expand from 5 tools to ~35 tools

- **1 `_paths.py`** to eliminate entirely

- **1 `pyproject.toml`** to restructure (build backend, package discovery,
  entry points)

- **1 `mcp.json`** to update

- **12 `conftest.py`** files to update

### 9.2 Zero-risk changes

- Moving code from `.vaultspec/lib/src/` to `src/vaultspec/` is purely
  structural

- Adding `vaultspec.` prefix to all imports is mechanical

- Adding `[project.scripts]` entry points is additive

- Switching `mcp.json` to `uv run` is a one-line change

### 9.3 Medium-risk changes

- Eliminating `_paths.py` and its `sys.path` hack requires workspace
  resolution to move into library code (already partially there via
  `core.workspace`)

- The `_validate()` check for `framework_root/lib/` must be updated

- Tests that import `cli` as a bare module need the module to be
  importable under the new namespace

### 9.4 Higher-risk changes

- Expanding the MCP server from 5 to ~35 tools requires careful API
  design to avoid tool sprawl

- Team commands involve async A2A network operations that are harder to
  test in MCP tool context

- RAG tools (index, search) require GPU and have long-running operations
  that may need background task patterns similar to dispatch_agent
