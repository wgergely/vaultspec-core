---
title: "claude-agent-sdk rate_limit_event Handling Gap"
tags: [sdk, streaming]
status: complete
date: 2026-02-21
---

# claude-agent-sdk `rate_limit_event` Handling Gap

## Summary

The `claude-agent-sdk` v0.1.39 `parse_message()` function raises `MessageParseError` when the Claude Code CLI emits a `rate_limit_event` message type during streaming. This is a **CLI-internal message type** not documented in the public Anthropic streaming API, but emitted by the Claude Code CLI process via its `--output-format stream-json` interface. The SDK's parser uses an exhaustive match with no fallback for unknown types, causing a hard crash.

---

## 1. SDK Internals

### 1.1 Installed Version

`claude-agent-sdk==0.1.39` (released 2026-02-19). This is the **latest version on PyPI** as of 2026-02-21.

### 1.2 Message Types Handled by `parse_message()`

File: `.venv/Lib/site-packages/claude_agent_sdk/_internal/message_parser.py`

The `match message_type` block at line 47 handles exactly **five** types:

| `type` value    | SDK dataclass     | Description                              |
|-----------------|-------------------|------------------------------------------|
| `"user"`        | `UserMessage`     | User input with content blocks           |
| `"assistant"`   | `AssistantMessage` | Model response with text/tool/thinking  |
| `"system"`      | `SystemMessage`   | System metadata (subtype-keyed)          |
| `"result"`      | `ResultMessage`   | Terminal message with cost/usage/session |
| `"stream_event"`| `StreamEvent`     | Partial SSE event for streaming          |

The wildcard `case _:` at line 179-180 raises `MessageParseError(f"Unknown message type: {message_type}", data)`. There is **no skip, filter, warn-and-continue, or callback mechanism** for unknown types.

### 1.3 Message Processing Pipeline

The full flow is:

```
Claude Code CLI process (subprocess)
  |
  | stdout: newline-delimited JSON (--output-format stream-json)
  v
SubprocessCLITransport._read_messages_impl()     [transport/subprocess_cli.py]
  |  Reads lines, buffers partial JSON, yields parsed dicts
  v
Query._read_messages()                            [_internal/query.py]
  |  Routes control_response / control_request / control_cancel_request
  |  Passes everything else into _message_send memory channel
  v
Query.receive_messages()                          [_internal/query.py]
  |  Reads from _message_receive channel, yields raw dicts
  v
ClaudeSDKClient.receive_messages()                [client.py:186]
  |  Calls parse_message(data) on each dict
  |  This is WHERE THE CRASH OCCURS
  v
Consumer (e.g., ClaudeA2AExecutor)
```

Key observation: `Query._read_messages()` passes **all** non-control messages through to the channel without filtering by type. The only types it intercepts are:
- `control_response` (routed to pending response handlers)
- `control_request` (dispatched to `_handle_control_request`)
- `control_cancel_request` (TODO: not implemented)
- `result` (sets `_first_result_event` flag, then also forwarded)

Everything else -- including `rate_limit_event` -- lands in `parse_message()`.

### 1.4 No Extension Mechanism

There is no:
- `on_unknown_message` callback
- Configuration to skip unknown types
- `try/except` wrapper around `parse_message` in `receive_messages()`
- Event filtering before parsing

### 1.5 TODO/FIXME in SDK Source

No TODO or FIXME comments exist related to message types or unknown events in the SDK source. There are TODOs for:
- Cancellation support (`control_cancel_request`)
- Abort signal support
- PermissionUpdate/PermissionMode types

---

## 2. Claude API Streaming Protocol vs. CLI Protocol

### 2.1 What `rate_limit_event` Is

`rate_limit_event` is **NOT** a documented Anthropic Messages API SSE event type. The documented SSE event types are:

- `message_start`
- `content_block_start`, `content_block_delta`, `content_block_stop`
- `message_delta`
- `message_stop`
- `ping`
- `error` (with subtypes like `overloaded_error`, `rate_limit_error`)

Source: [Streaming Messages - Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/streaming)

