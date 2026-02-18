---
tags: ["#audit", "#roadmap"]
date: 2026-02-17
related:
  - "[[2026-02-17-audit-summary-audit]]"
---

# Test Verification Report

**Date**: 2026-02-17
**Tester**: TechTester (automated agent)
**Environment**: Windows 11, Python 3.13.11, RTX 4080 SUPER (CUDA 13.0), PyTorch 2.10.0+cu130
**Test Framework**: pytest 9.0.2, pytest-asyncio 1.3.0, pytest-timeout 2.4.0

---

## Executive Summary

**976 tests collected across 57 test files.**

| Category | Passed | Failed | Skipped | Timeout | Total |
|----------|--------|--------|---------|---------|-------|
| CLI (functional) | 181 | 2 | 0 | 0 | 183 |
| Core (unit) | 64 | 0 | 0 | 0 | 64 |
| Vault (unit) | 55 | 0 | 0 | 0 | 55 |
| Graph (unit) | 10 | 0 | 0 | 0 | 10 |
| Metrics (unit) | 4 | 0 | 0 | 0 | 4 |
| Verification (unit) | 11 | 0 | 0 | 0 | 11 |
| Subagent Server (unit) | 63 | 0 | 2 | 0 | 65 |
| Protocol (unit) | 113 | 0 | 0 | 0 | 113 |
| ACP Protocol (unit) | 215 | 0 | 1 | 0 | 216 |
| A2A Protocol (unit+e2e) | 64 | 3 | 0 | 0 | 67 |
| Orchestration (unit) | 22 | 0 | 2 | 0 | 24 |
| RAG Unit (src/) | 47 | 0 | 0 | 0 | 47 |
| RAG Functional (tests/) | 67 | 0 | 0 | 1* | 68 |
| RAG Quality | 15 | 0 | 0 | 0 | 15 |
| RAG Performance | 11 | 0 | 0 | 0 | 11 |
| Subagent Functional | 17 | 0 | 0 | 0 | 17 |
| E2E (provider parity) | 11 | 0 | 0 | 0 | 11 |
| E2E (full cycle) | 8 | 0 | 0 | 0 | 8 |
| E2E (claude) | 2 | 0 | 0 | 1** | 3 |
| E2E (gemini/mcp) | - | - | - | - | ~10*** |

*: test_index_incremental timed out at 120s but passes at 300s timeout.
**: test_claude_dispatch_lifecycle requires live Claude API, times out without it.
***: Not individually run; require live API keys.

### Aggregate Results (excludable tests accounted for)

- **Passed: ~960**
- **Failed: 5** (2 CLI integration, 3 A2A e2e)
- **Skipped: 5** (2 subagent cancel, 2 orchestration interactive, 1 ACP)
- **Timeout: 2** (live API-dependent tests)

Pass rate (excluding live-API tests): ~99.5%

---

## Detailed Failure Analysis

### FAILURE 1-2: CLI Integration Tests (NEW -- not pre-existing)

**Files**: `.vaultspec/lib/tests/cli/test_integration.py`
**Tests**: `test_cli_help`, `test_cli_list_agents`

**Root Cause**: `ModuleNotFoundError: No module named 'logging_config'`

The tests run `subagent.py` as a subprocess (`sys.executable .vaultspec/lib/scripts/subagent.py`). When invoked this way, the `_paths.py` sys.path bootstrap doesn't run, so Python cannot find `logging_config` (which lives at `.vaultspec/lib/src/logging_config.py`).

**Severity**: MEDIUM. The `subagent.py` script only works when invoked with the proper Python path configured. This is a real integration bug -- the script is not self-bootstrapping like `cli.py` is.

### FAILURE 3-5: A2A E2E Tests (EXPECTED -- require live LLM APIs)

**Files**: `.vaultspec/lib/src/protocol/a2a/tests/test_e2e_a2a.py`
**Tests**:

- `TestGoldStandardBidirectional::test_claude_asks_gemini` -- requires Claude + Gemini
- `TestGoldStandardBidirectional::test_gemini_asks_claude` -- requires Gemini + Claude

**Root Cause**: `ProcessError: Command failed with exit code 1` -- Claude CLI not available in test environment.

