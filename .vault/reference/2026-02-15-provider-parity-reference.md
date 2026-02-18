---
tags: ["#reference", "#protocol"]
date: 2026-02-15
related: []
---

# Provider Parity Gap Report: Claude vs Gemini ACP Subagent Providers

**Date:** 2026-02-15
**Author:** Team Lead (provider parity audit)
**Contributors:** claude-specialist, gemini-specialist, acp-specialist
**Scope:** Comprehensive analysis of feature parity between Claude and Gemini as ACP subagent backends, with remediation plan for provider-agnostic orchestration.

---

## Executive Summary

The vaultspec subagent system supports two providers -- Claude (via custom ACP bridge, 1042 LOC) and Gemini (via native CLI with `--experimental-acp`) -- both communicating over ACP (Agent Client Protocol) via stdio. The orchestration layer (`run_subagent()` in `orchestration/subagent.py`) is well-abstracted and provider-agnostic.

However, significant **asymmetries** exist:

1. **Sandboxing**: Claude has dual-layer enforcement (bridge `can_use_tool` + client `write_text_file`). Gemini has single-layer (client `write_text_file` only). Terminal/shell commands bypass BOTH.
2. **System prompt delivery**: Neither provider uses the proper system prompt channel. Both prepend to user content.
3. **Streaming richness**: Claude emits `ToolCallProgress` with partial JSON args. Gemini emits `AgentPlanUpdate`, `CurrentModeUpdate`, etc. Neither covers the full ACP update spec.
4. **Session management**: Claude bridge implements 6 optional methods. Gemini added `load`/`resume` only in v0.28.0.
5. **Process architecture**: Claude is a 4-layer stack (orchestrator -> bridge -> SDK -> CLI -> API). Gemini is a 2-layer stack (orchestrator -> CLI -> API).

**Bottom line:** The architecture is sound. 11 parity gaps identified, 3 critical. The most dangerous is terminal/shell command escape from read-only mode, which affects BOTH providers.

---

## 1. ACP Method Coverage Matrix

