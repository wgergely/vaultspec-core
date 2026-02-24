---
tags:
  - "#research"
  - "#module-exports"
date: "2026-02-21"
related:
  - "[[2026-02-21-packaging-restructure-adr]]"
---
# `module-exports` research: core, vaultcore, orchestration

Audit of the import/export structure for three packages under `src/vaultspec/`: `core`, `vaultcore`, and `orchestration`. The goal is to catalog every public symbol, every cross-package import, every intra-package import, and propose explicit `__all__` and `__init__.py` re-exports for each package.

## 1. `vaultspec.core`

### 1A. `__init__.py` contents

Single docstring, no re-exports:

```python
"""Core configuration and types for vaultspec."""
```

### 1B. Module public symbols

| Module | Public symbols |
|--------|---------------|
| `config.py` | `parse_csv_list`, `parse_int_or_none`, `parse_float_or_none`, `VaultSpecConfig`, `ConfigVariable`, `CONFIG_REGISTRY`, `get_config`, `reset_config` |
| `workspace.py` | `LayoutMode`, `GitInfo`, `WorkspaceLayout`, `WorkspaceError`, `discover_git`, `resolve_workspace` |

**Private symbols (prefixed with `_`):** `_SENTINEL`, `_parse_raw`, `_OptionalInt`, `_OptionalFloat`, `_cached_config` (config.py); `_strip_unc`, `_parse_git_pointer`, `_walk_up_for_git`, `_find_container_root`, `_validate` (workspace.py).

### 1C. Cross-package imports (from other `vaultspec.*` packages)

None. `vaultspec.core` has zero imports from other `vaultspec.*` packages. It is a leaf dependency.

### 1D. Intra-package imports

None. `config.py` and `workspace.py` do not import from each other.

### 1E. External consumers of `vaultspec.core`

| Consumer file | Symbols imported |
|---------------|-----------------|
| `cli.py` | `get_config` (from config), `WorkspaceLayout`, `resolve_workspace` (from workspace) |
| `vault_cli.py` | `get_config` (from config), `WorkspaceLayout`, `resolve_workspace` (from workspace) |
| `subagent_cli.py` | `get_config` (from config), `WorkspaceLayout`, `resolve_workspace` (from workspace) |
| `team_cli.py` | `WorkspaceLayout`, `resolve_workspace` (from workspace) |
| `server.py` | `get_config` (from config) |
| `hooks/engine.py` | `get_config` (from config) |
| `subagent_server/server.py` | `get_config` (from config) |
| `verification/api.py` | `get_config` (from config) |
| `protocol/providers/gemini.py` | `get_config` (from config) |
| `protocol/acp/claude_bridge.py` | `get_config` (from config) |
| `protocol/acp/client.py` | `get_config` (from config) |
| `protocol/a2a/discovery.py` | `get_config` (from config) |
| `protocol/a2a/agent_card.py` | `get_config` (from config) |
| `rag/embeddings.py` | `get_config` (from config) |
| `rag/search.py` | `get_config` (from config) |
| `rag/store.py` | `get_config` (from config) |
| `rag/indexer.py` | `get_config` (from config) |
| `rag/api.py` | `get_config` (from config) |
| `vaultcore/models.py` | `get_config` (from config) -- deferred inside method |
| `vaultcore/scanner.py` | `get_config` (from config) -- deferred inside functions |
| `vaultcore/hydration.py` | `get_config` (from config) -- deferred inside function |
| `orchestration/task_engine.py` | `get_config` (from config) -- deferred inside methods |
| `orchestration/session_logger.py` | `get_config` (from config) -- top-level import |
| `orchestration/subagent.py` | `get_config` (from config) -- deferred inside function |
| Tests: `reset_config` | `metrics/tests/conftest.py`, `graph/tests/conftest.py`, `verification/tests/conftest.py`, `vaultcore/tests/test_scanner.py`, `rag/tests/test_indexer_unit.py`, `protocol/a2a/tests/test_agent_card.py`, `orchestration/tests/test_session_logger.py` |

**De facto public API of `vaultspec.core`**: `get_config`, `reset_config`, `VaultSpecConfig`, `WorkspaceLayout`, `resolve_workspace`. The `ConfigVariable` and `CONFIG_REGISTRY` symbols are only consumed by `core/tests/test_config.py`.

