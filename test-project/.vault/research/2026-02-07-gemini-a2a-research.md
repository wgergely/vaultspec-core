---
tags: ["#research", "#dispatch"]
related:
  - "[[2026-02-07-dispatch-project-scope]]"
  - "[[2026-02-07-dispatch-protocol-selection]]"
  - "[[2026-02-07-dispatch-architecture]]"
  - "[[2026-02-07-dispatch-task-contract]]"
  - "[[2026-02-07-dispatch-workspace-safety]]"
  - "[[2026-02-07-acp-protocol-compliance-brief]]"
  - "[[2026-02-07-a2a-protocol-compliance-brief]]"
  - "[[2026-02-07-dispatch-protocol-alignment-audit]]"
date: 2026-02-07
---

# Gemini A2A Alignment: ADR & Documentation Audit

**Author:** ADR Auditor (adr-auditor)
**Date:** 2026-02-07
**Scope:** Systematic extraction of all Gemini, A2A, ACP, and protocol alignment references from existing ADRs, research briefs, plans, execution records, and agent definitions. Identifies gaps, TODOs, and implications for Gemini A2A alignment.

---

## 1. Executive Summary

The existing documentation corpus (5 ADRs, 3 research briefs, 4 phase plans, 21 execution records, 9 agent definitions) contains extensive material on protocol selection and alignment. **Gemini is referenced as a first-class dispatch target** (both as MCP client and ACP sub-agent provider), but **no document addresses Gemini-specific A2A protocol support or Gemini's evolving protocol capabilities** beyond the `--experimental-acp` flag.

Key finding: The architecture assumes Gemini interacts with the dispatch system exclusively via MCP (Layer 1) or as a sub-agent via ACP (Layer 3). The possibility that Gemini CLI may natively support A2A -- or that Google's A2A protocol and Gemini CLI may converge -- is not addressed in any ADR or research document.

---

## 2. Document-by-Document Findings

### 2.1 ADR: Dispatch Project Scope (`2026-02-07-dispatch-project-scope.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Decision 2: "API Must Be Tool-Agnostic" | States: "Both Gemini CLI and Claude Code agents both need to act as team leads that dispatch sub-agents." | Gemini CLI is a first-class team lead. The MCP interface must work identically for Gemini and Claude. |
| Decision 2 rationale | "Research confirmed that MCP is the established standard... supported by Claude Code, **Gemini**, Cursor, VS Code" | Assumes Gemini CLI supports MCP client capabilities. No mention of whether Gemini may prefer A2A natively. |
| Decision 3: Python implementation | "All three protocol SDKs have official Python support; **A2A has no Rust SDK at all**." | A2A's Python SDK is acknowledged but only for the dispatch server side, not for Gemini integration. |

**Gap:** No analysis of whether Gemini CLI's MCP client implementation has limitations or differences compared to Claude Code's. The ADR treats them as equivalent.

---

### 2.2 ADR: Protocol Selection (`2026-02-07-dispatch-protocol-selection.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Three-Layer Stack (Decision 1) | "MCP at Layer 1... supported by Claude Code, **Gemini**, Cursor, and VS Code" | Gemini is expected to connect to the MCP dispatch server. |
| MCP at Layer 1 (Decision 2) | "Both Claude Code and **Gemini CLI** connect to the same MCP server via `.mcp.json`." | Both tools share the same dispatch interface. |
| ACP at Layer 3 (Decision 3) | "The existing `GeminiDispatchClient` (ACP client) and provider system work correctly at this layer." | Gemini is the primary ACP sub-agent provider (via `gemini --experimental-acp`). |
| Rejected: A2A for Transport (Decision 4) | "A2A requires HTTP transport. The stdio proposal (Issue #1074) is not merged into the spec. Running localhost HTTP servers per sub-agent introduces unnecessary infrastructure." | **A2A stdio was explicitly rejected.** This decision is static -- no mechanism to reassess if A2A adds stdio support. |
| A2A context | "A2A (Agent-to-Agent Protocol) by Google/Linux Foundation -- Agent-to-Agent protocol over HTTPS/SSE. 9-state task machine. Requires HTTP transport." | A2A is attributed to Google. No analysis of whether Gemini CLI will adopt A2A natively, given Google created A2A. |