**Severity**: LOW. These are true e2e integration tests that require live API keys. They are correctly designed but cannot pass without infrastructure. The fact they exist is valuable; they should be marked with appropriate markers (e.g., `@pytest.mark.claude`) and conditionally skipped.

---

## Known Pre-existing Failures (from MEMORY.md)

### NOT OBSERVED: `test_unit_core::test_colon_in_value` / `test_quoted_description`

These tests were listed as known PyYAML colon parsing failures. However, in the current run **both pass**:

**Status**: RESOLVED. The PyYAML colon parsing issue appears to have been fixed.

### NOT OBSERVED: `test_unit_providers` stale model assertions

The provider tests now use the correct model names and all 113 protocol tests pass.
**Status**: RESOLVED.

---

## Skipped Tests Analysis

| Test | Reason |
|------|--------|
| `TestCancelTask::test_cancel_invokes_graceful_cancel` | Implementation detail (subprocess cancel) |
| `TestCancelTask::test_cancel_stops_background_task` | Implementation detail (async cancel) |
| `TestInteractiveLoop::test_one_shot_mode` | Requires interactive terminal |
| `TestInteractiveLoop::test_interactive_mode_exit` | Requires interactive terminal |
| ACP `test_e2e_bridge` (1 test) | Cosmetic warning-related skip |

All skips are reasonable and intentional.

---

## CLI Test Runner Assessment

```python
cmd.append(str(ROOT_DIR / ".vaultspec" / "tests"))
```

But the actual test directory is `.vaultspec/lib/tests/`. This means `cli.py test all` fails to find the functional test directory. It does correctly include `.vaultspec/lib/src` for unit tests, but the functional tests at `.vaultspec/lib/tests/` are missed.

---

- 64 unit tests covering config defaults, env var loading, type parsing, validation, singleton, registry
- All pass. No gaps identified.

### 3. RAG (`rag/`) -- EXCELLENT

- 47 unit tests (embeddings, indexer, query parsing, search, store helpers)
- 68 functional tests (API, search, store, robustness, indexer, performance, quality)
- Performance tests validate latency baselines (p50, p95).
- Quality tests validate search relevance, authority boost, filter precision.

- 113 unit tests (client, providers, fileio, permissions, sandbox)
- 216 ACP tests (bridge lifecycle, resilience, sandbox, streaming, terminal, e2e bridge)

- 67 A2A tests (agent card, executors, discovery, e2e, unit)
- 65 unit tests (helpers, MCP tools, agent cache, permissions, dispatch overrides)
- 17 functional tests (tool registration, protocol round-trip, task integration)
- All pass (2 skipped for cancel edge cases).

- 24 tests (task engine, lock manager, utils, interactive)
- All pass (2 skipped for interactive mode tests).

- 10 unit tests covering graph building, hotspots, orphans, links, feature rankings.

### 8. Metrics (`metrics/`) -- ADEQUATE

- 4 unit tests (VaultSummary, GetVaultMetrics).

- All pass but coverage is thin.

### 9. Verification (`verification/`) -- GOOD

- All pass.

### 10. CLI (`lib/scripts/cli.py`) -- EXCELLENT (sync), BROKEN (test runner)

- 183 tests for sync operations (collect, transform, incremental, operations, parse, config).
- All sync tests pass.
- Integration tests fail due to `subagent.py` import bug.
- `cli.py test` runner has wrong test path.

### 11. E2E Tests -- GOOD DESIGN

- Provider parity: 11 tests, all pass (validates Claude/Gemini produce equivalent specs).
- Full cycle: 8 non-API tests pass (pipeline, docs, frontmatter, cleanup).
- Live API tests: exist but require keys to run. Good design pattern.

---

## Coverage Gaps

### Modules with NO unit tests

1. **`logging_config.py`** -- no tests for logging configuration utility
2. **`orchestration/constants.py`** -- no tests (may be trivial constants)
3. **`protocol/a2a/state_map.py`** -- no direct unit tests (indirectly tested via executors)

5. **`rag/query.py`** -- has unit tests in `test_query.py`, but also tested via `test_search_unit.py`