### 1F. Proposed `__all__`

**`config.py`:**
```python
__all__ = [
    "VaultSpecConfig",
    "ConfigVariable",
    "CONFIG_REGISTRY",
    "get_config",
    "reset_config",
    "parse_csv_list",
    "parse_int_or_none",
    "parse_float_or_none",
]
```

**`workspace.py`:**
```python
__all__ = [
    "LayoutMode",
    "GitInfo",
    "WorkspaceLayout",
    "WorkspaceError",
    "discover_git",
    "resolve_workspace",
]
```

### 1G. Proposed `__init__.py` re-exports

```python
"""Core configuration and types for vaultspec."""

from vaultspec.core.config import VaultSpecConfig, get_config, reset_config
from vaultspec.core.workspace import WorkspaceLayout, resolve_workspace

__all__ = [
    "VaultSpecConfig",
    "get_config",
    "reset_config",
    "WorkspaceLayout",
    "resolve_workspace",
]
```

### 1H. Circular import risk

**None.** `core` is a leaf package. No modules within `core` import from each other, and `core` does not import from any other `vaultspec.*` package. The `__init__.py` re-exports proposed above are safe for eager loading.

---

## 2. `vaultspec.vaultcore`

### 2A. `__init__.py` contents

Empty file (single blank line).

### 2B. Module public symbols

| Module | Public symbols |
|--------|---------------|
| `models.py` | `DocType` (StrEnum), `DocumentMetadata` (dataclass), `VaultConstants` (class) |
| `parser.py` | `parse_frontmatter`, `parse_vault_metadata` |
| `scanner.py` | `scan_vault`, `get_doc_type` |
| `links.py` | `extract_wiki_links`, `extract_related_links` |
| `hydration.py` | `hydrate_template`, `get_template_path` |

**Private symbols:** `_simple_yaml_load`, `_yaml_load`, `_yaml_load_impl` (parser.py).

### 2C. Cross-package imports (from other `vaultspec.*` packages)

| Module | Import | Symbol | Notes |
|--------|--------|--------|-------|
| `models.py` | `from vaultspec.core.config import get_config` | `get_config` | Deferred inside `VaultConstants._get_docs_dir()` |
| `scanner.py` | `from vaultspec.core.config import get_config` | `get_config` | Deferred inside `scan_vault()` and `get_doc_type()` |
| `hydration.py` | `from vaultspec.core.config import get_config` | `get_config` | Deferred inside `get_template_path()` |

All cross-package imports target `vaultspec.core.config.get_config` only. All are deferred (inside function bodies), avoiding import-time coupling.

### 2D. Intra-package imports

| Module | Imports from |
|--------|-------------|
| `parser.py` | `from vaultspec.vaultcore.models import DocumentMetadata` |
| `scanner.py` | `from vaultspec.vaultcore.models import DocType` |
| `hydration.py` | `from vaultspec.vaultcore.models import DocType` |

`models.py` and `links.py` have no intra-package imports. `models.py` is the leaf of the intra-package dependency graph.

Dependency order: `models.py` -> `parser.py`, `scanner.py`, `hydration.py` (all depend on models). `links.py` is fully independent.

### 2E. External consumers of `vaultspec.vaultcore`

| Consumer file | Symbols imported |
|---------------|-----------------|
| `cli.py` | `parse_frontmatter` (from parser) |
| `vault_cli.py` | `hydrate_template`, `get_template_path` (from hydration); `DocType` (from models) |
| `verification/api.py` | `DocType`, `DocumentMetadata`, `VaultConstants` (from models); `parse_vault_metadata` (from parser); `get_doc_type`, `scan_vault` (from scanner) |
| `metrics/api.py` | `DocType` (from models); `get_doc_type`, `scan_vault` (from scanner) |
| `graph/api.py` | `extract_related_links`, `extract_wiki_links` (from links); `DocType` (from models); `parse_vault_metadata` (from parser); `get_doc_type`, `scan_vault` (from scanner) |
| `rag/indexer.py` | `DocType` (from models); `parse_vault_metadata` (from parser); `get_doc_type`, `scan_vault` (from scanner) |
| `rag/api.py` | `DocType` (from models); `parse_vault_metadata` (from parser); `get_doc_type`, `scan_vault` (from scanner) |
| `subagent_server/server.py` | `parse_frontmatter` (from parser) |
| `orchestration/subagent.py` | `parse_frontmatter` (from parser) |

