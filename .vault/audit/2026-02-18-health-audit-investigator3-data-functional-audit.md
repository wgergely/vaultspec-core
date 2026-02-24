---
tags:
  - "#audit"
  - "#health-audit"
date: "2026-02-18"
---
# Code Health Audit: Data & Functional Modules

**Auditor:** Investigator3
**Date:** 2026-02-18
**Scope:** `rag/`, `graph/`, `metrics/`, `verification/` source modules + all functional/integration tests under `.vaultspec/lib/tests/`

---

## Executive Summary

The data and functional modules are structurally sound with clear separation of concerns. The RAG pipeline is the most complex subsystem and is well-implemented with proper GPU enforcement, incremental indexing, and hybrid search. Test coverage is broad but inconsistent in quality — several tests have silent failure modes, incorrect pytest marker classifications, and fragile coupling to implementation internals. The most actionable findings are: duplicated conftest helper functions, graph tests miscategorized as unit tests, a silently swallowing SQL injection test, and a docs CLI test that never exercises the CLI command it claims to test.

---

## Module Audit: `rag/`

### Code Quality

The RAG module (`embeddings.py`, `indexer.py`, `store.py`, `search.py`, `api.py`) is the most mature subsystem in scope:

- **`embeddings.py`**: `EmbeddingModel` enforces GPU-only with `GPUNotAvailableError`. `encode_documents()` uses length-sorted batching to minimize padding. `encode_query()` has `functools.lru_cache` for repeated query embeddings. `get_device_info()` uses `getattr` fallback for PyTorch 2.10 API compat (`total_memory` vs `total_mem`).
- **`indexer.py`**: `VaultIndexer` uses `ThreadPoolExecutor` for I/O-bound document preparation in `full_index()`. `incremental_index()` compares mtime via `index_meta.json` sidecar. `prepare_document()` is correctly a standalone function (not a method), enabling parallel use.
- **`store.py`**: `VaultStore.hybrid_search()` runs BM25 and ANN in parallel via `ThreadPoolExecutor`. `_sanitize_filter_value()` escapes SQL values via string replacement — functional but not parameterized. `_build_where()` constructs WHERE clauses from tag lists.
- **`search.py`**: `VaultSearcher.search()` implements RRF reranking. `rerank_with_graph()` applies three graph-based boosts (authority, neighborhood, recency). `VaultGraph` within searcher is cached with a configurable TTL.
- **`api.py`**: `VaultRAG` is a singleton engine with lazy properties. Global `_engine` var with `reset_engine()` for test isolation.

**Concern — SQL injection defense**: `_sanitize_filter_value()` uses `value.replace("'", "''").replace("\\", "\\\\")` rather than parameterized queries. This is a known-pattern workaround for LanceDB's filter API limitation, but it is a manual escaping approach. The tests cover the escape logic, but a future LanceDB API that does support parameterization should be preferred.

### Test Integrity

**`rag/tests/conftest.py`** (unit-level):

- Defines `_fast_index()` and `_build_rag_components()` — these are **verbatim duplicates** of the same functions in `.vaultspec/lib/tests/conftest.py`. This creates a silent drift risk: a bug fix in one copy will not propagate to the other.
- Uses `LANCE_SUFFIX_UNIT = ".lance-fast-unit/"` — a third lance directory distinct from the functional test fixtures (`.lance-fast/` and `.lance-full/`), which is correct for isolation.
- `VaultStore.__new__(VaultStore)` pattern bypasses `__init__` to avoid initializing a real LanceDB connection. This works but directly sets private attributes (`_root`, `_lance_dir`, `_table`). Fragile if `__init__` adds new required attributes.

**`rag/tests/test_store.py`**: Unit tests for `_parse_json_list` and `_build_where`. SQL injection escape check is present. Guard `pytest.importorskip("lancedb")` is used — correct.

**`rag/tests/test_query.py`** and **`test_search_unit.py`**: Both test `parse_query()`. Overlap is minor (one tests with RAG deps guard, the other is pure unit), but could be consolidated.

**`rag/tests/test_embeddings.py`**: Tests real `EmbeddingModel` — semantic similarity, batch shape, LRU cache hits. GPU-gated correctly.

**`rag/tests/test_indexer_unit.py`**: Tests `_extract_title`, `_extract_feature`, `prepare_document` against real test-project files. No GPU required. Well-isolated.

### Issues Found

