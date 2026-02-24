---
tags:
  - "#research"
  - "#a2a"
date: "2026-02-21"
---
# A2A Layer Audit

## File Map

### `src/vaultspec/protocol/a2a/`

- **`__init__.py`** — Re-exports: `agent_card_from_definition`, `create_app`,
  `generate_agent_md`, `write_agent_discovery`, `write_gemini_settings`,
  `A2A_TO_VAULTSPEC`, `VAULTSPEC_TO_A2A`
- **`agent_card.py`** — Converts vaultspec agent YAML metadata to A2A `AgentCard`.
  One skill per agent. Hardcoded version `"0.1.0"`. Default modes: `["text"]`.
  Capabilities: `streaming=True`, `push_notifications=False`, `state_transition_history=True`.
- **`discovery.py`** — Gemini CLI discovery: `generate_agent_md()`, `write_agent_discovery()`,
  `write_gemini_settings()`. Preserves existing keys.
- **`server.py`** — `create_app(executor, agent_card)`: wraps executor in
  `DefaultRequestHandler` + `InMemoryTaskStore`, returns Starlette ASGI app.
- **`state_map.py`** — Bidirectional state mapping: 6 vaultspec states <-> 9 A2A
  `TaskState` values. Fallbacks: `rejected -> "failed"`, `auth_required -> "input_required"`.

### `src/vaultspec/protocol/a2a/executors/`

- **`base.py`** — Re-exports sandbox utilities from `protocol.sandbox`.
- **`claude_executor.py`** — Core executor (detailed below).
- **`gemini_executor.py`** — Wraps `orchestration.subagent.run_subagent()` via DI.

## ClaudeA2AExecutor — Deep Analysis

**Class**: `ClaudeA2AExecutor(AgentExecutor)`

### Constructor

- `model: str` — Claude model identifier
- `root_dir: str` — workspace root
- `mode: str = "read-only"` — sandboxing mode
- `mcp_servers: dict | None` — optional MCP server config
- `system_prompt: str | None` — optional system prompt
- `client_factory: Callable | None` — DI for testing (defaults to `ClaudeSDKClient`)
- `options_factory: Callable | None` — DI for testing (defaults to `ClaudeAgentOptions`)

### State

- `_active_clients: dict[str, Any]` — task_id -> SDK client, for cancellation
- `_clients_lock: asyncio.Lock` — protects `_active_clients`
- `_cli_path: str | None` — `shutil.which("claude")` at init time

### `execute()` Flow

1. Create `TaskUpdater`, extract prompt from context
2. `await updater.start_work()` — emits `TaskState.working`
3. Build `ClaudeAgentOptions` (sandbox callback, `permission_mode="bypassPermissions"`)
4. Create `ClaudeSDKClient`, register in `_active_clients`
5. Pop `CLAUDECODE` env var (prevents child refusing inside Claude Code session)
6. `await sdk_client.connect()`
7. `await sdk_client.query(prompt)`
8. Iterate `sdk_client.receive_messages()`:
   - `AssistantMessage`: collect `TextBlock.text` chunks
   - `ResultMessage`: join text, add artifact, emit `complete()` or `failed()`; break
   - `MessageParseError`: log debug, `continue` (rate_limit_event workaround)
9. If no `ResultMessage` received: complete with collected text or fail with "Stream ended without result"
10. `finally`: disconnect, cleanup, restore `CLAUDECODE`

### `cancel()` Flow

1. Pop client from `_active_clients`
2. `client.interrupt()` (sync), `await client.disconnect()`
3. `await updater.cancel()`

## GeminiA2AExecutor

Delegates to `run_subagent()` via DI. Much simpler: no streaming, no connection lifecycle.
Cancel is fire-and-forget (no process handle to kill).

## Provider Layer (`providers/claude.py`)

- `_load_claude_oauth_token()`: Reads `~/.claude/.credentials.json`, refreshes OAuth if
  expired (5-min buffer), writes back atomically.
- `ClaudeProvider.prepare_process()`: Spawns `python -m vaultspec.protocol.acp.claude_bridge`.
  Sets env vars, pops `CLAUDECODE` from env copy (safe).

## Issues Found

### 1. `rate_limit_event` Crash (KNOWN — MEMORY)

- `claude_executor.py:134-136`: `MessageParseError` caught and skipped.
- Fragile: depends on exact exception type. If stream dies differently, fallback
  path silently completes with partial text or fails with generic error.
- No retry logic. Rate limit error is swallowed entirely.

### 2. Gemini Cancel Is a No-Op

- `gemini_executor.py:108-113`: Cancel emits `TaskState.canceled` but has no process
  handle. Subprocess continues running.

### 3. No Multi-Turn / Conversation Context

- Fresh `ClaudeSDKClient` per task. A2A `context_id` is passed to `TaskUpdater` but
  never used to resume a Claude conversation.

### 4. `InMemoryTaskStore` — No Persistence

- `server.py:51`: Tasks lost on restart. Fine for dev, production concern.

### 5. Hardcoded Version `"0.1.0"` in Agent Cards

- `agent_card.py:31`: No dynamic versioning.

### 6. `_cli_path` Set at Init, Not at Execute

- `claude_executor.py:93`: `shutil.which("claude")` called once. If binary added to
  PATH later, won't be found.

### 7. Test Marker Mismatch

- `test_claude_executor.py:134`: Marked `@pytest.mark.claude` and `@pytest.mark.integration`
  but uses `_InProcessSDKClient` (no CLI needed). May be falsely skipped in CI.

## Test Coverage

### Unit (no network, no LLM)

- `test_unit_a2a.py`: State mapping, agent card, EchoExecutor, PrefixExecutor,
  message serialization. All real types, no mocks.
- `test_agent_card.py`: 11 tests for `agent_card_from_definition`.
- `test_discovery.py`: generate_agent_md, write_agent_discovery, write_gemini_settings.
- `test_gemini_executor.py`: 5 tests via DI recorder. Happy path, error, cancel, empty, custom.
- `test_claude_executor.py`: 6 tests via DI `_InProcessSDKClient`.

### Integration (real HTTP via ASGITransport, no LLM)

- `test_integration_a2a.py`: Agent card, message/send, task lifecycle, error handling.

### E2E (real LLMs)

- `test_e2e_a2a.py`: `TestClaudeE2E`, `TestGeminiE2E`, `TestGoldStandardBidirectional`.
- `test_french_novel_relay.py`: 3-turn Claude->Gemini->Claude creative relay.

All test code is **mock-free** and exercises real code paths. DI pattern (constructor-injected
factories) is the correct approach.