**De facto public API of `vaultspec.vaultcore`**: `DocType`, `DocumentMetadata`, `VaultConstants`, `parse_frontmatter`, `parse_vault_metadata`, `scan_vault`, `get_doc_type`, `extract_wiki_links`, `extract_related_links`, `hydrate_template`, `get_template_path`. Every public symbol in every module is consumed externally.

### 2F. Proposed `__all__`

**`models.py`:**
```python
__all__ = ["DocType", "DocumentMetadata", "VaultConstants"]
```

**`parser.py`:**
```python
__all__ = ["parse_frontmatter", "parse_vault_metadata"]
```

**`scanner.py`:**
```python
__all__ = ["scan_vault", "get_doc_type"]
```

**`links.py`:**
```python
__all__ = ["extract_wiki_links", "extract_related_links"]
```

**`hydration.py`:**
```python
__all__ = ["hydrate_template", "get_template_path"]
```

### 2G. Proposed `__init__.py` re-exports

```python
"""Vault document parsing, scanning, and metadata models."""

from vaultspec.vaultcore.hydration import get_template_path, hydrate_template
from vaultspec.vaultcore.links import extract_related_links, extract_wiki_links
from vaultspec.vaultcore.models import DocType, DocumentMetadata, VaultConstants
from vaultspec.vaultcore.parser import parse_frontmatter, parse_vault_metadata
from vaultspec.vaultcore.scanner import get_doc_type, scan_vault

__all__ = [
    "DocType",
    "DocumentMetadata",
    "VaultConstants",
    "parse_frontmatter",
    "parse_vault_metadata",
    "scan_vault",
    "get_doc_type",
    "extract_wiki_links",
    "extract_related_links",
    "hydrate_template",
    "get_template_path",
]
```

### 2H. Circular import risk

**Low risk, but with a caveat.** Eagerly importing `scanner.py`, `hydration.py`, and `models.py` in `__init__.py` will trigger their module-level imports. However:

- `scanner.py` imports `DocType` from `models.py` (same package, safe).
- `hydration.py` imports `DocType` from `models.py` (same package, safe).
- `parser.py` imports `DocumentMetadata` from `models.py` (same package, safe).
- `models.py` has a deferred import of `vaultspec.core.config.get_config` inside a `@staticmethod` body -- safe at import time.
- `scanner.py` and `hydration.py` have deferred imports of `get_config` inside function bodies -- safe at import time.

**No circular risk.** All cross-package imports are deferred. Intra-package imports form a DAG rooted at `models.py`.

---

## 3. `vaultspec.orchestration`

### 3A. `__init__.py` contents

Empty file (single blank line).

### 3B. Module public symbols

| Module | Public symbols |
|--------|---------------|
| `subagent.py` | `AgentNotFoundError`, `load_agent`, `get_provider_for_model`, `run_subagent` |
| `task_engine.py` | `TaskStatus` (StrEnum), `is_terminal`, `SubagentTask` (dataclass), `FileLock` (dataclass), `TaskNotFoundError`, `InvalidTransitionError`, `generate_task_id`, `LockManager`, `TaskEngine` |
| `team.py` | `MemberStatus` (StrEnum), `TeamStatus` (StrEnum), `TeamMember` (dataclass), `TeamSession` (dataclass), `extract_artifact_text`, `TeamCoordinator` |
| `session_logger.py` | `SessionLogger`, `cleanup_old_logs` |
| `utils.py` | `SecurityError`, `find_project_root`, `safe_read_text` |
| `constants.py` | `READONLY_PERMISSION_PROMPT` |

**Private symbols:** `_CLAUDE_PATTERNS`, `_GEMINI_PATTERNS`, `_kill_process_tree`, `_build_task_prompt`, `_interactive_loop` (subagent.py); `_VALID_TRANSITIONS` (task_engine.py); `_TERMINAL_STATES`, `_DEFAULT_COLLECT_TIMEOUT` (team.py).

### 3C. Cross-package imports (from other `vaultspec.*` packages)

