---
tags:
  - "#research"
  - "#protocol-tests"
date: "2026-02-22"
related:
  - "[[2026-02-21-protocol-gap-analysis-research]]"
---
# Research: Protocol Test Architecture Overhaul

## Context
The current test suite is fragmented across `tests/e2e`, `tests/subagent`, `tests/integration`, `tests/cli`, and `tests/rag`. It mixes unit tests, system tests, and complex "fairytale" scenarios that are brittle and hard to maintain. The goal is to restructure this into a rigorous, matrix-based protocol test suite while moving true unit tests to their respective `src/` modules (Rust-style bundling).

## Industry Best Practices for Multi-Agent Testing
A review of current literature on testing collaborative AI agents highlights the following key challenges and solutions:

1.  **Non-Determinism**: LLMs are inherently probabilistic. Testing interaction dynamics requires controlling this randomness.
    *   *Solution*: **Deterministic Scaffolding**. Use "Echo" or "State" agents with strict instructions and Temperature 0 to verify the *protocol pipe* separate from the *model intelligence*.
2.  **Layered Evaluation**:
    *   **Unit**: Test individual components (parsers, state machines) in isolation.
    *   **Integration**: Test the communication channel (A2A) between two agents.
    *   **System**: Test the full collaborative workflow.
3.  **Observability**: Debugging multi-agent failures requires deep tracing of the message exchange, not just the final output.

**Conclusion**: Our proposed architecture aligns with these practices by:
*   Enforcing Rust-style **Unit Tests** for component logic.
*   Using **Echo Agents** (Deterministic Scaffolding) for Integration/System tests.
*   Mandating **Debug Logging** for observability.

## Audit Findings

### Legacy Test Suites (To Be Deleted)
The following directories contain mixed-level tests or "fairytale" scenarios that must be removed:

1.  **`tests/e2e/`**:
    *   `test_full_cycle.py`: Uses "French fairy tales" scenario. High complexity, brittle.
    *   `test_claude.py`: Mixes unit tests (rule loading) with CLI invocation.
    *   `test_gemini.py`: Similar to Claude tests.
    *   `test_mcp_e2e.py`: Redundant with new matrix.
    *   `test_provider_parity.py`: Actually a unit test for `ProcessSpec`.

2.  **`tests/subagent/`**:
    *   `test_subagent.py`: Unit tests for `TaskEngine` and `LockManager`.
    *   `test_mcp_protocol.py`: Unit tests for MCP messages.

3.  **`tests/integration/`**:
    *   `test_team_lifecycle.py`: Functional test of `TeamCoordinator` using `EchoExecutor`.

4.  **`tests/cli/`**:
    *   `test_vault_cli.py`: Unit tests for CLI args.
    *   Others: Unit tests for specific CLI commands.

5.  **`tests/rag/`**:
    *   `test_store.py`: Integration test for `VaultStore`.
    *   Others: Integration tests for RAG components.

### Unit Test Candidates (To Be Moved)
The following logic should be preserved but moved to `src/` to follow Rust-style bundling:

*   `tests/e2e/test_provider_parity.py` -> `src/vaultspec/protocol/providers/tests/test_parity.py`
*   `tests/subagent/*.py` -> `src/vaultspec/subagent_server/tests/`
*   `tests/integration/test_team_lifecycle.py` -> `src/vaultspec/orchestration/tests/test_team_lifecycle.py`
*   `tests/cli/*.py` -> `src/vaultspec/tests/cli/`
*   `tests/rag/*.py` -> `src/vaultspec/rag/tests/`

## Proposed Architecture: `tests/protocol/`

A new top-level directory `tests/protocol/` will house the rigorous ACP/A2A matrix tests.

### Design Principles
1.  **Surgical Precision**: Tests are named by their exact function in the matrix.
2.  **Simple Payloads**: Use "Echo", "Hello World", or "State Retention" tasks. No creative writing.
3.  **Strict Separation**: Isolation tests vs. Cross-wiring tests.

### Test Matrix

#### 1. Isolation (Single Provider)
Tests the provider's ACP implementation in isolation.

*   **Subagent (ACP)**:
    *   `isolation/test_subagent_gemini.py`:
        *   Single-turn: "Say 'hello'". Expect "hello".
        *   Multi-turn: "My number is 42." -> "What is my number?". Expect "42".
    *   `isolation/test_subagent_claude.py`:
        *   Same cases.

*   **Team (A2A)**:
    *   `isolation/test_team_gemini.py`:
        *   Form team of 2 Gemini agents.
        *   Dispatch "Echo this".
        *   Dissolve.
    *   `isolation/test_team_claude.py`:
        *   Same cases.

#### 2. Cross-Wiring (Mixed Providers)
Tests interoperability between Gemini and Claude.

*   **Subagent Dispatch**:
    *   `cross/test_dispatch_mixed.py`:
        *   Gemini agent uses `dispatch_agent` tool to spawn Claude agent.
        *   Claude agent uses `dispatch_agent` tool to spawn Gemini agent.

*   **Mixed Teams**:
    *   `cross/test_team_mixed.py`:
        *   Form team with 1 Gemini + 1 Claude agent.
        *   Broadcast message to both.
        *   Gemini relays message to Claude.

## Migration Strategy
1.  **Move** valid unit/integration logic to `src/`.
2.  **Delete** the legacy `tests/` directories.
3.  **Implement** the new `tests/protocol/` suite from scratch.
