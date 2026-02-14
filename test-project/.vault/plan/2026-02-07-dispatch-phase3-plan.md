---
feature: dispatch
phase: phase3
date: 2026-02-07
related:
  - [[2026-02-07-dispatch-architecture.md]]
  - [[2026-02-07-dispatch-workspace-safety.md]]
  - [[2026-02-07-dispatch-protocol-selection.md]]
  - [[2026-02-07-dispatch-phase2-plan.md]]
---

# Phase 3: Agent Cards as MCP Resources

## Goal

Expose agent definitions as MCP resources, dynamically parsed from `.rules/agents/*.md` frontmatter at runtime. Team leads can discover agents via `resources/list` and read detailed agent metadata via `resources/read`. The server emits `list_changed` notifications when agent files are modified.

## Prerequisites

- Phase 2 complete: async dispatch with task engine
- `.rules/agents/*.md` files with YAML frontmatter (tier, description, model, tools)
- Existing `list_agents` tool (Phase 1) provides basic discovery — resources provide richer metadata

## Steps

### Step 1: Research FastMCP resource API

**Complexity:** LOW
**Output:** Understanding of FastMCP resource registration, URI schemes, dynamic resources

Research:

- How FastMCP registers resources via `@mcp.resource()` decorator
- Dynamic resource templates vs static resources
- `resources/list` and `resources/read` protocol methods
- `list_changed` notification mechanism
- URI scheme conventions for custom resources

Consult MCP SDK source. Do NOT write code.

### Step 2: Standardize agent frontmatter schema

**Complexity:** LOW
**Files:**

- `.rules/agents/*.md` (audit and update frontmatter)

Audit all agent files to ensure consistent frontmatter fields:

- `tier`: LOW | MEDIUM | HIGH (required)
- `description`: One-line agent description (required)
- `model`: Default model name (optional)
- `mode`: Default permission mode — read-write | read-only (optional)
- `tools`: Comma-separated list of available tools (optional)

Do NOT change agent persona content — only standardize frontmatter keys.

### Step 3: Implement agent resource provider

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Implement MCP resources for agent discovery:

- Resource URI template: `agents://{name}`
- `resources/list` returns all agents from `.rules/agents/*.md`
- `resources/read` returns parsed frontmatter as structured JSON
- Resource metadata includes: name, description, tier, default_model, default_mode, tools, mimeType

Resource content schema (per ADR dispatch-workspace-safety Decision 2):

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

### Step 4: Implement file-watching for list_changed notifications

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Detect when `.rules/agents/*.md` files are added, removed, or modified:

- Use filesystem polling or `watchdog` library
- Emit MCP `notifications/resources/list_changed` when agent files change
- Cache parsed frontmatter to avoid re-reading on every `resources/read`
- Invalidate cache on file change

If `watchdog` adds too much dependency weight, simple polling with mtime checks is acceptable for Phase 3.

### Step 5: Write resource tests

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/tests/test_mcp_dispatch.py` (extend)

Test coverage:

- `resources/list` returns all agents
- `resources/read` returns correct metadata for each agent
- Unknown agent URI returns error
- Malformed frontmatter handled gracefully
- Resource content matches expected schema
- Cache invalidation on file change (if caching implemented)

### Step 6: Update list_agents to reference resources

**Complexity:** LOW
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Update `list_agents` tool response to include a hint that richer metadata is available via MCP resources:

```json
{
  "agents": [...],
  "hint": "Use resources/read with URI 'agents://{name}' for detailed agent metadata"
}
```

This bridges Phase 1 discovery (tool) with Phase 3 discovery (resources).

## ADR Compliance Checklist

- [ ] Agent definitions exposed as MCP resources (ADR: dispatch-workspace-safety, Decision 2)
- [ ] Resources dynamically parsed from `.rules/agents/*.md` frontmatter (ADR: dispatch-workspace-safety, Decision 2)
- [ ] `resources/list` provides agent discovery (ADR: dispatch-architecture, Decision 3, Phase 3)
- [ ] `list_changed` notification on agent file changes (ADR: dispatch-architecture, Decision 3, Phase 3)
- [ ] Resource content schema: name, description, tier, default_model, default_mode, tools (ADR: dispatch-workspace-safety, Decision 2)
- [ ] `acp_dispatch.py` preserved as library (ADR: dispatch-architecture, Decision 4)
- [ ] No Phase 4 scope creep — no locking, no permission enforcement (ADR: dispatch-architecture, Decision 3)
