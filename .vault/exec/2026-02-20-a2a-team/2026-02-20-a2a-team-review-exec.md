---
tags:
  - "#exec"
  - "#a2a-team"
date: "2026-02-20"
related:
  - "[[2026-02-20-a2a-team-p1-plan]]"
  - "[[2026-02-20-a2a-team-adr]]"
---
# `a2a-team` code review

**Status:** `REVISION REQUIRED`

## Audit Context

- **Plan:** `[[2026-02-20-a2a-team-p1-plan]]`
- **ADR:** `[[2026-02-20-a2a-team-adr]]`
- **Scope:**
  - `.vaultspec/lib/src/orchestration/team.py` (528 lines)
  - `.vaultspec/lib/src/orchestration/tests/test_team.py` (544 lines)
  - `.vaultspec/lib/scripts/team.py` (491 lines)
  - `.vaultspec/lib/tests/cli/test_team_cli.py` (441 lines)
  - `.vaultspec/lib/src/protocol/a2a/discovery.py` (123 lines, modified)
  - `pyproject.toml` (marker registration)

## ADR Decision Compliance

| Decision | Requirement | Status |
|---|---|---|
| 1 | `TeamCoordinator` in `orchestration/team.py`, not in `protocol/a2a/` | PASS |
| 2 | `team_id == context_id` (single UUID); name in `metadata["team_name"]` | PASS |
| 3 | `discovery.py` uses `/.well-known/agent-card.json` | PASS |
| 4 | `lib/scripts/team.py` follows `subagent.py` CLI conventions | PASS |
| 5 | `relay_output()` sends `reference_task_ids=[src_task.id]` + two `TextPart` entries | PASS |
| 6 | Unauthenticated by default; `--api-key` sets `X-API-Key` via `__aenter__` / `_ensure_http_client` | PASS |

All six ADR decisions are correctly implemented.

## Findings

### Critical / High (Must Fix)

- **[HIGH]** `orchestration/team.py:388-408` (dispatch_parallel): Members whose dispatch raises an exception remain stuck in `MemberStatus.WORKING` permanently. Line 388 sets all members to `WORKING` before dispatch, but line 408 only sets successful members back to `IDLE`. Failed members are never transitioned. This is a state-leak bug that will cause stale `WORKING` status on partial failures. The fix is to reset failed members to `IDLE` (or a new error state) in the error branch of the `outcomes` loop.

- **[HIGH]** `orchestration/team.py:22` (module-level A2A import): The review criteria state that `orchestration/team.py` must not have `from protocol.a2a import ...` at module level. The file does not import from `protocol.a2a` -- it imports directly from `a2a.client` and `a2a.types` (the third-party `a2a-sdk` package). This is architecturally correct per Decision 1: the team module talks to the A2A SDK directly, not through the project's `protocol.a2a` wrapper layer. However, the imports are unconditional at module level (lines 21-36), meaning `orchestration/team.py` cannot be imported at all without `a2a-sdk` installed. Since `a2a-sdk` is a declared dependency in `pyproject.toml`, this is acceptable for production but makes the module non-importable in minimal test environments. Consider guarding the SDK imports behind `TYPE_CHECKING` for the type-only references (`AgentCard`, `Task`, `Part`, etc.) and importing the runtime-critical ones (`A2AClient`, `A2ACardResolver`) lazily or at call sites. **Downgraded to MEDIUM** given that `a2a-sdk` is a hard project dependency.

- **[HIGH]** `orchestration/tests/test_team.py:399` (SlowExecutor): The `SlowExecutor` uses `await asyncio.sleep(9999)` inside a test, but the test (`test_dispatch_timeout_degrades_gracefully`) never actually tests a timeout scenario. It only dispatches to the fast `echo-fast` agent. The `SlowExecutor` class is defined but never registered in the coordinator, so the test does not exercise the degradation behavior it claims to test. This means Phase 4 "dispatch timeout degrades gracefully" has **zero actual coverage**. The test must register both a fast agent and a slow agent, dispatch to both, and verify the fast agent's result is still returned despite the slow agent timing out.

