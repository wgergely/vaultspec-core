---
tags:
  - "#research"
  - "#a2a"
date: "2026-02-21"
---
# A2A Reference Implementation: python-a2a

## Overview

Python A2A library (980 stars) with two distinct layers:
1. A **custom A2A protocol** (their own `python_a2a` format using `content`/`role` dict)
2. A **Google A2A compatibility layer** (`parts`-array format with JSON-RPC)

Our vaultspec implementation uses the **official Google A2A SDK** (`a2a-sdk`), which is
entirely different. The two are not directly comparable as "right vs wrong" — they implement
different variants of the A2A spec.

## Key Files

- `python_a2a/client/llm/anthropic.py` — AnthropicA2AClient
- `python_a2a/server/llm/anthropic.py` — AnthropicA2AServer
- `python_a2a/server/a2a_server.py` — Full A2A server with JSON-RPC
- `python_a2a/client/http.py` — HTTP client
- `python_a2a/models/task.py` — Task lifecycle model
- `python_a2a/models/agent.py` — AgentCard model

## 1. AnthropicA2AClient

Uses `anthropic.Anthropic(api_key=...)` — the **synchronous** Anthropic SDK directly.
NOT `claude-agent-sdk`. Calls `self.client.messages.create(...)` — simple REST API calls.

Key patterns:
- In-memory `_conversation_histories` dict keyed by `conversation_id`
- `send_message(message) -> Message` — single round-trip
- `send_conversation(conversation) -> Conversation` — multi-turn
- Handles `tool_use` responses by inspecting `response.content` for `content_item.type == "tool_use"`
- Falls back to regex parsing of `<tool>` XML tags for older models

```python
for content_item in response.content:
    if content_item.type == "tool_use":
        return Message(content=FunctionCallContent(...), role=MessageRole.AGENT)
```

**Why this works:** Direct Anthropic Messages API. No `claude-agent-sdk`, no subprocess.
No `rate_limit_event` parse errors — rate limits handled at HTTP level (429 + retry-after).

## 2. AnthropicA2AServer

Uses `anthropic.Anthropic` sync + `AsyncAnthropic` for streaming.

- `handle_message(message) -> Message` — calls `client.messages.create()`
- `handle_task(task) -> Task` — wraps `handle_message`, sets `task.artifacts` and `task.status`
- `handle_conversation(conversation) -> Conversation` — manages full conversation history
- `stream_response(message) -> AsyncGenerator[str, None]` — `AsyncAnthropic` with `stream=True`

Streaming pattern:
```python
stream = await self.async_client.messages.create(**kwargs)
async with stream as response:
    async for chunk in response:
        if chunk.type == "content_block_delta" and chunk.delta.type == "text":
            yield chunk.delta.text
```

Key: Separate `AsyncAnthropic` client for streaming, sync `Anthropic` for regular calls.

## 3. Protocol Models

### Message

```
Message:
  content: TextContent | FunctionCallContent | FunctionResponseContent | ErrorContent
  role: MessageRole (user | agent | system)
  message_id: str (UUID)
  parent_message_id: Optional[str]
  conversation_id: Optional[str]
```

### Task

```
Task:
  id: str (UUID)
  session_id: str (UUID)
  status: TaskStatus(state: TaskState, message: dict, timestamp: str)
  message: dict
  history: list
  artifacts: [{"parts": [{"type": "text", "text": "..."}]}]
  metadata: dict

TaskState: submitted | waiting | input-required | completed | canceled | failed | unknown
```

Note: `submitted` and `waiting` states not present in our implementation.

### AgentCard

```
AgentCard:
  name, description, url, version
  protocol_version: "0.3.0"
  preferred_transport: "JSONRPC"
  capabilities: {streaming, pushNotifications, stateTransitionHistory}
  default_input_modes, default_output_modes: ["text/plain"]
  skills: [AgentSkill(name, description, id, tags, examples, input_modes, output_modes)]
```

## 4. HTTP Server Transport

Flask-based with SSE for streaming.

Key endpoints:
- `GET /.well-known/agent.json` — agent card (A2A standard)
- `POST /a2a/tasks/send` — JSON-RPC tasks/send
- `POST /a2a/tasks/get` — JSON-RPC tasks/get
- `POST /a2a/tasks/cancel` — JSON-RPC tasks/cancel
- `POST /a2a/tasks/stream` — JSON-RPC tasks/sendSubscribe (SSE)

JSON-RPC method: `tasks/send` — NOT `message/send` as our implementation uses.

## 5. HTTP Client

Sophisticated with fallback:
1. First tries task-based endpoints (`/tasks/send`, `/a2a/tasks/send`)
2. Falls back to direct message POST
3. Auto-detects between python_a2a format and Google A2A format
4. Supports streaming via aiohttp + SSE parsing

## 6. Key Differences from Our Implementation

| Aspect | python-a2a | Our vaultspec |
|---|---|---|
| A2A SDK | Custom (Flask + requests) | Official `a2a-sdk` (Google) |
| Anthropic integration | Direct `anthropic.Anthropic` REST | `claude-agent-sdk` subprocess |
| Transport | HTTP (Flask server) | ASGI (Starlette) |
| JSON-RPC method | `tasks/send` | `message/send` |
| Streaming | SSE via Flask | ASGI streaming |
| Tool use | Native Anthropic API tool_use | claude-agent-sdk tool handling |
| Rate limit handling | HTTP 429 (transparent) | `rate_limit_event` parse error |
| Conversation history | In-memory dict per conversation_id | Stateless per task |

## 7. Why It Works and Ours Doesn't

Root difference: **python-a2a calls the Anthropic API directly** via
`client.messages.create()`. Simple synchronous REST with no subprocess. Rate limits
are standard HTTP 429 responses handled by the SDK's retry logic.

Our `claude-agent-sdk` spawns a Claude CLI subprocess and streams its output. The upstream
SDK fails to parse `rate_limit_event` messages → `MessageParseError`.

The reference's approach:
1. Create `anthropic.Anthropic(api_key=...)` client
2. Build messages list from conversation history
3. Call `client.messages.create(model=..., max_tokens=..., messages=...)`
4. Inspect `response.content` for `tool_use` or `text` blocks
5. Update conversation history for next turn

This is the canonical, reliable way to call Claude.
