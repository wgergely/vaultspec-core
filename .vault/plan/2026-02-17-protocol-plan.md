---
tags: ["#plan", "#protocol"]
date: 2026-02-17
related:
  - "[[2026-02-15-a2a-adr]]"
  - "[[2026-02-15-cross-agent-adr]]"
  - "[[2026-02-15-subagent-adr]]"
  - "[[2026-02-15-provider-feature-parity-adr]]"
  - "[[2026-02-07-a2a-research]]"
  - "[[2026-02-07-acp-research]]"
  - "[[2026-02-07-protocol-architecture-research]]"
  - "[[2026-02-07-protocol-review-research]]"
---

# Protocol Stack Evolution Plan

Consolidation plan for the vaultspec protocol layer covering MCP (agent-to-tool), ACP (orchestrator-to-agent), and A2A (agent-to-agent).

## Proposed Changes

Evolve the 3-layer protocol stack (MCP v1.26, ACP v0.8, A2A v0.3) based on research and ADR decisions. Key areas: provider parity between Claude and Gemini, cross-agent bidirectional communication via A2A, and subagent dispatch hardening.

## Tasks

- Harden ACP client for production reliability
- Implement A2A executor integration for cross-agent tasks
- Achieve provider feature parity (Claude/Gemini)
- Consolidate subagent dispatch with protocol-aware routing

## Verification

All protocol integration tests pass. A2A server starts and responds to agent card requests. ACP handshake succeeds with both Claude and Gemini providers.
