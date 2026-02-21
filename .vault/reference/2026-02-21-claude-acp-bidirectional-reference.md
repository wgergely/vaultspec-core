---
title: "Claude ACP Bidirectional Communication Reference"
date: 2026-02-21
tags: [acp, reference]
status: complete
source: "tmp-ref/acp-claude-code (github.com/Xuanwo/acp-claude-code, v0.8.0)"
related:
  - "[[2026-02-21-protocol-gap-analysis-research]]"
  - "[[2026-02-21-acp-ref-impl-research]]"
  - "[[2026-02-21-acp-layer-audit-research]]"
---

# Claude ACP Bidirectional Communication Reference

## Crates / Packages

| Package | Role |
|---------|------|
| `@anthropic-ai/claude-code` | Claude Code TypeScript SDK -- provides `query()` function |
| `@zed-industries/agent-client-protocol` | ACP protocol types and `AgentSideConnection` transport |
| `claude-agent-sdk` (Python) | Our Python SDK -- provides `ClaudeSDKClient` |
| `acp` (Python) | Our ACP protocol implementation -- provides `Agent`, `run_agent` |

## Files Audited

| File | Path | Lines | Role |
|------|------|-------|------|
| agent.ts | `tmp-ref/acp-claude-code/src/agent.ts` | 1-765 | Core `ClaudeACPAgent` -- ALL bidirectional logic |
| types.ts | `tmp-ref/acp-claude-code/src/types.ts` | 1-73 | Message types, tool call content types |
| utils.ts | `tmp-ref/acp-claude-code/src/utils.ts` | 1-5 | `toAsyncIterable()` helper |
| index.ts | `tmp-ref/acp-claude-code/src/index.ts` | 1-80 | Entry point -- `AgentSideConnection` with stdio |
| cli.ts | `tmp-ref/acp-claude-code/src/cli.ts` | 1-8 | CLI entry |
| claude_bridge.py | `src/vaultspec/protocol/acp/claude_bridge.py` | 1-987 | Our ACP bridge (comparison target) |
| client.py | `src/vaultspec/protocol/acp/client.py` | 1-473 | Our ACP client (comparison target) |
| types.py (SDK) | `.venv/Lib/site-packages/claude_agent_sdk/types.py` | 1-860 | SDK types -- `ClaudeAgentOptions.resume` field |
| client.py (SDK) | `.venv/Lib/site-packages/claude_agent_sdk/client.py` | 1-413 | SDK `ClaudeSDKClient` -- `receive_response()` method |
| message_parser.py (SDK) | `.venv/Lib/site-packages/claude_agent_sdk/_internal/message_parser.py` | 1-181 | SDK message parsing -- where `rate_limit_event` fails |

---

## 1. Session Resume End-to-End

### 1.1 Reference Architecture (TypeScript)

The reference uses `@anthropic-ai/claude-code`'s **stateless `query()` function** rather than
a persistent client connection. Each `prompt()` call creates a fresh `query()` invocation,
and session continuity is achieved by passing a `resume` parameter with the Claude session ID.

**Key mechanism: `tryToStoreClaudeSessionId()`**

```
File: tmp-ref/acp-claude-code/src/agent.ts, lines 746-764

private tryToStoreClaudeSessionId(sessionId: string, sdkMessage: SDKMessage) {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return;
    }
    if (
      "session_id" in sdkMessage &&
      typeof sdkMessage.session_id === "string" &&
      sdkMessage.session_id
    ) {
      if (session.claudeSessionId !== sdkMessage.session_id) {
        this.log(
          `Updating Claude session_id from ${session.claudeSessionId} to ${sdkMessage.session_id}`,
        );
        session.claudeSessionId = sdkMessage.session_id;
        return sdkMessage.session_id;
      }
    }
  }
```

**How it works:**

1. Every SDK message is checked for a `session_id` field
2. The TypeScript SDK's `SDKMessage` type includes `session_id` on several message types
3. The first message that carries a `session_id` populates `session.claudeSessionId`
4. Subsequent `query()` calls pass this as `resume: session.claudeSessionId`

### 1.2 Full Session Lifecycle

```
                    REFERENCE (TypeScript)
                    ======================

newSession()                          loadSession()
    |                                      |
    v                                      v
sessions.set(id, {                    if sessions.has(id):
  claudeSessionId: undefined,            keep claudeSessionId
  pendingPrompt: null,                else:
  abortController: null,                 sessions.set(id, fresh)
  permissionMode: "default",
  todoWriteToolCallIds: new Set(),
  toolCallContents: new Map(),
})
    |
    v
prompt() -- Turn 1
    |
    v
query({
  prompt: toAsyncIterable([userMsg]),
  options: {
    permissionMode,
    resume: undefined,         <-- No resume on first turn
  },
})
    |
    v
for await (const message of messages) {
    tryToStoreClaudeSessionId(sessionId, message)  <-- Captures session_id
    handleClaudeMessage(sessionId, message)
}
    |
    v
session.claudeSessionId = "sess_abc123"   <-- Now populated
    |
    v
prompt() -- Turn 2
    |
    v
query({
  prompt: toAsyncIterable([userMsg]),
  options: {
    permissionMode,
    resume: "sess_abc123",     <-- RESUMES previous conversation
  },
})
```

