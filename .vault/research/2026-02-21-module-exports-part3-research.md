---
tags:
  - '#research'
  - '#module-exports'
date: '2026-02-21'
related:
  - '[[2026-02-21-packaging-restructure-adr]]'
---

# `module-exports` research: graph, metrics, verification, subagent_server, mcp_tools, top-level

Part 3 of the import/export audit covers the remaining packages
(`graph`, `metrics`, `verification`, `subagent_server`, `mcp_tools`)
and all top-level modules under `src/vaultspec/`. This part also
provides cross-cutting analysis: complexity totals, test import
strategy, and circular import risk assessment.

______________________________________________________________________

## 1. `vaultspec.graph`

### 1A. `__init__.py`

Empty (single blank line). No re-exports.

### 1B. `api.py` -- public symbols

| Symbol       | Kind      | Description                       |
| ------------ | --------- | --------------------------------- |
| `DocNode`    | dataclass | Node in the vault document graph  |
| `VaultGraph` | class     | Directed graph of vault documents |

### 1C. Cross-package imports (absolute)

| Source file    | Import statement                                                                  | Target package |
| -------------- | --------------------------------------------------------------------------------- | -------------- |
| `graph/api.py` | `from vaultspec.vaultcore.links import extract_related_links, extract_wiki_links` | `vaultcore`    |
| `graph/api.py` | `from vaultspec.vaultcore.models import DocType`                                  | `vaultcore`    |
| `graph/api.py` | `from vaultspec.vaultcore.parser import parse_vault_metadata`                     | `vaultcore`    |
| `graph/api.py` | `from vaultspec.vaultcore.scanner import get_doc_type, scan_vault`                | `vaultcore`    |

No intra-package imports (single-module package).

### 1D. Proposed `__all__` for `api.py`

```python
__all__ = ["DocNode", "VaultGraph"]
```

### 1E. Proposed `__init__.py` re-exports

```python
from vaultspec.graph.api import DocNode, VaultGraph

__all__ = ["DocNode", "VaultGraph"]
```

______________________________________________________________________

## 2. `vaultspec.metrics`

### 2A. `__init__.py`

Empty (single blank line). No re-exports.

### 2B. `api.py` -- public symbols

| Symbol              | Kind      | Description                        |
| ------------------- | --------- | ---------------------------------- |
| `VaultSummary`      | dataclass | Aggregate statistics for the vault |
| `get_vault_metrics` | function  | Calculate summary statistics       |

### 2C. Cross-package imports (absolute)

| Source file      | Import statement                                                   | Target package                         |
| ---------------- | ------------------------------------------------------------------ | -------------------------------------- |
| `metrics/api.py` | `from vaultspec.vaultcore.models import DocType`                   | `vaultcore`                            |
| `metrics/api.py` | `from vaultspec.vaultcore.scanner import get_doc_type, scan_vault` | `vaultcore`                            |
| `metrics/api.py` | `from vaultspec.verification.api import list_features`             | `verification` (lazy, inside function) |

### 2D. Proposed `__all__` for `api.py`

```python
__all__ = ["VaultSummary", "get_vault_metrics"]
```

### 2E. Proposed `__init__.py` re-exports

```python
from vaultspec.metrics.api import VaultSummary, get_vault_metrics

__all__ = ["VaultSummary", "get_vault_metrics"]
```

______________________________________________________________________

## 3. `vaultspec.verification`

### 3A. `__init__.py`

Empty (single blank line). No re-exports.

### 3B. `api.py` -- public symbols

| Symbol                      | Kind      | Description                       |
| --------------------------- | --------- | --------------------------------- |
| `VerificationError`         | class     | Single vault verification failure |
| `verify_vault_structure`    | function  | Check unsupported dirs/files      |
| `verify_file`               | function  | All checks on a single file       |
| `get_malformed`             | function  | All docs that fail verification   |
| `list_features`             | function  | Infer features from tags          |
| `verify_vertical_integrity` | function  | Feature-to-plan mapping check     |
| `FixResult`                 | dataclass | Result of a single auto-repair    |
| `fix_violations`            | function  | Auto-repair common violations     |

