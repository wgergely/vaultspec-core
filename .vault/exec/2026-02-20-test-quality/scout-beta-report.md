---
tags: ["#exec", "#test-quality"]
date: 2026-02-20
related: []
---

# Scout Beta Report: CLI, e2e, RAG, Core, Vault, Hooks Tests

**Scope**: `.vaultspec/lib/tests/cli/`, `.vaultspec/lib/tests/e2e/`,
`.vaultspec/lib/src/rag/tests/`, `.vaultspec/lib/src/core/tests/`,
`.vaultspec/lib/src/vault/tests/`, `.vaultspec/lib/src/hooks/tests/`

**Total files scanned**: 27
**Files with violations**: 4
**Total violations**: 12

---

## Summary Table

| File | Violations |
|------|-----------|
| `.vaultspec/lib/tests/cli/test_team_cli.py` | 9 |
| `.vaultspec/lib/tests/cli/test_docs_cli.py` | 3 |
| `.vaultspec/lib/tests/e2e/test_provider_parity.py` | 1 (borderline) |
| All others | 0 |

---

## `.vaultspec/lib/tests/cli/test_team_cli.py`

### `TestCommandCreate::test_create_persists_session` [LINE 213]
**Violation**: `patch.object` on `TeamCoordinator.form_team`, `__aenter__`, `__aexit__`; `_fake_*` helper functions
**Why**: `patch.object(TeamCoordinator, "form_team", _fake_form)` replaces the actual `form_team` coroutine with `_fake_form` which just returns a canned `TeamSession`. The test never exercises real team formation logic — it only verifies that the CLI wrapper serializes the returned object to disk. The async context manager is also replaced so `TeamCoordinator.__aenter__`/`__aexit__` do nothing. The internal `_fake_form`, `_noop_aenter`, `_noop_aexit` are all `_fake_*` / `_noop_*` double functions defined inline.

### `TestCommandCreate::test_create_persists_session` [LINE 244]
**Violation**: `_fake_form` — function name with `_fake_` prefix (inline def)
**Why**: `async def _fake_form(self, name, agent_urls, api_key=None)` is a locally-defined stub replacing the production `form_team`. This is named with the `_fake_` prefix convention the task specifically prohibits.

### `TestCommandCreate::test_create_persists_session` [LINE 247]
**Violation**: `_noop_aenter` — function name with `_noop_` prefix (functionally a stub/dummy)
**Why**: `async def _noop_aenter(self): return self` replaces `__aenter__` entirely, meaning the coordinator never goes through real async context management. The real `__aenter__` may do meaningful setup that is bypassed.

### `TestCommandCreate::test_create_persists_session` [LINE 250]
**Violation**: `_noop_aexit` — function name with `_noop_` prefix (functionally a dummy)
**Why**: `async def _noop_aexit(self, *_): pass` replaces `__aexit__`, bypassing any real teardown or cleanup logic in `TeamCoordinator`.

### `TestCommandDissolve::test_dissolve_removes_json` [LINE 301]
**Violation**: `patch.object` on `TeamCoordinator.dissolve_team`, `__aenter__`, `__aexit__`; `_fake_*`/`_noop_*` helpers
**Why**: `patch.object(TeamCoordinator, "dissolve_team", _fake_dissolve)` replaces the real dissolution logic with a no-op coroutine. The test verifies only that the CLI deletes the JSON file after the coordinator "returns", but never exercises real A2A teardown. The real `dissolve_team` may signal agents, await shutdown confirmation, or perform network calls — all bypassed.

### `TestCommandDissolve::test_dissolve_removes_json` [LINE 302]
**Violation**: `_fake_dissolve` — function name with `_fake_` prefix (inline def)
**Why**: `async def _fake_dissolve(self): pass` is a stub replacing `TeamCoordinator.dissolve_team`.