### 1.3 Where session_id Appears in SDK Messages

From the Python SDK's `claude_agent_sdk/types.py`:

| Message Type | Has `session_id`? | Location |
|-------------|-------------------|----------|
| `ResultMessage` | YES -- `session_id: str` (required field) | line 679 |
| `StreamEvent` | YES -- `session_id: str` (required field) | line 691 |
| `UserMessage` | NO | |
| `AssistantMessage` | NO | |
| `SystemMessage` | NO | |

The Python SDK's `ResultMessage` and `StreamEvent` both carry `session_id`.
The `ResultMessage` is guaranteed to appear at the end of each response.
The `StreamEvent` appears early and often during streaming (when `include_partial_messages=True`).

**Therefore: the earliest opportunity to capture `session_id` is from the first `StreamEvent`.**

### 1.4 Our Current Implementation (Python) -- THE GAP

```
File: src/vaultspec/protocol/acp/claude_bridge.py

class _SessionState:                     # line 148-159
    session_id: str
    cwd: str
    model: str
    mode: str
    mcp_servers: list[Any]
    created_at: str
    sdk_client: ClaudeSDKClient | None   # NEVER USED
    connected: bool

    # MISSING: claude_session_id: str | None = None
    # MISSING: No session_id extraction from messages
    # MISSING: No resume parameter passed to query()
```

**What we do in `prompt()`:**

```python
# line 439
await self._sdk_client.query(prompt_text)
```

We call `query()` with just the prompt text. We never:
1. Extract `session_id` from `StreamEvent` or `ResultMessage`
2. Store it in `_SessionState`
3. Pass `resume` to `ClaudeAgentOptions`

**The Python SDK `ClaudeAgentOptions` already supports `resume`:**

```
File: .venv/Lib/site-packages/claude_agent_sdk/types.py, line 725

@dataclass
class ClaudeAgentOptions:
    ...
    resume: str | None = None           # <-- EXISTS, WE NEVER USE IT
```

### 1.5 What Must Change

The fix must handle two fundamentally different approaches:

**Approach A -- Stateless `query()` per turn (matching reference)**
- Each `prompt()` creates a fresh SDK `query()` call
- Pass `resume: stored_session_id` on subsequent turns
- This matches how `@anthropic-ai/claude-code` works

**Approach B -- Persistent `ClaudeSDKClient` connection (what we have)**
- Our `ClaudeSDKClient` maintains a persistent subprocess connection
- We call `client.query(prompt_text)` which sends a user message over the existing pipe
- Session continuity is handled by the persistent process
- BUT: we still need to capture `session_id` for ACP's `loadSession`/`resumeSession`

**We should use Approach B** (persistent client) since that is what `claude-agent-sdk` is
designed for, but we MUST extract `session_id` from messages for session restore after
bridge restart. The key difference is:

- Reference creates new `query()` per turn, needs `resume` every time
- We keep a persistent `ClaudeSDKClient`, but need `resume` for `load_session`/`resume_session`
  when recreating the client after disconnect

---

## 2. Multi-Turn Prompt Cycling

### 2.1 Reference Pattern

```
File: tmp-ref/acp-claude-code/src/agent.ts, lines 132-323

async prompt(params: PromptRequest): Promise<PromptResponse> {
    const session = this.sessions.get(params.sessionId);

    // Cancel any pending prompt
    if (session.abortController) {
      session.abortController.abort();       // <-- Kill previous turn
    }
    session.abortController = new AbortController();

    try {
      // Build user message from ACP prompt blocks
      const userMessage = { type: "user", message: { role: "user", content: [] } };
      // ... extract text, images, resources ...

      // Start NEW query per turn
      const messages = query({
        prompt: toAsyncIterable([userMessage]),
        options: {
          permissionMode,
          resume: session.claudeSessionId || undefined,
        },
      });

      session.pendingPrompt = messages;

      for await (const message of messages) {
        if (session.abortController?.signal.aborted) {
          return { stopReason: "cancelled" };
        }
        tryToStoreClaudeSessionId(sessionId, message);
        await handleClaudeMessage(sessionId, message);
      }

      session.pendingPrompt = null;
      return { stopReason: "end_turn" };
    } catch (error) {
      // Send error as agent_message_chunk, return end_turn
    } finally {
      session.pendingPrompt = null;
      session.abortController = null;
    }
}
```

**State preservation between turns:**