Private helper: `_rebuild_frontmatter` (not exported).

### 3C. Cross-package imports (absolute)

| Source file           | Import statement                                                                   | Target package    |
| --------------------- | ---------------------------------------------------------------------------------- | ----------------- |
| `verification/api.py` | `from vaultspec.vaultcore.models import DocType, DocumentMetadata, VaultConstants` | `vaultcore`       |
| `verification/api.py` | `from vaultspec.vaultcore.parser import parse_vault_metadata`                      | `vaultcore`       |
| `verification/api.py` | `from vaultspec.vaultcore.scanner import get_doc_type, scan_vault`                 | `vaultcore`       |
| `verification/api.py` | `from vaultspec.core.config import get_config`                                     | `core` (lazy, x2) |

### 3D. Proposed `__all__` for `api.py`

```python
__all__ = [
    "VerificationError",
    "verify_vault_structure",
    "verify_file",
    "get_malformed",
    "list_features",
    "verify_vertical_integrity",
    "FixResult",
    "fix_violations",
]
```

### 3E. Proposed `__init__.py` re-exports

```python
from vaultspec.verification.api import (
    FixResult,
    VerificationError,
    fix_violations,
    get_malformed,
    list_features,
    verify_file,
    verify_vault_structure,
    verify_vertical_integrity,
)

__all__ = [
    "FixResult",
    "VerificationError",
    "fix_violations",
    "get_malformed",
    "list_features",
    "verify_file",
    "verify_vault_structure",
    "verify_vertical_integrity",
]
```

______________________________________________________________________

## 4. `vaultspec.subagent_server`

### 4A. `__init__.py`

Empty (single blank line). No re-exports.

### 4B. `server.py` -- public symbols

**Functions:**

| Symbol              | Kind              | Description                                     |
| ------------------- | ----------------- | ----------------------------------------------- |
| `initialize_server` | function          | Initialize server config (must call before run) |
| `register_tools`    | function          | Register MCP tools on FastMCP instance          |
| `subagent_lifespan` | async context mgr | Lifespan: starts agent-file polling             |
| `list_agents`       | async function    | List available sub-agents                       |
| `dispatch_agent`    | async function    | Run sub-agent asynchronously                    |
| `get_task_status`   | async function    | Check task status                               |
| `cancel_task`       | async function    | Cancel a running task                           |
| `get_locks`         | async function    | List active advisory locks                      |
| `main`              | function          | Legacy standalone entry point                   |

**Private helpers (not for export):**
`_resolve_effective_mode`, `_inject_permission_prompt`, `_prepare_dispatch_kwargs`,
`_extract_artifacts`, `_merge_artifacts`, `_poll_interval`, `_strip_quotes`,
`_parse_tools`, `_parse_agent_metadata`, `_snapshot_mtimes`, `_has_changes`,
`_build_agent_cache`, `_register_agent_resources`, `_refresh_if_changed`,
`_send_list_changed`, `_poll_agent_files`, plus module-level globals.

### 4C. Cross-package imports (absolute)

| Source file                 | Import statement                                                           | Target package    |
| --------------------------- | -------------------------------------------------------------------------- | ----------------- |
| `subagent_server/server.py` | `from vaultspec.logging_config import configure_logging`                   | top-level         |
| `subagent_server/server.py` | `from vaultspec.vaultcore.parser import parse_frontmatter`                 | `vaultcore`       |
| `subagent_server/server.py` | `from vaultspec.orchestration.constants import READONLY_PERMISSION_PROMPT` | `orchestration`   |
| `subagent_server/server.py` | `from vaultspec.orchestration.subagent import run_subagent`                | `orchestration`   |
| `subagent_server/server.py` | `from vaultspec.orchestration.task_engine import LockManager, TaskEngine`  | `orchestration`   |
| `subagent_server/server.py` | `from vaultspec.orchestration.utils import safe_read_text`                 | `orchestration`   |
| `subagent_server/server.py` | `from vaultspec.protocol.acp.types import SubagentError`                   | `protocol`        |
| `subagent_server/server.py` | `from vaultspec.core.config import get_config`                             | `core` (lazy, x3) |

