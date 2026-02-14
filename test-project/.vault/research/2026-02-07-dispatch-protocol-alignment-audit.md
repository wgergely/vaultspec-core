---
tags: ["#audit", "#dispatch", "#protocol-alignment"]
related:
  - "[[2026-02-07-a2a-protocol-compliance-brief.md]]"
  - "[[2026-02-07-acp-protocol-compliance-brief.md]]"
  - "[[2026-02-07-dispatch-project-scope.md]]"
  - "[[2026-02-07-dispatch-protocol-selection.md]]"
  - "[[2026-02-07-dispatch-architecture.md]]"
  - "[[2026-02-07-dispatch-task-contract.md]]"
  - "[[2026-02-07-dispatch-workspace-safety.md]]"
date: 2026-02-07
---

# Dispatch Protocol Alignment Audit

**Author:** ADR Auditor (adr-auditor)
**Date:** 2026-02-07
**Inputs:** A2A Protocol Compliance Brief, ACP Protocol Compliance Brief, 5 Dispatch ADRs, mcp_dispatch.py, task_engine.py

---

## 1. Per-ADR Decision Compliance

### ADR: Project Scope and Goals

| # | Decision | Protocol Alignment | Implementation Status |
|---|----------|-------------------|----------------------|
| 1 | Framework is a Full Agent Development Platform | ALIGNED. Both protocols confirm the system operates at platform level: MCP tool interface, A2A-inspired state machine, ACP transport. | IMPLEMENTED. mcp_dispatch.py + task_engine.py + agent_providers/ form a complete dispatch platform. |
| 2 | API Must Be Tool-Agnostic | ALIGNED. MCP is the correct protocol for tool-agnostic service interfaces. Both Claude Code and Gemini can connect via .mcp.json. | IMPLEMENTED. dispatch_agent, list_agents, get_task_status, cancel_task exposed as MCP tools. .mcp.json registered. |
| 3 | Python is the Implementation Language | ALIGNED. Both protocol SDKs (mcp, acp) have official Python support. A2A has no Rust SDK. | IMPLEMENTED. All dispatch code is Python. |

**Verdict: 3/3 decisions correctly implemented.**

---

### ADR: Protocol Selection

