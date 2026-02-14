---
tags:
  - "#adr"
  - "#dispatch"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-protocol-selection]]"
  - "[[2026-02-07-dispatch-architecture]]"
  - "[[2026-02-07-dispatch-task-contract]]"
  - "[[2026-02-07-a2a-transport-feasibility]]"
---

# dispatch adr: A2A Convergence Monitoring | (**status:** accepted)

## Problem Statement

Google owns both A2A (Agent-to-Agent Protocol) and Gemini CLI. Evidence shows active convergence between these projects, but our dispatch architecture (ADR: [[2026-02-07-dispatch-protocol-selection]]) rejected A2A transport (Decision 4) based on its HTTP-only requirement. No mechanism exists to detect when this rejection should be revisited, nor is there an architectural sketch for how an A2A transport provider would integrate if the trigger conditions are met.

Additionally, a naming collision creates ongoing confusion: Zed's "ACP" (Agent Client Protocol) and IBM's "ACP" (Agent Communication Protocol, now merged into A2A) are completely different protocols sharing an acronym. Our codebase uses "ACP" exclusively to mean Zed's Agent Client Protocol, but external documentation and community discussions frequently conflate the two.

## Considerations

### Evidence for Convergence

**Code-level signals (Gemini CLI):**

- A2A client implementation exists in `packages/core/src/a2a/types.ts` and `packages/core/src/tools/a2a-tool.ts`
- PR #3079 (A2A Client Support) was closed as "not prioritized" but the code remains in the repository
- v0.28-preview adds pluggable A2A auth infrastructure (`A2AAuthConfig` types) and admin settings
- `@google/gemini-cli-a2a-server` is published as a separate npm package for A2A server capability
- Issue #10482 proposed embedding the A2A server directly into Gemini CLI (closed as stale by automation, not by explicit rejection)

**Governance signals:**

- Google donated A2A to the Linux Foundation (June 2025) with 100+ supporting organizations
- IBM's Agent Communication Protocol merged into A2A (September 2025), consolidating two competing agent-to-agent standards
- A Technical Steering Committee governs the specification under open-source governance
- RFC #7822 proposes standardizing all Gemini CLI integrations on A2A

**Specification signals:**

- A2A v0.2 added gRPC support and stateless interactions
- v0.3 roadmap includes signed Agent Cards and agent registry patterns
- Issue #1074 proposes stdio transport (labeled "TSC Review"), modeled after the Language Server Protocol message format
- Despite community interest, stdio transport is NOT on the official v0.3 roadmap

### The Naming Collision

| Acronym | Full Name | Creator | Transport | Status |
|---|---|---|---|---|
| ACP | Agent Client Protocol | Zed Industries | JSON-RPC/stdio | Active, our Layer 3 |
| ACP | Agent Communication Protocol | IBM | HTTP | Merged into A2A (Sept 2025) |
| A2A | Agent-to-Agent Protocol | Google/Linux Foundation | HTTP/SSE, gRPC | Active, spec v0.2+ |

When our code or ADRs reference "ACP," it means Zed's Agent Client Protocol. The IBM usage of "ACP" is obsolete -- it is now part of A2A. External references to "ACP" should be disambiguated on encounter.

## Constraints

- A2A requires HTTP/HTTPS transport (mandatory) with optional gRPC. There is no stdio binding.
- Our dispatch architecture uses subprocess-based agents communicating over stdio via ACP.
- Running an HTTP server per sub-agent introduces infrastructure complexity inappropriate for local development dispatch.
- The `AgentProvider` ABC expects `prepare_process()` to return a `ProcessSpec` (executable, args, env) for subprocess spawning -- fundamentally a stdio model.
- A2A's security model (OAuth 2.0, mTLS, API keys) is designed for untrusted/semi-trusted network boundaries, not same-machine subprocess communication.

## Implementation

### Trigger Conditions for Reassessment

The A2A transport rejection (Decision 4) should be reassessed if ANY of these conditions are met:

1. **Gemini CLI native A2A flag:** Gemini CLI ships `--a2a` or `--experimental-a2a` for local agent dispatch, bridging A2A semantics over a local transport (stdio, Unix socket, or localhost HTTP with automatic lifecycle management).
2. **A2A stdio transport merged:** Issue #1074 (or equivalent) is merged into the A2A specification and supported by at least one official SDK (Python or JavaScript).
3. **A2A reaches 1.0:** The specification is declared stable under Linux Foundation governance, signaling production readiness and long-term commitment.
4. **Gemini sub-agent registry adopts A2A semantics:** The v0.27+ sub-agent/agent-skills system begins using A2A task states or Agent Cards for internal coordination.

