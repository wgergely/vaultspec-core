---
tags:
  - "#plan"
  - "#a2a-team"
date: "2026-02-20"
related:
  - "[[2026-02-20-a2a-team-adr]]"
  - "[[2026-02-20-a2a-team-synthesis-research]]"
---
# `a2a-team` Phase 1 Plan — Multi-Agent Team Coordination Layer

Build the N-agent team coordination layer on top of the existing A2A bilateral
infrastructure (ADR 2026-02-15, Phases 1–5 complete). The gap is not the bilateral
plumbing — it is the `TeamCoordinator` and `TeamSession` orchestration layer, the
`team.py` CLI, liveness monitoring, integration tests, and Gemini `@a2a` client
validation. All six decisions from [[2026-02-20-a2a-team-adr]] are binding.

## Proposed Changes

The feature adds exactly four new files and modifies two existing files, per the ADR:

New files:
- `.vaultspec/lib/src/orchestration/team.py` — `TeamCoordinator`, `TeamSession`, `TeamMember`, `TeamStatus`, `MemberStatus`
- `.vaultspec/lib/src/orchestration/tests/test_team.py` — unit tests for the orchestration layer
- `.vaultspec/lib/scripts/team.py` — standalone CLI entry point following `subagent.py`/`vault.py` conventions exactly
- `.vaultspec/lib/tests/cli/test_team_cli.py` — functional CLI tests

Modified files:
- `pyproject.toml` — register `@pytest.mark.team` marker; optionally a `team` console script entry point
- `.vaultspec/lib/src/protocol/a2a/discovery.py` — confirm `write_gemini_settings()` sets `experimental.enableAgents: true` (already present; verify correctness for `@a2a` client use case)

Unchanged files (per ADR Decision 1): `task_engine.py`, `subagent.py`,
`executors/claude_executor.py`, `executors/gemini_executor.py`, `server.py`,
`protocol/acp/claude_bridge.py`, `subagent_server/server.py`.

The coordinator operates above the A2A transport layer. It uses `a2a-sdk`'s
`A2AClient` and `A2ACardResolver` directly — the same primitives used in
`test_french_novel_relay.py` — to fan out tasks and collect results. The
`contextId` equals the `team_id` UUID (Decision 2). Security is unauthenticated
by default; `--api-key` opt-in adds `X-API-Key` to outbound requests (Decision 6).

## Tasks

- `Phase 1` — TeamSession model and TeamCoordinator skeleton
    1. Create `.vaultspec/lib/src/orchestration/team.py` with `MemberStatus` (StrEnum: spawning|idle|working|shutdown_requested|terminated), `TeamStatus` (StrEnum: forming|active|dissolving|dissolved), `TeamMember` dataclass (name, url, card: AgentCard, status: MemberStatus), `TeamSession` dataclass (team_id, name, context_id, members: dict[str, TeamMember], status: TeamStatus, created_at: float), and `TeamCoordinator` class skeleton with `__init__` accepting optional api_key.
    2. Implement `TeamCoordinator.form_team(name: str, agent_urls: list[str], api_key: str | None) -> TeamSession`. This method generates a single UUID for `team_id` and `context_id` (they are the same value per Decision 2), fetches each agent's card via `A2ACardResolver` to populate `TeamMember.card`, sets session status to `ACTIVE`, and stores the session internally.
    3. Implement `TeamCoordinator.dissolve_team() -> None`. Cancels any in-flight `A2AClient` HTTP connections, sets session status to `DISSOLVED`, and marks all members as `TERMINATED`. Must be idempotent — calling on an already-dissolved team is a no-op.
    4. Create `.vaultspec/lib/src/orchestration/tests/test_team.py` with unit tests for Phase 1: `test_form_team_sets_context_id_equal_to_team_id`, `test_team_status_transitions`, `test_dissolve_is_idempotent`, and `test_member_status_on_form`. Use `EchoExecutor`-backed `httpx.ASGITransport` apps (same pattern as `conftest.py` in `protocol/a2a/tests/`) to serve mock agents in-process — no real TCP sockets required.

