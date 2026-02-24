---
tags:
  - "#exec"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-plan]]"
  - "[[2026-02-22-cli-ecosystem-factoring-adr]]"
---
# cli-ecosystem-factoring phase1 summary

## outcome

Phase 1 complete. `vaultspec.core` renamed to `vaultspec.config` across the
entire codebase with zero first-party references remaining.

## files changed

- `src/vaultspec/core/` → `src/vaultspec/config/` (git mv)
  - `__init__.py` — docstring updated to "Configuration and workspace types for vaultspec."
  - `config.py` — moved verbatim
  - `workspace.py` — moved verbatim
  - `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`, `tests/test_workspace.py` — moved, internal imports updated to `vaultspec.config.*`

- 33 source files updated via Python replace script:
  `cli.py`, `cli_common.py`, `server.py`, `subagent_cli.py`, `team_cli.py`,
  `vault_cli.py`, `hooks/engine.py`, `graph/tests/conftest.py`,
  `metrics/tests/conftest.py`, `orchestration/session_logger.py`,
  `orchestration/subagent.py`, `orchestration/task_engine.py`,
  `orchestration/tests/test_session_logger.py`, `protocol/a2a/agent_card.py`,
  `protocol/a2a/discovery.py`, `protocol/a2a/tests/test_agent_card.py`,
  `protocol/acp/claude_bridge.py`, `protocol/acp/client.py`,
  `protocol/providers/gemini.py`, `rag/api.py`, `rag/embeddings.py`,
  `rag/indexer.py`, `rag/search.py`, `rag/store.py`,
  `rag/tests/test_indexer_unit.py`, `subagent_server/server.py`,
  `tests/cli/test_integration.py`, `vaultcore/hydration.py`,
  `vaultcore/models.py`, `vaultcore/scanner.py`,
  `vaultcore/tests/test_scanner.py`, `verification/api.py`,
  `verification/tests/conftest.py`

- `subagent_cli.py` — fixed pre-existing indentation error at lines 98-102
  and restored missing `import warnings` (removed by prior Phase 2 work)

## deprecation shim

Not created — per authoritative refactor directive. The `core/` directory is
now empty and the namespace is freed for Phase 3.

## verification

- `rg "from vaultspec.core" src/ tests/` → 0 results
- `from vaultspec.config import get_config, WorkspaceLayout, ...` → OK
- `from vaultspec.config.config import VaultSpecConfig` → OK
- `from vaultspec.config.workspace import LayoutMode, WorkspaceError` → OK
- 218 tests pass; 5 failures are pre-existing (unrelated to rename)