### 4D. Proposed `__all__` for `server.py`

```python
__all__ = [
    "initialize_server",
    "register_tools",
    "subagent_lifespan",
    "list_agents",
    "dispatch_agent",
    "get_task_status",
    "cancel_task",
    "get_locks",
    "main",
]
```

### 4E. Proposed `__init__.py` re-exports

Given the server module's complexity and the fact that it holds mutable
global state, re-exporting only the primary integration API is safest:

```python
from vaultspec.subagent_server.server import (
    initialize_server,
    register_tools,
    subagent_lifespan,
)

__all__ = ["initialize_server", "register_tools", "subagent_lifespan"]
```

______________________________________________________________________

## 5. `vaultspec.mcp_tools`

### 5A. `__init__.py`

Contains a module docstring explaining the register-tools pattern.
No re-exports, no `__all__`.

### 5B. `vault_tools.py`, `team_tools.py`, `framework_tools.py`

All three are **no-op stubs** deferred to future phases. Each exports
a single function:

| Module               | Symbol                | Status         |
| -------------------- | --------------------- | -------------- |
| `vault_tools.py`     | `register_tools(mcp)` | Stub (Phase 3) |
| `team_tools.py`      | `register_tools(mcp)` | Stub (Phase 4) |
| `framework_tools.py` | `register_tools(mcp)` | Stub (Phase 3) |

### 5C. Cross-package imports

None at runtime. `from mcp.server.fastmcp import FastMCP` is under
`TYPE_CHECKING` only.

### 5D. Proposed `__init__.py` re-exports

```python
from vaultspec.mcp_tools.framework_tools import register_tools as register_framework_tools
from vaultspec.mcp_tools.team_tools import register_tools as register_team_tools
from vaultspec.mcp_tools.vault_tools import register_tools as register_vault_tools

__all__ = [
    "register_framework_tools",
    "register_team_tools",
    "register_vault_tools",
]
```

______________________________________________________________________

## 6. Top-level modules

### 6A. `logging_config.py`

| Symbol              | Kind     | Description              |
| ------------------- | -------- | ------------------------ |
| `configure_logging` | function | Idempotent logging setup |
| `reset_logging`     | function | Reset for tests          |

**Cross-package imports:** None (stdlib only).

### 6B. `server.py`

| Symbol          | Kind     | Description                     |
| --------------- | -------- | ------------------------------- |
| `create_server` | function | Create unified FastMCP instance |
| `main`          | function | Entry point for `vaultspec-mcp` |

**Cross-package imports (absolute):**

- `from vaultspec.subagent_server.server import initialize_server, register_tools, subagent_lifespan`
- `from vaultspec.core.config import get_config` (lazy)

### 6C. `cli.py`

The largest module (2359 lines). Framework resource manager.

**Cross-package imports (absolute, top-level):**

- `from vaultspec.core.workspace import WorkspaceLayout, resolve_workspace`
- `from vaultspec.logging_config import configure_logging`
- `from vaultspec.protocol.providers.claude import ClaudeProvider` (try/except)
- `from vaultspec.protocol.providers.gemini import GeminiProvider` (try/except)
- `from vaultspec.vaultcore.parser import parse_frontmatter`

**Lazy imports (inside functions):**

- `from vaultspec.core.config import get_config` (x7)
- `from vaultspec.protocol.providers.base import CapabilityLevel`
- `from vaultspec.hooks.engine import SUPPORTED_EVENTS, load_hooks, trigger`

Total: **12 unique absolute import statements**.

### 6D. `vault_cli.py`

**Cross-package imports (absolute):**

