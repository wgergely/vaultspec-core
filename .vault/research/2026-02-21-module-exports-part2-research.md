---
tags:
  - "#research"
  - "#module-exports"
date: "2026-02-21"
related:
  - "[[2026-02-21-packaging-restructure-adr]]"
---

# `module-exports` research: protocol, rag, hooks

Exhaustive audit of the import/export structure of three packages under `src/vaultspec/`: `protocol`, `rag`, and `hooks`. This research catalogs every public symbol, every cross-package import, every intra-package import, and proposes `__all__` and `__init__.py` re-exports for each module.

## Findings

---

## 1. `vaultspec.protocol`

A deep hierarchy with four sub-packages: `providers`, `acp`, `a2a`, and `a2a.executors`.

### 1.1 `protocol/__init__.py`

**Contents:** Empty (blank file, 1 line).

No re-exports. No `__all__`.

### 1.2 `protocol/sandbox.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `_WRITE_TOOLS` | `frozenset` constant | Private (underscore) |
| `_SHELL_TOOLS` | `frozenset` constant | Private (underscore) |
| `_is_vault_path` | function | Private (underscore) |
| `_make_sandbox_callback` | function | Private (underscore) |

**External imports:** `claude_agent_sdk.types` (`PermissionResultAllow`, `PermissionResultDeny`, `ToolPermissionContext`)

**Cross-package imports:** None.

**Intra-package imports:** None.

### 1.3 `protocol/providers/__init__.py`

**Contents:** Re-exports from `base.py`:

```python
from .base import CapabilityLevel, ClaudeModels, GeminiModels, ModelRegistry
__all__ = ["CapabilityLevel", "ClaudeModels", "GeminiModels", "ModelRegistry"]
```

### 1.4 `protocol/providers/base.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `CapabilityLevel` | `IntEnum` class | Public |
| `ClaudeModels` | class (model registry) | Public |
| `GeminiModels` | class (model registry) | Public |
| `ModelRegistry` | type alias | Public |
| `ProcessSpec` | `@dataclass` | Public |
| `resolve_includes` | function | Public |
| `resolve_executable` | function | Public |
| `AgentProvider` | ABC class | Public |

**Cross-package imports:** None (stdlib only).

**Intra-package imports:** None.

### 1.5 `protocol/providers/claude.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `_load_claude_oauth_token` | function | Private |
| `ClaudeProvider` | class (extends `AgentProvider`) | Public |
| `_GEMINI_ONLY_FEATURES` | tuple constant | Private |
| `_DEFAULT_CREDS_PATH` | constant | Private |
| `_DEFAULT_TOKEN_URL` | constant | Private |
| `_EXPIRY_BUFFER_SECONDS` | constant | Private |

**Intra-package imports:** `from .base import AgentProvider, CapabilityLevel, ClaudeModels, ModelRegistry, ProcessSpec, resolve_includes`

**Cross-package imports:** None.

### 1.6 `protocol/providers/gemini.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `_load_gemini_oauth_creds` | function | Private |
| `_refresh_gemini_oauth_token` | function | Private |
| `_is_gemini_token_expired` | function | Private |
| `GeminiProvider` | class (extends `AgentProvider`) | Public |
| `_CLAUDE_ONLY_FEATURES` | tuple constant | Private |
| `_MIN_VERSION_WINDOWS` | constant | Private |
| `_MIN_VERSION_RECOMMENDED` | constant | Private |

**Intra-package imports:** `from .base import AgentProvider, CapabilityLevel, GeminiModels, ModelRegistry, ProcessSpec, resolve_executable, resolve_includes`

**Cross-package imports:** `from vaultspec.core.config import get_config` (inside `prepare_process`)

### 1.7 `protocol/acp/__init__.py`

**Contents:** Empty (blank file, 1 line).

### 1.8 `protocol/acp/types.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `SubagentError` | Exception class | Public |
| `SubagentResult` | frozen `@dataclass` | Public |

**Cross-package imports:** None.

