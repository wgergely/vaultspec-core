---
feature: dispatch
phase: phase3
step: 3
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase3-plan]]"
---

# Step 3: Implement Agent Resource Provider

## Summary

Added MCP resource registration to `mcp_dispatch.py`. All agent definitions from `.rules/agents/*.md` are now exposed as concrete MCP resources with URI scheme `agents://<name>`.

## Implementation

### Cache Layer

- `_agent_cache: dict[str, dict]` -- in-memory cache keyed by agent name
- `_build_agent_cache()` -- scans `AGENTS_DIR`, parses frontmatter, returns cache dict
- `_parse_agent_metadata(path)` -- parses one agent file into the resource content schema

### Resource Registration

- `_register_agent_resources()` -- creates `FunctionResource` instances for each cached agent and registers them with `mcp._resource_manager.add_resource()`
- Called at module import time after `AGENTS_DIR` is resolved
- Each resource has URI `agents://<name>`, mime_type `application/json`, and a closure that returns cached metadata as JSON

### Helper Functions

- `_strip_quotes(value)` -- removes surrounding double quotes from YAML string values (parse_frontmatter preserves them)
- `_parse_tools(raw)` -- splits comma-separated tools string into a list

### Resource Content Schema

```json
{
  "name": "adr-researcher",
  "description": "...",
  "tier": "HIGH",
  "default_model": null,
  "default_mode": "read-only",
  "tools": ["Glob", "Grep", "Read", "WebFetch", "WebSearch", "Bash"]
}
```

## Verification

- Module loads successfully with 9 agents cached and registered
- `resources/list` returns all 9 agent resources
- `resources/read` for `agents://adr-researcher` returns correct JSON
- All 82 existing tests pass (31 dispatch + 51 task engine)

## Files Modified

- `.rules/scripts/mcp_dispatch.py` -- added resource cache, helpers, and registration