**Gap:** The rejection of A2A transport does not consider that **Google created both A2A and Gemini CLI**. If Gemini CLI gains native A2A support, the dispatch system would need to support A2A as an alternative Layer 3 transport for Gemini sub-agents. This scenario is not addressed.

---

### 2.3 ADR: MCP Server Architecture (`2026-02-07-dispatch-architecture.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Decision 1 | ".mcp.json provides auto-discovered, git-committable server registration" | Both Gemini CLI and Claude Code discover the server via `.mcp.json`. |
| Decision 2: Exposed Tools | `dispatch_agent`, `get_task_status`, `list_agents`, `cancel_task` | These tools must work when called by Gemini CLI as MCP client. |
| Phase 3: Agent Cards as MCP Resources | "resources/list provides agent discovery" | Gemini CLI must support MCP `resources/list` for full Phase 3 functionality. |
| Decision 4 | "The `GeminiDispatchClient` ACP client logic is preserved and wrapped by the MCP server." | The ACP wrapper (with `--experimental-acp`) remains the sub-agent transport for Gemini. |

**Gap:** No verification that Gemini CLI supports all MCP features used by the server (resources, list_changed notifications, tool schemas with optional parameters). If Gemini's MCP client is less feature-complete than Claude Code's, some dispatch features may not work for Gemini team leads.

---

### 2.4 ADR: Task Result Contract (`2026-02-07-dispatch-task-contract.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Decision 1: MCP 5-state vs A2A 9-state | "submitted is unnecessary because MCP tool calls are synchronous at invocation" | This applies equally to both Gemini and Claude as MCP clients. |
| Decision 4: Rejected A2A 9-state | "If A2A transport is ever added (e.g., for remote agent dispatch), the 5-state model can be mapped to A2A's 9-state model at that boundary." | Acknowledges future A2A adoption as possible, but only for remote dispatch, not for Gemini specifically. |

**Gap:** The mapping from 5-state to A2A 9-state is described as a future concern. No concrete design exists for this mapping.

---

### 2.5 ADR: Workspace Safety (`2026-02-07-dispatch-workspace-safety.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Decision 2: Agent Cards as MCP Resources | "Generating separate JSON Agent Card files (A2A-style `/.well-known/agent.json`) would duplicate information already in frontmatter" | A2A-style Agent Cards were explicitly rejected in favor of MCP resources parsed from frontmatter. |
| A2A Agent Card reference | Resource schema documented as simpler than A2A Agent Cards: no capabilities flags, no security schemes, no I/O modes. | If Gemini expects A2A Agent Cards for agent discovery, our MCP resource approach would be incompatible. |

**Gap:** No analysis of whether Gemini CLI's agent discovery mechanism expects A2A Agent Cards or can work with our MCP resources.

---