| ACP Agent Method | Claude Bridge | Gemini CLI | Parity |
|---|---|---|---|
| `initialize` | Implemented. Returns empty `AgentCapabilities()`, `Implementation(name="claude-acp-bridge")`. Ignores client_capabilities. | Native. Returns actual capabilities with feature flags. | PARTIAL -- Claude returns empty capabilities |
| `authenticate` | Implemented. Returns empty `AuthenticateResponse()`. Auth via `ANTHROPIC_API_KEY` env var. | Native. Supports OAuth, API key, GCP credentials. Auth issues reported in headless mode (issue #10855). | PARTIAL -- different mechanisms |
| `session/new` | Implemented. Creates `ClaudeSDKClient`, converts MCP servers (stdio only), sets up sandbox callback, tracks `_SessionState`. | Native. Creates session with cwd, mcpServers. Also reads `.gemini/settings.json`. | OK |
| `session/prompt` | Implemented. Extracts text from blocks, calls `sdk_client.query()`, streams via `_emit_updates()`. | Native. Accepts text content blocks. | OK |
| `session/cancel` | Implemented. Sets `_cancelled` flag, calls `interrupt()` + `disconnect()`. | Native. Notification-based. | OK |
| `session/load` | Implemented. Restores **config only** (not conversation history). Creates fresh SDK client. | **v0.28+ only**. Added in v0.28.0. Likely restores actual conversation history. | GAP -- different semantics |
| `session/resume` | Implemented. Functionally identical to `load_session`. Config only. | **v0.28+ only**. Added in v0.28.0. | GAP -- same issue |
| `session/fork` | Implemented. Clones config into new session with new UUID. No history. | No evidence of implementation. | GAP -- Claude-only |
| `session/list` | Implemented. Returns in-memory `SessionInfo` objects (current bridge instance only). | Via `gemini --list-sessions` CLI. Unknown if exposed over ACP. | GAP -- different scopes |
| `session/set_mode` | Implemented. Updates `_mode`, rebuilds sandbox callback. | Available in Gemini CLI. | OK |
| `session/set_model` | Implemented. Updates `_model` on SDK client options in-place. | Unknown if exposed over ACP (settable at launch via `--model`). | UNCERTAIN |
| `ext_method` | Stub. Returns `{}`. | Unknown. Likely returns `method_not_found`. | OK (both no-ops) |
| `ext_notification` | Stub. No-op. | Unknown. | OK |

**Key finding:** Claude bridge implements SIGNIFICANTLY more optional methods, but creates fresh SDK clients for load/resume (losing history). Gemini added native session resume in v0.28.0, likely preserving history. The SDK's native `resume` parameter exists but the bridge does NOT use it.

**Current risk:** LOW -- `run_subagent()` only uses `initialize`, `new_session`, `prompt`, `cancel`.

---

## 2. Session Update Types (Streaming Events)

| ACP Session Update | Claude Bridge | Gemini CLI | Notes |
|---|---|---|---|
| `AgentMessageChunk` | YES -- via `text_delta` + `TextBlock` | YES -- native | Both emit incremental text |
| `AgentThoughtChunk` | YES -- via `thinking_delta` + `ThinkingBlock` | YES -- requires `ui.inlineThinkingMode: "full"` | Claude: always when model supports it. Gemini: config-dependent. |
| `ToolCallStart` | YES -- via `ToolUseBlock` | YES -- native, with title/kind/status/locations | Both functional |
| `ToolCallProgress` | YES -- from `input_json_delta` (partial args) + tool result (completed/failed) | YES -- native progress updates | Claude streams partial JSON args; unclear if Gemini does |
| `SessionInfoUpdate` | YES -- from `SystemMessage` + `ResultMessage` | Unknown | May be Claude-only |
| `AgentPlanUpdate` | **NO** | YES -- entries with priority/status | Gemini-only |
| `AvailableCommandsUpdate` | **NO** | YES -- slash commands | Gemini-only |
| `CurrentModeUpdate` | **NO** | YES -- mode changes | Gemini-only |
| `ConfigOptionUpdate` | **NO** | YES -- config changes | Gemini-only |

**Key finding:** Gemini emits richer session metadata (plans, commands, modes, config). Claude emits more detailed tool call streaming (partial JSON input deltas). The `SubagentClient.session_update()` handles all types uniformly, so asymmetry is cosmetic unless a consumer depends on specific update types.

---

## 3. Sandboxing & Permission Model

### 3.1 Three Enforcement Layers

| Layer | Claude | Gemini | Notes |
|---|---|---|---|
| **L1: ACP Client (SubagentClient)** | `write_text_file()` checks `self.mode == "read-only"` and restricts to `.vault/` (lines 276-288) | **Same** -- same client code for both providers | BOTH ENFORCED |
| **L2: SDK/Bridge callback** | `_make_sandbox_callback()` blocks Write/Edit/MultiEdit/NotebookEdit outside `.vault/` | **None** -- no custom callback mechanism | Claude-only |
| **L3: OS-level sandbox** | None | `--sandbox` flag (Seatbelt profiles on macOS, Docker on Linux) | Gemini-only, but we NEVER pass it |

### 3.2 Terminal/Shell Escape (CRITICAL for BOTH)

Neither provider restricts terminal commands in read-only mode:

- **Claude**: `Bash` tool is NOT in `_WRITE_TOOLS` set. Terminal commands via ACP `create_terminal` bypass the sandbox callback entirely.
- **Gemini**: No custom sandboxing at all. Terminal and shell commands are unrestricted.

A subagent in read-only mode can run `echo "data" > file.txt` via terminal and bypass all write protections for BOTH providers.

### 3.3 Gemini `--sandbox` Flag

Gemini CLI offers OS-level sandboxing via `--sandbox`:

- macOS: Seatbelt profiles (permissive-open, restrictive-open, strict-open, strict-proxied, custom)
- Linux: Docker/Podman containers

We NEVER pass this flag. In read-only mode, adding `--sandbox` to Gemini args would add defense-in-depth.

---

## 4. System Prompt Delivery

| Aspect | Claude Bridge | Gemini CLI | Gap |
|---|---|---|---|
| **Current approach** | Prepend persona+rules to task via `initial_prompt_override` | Same -- `initial_prompt_override` | Parity, but suboptimal |
| **Proper channel** | SDK `system_prompt` option (currently set to `None`) | `GEMINI_SYSTEM_MD` env var pointing to file | NEITHER USED |
| **Impact** | System instructions treated as user content, subject to context compression | Same | Both lose system-level authority |
| **Rules loading** | `.claude/rules/*.md` via `load_rules()` | `.gemini/rules/*.md` + `.gemini/SYSTEM.md` via `load_rules()` + `load_system_prompt()` | OK |

**Both providers prepend system context to the first prompt as user content instead of using the dedicated system prompt channel.** This means:

- System instructions get different attention weighting than intended
- They are subject to context compression
- The model treats them as user suggestions, not authoritative instructions

---

## 5. MCP Server Forwarding

| Aspect | Claude Bridge | Gemini CLI |
|---|---|---|
| Accepts `mcp_servers` in `new_session` | YES -- `_convert_mcp_servers()` converts stdio-type only | YES -- native ACP, supports stdio + HTTP + SSE (SSE reported broken, issue #8672) |
| Reads workspace MCP config | NO -- only uses ACP-provided servers | YES -- reads `.gemini/settings.json` |
| Server types supported | Stdio only (`McpStdioServerConfig`) | Stdio (required), HTTP, SSE |
| **What we actually pass** | `mcp_servers=[]` | `mcp_servers=[]` |

**Both providers receive empty MCP server lists.** The Claude bridge has conversion code ready but receives nothing. Gemini falls back to its workspace config. Both are equally broken in practice.

---

## 6. Error Handling

| Aspect | Claude Bridge | Gemini CLI |
|---|---|---|
| Process crash | Caught by `run_subagent()` try/except | Same |
| ACP protocol error | `prompt()` try/except -> `stop_reason="refusal"` | Native JSON-RPC error responses |
| Tool errors | `ToolResultBlock.is_error` -> `ToolCallProgress.status="failed"` | Unknown -- likely similar |
| Stop reasons | `end_turn`, `cancelled`, `refusal` | Full set: `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled` |
| Cancel | `interrupt()` + `disconnect()` + flag | Notification-based |

**Parity assessment:** Claude bridge uses a limited set of stop reasons (no `max_tokens` or `max_turn_requests`). Error handling is asymmetric but equivalent at the orchestration level.

---

## 7. Environment Variable Contract

| Env Var | Claude | Gemini | Notes |
|---|---|---|---|
| `VS_ROOT_DIR` | Read in bridge constructor | Not read | Claude-only |
| `VS_AGENT_MODE` | Read in bridge -> sandbox policy | Not read | Claude-only |
| `ANTHROPIC_API_KEY` | Required | Not relevant | |
| `GEMINI_API_KEY` | Not relevant | Required | |
| `GEMINI_CWD` | Not relevant | Set by provider | **UNDOCUMENTED** -- may have no effect |
| `GEMINI_SYSTEM_MD` | Not relevant | NOT set (should be) | Proper system prompt channel |
| `CLAUDECODE` | Removed by provider (nested session safety) | Not relevant | |

**Finding from gemini-specialist:** `GEMINI_CWD` is NOT a documented Gemini CLI environment variable. It likely has no effect. Should be removed or validated.

---

## 8. Process Architecture

```
CLAUDE (4-layer stack):
  run_subagent() -> spawn_agent_process()
    -> python -m protocol.acp.claude_bridge    [ACP Agent - our bridge]
      -> ClaudeSDKClient (claude-agent-sdk)     [SDK wrapper]
        -> Claude Code CLI subprocess            [Anthropic tool]
          -> Claude API                          [Anthropic API]

GEMINI (2-layer stack):
  run_subagent() -> spawn_agent_process()
    -> gemini --experimental-acp --model X     [ACP Agent - native]
      -> Gemini API                              [Google API]
```

**Impact:** Claude's 4-layer stack adds ~5-10s startup. Gemini's 2-layer stack adds ~14s cold start (Node.js CLI overhead). Gemini is actually slower despite fewer layers.

---

## 9. Unexposed Provider Features

### Claude (via claude-agent-sdk)

| Feature | SDK Support | Bridge Status | Impact |
|---|---|---|---|
| Structured output (`output_format`, JSON Schema) | Full | NOT exposed | Would enable validated JSON responses |
| System prompt (`system_prompt` option) | Full | Always `None` | Missing proper system prompt channel |
| Tool control (`allowed_tools`, `disallowed_tools`) | Full | NOT exposed | No granular tool restrictions |
| Budget/turn limits (`max_turns`, `max_budget_usd`) | Full | NOT exposed | No cost/safety limits on subagents |
| Fallback model (`fallback_model`) | Full | NOT exposed | No auto-fallback on overload |
| Hooks (PreToolUse, PostToolUse, Stop, etc.) | Full | NOT exposed | No lifecycle hooks |
| Native session resume (SDK `resume` parameter) | Full | NOT used | Bridge creates fresh clients |
| File checkpointing (`rewind_files()`) | Full | NOT exposed | No rollback capability |
| SSE/HTTP MCP servers | Full | NOT converted | Only stdio servers supported |
| Subagent definitions (`agents` option) | Full | NOT exposed | No nested subagent support |

### Gemini CLI

| Feature | CLI Support | Provider Status | Impact |
|---|---|---|---|
| OS sandbox (`--sandbox`) | Full | NOT passed | No OS-level isolation |
| `GEMINI_SYSTEM_MD` env var | Full | NOT set | Missing system prompt channel |
| Agent Skills (v0.27+) | Full | NOT used | No reusable capability system |
| Session resume (`--resume`, ACP v0.28+) | Full | NOT used | No session persistence |
| Hooks system | Full | NOT used | No lifecycle hooks |
| Approval modes (`--approval-mode plan`) | Full | NOT passed | No plan-mode support |
| Dynamic MCP from settings.json | Full | Empty settings | No MCP tools for subagents |

---

## 10. Test Coverage

| Test Category | Claude | Gemini | Cross-Provider |
|---|---|---|---|
| Bridge unit tests | 112+ tests (4 files) | N/A (native ACP) | None |
| Provider unit tests | In `test_providers.py` | In `test_providers.py` | None |
| E2E MCP dispatch | `test_mcp_dispatch_claude` | `test_mcp_dispatch_gemini` | **None** |
| Integration tests | Exist but may be stale | Exist but may be stale | **None** |

**Stale test alert (from gemini-specialist):** `.vaultspec/tests/e2e/test_gemini.py:109` asserts `"--system" in spec.args` but current `GeminiProvider` does NOT produce `--system` args. This test will fail.

**Zero cross-provider parity tests exist.** No test verifies identical behavior for the same task dispatched to both providers.

---

## 11. Gap Summary & Prioritized Risk Matrix

| # | Gap | Severity | Affects | Fix Effort |
|---|---|---|---|---|
| **G1** | Terminal/shell commands bypass read-only for BOTH providers | **CRITICAL** | Security | 3h |
| **G2** | System prompts delivered as user content (both providers) | **CRITICAL** | Prompt quality | 4h |
| **G3** | No cross-provider parity tests | **HIGH** | Quality assurance | 4h |
| **G4** | `GEMINI_CWD` undocumented, likely no-op | **CRITICAL** | Code hygiene | 30m |
| **G5** | Stale E2E test asserts `--system` flag | **MEDIUM** | Test reliability | 30m |
| **G6** | `AgentCapabilities` empty for Claude bridge | **MEDIUM** | Protocol compliance | 1h |
| **G7** | MCP servers not forwarded to either provider | **MEDIUM** | Tool availability | 4h |
| **G8** | No cross-provider fallback chain | **MEDIUM** | Reliability | 3h |
| **G9** | Optional ACP methods are Claude-only | **LOW** | Feature parity | 2h |
| **G10** | Streaming update types differ between providers | **LOW** | UX consistency | N/A |
| **G11** | Claude SDK features unexposed (structured output, limits, etc.) | **LOW** | Feature depth | 6h |

---

## 12. Remediation Plan

### Phase 1: Critical Security -- Terminal Sandbox (G1)

**Problem:** Both providers allow shell commands that can write files in read-only mode.

**Fix A (Claude -- bridge-level):** Add terminal/Bash to the sandbox check:

```python
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"})
```

And make the callback inspect `tool_input` for Bash commands that write.

**Fix B (Gemini -- provider-level):** Pass `--sandbox` when `mode == "read-only"`:

```python
if mode == "read-only":
    args.append("--sandbox")
```

**Fix C (Client-level -- both providers):** Restrict `create_terminal` in `SubagentClient` when `self.mode == "read-only"`:

- Deny terminal creation entirely, OR
- Prepend read-only shell wrapper that blocks write operations

### Phase 2: System Prompt Channels (G2)

**Claude:** Use the SDK's `system_prompt` option:

```python
options = ClaudeAgentOptions(
    system_prompt=system_context,  # instead of None
    ...
)
```

Keep `initial_prompt_override` for the task only, not persona+rules.

**Gemini:** Set `GEMINI_SYSTEM_MD` to a temp file:

```python
system_file = root_dir / ".vaultspec" / ".tmp" / f"system-{uuid4()}.md"
system_file.write_text(system_prompt, encoding="utf-8")
env["GEMINI_SYSTEM_MD"] = str(system_file)
spec.cleanup_paths.append(system_file)
```

### Phase 3: Cross-Provider Tests (G3) + Stale Test Fix (G5)

Create `.vaultspec/tests/e2e/test_provider_parity.py`:

1. `test_same_persona_both_providers` -- "Jean-Claude" persona on both
2. `test_readonly_write_blocked_both_providers` -- verify ACP write rejection
3. `test_streaming_events_both_providers` -- verify `AgentMessageChunk` from both
4. `test_cancel_both_providers` -- verify cancellation works

Fix stale test: remove `assert "--system" in spec.args` from `test_gemini.py`.

### Phase 4: Quick Wins (G4, G5, G6)

- Remove `GEMINI_CWD` or replace with documented alternative
- Populate `AgentCapabilities` in Claude bridge (declare actual supported features)
- Add version enforcement/warning for `_MIN_VERSION_RECOMMENDED`

### Phase 5: Feature Expansion (G7, G8, G9, G11)

- Populate MCP servers from workspace config
- Add bidirectional fallback chain to `run_subagent()`
- Expose structured output, budget limits, tool control from agent metadata
- Use SDK's native `resume` parameter in bridge load/resume methods

---

## 13. Key Architectural Findings

### What's Working Well

1. **`AgentProvider` ABC** -- clean abstraction with `prepare_process()` -> `ProcessSpec`
2. **`SubagentClient`** -- provider-agnostic, handles ALL ACP update types uniformly
3. **`run_subagent()`** -- truly provider-agnostic after `prepare_process()`
4. **`initial_prompt_override`** -- identical pattern for both providers
5. **`resolve_includes()`** -- shared utility in `base.py`, no duplication
6. **Client-side sandboxing** -- `write_text_file()` enforces read-only for BOTH via ACP
7. **Model registries** -- `ClaudeModels` / `GeminiModels` with `CapabilityLevel` mapping

### What Needs Work

1. **Terminal/shell escape from read-only** -- CRITICAL gap for both providers
2. **System prompt channels unused** -- both providers prepend to user content
3. **Zero cross-provider tests** -- parity regressions undetectable
4. **Undocumented env vars** -- `GEMINI_CWD` likely no-op
5. **Many SDK features unexposed** -- structured output, limits, hooks, sandbox

---

## Sources

### Source Files Read

- `protocol/providers/base.py` -- `AgentProvider` ABC, `ProcessSpec`, `CapabilityLevel` (187 LOC)
- `protocol/providers/claude.py` -- `ClaudeProvider.prepare_process()` (97 LOC)
- `protocol/providers/gemini.py` -- `GeminiProvider.prepare_process()` (168 LOC)
- `protocol/acp/claude_bridge.py` -- `ClaudeACPBridge`, 13 ACP methods (1042 LOC)
- `protocol/acp/client.py` -- `SubagentClient`, ACP Client impl (451 LOC)
- `protocol/acp/types.py` -- `SubagentResult`, `SubagentError` (19 LOC)
- `orchestration/subagent.py` -- `run_subagent()`, `get_provider_for_model()` (322 LOC)

### Prior Research

- `test-project/.vault/research/2026-02-07-acp-protocol-compliance-brief.md` -- ACP audit

### External Documentation

- Gemini CLI Configuration: <https://geminicli.com/docs/get-started/configuration/>
- Gemini CLI v0.28.0 Changelog: <https://geminicli.com/docs/changelogs/latest/>
- ACP Protocol Overview: <https://agentclientprotocol.com/protocol/overview>
- agent-client-protocol PyPI: <https://pypi.org/project/agent-client-protocol/>