| State | Persists? | Notes |
|-------|-----------|-------|
| `claudeSessionId` | YES | Extracted from first message, used as `resume` |
| `pendingPrompt` | NO | Reset to `null` in `finally` |
| `abortController` | NO | Fresh `AbortController` per turn |
| `permissionMode` | YES | Persists across turns, can be changed mid-prompt |
| `todoWriteToolCallIds` | YES | Accumulates across turns |
| `toolCallContents` | YES | Accumulates across turns |

**What gets reset vs. persists in reference:**

```
                   +-- Per-Session (Map) --+
                   |                       |
  Persists:        | claudeSessionId       |  <-- Extracted from stream
                   | permissionMode        |  <-- Set once, changeable
                   | todoWriteToolCallIds  |  <-- Grows across turns
                   | toolCallContents      |  <-- Grows across turns
                   |                       |
  Per-Turn:        | pendingPrompt         |  <-- Set in prompt(), null in finally
                   | abortController       |  <-- Fresh per prompt()
                   +-----------------------+
```

### 2.2 Our Current Pattern

```python
# src/vaultspec/protocol/acp/claude_bridge.py

async def prompt(self, prompt, session_id, **kwargs):
    self._cancelled = False                    # Reset cancel flag
    prompt_text = _extract_prompt_text(prompt)
    await self._sdk_client.query(prompt_text)  # Send to persistent client

    stop_reason = "end_turn"
    async for message in self._sdk_client.receive_response():
        if self._cancelled:
            stop_reason = "cancelled"
            break
        await self._emit_updates(message, session_id)
        if isinstance(message, ResultMessage):
            if getattr(message, "is_error", False):
                stop_reason = "refusal"
    return PromptResponse(stop_reason=stop_reason)
```

**Differences:**

| Aspect | Reference | Ours |
|--------|-----------|------|
| Turn isolation | Fresh `query()` per turn | Reuses persistent `ClaudeSDKClient` |
| Cancel mechanism | `AbortController` per turn | Boolean `_cancelled` flag |
| Iterator lifecycle | Fresh `AsyncIterableIterator` per turn | Fresh `receive_response()` generator per turn |
| Session resume | `resume: claudeSessionId` | NONE |
| Error handling | `catch` emits error chunk, returns `end_turn` | `except` returns `refusal` |
| Pending prompt tracking | `session.pendingPrompt` | None |

### 2.3 Critical Issue: `_cancelled` Flag Is Global

Our `_cancelled` flag is a single boolean on the bridge instance, not per-session.
If we ever support concurrent sessions, one cancel would affect all sessions.

The reference uses a per-session `AbortController` -- each session has its own
abort signal that only affects that session's streaming loop.

---

## 3. Bidirectional Streaming -- Message Type Map

### 3.1 Reference: Complete Message Flow

```
                     CLIENT                          AGENT (Bridge)                     CLAUDE SDK
                    (Zed/ACP)                        (acp-claude-code)                  (@anthropic-ai/claude-code)
                       |                                   |                                  |
                       |--- PromptRequest(prompt) -------->|                                  |
                       |                                   |--- query({prompt, options}) ---->|
                       |                                   |                                  |
                       |                                   |<--- system message --------------|
                       |                                   |  (silently ignored)              |
                       |                                   |                                  |
                       |                                   |<--- stream_event (text_delta) ---|
                       |<-- agent_message_chunk ----------|                                  |
                       |                                   |                                  |
                       |                                   |<--- stream_event (thinking) -----|
                       |<-- agent_thought_chunk -----------|   (NOT in reference, we add this)|
                       |                                   |                                  |
                       |                                   |<--- stream_event (content_block_ |
                       |                                   |     start, tool_use) ------------|
                       |  (reference: no emit for this)    |  (we: populate _block_index_to_  |
                       |                                   |   tool map)                      |
                       |                                   |                                  |
                       |                                   |<--- assistant message ------------|
                       |                                   |     (text blocks + tool_use)     |
                       |<-- agent_message_chunk (text) ----|                                  |
                       |<-- tool_call (pending) -----------|                                  |
                       |    OR                             |                                  |
                       |<-- plan (if TodoWrite) -----------|                                  |
                       |                                   |                                  |
                       |                                   |<--- tool_use_start --------------|
                       |<-- tool_call (pending, with ------| (kind, content, rawInput)        |
                       |    kind+content+rawInput)         |                                  |
                       |    OR                             |                                  |
                       |<-- plan (if TodoWrite) -----------|                                  |
                       |                                   |                                  |
                       |                                   |<--- user message (tool_result) --|
                       |<-- tool_call_update (completed) --|                                  |
                       |    (with accumulated content)     |                                  |
                       |                                   |                                  |
                       |                                   |<--- tool_use_output -------------|
                       |<-- tool_call_update (completed) --|                                  |
                       |    (with accumulated content)     |                                  |
                       |                                   |                                  |
                       |                                   |<--- tool_use_error --------------|
                       |<-- tool_call_update (failed) -----|                                  |
                       |                                   |                                  |
                       |                                   |<--- text (direct) --------------|
                       |<-- agent_message_chunk -----------|                                  |
                       |                                   |                                  |
                       |                                   |<--- result ----------------------|
                       |                                   |  (logged, not emitted)           |
                       |                                   |                                  |
                       |<-- PromptResponse(end_turn) ------|                                  |
```

