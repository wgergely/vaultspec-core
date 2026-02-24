---
tags:
  - "#exec"
  - "#packaging-restructure"
date: "2026-02-21"
related:
  - "[[2026-02-21-packaging-restructure-p1p2-plan]]"
---
# Step 6: Rewrite imports in mid-tier packages `orchestration/`, `protocol/`, `hooks/`

## Status: COMPLETE

## Summary

Rewrote all bare-name imports in `src/vaultspec/orchestration/`, `src/vaultspec/protocol/` (including `acp/`, `a2a/`, `providers/` sub-packages), and `src/vaultspec/hooks/` to use `vaultspec.*` prefixed forms. This covered production code and all `tests/` subdirectories.

## Files Modified

### orchestration/
- `session_logger.py` -- `from core.config` -> `from vaultspec.core.config`
- `subagent.py` -- 7 import rewrites: `vaultcore.parser`, `orchestration.utils`, `protocol.acp.client`, `protocol.acp.types`, `protocol.providers.claude`, `protocol.providers.gemini`, plus TYPE_CHECKING `protocol.providers.base`
- `tests/test_utils.py` -- `from orchestration.utils` -> `from vaultspec.orchestration.utils`
- `tests/test_team.py` -- `from orchestration.team`, `from protocol.a2a.server`, `from protocol.a2a.tests.conftest` (3 rewrites)
- `tests/test_load_agent.py` -- `from orchestration.subagent`, `from orchestration.utils`, `from protocol.providers.base` (3 rewrites)
- `tests/test_session_logger.py` -- `from core.config` -> `from vaultspec.core.config`
- `tests/test_task_engine.py` -- `from orchestration.task_engine` -> `from vaultspec.orchestration.task_engine`

### protocol/
- `acp/claude_bridge.py` -- `from logging_config`, `from protocol.providers.base`, `from protocol.sandbox` (3 rewrites)
- `a2a/executors/base.py` -- `from protocol.sandbox` -> `from vaultspec.protocol.sandbox`
- `a2a/executors/gemini_executor.py` -- `from orchestration.subagent`, `from protocol.providers.base` (2 rewrites)
- `a2a/executors/claude_executor.py` -- `from protocol.a2a.executors.base` -> `from vaultspec.protocol.a2a.executors.base`
- `tests/test_sandbox.py` -- `from protocol.sandbox` -> `from vaultspec.protocol.sandbox`
- `tests/test_providers.py` -- 4 rewrites: `orchestration.subagent`, `protocol.providers.base`, `protocol.providers.claude`, `protocol.providers.gemini`
- `tests/test_permissions.py` -- `from protocol.acp.client` -> `from vaultspec.protocol.acp.client`
- `tests/test_fileio.py` -- `from protocol.acp.client` -> `from vaultspec.protocol.acp.client`
- `tests/conftest.py` -- `from protocol.providers.base` -> `from vaultspec.protocol.providers.base`
- `tests/test_client.py` -- `from protocol.acp.client` -> `from vaultspec.protocol.acp.client`
- `acp/tests/conftest.py` -- `from protocol.acp.claude_bridge`, `from protocol.providers.base` (2 rewrites)
- `acp/tests/test_bridge_lifecycle.py` -- `from protocol.acp.claude_bridge`, `from protocol.providers.base` (2 rewrites)
- `acp/tests/test_bridge_sandbox.py` -- `from protocol.sandbox` -> `from vaultspec.protocol.sandbox`
- `acp/tests/test_client_terminal.py` -- `from protocol.acp.client` -> `from vaultspec.protocol.acp.client`
- `acp/tests/test_bridge_resilience.py` -- `from protocol.acp.claude_bridge` -> `from vaultspec.protocol.acp.claude_bridge`
- `acp/tests/test_e2e_bridge.py` -- `from protocol.providers.base` -> `from vaultspec.protocol.providers.base`
- `acp/tests/test_bridge_streaming.py` -- `from protocol.acp.claude_bridge` -> `from vaultspec.protocol.acp.claude_bridge`
- `a2a/tests/test_discovery.py` -- `from protocol.a2a.discovery` -> `from vaultspec.protocol.a2a.discovery`
- `a2a/tests/test_french_novel_relay.py` -- 4 rewrites: `orchestration.team`, `protocol.a2a.server`, `protocol.a2a.tests.conftest`, `protocol.providers.base`
- `a2a/tests/test_claude_executor.py` -- 3 rewrites: `protocol.a2a.executors.claude_executor`, `protocol.a2a.tests.conftest`, `protocol.providers.base`
- `a2a/tests/test_e2e_a2a.py` -- 4 rewrites: `protocol.a2a.agent_card`, `protocol.a2a.server`, `protocol.a2a.tests.conftest`, `protocol.providers.base`
- `a2a/tests/test_unit_a2a.py` -- 3 rewrites: `protocol.a2a.agent_card`, `protocol.a2a.state_map`, `protocol.a2a.tests.conftest`
- `a2a/tests/test_gemini_executor.py` -- 4 rewrites: `protocol.a2a.executors.gemini_executor`, `protocol.a2a.tests.conftest`, `protocol.acp.types`, `protocol.providers.base`
- `a2a/tests/test_agent_card.py` -- `from core.config`, `from protocol.a2a.agent_card` (2 rewrites)
- `a2a/tests/test_integration_a2a.py` -- `from protocol.a2a.server`, `from protocol.a2a.tests.conftest` (2 rewrites)

### hooks/
- `engine.py` -- deferred `from core.config` -> `from vaultspec.core.config`
- `tests/test_hooks.py` -- `from hooks.engine` -> `from vaultspec.hooks.engine`

## Verification

Grep scan of all three directories confirms zero bare-name imports remain.