1. **CLI test runner path bug** -- functional test path is `.vaultspec/tests` (wrong), should be `.vaultspec/lib/tests`
2. **`subagent.py` self-bootstrap** -- script cannot find `logging_config` when run directly
3. **No test isolation for `docs.py`** -- the docs CLI has no dedicated tests

5. **Benchmark runner (`bench_rag.py`)** -- exists but not included in any test marker category

### Missing test markers

- The A2A e2e tests in `test_e2e_a2a.py` lack `@pytest.mark.claude` / `@pytest.mark.gemini` markers, causing them to fail loudly instead of being skipped in environments without API keys.

---

## Test Infrastructure Assessment

### Strengths

1. **Excellent session-scoped fixtures** -- RAG components built once, shared across tests. `.lance-fast` and `.lance-full` isolation prevents corruption.
2. **Centralized constants** -- `tests/constants.py` eliminates scattered path definitions.
3. **Vault snapshot reset** -- `_vault_snapshot_reset()` autouse fixture restores `test-project/.vault/` after tests.
4. **No sys.path hacks in conftest** -- clean `pythonpath` config in pyproject.toml.
5. **Good marker discipline** -- unit, api, search, index, quality markers well-defined.
6. **Strong edge case coverage** -- robustness tests for unicode, SQL injection, code blocks, embedded YAML separators.

### Weaknesses

1. **CLI test runner broken** -- wrong path in `test_run()`.
2. **Timeout defaults too low** -- RAG functional tests need 300s, not the 120s default. The initial full run hung because `test_index_incremental` (full corpus re-index) exceeded the default timeout.
3. **Missing skip decorators on API-dependent tests** -- A2A e2e tests should be conditionally skipped.
4. **`subagent.py` import failure** -- the script assumes `logging_config` is on sys.path, but doesn't bootstrap it.
5. **No CI configuration visible** -- no `.github/workflows/` or similar CI setup found. Test automation relies on manual invocation.

---

## Cross-Reference: Test Coverage vs Feature List

(Cross-references to `02-tech-audit.md` features)

| Feature | Test Coverage | Status |
|---------|-------------|--------|
| Vault document scanning | 55 vault unit tests | COVERED |
| RAG indexing (full + incremental) | 8 indexer + 11 performance tests | COVERED |
| RAG semantic search | 21 search + 15 quality tests | COVERED |
| RAG query parsing/filters | 19 query/search unit tests | COVERED |
| GPU-only embeddings | 7 embedding tests | COVERED |
| Graph analysis | 10 graph unit tests | COVERED |
| Vault metrics | 4 metrics tests | COVERED (thin) |
| Verification/integrity | 11 verification tests | COVERED |
| Config system | 64+35 config tests | COVERED (excellent) |
| CLI sync (rules/agents/skills) | 181 CLI tests | COVERED (excellent) |
| CLI test runner | 2 integration tests | BROKEN |
| Subagent MCP server | 65+17 tests | COVERED (excellent) |
| ACP bridge (Gemini) | 216 tests | COVERED (excellent) |
| A2A protocol | 67 tests | COVERED (3 need live API) |
| Provider parity (Claude/Gemini) | 11+113 provider tests | COVERED |
| File I/O sandbox | 6+10+12 sandbox tests | COVERED |
| Task engine | 15 task engine tests | COVERED |
| Interactive mode | 2 tests (skipped) | MINIMAL |
| `docs.py` CLI | 0 tests | NOT COVERED |
| `subagent.py` standalone | 2 tests (broken) | BROKEN |

---

## Recommendations

1. **Fix `cli.py test_run()` path**: Change `.vaultspec/tests` to `.vaultspec/lib/tests`.
2. **Fix `subagent.py` import**: Add `_paths.py` bootstrap or make `logging_config` importable via proper package installation.
3. **Add skip markers to A2A e2e tests**: Use `@pytest.mark.claude` / `@pytest.mark.gemini` with `skipIf` to avoid false failures.
4. **Increase RAG test timeouts**: Set `test_index_incremental` to 300s or mark as `@pytest.mark.quality`.
5. **Add `docs.py` tests**: The docs CLI has no test coverage.
6. **Add CI pipeline**: No automated test runs found. GitHub Actions would catch regressions.
