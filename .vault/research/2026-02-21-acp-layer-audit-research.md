---
title: "ACP Layer Audit: Our Implementation"
date: 2026-02-21
tags: [acp, audit]
status: complete
source: "src/vaultspec/protocol/acp/"
agent: acp-auditor
---

# ACP Layer Audit

## File Map

- **`__init__.py`** — Re-exports: ClaudeACPBridge, SessionLogger, SubagentClient,
  SubagentError, SubagentResult
- **`types.py`** — SubagentError (Exception), SubagentResult (frozen dataclass:
  response_text, written_files, session_id)
- **`claude_bridge.py`** — ACP Agent server, 994 lines (detailed below)
- **`client.py`** — ACP Client implementation, 473 lines (detailed below)
- **`sandbox.py`** — Shared can_use_tool sandbox callbacks

## ClaudeACPBridge (`claude_bridge.py`)

Implements `acp.Agent` protocol. Spawned as subprocess by `ClaudeProvider.prepare_process()`,
communicates over JSON-RPC via `acp.run_agent()` (stdin/stdout).

### Session State

```python
@dataclass
class _SessionState:
    session_id: str
    cwd: str
    model: str
    mode: str
    mcp_servers: dict
    created_at: float
    sdk_client: Any = None
    connected: bool = True
```

### Key Methods

- **`on_connect(conn)`** — Stores conn reference for session_update callbacks
- **`initialize()`** — Returns capabilities: load_session=True, fork/list/resume
- **`_build_options()`** — Centralized option construction
- **`new_session()`** — Creates ClaudeSDKClient, connects, creates persistent stream
  iterator, stores _SessionState
- **`prompt()`** — Resets cancel flag, calls sdk_client.query(text), streams messages,
  maps to ACP updates; returns stop_reason
- **`cancel()`** — Sets _cancelled flag, calls interrupt() + disconnect()
- **`authenticate()`** — No-op
- **`load_session()`** — Reconnects SDK from stored state; **NOT conversation history**
- **`resume_session()`** — Identical to load_session; same limitation
- **`fork_session()`** — Clones config into new UUID; fresh SDK client
- **`list_sessions()`** — In-memory only; filters by cwd; no pagination
- **`set_session_mode()`** — Updates _mode, mutates _options via getattr
- **`set_session_model()`** — Updates _model, mutates _options via getattr

### Streaming Pipeline

SDK message types → ACP update types:

| SDK Event | ACP Update |
|-----------|------------|
| `StreamEvent(content_block_start, tool_use)` | tracks `_block_index_to_tool[index]` |
| `StreamEvent(content_block_delta, text_delta)` | `AgentMessageChunk` |
| `StreamEvent(content_block_delta, thinking_delta)` | `AgentThoughtChunk` |
| `StreamEvent(content_block_delta, input_json_delta)` | `ToolCallProgress(in_progress)` |
| `AssistantMessage(ToolUseBlock)` | `ToolCallStart(pending)` + caches in `_pending_tools` |
| `AssistantMessage(TextBlock/ThinkingBlock)` | **skipped** (already streamed) |
| `UserMessage(parent_tool_use_id)` | `ToolCallProgress(completed/failed)` |
| `SystemMessage` | `SessionInfoUpdate(title=subtype)` |
| `ResultMessage` | `SessionInfoUpdate(title="Result: ...")` |
| `MessageParseError` | caught, logged, skipped |

### Configuration

Supports full feature set via env vars and constructor:
- max_turns, budget_usd, allowed_tools, disallowed_tools
- effort, output_format, fallback_model, include_dirs
- system_prompt (passed as `{"type": "preset", "preset": "claude_code", "append": ...}`)

## SubagentClient (`client.py`)

Implements `acp.Client` protocol. Handles ACP messages FROM the bridge.

### Key Methods