| Severity | Issue |
|----------|-------|
| Medium | `_fast_index` / `_build_rag_components` duplicated between `tests/conftest.py` and `rag/tests/conftest.py` |
| Low | SQL injection defense uses manual escaping rather than parameterized queries |
| Low | `test_query.py` and `test_search_unit.py` overlap on `parse_query()` tests |
| Low | `VaultStore.__new__()` bypass pattern in fixtures is fragile against `__init__` changes |

---

## Module Audit: `graph/`

### Code Quality

**`graph/api.py`**: `VaultGraph` performs a two-pass build over the vault. Pass 1 extracts metadata (doc_type, tags) from frontmatter. Pass 2 extracts wiki-links from content to build `out_links`/`in_links`. `DocNode` is a well-defined dataclass. `get_hotspots()`, `get_feature_rankings()`, `get_orphaned()`, `get_invalid_links()` are all clean query methods.

No concerns with production code quality.

### Test Integrity

**`graph/tests/test_graph.py`**: All tests read the real `TEST_PROJECT` filesystem. They verify node counts (`> 80`), doc_type assignment, link populations, and feature rankings against live data. These tests are marked `pytest.mark.unit` — **this is incorrect**. Tests that read the real filesystem and assert on live data counts are integration tests, not unit tests. This miscategorization means they will run in unit test suites that are expected to be fast and dependency-free.

### Issues Found

| Severity | Issue |
|----------|-------|
| Medium | `test_graph.py` marked `pytest.mark.unit` but tests against real filesystem (should be `integration` or a new `api` marker) |

---

## Module Audit: `metrics/`

### Code Quality

**`metrics/api.py`**: `get_vault_metrics()` returns a `VaultSummary` dataclass. It imports `list_features` from `verification.api` — a cross-module dependency that is intentional but worth noting. `VaultSummary` includes counts by `DocType` and a `features` set.

Clean, minimal code. No concerns.

### Test Integrity

**`metrics/tests/test_metrics.py`**: Tests `VaultSummary` construction and `get_vault_metrics()` on both the real vault root and `tmp_path`. Verifies that features are deduplicated (set semantics). Coverage is adequate.

### Issues Found

None of note.

---

## Module Audit: `verification/`

### Code Quality

**`verification/api.py`**: The most complex module in scope. `fix_violations()` performs 6 distinct auto-repair operations: add tags, add doc_type tag, add placeholder feature tag, add date field, fix wrong filename suffix, add date prefix. `_rebuild_frontmatter()` serializes `DocumentMetadata` back to YAML frontmatter.

The BOM stripping (`content.lstrip("\ufeff")`) before `parse_vault_metadata()` is a defensive correctness measure.

`verify_vertical_integrity()` requires every feature tag used anywhere in the vault to have a corresponding plan document. This is a strong invariant that will flag many false positives in a growing vault.

### Test Integrity

**`verification/tests/test_verification.py`**: `TestFixViolations` uses `tmp_path` for all mutation tests — this is correct isolation. However, `test_no_fixes_for_valid_file` calls `fix_violations(vault_root)` against the shared live `vault_root` fixture. If the vault contains any invalid documents (which it does — it has a `stories/` directory flagged by `verify_vault_structure`), `fix_violations` could **modify or rename files in the shared test corpus**. The `_vault_snapshot_reset` autouse fixture in `tests/conftest.py` runs `git checkout -- test-project/.vault/` at session teardown, which provides eventual recovery, but mid-session corruption is still possible.

### Issues Found

| Severity | Issue |
|----------|-------|
| High | `test_no_fixes_for_valid_file` runs `fix_violations()` against the live shared `vault_root` — could mutate shared test corpus mid-session |

---

## Functional Tests Audit: `tests/cli/`

### `test_sync_operations.py`, `test_sync_collect.py`, `test_sync_parse.py`

Well-structured unit tests for CLI sync subsystems. Real file operations against `TEST_PROJECT` via the `_isolate_cli` autouse fixture (which calls `cleanup_test_project()` after each test). Coverage of add/update/prune/dry-run/skip/atomic-write scenarios is comprehensive.

### `test_sync_incremental.py`

Multi-pass lifecycle test across 5 sync passes with mutations (agent tier changes, skill lifecycle, system prompt changes). This is the most thorough test in the CLI suite — valuable regression protection.

### `test_docs_cli.py`

Three concerns:

**1. Lone `unittest.mock` usage**: `TestLoggingDispatch` uses `from unittest.mock import patch` to patch `vault.py` internals. This is the only occurrence of `unittest.mock` in the entire functional test scope. Not a defect, but inconsistent with the rest of the test suite which relies on `monkeypatch`.