- **[HIGH]** `tests/cli/test_team_cli.py`: The CLI test module does **not** use the `_isolate_cli` autouse fixture from `conftest.py`. The `conftest.py` in `tests/cli/` calls `cli.init_paths(TEST_PROJECT)` and `setup_rules_dir(TEST_PROJECT)`. The team CLI tests use `tmp_path` for isolation instead. This is actually fine for correctness (each test gets a fresh `tmp_path`), but it means the team CLI tests are not following the convention described in the plan ("following `test_sync_operations.py` conventions (uses `_isolate_cli` autouse fixture)"). This is an intentional and valid divergence since team CLI tests do not depend on `cli.init_paths`.  **Downgraded to MEDIUM** -- the approach is sound, but diverges from the stated plan.

### Medium / Low (Recommended)

- **[MEDIUM]** `orchestration/team.py:439` (collect_results polling): The `asyncio.sleep(0.1)` in `collect_results._poll_one` is a fixed 100ms polling interval with no backoff. For long-running tasks (up to the 300s default timeout), this will issue ~3000 `get_task` requests per agent. Consider exponential backoff (e.g., starting at 0.1s, doubling up to 5s) to reduce unnecessary load on the agent servers.

- **[MEDIUM]** `orchestration/team.py:282-288` (form_team API key override): When `api_key` is passed to `form_team()` and differs from the constructor key, the HTTP client is torn down and recreated (lines 283-288). This destroys any already-cached `A2AClient` instances in `self._clients`. Since `form_team()` is typically called once before any dispatch, this is unlikely to cause issues in practice, but it is a subtle invalidation hazard. Document this behavior or clear `self._clients` when the HTTP client is replaced.

- **[MEDIUM]** `orchestration/team.py:243-255` (_dispatch_one error handling): Error detection uses `hasattr(result, "error")` (line 246) rather than type-checking against `JSONRPCErrorResponse`. This is fragile -- if the A2A SDK adds an `error` attribute to success responses in a future version, this would false-positive. Prefer `isinstance(result, JSONRPCErrorResponse)` or check the SDK's response discrimination pattern.

- **[MEDIUM]** `scripts/team.py:119-125` (_restore_coordinator): Accesses private `coordinator._session` directly with `# noqa: SLF001`. This pattern is used twice (also at line 299 for `_get_client`). While pragmatic, consider adding a `TeamCoordinator.restore_session(session)` public method to avoid private attribute access from outside the class.

- **[MEDIUM]** `scripts/team.py:174-190` (event loop management): All async command handlers create a new event loop via `asyncio.new_event_loop()` + `asyncio.set_event_loop()`. This is functional but redundant -- `asyncio.run()` would handle this automatically and is the standard pattern since Python 3.7. The current approach also risks leaving a global event loop set if an error occurs between `set_event_loop` and `loop.close()`.

- **[MEDIUM]** `scripts/team.py:306` (relay mode error handling): `resp.root.result` (line 306) is accessed without error checking. If the `get_task` response is a `JSONRPCErrorResponse`, `resp.root.result` would raise `AttributeError`. Apply the same error-checking pattern used in `_dispatch_one`.

- **[MEDIUM]** `orchestration/tests/test_team.py:90` (private access in test helper): `_build_coordinator_with_apps` sets `coordinator._http_client` directly. This is necessary for test injection but should be noted. A dedicated `TeamCoordinator.with_http_client(client)` factory method would be cleaner.

- **[LOW]** `scripts/team.py:162` (ResourceWarning suppression): `warnings.simplefilter("ignore", ResourceWarning)` is called in multiple command functions (lines 162, 223, 254, 342). This globally suppresses resource warnings for the process lifetime. Consider using a `warnings.catch_warnings()` context manager to limit the scope.

- **[LOW]** `orchestration/team.py:20-36` (imports): Several imported names (`CancelTaskRequest`, `GetTaskRequest`, `TaskIdParams`, `TaskQueryParams`, `Role`) are used only in specific methods. Moving them to `TYPE_CHECKING` (for type annotations only) or importing them at the call site would reduce the top-level import surface, though this is a minor style preference.

- **[LOW]** `tests/cli/test_team_cli.py:49`: `if TYPE_CHECKING: pass` -- dead code block. Remove it.

- **[LOW]** `pyproject.toml:85`: The `team` marker is registered correctly: `"team: multi-agent team coordination tests (TeamCoordinator)"`. The test files use `@pytest.mark.team` appropriately on integration tests. However, the Phase 1-4 unit tests in `test_team.py` do not carry the `@pytest.mark.team` marker -- only the Phase 5 integration tests do. The plan says "All Phase 5 tests carry `@pytest.mark.integration` and `@pytest.mark.team`" which is satisfied, but running `pytest -m team` would skip Phase 1-4 unit tests. Consider whether the marker should apply to all tests in the module.