**Intra-package imports:** None.

### 1.9 `protocol/acp/client.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `SessionLogger` | class | Public |
| `_Terminal` | class | Private |
| `SubagentClient` | class (extends `acp.interfaces.Client`) | Public |

**External imports:** `acp.interfaces.Client`, `acp.schema` (many types)

**Cross-package imports:** `from vaultspec.core.config import get_config` (inside methods)

**Intra-package imports:** None.

### 1.10 `protocol/acp/claude_bridge.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `_convert_mcp_servers` | function | Private |
| `_extract_prompt_text` | function | Private |
| `_SessionState` | `@dataclass` | Private |
| `ClaudeACPBridge` | class (ACP Agent) | Public |
| `main` | async function | Public |

**External imports:** `acp` (`PROTOCOL_VERSION`, `run_agent`, many `acp.schema` types), `claude_agent_sdk` (many types), `claude_agent_sdk.types` (`McpStdioServerConfig`, `StreamEvent`)

**Cross-package imports (vaultspec):**
- `from vaultspec.logging_config import configure_logging`
- `from vaultspec.protocol.providers.base import ClaudeModels`
- `from vaultspec.protocol.sandbox import _make_sandbox_callback`
- `from vaultspec.core.config import get_config` (inside `__init__`)

**Intra-package imports:** Uses symbols from sibling sub-packages within `protocol.*`.

### 1.11 `protocol/a2a/__init__.py`

**Contents:** Module docstring only, no imports, no re-exports.

### 1.12 `protocol/a2a/server.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `create_app` | function | Public |

**External imports:** `a2a.server.apps.A2AStarletteApplication`, `a2a.server.request_handlers.DefaultRequestHandler`, `a2a.server.tasks.InMemoryTaskStore`

**Cross-package imports:** None (TYPE_CHECKING only: `a2a.server.agent_execution.AgentExecutor`, `a2a.types.AgentCard`, `starlette.applications.Starlette`).

### 1.13 `protocol/a2a/discovery.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `generate_agent_md` | function | Public |
| `write_agent_discovery` | function | Public |
| `write_gemini_settings` | function | Public |

**Cross-package imports:** `from vaultspec.core.config import get_config` (inside `write_agent_discovery`)

### 1.14 `protocol/a2a/agent_card.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `agent_card_from_definition` | function | Public |

**External imports:** `a2a.types` (`AgentCapabilities`, `AgentCard`, `AgentSkill`)

**Cross-package imports:** `from vaultspec.core.config import get_config` (inside function)

### 1.15 `protocol/a2a/state_map.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `VAULTSPEC_TO_A2A` | dict constant | Public |
| `A2A_TO_VAULTSPEC` | dict constant | Public |

**External imports:** `a2a.types.TaskState`

**Cross-package imports:** None.

### 1.16 `protocol/a2a/executors/__init__.py`

**Contents:** Empty (blank file, 1 line).

### 1.17 `protocol/a2a/executors/base.py`

**Contents:** Re-exports from `protocol.sandbox`:

```python
from vaultspec.protocol.sandbox import (
    _SHELL_TOOLS, _WRITE_TOOLS, _is_vault_path, _make_sandbox_callback,
)
__all__ = ["_SHELL_TOOLS", "_WRITE_TOOLS", "_is_vault_path", "_make_sandbox_callback"]
```

### 1.18 `protocol/a2a/executors/claude_executor.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `_default_client_factory` | function | Private |
| `_default_options_factory` | function | Private |
| `ClaudeA2AExecutor` | class (extends `AgentExecutor`) | Public |

**External imports:** `a2a.server.agent_execution` (`AgentExecutor`, `RequestContext`), `a2a.server.tasks.TaskUpdater`, `a2a.types` (`Part`, `TextPart`), `claude_agent_sdk` (multiple), `claude_agent_sdk._errors.MessageParseError`

**Intra-package imports:** `from vaultspec.protocol.a2a.executors.base import _make_sandbox_callback`