| # | Decision | Protocol Alignment | Implementation Status |
|---|----------|-------------------|----------------------|
| 1 | Three-Layer Protocol Stack (MCP -> Task Engine -> ACP) | ALIGNED. A2A brief confirms our task engine correctly adopts A2A state semantics at Layer 2 without requiring A2A HTTP transport. ACP brief confirms ACP is correct for Layer 3 subprocess transport. | IMPLEMENTED. Three layers are architecturally clean and operational. |
| 2 | MCP is the Dispatch Interface (Layer 1) | ALIGNED. MCP is the established standard for this boundary. | IMPLEMENTED. FastMCP server with typed tool schemas, async dispatch, .mcp.json auto-discovery. |
| 3 | ACP Remains Sub-Agent Transport (Layer 3) | PARTIALLY ALIGNED. ACP brief identifies a fundamental misalignment: ACP is a Human-to-Agent protocol, but we use it for Agent-to-Agent delegation. The `request_permission` auto-approve is a symptom of this misalignment. However, there is no better alternative today -- A2A requires HTTP, and ACP proxy chains are RFD-stage. | IMPLEMENTED with known compromises. The YOLO auto-approve, missing client capabilities, and hardcoded interactive=False are all consequences of using a human-agent protocol for agent-agent work. |
| 4 | Rejected: A2A for Transport | STILL VALID. A2A brief confirms HTTP transport is still required (stdio proposal Issue #1074 not merged). Running localhost HTTP per sub-agent remains impractical for local subprocess dispatch. | N/A (rejection stands). |

**Verdict: 3/4 decisions correctly implemented. Decision 3 (ACP at Layer 3) works but has documented protocol misalignment that creates downstream compliance gaps.**

---

### ADR: MCP Server Architecture

| # | Decision | Protocol Alignment | Implementation Status |
|---|----------|-------------------|----------------------|
| 1 | Python MCP Server Using Official `mcp` SDK | ALIGNED. | IMPLEMENTED. FastMCP server over stdio transport. |
| 2 | Exposed MCP Tools (dispatch_agent, list_agents, get_task_status, cancel_task) | ALIGNED. Additionally `get_locks` was added for Phase 4 advisory locking visibility. | IMPLEMENTED. All 4 ADR-specified tools + bonus get_locks tool. |
| 3 | Incremental Implementation Phasing (4 phases) | ALIGNED per protocol review. | Phase 1 (sync dispatch): COMPLETE, now superseded by async. Phase 2 (async tasks): COMPLETE. dispatch_agent returns immediately with taskId. Phase 3 (Agent Cards as MCP resources): COMPLETE. agents:// URI scheme with runtime frontmatter parsing, background polling, list_changed notifications. Phase 4 (locking and permissions): COMPLETE. Advisory locking implemented in LockManager, permission prompt injection for read-only mode. |
| 4 | Preserve acp_dispatch.py as ACP Client Library | ALIGNED. | IMPLEMENTED. mcp_dispatch.py imports run_dispatch, parse_frontmatter, safe_read_text from acp_dispatch.py. CLI entry point preserved. |

**Verdict: 4/4 decisions correctly implemented. All four phases delivered.**

---

### ADR: Task Result Contract

| # | Decision | Protocol Alignment | Implementation Status |
|---|----------|-------------------|----------------------|
| 1 | Adopt MCP Tasks 5-State Machine | ALIGNED. A2A brief confirms all 4 rejected states (submitted, auth_required, rejected, unknown) are irrelevant for local subprocess dispatch. The 5-state model maps cleanly to both MCP Tasks and A2A's core states. | IMPLEMENTED. task_engine.py defines TaskStatus with WORKING, INPUT_REQUIRED, COMPLETED, FAILED, CANCELLED. Valid transitions enforced. Terminal states are immutable. |
| 2 | Structured Task Result Schema | PARTIALLY ALIGNED. The ADR specifies a schema with `artifacts` array, `summary`, `duration_seconds`, `model_used`. A2A brief highlights that A2A Artifacts provide a much richer contract (artifact_id, name, description, parts with media_type). | PARTIALLY IMPLEMENTED. The result schema is built in _run_dispatch_background (mcp_dispatch.py:433-442) with taskId, status, agent, model_used, duration_seconds, summary, response, and an empty artifacts array. **GAP: artifacts is always `[]`**. Sub-agents write files by convention but never report them as structured artifacts. The response field is truncated stdout (first 500 chars for summary, full for response). |
| 3 | READ-WRITE and READ-ONLY Permission Modes | PARTIALLY ALIGNED. ACP brief reveals that enforcement is prompt-level only (natural language instruction to agent). The ACP auto-approve means a non-compliant agent can still write anywhere. | PARTIALLY IMPLEMENTED. Mode resolution works correctly (_resolve_effective_mode checks per-dispatch > agent frontmatter > default). Prompt injection works (_inject_permission_prompt prepends read-only instructions). Advisory locking assigns lock_paths based on mode. **GAP: No protocol-level enforcement.** The ACP write_text_file handler enforces workspace boundaries but not mode boundaries. |
| 4 | Rejected: Full A2A 9-State Machine | STILL VALID. A2A brief confirms the 4 extra states add no value for local subprocess dispatch. If remote dispatch is added, the 5-state model can map to A2A's 9-state at that boundary. | N/A (rejection stands). |

**Verdict: 2/4 fully implemented, 2/4 partially implemented. Key gaps: empty artifacts array, prompt-only permission enforcement.**

---

### ADR: Workspace Safety and Agent Discovery

| # | Decision | Protocol Alignment | Implementation Status |
|---|----------|-------------------|----------------------|
| 1 | Shared Workspace with Advisory Locking | ALIGNED. A2A brief describes artifact-based coordination as the protocol-native approach, but advisory locking is a pragmatic alternative for local shared-filesystem scenarios. | IMPLEMENTED. LockManager (task_engine.py:143-276) provides acquire_lock, release_lock, check_conflicts, get_lock, get_locks. Locks are in-memory, thread-safe, and automatically released on terminal state transitions via TaskEngine._release_lock(). |
| 2 | Agent Cards as MCP Resources from Frontmatter | ALIGNED. A2A brief identifies gaps: our agents:// resources lack capabilities flags, security schemes, input/output modes, and detailed skills that A2A Agent Cards provide. But for internal local dispatch, the simplified schema is sufficient. | IMPLEMENTED. _register_agent_resources() parses frontmatter and registers FunctionResource objects with agents:// URIs. Background polling (_poll_agent_files) detects changes and emits list_changed notifications. |
| 3 | Team Lead Discovery via list_agents Tool | ALIGNED. | IMPLEMENTED. list_agents reads and parses all .rules/agents/*.md files, returns JSON with name, tier, description. |
| 4 | Rejected: Full Workspace Isolation | STILL VALID. ACP brief confirms sub-agents need to read shared source code and write to shared directories. The project workflow (1-4 concurrent agents) does not warrant isolation overhead. | N/A (rejection stands). |

**Verdict: 3/4 fully implemented. Decision 2 (Agent Cards) is implemented but with reduced schema richness compared to A2A spec.**

---

## 2. Implementation Gaps (ADR Promises vs Code)

### Gap 1: Artifacts Always Empty (CRITICAL)

**ADR Promise (Task Contract, Decision 2):** "The `artifacts` array captures what the sub-agent produced, replacing the convention of sub-agents write files and hope the caller knows where."

**Reality (mcp_dispatch.py:442):** `"artifacts": []` -- hardcoded empty array. Sub-agents write files to .docs/ by convention. The team lead has no structured way to know what was produced.

**Root Cause:** No mechanism for sub-agents to report artifacts back through the ACP session. The ACP response is a single text block. There is no post-processing to extract file references from the response.

**Impact:** High. The team lead must guess what files were written, or manually search .docs/ after each dispatch. Task chaining (use output of task A as input to task B) requires manual intervention.

---

### Gap 2: input_required State Never Triggered (MODERATE)

**ADR Promise (Task Contract, Decision 1):** The state machine includes `input_required` with transitions to/from `working`. "Sub-agent needs additional input from the team lead."

**Reality:** task_engine.py defines the state and valid transitions, but neither mcp_dispatch.py nor acp_dispatch.py ever transitions a task to INPUT_REQUIRED. There is no `resume_task` or `send_input` MCP tool. The A2A brief confirms this is a key gap for interactive turn-taking.

**Root Cause:** The MCP server wraps ACP as one-shot dispatch (interactive=False). There is no mechanism for a sub-agent to signal it needs input, nor for the team lead to inject additional input mid-task.

**Impact:** Moderate. Sub-agents must either succeed or fail with the initial prompt. Complex tasks that need clarification will fail unnecessarily.

---

### Gap 3: No Graceful ACP Cancel on MCP Cancel (MODERATE)

**ADR Promise (Architecture, Decision 2):** cancel_task provides graceful lifecycle management.

**Reality (mcp_dispatch.py:547-549):** cancel_task cancels the asyncio.Task and relies on process termination. ACP brief confirms: "cancel_task kills the asyncio.Task but does NOT send session/cancel to the ACP agent."

**Root Cause:** The cancel path terminates the Python coroutine, which triggers CancelledError. The context manager for spawn_agent_process eventually kills the subprocess, but the agent never receives a graceful cancellation signal.

**Impact:** Moderate. Agent processes may leave partial work, orphaned temp files, or corrupt session state. The agent has no opportunity to checkpoint or clean up.

---

### Gap 4: No Client Capabilities in ACP Initialize (LOW)

**ADR Promise (Protocol Selection, Decision 3):** "ACP is specifically designed for client-to-agent communication."

**Reality (acp_dispatch.py:620):** `await conn.initialize(protocol_version=1)` sends no client_capabilities or client_info. ACP brief flags this as non-compliant: "The agent doesn't know our filesystem and terminal capabilities."

**Root Cause:** The initialize call was written for MVP and never enhanced. The ACP SDK likely accepts capabilities parameters that we don't pass.

**Impact:** Low for Gemini (which has built-in tools), but potentially significant for Claude Code ACP adapter which may gate features on client capability advertisement.

---

### Gap 5: No Streaming Exposure to MCP Client (LOW)

**ADR Promise (Architecture, Phase 2):** "Non-blocking dispatch enabling concurrent sub-agents." Implied: visibility into task progress.

**Reality:** ACP session/update notifications (plan updates, tool calls, text chunks) are consumed by GeminiDispatchClient.session_update() and written to stderr. The MCP client sees nothing until get_task_status returns the final result. ACP brief: "Rich ACP streaming updates are consumed internally, never surfaced to the MCP client."

**Root Cause:** MCP does not natively support streaming progress updates from tools. Would require MCP progress notifications or a polling-based stream tool.

**Impact:** Low for current usage (team leads poll get_task_status). Would become moderate if tasks run for extended periods.

---

### Gap 6: Session Log Correlation (LOW)

**ADR Promise:** Not explicitly promised, but implied by the task engine's structured tracking.

**Reality (ACP brief):** SessionLogger writes JSONL logs to .rules/logs/{sessionId}.log, but there is no mapping from task_engine task_id to ACP session_id. Log files are never cleaned up. The MCP server does not expose log access.

**Root Cause:** The session logger predates the task engine. No correlation field was added when the task engine was introduced.

**Impact:** Low. Debugging requires manual correlation between task IDs and session log files.

---

## 3. Rejection Validity Assessment

### Rejection 1: A2A for Transport (Protocol Selection, Decision 4)

**Original Rationale:** A2A requires HTTP. Running localhost HTTP servers per sub-agent is impractical.

**Protocol Expert Assessment:** A2A brief confirms HTTP is still required. The stdio proposal (Issue #1074) remains unmerged.

**Verdict: REJECTION REMAINS VALID.** No change in protocol landscape invalidates this decision. If A2A adds stdio transport in the future, this should be reassessed.

---

### Rejection 2: Full A2A 9-State Machine (Task Contract, Decision 4)

**Original Rationale:** submitted, auth_required, rejected, unknown have no mapping in local subprocess dispatch.

**Protocol Expert Assessment:** A2A brief confirms all 4 states are irrelevant for our local subprocess model. Specifically:

- `submitted` is unnecessary because MCP tool invocation is synchronous (task goes directly to working).
- `auth_required` is not applicable to trusted local processes.
- `rejected` has no use case when the dispatcher controls agent selection.
- `unknown` is an error catch-all representable as `failed`.

**Verdict: REJECTION REMAINS VALID.** The 5-state model is correct for local dispatch. If remote agent dispatch is added, the mapping to A2A's 9-state should happen at the transport boundary, not in the core engine.

---

### Rejection 3: Full Workspace Isolation (Workspace Safety, Decision 4)

**Original Rationale:** Sub-agents need shared filesystem access. Isolation requires merge/reconciliation overhead.

**Protocol Expert Assessment:** ACP brief confirms sub-agents read shared source code and write to shared .docs/ directories. The current concurrency model (1-4 agents) does not warrant isolation.

**Verdict: REJECTION REMAINS VALID.** Advisory locking provides adequate coordination. Revisit if concurrency exceeds 4-6 agents or if write conflict incidents increase.

---

### Rejection 4: ACP Proxy Chains (Protocol Selection, implicit)

**Original Rationale:** ACP proxy chains are RFD-stage with only a Rust reference implementation.

**Protocol Expert Assessment:** ACP brief does not mention proxy chains advancing beyond RFD. The existing MCP+ACP layering provides equivalent functionality.

**Verdict: REJECTION REMAINS VALID.** Monitor ACP proxy chain development but no action needed now.

---

## 4. Phase 5 Recommendations

Based on both protocol briefs and the gap analysis above, Phase 5 should address three categories: **interactive dispatch**, **artifact tracking**, and **protocol compliance hardening**.

### 4.1 Implement input_required Flow (Interactive Dispatch)

**Problem:** Sub-agents either succeed or fail. No mechanism for clarification or iterative refinement.

**Design (drawing from both A2A and ACP patterns):**

1. Add a `resume_task` MCP tool:

   ```
   resume_task(task_id: str, message: str) -> str
   ```

   - Validates task is in INPUT_REQUIRED state.
   - Injects `message` as a new prompt in the existing ACP session.
   - Transitions task back to WORKING.

2. Modify `_run_dispatch_background` to support multi-turn:
   - Instead of a single `run_dispatch()` call, maintain the ACP session open.
   - When the agent's response includes a signal phrase (e.g., "[INPUT_REQUIRED]" or a structured JSON block), transition the task to INPUT_REQUIRED.
   - Wait (via asyncio.Event) for input from `resume_task`.
   - Re-prompt the agent with the provided input.

3. ACP session must stay alive across turns:
   - Refactor `run_dispatch()` to accept a message queue instead of a single task string.
   - The ACP session remains open until the task reaches a terminal state.

**A2A Alignment:** This implements A2A's `input_required` pattern over local ACP transport.

**ACP Alignment:** Uses ACP's native multi-turn `session/prompt` capability, which is already supported but disabled (interactive=False).

### 4.2 Implement Artifact Tracking

**Problem:** artifacts array is always empty. No structured knowledge of what sub-agents produce.

**Design (three complementary approaches):**

1. **Response parsing (immediate, S-effort):**
   - Post-process the agent's response text to extract file paths matching known patterns (`.docs/**/*.md`, `crates/**/*.rs`).
   - Populate the artifacts array with `{type: "file", path: <extracted>}`.
   - Heuristic-based but works with existing sub-agents without modification.

2. **System prompt contract (immediate, S-effort):**
   - Add an artifact reporting instruction to the permission/system prompt:

     ```
     When you complete your task, include a JSON block at the end of your response:
     ```json
     {"artifacts": [{"type": "file", "path": "relative/path.md", "description": "..."}]}
     ```

   - Parse this structured block from the response.

3. **ACP session metadata (future, M-effort):**
   - Use ACP session/update metadata or a custom content block to report artifacts in-band.
   - Requires extending both the GeminiDispatchClient.session_update() handler and the response parser.

**A2A Alignment:** Approach 2-3 mirror A2A's Artifact concept (artifact_id, name, description, parts).

### 4.3 Fix ACP Cancel Path

**Problem:** cancel_task does not send session/cancel to the agent.

**Design:**

1. Store the ACP connection reference alongside the asyncio.Task in _background_tasks:

   ```python
   _background_tasks: dict[str, tuple[asyncio.Task, Optional[Connection]]] = {}
   ```

2. In cancel_task, send `conn.cancel(session_id)` before cancelling the asyncio.Task:

   ```python
   conn, session_id = _connections.get(task_id, (None, None))
   if conn and session_id:
       await conn.cancel(session_id)
   ```

3. Allow a grace period (e.g., 5 seconds) for the agent to acknowledge cancellation before force-killing.

**ACP Alignment:** Directly uses the ACP `session/cancel` notification, which is the protocol-correct cancellation mechanism.

### 4.4 Add Client Capabilities to ACP Initialize

**Problem:** initialize() sends no capabilities, so agents don't know we support filesystem and terminal operations.

**Design:**

1. Construct a capabilities object based on our GeminiDispatchClient implementation:

   ```python
   await conn.initialize(
       protocol_version=1,
       client_capabilities={
           "fileSystem": {"readTextFile": True, "writeTextFile": True},
           "terminal": {"create": True, "output": True, "wait": True, "kill": True},
           "prompt": {"text": True},
       },
   )
   ```

2. Capture the agent's response capabilities (AgentCapabilities) and store them in the task metadata for debugging.

**ACP Alignment:** Restores ACP-compliant capability negotiation.

### 4.5 Enrich Agent Card Schema

**Problem:** MCP resources have a simpler schema than A2A Agent Cards (no capabilities flags, no security, no I/O modes).

**Design:**

1. Extend frontmatter schema with optional A2A-inspired fields:

   ```yaml
   capabilities:
     streaming: false
     input_required: true
   input_modes: ["text/plain"]
   output_modes: ["text/plain", "application/json"]
   ```

2. Parse and include these in the agents:// MCP resource response.

3. Use capabilities in dispatch routing (e.g., only dispatch to agents that support input_required for interactive tasks).

**A2A Alignment:** Brings Agent Card schema closer to A2A spec without requiring A2A transport.

---

## 5. Priority Gap List

Ranked by impact and effort. Effort: S = <1 day, M = 1-3 days, L = 3-5 days.

| Rank | Gap | Impact | Effort | Phase 5 Section |
|------|-----|--------|--------|-----------------|
| 1 | Artifacts always empty | HIGH -- blocks task chaining, forces manual file discovery | S | 4.2 (approach 1+2) |
| 2 | input_required flow not wired | HIGH -- sub-agents cannot request clarification, complex tasks fail unnecessarily | L | 4.1 |
| 3 | No graceful ACP cancel | MODERATE -- agent processes may leave partial work, no cleanup opportunity | M | 4.3 |
| 4 | Missing client capabilities in ACP initialize | LOW -- agents may not attempt all supported operations | S | 4.4 |
| 5 | No streaming exposure to MCP client | LOW -- team leads have no visibility into task progress | M | (future) |
| 6 | Session log correlation with task IDs | LOW -- debugging requires manual correlation | S | (future) |
| 7 | Agent Card schema enrichment | LOW -- sufficient for current internal use, future-proofing only | S | 4.5 |
| 8 | Code duplication in resolve_includes() | LOW -- maintenance burden, no functional impact | S | (refactor) |

### Recommended Phase 5 Scope

**Must-have (S1):**

1. Artifact tracking via response parsing + system prompt contract (Rank 1, effort S)
2. Graceful ACP cancel (Rank 3, effort M)
3. Client capabilities in initialize (Rank 4, effort S)

**Should-have (S2):**
4. input_required flow with resume_task tool (Rank 2, effort L)

**Nice-to-have (S3):**
5. Session log correlation (Rank 6, effort S)
6. Agent Card enrichment (Rank 7, effort S)
7. Streaming progress exposure (Rank 5, effort M)

---

## Appendix: Cross-Reference Matrix

| ADR | Decision | A2A Brief Finding | ACP Brief Finding | Implementation File | Status |
|-----|----------|------------------|------------------|-------------------|--------|
| Project Scope | Full Platform | Confirmed | Confirmed | mcp_dispatch.py, task_engine.py | OK |
| Project Scope | Tool-Agnostic API | MCP validated | MCP validated | mcp_dispatch.py, .mcp.json | OK |
| Protocol Selection | Three-Layer Stack | A2A states at L2, HTTP rejected at L3 | ACP correct at L3, misalignment noted | All files | OK (with notes) |
| Protocol Selection | MCP at Layer 1 | N/A | N/A | mcp_dispatch.py | OK |
| Protocol Selection | ACP at Layer 3 | N/A | Human-agent protocol misalignment | acp_dispatch.py | OK (compromise) |
| Protocol Selection | Reject A2A Transport | HTTP still required | N/A | N/A | Rejection valid |
| Architecture | Python MCP Server | N/A | N/A | mcp_dispatch.py | OK |
| Architecture | 4 MCP Tools | N/A | N/A | mcp_dispatch.py | OK (+get_locks) |
| Architecture | 4 Phases | N/A | N/A | mcp_dispatch.py, task_engine.py | All complete |
| Architecture | Preserve acp_dispatch | N/A | Compliance gaps noted | acp_dispatch.py | OK |
| Task Contract | 5-State Machine | 4 rejected states confirmed irrelevant | N/A | task_engine.py | OK |
| Task Contract | Structured Results | Artifacts richer in A2A | N/A | mcp_dispatch.py:433-442 | GAP: artifacts empty |
| Task Contract | Permission Modes | N/A | Prompt-only enforcement, YOLO approve | mcp_dispatch.py:82-108 | PARTIAL |
| Task Contract | Reject 9-State | Confirmed valid | N/A | N/A | Rejection valid |
| Workspace Safety | Advisory Locking | A2A artifact coordination noted | N/A | task_engine.py:143-276 | OK |
| Workspace Safety | Agent Cards as Resources | Schema gap vs A2A Agent Cards | N/A | mcp_dispatch.py:210-241 | OK (reduced schema) |
| Workspace Safety | list_agents Tool | N/A | N/A | mcp_dispatch.py:293-326 | OK |
| Workspace Safety | Reject Isolation | N/A | Shared access confirmed necessary | N/A | Rejection valid |