### 3.2 SDK Message Types: Reference vs Ours

```
File: tmp-ref/acp-claude-code/src/agent.ts, lines 357-659 (handleClaudeMessage)
File: src/vaultspec/protocol/acp/claude_bridge.py, lines 772-961 (_emit_updates)

Reference (TS) message types        Our (Python) SDK types          Emitted ACP update
================================    ============================    ============================
system                              SystemMessage                   Ref: silently ignored
                                                                    Ours: SessionInfoUpdate

user (tool_result)                  UserMessage                     Ref: tool_call_update(completed)
                                    (w/ ToolResultBlock)                 with accumulated content
                                                                    Ours: ToolCallProgress(completed)
                                                                         WITHOUT content

assistant (text)                    AssistantMessage(TextBlock)     Ref: agent_message_chunk
                                                                    Ours: SKIPPED (streamed earlier)

assistant (tool_use)                AssistantMessage(ToolUseBlock)  Ref: tool_call(pending) + kind
                                                                         + content + rawInput
                                                                    Ours: ToolCallStart(pending)
                                                                         title only, no kind/content

assistant (TodoWrite)               (not handled)                   Ref: plan update
                                                                    Ours: N/A

text                                (no direct equivalent)          Ref: agent_message_chunk
                                                                    Ours: N/A

tool_use_start                      (no direct equivalent -         Ref: tool_call(pending) + kind
                                     we get it via StreamEvent)          + content + rawInput
                                                                    Ours: via content_block_start
                                                                         -> _block_index_to_tool only

tool_use_output                     (no direct equivalent -         Ref: tool_call_update(completed)
                                     we get tool_result in               + accumulated content
                                     UserMessage)
                                                                    Ours: via UserMessage handler

tool_use_error                      (no direct equivalent)          Ref: tool_call_update(failed)
                                                                    Ours: via UserMessage is_error

stream_event (text_delta)           StreamEvent                     Ref: agent_message_chunk
                                                                    Ours: agent_message_chunk

stream_event (content_block_start)  StreamEvent                     Ref: agent_message_chunk
                                                                    Ours: _block_index_to_tool mapping

stream_event (content_block_delta)  StreamEvent                     Ref: agent_message_chunk
                                                                    Ours: agent_message_chunk

result                              ResultMessage                   Ref: logged, not emitted
                                                                    Ours: SessionInfoUpdate
```

### 3.3 Message Type Difference: TS SDK vs Python SDK

The TypeScript SDK (`@anthropic-ai/claude-code`) emits fine-grained types like
`tool_use_start`, `tool_use_output`, `tool_use_error`, and `text` that the Python SDK
(`claude-agent-sdk`) consolidates into higher-level types:

- `tool_use_start` -> appears as `StreamEvent` with `content_block_start` + `tool_use` type
- `tool_use_output` -> appears as `UserMessage` with `ToolResultBlock`
- `tool_use_error` -> appears as `UserMessage` with `ToolResultBlock(is_error=True)`
- `text` -> appears as `StreamEvent` with `text_delta`

This means our Python implementation receives functionally equivalent data but through
different type wrappers. The mapping is 1:1, we just need to extract the right fields.

---

## 4. Tool Call Lifecycle as Bidirectional Exchange

### 4.1 Reference: Full Round-Trip

```
File: tmp-ref/acp-claude-code/src/agent.ts

                    +------------------+
                    | tool_use_start   |   lines 495-556
                    | (from SDK)       |
                    +--------+---------+
                             |
                             v
              Is it TodoWrite?
              /             \
            YES              NO
             |                |
             v                v
        sendAgentPlan()   tool_call(pending)      <-- ACP update with:
        Track ID in         - toolCallId             kind, content (diff blocks
        todoWriteToolCallIds - title                  for Edit/MultiEdit),
                             - kind (mapped)          rawInput
                             - status: "pending"
                             - content (getToolCallContent)
                             - rawInput
                             |
                             v
                    +------------------+
                    | tool_use_output  |   lines 558-592
                    | (from SDK)       |
                    +--------+---------+
                             |
                             v
              Is it TodoWrite?
              /             \
            YES              NO
             |                |
             v                v
           SKIP          tool_call_update(completed)  <-- ACP update with:
                             - toolCallId                  accumulated content
                             - status: "completed"         (previous + new)
                             - content: [...prev, newContent]
                             - rawOutput
                             |
                             v
                    +------------------+
                    | tool_use_error   |   lines 594-613
                    | (from SDK)       |
                    +--------+---------+
                             |
                             v
                    tool_call_update(failed)           <-- ACP update with:
                             - toolCallId                  error text
                             - status: "failed"
                             - content: [{type: "content", text: error}]
                             - rawOutput: {error: msg}
```

