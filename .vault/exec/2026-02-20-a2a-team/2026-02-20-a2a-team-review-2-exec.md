---
tags:
  - "#exec"
  - "#a2a-team"
date: "2026-02-20"
related:
  - "[[2026-02-20-a2a-team-p1-plan]]"
  - "[[2026-02-20-a2a-team-adr]]"
  - "[[2026-02-20-a2a-team-review]]"
---
# `a2a-team` code review (re-review)

**Status:** `PASS`

## Audit Context

- **Plan:** `[[2026-02-20-a2a-team-p1-plan]]`
- **ADR:** `[[2026-02-20-a2a-team-adr]]`
- **Previous Review:** `[[2026-02-20-a2a-team-review]]` (status: REVISION REQUIRED)
- **Scope:**
  - `.vaultspec/lib/src/orchestration/team.py` (530 lines)
  - `.vaultspec/lib/src/orchestration/tests/test_team.py` (541 lines)
  - `.vaultspec/lib/scripts/team.py` (491 lines)
  - `.vaultspec/lib/tests/cli/test_team_cli.py` (441 lines)
  - `.vaultspec/lib/src/protocol/a2a/discovery.py` (123 lines, modified)
  - `pyproject.toml` (marker registration)

## Previous HIGH Findings — Resolution Verification

### HIGH #1: Member status leak in `dispatch_parallel` — RESOLVED

**Previous Issue:** Failed members in `dispatch_parallel` remained stuck at `MemberStatus.WORKING` permanently. The error branch executed `continue` without resetting the member's status.

**Fix Applied** (`team.py:399-410`):

```python
agent_names = list(assignments.keys())
coros = [_send_one(name, text) for name, text in assignments.items()]
outcomes = await asyncio.gather(*coros, return_exceptions=True)

for i, item in enumerate(outcomes):
    if isinstance(item, BaseException):
        logger.error("dispatch_parallel agent error: %s", item)
        self._session_member(agent_names[i]).status = MemberStatus.IDLE
        continue
    agent_name, task = item
    results[agent_name] = task
    self._session_member(agent_name).status = MemberStatus.IDLE
```

**Verification:** The fix is correct. The `agent_names` list (line 399) and the `coros` list (line 400) are both derived from `assignments.items()`, which guarantees identical iteration order in Python 3.7+. The index `i` from `enumerate(outcomes)` correctly maps to `agent_names[i]`, resolving the agent name for the failed coroutine. Both the success path (line 410) and the error path (line 406) now transition the member to `IDLE`. The status lifecycle is now WORKING -> IDLE for all outcomes.

**No new bugs introduced:** The fix does not alter the happy path. It only adds one line (`agent_names = list(...)`) and one status-reset line in the error branch. No side effects.

### HIGH #2: False-positive timeout test — RESOLVED

**Previous Issue:** `test_dispatch_timeout_degrades_gracefully` defined a `SlowExecutor` but never registered it as a team member. The test only dispatched to `echo-fast`, passing trivially without exercising any degradation behavior.

**Fix Applied** (`test_team.py:390-419`):

The test was renamed to `test_dispatch_parallel_degrades_gracefully_on_failure` and fully rewritten:
- Defines `FailingExecutor` that raises `RuntimeError("simulated agent failure")` immediately on `execute()`.
- Registers it as `broken-agent` on port 19951 via `_build_coordinator_with_apps`, alongside `echo-fast` on port 19950.
- Dispatches to both agents: `{"echo-fast": "quick task", "broken-agent": "this will fail"}`.
- Asserts three conditions:
  - `"echo-fast" in results` -- the healthy agent's result is present.
  - `"broken-agent" not in results` -- the failed agent's result is omitted.
  - `coordinator.session.members["broken-agent"].status == MemberStatus.IDLE` -- the failed member's status was properly reset (directly proves HIGH #1 fix is observable).

