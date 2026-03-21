---
tags:
  - '#plan'
  - '#mcp-testing'
date: '2026-02-22'
related:
  - '[[2026-02-22-mcp-testing-adr]]'
  - '[[2026-02-22-mcp-testing-research]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `mcp-testing` plan

Add in-memory MCP client session tests using the SDK's
`create_connected_server_and_client_session` per
\[[2026-02-22-mcp-testing-adr]\].

## Proposed Changes

Create `src/vaultspec/mcp_server/tests/test_client_session.py` — a new test
file exercising the full MCP protocol stack via in-memory transport. Two
fixture variants (with and without lifespan). Tests cover handshake, tool
discovery, resource discovery, tool round-trips, error propagation, and
concurrency.

## Tasks

- Task 1: Create fixtures

  1. `client_session` fixture — uses `create_server()` (with lifespan),
     calls `initialize_server()` first, passes `raise_exceptions=True`

  1. `client_session_no_lifespan` fixture — bare `FastMCP` with tools
     registered but no lifespan, for focused tests

  1. Helper fixtures: `baker_cache`, `fresh_engine` (reuse existing
     patterns from `test_mcp_protocol.py`)

- Task 2: Protocol handshake + discovery tests

  1. `TestProtocolHandshake::test_initialize_succeeds` — session connects
  1. `TestProtocolHandshake::test_capabilities_include_tools` — tools cap
  1. `TestProtocolHandshake::test_capabilities_include_resources` — resources cap
  1. `TestToolDiscovery::test_all_15_tools_listed` — count + names
  1. `TestToolDiscovery::test_tool_schemas_present` — inputSchema on each
  1. `TestToolDiscovery::test_tool_annotations_present` — annotations set
  1. `TestResourceDiscovery::test_agent_resources_listed` — agents:// URIs
  1. `TestResourceDiscovery::test_read_agent_resource` — returns JSON

- Task 3: Subagent tool round-trip tests

  1. `TestSubagentToolsRoundTrip::test_list_agents` — call through protocol
  1. `TestSubagentToolsRoundTrip::test_dispatch_agent` — dispatch + taskId
  1. `TestSubagentToolsRoundTrip::test_get_task_status` — poll status
  1. `TestSubagentToolsRoundTrip::test_cancel_task` — cancel a task
  1. `TestSubagentToolsRoundTrip::test_get_locks` — empty locks list

- Task 4: Team tool round-trip tests

  1. `TestTeamToolsRoundTrip::test_list_teams` — empty list
  1. `TestTeamToolsRoundTrip::test_list_teams_after_create` — if feasible

- Task 5: Error propagation tests

  1. `TestErrorPropagation::test_unknown_tool_is_error`
  1. `TestErrorPropagation::test_dispatch_unknown_agent_is_error`
  1. `TestErrorPropagation::test_get_status_missing_task_is_error`
  1. `TestErrorPropagation::test_cancel_missing_task_is_error`

- Task 6: Concurrent calls

  1. `TestConcurrentCalls::test_parallel_list_agents` — fire 5 concurrent
     `list_agents` calls on one session

## Parallelization

Tasks 2-6 are independent test classes that can be written in parallel by
separate agents. However, they all go in the same file and share fixtures
from Task 1, so sequential writing is simpler.

Recommended: single executor agent writes the entire file.

## Verification

- `uv run pytest src/vaultspec/mcp_server/tests/test_client_session.py -v`
  passes all tests

- No Windows async hangs (in-memory transport)

- Existing 105 tests remain unaffected