`rate_limit_event` is an **internal message type emitted by the Claude Code CLI** (the Node.js process) via its `stream-json` output format. The CLI interprets the underlying API rate limit (HTTP 429 or in-stream error event) and emits its own structured message type to inform SDK consumers. This is part of the CLI's internal protocol, which is **not fully documented externally** and evolves independently of the raw API.

### 2.2 Other Potentially Unhandled CLI Event Types

The Claude API docs explicitly state: "new event types may be added, and your code should handle unknown event types gracefully." The CLI wraps the API and may emit additional internal message types at any time. Besides `rate_limit_event`, potential future types could include:
- Billing/quota events
- Connection status events
- Retry notifications
- Compaction events

### 2.3 Wire Format

The CLI uses newline-delimited JSON over stdout (not SSE). Each line is a JSON object with a `type` field. The SDK sets `--output-format stream-json` and `--input-format stream-json` for bidirectional communication.

---

## 3. ClaudeA2AExecutor Integration

### 3.1 How the Executor Consumes the Stream

File: `src/vaultspec/protocol/a2a/executors/claude_executor.py`

The executor at lines 127-167 uses a manual iteration loop:

```python
_stream = sdk_client.receive_messages().__aiter__()
while True:
    try:
        msg = await _stream.__anext__()
    except StopAsyncIteration:
        break
    except MessageParseError as exc:
        exc_str = str(exc)
        if "rate_limit_event" in exc_str:
            raise RuntimeError(
                "Claude CLI rate limited - retry after the rate-limit window expires."
            ) from exc
        logger.debug("Skipping unparseable SDK message: %s", exc)
        continue
```

### 3.2 Where It Breaks

The crash path is:
1. `sdk_client.receive_messages()` calls `parse_message(data)` at `client.py:187`
2. `parse_message()` hits the wildcard case and raises `MessageParseError("Unknown message type: rate_limit_event", data)`
3. The executor catches `MessageParseError` and checks if `"rate_limit_event"` is in the string
4. If yes, it raises `RuntimeError` -- which propagates to the outer `except Exception` at line 182
5. The outer handler calls `updater.failed()` with the error message

### 3.3 Current Error Handling Strategy

The executor distinguishes:
- **`MessageParseError` with "rate_limit_event"**: Treated as fatal, raises `RuntimeError` which becomes a task failure
- **Other `MessageParseError`**: Logged at debug level, skipped (continues iteration)
- **`StopAsyncIteration`**: Normal stream end
- **Any other `Exception`**: Logged, task marked as failed

### 3.4 Problems with Current Approach

1. **String matching on error messages** is fragile -- SDK could change the error format
2. **Rate limit treated as fatal** -- the task fails immediately instead of retrying
3. **The `rate_limit_event` message likely contains retry-after metadata** (delay, window) that is completely lost because `parse_message` discards the raw data in the exception
4. **No retry mechanism** -- the A2A task goes straight to `failed` terminal state

---

## 4. A2A Protocol Task Lifecycle Implications

### 4.1 How Rate Limits Should Manifest

