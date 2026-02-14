---
feature: dispatch
phase: phase3
step: 5
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase3-plan]]"
---

# Step 5: Write Resource Tests

## Summary

Added 14 new tests in two classes to `test_mcp_dispatch.py`:

### TestAgentResources (7 tests)

- `test_resources_list_returns_all_agents` -- verifies `resources/list` includes valid agent URIs
- `test_resources_read_correct_metadata` -- verifies full schema for test-researcher
- `test_resources_read_executor_metadata` -- verifies test-executor schema
- `test_unknown_agent_uri_errors` -- verifies error raised for nonexistent agent
- `test_malformed_frontmatter_still_cached` -- verifies graceful handling of bad frontmatter
- `test_resource_content_matches_schema` -- verifies all resources have required keys
- `test_list_agents_includes_hint` -- verifies Phase 3 hint in list_agents response

### TestFileWatching (7 tests)

- `test_no_changes_detected_initially` -- baseline: no false positives
- `test_file_modification_detected` -- mtime change on existing file
- `test_file_addition_detected` -- new agent file added
- `test_file_removal_detected` -- agent file deleted
- `test_refresh_updates_cache` -- cache contains new agent after refresh
- `test_refresh_updates_resources` -- resources/list includes new agent after refresh
- `test_refresh_removes_deleted_agent` -- resources/list excludes deleted agent after refresh

## Fixture Updates

- `mcp_workspace` updated to include `mode` and `tools` in test agent frontmatter
- `mcp_workspace` now calls `_register_agent_resources()` after monkeypatching to ensure test resources are registered

## Test Counts

- Total dispatch tests: 45 (31 existing + 14 new)
- Total task engine tests: 51
- Full suite: 96 passed

## Files Modified

- `.rules/scripts/tests/test_mcp_dispatch.py` -- added TestAgentResources and TestFileWatching classes, updated mcp_workspace fixture