### `TestCommandAssign::test_assign_calls_dispatch_parallel` [LINE 349]
**Violation**: `patch.object` on `TeamCoordinator.dispatch_parallel`, `__aenter__`, `__aexit__`
**Why**: `patch.object(TeamCoordinator, "dispatch_parallel", _fake_dispatch)` replaces the actual parallel dispatch implementation with a function that returns a hardcoded `A2ATask`. This means the test never exercises real HTTP dispatch, task polling, or error handling — only the CLI's output formatting is tested.

### `TestCommandAssign::test_assign_calls_dispatch_parallel` [LINE 348]
**Violation**: `_fake_dispatch` inline — name with `_fake_` prefix
**Why**: `async def _fake_dispatch(self, assignments): return {"echo-agent": fake_task}` returns a canned task dict, so the test assertion `assert "completed" in out` is trivially true (the fake already produces a completed task).

### `TestCommandBroadcast::test_broadcast_dispatches_to_all` [LINE 391]
**Violation**: `patch.object` on `TeamCoordinator.dispatch_parallel`, `__aenter__`, `__aexit__`; `_fake_dispatch` inline
**Why**: Same pattern as `TestCommandAssign` — `dispatch_parallel` is replaced entirely with a function returning a canned completed task. The assertion that `"completed" in out` is trivially true because `_fake_dispatch` hard-codes `TaskState.completed`. The test cannot detect regressions in the actual broadcast path.

---

## `.vaultspec/lib/tests/cli/test_docs_cli.py`

### `TestLoggingDispatch::test_verbose_configures_info` [LINE 458]
**Violation**: `monkeypatch.setattr` used to replace `docs.configure_logging` and `docs.handle_audit` with lambdas
**Why**: `monkeypatch.setattr(docs, "configure_logging", lambda **kw: calls.append(kw))` replaces the real `configure_logging` function with a lambda that records calls. `monkeypatch.setattr(docs, "handle_audit", lambda *_args: None)` prevents the audit handler from running at all. The test verifies only that `main()` calls `configure_logging` with certain kwargs — but since `handle_audit` is also stubbed, the actual audit pipeline is never invoked, making this a mock-of-dispatch test, not a real behavior test.

### `TestLoggingDispatch::test_debug_configures_debug` [LINE 469]
**Violation**: Same pattern as above — `monkeypatch.setattr` replaces both `configure_logging` and `handle_audit` with stubs
**Why**: `monkeypatch.setattr(docs, "configure_logging", lambda **kw: calls.append(kw))` and `monkeypatch.setattr(docs, "handle_audit", lambda *_args: None)` mean the test never runs real logging configuration nor real audit logic. It verifies the if/elif dispatch logic in `main()` but cannot catch bugs in the actual `configure_logging` implementation.

### `TestLoggingDispatch::test_default_configures_no_args` [LINE 480]
**Violation**: Same pattern — `configure_logging` and `handle_audit` replaced via `monkeypatch.setattr`
**Why**: `monkeypatch.setattr(docs, "configure_logging", lambda **kw: calls.append(kw))` replaces the real function. The assertion `assert calls == [{}]` is trivially self-fulfilling — the lambda always records what was passed, and the test only checks that a call was made with empty kwargs. It cannot catch bugs in the actual logging configuration logic.

---

## `.vaultspec/lib/tests/e2e/test_provider_parity.py`

### `_seed_gemini_version_cache` fixture [LINE 39]
**Violation** (borderline): Directly mutates module-level private state (`gmod._cached_version`, `gmod._which_fn`) to bypass `check_version()` I/O
**Why**: The `autouse=True` fixture sets `gmod._cached_version = (0, 27, 0)` and `gmod._which_fn = lambda _name: "/usr/bin/gemini"` to pre-seed internal state, bypassing the real version detection. This is not a `MagicMock`/`patch` call, but it is a direct replacement of private module state (`_which_fn`) with a lambda stub. The test then asserts on `ProcessSpec` outputs without ever checking that Gemini is actually installed or at the right version — the version check always passes because it's faked. If `check_version()` logic changes, this fixture will silently mask the breakage. Flagged as borderline because the comment states "no mocks needed — cache pre-seeded" but the which_fn replacement is functionally equivalent to a stub.

