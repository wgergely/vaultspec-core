---
tags:
  - "#plan"
  - "#protocol-tests"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-test-architecture-adr]]"
---
# Plan: Protocol Test Architecture Implementation

## Goal
Implement the test architecture defined in [[2026-02-22-protocol-test-architecture-adr]]: strict unit test bundling and a deterministic protocol matrix.

## Phase 1: Unit Test Migration (Rust-Style Bundling)
Move valid logic tests to `src/` modules. Preserve git history where possible (using `mv`).

1.  **Providers**:
    *   `mv tests/e2e/test_provider_parity.py src/vaultspec/protocol/tests/test_parity.py`
2.  **Subagent Server**:
    *   `mv tests/subagent/test_subagent.py src/vaultspec/subagent_server/tests/test_task_engine_integration.py`
    *   `mv tests/subagent/test_mcp_protocol.py src/vaultspec/subagent_server/tests/test_mcp_protocol.py`
3.  **Orchestration**:
    *   `mv tests/integration/test_team_lifecycle.py src/vaultspec/orchestration/tests/test_team_lifecycle.py`
4.  **CLI**:
    *   `mkdir -p src/vaultspec/tests/cli`
    *   `mv tests/cli/* src/vaultspec/tests/cli/`
5.  **RAG**:
    *   `mv tests/rag/* src/vaultspec/rag/tests/` (rename `test_*.py` -> `test_*_integration.py` to avoid collisions with existing unit tests).

## Phase 2: Legacy Cleanup
Delete deprecated test suites.

1.  `rm -rf tests/e2e` (Full Cycle, Claude/Gemini "fairytale" tests).
2.  `rm -rf tests/subagent` (Empty after move).
3.  `rm -rf tests/integration` (Empty after move).
4.  `rm -rf tests/cli` (Empty after move).
5.  `rm -rf tests/rag` (Empty after move).

## Phase 3: Protocol Matrix Setup
Create the new `tests/protocol/` directory structure.

1.  `mkdir -p tests/protocol/isolation`
2.  `mkdir -p tests/protocol/cross`
3.  **Fixtures**: Create `tests/protocol/conftest.py`.
    *   Implement `echo_agent_def`: Returns markdown definition for "Echo Agent".
    *   Implement `state_agent_def`: Returns markdown definition for "State Agent".
    *   Implement `debug_logging`: Fixture to force DEBUG level.

## Phase 4: Isolation Tests (Single Provider)
Implement single-provider test files.

1.  **Gemini Subagent**: `tests/protocol/isolation/test_subagent_gemini.py`
    *   `test_echo_single_turn`: Dispatch Echo Agent -> "Echo: Hello".
    *   `test_state_multi_turn`: Dispatch State Agent -> Set X -> Get X.
2.  **Claude Subagent**: `tests/protocol/isolation/test_subagent_claude.py`
    *   Same as Gemini.
3.  **Gemini Team**: `tests/protocol/isolation/test_team_gemini.py`
    *   `test_team_lifecycle`: Form team (2x Echo Gemini) -> Dispatch -> Dissolve.
4.  **Claude Team**: `tests/protocol/isolation/test_team_claude.py`
    *   Same as Gemini.

## Phase 5: Cross-Wiring Tests (Multi-Provider)
Implement multi-provider interoperability tests.

1.  **Dispatch**: `tests/protocol/cross/test_dispatch_mixed.py`
    *   `test_gemini_spawns_claude`: Gemini (Echo) spawns Claude (Echo).
    *   `test_claude_spawns_gemini`: Claude (Echo) spawns Gemini (Echo).
2.  **Mixed Team**: `tests/protocol/cross/test_team_mixed.py`
    *   `test_mixed_team_broadcast`: Form team (1 Gemini, 1 Claude). Broadcast "Hello". Verify both results.

## Phase 6: Verification
1.  Run `pytest src/` to verify migrated unit tests pass.
2.  Run `pytest tests/protocol/` to verify the new matrix. (Expect some failures initially if providers have bugs, but structure is verified).
