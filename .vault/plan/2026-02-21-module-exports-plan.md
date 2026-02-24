---
tags:
  - "#plan"
  - "#module-exports"
date: "2026-02-21"
related:
  - "[[2026-02-21-module-exports-adr]]"
  - "[[2026-02-21-module-exports-part1-research]]"
  - "[[2026-02-21-module-exports-part2-research]]"
  - "[[2026-02-21-module-exports-part3-research]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `module-exports` plan

Add `__all__` declarations to every production module, populate `__init__.py` files with re-exports (eager, selective, or lazy per [[2026-02-21-module-exports-adr]]), convert intra-package imports to relative form, and rewrite all consumers to use package-level imports. The refactor touches approximately 384 import statements across the entire `src/vaultspec/` tree and `tests/` directory.

## Proposed Changes

The [[2026-02-21-module-exports-adr]] mandates three re-export strategies based on package characteristics:

- **Eager re-export** (default): `__init__.py` imports from sub-modules at package load time. Applies to `core/`, `vaultcore/`, `hooks/`, `graph/`, `metrics/`, `verification/`, `subagent_server/`, `mcp_tools/`.
- **Selective re-export**: `__init__.py` eagerly re-exports only modules with stdlib-only dependencies. Applies to `orchestration/` -- `subagent.py` and `team.py` are excluded from `__init__.py` because they pull in `acp`, `a2a-sdk`, and `httpx`.
- **Lazy re-export**: `__init__.py` uses `__getattr__`-based lazy loading to avoid importing torch/lancedb at package load time. Applies exclusively to `rag/`.

Each phase follows the same mechanical pattern: (1) add `__all__` to every module listing public symbols, (2) populate `__init__.py` with re-exports using relative imports, (3) convert intra-package imports to relative form, (4) rewrite all consumers to use package-level imports.

Execution order follows the dependency DAG bottom-up so each phase can be verified independently. The specific `__all__` symbol lists are documented in [[2026-02-21-module-exports-part1-research]], [[2026-02-21-module-exports-part2-research]], and [[2026-02-21-module-exports-part3-research]].

## Tasks

<!-- IMPORTANT: This document must be updated between execution runs to
     track progress. -->

- **Wave 1** -- Phase 1: Leaf packages `core/`, `vaultcore/`, `hooks/` (1 agent, sequential)

    1. **Step 1**: Add `__all__` and `__init__.py` re-exports for `core/`, `vaultcore/`, `hooks/`
        - Name: Leaf package `__all__` and `__init__.py` re-exports
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave1-step1.md`
        - Executing sub-agent: vaultspec-standard-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part1-research]], [[2026-02-21-module-exports-part2-research]]
        - Dependencies: none
        - Affected files:
            - `src/vaultspec/core/config.py` -- add `__all__` with 8 symbols (see part1 section 1F)
            - `src/vaultspec/core/workspace.py` -- add `__all__` with 6 symbols (see part1 section 1F)
            - `src/vaultspec/core/__init__.py` -- eager re-export: `VaultSpecConfig`, `get_config`, `reset_config`, `WorkspaceLayout`, `resolve_workspace` using relative imports
            - `src/vaultspec/vaultcore/models.py` -- add `__all__` with 3 symbols
            - `src/vaultspec/vaultcore/parser.py` -- add `__all__` with 2 symbols
            - `src/vaultspec/vaultcore/scanner.py` -- add `__all__` with 2 symbols
            - `src/vaultspec/vaultcore/links.py` -- add `__all__` with 2 symbols
            - `src/vaultspec/vaultcore/hydration.py` -- add `__all__` with 2 symbols
            - `src/vaultspec/vaultcore/__init__.py` -- eager re-export all 11 public symbols using relative imports
            - `src/vaultspec/hooks/engine.py` -- add `__all__` with 6 symbols
            - `src/vaultspec/hooks/__init__.py` -- eager re-export: `SUPPORTED_EVENTS`, `Hook`, `HookAction`, `HookResult`, `load_hooks`, `trigger` using relative imports
        - Intra-package relative import conversions within `vaultcore/`:
            - `parser.py`: `from vaultspec.vaultcore.models import DocumentMetadata` -> `from .models import DocumentMetadata`
            - `scanner.py`: `from vaultspec.vaultcore.models import DocType` -> `from .models import DocType`
            - `hydration.py`: `from vaultspec.vaultcore.models import DocType` -> `from .models import DocType`

    2. **Step 2**: Rewrite all consumers of `core/`, `vaultcore/`, `hooks/` to use package-level imports
        - Name: Leaf package consumer rewrite
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave1-step2.md`
        - Executing sub-agent: vaultspec-standard-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part1-research]]
        - Dependencies: Step 1
        - Rewrite patterns (production code, excluding tests):
            - `from vaultspec.core.config import get_config` -> `from vaultspec.core import get_config`
            - `from vaultspec.core.config import VaultSpecConfig` -> `from vaultspec.core import VaultSpecConfig`
            - `from vaultspec.core.config import reset_config` -> `from vaultspec.core import reset_config`
            - `from vaultspec.core.workspace import WorkspaceLayout, resolve_workspace` -> `from vaultspec.core import WorkspaceLayout, resolve_workspace`
            - `from vaultspec.vaultcore.models import DocType` -> `from vaultspec.vaultcore import DocType`
            - `from vaultspec.vaultcore.parser import parse_frontmatter` -> `from vaultspec.vaultcore import parse_frontmatter`
            - `from vaultspec.vaultcore.parser import parse_vault_metadata` -> `from vaultspec.vaultcore import parse_vault_metadata`
            - `from vaultspec.vaultcore.scanner import scan_vault, get_doc_type` -> `from vaultspec.vaultcore import scan_vault, get_doc_type`
            - `from vaultspec.vaultcore.links import extract_wiki_links, extract_related_links` -> `from vaultspec.vaultcore import extract_wiki_links, extract_related_links`
            - `from vaultspec.vaultcore.hydration import hydrate_template, get_template_path` -> `from vaultspec.vaultcore import hydrate_template, get_template_path`
            - `from vaultspec.hooks.engine import ...` -> `from vaultspec.hooks import ...`
        - Affected files: all production `.py` files under `src/vaultspec/` that import from `core/`, `vaultcore/`, or `hooks/` (approximately 25+ consumer files per part1 research sections 1E, 2E, and part2 section 3)

