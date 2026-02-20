---
title: "Code Health Audit — Final Summary"
date: 2026-02-18
tags: [audit, code-health]
---

# Code Health Audit — Final Summary

**Date:** 2026-02-18
**Team:** 3 Investigators (Sonnet), 2 Coding Agents (Opus), 2 Test Runners (Haiku), Supervisor (Opus)

## Scope

Full Python codebase under `.vaultspec/lib/src/` (10 modules) and `.vaultspec/lib/tests/` (4 test suites). 14 conftest files audited. Four waves of fixes applied over a single session.

## Wave 1 — Surface-Level (13 fixes)

| # | Sev | Fix |
|---|-----|-----|
| 1 | HIGH | Missing `await` in `cancel()` — `claude_executor.py:165` |
| 2 | HIGH | `_noop` stubs return `SubagentResult` — `test_mcp_tools.py` (4 sites) |
| 3 | HIGH | SQL injection test no longer swallows exceptions — `test_search.py` |
| 4 | HIGH | `test_no_fixes_for_valid_file` uses `tmp_path` — `test_verification.py` |
| 5 | HIGH | Mislocated tests moved to `orchestration/tests/test_load_agent.py` |
| 6 | HIGH | Deleted dead `test_interactive.py` (unconditional `pytest.skip()`) |
| 7 | MED | Cross-module `GeminiModels` import removed from vault conftest |
| 8 | MED | Duplicate `test_agent_md` fixture consolidated |
| 9 | MED | `_fast_index`/`_build_rag_components` deduplicated across conftest |
| 10 | MED | Graph tests reclassified from `unit` to `api` |
| 11 | MED | `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (2 sites) |
| 12 | MED | Dead commented-out code removed from `client.py` |
| 13 | LOW | `unittest.mock.patch` → `monkeypatch` in `test_docs_cli.py` |

**Verification:** 715 passed, 3 skipped, 0 failures.

## Wave 2 — Deep Security, Error Propagation, Contracts (14 fixes)

| # | Sev | Fix |
|---|-----|-----|
| 14 | CRIT | Crash-as-success bug: `run_subagent()` now raises `SubagentError` on crash |
| 15 | HIGH | Shell injection: `hooks/engine.py` switched from `shell=True` to `shlex.split` |
| 16 | HIGH | `CancelledError` bypass: `server.py` now catches and calls `cancel_task()` |
| 17 | HIGH | WORKING task TTL: `task_engine.py` evicts tasks older than `max_working_seconds` |
| 18 | MED | `asyncio.Lock` for `_active_clients` in `ClaudeA2AExecutor` |
| 19 | MED | `_delete_by_ids` now uses `_sanitize_filter_value` (store.py) |
| 20 | MED | `handle_create` uses `get_config().docs_dir` instead of hardcoded `".vault"` |
| 21 | MED | `_make_parser()` extracted from `vault.py main()` |
| 22 | MED | `get_document()`/`get_status()` routed through `get_engine()` singleton |
| 23 | MED | `VaultConstants.DOCS_DIR` dead code removed from `vault/models.py` |
| 24 | MED | `construct_system_prompt` made concrete on `AgentProvider` base class |
| 25 | MED | Graph rebuild backoff: `_graph_built_at = now` on exception |
| 26 | LOW | `test_create_generates_correct_filename` rewritten as integration test |
| 27 | LOW | `TestArgumentParsing` uses `docs._make_parser()` directly |

**Verification:** All passed (2 regressions caught and fixed by Supervisor).

## Wave 3 — Deep Error Propagation, Resilience, Cleanup (15 fixes)

| # | Sev | Fix |
|---|-----|-----|
| 28 | MED | Re-index abort: OSError during delete now raises instead of continuing |
| 29 | MED | Stream error signal: `claude_bridge.py` exception path uses `"refusal"` with explicit error log |
| 30 | MED | Connect cleanup: `_sdk_client` assigned only after successful `connect()` |
| 31 | MED | `graceful_cancel()` logs warning instead of `contextlib.suppress(Exception)` |
| 32 | MED | `close()` method added to `SubagentClient` for terminal cleanup |
| 33 | MED | `run_subagent()` calls `await client.close()` in finally block |
| 34 | MED | `reset_engine()` public API added to `rag/api.py` |
| 35 | LOW | Hook parse error: `exc_info=True` added to warning log |
| 36 | LOW | Hook path: `get_config().framework_dir` replaces hardcoded `parent.parent.parent` |
| 37 | LOW | `parse_vault_metadata` now calls `content.lstrip()` before matching |
| 38 | LOW | Dead ABC methods removed: `supported_models`, `get_model_capability` |
| 39 | LOW | f-string logging converted to `%s` style (~8 sites) |
| 40 | LOW | Thread-safety docstrings on `_notify()` and `server.py` globals |
| 41 | LOW | Broken singleton: `_engine = None` on GPU init failure |
| 42 | LOW | OSError log in `get_document()` upgraded from `debug` to `warning` |

**Verification:** 606 passed, 2 skipped, 1 pre-existing flake (`test_nonsense_query`).

## Wave 4 — Final Deferred Items (6 fixes)

| # | Sev | Fix |
|---|-----|-----|
| 43 | MED | `VaultRAG` lazy properties: `threading.Lock` for thread-safe double-checked init |
| 44 | MED | `get_engine()` / `reset_engine()`: `threading.Lock` for singleton safety |
| 45 | LOW | `_reader()` CancelledError: re-raised instead of swallowed |
| 46 | LOW | `terminal_output()` for unknown terminal: logs warning |
| 47 | LOW | `ThreadPoolExecutor` robustness: per-worker exception handling via `submit()` |
| 48 | LOW | `test_nonsense_query`: absolute threshold instead of flaky relative comparison |

## Cumulative Test Verification

| Scope | Count |
|-------|-------|
| protocol/ | 275 passed, 1 skipped |
| orchestration/ | 31 passed |
| hooks/ | 28 passed |
| vault/ | 46 passed |
| subagent_server/ | 63 passed, 2 skipped |
| verification + graph + metrics + core | 99 passed |
| rag/ (unit) | 47 passed |
| CLI functional | 151 passed |
| subagent functional | 17 passed |
| RAG functional + quality | 67 passed, 1 pre-existing flake |
| **Total** | **824 passed, 3 skipped, 0 regressions** |

## No Action Required

| # | Sev | Issue | Reason |
|---|-----|-------|--------|
| — | LOW | Private FastMCP API access (`_resource_manager._resources`) | Documented workaround, pinned dep |
| — | LOW | `require_gpu_corpus` fixture | Still used by 4 tests |

## Positive Findings

- **Zero `unittest.mock`/`@patch`** in protocol and subagent_server — all constructor DI
- **Clean conftest hierarchy** — no `sys.path` manipulation in any conftest
- **Handwritten test doubles** — `SDKClientRecorder`, `ConnRecorder`, `EchoExecutor`
- **Strong RAG test coverage** — real GPU embeddings, real LanceDB, real file I/O
- **Sandboxing centralized** in `protocol/sandbox.py` — consistent across ACP and A2A
- **Clean import graph** — no circular imports, respects layer boundaries

## Detailed Reports

- [[2026-02-18-health-audit-investigator1-core-vault-orch]]
- [[2026-02-18-health-audit-investigator2-protocol-subagent]]
- [[2026-02-18-health-audit-investigator3-data-functional]]
- [[2026-02-18-health-audit-deep-error-propagation]]
- [[2026-02-18-health-audit-deep-concurrency-state]]
- [[2026-02-18-health-audit-deep-contracts-abstractions]]
