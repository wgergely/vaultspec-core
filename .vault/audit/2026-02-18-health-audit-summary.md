---
title: "Code Health Audit — Final Summary"
date: 2026-02-18
tags: [audit, code-health]
---

# Code Health Audit — Final Summary

**Date:** 2026-02-18
**Team:** 3 Investigators (Sonnet), 2 Coding Agents (Opus), 2 Test Runners (Haiku)

## Scope

Full Python codebase under `.vaultspec/lib/src/` (10 modules) and `.vaultspec/lib/tests/` (4 test suites). 14 conftest files audited.

## Findings: 21 total (6 HIGH, 11 MEDIUM, 4 LOW)

### Fixed (13 items)

| # | Sev | Fix | Agent |
|---|-----|-----|-------|
| 1 | HIGH | Missing `await` in `cancel()` — `claude_executor.py:165` | CodingAgent1 |
| 2 | HIGH | `_noop` stubs return `SubagentResult` — `test_mcp_tools.py` (4 sites) | CodingAgent1 |
| 3 | HIGH | SQL injection test no longer swallows exceptions — `test_search.py` | CodingAgent1 |
| 4 | HIGH | `test_no_fixes_for_valid_file` uses `tmp_path` — `test_verification.py` | CodingAgent1 |
| 5 | HIGH | Mislocated tests moved to `orchestration/tests/test_load_agent.py` | CodingAgent2 |
| 6 | HIGH | Deleted dead `test_interactive.py` (unconditional `pytest.skip()`) | CodingAgent1 |
| 7 | MED | Cross-module `GeminiModels` import removed from vault conftest | CodingAgent2 |
| 8 | MED | Duplicate `test_agent_md` fixture consolidated | CodingAgent2 |
| 9 | MED | `_fast_index`/`_build_rag_components` deduplicated across conftest | CodingAgent2 |
| 10 | MED | Graph tests reclassified from `unit` to `api` | CodingAgent2 |
| 11 | MED | `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (2 sites) | CodingAgent1 |
| 12 | MED | Dead commented-out code removed from `client.py` | CodingAgent1 |
| 13 | LOW | `unittest.mock.patch` → `monkeypatch` in `test_docs_cli.py` | CodingAgent2 |

### Deferred (7 items — require design decisions or deeper changes)

| # | Sev | Issue | Reason |
|---|-----|-------|--------|
| 14 | MED | `test_create_generates_correct_filename` never invokes CLI | Needs new CLI integration test design |
| 15 | MED | `TestArgumentParsing` rebuilds parser in-test | Needs CLI test refactoring strategy |
| 16 | MED | Broad `except Exception:` in `run_subagent()` | Error propagation design decision |
| 17 | MED | TaskEngine working-task memory leak (no TTL) | Needs TTL policy decision |
| 18 | MED | Shell injection risk in `hooks/engine.py` (`shell=True`) | Security design decision |
| 19 | LOW | f-string logging anti-pattern (~8 sites) | Style, low impact |
| 20 | LOW | `require_gpu_corpus` fixture kept (still used by 4 tests) | Investigator3 corrected — not dead |

### No Action Required (1 item)

| # | Sev | Issue | Reason |
|---|-----|-------|--------|
| 21 | LOW | Private FastMCP API access (`_resource_manager._resources`) | Documented workaround, pinned dep |

## Test Verification

| Runner | Scope | Result |
|--------|-------|--------|
| TestRunner1 | Unit: orchestration, vault, protocol, subagent_server, graph, verification | **546 passed**, 3 skipped |
| TestRunner2 | Functional: CLI, subagent, RAG SQL injection | **169 passed** |
| **Total** | | **715 passed, 3 skipped, 0 failures** |

## Positive Findings

- **Zero `unittest.mock`/`@patch`** in protocol and subagent_server test scopes — all constructor DI
- **Clean conftest hierarchy** — no `sys.path` manipulation in any conftest
- **Handwritten test doubles** — `SDKClientRecorder`, `ConnRecorder`, `EchoExecutor`, etc.
- **Strong RAG test coverage** — real GPU embeddings, real LanceDB, real file I/O
- **Sandboxing is centralized** in `protocol/sandbox.py` — consistent across ACP and A2A
- **`ClaudeACPBridge` well-documented** despite ~965 lines — every method has a docstring

## Files Modified

- `.vaultspec/lib/src/protocol/a2a/executors/claude_executor.py` — await fix
- `.vaultspec/lib/src/protocol/acp/client.py` — dead code removal
- `.vaultspec/lib/src/orchestration/subagent.py` — asyncio API fix
- `.vaultspec/lib/src/orchestration/tests/test_interactive.py` — deleted
- `.vaultspec/lib/src/orchestration/tests/test_load_agent.py` — new (moved tests)
- `.vaultspec/lib/src/orchestration/tests/conftest.py` — added fixtures
- `.vaultspec/lib/src/vault/tests/test_core.py` — removed moved classes
- `.vaultspec/lib/src/vault/tests/conftest.py` — removed moved fixtures
- `.vaultspec/lib/src/verification/tests/test_verification.py` — tmp_path fix
- `.vaultspec/lib/src/subagent_server/tests/test_mcp_tools.py` — _noop fix
- `.vaultspec/lib/src/graph/tests/test_graph.py` — marker fix
- `.vaultspec/lib/src/rag/tests/conftest.py` — deduplicated
- `.vaultspec/lib/tests/conftest.py` — removed duplicate fixture
- `.vaultspec/lib/tests/rag/test_search.py` — exception swallowing fix
- `.vaultspec/lib/tests/cli/test_docs_cli.py` — monkeypatch conversion

## Detailed Reports

- [[2026-02-18-health-audit-investigator1-core-vault-orch]]
- [[2026-02-18-health-audit-investigator2-protocol-subagent]]
- [[2026-02-18-health-audit-investigator3-data-functional]]