| Module | Import | Symbols | Deferred? |
|--------|--------|---------|-----------|
| `subagent.py` | `from vaultspec.vaultcore.parser` | `parse_frontmatter` | No (top-level) |
| `subagent.py` | `from vaultspec.protocol.acp.client` | `SessionLogger`, `SubagentClient` | No (top-level) |
| `subagent.py` | `from vaultspec.protocol.acp.types` | `SubagentError`, `SubagentResult` | No (top-level) |
| `subagent.py` | `from vaultspec.protocol.providers.claude` | `ClaudeProvider` | No (top-level) |
| `subagent.py` | `from vaultspec.protocol.providers.gemini` | `GeminiProvider` | No (top-level) |
| `subagent.py` | `from vaultspec.core.config` | `get_config` | Yes (inside `load_agent`) |
| `subagent.py` | `from acp` | `spawn_agent_process` | No (top-level, third-party) |
| `subagent.py` | `from acp.schema` | `ClientCapabilities`, etc. | No (top-level, third-party) |
| `task_engine.py` | `from vaultspec.core.config` | `get_config` | Yes (inside `LockManager._readonly_allowed_prefixes` and `TaskEngine.__init__`) |
| `team.py` | `from a2a.client` | `A2ACardResolver`, `A2AClient` | No (top-level, third-party) |
| `team.py` | `from a2a.types` | `AgentCard`, `Task`, etc. | No (top-level, third-party) |
| `session_logger.py` | `from vaultspec.core.config` | `get_config` | No (top-level) |
| `subagent.py` (TYPE_CHECKING) | `from vaultspec.protocol.providers.base` | `AgentProvider` | TYPE_CHECKING only |

**Summary of vaultspec-internal cross-package dependencies:**
- `subagent.py` depends on: `vaultspec.vaultcore`, `vaultspec.protocol.acp`, `vaultspec.protocol.providers`, `vaultspec.core`
- `task_engine.py` depends on: `vaultspec.core`
- `team.py` depends on: none (only third-party `a2a`, `httpx`)
- `session_logger.py` depends on: `vaultspec.core`
- `utils.py` depends on: none
- `constants.py` depends on: none

### 3D. Intra-package imports

| Module | Imports from |
|--------|-------------|
| `subagent.py` | `from vaultspec.orchestration.utils import safe_read_text` |

Only one intra-package import. All other modules are independent of each other within the package.

### 3E. External consumers of `vaultspec.orchestration`

| Consumer file | Symbols imported |
|---------------|-----------------|
| `subagent_cli.py` | `run_subagent` (from subagent); `READONLY_PERMISSION_PROMPT` (from constants) |
| `subagent_server/server.py` | `READONLY_PERMISSION_PROMPT` (from constants); `load_agent`, `get_provider_for_model`, `run_subagent` (from subagent); `TaskStatus`, `TaskNotFoundError`, `InvalidTransitionError`, `TaskEngine`, `LockManager` (from task_engine); `safe_read_text` (from utils) |
| `team_cli.py` | `TeamCoordinator`, `TeamSession`, `TeamMember`, `MemberStatus`, `TeamStatus` (from team) |
| `protocol/tests/test_providers.py` | `get_provider_for_model` (from subagent) |
| `protocol/a2a/executors/gemini_executor.py` | `run_subagent` as `_default_run_subagent` (from subagent) |
| `protocol/a2a/tests/test_french_novel_relay.py` | `TeamCoordinator`, `extract_artifact_text` (from team) |

**De facto public API of `vaultspec.orchestration`:**
- From `subagent.py`: `AgentNotFoundError`, `load_agent`, `get_provider_for_model`, `run_subagent`
- From `task_engine.py`: `TaskStatus`, `SubagentTask`, `FileLock`, `TaskNotFoundError`, `InvalidTransitionError`, `generate_task_id`, `LockManager`, `TaskEngine`, `is_terminal`
- From `team.py`: `MemberStatus`, `TeamStatus`, `TeamMember`, `TeamSession`, `TeamCoordinator`, `extract_artifact_text`
- From `session_logger.py`: `SessionLogger`, `cleanup_old_logs`
- From `utils.py`: `SecurityError`, `find_project_root`, `safe_read_text`
- From `constants.py`: `READONLY_PERMISSION_PROMPT`

### 3F. Proposed `__all__`

**`subagent.py`:**
```python
__all__ = [
    "AgentNotFoundError",
    "load_agent",
    "get_provider_for_model",
    "run_subagent",
]
```

