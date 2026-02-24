---
tags:
  - "#research"
  - "#gemini-acp-audit"
date: "2026-02-22"
related:
  - "[[2026-02-21-claude-acp-bidirectional-adr]]"
  - "[[2026-02-21-claude-acp-bidirectional-reference]]"
---
# Research: Gemini ACP Audit & Gap Analysis

## Context
The project aims to provide feature parity between Claude and Gemini providers within the VaultSpec ecosystem. The Claude implementation uses a sophisticated ACP (Agent Control Protocol) bridge (`claude_bridge.py`) that wraps the Claude SDK to provide multi-turn conversations, rich tool interactions, and structured planning (`TodoWrite` -> `AgentPlanUpdate`). This audit evaluates the current Gemini implementation against this reference architecture.

## Reference Architecture (Claude ACP)
Based on `src/vaultspec/protocol/acp/claude_bridge.py` and `.vault/adr/2026-02-21-claude-acp-bidirectional-adr.md`:

1.  **Bridge Pattern**: A dedicated Python process (`ClaudeACPBridge`) wraps the underlying SDK.
2.  **Session Management**:
    - Implements `load_session`, `resume_session`, `fork_session` via SDK client lifecycle management.
    - Persists session configuration (model, mode, MCP servers) and reconnects using `session_id` for context resumption.
3.  **Rich Tool Support**:
    - **Content Accumulation**: Accumulates tool output and emits rich `ToolCallStart`/`ToolCallProgress` events with `content` (including structured diffs for `Edit` tools) and mapped `kind`.
    - **Kind Mapping**: Maps tool names (e.g., "Edit") to ACP kinds (e.g., "edit").
4.  **Planning Interception**:
    - Intercepts `TodoWrite` tool calls (used by Claude for planning).
    - Converts them to `AgentPlanUpdate` notifications for the client (e.g., Zed plan panel).
    - Suppresses raw tool calls for `TodoWrite` to avoid noise.
5.  **Cancellation**:
    - Uses `asyncio.Event` for per-session non-destructive cancellation.
    - Interrupts the stream without killing the session.

## Current Gemini Implementation Status
Based on `src/vaultspec/protocol/providers/gemini.py`:

1.  **Direct CLI Execution**: `GeminiProvider` prepares a `ProcessSpec` that executes the `gemini` CLI directly with the `--experimental-acp` flag.
2.  **No Bridge**: There is no `src/vaultspec/protocol/acp/gemini_bridge.py`.
3.  **No Known Plan Support**: The `gemini` CLI is unlikely to natively support the specific `TodoWrite` -> `AgentPlanUpdate` conversion pattern required by VaultSpec/Zed.
4.  **No Test Coverage**: `src/vaultspec/protocol/acp/tests/` contains only Claude-specific tests.

## Gap Analysis

| Feature | Claude Implementation | Gemini Implementation | Gap Severity |
| :--- | :--- | :--- | :--- |
| **ACP Bridge** | `ClaudeACPBridge` (Python) | None (Direct CLI) | **Critical** |
| **Plan Support** | `TodoWrite` -> `AgentPlanUpdate` | Missing | **High** |
| **Tool Diffs** | Structured `FileEditToolCallContent` | Raw text (presumed) | **Medium** |
| **Tool Kind** | Mapped (e.g., `edit`, `read`) | Unknown/Generic | **Medium** |
| **Session Resume** | `resume_session` with history | CLI-dependent (likely stateless) | **High** |
| **Cancellation** | Non-destructive `interrupt()` | Process termination (likely) | **Medium** |

### 1. Missing Bridge (Critical)
The lack of a bridge means VaultSpec has no control over the protocol translation. We cannot inject custom logic for planning, logging, or normalizing tool behavior. Relying on `--experimental-acp` in the `gemini` CLI couples VaultSpec tightly to the CLI's internal implementation, which may diverge from the VaultSpec/Claude reference.

### 2. Planning & TodoWrite (High)
The `TodoWrite` tool is a key part of the agentic workflow (used for "Thinking" and "Planning" display in UIs). Without a bridge to intercept a similar planning tool from Gemini (or `TodoWrite` itself if injected), this feature is completely absent.

### 3. Session Management (High)
The `claude_bridge.py` manages `_SessionState` to allow `load_session` to reconnect to an existing context. If the `gemini` CLI is stateless or doesn't expose an API to "attach" to a session ID with history, multi-turn conversations across `prompt()` calls (or client restarts) will fail or lose context.

## Recommendations

1.  **Implement `GeminiACPBridge`**:
    - Create `src/vaultspec/protocol/acp/gemini_bridge.py`.
    - It should implement the ACP `Agent` protocol (using `acp` library).
    - It should wrap the `google-generativeai` Python SDK (or `gemini` CLI in subprocess if SDK is insufficient) to maintain control over the session lifecycle.

2.  **Align Features**:
    - **Session**: Implement `_SessionState` tracking similar to `ClaudeACPBridge`.
    - **Tools**: Implement `TodoWrite` interception (and inject `TodoWrite` tool definition into the system prompt if Gemini doesn't have it natively).
    - **Diffs**: Implement `_get_tool_call_content` logic to parse Gemini tool calls into structured diffs.

3.  **Add Test Coverage**:
    - Create `src/vaultspec/protocol/acp/tests/test_gemini_bridge.py`.
    - Mirror the lifecycle and streaming tests from `claude_bridge` tests.

4.  **Update Provider**:
    - Modify `GeminiProvider.prepare_process` to spawn `python -m vaultspec.protocol.acp.gemini_bridge` instead of the raw `gemini` CLI.

## Conclusion
To achieve feature parity, a dedicated `GeminiACPBridge` is required. The current direct-CLI approach leaves significant functional gaps, particularly in session management and rich UI integration (Plans/Diffs).