- `Phase 2` — Parallel dispatch, fan-in, and relay
    1. Implement `TeamCoordinator.dispatch_parallel(assignments: dict[str, str]) -> dict[str, Task]`. Fan out via `asyncio.gather` over one `A2AClient.send_message()` call per agent. Each outbound `Message` carries `context_id=self.session.team_id` and `metadata={"team_name": self.session.name}` (Decision 2). Members are set to status `WORKING` before dispatch; `IDLE` on completion. Returns a dict mapping agent name to the returned `a2a.types.Task`.
    2. Implement `TeamCoordinator.collect_results() -> dict[str, str]`. Polls `A2AClient.get_task()` for each in-progress task until all reach a terminal state (`completed`, `canceled`, `failed`). Extracts text via a module-level helper `extract_artifact_text(task: Task) -> str` that navigates `task.status.message.parts[0].text`. Apply an `asyncio.timeout` guard (configurable, default 300s) to avoid hanging indefinitely.
    3. Implement `TeamCoordinator.relay_output(src_task: Task, dst_agent: str, instructions: str) -> Task`. Fetches `src_task`'s completed text via `extract_artifact_text`, then calls `_dispatch_one` (private helper) sending a `Message` with `reference_task_ids=[src_task.id]` and two `TextPart` entries: the source output and the instruction (Decision 5). Returns the resulting `Task` for the destination agent.
    4. Extend `test_team.py` with Phase 2 coverage: `test_dispatch_parallel_fan_out`, `test_collect_results_all_complete`, `test_relay_output_injects_reference_task_id`, and `test_dispatch_parallel_partial_failure`. All use `EchoExecutor` / `PrefixExecutor` in-process apps. Verify that `contextId` on each dispatched message equals `session.team_id`.

- `Phase 3` — `team.py` CLI entry point
    1. Create `.vaultspec/lib/scripts/team.py` following `subagent.py` conventions exactly: `from _paths import ROOT_DIR`, `from _paths import _layout as _paths_layout`, `from core.workspace import resolve_workspace`, `argparse` subparsers (not typer/click), top-level `--root` (`type=Path`, `default=None`), `--content-dir`, `--verbose`/`-v`, `--debug`, `--version`/`-V`. No other top-level flags.
    2. Implement the `create` subcommand: `python team.py create --name NAME --agents agent1:port1[,agent2:port2,...] [--api-key KEY]`. Instantiates `TeamCoordinator`, calls `form_team()`, and prints `team_id` to stdout. Stores the active `TeamSession` state to a JSON file under `{root}/.vault/logs/teams/{name}.json` so that subsequent CLI invocations can reload it.
    3. Implement `status`, `list`, `assign`, `broadcast`, `message`, and `dissolve` subcommands. Each reloads the session JSON from `.vault/logs/teams/{name}.json`. `assign` calls `dispatch_parallel` with a single-agent mapping. `broadcast` calls `dispatch_parallel` with the same message text for all members. `message` calls `relay_output` if a `--from` agent is named, or `_dispatch_one` directly. `dissolve` calls `dissolve_team()` and removes the JSON file. `list` reads all files under `.vault/logs/teams/` and prints team names, IDs, and statuses. `--force` on dissolve skips confirmation.
    4. Create `.vaultspec/lib/tests/cli/test_team_cli.py` following `test_sync_operations.py` conventions (uses `_isolate_cli` autouse fixture). Test each subcommand against an in-process mock server. Verify `--root` propagation, `--api-key` passthrough, and JSON state persistence across invocations.