**Verification:** This test genuinely exercises the degradation path. The `FailingExecutor` is registered as a full team member and dispatched to. The `asyncio.gather(return_exceptions=True)` captures the `RuntimeError` as a `BaseException` in the outcomes list, triggering the error branch of `dispatch_parallel`. The third assertion (`status == IDLE`) is the observable proof that the HIGH #1 status-reset fix is working. This is no longer a false positive.

## ADR Decision Compliance

| Decision | Requirement | Status |
|---|---|---|
| 1 | `TeamCoordinator` in `orchestration/team.py`, not in `protocol/a2a/` | PASS |
| 2 | `team_id == context_id` (single UUID); name in `metadata["team_name"]` | PASS |
| 3 | `discovery.py` uses `/.well-known/agent-card.json` | PASS |
| 4 | `lib/scripts/team.py` follows `subagent.py` CLI conventions | PASS |
| 5 | `relay_output()` sends `reference_task_ids=[src_task.id]` + two `TextPart` entries | PASS |
| 6 | Unauthenticated by default; `--api-key` sets `X-API-Key` via `__aenter__` / `_ensure_http_client` | PASS |

All six ADR decisions remain correctly implemented. No drift from the previous review.

## Findings

### Critical / High (Must Fix)

None. Both previous HIGH findings are resolved.

### Medium / Low (Carried Forward)

The following findings from the initial review remain present and unchanged. They were not in scope for the HIGH-fix revision cycle and do not block merge.

- **[MEDIUM]** `orchestration/team.py:441` (collect_results polling): Fixed 100ms polling interval with no backoff. For long-running tasks (up to 300s timeout), this issues ~3000 `get_task` requests per agent. Exponential backoff (0.1s doubling to 5s cap) would reduce load by ~90%.

- **[MEDIUM]** `orchestration/team.py:282-288` (form_team API key override): When `api_key` is passed to `form_team()` and differs from the constructor key, the HTTP client is torn down and recreated, but `self._clients` is not cleared. Stale `A2AClient` instances could reference the old HTTP client. In practice this is low-risk because `form_team()` is called before any dispatches, but document the behavior or clear `self._clients`.

- **[MEDIUM]** `orchestration/team.py:245` (_dispatch_one error detection): Uses `hasattr(result, "error")` instead of `isinstance(result, JSONRPCErrorResponse)`. Fragile if the SDK adds an `error` attribute to success responses in a future version.

- **[MEDIUM]** `scripts/team.py:124,299` (_restore_coordinator and _get_client): Private attribute access `coordinator._session` and `coordinator._get_client` via `# noqa: SLF001`. Consider adding public `restore_session()` method.

- **[MEDIUM]** `scripts/team.py:174,235,263,317,349` (event loop management): All async command handlers use `asyncio.new_event_loop()` + `asyncio.set_event_loop()` instead of `asyncio.run()`. The current approach risks leaving a global event loop set on error between `set_event_loop` and `loop.close()`.

- **[MEDIUM]** `scripts/team.py:306` (relay mode error handling): `resp.root.result` accessed without error checking. If the `get_task` response is a `JSONRPCErrorResponse`, this raises `AttributeError`.

- **[MEDIUM]** `orchestration/tests/test_team.py:90` (private access in test helper): `_build_coordinator_with_apps` sets `coordinator._http_client` directly. Necessary for test injection but a dedicated factory method would be cleaner.

- **[LOW]** `scripts/team.py:162,223,254,283,342` (ResourceWarning suppression): `warnings.simplefilter("ignore", ResourceWarning)` called globally in multiple command functions. A `warnings.catch_warnings()` context manager would limit the scope.

- **[LOW]** `tests/cli/test_team_cli.py:48-49`: `if TYPE_CHECKING: pass` is dead code.

- **[LOW]** `pyproject.toml:85`: Phase 1-4 unit tests do not carry `@pytest.mark.team`; only Phase 5 integration tests do. Running `pytest -m team` would skip unit tests. Consider applying the marker module-wide.

