---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-phase3-plan]]"
  - "[[2026-02-07-dispatch-phase2-summary]]"
---
# Phase 3 Summary: Agent Cards as MCP Resources

## Overview

Phase 3 adds MCP resource support to the dispatch server. Agent definitions from `.rules/agents/*.md` are exposed as MCP resources, enabling richer metadata discovery beyond the existing `list_agents` tool.

## Completed Steps

### Step 1: Research FastMCP Resource API

- Examined MCP SDK source for resource registration, templates, and notifications
- Key findings: `@mcp.resource()` decorator, `FunctionResource` for lazy content, `ResourceManager` for concrete/template resources, `ServerSession.send_resource_list_changed()` for notifications

### Step 2: Standardize Agent Frontmatter Schema

- Audited all 9 agent files in `.rules/agents/*.md`
- Added `mode` (read-write | read-only) and `tools` (comma-separated list) to every agent
- Fixed unquoted YAML string in `docs-curator.md`

### Step 3: Implement Agent Resource Provider

- Added `_agent_cache` and `_build_agent_cache()` for parsed frontmatter storage
- Added `_register_agent_resources()` using `FunctionResource` with `agents://<name>` URIs
- Resources registered at import time, discoverable via `resources/list` and `resources/read`
- Resource content schema: `name`, `description`, `tier`, `default_model`, `default_mode`, `tools`

### Step 4: Implement File-Watching for list_changed Notifications

- Added mtime-based change detection (`_snapshot_mtimes()`, `_has_changes()`)
- Added `_refresh_if_changed()` for lazy cache invalidation
- Added background `_poll_agent_files()` coroutine (5-second interval)
- Best-effort `list_changed` notification via active session (silently skipped if no session)

### Step 5: Write Resource Tests (14 tests)

- `TestAgentResources` (7 tests): listing, reading, schema validation, error handling, hint presence
- `TestFileWatching` (7 tests): mtime detection (add/modify/remove), cache refresh, resource re-registration

### Step 6: Update list_agents with Resource Hint

- Added `hint` field to `list_agents` response directing clients to `agents://{name}` for detailed metadata

## Test Summary

| Suite | Tests |
|---|---|
| test_mcp_dispatch.py | 45 |
| test_task_engine.py | 51 |
| **Total** | **96** |

## Commits

- `b249688` -- Standardize agent frontmatter and research FastMCP resource API
- `ecb453f` -- Implement agent resource provider for MCP resource discovery
- `6f50d82` -- Add mtime-based file watching and list_changed notifications
- `377313b` -- Add resource hint to list_agents response
- `dd7ed64` -- Add 14 tests for MCP resources and file-watching

## Files Modified

- `.rules/agents/*.md` (9 files) -- added `mode` and `tools` frontmatter
- `.rules/scripts/mcp_dispatch.py` -- resource cache, registration, file-watching, hint
- `.rules/scripts/tests/test_mcp_dispatch.py` -- 14 new tests, updated fixture

## ADR Compliance

- [x] Agent definitions exposed as MCP resources
- [x] Resources dynamically parsed from `.rules/agents/*.md` frontmatter
- [x] `resources/list` provides agent discovery
- [x] `list_changed` notification on agent file changes (best-effort)
- [x] Resource content schema: name, description, tier, default_model, default_mode, tools
- [x] `acp_dispatch.py` preserved as library (unchanged)
- [x] No Phase 4 scope creep
