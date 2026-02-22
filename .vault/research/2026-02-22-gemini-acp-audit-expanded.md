---
tags: ["#research", "#gemini-acp-audit"]
date: "2026-02-22"
related:
  - "[[2026-02-21-claude-acp-bidirectional-adr]]"
  - "[[2026-02-20-a2a-team-adr]]"
  - "[[2026-02-22-gemini-acp-audit-research]]"
---

# Expanded Research: Gemini ACP & A2A Parity Audit

## Overview
This research expands on the initial audit by looking deeper into the A2A executors and the missing bridge layer for Gemini. The goal is to achieve full feature parity with Claude's ACP/A2A implementation.

## Detailed Findings

### 1. ACP Architecture Gap
- **Claude**: `SubagentClient` <--> `ClaudeACPBridge` (Python) <--> `ClaudeSDKClient`. The bridge handles protocol normalization, session resume, and rich tool content.
- **Gemini**: `SubagentClient` <--> `gemini --experimental-acp`. No intermediate bridge. This makes it impossible to:
    - Map `TodoWrite` tool calls to `AgentPlanUpdate` notifications.
    - Map generic tool names to ACP `ToolKind` (e.g., "edit", "search").
    - Accumulate tool content (e.g., diffs for Edit tools).
    - Handle session resume if the CLI process is terminated.

### 2. A2A Executor Gap
- **`ClaudeA2AExecutor`**:
    - Supports `resume` via `session_id` persistence keyed by `context_id`.
    - Corrects `CLAUDECODE` environment variable to prevent conflicts.
    - Handles rate-limit retries with exponential back-off.
    - Non-destructive `cancel()`: interrupts the stream but keeps the client/session alive.
- **`GeminiA2AExecutor`**:
    - No `resume` support. Every task spawns a fresh `gemini` CLI subprocess.
    - No session persistence. Conversation history within an A2A `context_id` is lost between tasks unless explicitly injected into the prompt.
    - `cancel()` is likely destructive (process termination).

### 3. Protocol Implementation Gaps in `SubagentClient`
- `SubagentClient` (`src/vaultspec/protocol/acp/client.py`) does not handle `AgentPlanUpdate` in `session_update`. It logs it but doesn't call a callback for UI rendering.
- `AgentThoughtChunk` is handled but `AgentPlanUpdate` (the "Thinking" vs "Planning" distinction in Zed) is lost at the client level.

### 4. Testing Gaps
- `src/vaultspec/protocol/acp/tests/` contains 11 test files, almost all tailored for `ClaudeACPBridge`.
- There are no equivalent "rigorous" tests for Gemini's ACP flow (lifecycle, streaming, reliability, resilience).
- Existing Gemini tests (`tests/e2e/test_gemini.py`) are basic single-turn functional tests.

## Proposed Strategy

### Phase 1: Implement `GeminiACPBridge`
- Create `src/vaultspec/protocol/acp/gemini_bridge.py`.
- It should wrap the `gemini` CLI (using its `--experimental-acp` mode) but intercept/normalize the protocol.
- Implement `TodoWrite` (or equivalent) interception.
- Implement tool kind mapping and content accumulation.

### Phase 2: Update `GeminiProvider`
- Change `prepare_process` to spawn `python -m vaultspec.protocol.acp.gemini_bridge`.
- Ensure it passes the necessary configuration to the bridge.

### Phase 3: Enhance `GeminiA2AExecutor`
- Implement `session_id` persistence similar to `ClaudeA2AExecutor`.
- Use the new bridge's `resume` capability (once implemented).

### Phase 4: Rigorous Testing
- Mirror `test_bridge_*.py` for Gemini.
- Validate multi-turn interactive sessions and bidirectional A2A relays.

## Conclusion
The lack of a dedicated bridge for Gemini is the root cause of the feature asymmetry. By implementing `GeminiACPBridge`, we can centralize protocol normalization and session management, bringing Gemini to the same "rigorous" standard as Claude.