### 1.19 `protocol/a2a/executors/gemini_executor.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `GeminiA2AExecutor` | class (extends `AgentExecutor`) | Public |

**Cross-package imports:**
- `from vaultspec.orchestration.subagent import run_subagent as _default_run_subagent`
- `from vaultspec.protocol.providers.base import GeminiModels`

---

### Protocol: Cross-Package Consumers (production code only, excluding tests)

| Consumer Module | Imports From | Symbols |
|---|---|---|
| `cli.py` | `protocol.providers.claude` | `ClaudeProvider` |
| `cli.py` | `protocol.providers.gemini` | `GeminiProvider` |
| `cli.py` | `protocol.providers.base` | `CapabilityLevel` |
| `subagent_cli.py` | `protocol.acp.client` | `SubagentClient` |
| `subagent_cli.py` | `protocol.providers.base` | `ClaudeModels`, `GeminiModels` |
| `subagent_cli.py` | `protocol.a2a.agent_card` | `agent_card_from_definition` |
| `subagent_cli.py` | `protocol.a2a.server` | `create_app` |
| `subagent_cli.py` | `protocol.a2a.executors.claude_executor` | `ClaudeA2AExecutor` |
| `subagent_cli.py` | `protocol.a2a.executors.gemini_executor` | `GeminiA2AExecutor` |
| `orchestration.subagent` | `protocol.acp.client` | `SessionLogger`, `SubagentClient` |
| `orchestration.subagent` | `protocol.acp.types` | `SubagentError`, `SubagentResult` |
| `orchestration.subagent` | `protocol.providers.claude` | `ClaudeProvider` |
| `orchestration.subagent` | `protocol.providers.gemini` | `GeminiProvider` |
| `orchestration.subagent` | `protocol.providers.base` | `AgentProvider` (TYPE_CHECKING) |
| `subagent_server.server` | `protocol.acp.types` | `SubagentError` |

### Protocol: Intra-Package Import Graph

| Module | Imports From | Symbols |
|---|---|---|
| `providers/claude.py` | `providers/base.py` | `AgentProvider`, `CapabilityLevel`, `ClaudeModels`, `ModelRegistry`, `ProcessSpec`, `resolve_includes` |
| `providers/gemini.py` | `providers/base.py` | `AgentProvider`, `CapabilityLevel`, `GeminiModels`, `ModelRegistry`, `ProcessSpec`, `resolve_executable`, `resolve_includes` |
| `acp/claude_bridge.py` | `providers/base.py` | `ClaudeModels` |
| `acp/claude_bridge.py` | `sandbox.py` | `_make_sandbox_callback` |
| `a2a/executors/base.py` | `sandbox.py` | `_SHELL_TOOLS`, `_WRITE_TOOLS`, `_is_vault_path`, `_make_sandbox_callback` |
| `a2a/executors/claude_executor.py` | `a2a/executors/base.py` | `_make_sandbox_callback` |
| `a2a/executors/gemini_executor.py` | `providers/base.py` | `GeminiModels` |

### Protocol: Proposed `__all__` per Module

**`protocol/sandbox.py`**
```python
__all__ = ["_WRITE_TOOLS", "_SHELL_TOOLS", "_is_vault_path", "_make_sandbox_callback"]
```

Note: All symbols are underscore-prefixed but are consumed by other sub-packages. Consider renaming to remove underscores if they are part of the public internal API, or accept the convention that these are "package-private" symbols shared across the `protocol` tree.

**`protocol/providers/base.py`**
```python
__all__ = [
    "AgentProvider", "CapabilityLevel", "ClaudeModels", "GeminiModels",
    "ModelRegistry", "ProcessSpec", "resolve_includes", "resolve_executable",
]
```

**`protocol/providers/claude.py`**
```python
__all__ = ["ClaudeProvider"]
```

**`protocol/providers/gemini.py`**
```python
__all__ = ["GeminiProvider"]
```

