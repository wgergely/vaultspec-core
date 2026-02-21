---
title: "Protocol Layer Gap Analysis: A2A and ACP vs Reference Implementations"
date: 2026-02-21
tags: [a2a, acp]
status: complete
source: "Synthesis of 4 agent research reports"
agent: orchestrator
related:
  - "[[2026-02-21-acp-ref-impl-research]]"
  - "[[2026-02-21-a2a-ref-impl-research]]"
  - "[[2026-02-21-a2a-layer-audit-research]]"
  - "[[2026-02-21-acp-layer-audit-research]]"
---

# Protocol Layer Gap Analysis

## Executive Summary

Comprehensive comparison of our A2A and ACP implementations against two reference repos:
- **python-a2a** (980 stars) — Python A2A library with Anthropic support
- **acp-claude-code** (235 stars) — TypeScript ACP bridge for Claude Code

19 findings total. Both layers share a root cause: we use `claude-agent-sdk` (CLI wrapper)
where references use the raw `anthropic` SDK or `@anthropic-ai/claude-code` TypeScript SDK
directly. This introduces `rate_limit_event` parse bugs, env var juggling, PATH dependency,
and prevents session resume.

---

## P0 — Fix Immediately

### 1. No Session Resume in ACP Bridge (CRITICAL)

- **File**: `src/vaultspec/protocol/acp/claude_bridge.py`
- **Impact**: Every `prompt()` starts a fresh conversation. Multi-turn is broken.
- **Root cause**: We never extract Claude's `session_id` from messages and pass it as
  `resume` on subsequent queries.
- **Reference pattern**: acp-claude-code's `tryToStoreClaudeSessionId()` extracts
  `session_id` from any SDK message and passes it as `resume` option to `query()`.
- **Fix**: Add session ID extraction to the streaming loop. Store in `_SessionState`.
  Pass as `resume` parameter on subsequent `query()` calls.

### 2. `cancel()` Missing `await` (BUG)

- **File**: `src/vaultspec/protocol/acp/claude_bridge.py:485`
- **Impact**: Silent no-op on cancellation, leaking resources.
- **Fix**: Add `await` to `self._sdk_client.disconnect()`.

### 3. Dead `self._stream` in `fork_session()` (BUG)

- **File**: `src/vaultspec/protocol/acp/claude_bridge.py:657`
- **Impact**: Creates orphaned stream iterator. Resource leak.
- **Fix**: Remove the dead stream assignment. `prompt()` uses `receive_response()`, not
  the persistent stream.

### 4. `CLAUDECODE` Env Var Mutation Is Thread-Unsafe (BUG)

- **File**: `src/vaultspec/protocol/a2a/executors/claude_executor.py:121`
- **Impact**: Races if multiple executors run concurrently.
- **Fix**: Use subprocess env isolation (copy env dict) instead of mutating `os.environ`.
  The ACP provider already does this correctly.

---

## P1 — Fix Soon

### 5. No Tool Use Handling in A2A Executor

- **File**: `src/vaultspec/protocol/a2a/executors/claude_executor.py:137-140`
- **Impact**: `ToolUseBlock` silently ignored. Empty artifacts if Claude responds with tools.
- **Reference**: python-a2a handles `tool_use` content items explicitly.

### 6. A2A Executor Uses `receive_messages()` Instead of `receive_response()`

- **File**: `src/vaultspec/protocol/a2a/executors/claude_executor.py`
- **Impact**: Exposed to raw parse errors. ACP bridge uses `receive_response()` (filtered).
- **Fix**: Switch to `receive_response()` for consistency and robustness.

### 7. No Multi-Turn Conversation in A2A

- **File**: `src/vaultspec/protocol/a2a/executors/claude_executor.py:95-161`
- **Impact**: Fresh `ClaudeSDKClient` per task. No conversation history.
- **Reference**: python-a2a maintains `_conversation_histories` per `conversation_id`.

### 8. Agent Card Discovery Path Mismatch

- **File**: `src/vaultspec/protocol/a2a/discovery.py:75`
- **Impact**: Generates `/.well-known/agent.json` but server serves `/.well-known/agent-card.json`.
- **Fix**: Align paths.