---

## Files with ZERO violations

All tests in these files use real production code, real filesystem I/O, and
contain no mock/patch usage, `_fake_*`/`_mock_*` names, skip markers, or
trivially self-fulfilling assertions:

- `.vaultspec/lib/tests/cli/conftest.py` — clean
- `.vaultspec/lib/tests/cli/test_sync_parse.py` — clean
- `.vaultspec/lib/tests/cli/test_sync_collect.py` — clean
- `.vaultspec/lib/tests/cli/test_sync_operations.py` — clean
- `.vaultspec/lib/tests/cli/test_sync_incremental.py` — clean
- `.vaultspec/lib/tests/cli/test_integration.py` — clean
- `.vaultspec/lib/tests/e2e/test_claude.py` — clean (skipif on CLI availability is conditional, not unconditional skip)
- `.vaultspec/lib/tests/e2e/test_gemini.py` — clean (same)
- `.vaultspec/lib/tests/e2e/test_full_cycle.py` — clean (same)
- `.vaultspec/lib/tests/e2e/test_mcp_e2e.py` — clean (same)
- `.vaultspec/lib/tests/e2e/test_provider_parity.py` — 1 borderline violation noted above
- `.vaultspec/lib/src/rag/tests/conftest.py` — clean
- `.vaultspec/lib/src/rag/tests/test_store.py` — clean
- `.vaultspec/lib/src/rag/tests/test_query.py` — clean
- `.vaultspec/lib/src/rag/tests/test_search_unit.py` — clean
- `.vaultspec/lib/src/rag/tests/test_embeddings.py` — clean
- `.vaultspec/lib/src/rag/tests/test_indexer_unit.py` — clean
- `.vaultspec/lib/src/core/tests/test_config.py` — clean (monkeypatch used only for env vars, not to replace production functions)
- `.vaultspec/lib/src/core/tests/test_workspace.py` — clean
- `.vaultspec/lib/src/vault/tests/test_types.py` — clean
- `.vaultspec/lib/src/vault/tests/test_links.py` — clean
- `.vaultspec/lib/src/vault/tests/test_hydration.py` — clean
- `.vaultspec/lib/src/vault/tests/test_scanner.py` — clean
- `.vaultspec/lib/src/vault/tests/test_core.py` — clean
- `.vaultspec/lib/src/hooks/tests/test_hooks.py` — clean

---

## Notes on Conditional `skipif` Usage

Several e2e tests use `@pytest.mark.skipif(not _has_claude_cli, reason=...)` and
`@pytest.mark.skipif(not _has_gemini_cli, reason=...)`. These are **not** flagged
as violations because:
1. They guard against missing external dependencies (the actual CLI binary), not internal code.
2. The condition is determined at import time using `shutil.which()`.
3. When the CLI is present, the full real code path runs — no mocking of the CLI dispatch.

This is an acceptable pattern for external-dependency integration tests.

---

## Violation Count by Category

| Category | Count |
|----------|-------|
| `patch.object` usage | 6 |
| `_fake_*` / `_noop_*` inline function names | 5 |
| `monkeypatch.setattr` replacing production functions | 3 |
| Module private state mutation (borderline) | 1 |
| `MagicMock` / `AsyncMock` imports | 1 (imported in test_team_cli.py at line 16 but not directly used; the import is present and flags the file) |

**Note**: `from unittest.mock import AsyncMock, MagicMock, patch` is imported at line 16 of `test_team_cli.py`. `MagicMock` and `AsyncMock` are imported but the violations are via `patch.object` and inline async def stubs. The import itself is flagged because it signals mock infrastructure is present.