### 4.2 Tool Call Content Accumulation (Reference)

This is a key pattern we completely miss. The reference maintains a
`toolCallContents: Map<string, ACPToolCallContent[]>` per session:

```typescript
// On tool_use_start (line 538-539):
const toolCallContent = this.getToolCallContent(msg.tool_name, input);
session.toolCallContents.set(msg.id, toolCallContent);

// On tool_use_output (line 576-578):
const prevToolCallContent = session.toolCallContents.get(msg.id) || [];
const toolCallContent = [...prevToolCallContent, newContent];
session.toolCallContents.set(msg.id, toolCallContent);

// On user message tool_result (line 395-397):
const prevToolCallContent = session.toolCallContents.get(content.tool_use_id) || [];
const toolCallContent = [...prevToolCallContent, newContent];
session.toolCallContents.set(content.tool_use_id, toolCallContent);
```

The accumulated content is sent with every update, so the client always receives
the full history of content blocks for each tool call.

### 4.3 Tool Call Content Types (Reference)

```
File: tmp-ref/acp-claude-code/src/types.ts, lines 58-73

interface ACPToolCallRegularContent {
  type: "content";
  content: {
    type: "text";
    text: string;
  };
}

interface ACPToolCallDiffContent {
  type: "diff";
  path: string;
  oldText: string;
  newText: string;
}

type ACPToolCallContent = ACPToolCallRegularContent | ACPToolCallDiffContent;
```

### 4.4 `getToolCallContent()` -- Structured Diff for Edit Tools

```
File: tmp-ref/acp-claude-code/src/agent.ts, lines 713-744

private getToolCallContent(toolName: string, toolInput: Record<string, unknown>):
    ACPToolCallContent[] {
  const result: ACPToolCallContent[] = [];
  switch (toolName) {
    case "Edit":
      if (toolInput.file_path && toolInput.old_string && toolInput.new_string) {
        result.push({
          type: "diff",
          path: toolInput.file_path as string,
          oldText: toolInput.old_string as string,
          newText: toolInput.new_string as string,
        });
      }
      break;
    case "MultiEdit":
      if (toolInput.file_path && toolInput.edits) {
        for (const edit of toolInput.edits) {
          result.push({
            type: "diff",
            path: toolInput.file_path as string,
            oldText: edit.old_string as string,
            newText: edit.new_string as string,
          });
        }
      }
  }
  return result;
}
```

### 4.5 Our Current Tool Call Handling -- Comparison

```python
# src/vaultspec/protocol/acp/claude_bridge.py, lines 863-896

async def _emit_assistant(self, msg: AssistantMessage, session_id: str):
    for block in msg.content:
        if isinstance(block, (TextBlock, ThinkingBlock)):
            continue                              # Already streamed
        elif isinstance(block, ToolUseBlock):
            self._pending_tools[block.id] = block.name
            await self._conn.session_update(
                session_id=session_id,
                update=ToolCallStart(
                    session_update="tool_call",
                    tool_call_id=block.id,
                    title=block.name,
                    status="pending",
                    # MISSING: kind
                    # MISSING: content (diff blocks for Edit)
                    # MISSING: rawInput
                ),
            )
```

**Gaps:**

| Feature | Reference | Ours |
|---------|-----------|------|
| `kind` field | `mapToolKind()` maps tool name to read/edit/search/etc. | Not set |
| `content` field | `getToolCallContent()` returns diff blocks for Edit/MultiEdit | Not set |
| `rawInput` field | Full `content.input` dict passed through | Not set |
| Content accumulation | `toolCallContents` Map tracks all content across lifecycle | Not tracked |
| TodoWrite interception | Detected at `tool_use_start` and `assistant`, emits `plan` | Not handled |
| Diff content blocks | Edit -> `{type: "diff", path, oldText, newText}` | Not emitted |

---

## 5. Abort/Cancel Pattern

### 5.1 Reference: AbortController per Session

```
File: tmp-ref/acp-claude-code/src/agent.ts, lines 325-337

async cancel(params: CancelNotification): Promise<void> {
    const session = this.sessions.get(params.sessionId);
    if (session) {
      // 1. Signal abort to the streaming loop
      session.abortController?.abort();

      // 2. Terminate the pending async iterator
      if (session.pendingPrompt && session.pendingPrompt.return) {
        await session.pendingPrompt.return();
        session.pendingPrompt = null;
      }
    }
  }
```

**Cancel check in the streaming loop (line 250-252):**

```typescript
for await (const message of messages) {
    if (session.abortController?.signal.aborted) {
      return { stopReason: "cancelled" };
    }
    // ... process message
}
```