### 9. ACP `stop_reason: "refusal"` Is Non-Standard

- **File**: `src/vaultspec/protocol/acp/claude_bridge.py:448-474`
- **Impact**: ACP spec defines `end_turn`, `cancelled`, `max_tokens`, `tool_use`.
  "refusal" is not standard.
- **Fix**: Map to appropriate standard stop reasons.

### 10. No Multi-Turn E2E Tests

- **Impact**: Session resume, load, fork untested end-to-end.
- **Fix**: Add tests that exercise multi-turn conversations across both layers.

### 11. `SubagentClient.on_connect()` Is a No-Op (BUG)

- **File**: `src/vaultspec/protocol/acp/client.py:447`
- **Impact**: `_conn` is never assigned. `graceful_cancel()` silently does nothing.
- **Fix**: Store `conn` in `self._conn` inside `on_connect()`.

### 12. Broad Exception Catch Masks Error Types

- **File**: `src/vaultspec/protocol/acp/claude_bridge.py:457-459`
- **Impact**: All exceptions become "refusal". Network errors indistinguishable from model refusal.
- **Fix**: Differentiate exception types. Map to appropriate stop reasons.

---

## P2 — Fix When Convenient

### 13. No TodoWrite-to-Plan Conversion in ACP

- **Reference**: acp-claude-code intercepts TodoWrite, emits `AgentPlanUpdate`.
- **Impact**: Zed's plan panel stays empty.

### 14. No Tool Kind Mapping in ACP

- **Reference**: Maps tool names to ACP kinds (read/edit/search/execute/etc.).
- **Impact**: Clients can't render appropriate tool icons.

### 15. No Image/Resource Prompt Handling in ACP

- **Reference**: Handles `image`, `resource`, `resource_link` prompt block types.
- **Impact**: Only text extracted. Images and file references dropped.

### 16. OAuth Token Refresh Race Condition

- **File**: `src/vaultspec/protocol/providers/claude.py:131-152`
- **Impact**: Multiple bridges refreshing simultaneously can overwrite tokens.
- **Fix**: Add file locking.

### 17. Per-Session SDK Clients in ACP Bridge

- **Impact**: Single SDK client means no concurrent sessions.
- **Reference**: acp-claude-code stores per-session state in a Map.

### 18. `_block_index_to_tool` and `_pending_tools` Never Cleared

- **File**: `src/vaultspec/protocol/acp/claude_bridge.py:263-267`
- **Impact**: Stale entries in long sessions. Low risk with UUID IDs.

### 19. `set_session_mode/model` Use Internal SDK Attributes

- **File**: `src/vaultspec/protocol/acp/claude_bridge.py:725-753`
- **Impact**: Reaches into `_options` via getattr. Fragile if SDK changes.

---

## P3 — Nice to Have

- Structured diff content for Edit/MultiEdit tools in ACP bridge
- Dynamic permission mode switching in ACP bridge
- `input_required` state support in A2A executor
- API key auth support in A2A executor (alternative to CLI auth)
- Agent card validation in A2A layer

---

## Root Cause Pattern

Both layers use `claude-agent-sdk` (CLI wrapper) where references use either:
- Raw `anthropic` SDK (python-a2a) — simple REST, no subprocess
- `@anthropic-ai/claude-code` TypeScript SDK (acp-claude-code) — stateless `query()` calls

The CLI wrapper introduces:
- `rate_limit_event` parse bug (upstream `claude-agent-sdk`)
- Env var juggling (`CLAUDECODE` stripping)
- PATH dependency on `claude` binary
- No native session resume (must extract session ID from stream)

The reference ACP bridge solves multi-turn by capturing the CLI's own session ID from
the stream — we never do this.

---

## Cross-References

- [[2026-02-21-acp-ref-impl-research]] — Full acp-claude-code analysis
- [[2026-02-21-a2a-ref-impl-research]] — Full python-a2a analysis
- [[2026-02-21-a2a-layer-audit-research]] — Our A2A layer audit
- [[2026-02-21-acp-layer-audit-research]] — Our ACP layer audit