### A2AProvider Design Sketch

If trigger conditions are met, the provider system would gain an `A2AProvider` alongside the existing `GeminiProvider` and `ClaudeProvider`:

```
AgentProvider (ABC)
  +-- GeminiProvider    (ACP/stdio transport)
  +-- ClaudeProvider    (ACP/stdio transport)
  +-- A2AProvider       (A2A/HTTP transport)  <-- future
```

**What A2AProvider would implement from AgentProvider ABC:**

| Method | Current Interface | A2A Adaptation |
|---|---|---|
| `name` | Returns provider name | Returns `"a2a"` |
| `supported_models` | List of model strings | A2A-capable models (may overlap with Gemini models) |
| `get_model_capability()` | Model -> CapabilityLevel | Same mapping |
| `get_best_model_for_capability()` | Level -> model string | Same logic |
| `prepare_process()` | Returns `ProcessSpec` | **Key tension point** -- see below |

**The `prepare_process()` tension:**

`ProcessSpec` contains `executable`, `args`, `env`, and `cleanup_paths` -- all oriented toward subprocess spawning. An A2A provider would need either:

- **Option A:** Return a `ProcessSpec` that launches an A2A agent as a subprocess (e.g., `node a2a-server.js --port 0`), then communicate via HTTP to localhost. The `ProcessSpec.session_meta` could carry the negotiated port.
- **Option B:** Introduce an `A2AConnectionSpec` alongside `ProcessSpec` for HTTP-based connections (agent URL, auth credentials). This would require modifying the dispatch loop in `acp_dispatch.py` to handle both connection models.

Option A preserves the existing interface but adds complexity to the dispatch loop. Option B is cleaner architecturally but requires broader refactoring.

**Task state mapping (our 5-state to A2A 9-state):**

| Our State (MCP-aligned) | A2A State | Mapping Notes |
|---|---|---|
| (initial) | `submitted` | We skip `submitted`; tasks start as `working` |
| `working` | `working` | Direct 1:1 mapping |
| `input_required` | `input_required` | Direct 1:1 mapping |
| `completed` | `completed` | Direct 1:1 mapping |
| `failed` | `failed` | Direct 1:1 mapping |
| `cancelled` | `canceled` | Spelling difference only |
| -- | `rejected` | Map to `failed` with rejection metadata |
| -- | `auth_required` | Map to `failed` with auth error metadata |
| -- | `unknown` | Map to `failed` with unknown error metadata |

## Rationale

Monitoring with explicit triggers is chosen over both premature adoption and willful ignorance:

- **Not adopting now:** A2A's HTTP requirement creates real architectural friction with our subprocess model. The stdio transport proposal (Issue #1074) is under TSC review but not on the v0.3 roadmap. Premature adoption would add infrastructure complexity with no current benefit.
- **Not ignoring:** Google's dual ownership of A2A and Gemini CLI, the Linux Foundation governance with 100+ organizations, and code-level evidence of A2A infrastructure in Gemini CLI make convergence a reasonable medium-term scenario. Ignoring it risks a disruptive architectural retrofit.
- **Monitoring with triggers:** Explicit trigger conditions transform an ambiguous "maybe someday" into testable criteria that can be evaluated at each Gemini CLI release. The `AgentProvider` abstraction already supports adding new providers without modifying the core dispatch loop.

## Consequences

**Benefits:**

- The architecture is prepared for A2A adoption without premature commitment.
- The `AgentProvider` ABC demonstrates extensibility -- new transport providers can be added at Layer 3 without touching Layers 1 or 2.
- Explicit triggers prevent both premature adoption and missed adoption windows.
- The naming collision is documented, reducing confusion in future ADR discussions.

**Difficulties:**

- Monitoring requires discipline: someone must check trigger conditions quarterly or on Gemini CLI releases.
- If A2A adds stdio transport, the `prepare_process()` interface may still require adaptation for A2A's richer session model (Agent Cards, capabilities negotiation).
- If Gemini CLI bridges A2A over a proprietary local transport (not stdio), we may need to evaluate a non-standard integration path.
- The design sketch is speculative -- actual implementation details will depend on which trigger fires and what the A2A/Gemini CLI landscape looks like at that time.