- **`request_permission()`** — Auto-approves ALL tool calls (selects first allow option)
- **`session_update()`** — Routes ACP updates: AgentMessageChunk/AgentThoughtChunk →
  `_handle_content_chunk`; ToolCallStart → `on_tool_update` callback
- **`_handle_content_chunk()`** — Accumulates `response_text`; fires callbacks
- **`read_text_file()`** — Workspace-bounded file read with line/limit slicing
- **`write_text_file()`** — In read-only mode, only allows writes to `.vault/`
- **`create_terminal()`** — Blocked in read-only; Windows requires ProactorEventLoop;
  spawns subprocess with combined stdout+stderr
- **`terminal_output()`** — Returns accumulated output, truncates to byte_limit (keeps tail)
- **`wait_for_terminal_exit()`** — Awaits process + reader task
- **`close()`** — Kills all tracked terminals (zombie prevention)
- **`graceful_cancel()`** — Sends ACP cancel to conn before shutdown

## Issues Found

### 1. CONFIRMED BUG — `on_connect()` is a no-op but `_conn` is used

`client.py:447`: `on_connect(self, conn)` does `pass`. But `graceful_cancel()` at line 468
reads `self._conn` which is initialized to `None` and never assigned. `graceful_cancel()`
will silently do nothing. The conn passed to `on_connect` is discarded.

### 2. Session History NOT Persisted

`claude_bridge.py:526-568` (load_session), `claude_bridge.py:571-622` (resume_session):
Both restore configuration but NOT conversation history. The Claude SDK does not support
persistent message history across client instances. ACP clients expecting true session
resumption get fresh conversations.

### 3. Streaming Loop Catches All Exceptions as "refusal"

`claude_bridge.py:457-459`:
```python
except Exception:
    logger.exception(...)
    stop_reason = "refusal"
    break
```
Converts ALL streaming exceptions into "refusal". Network errors look identical to model
refusal. Should differentiate.

### 4. `_block_index_to_tool` and `_pending_tools` Never Cleared Between Turns

`claude_bridge.py:263-267`: These dicts accumulate across multiple `prompt()` calls.
In long sessions, stale entries could cause incorrect tool correlation. Low risk with
UUID-style IDs, but no explicit cleanup.

### 5. `set_session_mode/model` Mutate SDK Internals via getattr

`claude_bridge.py:728-732, 750-753`: Reaches into `self._sdk_client._options`. If SDK
changes internals, these silently fail (getattr returns None).

### 6. `fork_session` Creates Dead Stream Reference

`claude_bridge.py:657`: Assigns `self._stream = self._sdk_client.receive_messages().__aiter__()`
but `prompt()` uses `self._sdk_client.receive_response()`. Orphaned stream, resource leak.

### 7. Windows ProactorEventLoop Is a Runtime Error

`client.py:300-307`: Terminal creation raises RuntimeError if not using ProactorEventLoop.
Error says to set policy before starting loop, but loop is already running.

### 8. Authentication Is Entirely a No-Op

`claude_bridge.py:496-513`: Returns empty `AuthenticateResponse()` regardless. Claude auth
handled via env vars. Correct for current design but means ACP auth methods have no effect.

### 9. `cancel()` Calls `disconnect()` Without `await`

`claude_bridge.py:485`: If `disconnect()` is a coroutine, this silently fails to disconnect.
Resource leak on cancellation.

## Test Quality

All tests use real DI-injected recorders (`SDKClientRecorder`, `ConnRecorder`).
No mocks. Fully compliant with no-mocking rule.

Test coverage:
- **`test_bridge_lifecycle.py`** — Session creation, load, fork, list, cancel
- **`test_bridge_streaming.py`** — All message type → ACP update mappings
- **`test_bridge_resilience.py`** — Error handling, disconnection, edge cases
- **`test_e2e_bridge.py`** — Real subprocess bridge via JSON-RPC over asyncio pipes

Integration tests properly gated behind `@pytest.mark.integration` and `@pytest.mark.claude`.