**`protocol/acp/types.py`**
```python
__all__ = ["SubagentError", "SubagentResult"]
```

**`protocol/acp/client.py`**
```python
__all__ = ["SessionLogger", "SubagentClient"]
```

**`protocol/acp/claude_bridge.py`**
```python
__all__ = ["ClaudeACPBridge"]
```

**`protocol/a2a/server.py`**
```python
__all__ = ["create_app"]
```

**`protocol/a2a/discovery.py`**
```python
__all__ = ["generate_agent_md", "write_agent_discovery", "write_gemini_settings"]
```

**`protocol/a2a/agent_card.py`**
```python
__all__ = ["agent_card_from_definition"]
```

**`protocol/a2a/state_map.py`**
```python
__all__ = ["VAULTSPEC_TO_A2A", "A2A_TO_VAULTSPEC"]
```

**`protocol/a2a/executors/claude_executor.py`**
```python
__all__ = ["ClaudeA2AExecutor"]
```

**`protocol/a2a/executors/gemini_executor.py`**
```python
__all__ = ["GeminiA2AExecutor"]
```

### Protocol: Proposed `__init__.py` Re-Exports

**`protocol/__init__.py`** -- Should re-export the most commonly consumed top-level symbols:
```python
from vaultspec.protocol.sandbox import _make_sandbox_callback
from vaultspec.protocol.providers.base import (
    AgentProvider, CapabilityLevel, ClaudeModels, GeminiModels,
    ModelRegistry, ProcessSpec,
)
from vaultspec.protocol.providers.claude import ClaudeProvider
from vaultspec.protocol.providers.gemini import GeminiProvider
from vaultspec.protocol.acp.types import SubagentError, SubagentResult
from vaultspec.protocol.acp.client import SessionLogger, SubagentClient

__all__ = [
    "AgentProvider", "CapabilityLevel", "ClaudeModels", "ClaudeProvider",
    "GeminiModels", "GeminiProvider", "ModelRegistry", "ProcessSpec",
    "SessionLogger", "SubagentClient", "SubagentError", "SubagentResult",
]
```

**`protocol/acp/__init__.py`**:
```python
from vaultspec.protocol.acp.types import SubagentError, SubagentResult
from vaultspec.protocol.acp.client import SessionLogger, SubagentClient
from vaultspec.protocol.acp.claude_bridge import ClaudeACPBridge

__all__ = [
    "ClaudeACPBridge", "SessionLogger", "SubagentClient",
    "SubagentError", "SubagentResult",
]
```

**`protocol/a2a/__init__.py`**:
```python
from vaultspec.protocol.a2a.server import create_app
from vaultspec.protocol.a2a.agent_card import agent_card_from_definition
from vaultspec.protocol.a2a.discovery import (
    generate_agent_md, write_agent_discovery, write_gemini_settings,
)
from vaultspec.protocol.a2a.state_map import A2A_TO_VAULTSPEC, VAULTSPEC_TO_A2A

__all__ = [
    "A2A_TO_VAULTSPEC", "VAULTSPEC_TO_A2A",
    "agent_card_from_definition", "create_app",
    "generate_agent_md", "write_agent_discovery", "write_gemini_settings",
]
```

**`protocol/a2a/executors/__init__.py`**:
```python
from vaultspec.protocol.a2a.executors.claude_executor import ClaudeA2AExecutor
from vaultspec.protocol.a2a.executors.gemini_executor import GeminiA2AExecutor

__all__ = ["ClaudeA2AExecutor", "GeminiA2AExecutor"]
```

### Protocol: Circular Import Risks

- **`a2a/executors/gemini_executor.py`** imports `vaultspec.orchestration.subagent.run_subagent` at module level. The `orchestration.subagent` module imports from `vaultspec.protocol.providers.*` and `vaultspec.protocol.acp.*`. This creates a **bidirectional dependency** between `protocol` and `orchestration`. Currently safe because both sides use top-level imports of different sub-modules, but it is fragile. If `protocol/__init__.py` were to eagerly import `a2a.executors`, it would trigger the cycle.

