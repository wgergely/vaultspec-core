---
tags:
  - "#research"
  - "#acp"
date: "2026-02-21"
---
# ACP Reference Implementation: acp-claude-code

## Overview

TypeScript implementation (235 stars) that successfully bridges Claude Code with ACP.
Published as npm package. Deprecated in favor of `@zed-industries/claude-code-acp` but
contains excellent, well-documented code.

**Files studied:**
- `src/agent.ts` (core — ClaudeACPAgent)
- `src/types.ts`
- `src/utils.ts`
- `src/index.ts`
- `src/cli.ts`
- `package.json`

## 1. Core Agent: ClaudeACPAgent

Implements `@zed-industries/agent-client-protocol`'s `Agent` interface. Instantiated with
a `Client` object injected via constructor.

### Session State

```typescript
interface AgentSession {
  pendingPrompt: AsyncIterableIterator<SDKMessage> | null;
  abortController: AbortController | null;
  claudeSessionId?: string;          // lazy — filled from first SDK message
  permissionMode?: "default" | "acceptEdits" | "bypassPermissions" | "plan";
  todoWriteToolCallIds: Set<string>;
  toolCallContents: Map<string, ACPToolCallContent[]>;
}
```

### Key Methods

- **`initialize()`** — Returns protocol version + capabilities: `loadSession: true`,
  `image: true`, `embeddedContext: true`.
- **`newSession()`** — Creates random ACP session ID. `claudeSessionId` is initially
  `undefined` — filled lazily from first SDK message containing `session_id`.
- **`loadSession()`** — If session in map, keeps `claudeSessionId`. If not, creates
  fresh state. Handles client reconnects after bridge restarts.
- **`authenticate()`** — No-op. Claude Code SDK uses `~/.claude/config.json`.

## 2. Session Persistence & Resume (Critical Pattern)

The key mechanism — completely different from our Python implementation:

- Uses `@anthropic-ai/claude-code`'s `query()` function: a **stateless call** returning
  an async iterable.
- Session resume via `resume: session.claudeSessionId` option passed to `query()`.
- `claudeSessionId` extracted from any SDK message with `session_id` field via
  `tryToStoreClaudeSessionId()`.
- Multi-turn = multiple separate `query()` calls, each resuming by passing stored session ID.

**Our gap:** We never extract Claude's native `session_id` from messages and never pass
it as a `resume` parameter. The reference does this automatically.

## 3. Streaming Architecture

```typescript
const messages = query({
  prompt: toAsyncIterable([userMessage]) as any,
  options: { permissionMode, resume: session.claudeSessionId || undefined },
});

for await (const message of messages) {
  // check abort
  // extract session_id
  // dispatch to handleClaudeMessage()
}
```

`query()` yields messages as `AsyncIterable<SDKMessage>`. Each `prompt()` runs a fresh
iterable — no persistent connection needed.

## 4. Message Type Handling

`handleClaudeMessage()` handles ALL SDK message types:

| Type | Handling |
|------|----------|
| `system` | Silently ignored |
| `user` | Processes `tool_result` blocks → `tool_call_update` with `status: "completed"` |
| `assistant` | text → `agent_message_chunk`; tool_use → `tool_call` (or `plan` if TodoWrite) |
| `result` | Logged, not emitted |
| `text` | Direct text → `agent_message_chunk` |
| `tool_use_start` | `tool_call` with `status: "pending"` (or `plan` if TodoWrite) |
| `tool_use_output` | `tool_call_update` with `status: "completed"` + accumulated content |
| `tool_use_error` | `tool_call_update` with `status: "failed"` |
| `stream_event` | `content_block_delta` with `text_delta` → `agent_message_chunk` |

## 5. Tool Call Mapping

`mapToolKind()` maps tool names by substring matching:
- `read/view/get` → `"read"`
- `write/create/update/edit` → `"edit"`
- `delete/remove` → `"delete"`
- `move/rename` → `"move"`
- `search/find/grep` → `"search"`
- `run/execute/bash` → `"execute"`
- `think/plan` → `"think"`
- `fetch/download` → `"fetch"`
- else → `"other"`

`getToolCallContent()` for `Edit` tool emits `diff` content block with `path`, `oldText`,
`newText`. For `MultiEdit`: multiple diff blocks. All others: empty content array.

**Our gap:** We emit `ToolCallStart` with just `title` and `status`. No `kind`, `content`,
or `rawInput`. No diff content blocks.

## 6. TodoWrite to Plan Conversion

Intercepted at TWO points:

1. **`tool_use_start`** (streaming): If `tool_name === "TodoWrite"` and input has `todos`,
   calls `sendAgentPlan()` and tracks `tool_call_id` in `todoWriteToolCallIds`.
2. **`assistant` message**: If `content.name === "TodoWrite"`, calls `sendAgentPlan()`.

`sendAgentPlan()` emits ACP `plan` update with entries mapped from todos. TodoWrite tool
results are **suppressed** — not emitted as `tool_call` or `tool_call_update`.

**Our gap:** We do not handle TodoWrite at all.

## 7. Tool Call Content Accumulation

Accumulates content across the lifecycle:
- On `tool_use_start`/`tool_use`: stores initial `ACPToolCallContent[]` (diff blocks for Edit)
- On `tool_use_output`/`tool_result`: prepends prior content, adds new `content` block
- Sends cumulative array on each update

**Our gap:** We only send status on completion — no content accumulation.

## 8. Input Content Block Handling

`prompt()` handles four ACP prompt block types:
- `text` → appended to `textMessagePieces`
- `image` → base64 image block added to SDK message content
- `resource` → `file://` URI → `@/path/to/file` (Claude's @-mention syntax)
- `resource_link` → same URI handling

**Our gap:** Only text blocks extracted. Images and resources dropped.

## 9. Permission Mode

Supports dynamic switching via special prompt markers:
- `[ACP:PERMISSION:ACCEPT_EDITS]`
- `[ACP:PERMISSION:BYPASS]`
- `[ACP:PERMISSION:DEFAULT]`

Stored per-session, passed to each `query()` call.

**Our gap:** Fixed `bypassPermissions` for all sessions.

## 10. Abort/Cancel

Uses `AbortController` per-session. `cancel()` calls `abort()` then `.return()` on
pending iterator. Clean async-safe pattern.

**Our gap:** Boolean `_cancelled` flag + sync `interrupt()`/`disconnect()`.

## 11. Error Handling

Catches errors in `prompt()`, emits error as `agent_message_chunk`, returns
`stopReason: "end_turn"`. Unknown message types fall to `default:` with debug
logging — no exception thrown.

## 12. Dependencies

```json
"dependencies": {
  "@anthropic-ai/claude-code": "latest",
  "@zed-industries/agent-client-protocol": "0.1.2"
}
```

Two dependencies only. Transport: `AgentSideConnection` with stdin/stdout Web Streams.