- `from vaultspec.core.workspace import WorkspaceLayout, resolve_workspace`
- `from vaultspec.graph.api import VaultGraph`
- `from vaultspec.logging_config import configure_logging`
- `from vaultspec.metrics.api import get_vault_metrics`
- `from vaultspec.vaultcore.hydration import get_template_path, hydrate_template`
- `from vaultspec.vaultcore.models import DocType`
- `from vaultspec.verification.api import fix_violations, get_malformed, list_features, verify_vertical_integrity`
- `from vaultspec.core.config import get_config` (lazy)
- `from vaultspec.rag.api import index` (lazy)
- `from vaultspec.rag.embeddings import get_device_info` (lazy)
- `from vaultspec.rag.api import search` (lazy)

Total: **11 unique absolute import statements**.

### 6E. `team_cli.py`

**Cross-package imports (absolute):**

- `from vaultspec.core.workspace import WorkspaceLayout, resolve_workspace`
- `from vaultspec.logging_config import configure_logging`
- `from vaultspec.orchestration.team import MemberStatus, TeamCoordinator, TeamMember, TeamSession, TeamStatus`

Total: **3 unique absolute import statements**.

### 6F. `subagent_cli.py`

**Cross-package imports (absolute):**

- `from vaultspec.core.workspace import WorkspaceLayout, resolve_workspace`
- `from vaultspec.logging_config import configure_logging`
- `from vaultspec.subagent_server.server import main as server_main` (try/except)
- `from vaultspec.orchestration.subagent import run_subagent` (try/except)
- `from vaultspec.protocol.acp.client import SubagentClient` (try/except)
- `from vaultspec.protocol.providers.base import ClaudeModels, GeminiModels` (try/except)
- `from vaultspec.orchestration.constants import READONLY_PERMISSION_PROMPT` (lazy)
- `from vaultspec.protocol.a2a.agent_card import agent_card_from_definition` (lazy)
- `from vaultspec.protocol.a2a.server import create_app` (lazy)
- `from vaultspec.protocol.a2a.executors.claude_executor import ClaudeA2AExecutor` (lazy)
- `from vaultspec.protocol.a2a.executors.gemini_executor import GeminiA2AExecutor` (lazy)
- `from vaultspec.core.config import get_config` (lazy)

Total: **12 unique absolute import statements**.

### 6G. `__init__.py`

Empty (single blank line). No re-exports, no `__all__`.

### 6H. `__main__.py`

```python
from vaultspec.cli import main
```

Single absolute import enabling `python -m vaultspec`.

______________________________________________________________________

## 7. Complexity assessment

### 7A. Total absolute `from vaultspec.X.Y import Z` counts

**Production code** (non-test files under `src/vaultspec/`):

| Location                    | Count  |
| --------------------------- | ------ |
| `graph/api.py`              | 4      |
| `metrics/api.py`            | 3      |
| `verification/api.py`       | 5      |
| `subagent_server/server.py` | 10     |
| `mcp_tools/*.py`            | 0      |
| `logging_config.py`         | 0      |
| `server.py`                 | 2      |
| `cli.py`                    | 12     |
| `vault_cli.py`              | 11     |
| `team_cli.py`               | 3      |
| `subagent_cli.py`           | 12     |
| `__main__.py`               | 1      |
| **Subtotal (this part)**    | **63** |

Combining with parts 1 and 2 (packages `core`, `vaultcore`, `rag`,
`orchestration`, `protocol`, `hooks`), the full codebase total of
absolute `from vaultspec.*` imports in production code is approximately
**~160 statements**.

### 7B. Package complexity ranking (most complex first)

1. **`cli.py`** -- 2359 lines, 12 cross-package imports, imports from 5 different packages
1. **`subagent_cli.py`** -- 367 lines, 12 cross-package imports, imports from 5 different packages
1. **`subagent_server/server.py`** -- 755 lines, 10 cross-package imports, heavy async/state management
1. **`vault_cli.py`** -- 466 lines, 11 cross-package imports, imports from 6 different packages
1. **`verification/api.py`** -- 353 lines, 5 cross-package imports, complex repair logic
1. **`graph/api.py`** -- 128 lines, 4 cross-package imports, self-contained
1. **`metrics/api.py`** -- 53 lines, 3 cross-package imports, simple
1. **`mcp_tools/*`** -- stubs, no imports