- **`acp/claude_bridge.py`** and **`acp/client.py`** both import `vaultspec.core.config.get_config` inside methods (lazy), which is safe.

- **No circular imports within the `protocol` package itself.** All intra-package imports flow downward: `claude_bridge` -> `providers/base` + `sandbox`; `executors/*` -> `executors/base` -> `sandbox`; `providers/claude|gemini` -> `providers/base`.

---

## 2. `vaultspec.rag`

### 2.1 `rag/__init__.py`

**Contents:** Empty (blank file, 1 line).

No re-exports. No `__all__`.

### 2.2 `rag/api.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `VaultRAG` | class (singleton engine) | Public |
| `_engine` | module-level singleton | Private |
| `_engine_lock` | `threading.Lock` | Private |
| `reset_engine` | function | Public |
| `get_engine` | function | Public |
| `list_documents` | function | Public |
| `get_document` | function | Public |
| `get_related` | function | Public |
| `get_status` | function | Public |
| `index` | function | Public |
| `search` | function | Public |

**Intra-package imports (lazy, inside methods/properties):**
- `from vaultspec.rag.embeddings import EmbeddingModel` (TYPE_CHECKING + lazy)
- `from vaultspec.rag.indexer import IndexResult, VaultIndexer` (TYPE_CHECKING + lazy)
- `from vaultspec.rag.search import SearchResult, VaultSearcher` (TYPE_CHECKING + lazy)
- `from vaultspec.rag.store import VaultStore` (TYPE_CHECKING + lazy)
- `from vaultspec.rag.embeddings import _require_cuda` (lazy)
- `from vaultspec.rag.embeddings import get_device_info` (lazy)

**Cross-package imports:**
- `from vaultspec.vaultcore.models import DocType`
- `from vaultspec.vaultcore.parser import parse_vault_metadata`
- `from vaultspec.vaultcore.scanner import get_doc_type, scan_vault`
- `from vaultspec.graph.api import VaultGraph`
- `from vaultspec.metrics.api import get_vault_metrics`
- `from vaultspec.verification.api import list_features`
- `from vaultspec.core.config import get_config`

### 2.3 `rag/embeddings.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `CUDA_INDEX_TAG` | string constant | Public |
| `CUDA_INDEX_URL` | string constant | Public |
| `GPUNotAvailableError` | Exception class | Public |
| `_check_rag_deps` | function | Private |
| `_require_cuda` | function | Private |
| `get_device_info` | function | Public |
| `EmbeddingModel` | class | Public |

**Cross-package imports:** `from vaultspec.core.config import get_config` (inside methods)

**Intra-package imports:** None.

### 2.4 `rag/indexer.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `IndexResult` | `@dataclass` | Public |
| `_extract_title` | function | Private |
| `_extract_feature` | function | Private |
| `prepare_document` | function | Public |
| `VaultIndexer` | class | Public |

**Intra-package imports:**
- `from vaultspec.rag.embeddings import EmbeddingModel` (TYPE_CHECKING)
- `from vaultspec.rag.store import VaultStore` (TYPE_CHECKING)
- `from vaultspec.rag.store import VaultDocument` (runtime)

**Cross-package imports:**
- `from vaultspec.vaultcore.models import DocType`
- `from vaultspec.vaultcore.parser import parse_vault_metadata`
- `from vaultspec.vaultcore.scanner import get_doc_type, scan_vault`
- `from vaultspec.core.config import get_config`

### 2.5 `rag/search.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `_FILTER_PATTERN` | compiled regex | Private |
| `_FILTER_KEY_MAP` | dict constant | Private |
| `ParsedQuery` | `@dataclass` | Public |
| `SearchResult` | `@dataclass` | Public |
| `parse_query` | function | Public |
| `rerank_with_graph` | function | Public |
| `VaultSearcher` | class | Public |

**Intra-package imports (TYPE_CHECKING):**
- `from vaultspec.rag.embeddings import EmbeddingModel`
- `from vaultspec.rag.store import VaultStore`