## Key Quality Criteria Verification

| Criterion | Verdict |
|---|---|
| HIGH #1 fix: error branch resets status to IDLE | PASS -- `team.py:406` sets `MemberStatus.IDLE` for failed members |
| HIGH #1 fix: agent name resolution is order-safe | PASS -- `agent_names` and `coros` derive from same `assignments.items()` call |
| HIGH #2 fix: test registers failing agent as team member | PASS -- `FailingExecutor` registered on port 19951 in `_build_coordinator_with_apps` |
| HIGH #2 fix: test asserts status reset (no false positive) | PASS -- line 417 asserts `broken-agent` status == `MemberStatus.IDLE` |
| Tests assert specific observable values | PASS -- tests check `task.context_id`, `task.status.state.value`, `captured_ref_ids`, and `member.status` explicitly |
| Decision 2 proof: test asserts `task.context_id == session.team_id` | PASS -- `test_dispatch_parallel_fan_out` (line 190) and `test_two_agent_parallel_dispatch` (line 458) |
| Decision 5 proof: test inspects outbound `reference_task_ids` | PASS -- `test_relay_output_injects_reference_task_id` (line 279) and `test_relay_chain` (line 531) |
| No `# type: ignore` without justification | PASS -- zero occurrences |
| No bare `except: pass` | PASS -- all handlers use `except Exception as exc:` with logging and `# noqa: BLE001` |
| dispatch_parallel: WORKING -> IDLE on both success and failure | PASS -- lines 406 (error) and 410 (success) both set IDLE |

## Safety Audit

| Category | Status | Notes |
|---|---|---|
| Panic Prevention | N/A | Python -- no `.unwrap()` / `panic!` equivalents |
| Exception Safety | PASS | All exception handlers catch `Exception`, log, and degrade. No bare `except:` |
| Resource Cleanup | PASS | `__aexit__` closes httpx client. `dissolve_team` clears in-flight state |
| Concurrency Safety | PASS | `asyncio.gather` with `return_exceptions=True` prevents one coroutine from crashing the group. `asyncio.timeout` guards the polling loop |
| State Consistency | PASS | `dispatch_parallel` now correctly resets all member statuses on both success and failure paths (previously HIGH -- now resolved) |

## Recommendations

1. **[Should Fix, Future]** Add exponential backoff to `collect_results` polling (MEDIUM, carried forward).
2. **[Should Fix, Future]** Add error checking to `command_message` relay mode `resp.root.result` access (MEDIUM, carried forward).
3. **[Should Fix, Future]** Replace `asyncio.new_event_loop()` / `set_event_loop()` with `asyncio.run()` in CLI command handlers (MEDIUM, carried forward).
4. **[Optional, Future]** Add a public `TeamCoordinator.restore_session()` method to eliminate private attribute access from `scripts/team.py` (MEDIUM, carried forward).
5. **[Optional, Future]** Clear `self._clients` when HTTP client is recreated in `form_team()` API key override path (MEDIUM, carried forward).

## Notes

- Both HIGH findings from the initial review are correctly resolved. The fixes are minimal, targeted, and do not introduce new issues.
- The `dispatch_parallel` status lifecycle is now sound end-to-end: WORKING (line 388) -> IDLE on success (line 410) or IDLE on error (line 406). There are no paths that leave a member stuck in WORKING.
- The replacement test (`test_dispatch_parallel_degrades_gracefully_on_failure`) is materially better than the old `test_dispatch_timeout_degrades_gracefully`: it uses a `FailingExecutor` that raises immediately (deterministic, no timing sensitivity), registers it as an actual team member, and asserts all three expected outcomes (success present, failure omitted, status reset).
- All 6 MEDIUM and 3 LOW findings from the initial review are carried forward. None are blocking; all are improvements for a future iteration.
- Total test count remains 13 in `test_team.py` + 15 in `test_team_cli.py` = 28 tests.