### 2.6 Research: ACP Protocol Compliance Brief (`2026-02-07-acp-protocol-compliance-brief.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Section 6.2: GeminiProvider | "**Executable:** `gemini` CLI with `--experimental-acp` flag" | Gemini sub-agent transport uses an **experimental** flag. This could change or be removed. |
| Section 6.2: Model mapping | `gemini-3-pro-preview` (HIGH), `gemini-3-flash-preview` (MEDIUM), `gemini-2.5-pro` (LOW), `gemini-2.5-flash` (LOW) | Model mapping is hardcoded. No dynamic discovery of available Gemini models. |
| Section 6.2: System prompt delivery | "Written to a temp file, path stored in `GEMINI_SYSTEM_MD` environment variable. The Gemini CLI reads this at startup." | Gemini-specific system prompt mechanism (env var + temp file). Different from Claude's approach. |
| Section 6.2: Include resolution | "resolve_includes() recursively resolves @path/to/file.md directives... Reads `.gemini/GEMINI.md`" | Gemini provider reads `.gemini/GEMINI.md` for rules. Claude reads `.claude/CLAUDE.md`. Both resolve `@` includes. |
| Section 6.4: Provider selection | "Starts with 'gemini' -> GeminiProvider; Default/unknown -> GeminiProvider" | Gemini is the **default fallback** provider. Unknown models go to Gemini. |
| Section 6.4: Fallback chain | "Fallback is one-directional: Gemini -> Claude only. Claude -> Gemini is not implemented." | If Gemini fails, fallback to Claude. Not bidirectional. |
| Section 6.5: Gaps | "No Antigravity provider... No capability advertisement... Code duplication in resolve_includes()" | Gemini provider has no capability negotiation with the Gemini CLI ACP adapter. |
| Section 2.2: YOLO auto-approve | Auto-approves all permissions | Both Gemini and Claude sub-agents get auto-approved. No Gemini-specific permission handling. |
| Section 3.2: interactive=False in MCP | "MCP uses stdout for JSON-RPC messages. The ACP client's response text goes to stdout by default, which would corrupt the MCP transport." | This is a transport-level constraint that affects Gemini sub-agents equally. |
| Section 4.3: Missing client capabilities | "initialize() sends no capabilities... The agent doesn't know our filesystem and terminal capabilities." | The Gemini CLI ACP adapter may gate features based on client capabilities we don't declare. |
| Section 7: Architecturally Misaligned | "**Human-agent protocol for agent-agent use:** ACP is designed for editor-to-agent communication with a human in the loop. We use it for headless agent-to-agent delegation, which is **A2A's domain**." | The fundamental misalignment: we use ACP (human-agent) where A2A (agent-agent) would be semantically correct. Gemini's relationship to both protocols makes this particularly relevant. |

**Gaps identified:**

1. `--experimental-acp` flag instability: no contingency plan if Gemini removes or changes this flag.
2. No dynamic model discovery for Gemini models.
3. Missing client capabilities in ACP initialize may affect Gemini's behavior.
4. The human-agent vs agent-agent protocol misalignment is most acute for Gemini, since Google created A2A specifically for the agent-agent boundary.

---

### 2.7 Research: A2A Protocol Compliance Brief (`2026-02-07-a2a-protocol-compliance-brief.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Section 1.0 | "A2A Protocol is an open standard created by **Google** (April 2025), donated to the Linux Foundation (June 2025). Version 0.3.x with 150+ supporting organizations." | A2A is Google's protocol. Gemini CLI is Google's AI tool. Convergence is highly likely. |
| Section 1.1: Agent Cards | "Agent Cards are self-describing manifests served at `/.well-known/agent-card.json`" | A2A's discovery mechanism is HTTP-based. Incompatible with our local MCP resource approach. |
| Section 2.1: State machine comparison | Our 5-state vs A2A 9-state mapped in detail | The mapping is documented but no implementation exists for protocol translation. |
| Section 3.1: input_required (HIGH PRIORITY) | "Neither mcp_dispatch.py nor acp_dispatch.py ever transitions a task to INPUT_REQUIRED" | Interactive dispatch is blocked for both Gemini and Claude sub-agents. |
| Section 3.4: Multi-part messages (MEDIUM) | "artifacts is always `[]`" | Both Gemini and Claude sub-agent results lack structured artifact reporting. |
| Section 3.5: context_id (MEDIUM) | "DispatchTask has no context_id field" | No workflow grouping for either provider. |
| Section 5.2: Gap analysis | Our resources lack: skill-level routing, security negotiation, interface multiplexity, extended Agent Card, cryptographic signing | All of these are A2A Agent Card features that Gemini may eventually expect. |
| Section 5.3: Convergence path | 4-step plan to evolve MCP resources toward A2A Agent Cards | Near-term: enrich skill metadata, add capability flags. Long-term: security schemes. |
| Section 7: Recommendation | "Keep ACP for transport and layer A2A semantics on top" | This is the accepted hybrid approach. The brief explicitly recommends A2A data models without A2A transport. |

**Key Gemini-specific implication:** The A2A brief correctly identifies that Google created A2A, but does not analyze what this means for Gemini CLI's future protocol support. If Gemini CLI adopts A2A natively, the dispatch system's Layer 3 would need an A2A transport option alongside ACP.