**Cross-package imports:**
- `from vaultspec.graph.api import VaultGraph` (TYPE_CHECKING + lazy inside `rerank_with_graph` and `_get_graph`)
- `from vaultspec.core.config import get_config`

### 2.6 `rag/store.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `EMBEDDING_DIM` | int constant | Public |
| `_check_rag_deps` | function | Private |
| `_sanitize_filter_value` | function | Private |
| `_parse_json_list` | function | Private |
| `VaultDocument` | `@dataclass` | Public |
| `VaultStore` | class | Public |

**Cross-package imports:** `from vaultspec.core.config import get_config` (inside `__init__`)

**Intra-package imports:** None.

### RAG: Cross-Package Consumers (production code only)

| Consumer Module | Imports From | Symbols |
|---|---|---|
| `vault_cli.py` | `rag.api` | `index` |
| `vault_cli.py` | `rag.embeddings` | `get_device_info` |
| `vault_cli.py` | `rag.api` | `search` |

The `rag` package is consumed exclusively by `vault_cli.py` in production. All other access is internal (intra-package) or from tests.

### RAG: Intra-Package Import Graph

```
api.py ──(lazy)──> embeddings.py
api.py ──(lazy)──> store.py
api.py ──(lazy)──> indexer.py
api.py ──(lazy)──> search.py

indexer.py ──(runtime)──> store.py (VaultDocument)
indexer.py ──(TYPE_CHECKING)──> embeddings.py, store.py

search.py ──(TYPE_CHECKING)──> embeddings.py, store.py
```

All intra-package imports are either lazy (inside method bodies) or under `TYPE_CHECKING`. This is a deliberate pattern to avoid importing heavy dependencies (torch, sentence-transformers, lancedb) at module load time.

### RAG: Proposed `__all__` per Module

**`rag/api.py`**
```python
__all__ = [
    "VaultRAG", "get_engine", "reset_engine",
    "list_documents", "get_document", "get_related", "get_status",
    "index", "search",
]
```

**`rag/embeddings.py`**
```python
__all__ = [
    "CUDA_INDEX_TAG", "CUDA_INDEX_URL",
    "GPUNotAvailableError", "EmbeddingModel", "get_device_info",
]
```

**`rag/indexer.py`**
```python
__all__ = ["IndexResult", "VaultIndexer", "prepare_document"]
```

**`rag/search.py`**
```python
__all__ = [
    "ParsedQuery", "SearchResult", "VaultSearcher",
    "parse_query", "rerank_with_graph",
]
```

**`rag/store.py`**
```python
__all__ = ["EMBEDDING_DIM", "VaultDocument", "VaultStore"]
```

### RAG: Proposed `__init__.py` Re-Exports

**`rag/__init__.py`** -- Should expose the public API facade and the key types needed by callers:
```python
from vaultspec.rag.api import (
    VaultRAG,
    get_document,
    get_engine,
    get_related,
    get_status,
    index,
    list_documents,
    reset_engine,
    search,
)
from vaultspec.rag.embeddings import GPUNotAvailableError
from vaultspec.rag.indexer import IndexResult
from vaultspec.rag.search import SearchResult
from vaultspec.rag.store import VaultDocument

__all__ = [
    "GPUNotAvailableError", "IndexResult", "SearchResult",
    "VaultDocument", "VaultRAG",
    "get_document", "get_engine", "get_related", "get_status",
    "index", "list_documents", "reset_engine", "search",
]
```

**Important caveat:** The `rag` package uses aggressive lazy loading to avoid pulling in torch/lancedb at import time. Any `__init__.py` re-exports must use lazy import patterns (e.g., `TYPE_CHECKING` guards or module-level `__getattr__`) to preserve this behavior. A naive `from vaultspec.rag.store import VaultDocument` in `__init__.py` would trigger `lancedb` import immediately. The proposed re-exports above are **aspirational** -- actual implementation should use `__getattr__`-based lazy loading or restrict `__init__.py` to only re-exporting types that have no heavy dependencies (like `IndexResult`, `SearchResult`, `GPUNotAvailableError`).