**2. Fragile argument parser reconstruction**: `TestArgumentParsing` rebuilds the argument parser in-test by importing the parser-creation function and constructing it independently, rather than invoking the CLI. Changes to the production parser will not automatically break these tests if the test's manual construction diverges from the real code path.

**3. No-op CLI test**: `TestCreateSubcommand.test_create_generates_correct_filename` constructs the expected output filename manually and asserts the constructed string — it does not invoke the `create` subcommand at all. This test provides zero coverage of the actual `create` command execution path.

### `test_integration.py`

Two subprocess integration tests (`test_cli_help`, `test_cli_list_agents`). Thin but correctly marked `integration`. Provides basic smoke-test coverage.

### Issues Found

| Severity | Issue |
|----------|-------|
| Medium | `test_create_generates_correct_filename` never invokes the CLI `create` command — zero command coverage |
| Medium | `TestArgumentParsing` reconstructs the parser in-test rather than exercising the real CLI entry point |
| Low | `test_docs_cli.py` uses `unittest.mock.patch` inconsistently with the rest of the suite (which uses `monkeypatch`) |

---

## Functional Tests Audit: `tests/rag/`

### `test_api.py`

Tests the RAG public facade. Uses `VaultSearcher` directly to avoid conflicting LanceDB connections (correct design). `test_engine_singleton` manually resets `api_mod._engine = None` for cleanup — acceptable but depends on module-internal state.

### `test_search.py`

End-to-end `VaultSearcher` tests. The SQL injection adversarial query test (`test_sql_injection_in_filter_value`) uses `try/except: pass` which **silently swallows all exceptions**. If the search call raises an exception (including an `AssertionError` from the test framework), the test will pass. This is a silent failure mode that provides false confidence about the SQL injection defense.

### `test_store.py`, `test_indexer.py`

Integration tests against real GPU-indexed data. Well-structured, no major concerns.

### `test_robustness.py`

Edge-case tests: `stories/` directory skipped, audit nonstandard frontmatter, unicode content, YAML separator edge cases, graph reranking with orphans. Good coverage of known edge cases.

### `test_quality.py`

Known-answer precision tests and ranking quality checks. Authority boost measurability test requires the full corpus. Correct use of `pytest.mark.quality`.

### `test_performance.py`

Latency bounds (single query <2s, batch 5 queries <5s), disk footprint (<50MB), graph cache TTL. Performance thresholds are generous relative to observed baselines (~36ms p50), providing a large buffer.

### Issues Found

| Severity | Issue |
|----------|-------|
| High | `test_sql_injection_in_filter_value` uses `try/except: pass` — silently swallows all exceptions including test assertion failures |

---

## Functional Tests Audit: `tests/e2e/`

### `test_full_cycle.py`

Full Research→ADR→Plan pipeline via real Claude/Gemini CLIs. Correctly skipped if CLI not installed (`pytest.importorskip` equivalent via skip conditions). Also contains `@pytest.mark.unit` helper tests for fixture functions — acceptable compartmentalization.

### `test_claude.py`, `test_gemini.py`

Unit tests for provider `prepare_process()` and `load_rules()`. Real CLI dispatch tests gated on CLI availability. Correct structure.

### `test_provider_parity.py`

Uses `_seed_gemini_version_cache` fixture to pre-seed module globals (`gmod._cached_version`, `gmod._which_fn`). This is module-level monkey-patching via pytest fixture — non-obvious but acceptable. The fixture name clearly describes its purpose.

### `test_mcp_e2e.py`

Directly patches internal server state (`_srv._agent_cache`, `_srv.task_engine`) before calling `mcp.call_tool()`. This tests the observable MCP protocol behavior but is tightly coupled to implementation internals — any refactor of `_agent_cache` or `task_engine` attribute names will break these tests silently rather than through a compilation error.

### Issues Found

| Severity | Issue |
|----------|-------|
| Low | `test_mcp_e2e.py` directly patches private server attributes — tight coupling to implementation internals |
| Low | `test_provider_parity.py` module-global monkeypatching via fixture is non-obvious but not defective |

---

## Functional Tests Audit: `tests/subagent/`

### `test_subagent.py`

Single integration test: verifies that `LockManager` releases a lock when a `TaskEngine` task completes. The test exercises the `TaskEngine` + `LockManager` integration path. Thin coverage for the subagent subsystem — the MCP tool surface is tested separately in `subagent_server/tests/`.

### `test_mcp_protocol.py`