Per the [A2A Protocol specification](https://a2a-protocol.org/latest/specification/):

- Tasks have states: `pending`, `in-progress`, `completed`, `failed`, `canceled`, `rejected`
- A task in a **terminal state** (`completed`, `canceled`, `rejected`, `failed`) **cannot be restarted**
- The protocol recommends servers return appropriate error codes for temporary vs. permanent failures
- Servers MAY include retry guidance (e.g., `Retry-After` header)

Rate limiting is a **transient condition**, not a permanent failure. Current behavior marks the task as `failed` (terminal), which means:
- The client cannot retry via the same task
- The client must create a brand new task
- No retry-after guidance is communicated

### 4.2 Recommended A2A Behavior

For rate limits, the executor should either:

1. **Retry internally** with exponential backoff before surfacing failure, keeping the task in `in-progress` state
2. **Report a specific error code** (e.g., HTTP 429 equivalent) with retry-after metadata, so the A2A client can decide to retry
3. **At minimum**, not mark the task as permanently failed on the first rate limit encounter

---

## 5. Upstream SDK State

### 5.1 Version Currency

The installed version (`0.1.39`) is the latest release on [PyPI](https://pypi.org/project/claude-agent-sdk/) as of 2026-02-21. There is no newer version that fixes this issue.

### 5.2 Root Cause Analysis

The fundamental issue is a **design gap** in the SDK's `parse_message()` function: it uses an exhaustive match without a graceful fallback for unknown message types, despite the Claude Code CLI being free to emit new types at any time. The [Anthropic streaming docs](https://platform.claude.com/docs/en/build-with-claude/streaming) explicitly advise handling unknown event types gracefully ("Other events: new event types may be added, and your code should handle unknown event types gracefully").

The `MessageParseError` does preserve the raw `data` dict in its `.data` attribute, which means callers can inspect the original message. However, the SDK's `receive_messages()` generator propagates the exception rather than offering a filter-or-skip option.

---

## 6. Fix Options

### Option A: Patch the Executor (Local Workaround)

Improve `ClaudeA2AExecutor` to:
1. Catch `MessageParseError` and extract `.data` for the raw event payload
2. For `rate_limit_event`, parse retry-after metadata from `.data`
3. Implement retry with backoff instead of immediate failure
4. For other unknown types, continue skipping (current behavior)

**Pros**: No upstream dependency; immediately actionable.
**Cons**: Still relies on catching exceptions from the SDK for normal control flow.

### Option B: Monkey-Patch `parse_message` (Fragile)

Replace `parse_message` at import time to add a fallback case. Not recommended given the project's no-mocking policy and general fragility.

### Option C: Wrap at the Query Level

Subclass or wrap `Query.receive_messages()` to filter unknown types before they reach `parse_message()`. This would require access to SDK internals.

### Option D: Upstream SDK Fix

File an issue / PR against `claude-agent-sdk` to:
1. Add a catch-all case in `parse_message()` that returns a new `UnknownMessage` type (or logs and skips)
2. Add a callback/filter mechanism for unknown message types

**Pros**: Correct long-term fix.
**Cons**: Dependent on upstream release timeline.

### Recommended Approach

**Option A (immediate)** combined with **Option D (long-term)**. The executor should:
1. Extract the raw data from `MessageParseError.data` instead of string-matching
2. Check `exc.data.get("type") == "rate_limit_event"` for reliable identification
3. Parse any retry-after / delay metadata from the event
4. Implement a bounded retry loop (e.g., 3 attempts with exponential backoff)
5. Only fail the task after retries are exhausted

---

## 7. Key Files

| File | Role |
|------|------|
| `.venv/Lib/site-packages/claude_agent_sdk/_internal/message_parser.py` | Parser with exhaustive match (line 179) |
| `.venv/Lib/site-packages/claude_agent_sdk/client.py` | `receive_messages()` calls `parse_message()` (line 187) |
| `.venv/Lib/site-packages/claude_agent_sdk/_internal/query.py` | Message routing, no type filtering before channel |
| `.venv/Lib/site-packages/claude_agent_sdk/_internal/transport/subprocess_cli.py` | Raw JSON reading from CLI stdout |
| `.venv/Lib/site-packages/claude_agent_sdk/_errors.py` | `MessageParseError` definition with `.data` attribute |
| `.venv/Lib/site-packages/claude_agent_sdk/types.py` | `Message` union type (5 variants), `AssistantMessageError` includes `"rate_limit"` |
| `src/vaultspec/protocol/a2a/executors/claude_executor.py` | A2A executor with current workaround |

---

## 8. Additional Finding: `AssistantMessageError` Already Models Rate Limits

In `types.py` line 632-639:

```python
AssistantMessageError = Literal[
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "unknown",
]
```

The `AssistantMessage.error` field can be `"rate_limit"`, meaning the CLI can also signal rate limits via a normal `assistant` message with `error="rate_limit"`. The `rate_limit_event` appears to be a separate, more granular signal emitted mid-stream before the assistant message, possibly containing timing metadata for when to retry.

The executor does NOT currently check `AssistantMessage.error` -- it only looks at `TextBlock` content. This is a second gap: even when rate limits arrive through the supported `AssistantMessage` path, they are silently collected as empty text.