- **Wave 2** -- Phases 2+3: Mid-tier analytics + RAG (2 agents in parallel)

    3. **Step 3** (Agent A): Add `__all__`, `__init__.py` re-exports for `graph/`, `metrics/`, `verification/` and rewrite their consumers
        - Name: Analytics packages `__all__` + re-exports + consumer rewrite
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave2-step3.md`
        - Executing sub-agent: vaultspec-standard-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part3-research]]
        - Dependencies: Steps 1-2
        - Affected files:
            - `src/vaultspec/graph/api.py` -- add `__all__`: `["DocNode", "VaultGraph"]`
            - `src/vaultspec/graph/__init__.py` -- eager re-export `DocNode`, `VaultGraph`
            - `src/vaultspec/metrics/api.py` -- add `__all__`: `["VaultSummary", "get_vault_metrics"]`
            - `src/vaultspec/metrics/__init__.py` -- eager re-export `VaultSummary`, `get_vault_metrics`
            - `src/vaultspec/verification/api.py` -- add `__all__`: 8 symbols (see part3 section 3D)
            - `src/vaultspec/verification/__init__.py` -- eager re-export all 8 symbols
            - Consumer rewrites: `from vaultspec.graph.api import VaultGraph` -> `from vaultspec.graph import VaultGraph`, etc.
            - Consumers: `src/vaultspec/vault_cli.py`, `src/vaultspec/rag/api.py`, `src/vaultspec/metrics/api.py` (for verification lazy import)
        - These are single-module packages; no intra-package relative import conversion needed

    4. **Step 4** (Agent B): Add `__all__`, lazy `__init__.py` for `rag/` and rewrite consumers
        - Name: RAG package lazy `__init__.py` + `__all__` + consumer rewrite
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave2-step4.md`
        - Executing sub-agent: vaultspec-complex-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part2-research]]
        - Dependencies: Steps 1-2
        - Affected files:
            - `src/vaultspec/rag/api.py` -- add `__all__` with 10 symbols
            - `src/vaultspec/rag/embeddings.py` -- add `__all__` with 5 symbols
            - `src/vaultspec/rag/indexer.py` -- add `__all__` with 3 symbols
            - `src/vaultspec/rag/search.py` -- add `__all__` with 5 symbols
            - `src/vaultspec/rag/store.py` -- add `__all__` with 3 symbols
            - `src/vaultspec/rag/__init__.py` -- **`__getattr__`-based lazy loading**: `__all__` declares the full public API but no import statements execute at module load time; `__getattr__` intercepts attribute access and performs imports on first use. torch/lancedb must NOT be imported eagerly.
            - Intra-package relative imports: `from vaultspec.rag.store import VaultDocument` -> `from .store import VaultDocument` in `indexer.py`, etc.
            - Consumer rewrite: `src/vaultspec/vault_cli.py` -- `from vaultspec.rag.api import index` -> `from vaultspec.rag import index`, `from vaultspec.rag.embeddings import get_device_info` -> `from vaultspec.rag import get_device_info`