**`task_engine.py`:**
```python
__all__ = [
    "TaskStatus",
    "is_terminal",
    "SubagentTask",
    "FileLock",
    "TaskNotFoundError",
    "InvalidTransitionError",
    "generate_task_id",
    "LockManager",
    "TaskEngine",
]
```

**`team.py`:**
```python
__all__ = [
    "MemberStatus",
    "TeamStatus",
    "TeamMember",
    "TeamSession",
    "extract_artifact_text",
    "TeamCoordinator",
]
```

**`session_logger.py`:**
```python
__all__ = ["SessionLogger", "cleanup_old_logs"]
```

**`utils.py`:**
```python
__all__ = ["SecurityError", "find_project_root", "safe_read_text"]
```

**`constants.py`:**
```python
__all__ = ["READONLY_PERMISSION_PROMPT"]
```

### 3G. Proposed `__init__.py` re-exports

Due to the heavy third-party dependencies in `subagent.py` and `team.py` (`acp`, `a2a`, `httpx`), eager re-exports in `__init__.py` would force every consumer to have these packages installed even if they only need `task_engine` or `utils`. **A selective approach is recommended:**

```python
"""Agent orchestration: subagent dispatch, task engine, team coordination."""

from vaultspec.orchestration.constants import READONLY_PERMISSION_PROMPT
from vaultspec.orchestration.session_logger import SessionLogger, cleanup_old_logs
from vaultspec.orchestration.task_engine import (
    InvalidTransitionError,
    LockManager,
    SubagentTask,
    TaskEngine,
    TaskNotFoundError,
    TaskStatus,
    generate_task_id,
    is_terminal,
)
from vaultspec.orchestration.utils import SecurityError, find_project_root, safe_read_text

__all__ = [
    # constants
    "READONLY_PERMISSION_PROMPT",
    # session_logger
    "SessionLogger",
    "cleanup_old_logs",
    # task_engine
    "TaskStatus",
    "is_terminal",
    "SubagentTask",
    "TaskNotFoundError",
    "InvalidTransitionError",
    "generate_task_id",
    "LockManager",
    "TaskEngine",
    # utils
    "SecurityError",
    "find_project_root",
    "safe_read_text",
]
```

**Omitted from `__init__.py`:** `subagent.py` (depends on `acp` SDK) and `team.py` (depends on `a2a`, `httpx`). These should remain as explicit deep imports (`from vaultspec.orchestration.subagent import run_subagent`) to keep the package importable without heavy optional dependencies.

### 3H. Circular import risk

**Medium risk in `subagent.py`.** This module has top-level imports from `vaultspec.protocol.acp.client`, `vaultspec.protocol.providers.claude`, and `vaultspec.protocol.providers.gemini`. If any of those modules imports from `vaultspec.orchestration` at the top level, a cycle would form.

Current state:
- `protocol/a2a/executors/gemini_executor.py` imports `run_subagent` from `orchestration.subagent` -- but this is a different module path than what `subagent.py` imports from `protocol.providers.gemini`.
- No direct cycle exists today, but the bidirectional dependency between `orchestration` and `protocol` is a latent risk.

**Mitigation:** The proposed `__init__.py` above deliberately excludes `subagent.py` and `team.py`, preventing their top-level imports from executing at package-init time. This is the correct defensive posture.

---

## 4. Cross-package dependency summary

```
vaultspec.core (leaf -- no vaultspec.* imports)
    ^
    |  (get_config, reset_config, WorkspaceLayout, resolve_workspace)
    |
    +-- vaultspec.vaultcore (depends on core only, all deferred)
    |       ^
    |       |  (DocType, parse_frontmatter, parse_vault_metadata,
    |       |   scan_vault, get_doc_type, extract_*_links,
    |       |   hydrate_template, get_template_path)
    |       |
    |       +-- vaultspec.orchestration.subagent (parse_frontmatter)
    |
    +-- vaultspec.orchestration.task_engine (get_config, deferred)
    +-- vaultspec.orchestration.session_logger (get_config, top-level)
    +-- vaultspec.orchestration.subagent (get_config, deferred)
```

The dependency graph is acyclic. `core` is the foundation, `vaultcore` sits above it, and `orchestration` modules consume from both. The only structural concern is the top-level import of `get_config` in `session_logger.py` -- all other cross-package imports from `core` are deferred.