- `Phase 4` — Liveness monitoring and error handling
    1. Implement `TeamCoordinator.ping_agents() -> dict[str, bool]`. Issues `GET /.well-known/agent.json` to each member URL using the existing `A2ACardResolver` or a bare `httpx.AsyncClient` GET. Returns a dict of agent name → reachable bool. No authentication required for the ping endpoint (it is the public agent card endpoint). Updates member status to `IDLE` or leaves unchanged based on the response.
    2. Add timeout and retry logic to `dispatch_parallel`. Wrap each `asyncio.gather` entry with `asyncio.timeout`. On `TimeoutError` or `httpx.ConnectError`, set the member's task entry to a sentinel error string in `collect_results` output rather than raising. Phase 4 establishes that the coordinator degrades gracefully when one member is unreachable.
    3. Add `coordinated_shutdown` logic to `dissolve_team`: before marking members terminated, attempt to cancel any in-flight task via `A2AClient.cancel_task(task_id)` if the SDK exposes it; otherwise close the HTTP session. This is a best-effort cancel — timeouts during cancel are swallowed with a warning log.
    4. Extend `test_team.py` with Phase 4 coverage: `test_ping_agents_reachable`, `test_ping_agents_unreachable_returns_false`, `test_dispatch_timeout_degrades_gracefully`. Use `httpx.ASGITransport` for reachable agents and a non-existent URL for the unreachable case.

- `Phase 5` — Integration test suite
    1. Create a `TeamCoordinatorFixture` helper in `.vaultspec/lib/src/orchestration/tests/test_team.py` (or a shared conftest if appropriate) that: spawns two `EchoExecutor` ASGI apps on virtual ports via `httpx.ASGITransport`, instantiates `TeamCoordinator`, calls `form_team()`, and yields the coordinator for test use. Cleans up with `dissolve_team()` in teardown.
    2. Write `test_two_agent_parallel_dispatch_integration`: form a two-member team (one `EchoExecutor`, one `PrefixExecutor`), call `dispatch_parallel` with distinct tasks, assert both tasks reach `completed`, assert `contextId` matches `team_id` on both, and assert the two task IDs are distinct.
    3. Write `test_relay_chain_integration`: form a two-member team, dispatch to agent A, relay A's output to agent B with instructions, assert B's response contains A's output text (since `EchoExecutor` echoes the full input), and assert `reference_task_ids` on B's outbound message contains A's task ID.
    4. Register `@pytest.mark.team` in `pyproject.toml` `[tool.pytest.ini_options]` markers list. All Phase 5 tests carry `@pytest.mark.integration` and `@pytest.mark.team`. Live tests additionally carry `@pytest.mark.claude` or `@pytest.mark.gemini` and the appropriate skip guards (matching the pattern in `test_french_novel_relay.py`).

- `Phase 6` — Gemini `@a2a` client validation and discovery update
    1. Audit `discovery.py`'s `write_gemini_settings()` to confirm it writes `experimental.enableAgents: true` under the `experimental` key of `~/.gemini/settings.json` (and not the per-project `.gemini/settings.json`). The current implementation writes to `root_dir / ".gemini" / "settings.json"` — determine whether the Gemini CLI reads from the home directory or the project directory and adjust if needed. Document the finding in a comment in `discovery.py`.
    2. Update `write_agent_discovery()` if the agent card URL it generates uses the wrong endpoint path. The current code generates `http://{host}:{port}/.well-known/agent.json` — verify against the A2A spec and the Gemini `@a2a` PR #3079 that this is the correct discovery endpoint (the SDK uses `/.well-known/agent.json` consistently; confirm no `.json` vs no-extension ambiguity).
    3. Write `test_gemini_a2a_client_sub_delegation` in `.vaultspec/lib/src/protocol/a2a/tests/test_french_novel_relay.py` or a new file. This live test: starts a `ClaudeA2AExecutor` server on port 10110, calls `write_agent_discovery()` and `write_gemini_settings()`, then dispatches a task to a `GeminiA2AExecutor` server on port 10111 with a prompt that instructs Gemini to sub-delegate via `@a2a`. Asserts the final task completes and the response text contains evidence of cross-agent delegation. Marked `@pytest.mark.integration`, `@pytest.mark.gemini`, `@pytest.mark.claude`, `@pytest.mark.slow`, and guarded by both `requires_anthropic` and `requires_gemini` skip marks.
    4. Verify the end-to-end three-layer stack works: Claude Code (coordinator) → `ClaudeA2AExecutor :10010` and `GeminiA2AExecutor :10011`, with Gemini optionally sub-delegating back to Claude via `@a2a`. This is the diagram from Decision 3 in the ADR. Run the Phase 5 integration test suite to confirm no regressions.