### 7C. Recommended execution order (leaf-first)

1. `mcp_tools/` -- stubs, trivial, no real imports
1. `graph/` -- leaf package, depends only on `vaultcore`
1. `metrics/` -- leaf package, depends on `vaultcore` + lazy `verification`
1. `verification/` -- leaf package, depends on `vaultcore` + lazy `core`
1. `subagent_server/` -- depends on `orchestration`, `protocol`, `vaultcore`, `core`
1. `logging_config.py` -- no internal deps, trivial
1. `server.py` -- thin wrapper over `subagent_server`
1. `__main__.py` -- single import
1. `vault_cli.py` -- entry point, imports many packages
1. `team_cli.py` -- entry point
1. `subagent_cli.py` -- entry point
1. `cli.py` -- entry point, largest module

### 7D. Should CLI modules and `server.py` use relative imports?

**Recommendation: No.** CLI modules (`cli.py`, `vault_cli.py`, `team_cli.py`,
`subagent_cli.py`) and `server.py` are **entry points** -- they sit at the
package root and are invoked as `python -m vaultspec` or via
`[project.scripts]` console entry points. These modules should continue
using absolute imports for these reasons:

- Entry points are the "outermost layer" and do not benefit from refactor
  portability that relative imports provide.

- Absolute imports in entry points make the dependency graph explicit and
  readable.

- PEP 328 relative imports only add value within packages with internal
  structure; top-level modules have no parent package to be relative to
  (their relative import would be `from .core.config import get_config`,
  which is valid but provides no clarity benefit).

The one exception: `__main__.py` currently uses `from vaultspec.cli import main`.
This could become `from .cli import main` but the gain is negligible.

**For sub-packages** (`graph/api.py`, `metrics/api.py`, `verification/api.py`,
`subagent_server/server.py`): cross-package imports (e.g.,
`from vaultspec.vaultcore.X`) should remain absolute. Only intra-package
imports (e.g., within `subagent_server/` if it had multiple modules
importing each other) should use relative form.

______________________________________________________________________

## 8. Test import strategy

### 8A. Test import inventory