- **Wave 3** -- Phase 4: `orchestration/` (1 agent)

    5. **Step 5**: Add `__all__`, selective `__init__.py` for `orchestration/` and rewrite consumers
        - Name: Orchestration selective re-exports + `__all__` + consumer rewrite
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave3-step5.md`
        - Executing sub-agent: vaultspec-complex-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part1-research]]
        - Dependencies: Steps 1-2
        - Affected files:
            - `src/vaultspec/orchestration/constants.py` -- add `__all__`: `["READONLY_PERMISSION_PROMPT"]`
            - `src/vaultspec/orchestration/utils.py` -- add `__all__`: `["SecurityError", "find_project_root", "safe_read_text"]`
            - `src/vaultspec/orchestration/session_logger.py` -- add `__all__`: `["SessionLogger", "cleanup_old_logs"]`
            - `src/vaultspec/orchestration/task_engine.py` -- add `__all__`: 9 symbols (see part1 section 3F)
            - `src/vaultspec/orchestration/subagent.py` -- add `__all__`: `["AgentNotFoundError", "load_agent", "get_provider_for_model", "run_subagent"]`
            - `src/vaultspec/orchestration/team.py` -- add `__all__`: 6 symbols (see part1 section 3F)
            - `src/vaultspec/orchestration/__init__.py` -- **selective** re-export: eagerly re-export from `constants`, `utils`, `session_logger`, `task_engine` only. `subagent` and `team` stay deep-importable (NOT in `__init__.py`).
            - Intra-package relative import: `subagent.py` `from vaultspec.orchestration.utils import safe_read_text` -> `from .utils import safe_read_text`
            - Consumer rewrites for eagerly re-exported symbols: `from vaultspec.orchestration.constants import READONLY_PERMISSION_PROMPT` -> `from vaultspec.orchestration import READONLY_PERMISSION_PROMPT`, `from vaultspec.orchestration.task_engine import TaskEngine` -> `from vaultspec.orchestration import TaskEngine`, etc.
            - Deep imports retained: `from vaultspec.orchestration.subagent import run_subagent` (keeps current form), `from vaultspec.orchestration.team import TeamCoordinator` (keeps current form)

- **Wave 4** -- Phase 5: `protocol/` (1 agent)

    6. **Step 6**: Add `__all__`, `__init__.py` re-exports for entire `protocol/` hierarchy and rewrite consumers
        - Name: Protocol hierarchy `__all__` + re-exports + consumer rewrite
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave4-step6.md`
        - Executing sub-agent: vaultspec-complex-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part2-research]]
        - Dependencies: Steps 1-2, Step 5
        - 5 `__init__.py` files to populate:
            - `src/vaultspec/protocol/providers/__init__.py` -- already has partial re-exports; extend to include `ClaudeProvider`, `GeminiProvider`, full `base.py` public API (`AgentProvider`, `ProcessSpec`, `resolve_includes`, `resolve_executable`)
            - `src/vaultspec/protocol/acp/__init__.py` -- re-export: `SubagentError`, `SubagentResult`, `SessionLogger`, `SubagentClient`, `ClaudeACPBridge`
            - `src/vaultspec/protocol/a2a/__init__.py` -- re-export from `server`, `agent_card`, `discovery`, `state_map`. Do NOT re-export from `executors/`
            - `src/vaultspec/protocol/a2a/executors/__init__.py` -- re-export `ClaudeA2AExecutor`, `GeminiA2AExecutor` (safe: only loaded on explicit import)
            - `src/vaultspec/protocol/__init__.py` -- re-export most-consumed symbols from `providers` and `acp`. Do NOT transitively re-export from `a2a/executors/` (circular risk with `orchestration`)
        - Add `__all__` to all 13 production modules:
            - `protocol/sandbox.py`, `protocol/providers/base.py`, `protocol/providers/claude.py`, `protocol/providers/gemini.py`, `protocol/acp/types.py`, `protocol/acp/client.py`, `protocol/acp/claude_bridge.py`, `protocol/a2a/server.py`, `protocol/a2a/discovery.py`, `protocol/a2a/agent_card.py`, `protocol/a2a/state_map.py`, `protocol/a2a/executors/claude_executor.py`, `protocol/a2a/executors/gemini_executor.py`
        - Convert all intra-package imports to relative form throughout the hierarchy (see part2 section "Protocol: Intra-Package Import Graph"):
            - `providers/claude.py`: `from .base import ...`
            - `providers/gemini.py`: `from .base import ...`
            - `acp/claude_bridge.py`: `from vaultspec.protocol.providers.base import ClaudeModels` -> relative to parent: keep absolute (cross-sub-package)
            - `a2a/executors/base.py`: `from vaultspec.protocol.sandbox import ...` -> keep absolute (cross-sub-package)
            - `a2a/executors/claude_executor.py`: `from vaultspec.protocol.a2a.executors.base import ...` -> `from .base import ...`
            - `a2a/executors/gemini_executor.py`: `from vaultspec.protocol.providers.base import GeminiModels` -> keep absolute (cross-sub-package)
        - Consumer rewrites:
            - `from vaultspec.protocol.providers.claude import ClaudeProvider` -> `from vaultspec.protocol.providers import ClaudeProvider`
            - `from vaultspec.protocol.providers.gemini import GeminiProvider` -> `from vaultspec.protocol.providers import GeminiProvider`
            - `from vaultspec.protocol.providers.base import CapabilityLevel` -> `from vaultspec.protocol.providers import CapabilityLevel`
            - `from vaultspec.protocol.acp.types import SubagentError` -> `from vaultspec.protocol.acp import SubagentError`
            - `from vaultspec.protocol.acp.client import SubagentClient` -> `from vaultspec.protocol.acp import SubagentClient`
            - `from vaultspec.protocol.a2a.agent_card import agent_card_from_definition` -> `from vaultspec.protocol.a2a import agent_card_from_definition`
            - `from vaultspec.protocol.a2a.server import create_app` -> `from vaultspec.protocol.a2a import create_app`
            - `from vaultspec.protocol.a2a.executors.claude_executor import ClaudeA2AExecutor` -> `from vaultspec.protocol.a2a.executors import ClaudeA2AExecutor`
            - `from vaultspec.protocol.a2a.executors.gemini_executor import GeminiA2AExecutor` -> `from vaultspec.protocol.a2a.executors import GeminiA2AExecutor`