**Teardown sequence:**

```
cancel() called
    |
    v
session.abortController.abort()    -- Sets signal.aborted = true
    |
    v
session.pendingPrompt.return()     -- Closes the async iterator
    |                                  (sends return signal to query())
    v
Streaming loop sees signal.aborted
    |
    v
Returns { stopReason: "cancelled" }
    |
    v
finally block:
    session.pendingPrompt = null
    session.abortController = null
```

### 5.2 Our Current Cancel Pattern

```python
# src/vaultspec/protocol/acp/claude_bridge.py, lines 476-491

async def cancel(self, session_id: str, **kwargs: Any) -> None:
    self._cancelled = True                      # Global flag
    if self._sdk_client is not None:
        try:
            self._sdk_client.interrupt()        # Sync call -- BUG: missing await
        except Exception:
            logger.exception("Error interrupting SDK client")
        try:
            self._sdk_client.disconnect()       # Sync call -- BUG: missing await
        except Exception:
            logger.exception("Error disconnecting SDK client")

    if session_id in self._sessions:
        self._sessions[session_id].connected = False
```

### 5.3 Cancel Pattern Comparison

```
REFERENCE                                    OURS
=========                                    ====

Per-session AbortController                  Global self._cancelled bool
    |                                            |
session.abortController.abort()              self._cancelled = True
    |                                            |
session.pendingPrompt.return()               self._sdk_client.interrupt()
    |                                        self._sdk_client.disconnect()
Graceful iterator close                          |
    |                                        Kills the entire SDK client
Returns { stopReason: "cancelled" }              |
    |                                        Next prompt() needs new session
finally: cleanup                             Session marked disconnected

ISSUES WITH OURS:
- self._cancelled is not per-session
- interrupt() and disconnect() are called synchronously
  but the SDK client methods are async (BUG #2 from gap analysis)
- disconnect() kills the persistent client, requiring full reconnect
- No way to cancel one session without destroying the client
- No pending iterator tracking -- no graceful close
```

### 5.4 What In-Flight State Looks Like After Cancel

**Reference:**
- Session remains in the `sessions` Map
- `claudeSessionId` preserved -- next `prompt()` can still resume
- `abortController` and `pendingPrompt` nulled in `finally`
- Session is fully ready for next `prompt()` call

**Ours:**
- `_cancelled` flag stays true until next `prompt()` resets it
- `_sdk_client` is disconnected (subprocess killed)
- Session marked `connected = False`
- Next `prompt()` will fail with "No active session" unless `load_session`/`resume_session` called
- Session recovery requires full client recreation

---

## 6. Session State Machine

### 6.1 Reference State Machine

```
                    +----------+
                    |  NO      |
                    | SESSION  |
                    +----+-----+
                         |
              newSession() or loadSession()
                         |
                         v
                    +----------+
                    |  IDLE    |  claudeSessionId: undefined or restored
                    |          |  pendingPrompt: null
                    +----+-----+  abortController: null
                         |
                    prompt()
                         |
                         v
                    +----------+
                    | STREAMING|  claudeSessionId: extracted from messages
                    |          |  pendingPrompt: active iterator
                    +----+-----+  abortController: active
                        / \
                       /   \
              natural    cancel()
              end          |
               |           v
               |     +----------+
               |     |CANCELLING|  abortController.abort()
               |     |          |  pendingPrompt.return()
               |     +----+-----+
               |          |
               v          v
                    +----------+
                    |  IDLE    |  claudeSessionId: preserved
                    |          |  pendingPrompt: null
                    +----+-----+  abortController: null
                         |
                    prompt() (multi-turn)
                         |
                    [loops back to STREAMING with resume]
```

### 6.2 Our State Machine (Actual)

```
                    +----------+
                    |  NO      |
                    | SESSION  |
                    +----+-----+
                         |
                    new_session()
                         |
                         v
                    +----------+
                    | CONNECTED|  _sdk_client: active
                    |          |  _session_id: set
                    +----+-----+  _cancelled: false
                         |
                    prompt()
                         |
                         v
                    +----------+
                    | STREAMING|  _cancelled: false
                    |          |  receive_response() active
                    +----+-----+
                        / \
                       /   \
              natural    cancel()
              end          |
               |           v
               |     +----------+
               |     |CANCELLED |  _cancelled: true
               |     |          |  _sdk_client.interrupt()
               |     +----+-----+  _sdk_client.disconnect() -- CLIENT KILLED
               |          |
               v          v
          +----------+  +----------+
          | CONNECTED|  |DISCONN.  |  _sdk_client: dead
          | (ready)  |  |          |  session.connected: false
          +----+-----+  +----+-----+
               |              |
          prompt()       load_session() or resume_session()
               |              |
               v              v
          [STREAMING]    [rebuilds entire SDK client]
```

---