**Top-level `tests/` directory** (`Y:\code\vaultspec-worktrees\main\tests\`):
Approximately **94** `from vaultspec.*` import statements across test files.

**In-tree tests** (`src/vaultspec/*/tests/`):
Approximately **130** `from vaultspec.*` import statements.

**Combined total: ~224 `from vaultspec.*` statements in test files.**

All test imports use absolute `from vaultspec.X.Y import Z` form.
No test files use relative imports.

### 8B. Test import patterns observed

Tests import at three levels of depth:

- **Public API** (e.g., `from vaultspec.graph.api import VaultGraph`) -- most common
- **Sub-module internals** (e.g., `from vaultspec.rag.store import _parse_json_list`) -- testing private helpers
- **Module-as-namespace** (e.g., `import vaultspec.cli as cli`) -- for monkeypatching

### 8C. Recommendation

Tests **should use public API imports** where possible (e.g.,
`from vaultspec.verification import get_malformed` once `__init__.py`
re-exports are in place). However, reaching into sub-modules is
**acceptable and expected** for tests that:

- Test private/internal helpers directly (e.g., `_parse_json_list`,
  `_extract_feature`)

- Need to monkeypatch module-level state

- Need fine-grained import control for isolation

The pragmatic approach: do NOT rewrite existing test imports during
the module-exports restructure. Tests should not break. Once
`__init__.py` re-exports are in place, new tests should prefer the
public API surface. Existing tests can be migrated opportunistically.

______________________________________________________________________

## 9. Circular import risk analysis

### 9A. Dependency graph (packages only)

```
core           <- (no internal deps, true leaf)
vaultcore      <- core (lazy)
hooks          <- core (lazy)
graph          <- vaultcore
metrics        <- vaultcore, verification (lazy)
verification   <- vaultcore, core (lazy)
rag            <- vaultcore, core (lazy), graph (lazy), metrics (lazy), verification (lazy)
orchestration  <- vaultcore, core (lazy), protocol
protocol       <- core (lazy), orchestration (partial), vaultcore
subagent_server <- orchestration, protocol, vaultcore, core (lazy), logging_config
mcp_tools      <- (no deps, stubs)
```

### 9B. Identified circular risk: `metrics` \<-> `verification`

**Current state:**

- `metrics/api.py` has a **lazy** import: `from vaultspec.verification.api import list_features` (inside `get_vault_metrics()`)
- `verification/api.py` does NOT import from `metrics`

**Risk if `__init__.py` re-exports are added eagerly:**
If `metrics/__init__.py` eagerly imports from `metrics/api.py`, and
`metrics/api.py` eagerly imports from `verification/api.py`, and
`verification/__init__.py` eagerly imports from `verification/api.py`...
this chain is **one-directional** and safe. No circular dependency exists.

**Verdict: SAFE.** The `metrics -> verification` import is lazy (inside
a function body), so even if both `__init__.py` files eagerly re-export
their `api.py` symbols, no circular import occurs at module load time.

### 9C. Identified circular risk: `orchestration` \<-> `protocol`

**Current state:**

- `orchestration/subagent.py` imports from `protocol.acp.client`, `protocol.acp.types`, `protocol.providers.claude`, `protocol.providers.gemini`
- `protocol/a2a/executors/gemini_executor.py` imports from `orchestration.subagent`
- `protocol/acp/claude_bridge.py` does NOT import from `orchestration`

**Risk with `__init__.py` re-exports:**
If `orchestration/__init__.py` eagerly imports `run_subagent` from
`orchestration/subagent.py`, which eagerly imports from `protocol/...`,
and `protocol/__init__.py` eagerly imports from its sub-modules which
import from `orchestration`... this would create:

```
orchestration/__init__ -> orchestration/subagent -> protocol/providers/...
protocol/a2a/executors/gemini_executor -> orchestration/subagent
```

This is NOT a circular import because:

- The `orchestration/__init__.py` would import from `orchestration/subagent.py`
- `subagent.py` imports from `protocol.providers.claude`, `protocol.providers.gemini`, etc.
- Those provider modules do NOT import from `orchestration`
- The reverse direction (`protocol/a2a/executors/gemini_executor -> orchestration/subagent`) only triggers when `gemini_executor` is loaded, which would not happen during `orchestration/__init__` loading

**Verdict: SAFE** as long as `protocol/__init__.py` does not eagerly
re-export from `a2a/executors/gemini_executor.py`. The `protocol`
package's `__init__.py` should only re-export from `protocol/acp/` and
`protocol/providers/`, not from `protocol/a2a/executors/`.

### 9D. Identified circular risk: `rag` -> `graph` -> `vaultcore` -> `core`

**Chain:** `rag/api.py` -> `graph/api.py` -> `vaultcore/...` -> `core/config` (lazy)

All `core` imports in this chain are lazy (inside function bodies). The
chain is strictly one-directional. **No circular risk.**

### 9E. Summary of circular import risks

| Pair                                  | Direction      | Risk | Mitigation                                                         |
| ------------------------------------- | -------------- | ---- | ------------------------------------------------------------------ |
| `metrics` -> `verification`           | One-way        | None | Lazy import already in place                                       |
| `orchestration` \<-> `protocol`       | Bidirectional  | Low  | Keep `protocol/__init__` shallow; do NOT re-export `a2a.executors` |
| `rag` -> `graph/metrics/verification` | One-way        | None | All lazy imports                                                   |
| `core` \<- everything                 | One-way inward | None | `core` has no internal deps                                        |
| `vaultcore` \<- everything            | One-way inward | None | `vaultcore` depends only on `core` (lazy)                          |

**Key rule:** When populating `__init__.py` files with re-exports, limit
re-exports to the package's own `api.py` or immediate children. Do NOT
transitively re-export symbols from deeply nested sub-packages. This
preserves the lazy-import boundaries that currently prevent circular
chains.