---

### 2.8 Research: Dispatch Protocol Alignment Audit (`2026-02-07-dispatch-protocol-alignment-audit.md`)

| Reference | Finding | Implication |
|-----------|---------|-------------|
| Gap 1: Artifacts always empty | "CRITICAL... blocks task chaining, forces manual file discovery" | Affects both providers equally. |
| Gap 2: input_required never triggered | "MODERATE... sub-agents cannot request clarification" | Affects both providers. |
| Gap 3: No graceful ACP cancel | "cancel_task does NOT send session/cancel to the ACP agent" | Affects Gemini sub-agents specifically (ACP transport). |
| Gap 4: Missing client capabilities | "LOW... agents may not attempt all supported operations" | Specifically relevant to Gemini CLI ACP adapter behavior. |
| Phase 5 Recommendations | 8-item prioritized gap list | No Gemini-specific Phase 5 items. All gaps are provider-agnostic. |
| Rejection validity: A2A transport | "REJECTION REMAINS VALID... If A2A adds stdio transport in the future, this should be reassessed." | Conditional reassessment trigger identified but no monitoring mechanism. |

**Gap:** The alignment audit treats all gaps as provider-agnostic. No analysis of whether gaps affect Gemini differently from Claude.

---

### 2.9 Plan Documents (Phase 1-4)

| Document | Gemini Reference | Finding |
|----------|-----------------|---------|
| Phase 1 Plan | None explicit | MCP server creation. Implicitly serves both Gemini and Claude team leads via `.mcp.json`. |
| Phase 2 Plan | None explicit | Async tasks. Provider-agnostic. |
| Phase 3 Plan | Step 3 example: `"default_model": "gemini-3-pro-preview"` | Agent resource schema uses Gemini model as example, confirming Gemini as primary provider. |
| Phase 4 Plan | Step 1: "Research... whether ACP supports permission constraints on the protocol level" | ACP research applies to Gemini sub-agent transport. Concluded: no protocol-level permissions in ACP. |

**Gap:** No plan document addresses Gemini-specific protocol testing or validation. All plans treat the two providers symmetrically.

---

### 2.10 Execution Records and Summaries

| Document | Finding |
|----------|---------|
| Phase 3 Summary | "Audited all 9 agent files... Added mode and tools" -- no Gemini-specific notes. |
| Phase 4 Summary | "ACP has no protocol-level permission constraints" -- applies to Gemini ACP transport. |
| Audit Review | Reviews code quality of Phase 4 changes. No Gemini-specific findings. Provider behavior not tested. |

**Gap:** No execution record tests Gemini CLI behavior specifically. All testing is against mocked `run_dispatch()`.

---

### 2.11 Agent Definitions (`.rules/agents/*.md`)

| Agent | Gemini Reference | Finding |
|-------|-----------------|---------|
| All 9 agents | None | No agent definition references Gemini, A2A, ACP, or any protocol. Agents are provider-agnostic. |
| Frontmatter schema | `tier`, `mode`, `tools`, `description` | No provider-specific fields (e.g., no `preferred_provider` or `gemini_model` field). |

**Finding:** Agent definitions are correctly provider-agnostic. The provider is determined at dispatch time by the model parameter, not by the agent definition.

---

## 3. Gemini-Specific Protocol References Summary

### 3.1 Accepted Decisions Involving Gemini

| Decision | Document | Status |
|----------|----------|--------|
| Gemini CLI as MCP client (team lead) | Project Scope ADR, Protocol Selection ADR | Accepted, implemented |
| Gemini CLI as ACP sub-agent (via `--experimental-acp`) | Protocol Selection ADR, ACP Brief | Accepted, implemented |
| `GeminiProvider` with model mapping | ACP Brief Section 6.2 | Implemented |
| Gemini -> Claude fallback chain | ACP Brief Section 6.4 | Implemented |
| `GEMINI_SYSTEM_MD` env var for system prompt | ACP Brief Section 6.2 | Implemented |
| `.gemini/GEMINI.md` for rules loading | ACP Brief Section 6.2 | Implemented |
| Gemini as default fallback provider | ACP Brief Section 6.4 | Implemented |