## 7. Comparison Table: Reference vs Our Implementation

| Feature | Reference (acp-claude-code) | Ours (claude_bridge.py) | Priority |
|---------|---------------------------|-------------------------|----------|
| Session resume (`resume` param) | YES -- `query({resume: sessionId})` | NO -- never extracted, never passed | P0 |
| `session_id` extraction | `tryToStoreClaudeSessionId()` on every message | Never extracted | P0 |
| Cancel per-session | `AbortController` per session | Global `_cancelled` boolean | P0 |
| `cancel()` preserves session | Yes -- session stays in map, ready for next turn | No -- kills SDK client | P0 |
| `cancel()` async correctness | `await session.pendingPrompt.return()` | `self._sdk_client.interrupt()` (sync, missing await) | P0 |
| Error stop reason | Always `end_turn` + error chunk | `refusal` (non-standard) | P1 |
| Tool call `kind` field | `mapToolKind()` substring matching | Not set | P1 |
| Tool call `content` field | `getToolCallContent()` with diff blocks | Not set | P1 |
| Tool call `rawInput` field | Full input dict passed through | Not set | P1 |
| Tool call content accumulation | `toolCallContents` Map, accumulated per lifecycle | Not tracked | P1 |
| TodoWrite -> Plan conversion | Intercepted at `tool_use_start` and `assistant` | Not handled | P2 |
| Diff content for Edit/MultiEdit | `ACPToolCallDiffContent` with path/oldText/newText | Not emitted | P2 |
| Image prompt handling | base64 image blocks added to SDK message | Dropped | P2 |
| Resource/resource_link handling | file:// URI -> @-mention syntax | Dropped | P2 |
| Permission mode switching | Dynamic via `[ACP:PERMISSION:*]` markers | Fixed `bypassPermissions` | P2 |
| Multiple concurrent sessions | `sessions: Map<string, AgentSession>` | Single `_sdk_client` | P2 |
| `loadSession()` preserves Claude ID | Keeps `claudeSessionId` if session exists | Creates fresh client, no Claude ID | P1 |
| Unhandled message types | `default:` logs and continues | `MessageParseError` exception | P1 |

---

## 8. Concrete Implementation Recommendations

### 8.1 P0: Session Resume (Highest Impact)

**Step 1: Add `claude_session_id` to `_SessionState`**

```python
@dataclasses.dataclass
class _SessionState:
    session_id: str
    cwd: str
    model: str
    mode: str
    mcp_servers: list[Any]
    created_at: str
    claude_session_id: str | None = None    # NEW
    sdk_client: ClaudeSDKClient | None = None
    connected: bool = True
```

**Step 2: Extract `session_id` from SDK messages in the streaming loop**

```python
async def prompt(self, prompt, session_id, **kwargs):
    # ...
    state = self._sessions.get(session_id)

    async for message in self._sdk_client.receive_response():
        # Extract session_id from ResultMessage or StreamEvent
        msg_session_id = getattr(message, 'session_id', None)
        if msg_session_id and state and state.claude_session_id != msg_session_id:
            state.claude_session_id = msg_session_id

        await self._emit_updates(message, session_id)
        # ...
```

**Step 3: Pass `resume` when rebuilding SDK client in `load_session`/`resume_session`**

```python
async def load_session(self, cwd, session_id, mcp_servers=None, **kwargs):
    state = self._sessions.get(session_id)
    if state is None:
        return None

    # ... rebuild SDK client ...
    options = self._build_options(cwd, sdk_mcp, sandbox_cb)

    # KEY: Pass resume parameter if we have a Claude session ID
    if state.claude_session_id:
        options.resume = state.claude_session_id

    self._sdk_client = self._client_factory(options)
    await self._sdk_client.connect()
```

### 8.2 P0: Fix Cancel Pattern

**Replace global `_cancelled` with per-session tracking:**

```python
@dataclasses.dataclass
class _SessionState:
    # ... existing fields ...
    cancelled: bool = False                    # NEW: per-session

async def cancel(self, session_id, **kwargs):
    state = self._sessions.get(session_id)
    if state:
        state.cancelled = True
    if self._sdk_client is not None:
        try:
            await self._sdk_client.interrupt()   # FIX: add await
        except Exception:
            logger.exception("Error interrupting SDK client")
        # DO NOT disconnect -- preserve the client for future turns

async def prompt(self, prompt, session_id, **kwargs):
    state = self._sessions.get(session_id)
    if state:
        state.cancelled = False                 # Reset per-session flag

    # ... streaming loop ...
    async for message in self._sdk_client.receive_response():
        if state and state.cancelled:
            stop_reason = "cancelled"
            break
        # ...
```

### 8.3 P1: Tool Call Enrichment

**Add `mapToolKind()` equivalent:**