## Parallelization

Phases 1 and 2 are strictly sequential — the skeleton (Phase 1) must exist before
dispatch logic (Phase 2) can be implemented. Phase 3 (CLI) depends on Phase 1 and 2
types being stable, but can begin in parallel with Phase 2 once `TeamSession` and
`form_team()` signatures are locked (the CLI can stub unimplemented methods).

Phase 4 (liveness/error handling) is independent of Phase 3 and can proceed in
parallel with CLI development. Both Phases 3 and 4 depend only on the Phase 2 API
surface, not on each other.

Phase 5 (integration test suite) can begin writing the fixture infrastructure in
parallel with Phase 4 once Phase 2 is complete. The live tests in Phase 5 require
Phase 3 (CLI) only for CLI-invocation tests; the programmatic integration tests do not.

Phase 6 (Gemini `@a2a` validation) is fully independent of Phases 3–5 once Phase 2
is complete. The `discovery.py` audit (Phase 6, Step 1) can happen in parallel with
Phase 1.

Recommended parallelization for a two-agent execution:
- Agent A: Phases 1 → 2 → 4 (orchestration core)
- Agent B: Phase 6 Step 1 audit runs immediately; Phases 3 and 5 begin once Phase 2 is merged

## Verification

**Unit test coverage (CI):** All tests in `.vaultspec/lib/src/orchestration/tests/test_team.py` and `.vaultspec/lib/tests/cli/test_team_cli.py` must pass with `@pytest.mark.team` and no live LLM. The mock relay in `TestFrenchNovelRelayMock` must continue to pass — no regressions to existing A2A tests.

**Integration correctness:** The `test_two_agent_parallel_dispatch_integration` test must demonstrate that `contextId` on both dispatched tasks equals `session.team_id` — this is the observable proof that Decision 2 is correctly implemented. A test that passes but dispatches without `contextId` would be a false positive.

**Relay integrity:** `test_relay_chain_integration` must assert that `reference_task_ids` on the outbound relay message contains the source task ID. This is the observable proof that Decision 5 is correctly implemented. Inspecting the outbound `Message` object (not just the response) is required.

**CLI state persistence:** `test_team_cli.py` must verify that a `team.py create` invocation followed by a `team.py status` invocation in a separate process reloads the correct session. This rules out the common failure mode of in-memory-only state.

**Gemini E2E (manual gate):** The Phase 6 live test is not a CI gate — it requires both CLIs on PATH and `experimental.enableAgents`. The verification criterion is that the test passes at least once on the development machine before the feature is declared complete. An LLM responding with content that merely mentions delegation without actually calling `@a2a` does not satisfy the criterion.

**ADR coverage audit:** After all phases complete, manually compare the seven behaviors listed in the ADR's "New Files" and "Modified Files" sections against the actual filesystem. Any ADR-specified file that does not exist or is empty is a verification failure regardless of test results.

**No regression on bilateral A2A:** Run the full `protocol/a2a/tests/` suite (`pytest -m integration`) and confirm all existing tests pass. The `TeamCoordinator` must not modify any file in `protocol/a2a/executors/`, `server.py`, `agent_card.py`, `state_map.py`, or `discovery.py` beyond the targeted `write_gemini_settings()` audit in Phase 6.
