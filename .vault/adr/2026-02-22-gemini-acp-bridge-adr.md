---
tags: ["#adr", "#gemini-acp-bridge"]
date: "2026-02-22"
related:
  - "[[2026-02-22-gemini-acp-audit-expanded]]"
  - "[[2026-02-21-claude-acp-bidirectional-adr]]"
---

# ADR: `gemini-acp-bridge` — Gemini ACP Protocol Normalization & Session Parity

## Status
**Proposed**

## Context
The VaultSpec ecosystem requires feature parity between Claude and Gemini providers to ensure a consistent agent experience. While Claude has a robust ACP bridge (`claude_bridge.py`) that handles protocol normalization, session persistence, and rich tool interactions, Gemini currently relies on a direct subprocess execution of the `gemini` CLI with `--experimental-acp`.

This direct execution creates several architectural gaps:
1.  **Session Persistence**: No mechanism to `resume` sessions across tasks, which breaks multi-turn A2A coordination.
2.  **Planning Interception**: Missing conversion of `TodoWrite` tool calls to `AgentPlanUpdate` notifications (the "Planning" UI in Zed).
3.  **Tool Normalization**: Inconsistent `ToolKind` mapping and missing structured content (e.g., diffs for file edits).
4.  **Testability**: The lack of a Python-controlled bridge prevents the use of the rigorous ACP test suite established for Claude.

## Decision
We will implement `src/vaultspec/protocol/acp/gemini_bridge.py`, a Python-based ACP bridge for Gemini.

### Architectural Requirements:
1.  **Bridge Pattern**: The bridge will implement the ACP `Agent` interface, wrapping the `gemini` CLI (or `google-generativeai` SDK if necessary) to provide a stable, normalized protocol stream.
2.  **Session Management**: Implement `_SessionState` to track and persist session configuration and history, enabling `resume_session` and `load_session` parity with Claude.
3.  **TodoWrite Interception**: Intercept tool calls representing planning/thinking (matching Claude's `TodoWrite` semantics) and emit `AgentPlanUpdate` notifications.
4.  **Tool Kind Mapping**: Use the same keyword-based mapping as `claude_bridge.py` to ensure consistent UI iconography.
5.  **Provider Integration**: Update `GeminiProvider.prepare_process` to spawn the Python bridge instead of the raw CLI.

## Rationale
A dedicated bridge layer is the only way to achieve protocol normalization without modifying the underlying model or CLI. It decouples the VaultSpec protocol from the provider's specific ACP implementation details, allowing for custom logic like planning interception and rich tool diffs which are essential for high-fidelity client integrations.

## Consequences

### Positive
- **Feature Parity**: Gemini agents gain multi-turn persistence, planning UIs, and rich tool feedback.
- **Architectural Consistency**: Both major providers follow the same bridge-based pattern.
- **Testing Rigor**: Enables end-to-end and unit testing of the Gemini ACP flow using the existing test infrastructure.

### Negative
- **Maintenance Overhead**: Adds another component to maintain within the `protocol/acp` layer.
- **Subprocess Complexity**: The bridge will likely spawn its own `gemini` subprocess, adding a layer of process management.

## References
- [[2026-02-22-gemini-acp-audit-expanded]]
- [[2026-02-21-claude-acp-bidirectional-adr]]
- [A2A Protocol Specification](https://a2a-protocol.org)
