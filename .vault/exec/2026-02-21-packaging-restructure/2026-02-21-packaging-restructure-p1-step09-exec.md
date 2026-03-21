---
tags:
  - '#exec'
  - '#packaging-restructure'
date: '2026-02-21'
related:
  - '[[2026-02-21-packaging-restructure-p1p2-plan]]'
  - '[[2026-02-21-packaging-restructure-research]]'
---

# Step 9: Rewrite imports in all test files and conftest files

## Status: COMPLETE

## Summary

Rewrote all bare-name imports across the entire test tree (top-level `tests/` and in-package `src/vaultspec/*/tests/`) to use `vaultspec.*` prefixed forms. Also fixed incorrect `vaultspec.tests.*` import patterns and updated stale path references.

## Changes

### `tests/constants.py`

- Fixed `PROJECT_ROOT` path derivation: was 4 levels up (`.vaultspec/lib/tests/`), now 2 levels up (`tests/`)
- Updated `LIB_SRC` to point to `src/vaultspec/` instead of `.vaultspec/lib/src/`
- Updated `SCRIPTS` to point to `src/vaultspec/` instead of `.vaultspec/lib/scripts/`

### Root `conftest.py`

- Updated docstring to reflect new test tree layout

### `tests/conftest.py`

- `from core.config import ...` -> `from vaultspec.core.config import ...`
- `from rag.indexer import ...` -> `from vaultspec.rag.indexer import ...`
- `from vaultcore.scanner import ...` -> `from vaultspec.vaultcore.scanner import ...`
- `from rag.embeddings import ...` -> `from vaultspec.rag.embeddings import ...`
- `from rag.indexer import ...` -> `from vaultspec.rag.indexer import ...`
- `from rag.store import ...` -> `from vaultspec.rag.store import ...`

### `tests/cli/` (7 files)

- `import cli` -> `import vaultspec.cli as cli` (6 occurrences across conftest, test_sync\_\*, test_integration)
- `from core.workspace import ...` -> `from vaultspec.core.workspace import ...` (3 occurrences)
- `from protocol.providers.base import ...` -> `from vaultspec.protocol.providers.base import ...` (2 files)
- `from team import ...` -> `from vaultspec.team_cli import ...` (test_team_cli.py)
- `from orchestration.team import ...` -> `from vaultspec.orchestration.team import ...`
- `from protocol.a2a.server import ...` -> `from vaultspec.protocol.a2a.server import ...`
- `from protocol.a2a.tests.conftest import ...` -> `from vaultspec.protocol.a2a.tests.conftest import ...`
- `import vault` -> `import vaultspec.vault_cli as vault` (test_vault_cli.py)
- `import logging_config` -> `import vaultspec.logging_config as logging_config` (test_vault_cli.py)
- `from vaultcore.models import DocType` -> `from vaultspec.vaultcore.models import DocType`
- Updated subprocess calls: `.vaultspec/lib/scripts/subagent.py` -> `-m vaultspec.subagent_cli`
- Updated DOCS_SCRIPT path to `src/vaultspec/vault_cli.py`
- Updated run_vault() to use `-m vaultspec.vault_cli` instead of direct script execution

### `tests/e2e/` (5 files)

- All `from orchestration.*` -> `from vaultspec.orchestration.*`
- All `from protocol.*` -> `from vaultspec.protocol.*`
- All `from subagent_server.*` -> `from vaultspec.subagent_server.*`
- All `from vaultcore.*` -> `from vaultspec.vaultcore.*`
- All `import subagent_server.*` -> `import vaultspec.subagent_server.*`

### `tests/subagent/` (2 files)

- `import subagent_server.server as srv` -> `import vaultspec.subagent_server.server as srv`
- `from subagent_server.server import ...` -> `from vaultspec.subagent_server.server import ...`
- `from orchestration.task_engine import ...` -> `from vaultspec.orchestration.task_engine import ...`
- Updated docstring reference to `src/vaultspec/subagent_server/tests/test_helpers.py`

### `tests/rag/` (7 files)

- All `from rag.*` -> `from vaultspec.rag.*` (many inline imports across all files)
- All `from vaultcore.*` -> `from vaultspec.vaultcore.*`
- `from graph.api import ...` -> `from vaultspec.graph.api import ...`
- `from metrics.api import ...` -> `from vaultspec.metrics.api import ...`
- `from verification.api import ...` -> `from vaultspec.verification.api import ...`
- `import rag.api as api_mod` -> `import vaultspec.rag.api as api_mod`
- Updated docstring references

### `tests/test_config.py`

- `from core.config import ...` -> `from vaultspec.core.config import ...`

### `tests/test_logging_config.py`

- `import logging_config` -> `import vaultspec.logging_config as logging_config`

### `tests/benchmarks/bench_rag.py`

- Fixed standalone bootstrap to use `src/` instead of `.vaultspec/lib/src/`
- All `from rag.*` -> `from vaultspec.rag.*`

### In-package conftest fixes (`src/vaultspec/*/tests/conftest.py`)

- `vaultspec.tests.constants` -> `tests.constants` (graph, metrics, verification, rag, subagent_server conftest files)
- `vaultspec.tests.conftest` -> `tests.conftest` (rag conftest)

### In-package test fixes (Wave 2 missed inline imports)

- `src/vaultspec/orchestration/tests/test_session_logger.py`: 9 inline bare-name imports fixed
- `src/vaultspec/orchestration/tests/test_team.py`: 2 inline bare-name imports fixed
- `src/vaultspec/protocol/tests/test_providers.py`: 6 inline bare-name imports fixed
- `src/vaultspec/protocol/acp/tests/test_e2e_bridge.py`: 4 inline bare-name imports fixed
- `src/vaultspec/protocol/acp/tests/test_bridge_lifecycle.py`: 4 inline bare-name imports fixed
- `src/vaultspec/protocol/a2a/tests/test_e2e_a2a.py`: 5 inline bare-name imports fixed
- `src/vaultspec/protocol/a2a/tests/test_french_novel_relay.py`: 2 inline bare-name imports fixed
- `src/vaultspec/subagent_server/tests/test_mcp_tools.py`: 1 `vaultspec.tests.constants` fixed
- `src/vaultspec/rag/tests/test_indexer_unit.py`: 1 `vaultspec.tests.constants` fixed

## Verification

Post-edit grep scan confirms ZERO remaining bare-name imports across:

- All files in `tests/` (recursively)
- All files in `src/vaultspec/*/tests/` (recursively)
- Root `conftest.py`
- No remaining `vaultspec.tests.*` patterns