### RAG: Circular Import Risks

- **No circular imports.** The import graph is acyclic: `api` -> `{embeddings, store, indexer, search}`, `indexer` -> `store`, `search` -> nothing at runtime. All heavy cross-references use `TYPE_CHECKING`.

- **Cross-package dependency fan-out is wide but uni-directional.** `rag.api` depends on `vaultcore`, `graph`, `metrics`, `verification`, and `core.config`. None of those packages depend on `rag`. Safe.

---

## 3. `vaultspec.hooks`

### 3.1 `hooks/__init__.py`

**Contents:** Module docstring only, no imports, no re-exports.

### 3.2 `hooks/engine.py`

| Symbol | Kind | Visibility |
|---|---|---|
| `SUPPORTED_EVENTS` | `frozenset` constant | Public |
| `HookAction` | `@dataclass` | Public |
| `Hook` | `@dataclass` | Public |
| `HookResult` | `@dataclass` | Public |
| `_parse_yaml` | function | Private |
| `load_hooks` | function | Public |
| `_parse_hook` | function | Private |
| `_parse_action` | function | Private |
| `trigger` | function | Public |
| `_interpolate` | function | Private |
| `_execute_action` | function | Private |
| `_execute_shell` | function | Private |
| `_execute_agent` | function | Private |

**Cross-package imports:** `from vaultspec.core.config import get_config` (inside `_execute_agent`)

**Intra-package imports:** None.

### Hooks: Cross-Package Consumers (production code only)

| Consumer Module | Imports From | Symbols |
|---|---|---|
| `cli.py` | `hooks.engine` | `SUPPORTED_EVENTS`, `load_hooks` |
| `cli.py` | `hooks.engine` | `SUPPORTED_EVENTS`, `load_hooks`, `trigger` |

The `hooks` package is consumed exclusively by `cli.py`.

### Hooks: Proposed `__all__` for `engine.py`

```python
__all__ = [
    "SUPPORTED_EVENTS", "Hook", "HookAction", "HookResult",
    "load_hooks", "trigger",
]
```

### Hooks: Proposed `__init__.py` Re-Exports

**`hooks/__init__.py`**:
```python
from vaultspec.hooks.engine import (
    SUPPORTED_EVENTS,
    Hook,
    HookAction,
    HookResult,
    load_hooks,
    trigger,
)

__all__ = [
    "SUPPORTED_EVENTS", "Hook", "HookAction", "HookResult",
    "load_hooks", "trigger",
]
```

### Hooks: Circular Import Risks

- **None.** `hooks.engine` imports only from `vaultspec.core.config` (lazy, inside a function body). No other package imports from `hooks` at module level. The `cli.py` imports are inside command handler functions (lazy).

---

## Summary of Structural Observations

- **All three packages have empty or near-empty `__init__.py` files.** No package currently defines `__all__` at the package level or re-exports symbols, forcing consumers to import from deep paths like `vaultspec.protocol.acp.types.SubagentResult`.

- **No module-level `__all__` in any production module** except `protocol/providers/__init__.py` and `protocol/a2a/executors/base.py`.

- **The `protocol` package is the most widely consumed** (by `cli`, `subagent_cli`, `orchestration`, `subagent_server`). Its deep hierarchy means consumers must know exact sub-module paths.

- **The `rag` package uses a disciplined lazy-import pattern** to avoid loading heavy ML dependencies. Any `__init__.py` re-exports must preserve this.

- **The `hooks` package is the simplest** -- a single module (`engine.py`) with no intra-package dependencies and only one consumer (`cli.py`).

- **One cross-package bidirectional dependency exists**: `protocol.a2a.executors.gemini_executor` -> `orchestration.subagent` -> `protocol.*`. Currently safe due to lazy imports but should be documented as a known coupling point.
