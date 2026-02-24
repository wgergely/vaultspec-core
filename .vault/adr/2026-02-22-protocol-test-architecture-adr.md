---
tags:
  - "#adr"
  - "#protocol-tests"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-test-architecture-research]]"
  - "[[2026-02-21-protocol-gap-analysis-research]]"
  - "[[2026-02-21-provider-auth-billing-research]]"
---
# ADR: Rust-Style Unit Testing & Deterministic Protocol Matrix

## Status
**Proposed**

## Context
The current test suite is fragmented (`tests/e2e`, `tests/subagent`, `tests/integration`, etc.) and relies on brittle "fairytale" scenarios that test LLM creativity rather than protocol correctness. Debugging is difficult due to mixed abstraction levels and inconsistent logging. We need a rigorous, surgical test architecture that verifies the **VaultSpec Protocol** (ACP and A2A) across all provider combinations (Gemini, Claude) and topologies (Isolation, Cross-Wiring).

## Decisions

### 1. Test Suite Partitioning
We will strictly separate **Unit Tests** (logic verification) from **Protocol Tests** (system verification).

*   **Unit Tests**: Must be co-located with the source code they test (`src/**/tests/`). This follows Rust-style bundling.
    *   *Action*: Move all valid logic tests from `tests/` to `src/`.
    *   *Example*: `tests/cli/test_vault_cli.py` -> `src/vaultspec/tests/cli/test_vault_cli.py`.
*   **Protocol Tests**: All system-level tests will reside in `tests/protocol/`.
    *   *Action*: Delete `tests/e2e`, `tests/subagent`, `tests/integration`, `tests/cli`, `tests/rag`.

### 2. Deterministic "Echo" & "State" Agents
Protocol tests must verify the *pipe*, not the *model*. We will use specific agent personas designed for deterministic output.

*   **Single-Turn ("Echo Agent")**:
    *   *Behavior*: The agent instruction is "You are an Echo Agent. Repeat the user's input exactly, prefixed with 'Echo: '. Do not add any other text."
    *   *Verification*: `assert response == "Echo: <input>"`
*   **Multi-Turn ("State Agent")**:
    *   *Behavior*: The agent instruction is "You are a State Agent. If the user says 'Set <key>=<value>', reply 'OK'. If the user says 'Get <key>', reply with <value>. Do not explain."
    *   *Verification*:
        *   Turn 1: "Set secret=1234" -> Expect "OK"
        *   Turn 2: "Get secret" -> Expect "1234"
    *   *Purpose*: Verifies session persistence, context retention, and memory across turns.

### 3. Protocol Matrix Coverage
The `tests/protocol/` directory will implement a strict matrix covering all permutations of Provider, Topology, and Turn-Count.

#### A. Isolation (Single Provider)
Verifies the provider's ACP implementation works in a vacuum.

*   **Subagent (ACP)**:
    *   `tests/protocol/isolation/test_subagent_gemini.py`:
        *   `test_gemini_echo_single_turn`: User "Hello" -> Agent "Echo: Hello"
        *   `test_gemini_state_multi_turn`: Set X -> Get X
    *   `tests/protocol/isolation/test_subagent_claude.py`:
        *   Same for Claude.
*   **Team (A2A)**:
    *   `tests/protocol/isolation/test_team_gemini.py`:
        *   `test_gemini_team_lifecycle`: Form team (2 Gemini agents), Dispatch Echo, Dissolve.
    *   `tests/protocol/isolation/test_team_claude.py`:
        *   Same for Claude.

#### B. Cross-Wiring (Interoperability)
Verifies providers can talk to each other.

*   **Subagent Dispatch**:
    *   `tests/protocol/cross/test_dispatch_mixed.py`:
        *   `test_gemini_spawns_claude`: Gemini agent uses `dispatch_agent` tool -> Spawns Claude Echo Agent -> Returns result.
        *   `test_claude_spawns_gemini`: Claude agent uses `dispatch_agent` tool -> Spawns Gemini Echo Agent -> Returns result.
*   **Mixed Teams**:
    *   `tests/protocol/cross/test_team_mixed.py`:
        *   `test_mixed_team_broadcast`: Form team (1 Gemini, 1 Claude). Broadcast "Hello". Verify both return "Echo: Hello".

### 4. Authentication & Environment
Tests will rely on the existing authentication fallback chain (OAuth CLI session -> Environment Variable). No new API key management logic will be introduced. Tests assume the environment is configured (e.g., `gemini auth login` or `GEMINI_API_KEY`).

### 5. Logging & Debugging
*   **Debug-by-Default**: All protocol tests will force `VAULTSPEC_LOG_LEVEL=DEBUG` (or equivalent code config).
*   **Capture**: `pytest` output will capture full ACP JSON messages and A2A HTTP traffic.
*   **No Retries**: We explicitly **reject** retry logic for now. Failures should be noisy to expose protocol instability.

## Consequences
*   **Positive**:
    *   Eliminates flaky "creative" tests.
    *   Provides rigorous coverage of the ACP/A2A state machine.
    *   Enforces modularity via Rust-style bundling.
*   **Negative**:
    *   Requires rewriting the entire integration suite.
    *   Requires manual environment setup (auth) for local runs (though this is standard for E2E).