Protocol tests via `mcp.call_tool()`. Uses `_noop_run_subagent` (returns a fixed `SubagentResult`) and `_test_run` stubs injected via `srv._run_subagent_fn`. Tests tool registration, annotations, schema, and round-trip lifecycle. The dispatch path (`run_subagent()` → actual ACP subprocess) is not exercised in these tests — this is an acceptable trade-off for protocol isolation but means real dispatch failures would not be caught here.

### Issues Found

| Severity | Issue |
|----------|-------|
| Low | `test_subagent.py` has only one test — subagent subsystem has thin functional coverage |

---

## `conftest.py` Audit

### `.vaultspec/lib/conftest.py` (common ancestor)

Minimal — re-exports `PROJECT_ROOT`, `TEST_PROJECT`, `TEST_VAULT` from `tests.constants`. No fixtures defined. Correct role as a thin path-forwarding shim.

### `.vaultspec/lib/tests/conftest.py` (functional test root)

Contains the session-scoped GPU fixtures:

- `_fast_index()` and `_build_rag_components()` — **duplicated in `rag/tests/conftest.py`**
- `rag_components` (`.lance-fast/`) and `rag_components_full` (`.lance-full/`) — correct separate lance dirs
- `_vault_snapshot_reset` autouse session fixture — runs `git checkout -- test-project/.vault/` at teardown. This is a critical safety net for mutation tests, but does not protect against mid-session corruption within the same test session.
- `test_agent_md`, `vaultspec_config`, `config_override`, `clean_config` — config management fixtures

**`require_gpu_corpus` fixture**: documented as a no-op kept for backward compatibility after CPU support was removed. It should be removed to reduce dead code.

### Sub-directory `conftest.py` files (graph, metrics, verification, rag)

All follow the same pattern: `_reset_cfg` autouse fixture + `vault_root` returning `TEST_PROJECT`. Consistent and minimal. No concerns.

### Issues Found

| Severity | Issue |
|----------|-------|
| Medium | `_fast_index` / `_build_rag_components` duplicated between `tests/conftest.py` and `rag/tests/conftest.py` (same as RAG module issue) |
| Low | `require_gpu_corpus` fixture is a documented no-op — dead code that should be removed |

---

## Critical Findings Summary

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | High | `tests/rag/test_search.py` | `test_sql_injection_in_filter_value` uses bare `try/except: pass` — silently swallows all exceptions, providing false positive test result |
| 2 | High | `verification/tests/test_verification.py:194` | `test_no_fixes_for_valid_file` runs `fix_violations()` against the live shared `vault_root` — can mutate shared corpus mid-session |
| 3 | Medium | `rag/tests/conftest.py` + `tests/conftest.py` | `_fast_index` and `_build_rag_components` are verbatim duplicates — silent drift risk |
| 4 | Medium | `graph/tests/test_graph.py` | All tests marked `pytest.mark.unit` but read real filesystem — should be `integration` |
| 5 | Medium | `tests/cli/test_docs_cli.py` | `test_create_generates_correct_filename` never invokes the CLI `create` command — zero real coverage |
| 6 | Medium | `tests/cli/test_docs_cli.py` | `TestArgumentParsing` rebuilds the argparser in-test — divergence from production parser will not be caught |
| 7 | Low | `tests/conftest.py` | `require_gpu_corpus` is a documented no-op — dead code |
| 8 | Low | `tests/e2e/test_mcp_e2e.py` | Patches private server attributes directly — tight coupling to implementation internals |
| 9 | Low | `rag/store.py` | SQL injection defense via manual string escaping (functional but not parameterized) |

---

## Recommendations

**Immediate (High severity):**

- Fix `test_sql_injection_in_filter_value`: replace `try/except: pass` with an explicit assertion that no exception is raised, or assert on the return value. A `pytest.raises` pattern or explicit empty `assert result is not None` is sufficient.

- Fix `test_no_fixes_for_valid_file`: either change it to use `tmp_path` with a known-valid file, or add a `_vault_snapshot_reset` fixture scope that covers this test.

**Short-term (Medium severity):**

- Deduplicate `_fast_index` / `_build_rag_components`: define once in `tests/conftest.py` and import in `rag/tests/conftest.py`.
- Reclassify `graph/tests/test_graph.py` tests as `pytest.mark.api` (or `integration`).

- Replace `test_create_generates_correct_filename` with a real subprocess invocation of `vault.py create`.
- Fix `TestArgumentParsing` to invoke the real CLI rather than rebuilding the parser.

**Cleanup (Low severity):**

- Remove `require_gpu_corpus` fixture.
- Evaluate whether `test_docs_cli.py` can adopt `monkeypatch` consistently with the rest of the suite.