```python
def _map_tool_kind(tool_name: str) -> str:
    lower = tool_name.lower()
    if any(kw in lower for kw in ("read", "view", "get")):
        return "read"
    if any(kw in lower for kw in ("write", "create", "update", "edit")):
        return "edit"
    if any(kw in lower for kw in ("delete", "remove")):
        return "delete"
    if any(kw in lower for kw in ("move", "rename")):
        return "move"
    if any(kw in lower for kw in ("search", "find", "grep")):
        return "search"
    if any(kw in lower for kw in ("run", "execute", "bash")):
        return "execute"
    if any(kw in lower for kw in ("think", "plan")):
        return "think"
    if any(kw in lower for kw in ("fetch", "download")):
        return "fetch"
    return "other"
```

**Add diff content extraction:**

```python
def _get_tool_call_content(tool_name: str, tool_input: dict) -> list[dict]:
    result = []
    if tool_name == "Edit":
        if all(k in tool_input for k in ("file_path", "old_string", "new_string")):
            result.append({
                "type": "diff",
                "path": tool_input["file_path"],
                "oldText": tool_input["old_string"],
                "newText": tool_input["new_string"],
            })
    elif tool_name == "MultiEdit":
        if "file_path" in tool_input and "edits" in tool_input:
            for edit in tool_input["edits"]:
                result.append({
                    "type": "diff",
                    "path": tool_input["file_path"],
                    "oldText": edit.get("old_string", ""),
                    "newText": edit.get("new_string", ""),
                })
    return result
```

### 8.4 P1: Fix Error Stop Reasons

Replace `"refusal"` with standard ACP stop reasons:

```python
# In prompt():
except MessageParseError as exc:
    logger.debug("Skipping unparseable SDK message: %s", exc)
    # Don't change stop_reason -- this is recoverable
except Exception:
    logger.exception("Error streaming SDK messages")
    # Emit error as agent_message_chunk (matching reference pattern)
    if self._conn:
        await self._conn.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=TextContentBlock(type="text", text=f"Error: {exc}"),
            ),
        )
    stop_reason = "end_turn"      # NOT "refusal" -- match reference
```

### 8.5 P1: Tool Call Content Accumulation

Add per-session content tracking:

```python
@dataclasses.dataclass
class _SessionState:
    # ... existing fields ...
    tool_call_contents: dict[str, list[dict]] = dataclasses.field(default_factory=dict)
```

Update `_emit_assistant` and `_emit_user_message` to accumulate and send
content arrays matching the reference's pattern.

---

## 9. SDK Type Cross-Reference

### 9.1 Python SDK Types Relevant to Session Resume

```
ClaudeAgentOptions.resume: str | None       # .venv/.../claude_agent_sdk/types.py:725
    -- Pass Claude session ID here to resume conversation

ResultMessage.session_id: str               # .venv/.../claude_agent_sdk/types.py:679
    -- Available after every completed response

StreamEvent.session_id: str                 # .venv/.../claude_agent_sdk/types.py:691
    -- Available on every streaming delta event
    -- First StreamEvent in a response is the EARLIEST extraction point
```

### 9.2 Python SDK Client Methods

```
ClaudeSDKClient.connect()                   # Opens subprocess, initializes
ClaudeSDKClient.query(prompt)               # Sends user message over pipe
ClaudeSDKClient.receive_response()          # Yields messages up to ResultMessage
ClaudeSDKClient.receive_messages()           # Yields all messages (no auto-stop)
ClaudeSDKClient.interrupt()                  # Sends interrupt signal (async)
ClaudeSDKClient.disconnect()                 # Kills subprocess, cleans up (async)
```

Note: `interrupt()` in the `ClaudeSDKClient` public API is `async` (line 219-223):

```python
async def interrupt(self) -> None:
    """Send interrupt signal (only works with streaming mode)."""
    if not self._query:
        raise CLIConnectionError("Not connected. Call connect() first.")
    await self._query.interrupt()
```

Our bridge calls it without `await` -- this is confirmed as a bug.

---

## 10. Implementation Priority Matrix

```
                        IMPACT
                   HIGH         LOW
              +----------+----------+
         HIGH | P0:      | P2:      |
              | Session  | Image    |
    EFFORT    | Resume,  | handling,|
              | Cancel   | Perm mode|
              +----------+----------+
          LOW | P1:      | P3:      |
              | Tool kind| Diff     |
              | rawInput,| content  |
              | Error    | TodoWrite|
              | reasons  |          |
              +----------+----------+
```

**Recommended implementation order:**

1. Session resume (extract session_id + pass resume) -- unblocks multi-turn
2. Fix cancel (per-session, await, don't kill client) -- unblocks reliable operation
3. Tool kind + rawInput + content -- improves ACP compliance for rich clients
4. Error stop reasons -- correctness
5. Content accumulation -- rich tool call display
6. TodoWrite -> Plan -- Zed plan panel support
7. Image/resource handling -- rich input support
8. Permission mode switching -- flexible operation