## Key Quality Criteria Verification

| Criterion | Verdict |
|---|---|
| Tests assert specific observable values | PASS -- tests check `task.context_id`, `task.status.state.value`, `captured_ref_ids`, and `member.status` explicitly |
| Decision 2 proof: test asserts `task.context_id == session.team_id` | PASS -- `test_dispatch_parallel_fan_out` (line 190) and `test_two_agent_parallel_dispatch` (line 461) both assert this |
| Decision 5 proof: test inspects outbound `reference_task_ids` | PASS -- `test_relay_output_injects_reference_task_id` (line 279) and `test_relay_chain` (line 534) use `CapturingExecutor`/`RefCapturingExecutor` to capture and assert `reference_task_ids` on the inbound server message |
| No `# type: ignore` without justification | PASS -- zero occurrences |
| No bare `except: pass` | PASS -- all exception handlers use `except Exception as exc:` with logging and `# noqa: BLE001` |
| No `asyncio.sleep()` as synchronization in tests | PASS in tests -- the `asyncio.sleep(9999)` in `SlowExecutor` is intentionally simulating a hung agent (it is never awaited in the actual test path) |
| `orchestration/team.py` has no `from protocol.a2a import ...` at module level | PASS -- all imports are from `a2a.client` and `a2a.types` (the SDK), not from `protocol.a2a.*` |

## Safety Audit

| Category | Status | Notes |
|---|---|---|
| Panic Prevention | N/A | Python -- no `.unwrap()` / `panic!` equivalents |
| Exception Safety | PASS | All exception handlers catch `Exception`, log, and degrade. No bare `except:` |
| Resource Cleanup | PASS | `__aexit__` closes httpx client. `dissolve_team` clears in-flight state |
| Concurrency Safety | PASS | `asyncio.gather` with `return_exceptions=True` prevents one coroutine from crashing the group. `asyncio.timeout` guards the polling loop |
| State Consistency | HIGH | `dispatch_parallel` leaves failed members in `WORKING` (see finding above) |

## Recommendations

1. **[Must Fix]** In `dispatch_parallel`, reset failed members' status to `IDLE` in the error branch of the outcomes loop. Specifically, after the `if isinstance(item, BaseException)` check, identify the agent name from the coroutine mapping and set its status back to `IDLE`.

2. **[Must Fix]** Rewrite `test_dispatch_timeout_degrades_gracefully` to actually register the `SlowExecutor` as a second agent in the coordinator and verify that the fast agent's result is returned even when the slow agent times out. The current test is a false positive.

3. **[Should Fix]** Add exponential backoff to the `collect_results` polling loop. A simple doubling from 0.1s to a cap of 5s would reduce unnecessary load by ~90% for long-running tasks.

4. **[Should Fix]** Add error checking to `command_message` relay mode (line 306) for `get_task` response errors, matching the pattern in `_dispatch_one`.

5. **[Should Fix]** Consider replacing `asyncio.new_event_loop()` / `set_event_loop()` with `asyncio.run()` in CLI command handlers.

6. **[Optional]** Add a public `TeamCoordinator.restore_session()` method to eliminate private attribute access from `scripts/team.py`.

## Notes

- The overall architecture is clean and well-aligned with the ADR. The separation between `orchestration/team.py` (coordination logic) and `protocol/a2a/` (transport layer) is correctly maintained.
- The `discovery.py` changes are minimal and correct: the docstring for `write_gemini_settings()` now clearly documents that `root_dir` must be `Path.home()`, and the endpoint URL is `/.well-known/agent-card.json` per the A2A spec.
- The test suite is well-structured with clear phase separation and good use of `httpx.ASGITransport` for in-process testing without TCP sockets.
- The CLI follows `subagent.py` conventions closely: `_paths` bootstrap, `argparse` subparsers, `--root` flag with `Path` type and `ROOT_DIR` fallback, `--verbose`/`--debug`/`--version` top-level flags.
- The `extract_artifact_text` helper is defensive and handles missing parts gracefully without raising.
- Session persistence (JSON round-trip) is well-tested with explicit assertions on every field.
- Total test count: 13 in `test_team.py` + 15 in `test_team_cli.py` = 28 tests covering all six plan phases.