- **Wave 5** -- Phase 6: `subagent_server/` (1 agent)

    7. **Step 7**: Add `__all__`, `__init__.py` re-exports for `subagent_server/` and rewrite consumers
        - Name: Subagent server `__all__` + re-exports + consumer rewrite
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave5-step7.md`
        - Executing sub-agent: vaultspec-standard-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part3-research]]
        - Dependencies: Steps 1-6
        - Affected files:
            - `src/vaultspec/subagent_server/server.py` -- add `__all__` with 9 symbols (see part3 section 4D)
            - `src/vaultspec/subagent_server/__init__.py` -- eager re-export: `initialize_server`, `register_tools`, `subagent_lifespan`
        - Consumer rewrites:
            - `src/vaultspec/server.py`: `from vaultspec.subagent_server.server import initialize_server, register_tools, subagent_lifespan` -> `from vaultspec.subagent_server import initialize_server, register_tools, subagent_lifespan`
            - `src/vaultspec/subagent_cli.py`: `from vaultspec.subagent_server.server import main as server_main` -> retain deep import (not in `__init__` re-exports)

- **Wave 6** -- Phase 7: Entry points + tests (1 agent, sequential)

    8. **Step 8**: Retarget entry point imports and add `__all__` to top-level modules
        - Name: Entry point retargeting + top-level `__all__`
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave6-step8.md`
        - Executing sub-agent: vaultspec-standard-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part3-research]]
        - Dependencies: Steps 1-7
        - Affected files:
            - `src/vaultspec/cli.py` -- retarget 12 absolute imports to package-level exports (keep absolute form, change depth); e.g., `from vaultspec.core.config import get_config` -> `from vaultspec.core import get_config`
            - `src/vaultspec/vault_cli.py` -- retarget 11 absolute imports similarly
            - `src/vaultspec/team_cli.py` -- retarget 3 absolute imports (note: `orchestration.team` stays deep-import)
            - `src/vaultspec/subagent_cli.py` -- retarget 12 absolute imports (note: `orchestration.subagent` stays deep-import; `a2a.executors.*` use `executors/__init__` level)
            - `src/vaultspec/server.py` -- already addressed in Step 7
            - `src/vaultspec/logging_config.py` -- add `__all__`: `["configure_logging", "reset_logging"]`
            - `src/vaultspec/mcp_tools/vault_tools.py` -- add `__all__`: `["register_tools"]`
            - `src/vaultspec/mcp_tools/team_tools.py` -- add `__all__`: `["register_tools"]`
            - `src/vaultspec/mcp_tools/framework_tools.py` -- add `__all__`: `["register_tools"]`
            - `src/vaultspec/mcp_tools/__init__.py` -- re-export with disambiguated names: `register_vault_tools`, `register_team_tools`, `register_framework_tools`
            - `src/vaultspec/__main__.py` -- optionally convert to `from .cli import main` (low priority)

    9. **Step 9**: Rewrite all test imports to use package-level imports
        - Name: Test import migration
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave6-step9.md`
        - Executing sub-agent: vaultspec-complex-executor
        - References: [[2026-02-21-module-exports-adr]], [[2026-02-21-module-exports-part3-research]]
        - Dependencies: Steps 1-8
        - Approximately 224 test import statements across:
            - `tests/` directory (~94 statements)
            - `src/vaultspec/*/tests/` in-tree tests (~130 statements)
        - Rewrite to package-level: `from vaultspec.core.config import get_config` -> `from vaultspec.core import get_config`, etc.
        - Exception: tests explicitly testing private internals retain deep imports (e.g., `from vaultspec.rag.store import _parse_json_list`, `from vaultspec.rag.indexer import _extract_feature`, monkeypatching targets like `import vaultspec.cli as cli`)

- **Wave 7** -- Verification (1 agent)

    10. **Step 10**: Full verification pass
        - Name: Verification and audit
        - Step summary: `.vault/exec/2026-02-21-module-exports/2026-02-21-module-exports-wave7-step10.md`
        - Executing sub-agent: vaultspec-code-reviewer
        - References: [[2026-02-21-module-exports-adr]]
        - Dependencies: Steps 1-9
        - Checks:
            - `uv sync --dev` -- must succeed
            - `uv run pytest tests/ src/ --timeout=30 -m "not e2e and not integration and not benchmark and not gemini and not claude and not a2a and not team"` -- all tests pass (1017+ expected)
            - Grep audit: no `from vaultspec.X.Y import Z` where `Z` is re-exported at `vaultspec.X` level (exceptions: `orchestration.subagent`, `orchestration.team`, test files testing internals)
            - Every `__init__.py` under `src/vaultspec/` has re-exports (grep for `from .` in each)
            - Every production `.py` module has `__all__` (grep verification)
            - REPL smoke test: `from vaultspec.core import get_config` works

## Parallelization

```
Wave 1: Steps 1-2 (sequential, 1 agent -- leaf packages + consumer rewrite)
Wave 2: Steps 3+4 (parallel, 2 agents -- analytics packages + rag)
Wave 3: Step 5   (1 agent -- orchestration)
Wave 4: Step 6   (1 agent -- protocol)
Wave 5: Step 7   (1 agent -- subagent_server)
Wave 6: Steps 8+9 (sequential, 1 agent -- entry points then tests)
Wave 7: Step 10  (1 agent -- verification)
```

Waves 2-5 could theoretically run in parallel since they share only the dependency on Wave 1 completion. However, the ADR prescribes bottom-up DAG ordering for independent verifiability, and waves 3-5 have implicit ordering constraints (`subagent_server` depends on `orchestration` and `protocol` re-exports being finalized). Wave 2 steps 3 and 4 are fully independent and should run in parallel.

## Verification

Success criteria per [[2026-02-21-module-exports-adr]]:

- `uv sync --dev` succeeds without errors
- `uv run pytest tests/ src/ --timeout=30 -m "not e2e and not integration and not benchmark and not gemini and not claude and not a2a and not team"` passes with zero regressions (baseline: 1017+ tests)
- Every `__init__.py` under `src/vaultspec/` (excluding `tests/__init__.py` files) contains re-exports (verifiable by grepping for `from .` in each `__init__.py`)
- Every production `.py` module (excluding `__init__.py`, `__main__.py`, `conftest.py`, and test files) has an `__all__` declaration
- No `from vaultspec.X.Y import Z` patterns remain in production code where `Z` is re-exported at the `vaultspec.X` package level. Allowed exceptions:
    - `from vaultspec.orchestration.subagent import ...` (deep-import-only by design)
    - `from vaultspec.orchestration.team import ...` (deep-import-only by design)
    - `from vaultspec.subagent_server.server import main` in `subagent_cli.py` (not in `__init__` re-exports)
    - Test files testing private internals
- `from vaultspec.core import get_config` works in a Python REPL (smoke test for the re-export mechanism)
- `import vaultspec.rag` does NOT trigger torch/lancedb import (lazy loading verified)