### 3.2 Rejected Decisions Relevant to Gemini

| Decision | Document | Rationale | Reassessment Trigger |
|----------|----------|-----------|---------------------|
| A2A for transport (Layer 3) | Protocol Selection ADR | HTTP transport required, impractical for local subprocess | A2A adds stdio transport (Issue #1074) |
| A2A 9-state machine | Task Contract ADR | 4 states irrelevant for local dispatch | Remote dispatch scenarios emerge |
| A2A Agent Cards | Workspace Safety ADR | Duplicates frontmatter, requires HTTP serving | Gemini CLI requires A2A Agent Cards for discovery |

### 3.3 `--experimental-acp` Flag References

| Document | Reference | Context |
|----------|-----------|---------|
| ACP Brief 6.2 | "Executable: `gemini` CLI with `--experimental-acp` flag" | How Gemini sub-agents are spawned |
| ACP Brief 6.2 | "gemini.py:166-167" | Exact code location where flag is passed |

**Risk:** The `--experimental-acp` flag is by definition unstable. No contingency plan exists for when Gemini CLI:

- Removes the flag (moves ACP to stable or removes ACP support)
- Changes the flag name
- Adds alternative flags (e.g., `--a2a`)
- Changes the ACP protocol implementation behind the flag

---

## 4. Identified Gaps and TODOs for Gemini A2A Alignment

### Gap 1: No Analysis of Google's A2A + Gemini Convergence Path (HIGH)

**Description:** Google created both A2A (donated to Linux Foundation) and Gemini CLI. No ADR or research document analyzes the likelihood, timeline, or implications of Gemini CLI gaining native A2A support.

**Impact:** If Gemini CLI adds A2A server capabilities, our dispatch system could dispatch to Gemini sub-agents via A2A instead of ACP, potentially with richer features (artifact exchange, streaming, proper agent-agent semantics).

**Recommendation:** Research Gemini CLI's protocol roadmap. Check if `--experimental-a2a` or similar flags exist or are planned.

### Gap 2: No Gemini-Specific MCP Client Capability Testing (HIGH)

**Description:** The dispatch server exposes MCP resources (Phase 3), list_changed notifications, and tool schemas with optional parameters. No testing verifies that Gemini CLI's MCP client implementation supports all of these features.

**Impact:** Gemini CLI may not support MCP resources, or may handle tool schemas differently from Claude Code. Phase 3 features may be Gemini-inaccessible.

**Recommendation:** Test the dispatch server with Gemini CLI as the MCP client and document any behavioral differences.

### Gap 3: `--experimental-acp` Flag Instability (MEDIUM)

**Description:** The Gemini sub-agent transport depends on an experimental flag. No fallback or version pinning exists.

**Impact:** A Gemini CLI update could break all Gemini sub-agent dispatch without warning.

**Recommendation:** Pin Gemini CLI version in development environment, or implement version detection and flag adaptation.

### Gap 4: No Bidirectional Fallback (Claude -> Gemini) (LOW)

**Description:** ACP Brief Section 6.4 documents that fallback is Gemini -> Claude only. Claude -> Gemini is not implemented.

**Impact:** If Claude sub-agents fail, there is no fallback to Gemini. Given Gemini is the default provider, this asymmetry may cause unexpected failures.

**Recommendation:** Implement bidirectional fallback or document the intentional asymmetry.

### Gap 5: Missing Client Capabilities Affects Gemini Behavior (LOW)

**Description:** ACP Brief Section 6.5 identifies that `initialize()` sends no client capabilities. The Gemini CLI ACP adapter may not know we support filesystem and terminal operations.

**Impact:** Gemini sub-agents may not utilize available operations (file read/write, terminal) because the adapter does not know they are supported.

**Recommendation:** Add client capability declaration to the ACP initialize call. Test impact on Gemini CLI behavior.

### Gap 6: No A2A Transport Reassessment Mechanism (LOW)

**Description:** The Protocol Selection ADR states A2A transport rejection "should be reassessed" if A2A adds stdio support. No mechanism exists to trigger this reassessment.

**Impact:** A2A could add stdio transport (via Issue #1074 or equivalent) and the team would not be notified.

**Recommendation:** Add a periodic protocol landscape review (quarterly) or monitor A2A GitHub for stdio-related changes.

---

## 5. Differences Between Claude and Gemini Dispatch Behavior

Based on the ACP Brief Section 6, the following behavioral differences exist:

| Dimension | Gemini | Claude |
|-----------|--------|--------|
| **ACP executable** | `gemini --experimental-acp` | `npx -y @zed-industries/claude-code-acp` (or `npx.cmd` on Windows) |
| **System prompt delivery** | Temp file via `GEMINI_SYSTEM_MD` env var | `session_meta["systemPrompt"]` + prepended to initial prompt |
| **Rules source** | `.gemini/GEMINI.md` | `.claude/CLAUDE.md` |
| **Include resolution** | Duplicated code in `gemini.py` | Duplicated code in `claude.py` |
| **Cleanup** | Temp file deleted after dispatch | No cleanup needed (no temp files) |
| **Provider fallback** | Falls back to Claude on failure | No fallback (terminal) |
| **Default provider** | Yes (unknown models default to Gemini) | No |
| **Session metadata** | Standard `NewSessionRequest` fields | Non-standard `systemPrompt` in `session_meta` kwargs |

---

## 6. Cross-Reference: What Each Document Says About A2A

| Topic | Protocol Selection ADR | Task Contract ADR | Workspace Safety ADR | ACP Brief | A2A Brief | Alignment Audit |
|-------|----------------------|-------------------|---------------------|-----------|-----------|-----------------|
| A2A rejected for transport | YES (Decision 4) | -- | -- | -- | Confirms (Section 7) | Validates rejection |
| A2A 9-state rejected | -- | YES (Decision 4) | -- | -- | Maps 5-to-9 (Section 2) | Validates rejection |
| A2A Agent Cards rejected | -- | -- | YES (Decision 2) | -- | Gap analysis (Section 5) | Notes reduced schema |
| A2A semantics adopted internally | YES (Layer 2) | YES (state machine inspired) | -- | -- | Recommends hybrid (Section 7) | Confirms alignment |
| A2A stdio proposal | YES (Issue #1074) | -- | -- | -- | -- | Notes reassessment trigger |
| Google created A2A | YES | -- | -- | -- | YES (Section 1) | -- |
| Gemini + A2A convergence | -- | -- | -- | -- | -- | -- |

**Key observation:** The "Gemini + A2A convergence" row is empty across all documents. This is the primary documentation gap.

---

## 7. Conclusion

The existing documentation corpus provides a thorough protocol analysis with clear decisions about MCP, ACP, and A2A boundaries. However, it treats Gemini as a generic provider and does not analyze the strategic implications of Google's dual ownership of A2A and Gemini CLI. The highest-priority gap is the missing analysis of whether Gemini CLI will adopt A2A natively, which could fundamentally change the dispatch system's Layer 3 architecture for Gemini sub-agents.

### Priority Actions

1. **Research Gemini CLI's protocol roadmap** -- Does `--experimental-a2a` exist? Is A2A support planned?
2. **Test MCP client compatibility** -- Validate that Gemini CLI supports all MCP features used by the dispatch server.
3. **Document `--experimental-acp` contingency** -- Plan for flag removal/change.
4. **Add Gemini-specific section to Phase 5 planning** -- Currently all Phase 5 recommendations are provider-agnostic.

---

## Sources

- ADRs: `.docs/adr/2026-02-07-dispatch-{project-scope,protocol-selection,architecture,task-contract,workspace-safety}.md`
- Research Briefs: `.docs/research/2026-02-07-{acp,a2a}-protocol-compliance-brief.md`, `.docs/research/2026-02-07-dispatch-protocol-alignment-audit.md`
- Plans: `.docs/plan/2026-02-07-dispatch-phase{1,2,3,4}-plan.md`
- Execution: `.docs/exec/2026-02-07-dispatch/` (21 step records, summaries, audit review)
- Agents: `.rules/agents/*.md` (9 agent definitions)
