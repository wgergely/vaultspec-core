# Gemini A2A Alignment Report

**Date:** 2026-02-07
**Synthesized by:** code-analyst
**Sources:** Web research (web-researcher), ADR audit (adr-auditor), code analysis (code-analyst)
**Scope:** Protocol disambiguation, Gemini capability assessment, implementation gap analysis, and prioritized recommendations.

---

## 1. Executive Summary

Our dispatch system interfaces with Gemini CLI at two boundaries: as MCP client (team lead role) and as ACP sub-agent (worker role). Both boundaries are **mechanically functional** today for simple one-shot tasks.

Cross-referencing three independent research streams reveals **4 HIGH**, **7 MEDIUM**, and **9 LOW** severity gaps -- plus a **strategic concern** that no existing ADR addresses: Google created both A2A and Gemini CLI, and evidence shows active convergence (A2A auth in v0.28-preview, RFC #7822 proposing A2A standardization). Our architecture rejected A2A transport because it requires HTTP, but that decision does not account for Gemini CLI likely gaining native A2A capabilities.

The **most impactful operational gap** is that MCP servers are not forwarded to sub-agents (`mcp_servers=[]`), meaning dispatched Gemini sub-agents cannot access cargo build/test/clippy tools -- the core project activity.

The **most urgent fix** is enforcing read-only mode at the protocol level. Currently, read-only enforcement is prompt-injection only; a non-compliant agent can write anywhere in the workspace.

---

## 2. Protocol Disambiguation

Three protocols are in play. Two share the name "ACP" (a real source of confusion in our own ADRs).

### 2.1 ACP -- Agent Client Protocol (Zed)

| Property | Value |
|---|---|
| **Full name** | Agent Client Protocol |
| **Created by** | Zed Industries, August 2025 |
| **Purpose** | Human/Editor <-> AI Agent communication |
| **Transport** | JSON-RPC 2.0 over stdio (subprocess) |
| **Trust model** | Implicit -- same machine, same user, editor-supervised |
| **Relationship** | Vertical: human controls agent through editor intermediary |
| **State model** | Session-based (initialize -> session/new -> prompt loop) |
| **Our usage** | Layer 3 sub-agent transport (`gemini --experimental-acp`) |

**This is the ACP we actually use.** When our code references "ACP," it means this protocol.

### 2.2 A2A -- Agent-to-Agent Protocol (Google/Linux Foundation)

| Property | Value |
|---|---|
| **Full name** | Agent-to-Agent Protocol |
| **Created by** | Google (April 2025), donated to Linux Foundation (June 2025) |
| **Purpose** | Agent <-> Agent communication |
| **Transport** | JSON-RPC 2.0 over HTTPS; SSE for streaming |
| **Trust model** | Untrusted/semi-trusted (OAuth 2.0, mTLS, API keys) |
| **Relationship** | Horizontal: autonomous peers collaborating |
| **State model** | Task-based (submitted -> working -> completed/failed/canceled) |
| **Discovery** | Agent Cards at `/.well-known/agent.json` |
| **Our usage** | Semantic inspiration for task states; no transport usage |

**This is the protocol Google is building into Gemini CLI.** PR #3079 (A2A client) was closed as "not prioritized," but v0.28-preview adds A2A auth infrastructure.

### 2.3 The Naming Collision: IBM's "ACP"

IBM had a protocol also called "ACP" (Agent Communication Protocol). In September 2025, IBM's ACP **merged into A2A** under Linux Foundation governance. This means:

- "ACP" in Zed/our context = **Agent Client Protocol** (stdio, editor-agent)
- "ACP" in IBM/Google/A2A context = **Agent Communication Protocol** (now part of A2A)
- These are **completely different protocols** that share an acronym

Our ADRs sometimes reference "A2A semantics" when discussing task state machines inspired by A2A, while using Zed's ACP for actual transport. This is architecturally sound but the naming overlap creates confusion.

### 2.4 MCP -- Model Context Protocol (Anthropic)

| Property | Value |
|---|---|
| **Full name** | Model Context Protocol |
| **Created by** | Anthropic |
| **Purpose** | Tool and resource access for AI agents |
| **Transport** | JSON-RPC 2.0 over stdio or HTTP |
| **Our usage** | Layer 1 team-lead interface (`pp-dispatch` MCP server) |

MCP is complementary to both ACP and A2A. In ACP mode, Gemini CLI retains full MCP support. Our MCP server is how both Claude Code and Gemini CLI (as team leads) access dispatch tools.

### 2.5 How They Relate

```
ACP:  Human -> Editor/Client -> [stdio] -> Agent subprocess
      (vertical: human controls agent through intermediary)

A2A:  Agent A -> [HTTPS] -> Agent B -> [HTTPS] -> Agent C
      (horizontal: peers collaborating, no human in wire)

MCP:  Agent -> [stdio/HTTP] -> Tool Server -> response
      (tool access: agent invokes tools for data/actions)

Our architecture:
  Human -> Claude/Gemini (team lead) -> [MCP] -> pp-dispatch -> [ACP] -> sub-agent
  We use ACP where A2A would be semantically correct (agent-to-agent delegation).
```

---

## 3. What Gemini Supports Today

### 3.1 ACP Support (via `--experimental-acp`)

**Status:** Working but experimental. Used by Zed, IntelliJ, Neovim, our dispatch system.

| ACP Feature | Gemini Status | Our Usage |
|---|---|---|
| `initialize` (version + capabilities) | Working | Used, response ignored |
| `session/new` (cwd, mcp_servers) | Working | Used, mcp_servers=[] |
| `session/prompt` (text content blocks) | Working | Used |
| `session/update` (streaming) | Working | Consumed, not forwarded |
| `session/request_permission` | Working | Auto-approved |
| `fs/read_text_file`, `fs/write_text_file` | Working | Used |
| `terminal/*` (full lifecycle) | Working | Used |
| `session/cancel` | Available | NOT used from MCP path |
| `session/load` (resume) | v0.28-preview | Not used |
| `session/set_mode` | Available | Not used |
| MCP server provisioning | Available | NOT used (empty list) |

**Version notes:**

- v0.9.0: Windows ACP hang fix (Zed pins this as minimum on Windows)
- v0.27.0: Agent Skills stable, sub-agent registry, event-driven scheduler
- v0.28.0-preview: ACP session resume, A2A auth infrastructure

### 3.2 A2A Support (Emerging, Not Production)

| A2A Feature | Status | Evidence |
|---|---|---|
| A2A Client (`A2AClient`) | Code exists, PR closed (not merged) | PR #3079 |
| A2A Types | Code exists | `packages/core/src/a2a/types.ts` |
| `@a2a` Tool | Code exists | `packages/core/src/tools/a2a-tool.ts` |
| A2A Server | Separate npm package | `@google/gemini-cli-a2a-server` |
| A2A Auth config | v0.28-preview | Pluggable auth provider infrastructure |
| A2A Admin settings | v0.28-preview | Configuration UI |
| Agent Cards | Server-side only | Separate package |

**Key signal:** Gemini CLI maintainers said A2A client work is "not prioritized" but remain open to server-side contributions. RFC #7822 proposes standardizing on A2A for all integrations. The trajectory points toward future A2A adoption, but it is not usable today.

### 3.3 MCP Support

| Feature | Status |
|---|---|
| MCP client (tool invocation) | Working |
| MCP in ACP mode | Working ("MCP servers remain fully available") |
| MCP server enable/disable (v0.27) | Working |
| MCP server prefix enforcement | Working |

---

## 4. What Our Implementation Does

### 4.1 Layer 1: MCP Server (Team Lead Interface)

**File:** `mcp_dispatch.py`

Exposes dispatch capabilities as MCP tools consumable by both Claude Code and Gemini CLI:

| Tool | Purpose | Status |
|---|---|---|
| `dispatch_agent` | Async sub-agent dispatch, returns taskId | Working |
| `get_task_status` | Poll task engine for results | Working |
| `cancel_task` | Cancel running task | Working (not graceful) |
| `list_agents` | Discover available agents | Working |
| `get_locks` | Inspect advisory locks | Working |

Agent resources (`agents://{name}`) expose metadata as MCP resources.

### 4.2 Layer 2: Task Engine

**File:** `task_engine.py`

5-state lifecycle: `working -> completed | failed | cancelled | input_required`

Advisory locking for workspace coordination (in-memory, warning-only). TTL-based expiry (1 hour). Automatic lock release on terminal state transitions.

Note: `input_required` state exists but is **never triggered** by any code path.

### 4.3 Layer 3: ACP Sub-Agent Transport

**File:** `acp_dispatch.py` + `agent_providers/`

| Component | Gemini Implementation | Claude Implementation |
|---|---|---|
| Executable | `gemini --experimental-acp` | `npx -y @zed-industries/claude-code-acp` |
| System prompt | Temp file via `GEMINI_SYSTEM_MD` env var | `session_meta["systemPrompt"]` + prepended to first prompt |
| Rules source | `.gemini/GEMINI.md` (with @include resolution) | `.claude/CLAUDE.md` (with @include resolution) |
| Model selection | `--model` CLI arg | ACP session / adapter config |
| Prompt ordering | Rules first, persona second | Persona first, rules second |
| Temp file cleanup | Yes (temp file deleted) | None needed |
| Fallback | Falls back to Claude on failure | Terminal (no fallback) |

Shared infrastructure: `GeminiDispatchClient` (ACP client callbacks), `spawn_agent_process` (ACP SDK), permission auto-approval, workspace-scoped file I/O, terminal management.

---

## 5. Misalignment Matrix

### 5.1 HIGH Severity

| # | Gap | Severity | Effort | Recommendation |
|---|---|---|---|---|
| H1 | **No Gemini CLI version pinning.** Zed pins v0.9.0 (Win) / v0.2.1+ (other). We use whatever is on PATH. `--experimental-acp` behavior can change without warning. | HIGH | 2h | Add version detection in `GeminiProvider.prepare_process()`. Warn below v0.27.0, fail below v0.9.0. |
| H2 | **Read-only mode not enforced at protocol level.** `write_text_file()` allows all writes within workspace. Permission enforcement is prompt-injection only. Advisory locks warn but don't block. | HIGH | 1h | Check `mode` in `write_text_file()` callback. Reject writes outside `.docs/` when read-only. |
| H3 | **MCP servers not forwarded to sub-agents.** `mcp_servers=[]` in `session/new`. Sub-agents lose access to `rust-mcp-server` (cargo tools) and `pp-dispatch` (nested dispatch). Web research confirms MCP works in ACP mode. | HIGH | 4h | Read `.gemini/settings.json` mcpServers, convert to ACP format, pass in `session/new`. |
| H4 | **InitializeResponse capabilities ignored.** We send `client_capabilities` but never inspect the agent's response. Don't know what content blocks, modes, or features the agent supports. | HIGH | 2h | Store `response.agentCapabilities` after `conn.initialize()`. Gate features accordingly. |

### 5.2 MEDIUM Severity

| # | Gap | Severity | Effort | Recommendation |
|---|---|---|---|---|
| M1 | **`GEMINI_SYSTEM_MD` is undocumented.** Not part of ACP protocol. Gemini-specific mechanism that may break silently across versions. | MEDIUM | 2h | Add fallback: prepend system prompt to first `session/prompt` (like ClaudeProvider). |
| M2 | **No graceful ACP cancellation from MCP.** `cancel_task` kills asyncio.Task but never sends `session/cancel`. Gemini process continues until force-killed. | MEDIUM | 2h | Send `await conn.cancel(session_id)` before cancelling asyncio.Task. |
| M3 | **Terminal commands unrestricted in read-only.** Agent can execute `git commit`, `rm -rf`, etc. Permission auto-approval + no command filtering. | MEDIUM | 3h | Disable terminal capability (`terminal=False`) or implement command allowlisting in read-only mode. |
| M4 | **No `--cwd` CLI argument for Gemini.** Relies solely on ACP session `cwd` parameter. Gemini's respect for this is unverified. | MEDIUM | 15m | Pass `--cwd` in CLI args as belt-and-suspenders. |
| M5 | **System prompt ordering inconsistent.** Gemini: rules-first, persona-second. Claude: persona-first, rules-second. May affect model attention patterns. | MEDIUM | 1h | Standardize ordering or make configurable per provider. |
| M6 | **`gemini-2.5-pro` mapped to LOW capability.** Pro model at LOW seems incorrect. Creates circular fallback (LOW -> gemini-2.5-pro). | MEDIUM | 5m | Map to MEDIUM. |
| M7 | **Stale data in compliance brief.** Brief claims we don't send `client_capabilities` (line 294). Current code DOES send them (`acp_dispatch.py:634-647`). | MEDIUM | 15m | Update or mark superseded. |

### 5.3 LOW Severity

| # | Gap | Severity | Effort | Recommendation |
|---|---|---|---|---|
| L1 | `resolve_includes()` duplicated in both providers | LOW | 1h | Extract to shared utility |
| L2 | Stderr silently consumed in non-debug mode | LOW | 1h | Log last N lines for post-mortem |
| L3 | Session logs never cleaned up | LOW | 1h | Add TTL-based cleanup |
| L4 | No Antigravity provider (but referenced in code) | LOW | 30m | Remove dead references or implement |
| L5 | `provider_override` not exposed via MCP | LOW | 1h | Add optional `provider` parameter |
| L6 | Windows cleanup heuristics fragile | LOW | 4h | Address underlying Proactor issues |
| L7 | No Gemini-specific MCP client testing | LOW | 8h | Integration test with Gemini as MCP client |
| L8 | No bidirectional fallback (Claude -> Gemini) | LOW | 2h | Implement or document as intentional |
| L9 | No A2A transport reassessment mechanism | LOW | 1h | Quarterly protocol landscape review |

### 5.4 Cross-Reference Confidence

Findings corroborated by multiple research streams have highest confidence:

| Finding | Web | ADR | Code | Confidence |
|---|---|---|---|---|
| `--experimental-acp` fragility | Yes | Yes | Yes | **Highest** (all three) |
| A2A convergence risk | Yes | Yes | -- | **High** (web + ADR) |
| Read-only enforcement gap | -- | Yes | Yes | **High** (ADR + code) |
| MCP servers not forwarded | Yes | -- | Yes | **High** (web + code) |
| Permission auto-approval by design | Yes | Yes | Yes | **Highest** (all three, accepted risk) |
| Stale compliance brief data | -- | Yes | Yes | **High** (ADR contradicts code) |
| Graceful cancellation gap | -- | Yes | Yes | **High** (ADR + code) |

---

## 6. Recommended Next Steps (Prioritized)

### Phase 5A: Immediate (this sprint, <2 hours total)

1. **Enforce read-only in `write_text_file()`** -- Single path check in callback. 1 hour.
2. **Fix `gemini-2.5-pro` capability mapping** -- One-line change. 5 minutes.
3. **Update stale compliance brief** -- Mark Section 4.2 as corrected. 15 minutes.

### Phase 5B: Operational (next sprint, ~10 hours total)

4. **Forward MCP servers to sub-agents** -- Highest operational impact. 4 hours.
5. **Add Gemini CLI version detection** -- Runtime warning/fail. 2 hours.
6. **Send `session/cancel` on task cancellation** -- Graceful shutdown. 2 hours.
7. **Inspect InitializeResponse** -- Store and use agent capabilities. 2 hours.

### Phase 5C: Protocol Alignment (following sprint, ~7 hours total)

8. **`GEMINI_SYSTEM_MD` fallback** -- Dual delivery (env var + prompt prepend). 2 hours.
9. **Restrict terminal in read-only** -- Close mutation escape hatch. 3 hours.
10. **Extract shared `resolve_includes()`** -- DRY refactor. 1 hour.
11. **Standardize system prompt ordering** -- Consistency. 1 hour.

### Phase 5D: Strategic (requires ADR, ~20 hours total)

12. **Draft A2A Convergence ADR** -- Document risk and triggers. 4 hours.
13. **Integration test: Gemini as MCP client** -- Validate team-lead path. 8 hours.
14. **A2A transport feasibility study** -- Evaluate stdio A2A. 4 hours.
15. **Explore v0.28 ACP session resume** -- Enable long-running tasks. 4 hours.

---

## 7. ADR Update Recommendations

### 7.1 Protocol Selection ADR (`2026-02-07-dispatch-protocol-selection.md`)

**Add new section: "Gemini A2A Convergence Watch"**

The ADR rejected A2A transport (Decision 4) because it requires HTTP. This rejection remains valid today, but lacks a **convergence contingency** for Google's dual ownership of A2A and Gemini CLI.

Recommended addition:

```markdown
### Decision 4a: A2A Convergence Monitoring (NEW)

**Context:** Google created both A2A and Gemini CLI. Evidence of convergence:
- A2A code exists in Gemini CLI codebase (PR #3079, closed but code present)
- v0.28-preview adds A2A auth infrastructure
- RFC #7822 proposes standardizing on A2A for all Gemini CLI integrations
- Google donated A2A to Linux Foundation with 150+ supporting organizations

**Decision:** Monitor Gemini CLI releases for A2A changes. Reassess if:
1. Gemini CLI adds `--a2a` or `--experimental-a2a` flag
2. A2A spec adds stdio transport (Issue #1074 or equivalent)
3. Gemini CLI's sub-agent registry (v0.27) adopts A2A task semantics

**Contingency:** The `AgentProvider` abstraction at Layer 3 supports adding
an `A2AProvider` without modifying the MCP or task engine layers.
```

### 7.2 Task Contract ADR (`2026-02-07-dispatch-task-contract.md`)

**Update: 5-state to A2A 9-state mapping**

The ADR documents this mapping as "future work." With A2A convergence becoming more concrete, the mapping should be elevated from theoretical to documented-and-tested.

Recommended addition: a concrete mapping table with implementation notes for when an `A2AProvider` is added.

### 7.3 Workspace Safety ADR (`2026-02-07-dispatch-workspace-safety.md`)

**Update: Protocol-Level Read-Only Enforcement**

Decision 1 describes advisory locking but does not address protocol-level enforcement. The read-only mode gap (H2) should be documented as a known limitation with a fix committed (Phase 5A item 1).

Recommended addition:

```markdown
### Addendum: Protocol-Level Write Enforcement

The `write_text_file()` ACP callback MUST enforce permission mode
boundaries. When mode="read-only", writes outside `.docs/` are rejected
with an error response. This supplements the prompt-level instruction
and advisory lock warning with actual protocol enforcement.
```

### 7.4 Architecture ADR (`2026-02-07-dispatch-architecture.md`)

**Update: MCP Server Forwarding**

Decision 4 preserves the ACP client wrapper but does not address MCP server provisioning to sub-agents. The `mcp_servers=[]` gap (H3) should be documented with a design for forwarding.

Recommended addition: document how `session/new` `mcp_servers` parameter should be populated from `.gemini/settings.json` or a dispatch-level configuration.

### 7.5 New ADR: Gemini A2A Convergence

**Status:** Recommended for Phase 5D

A standalone ADR analyzing:

- The evidence for Google A2A + Gemini CLI convergence
- Impact on our Layer 3 architecture
- Trigger conditions for adding an A2A transport provider
- The naming collision between Zed's ACP and IBM's ACP (now part of A2A)
- Design sketch for `A2AProvider` alongside existing providers

### 7.6 Stale Data Correction

**File:** `2026-02-07-acp-protocol-compliance-brief.md`

Section 4.2 (line ~294) states: "We don't send `client_capabilities` or `client_info`." This is **incorrect** in the current codebase. `acp_dispatch.py:634-647` sends both. Either:

- Strike the sentence and add a correction note, or
- Add a dated addendum noting the code was updated after the brief was written.

---

## Sources

### Research Inputs

- **Web Research:** `.docs/research/2026-02-07-gemini-a2a-web-research.md`
- **ADR Audit:** `.docs/research/2026-02-07-gemini-a2a-adr-audit.md`
- **Code Analysis:** `.docs/research/2026-02-07-gemini-a2a-code-analysis.md`

### Key External References

- [ACP Protocol Overview](https://agentclientprotocol.com/protocol/overview)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [Gemini CLI v0.27.0 Changelog](https://geminicli.com/docs/changelogs/latest/)
- [Gemini CLI v0.28.0-preview Changelog](https://geminicli.com/docs/changelogs/preview/)
- [RFC #7822: Gemini CLI A2A Development-Tool Extension](https://github.com/google-gemini/gemini-cli/discussions/7822)
- [PR #3079: A2A Client Support](https://github.com/google-gemini/gemini-cli/pull/3079)
- [Zed Blog: Bring Your Own Agent](https://zed.dev/blog/bring-your-own-agent-to-zed)

### Internal Code References

- `acp_dispatch.py:213-483` -- GeminiDispatchClient
- `acp_dispatch.py:503-752` -- run_dispatch()
- `acp_dispatch.py:619-649` -- ACP initialization + session creation
- `agent_providers/gemini.py:138-177` -- GeminiProvider.prepare_process()
- `agent_providers/claude.py:129-183` -- ClaudeProvider.prepare_process()
- `mcp_dispatch.py:389-468` -- dispatch_agent MCP tool
- `mcp_dispatch.py:471-546` -- _run_dispatch_background()
- `task_engine.py:279-567` -- TaskEngine
- `.gemini/settings.json:34-45` -- MCP server configuration
- `ref/zed/crates/project/src/agent_server_store.rs:1340-1385` -- Zed's Gemini integration
