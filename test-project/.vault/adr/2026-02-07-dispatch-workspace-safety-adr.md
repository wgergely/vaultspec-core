---
tags:
  - "#adr"
  - "#uncategorized"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-project-scope.md]]"
  - "[[2026-02-07-dispatch-protocol-selection.md]]"
  - "[[2026-02-07-dispatch-architecture.md]]"
  - "[[2026-02-07-dispatch-task-contract.md]]"
---
# Dispatch Framework: Workspace Safety and Agent Discovery

## Context

When multiple sub-agents operate concurrently on a shared workspace, two risks emerge:

1. **Write Conflicts:** Two agents editing the same file simultaneously, leading to data loss or corruption.
2. **Discovery Opacity:** Team leads must know agent names and capabilities a priori, with no runtime discovery mechanism.

The current system has no workspace coordination (agents freely read and write anywhere) and agent discovery is hard-coded (the team lead must know the exact filename in `.rules/agents/`).

## Decisions

### 1. Shared Workspace with Advisory Locking

**Decision:** Sub-agents share the workspace filesystem. Concurrent access is coordinated via advisory file locks managed by the task engine.

**Rationale:**

- Full workspace isolation (per-agent directories, copy-on-write) is impractical for the project's workflow where agents read shared source code and write to shared `.docs/` directories.
- Advisory locking provides sufficient coordination for the current concurrency model (sequential or lightly parallel dispatch).
- The task engine tracks which files each active task is writing to and warns on conflicts.

**Locking Mechanism:**

- When a sub-agent declares intent to write to a path (via task metadata or artifact declaration), the task engine records the path as locked.
- If a second task attempts to write to a locked path, the task engine logs a warning and may block the dispatch (in Phase 4).
- Locks are released when the task transitions to a terminal state (`completed`, `failed`, `cancelled`).
- Lock state is in-memory within the MCP server process. No filesystem lock files are created.

**Implications:**

- Locking is cooperative, not enforced at the OS level. Sub-agents with full filesystem access can still write to locked paths.
- The primary purpose is conflict detection and coordination, not prevention.
- This is implemented in Phase 4 of the architecture rollout.

### 2. Agent Cards as MCP Resources from Frontmatter

**Decision:** Agent definitions are exposed as MCP resources, dynamically parsed from `.rules/agents/*.md` frontmatter at server startup and on file change.

**Rationale:**

- The existing `.rules/agents/*.md` files already contain structured frontmatter with agent metadata (tier, model, description, tools).
- MCP resources provide a standard discovery mechanism via `resources/list` and `resources/read`.
- Generating separate JSON Agent Card files (A2A-style `/.well-known/agent.json`) would duplicate information already in frontmatter and require an additional sync step in `cli.py`.
- Parsing frontmatter at runtime keeps `.rules/agents/*.md` as the single source of truth.

**Resource URI Scheme:**

```
agents://adr-researcher       -> Returns parsed agent metadata
agents://complex-executor      -> Returns parsed agent metadata
agents://docs-curator          -> Returns parsed agent metadata
```

**Resource Content (parsed from frontmatter):**

```json
{
  "name": "adr-researcher",
  "description": "Conducts research and formalizes architectural decisions into ADRs",
  "tier": "HIGH",
  "default_model": "gemini-3-pro-preview",
  "default_mode": "read-only",
  "tools": ["Glob", "Grep", "Read", "WebFetch", "WebSearch"]
}
```

**Rationale for Runtime Parsing over Generated Files:**

- Frontmatter is already the canonical source for agent definitions.
- Runtime parsing avoids a sync step that could become stale.
- MCP `list_changed` notifications can be triggered on file system changes to `.rules/agents/`.

**Implications:**

- The MCP server needs a frontmatter parser (reusing `parse_frontmatter()` from `acp_dispatch.py`).
- Agent metadata schema must be standardized across all `.rules/agents/*.md` files.
- This is implemented in Phase 3 of the architecture rollout.

### 3. Team Lead Discovery via `list_agents` Tool

**Decision:** In addition to MCP resources (Phase 3), the server exposes a `list_agents` tool from Phase 1 that returns a summary of available agents.

**Rationale:**

- MCP resources (Phase 3) provide the standard discovery mechanism, but team leads need agent discovery from Phase 1.
- A `list_agents` tool is simpler to implement and use than resource URIs for basic "what agents are available?" queries.
- Both mechanisms coexist: `list_agents` for quick queries, MCP resources for detailed metadata.

**`list_agents` Response:**

```json
{
  "agents": [
    {
      "name": "adr-researcher",
      "tier": "HIGH",
      "description": "Conducts research and formalizes architectural decisions"
    },
    {
      "name": "simple-executor",
      "tier": "LOW",
      "description": "Straightforward edits and low-risk logic changes"
    }
  ]
}
```

### 4. Rejected Alternative: Full Workspace Isolation

**Decision:** Per-agent workspace isolation (separate directories, copy-on-write filesystems, or container-based sandboxing) is not adopted.

**Rationale:**

- The project's sub-agent workflows require reading shared source code (for reference auditing, code review, plan execution) and writing to shared directories (`.docs/`, `crates/`).
- Isolation would require a merge/reconciliation step that adds complexity without proportionate benefit for the current team sizes (1-4 concurrent agents).
- If the system scales to significantly higher concurrency, isolation can be revisited as an evolution of the advisory locking system.

## Status

Accepted

## Consequences

**Benefits:**

- Advisory locking provides conflict detection without the complexity of true isolation.
- MCP resources as the discovery mechanism uses a standard protocol rather than inventing a custom discovery layer.
- Frontmatter remains the single source of truth for agent definitions, eliminating sync drift between definition and discovery.
- `list_agents` provides immediate value from Phase 1 without waiting for the full resource system.

**Drawbacks:**

- Advisory locking is cooperative and cannot prevent determined or buggy agents from creating write conflicts.
- Runtime frontmatter parsing adds startup latency and requires robust error handling for malformed files.
- The MCP resource system (Phase 3) duplicates some functionality of the `list_agents` tool (Phase 1), though they serve different levels of detail.
- In-memory lock state is lost on server restart, which could leave stale lock perceptions if not properly handled.

---

## Addendum: Protocol-Level Write Enforcement (2026-02-07)

**Context:** The advisory locking system (Decision 1) provides conflict *detection* but not *prevention*. The `write_text_file()` ACP callback in `acp_dispatch.py` originally only enforced workspace boundaries (writes must be within the project root). When `mode="read-only"` was set via `dispatch_agent`, the constraint was enforced solely through prompt-level instructions -- a non-compliant agent could still write anywhere in the workspace.

**Update:** Protocol-level write enforcement has been added to the `write_text_file()` ACP callback. When the dispatch mode is `"read-only"`:

- Writes within `.docs/` are **permitted** (documentation is the expected output).
- Writes outside `.docs/` are **rejected** with an error response at the protocol level.
- This supplements the prompt-level instruction and advisory lock warning with actual protocol enforcement.

This change closes gap H2 identified in the Gemini A2A Alignment Report (`.docs/research/2026-02-07-gemini-a2a-alignment-report.md`, Section 5.1). The advisory locking system remains in place for write-write conflict detection between concurrent agents operating in `read-write` mode.
