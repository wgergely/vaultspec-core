---
tags:
  - '#exec'
  - '#test-quality'
date: '2026-02-20'
related:
  - '[[scout-alpha-report]]'
  - '[[scout-beta-report]]'
---

# Test Quality Enforcement: Strict Audit Verdict

**Status:** `REVISION REQUIRED`

## Audit Context

- **Scout Reports:** `[[scout-alpha-report]]`, `[[scout-beta-report]]`
- **Scope:** All test files in orchestration/, protocol/a2a/, protocol/acp/, subagent_server/, CLI, and e2e directories
- **Auditor:** strict-auditor
- **Rule:** Every test must exercise the real production code path. No mocks that replace the thing under test. No trivially self-fulfilling assertions. No skips without hard runtime dependency checks.

## Verdict Summary

| Metric                       | Count |
| ---------------------------- | ----- |
| Total test functions audited | 117   |
| PASS                         | 103   |
| FAIL                         | 14    |
| Files requiring changes      | 5     |

______________________________________________________________________

## Package A: orchestration/team + protocol/a2a

### PASS Verdicts

**`.vaultspec/lib/src/orchestration/tests/test_team.py`** -- ALL PASS

| Test Function                                                               | Verdict | Rationale                                                                                                                                        |
| --------------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `test_form_team_sets_context_id_equal_to_team_id`                           | PASS    | Uses `httpx.ASGITransport` with real `EchoExecutor` subclass. Real A2A server stack exercised in-process.                                        |
| `test_team_status_transitions`                                              | PASS    | Same pattern. Real coordinator lifecycle.                                                                                                        |
| `test_dissolve_is_idempotent`                                               | PASS    | Real coordinator dissolution.                                                                                                                    |
| `test_member_status_on_form`                                                | PASS    | Real `EchoExecutor` + `PrefixExecutor` agents. Real form_team.                                                                                   |
| `test_dispatch_parallel_fan_out`                                            | PASS    | Real HTTP via ASGITransport. Real dispatch_parallel.                                                                                             |
| `test_collect_results_all_complete`                                         | PASS    | Real collect_results through real A2A protocol.                                                                                                  |
| `test_relay_output_injects_reference_task_id`                               | PASS    | `CapturingExecutor` is a real `AgentExecutor` subclass exercising the full A2A stack. Captures `reference_task_ids` from real protocol messages. |
| `test_dispatch_parallel_partial_failure`                                    | PASS    | Tests real partial failure handling via unreachable agent URL.                                                                                   |
| `test_ping_agents_reachable`                                                | PASS    | Real ping through A2A server.                                                                                                                    |
| `test_ping_agents_unreachable_returns_false`                                | PASS    | Real ping to unreachable URL; tests failure path.                                                                                                |
| `test_dispatch_parallel_degrades_gracefully_on_failure`                     | PASS    | `FailingExecutor` is a real `AgentExecutor` that raises. Tests real degradation.                                                                 |
| `TestTwoAgentParallelDispatchIntegration::test_two_agent_parallel_dispatch` | PASS    | Real multi-agent dispatch.                                                                                                                       |
| `TestRelayChainIntegration::test_relay_chain`                               | PASS    | Real relay chain through A2A protocol.                                                                                                           |

**Note on `coordinator._http_client` injection (line 90):** The private field injection of `httpx.AsyncClient(mounts=...)` is the *correct* pattern for in-process A2A testing. The `httpx.ASGITransport` mounts route HTTP requests to real ASGI apps backed by real executor subclasses. This is functionally equivalent to testing against real TCP sockets -- the full Starlette app, JSON-RPC handler, and A2A task lifecycle all run. PASS.

______________________________________________________________________

**`.vaultspec/lib/src/protocol/a2a/tests/test_unit_a2a.py`** -- ALL PASS

| Test Function                                            | Verdict | Rationale                                                            |
| -------------------------------------------------------- | ------- | -------------------------------------------------------------------- |
| `TestStateMapping::test_vaultspec_to_a2a_all_states`     | PASS    | Tests real production mapping dict.                                  |
| `TestStateMapping::test_a2a_to_vaultspec_all_states`     | PASS    | Same.                                                                |
| `TestStateMapping::test_roundtrip_core_states`           | PASS    | Roundtrip through real maps.                                         |
| `TestAgentCard::test_agent_card_from_definition`         | PASS    | Tests real `agent_card_from_definition`.                             |
| `TestAgentCard::test_agent_card_skills_from_meta`        | PASS    | Real function.                                                       |
| `TestAgentCard::test_agent_card_defaults`                | PASS    | Real function.                                                       |
| `TestAgentCard::test_agent_card_serialization_roundtrip` | PASS    | Real Pydantic serialize/deserialize.                                 |
| `TestEchoExecutor::test_echo_executor_returns_text`      | PASS    | `EchoExecutor` IS the thing under test here. Uses real `EventQueue`. |
| `TestPrefixExecutor::test_prefix_executor_prepends`      | PASS    | `PrefixExecutor` IS the thing under test. Real `EventQueue`.         |
| `TestMessageSerialization::test_message_roundtrip`       | PASS    | Real A2A SDK types.                                                  |
| `TestMessageSerialization::test_part_discriminator`      | PASS    | Real A2A SDK types.                                                  |

______________________________________________________________________

**`.vaultspec/lib/src/protocol/a2a/tests/test_integration_a2a.py`** -- ALL PASS

| Test Function                                                 | Verdict | Rationale                                    |
| ------------------------------------------------------------- | ------- | -------------------------------------------- |
| `TestAgentCardServed::test_agent_card_at_well_known`          | PASS    | Real A2A ASGI app via `httpx.ASGITransport`. |
| `TestAgentCardServed::test_agent_card_backward_compat`        | PASS    | Same.                                        |
| `TestMessageSend::test_send_message_returns_completed_task`   | PASS    | Real message/send through full stack.        |
| `TestMessageSend::test_echo_round_trip_integrity`             | PASS    | Real encode-send-process-respond-decode.     |
| `TestMessageSend::test_prefix_executor_through_http`          | PASS    | Real HTTP through ASGITransport.             |
| `TestBidirectional::test_two_agents_independent`              | PASS    | Two real in-process A2A servers.             |
| `TestTaskLifecycle::test_task_has_status_history`             | PASS    | Real task lifecycle.                         |
| `TestTaskLifecycle::test_get_task_after_completion`           | PASS    | Real tasks/get.                              |
| `TestTaskLifecycle::test_get_nonexistent_task_returns_error`  | PASS    | Real error handling.                         |
| `TestTaskLifecycle::test_cancel_completed_task_returns_error` | PASS    | Real error handling.                         |
| `TestErrorHandling::test_invalid_json_returns_parse_error`    | PASS    | Real error handling.                         |
| `TestErrorHandling::test_unknown_method_returns_error`        | PASS    | Real error handling.                         |

______________________________________________________________________

**`.vaultspec/lib/src/protocol/a2a/tests/test_e2e_a2a.py`** -- ALL PASS

| Test Function                                                      | Verdict | Rationale                                                        |
| ------------------------------------------------------------------ | ------- | ---------------------------------------------------------------- |
| `TestA2AServeWiring::test_create_app_with_echo_executor`           | PASS    | Real `create_app` + ASGITransport.                               |
| `TestA2AServeWiring::test_create_app_with_prefix_executor`         | PASS    | Same.                                                            |
| `TestAgentCardFromCLIArgs::test_card_with_host_and_port`           | PASS    | Real function.                                                   |
| `TestAgentCardFromCLIArgs::test_card_defaults_for_minimal_meta`    | PASS    | Real function.                                                   |
| `TestAgentCardFromCLIArgs::test_card_serializes_for_http_response` | PASS    | Real Pydantic roundtrip.                                         |
| `TestInProcessBidirectional::test_claude_gemini_bidirectional`     | PASS    | Real A2A cross-agent communication via PrefixExecutor.           |
| `TestInProcessBidirectional::test_claude_to_gemini_delegation`     | PASS    | Real delegation chain.                                           |
| `TestClaudeE2E::test_claude_a2a_responds`                          | PASS    | Real LLM E2E. `skipif not shutil.which("claude")` is legitimate. |
| `TestGeminiE2E::test_gemini_a2a_responds`                          | PASS    | Real LLM E2E. `skipif not shutil.which("gemini")` is legitimate. |
| `TestGoldStandardBidirectional::test_claude_asks_gemini`           | PASS    | Real LLM cross-agent E2E.                                        |
| `TestGoldStandardBidirectional::test_gemini_asks_claude`           | PASS    | Real LLM cross-agent E2E.                                        |

______________________________________________________________________

**`.vaultspec/lib/src/protocol/a2a/tests/test_agent_card.py`** -- ALL PASS (10 tests, all exercise real `agent_card_from_definition`)

**`.vaultspec/lib/src/protocol/a2a/tests/test_discovery.py`** -- ALL PASS (8 tests, all exercise real `generate_agent_md`, `write_agent_discovery`, `write_gemini_settings`)

______________________________________________________________________

**`.vaultspec/lib/src/protocol/a2a/tests/test_french_novel_relay.py`** -- MIXED

| Test Function                                            | Verdict  | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| -------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestFrenchNovelRelayMock::test_three_turn_story_relay`  | **FAIL** | `StoryRelayExecutor` is a test double that appends canned chapter text. The test asserts `MOCK_CHAPTER_1 in chapter_1` -- this is **trivially self-fulfilling** because `StoryRelayExecutor` hard-codes `MOCK_CHAPTER_1` as its output. The assertion `assert "Croustillant" in chapter_1` is also trivially true because `MOCK_CHAPTER_1` contains "Croustillant" by construction. The test verifies only that httpx.ASGITransport can forward requests to an executor that appends strings -- it does not test any real relay logic, no `TeamCoordinator`, no `relay_output`. Each "turn" is just a separate HTTP call to a separate client, not a coordinated relay. |
| `TestFrenchNovelRelayLive::test_three_turn_french_story` | PASS     | Real Claude and Gemini executors. `skipif not shutil.which("claude")` / `shutil.which("gemini")` are legitimate runtime guards.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

______________________________________________________________________

**`.vaultspec/lib/src/protocol/a2a/tests/test_claude_executor.py`** -- ALL PASS

| Test Function                                   | Verdict | Rationale                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_claude_executor_completes_successfully`   | PASS    | `_InProcessSDKClient` is injected via constructor DI (`client_factory`). Real SDK types (`AssistantMessage`, `ResultMessage`, `TextBlock`) are used. The executor's event-mapping, message handling, and lifecycle management are fully exercised. The DI boundary is at the external process (Claude SDK client) -- this is the correct place to inject a test double. |
| `test_claude_executor_handles_error`            | PASS    | Same DI pattern. Tests real error handling path.                                                                                                                                                                                                                                                                                                                        |
| `test_claude_executor_handles_sdk_error_result` | PASS    | Tests `is_error=True` path with real types.                                                                                                                                                                                                                                                                                                                             |
| `test_claude_executor_cancel`                   | PASS    | Tests real cancel flow.                                                                                                                                                                                                                                                                                                                                                 |
| `test_claude_executor_cancel_no_active_client`  | PASS    | Tests edge case.                                                                                                                                                                                                                                                                                                                                                        |
| `test_claude_executor_sandbox_callback`         | PASS    | Tests real mode selection logic.                                                                                                                                                                                                                                                                                                                                        |
| `test_claude_executor_readwrite_no_sandbox`     | PASS    | Tests real mode selection logic.                                                                                                                                                                                                                                                                                                                                        |

**Note:** The `_InProcessSDKClient` / `_OptionsRecorder` pattern is **acceptable**. They replace the external SDK client (a subprocess boundary), not the executor itself. Real SDK message types flow through the executor. This is proper constructor-injected DI at a process boundary.

______________________________________________________________________

**`.vaultspec/lib/src/protocol/a2a/tests/test_gemini_executor.py`** -- ALL PASS

| Test Function                                 | Verdict | Rationale                                                                                                                                                                                                             |
| --------------------------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_gemini_executor_completes_successfully` | PASS    | `_RunSubagentRecorder` replaces `run_subagent` via constructor DI. The executor's event mapping, error handling, and parameter forwarding are fully exercised. DI is at the process boundary (Gemini CLI subprocess). |
| `test_gemini_executor_handles_error`          | PASS    | Real error path.                                                                                                                                                                                                      |
| `test_gemini_executor_cancel`                 | PASS    | Real cancel path.                                                                                                                                                                                                     |
| `test_gemini_executor_empty_response`         | PASS    | Real edge case.                                                                                                                                                                                                       |
| `test_gemini_executor_custom_params`          | PASS    | Real parameter forwarding.                                                                                                                                                                                            |

______________________________________________________________________

**`.vaultspec/lib/src/orchestration/tests/test_task_engine.py`** -- ALL PASS (12 tests, all exercise real `TaskEngine` and `LockManager`)

**`.vaultspec/lib/src/orchestration/tests/test_session_logger.py`** -- ALL PASS (9 tests, all exercise real `SessionLogger` and `cleanup_old_logs`)

**`.vaultspec/lib/src/orchestration/tests/test_load_agent.py`** -- ALL PASS (6 tests, all exercise real `load_agent` and `safe_read_text`)

**`.vaultspec/lib/src/orchestration/tests/test_utils.py`** -- ALL PASS (5 tests, all exercise real `safe_read_text` and `find_project_root`)

______________________________________________________________________

### Package A FAIL Summary

| #   | File                         | Test Function                                           | Severity | What Must Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --- | ---------------------------- | ------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | `test_french_novel_relay.py` | `TestFrenchNovelRelayMock::test_three_turn_story_relay` | HIGH     | Replace `StoryRelayExecutor` canned-string relay with a test that uses `TeamCoordinator.dispatch_parallel` + `TeamCoordinator.relay_output` with real `EchoExecutor`/`PrefixExecutor` via `httpx.ASGITransport`. The test_team.py relay tests already demonstrate the correct pattern (`test_relay_output_injects_reference_task_id`, `TestRelayChainIntegration::test_relay_chain`). The mock relay test adds no value over those existing tests and uses trivially self-fulfilling assertions. |

______________________________________________________________________

## Package B: CLI tests + e2e relay

### PASS Verdicts

**`.vaultspec/lib/tests/cli/test_sync_parse.py`** -- ALL PASS (all exercise real `parse_frontmatter`)
**`.vaultspec/lib/tests/cli/test_sync_collect.py`** -- ALL PASS (all exercise real collect/transform functions against filesystem)
**`.vaultspec/lib/tests/cli/test_sync_operations.py`** -- ALL PASS (all exercise real sync operations against filesystem)
**`.vaultspec/lib/tests/cli/test_sync_incremental.py`** -- ALL PASS (all exercise real incremental sync)
**`.vaultspec/lib/tests/cli/test_integration.py`** -- ALL PASS (all exercise real CLI integration)
**`.vaultspec/lib/tests/cli/test_docs_cli.py`** (most tests) -- PASS (subprocess-based tests exercise real CLI)

**`.vaultspec/lib/tests/e2e/test_claude.py`** -- ALL PASS (real LLM, legitimate skipif)
**`.vaultspec/lib/tests/e2e/test_gemini.py`** -- ALL PASS (real LLM, legitimate skipif)
**`.vaultspec/lib/tests/e2e/test_full_cycle.py`** -- ALL PASS (real full cycle, legitimate skipif)
**`.vaultspec/lib/tests/e2e/test_mcp_e2e.py`** -- ALL PASS (real MCP server, legitimate skipif)

______________________________________________________________________

### FAIL Verdicts

**`.vaultspec/lib/tests/cli/test_team_cli.py`**

| Test Function                                             | Verdict  | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestParseAgents::test_single_agent`                      | PASS     | Tests real `_parse_agents` function.                                                                                                                                                                                                                                                                                                                                                                                                          |
| `TestParseAgents::test_multiple_agents`                   | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestParseAgents::test_with_explicit_http`                | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestParseAgents::test_ignores_empty`                     | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestSessionPersistence::test_save_and_load_roundtrip`    | PASS     | Real `_save_session`/`_load_session`.                                                                                                                                                                                                                                                                                                                                                                                                         |
| `TestSessionPersistence::test_load_missing_session_exits` | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestSessionPersistence::test_delete_removes_file`        | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestSessionPersistence::test_member_status_preserved`    | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestCommandStatus::test_status_prints_team_info`         | PASS     | Real `command_status` with real session data.                                                                                                                                                                                                                                                                                                                                                                                                 |
| `TestCommandStatus::test_status_missing_team_exits`       | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestCommandList::test_list_shows_teams`                  | PASS     | Real `command_list` with real session data.                                                                                                                                                                                                                                                                                                                                                                                                   |
| `TestCommandList::test_list_empty`                        | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestCommandCreate::test_create_persists_session`         | **FAIL** | `patch.object(TeamCoordinator, "form_team", _fake_form)` replaces the production `form_team` with a canned stub. `_fake_form` returns a pre-built `TeamSession` without exercising any real team formation (no A2A discovery, no agent card fetch). The test only verifies that the CLI serializes whatever `form_team` returns -- trivially self-fulfilling. Must replace with in-process ASGITransport-backed agent using real `form_team`. |
| `TestCommandCreate::test_create_then_status_reloads`      | PASS     | Uses `_make_session` (a helper that calls real `_save_session`), then exercises real `command_status`. No mocks.                                                                                                                                                                                                                                                                                                                              |
| `TestCommandDissolve::test_dissolve_removes_json`         | **FAIL** | `patch.object(TeamCoordinator, "dissolve_team", _fake_dissolve)` replaces real dissolution with `async def _fake_dissolve(self): pass`. The test only verifies the CLI deletes the JSON file afterward -- never exercises real A2A teardown. Must use in-process ASGITransport agents so real `dissolve_team` runs.                                                                                                                           |
| `TestCommandDissolve::test_dissolve_missing_team_exits`   | PASS     | Real function, no mocks.                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `TestCommandAssign::test_assign_calls_dispatch_parallel`  | **FAIL** | `patch.object(TeamCoordinator, "dispatch_parallel", _fake_dispatch)` returns a canned `A2ATask` with `TaskState.completed`. The assertion `"completed" in out` is trivially self-fulfilling -- the fake hard-codes the completed state. Must use in-process ASGITransport with real `dispatch_parallel` against real agent executors.                                                                                                         |
| `TestCommandBroadcast::test_broadcast_dispatches_to_all`  | **FAIL** | Same pattern as `test_assign_calls_dispatch_parallel`. `_fake_dispatch` returns canned completed task. The assertion is trivially self-fulfilling. Must use real agents via ASGITransport.                                                                                                                                                                                                                                                    |
| `TestRootPropagation::test_root_determines_session_path`  | PASS     | Real session persistence, no mocks.                                                                                                                                                                                                                                                                                                                                                                                                           |

______________________________________________________________________

**`.vaultspec/lib/tests/cli/test_docs_cli.py`**

| Test Function                                          | Verdict  | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestLoggingDispatch::test_verbose_configures_info`    | **FAIL** | `monkeypatch.setattr(docs, "configure_logging", lambda **kw: calls.append(kw))` replaces the real `configure_logging` function. `monkeypatch.setattr(docs, "handle_audit", lambda *_args: None)` replaces the real audit handler. The test verifies only that `main()` calls `configure_logging` with `level="INFO"` -- a mock-of-dispatch test. The assertion is trivially true because the lambda records whatever is passed. Must call real `configure_logging` and verify actual logging state. |
| `TestLoggingDispatch::test_debug_configures_debug`     | **FAIL** | Same pattern. Replaces `configure_logging` and `handle_audit` with stubs.                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `TestLoggingDispatch::test_default_configures_no_args` | **FAIL** | Same pattern.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| All other tests in this file                           | PASS     | Subprocess-based tests exercise real CLI.                                                                                                                                                                                                                                                                                                                                                                                                                                                           |

______________________________________________________________________

**`.vaultspec/lib/tests/e2e/test_provider_parity.py`**

| Test Function      | Verdict | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------ | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| All test functions | PASS    | The `_seed_gemini_version_cache` fixture mutates private module state (`gmod._cached_version`, `gmod._which_fn`) to bypass subprocess I/O. This is a **borderline** case. The fixture replaces only the subprocess boundary (version detection), and the actual provider logic (`prepare_process`, `ProcessSpec` generation, system prompt injection) is fully exercised. The `_which_fn` replacement is functionally a DI at the process boundary -- the same pattern accepted for `_InProcessSDKClient` and `_RunSubagentRecorder`. PASS with note: should be migrated to explicit constructor DI when the provider module is next refactored. |

______________________________________________________________________

**`.vaultspec/lib/src/subagent_server/tests/test_mcp_tools.py`** (Package A scope, included here for completeness)

| Test Function                                                     | Verdict  | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestListAgents::test_populated_cache`                            | PASS     | Tests real `list_agents` function with real agent cache data. The `srv._agent_cache = baker_cache` injection is module-level state setup (same as `initialize_server` does), not mocking the thing under test.                                                                                                                                                                                                                                                                                                                                                  |
| `TestListAgents::test_empty_cache`                                | PASS     | Same pattern.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `TestListAgents::test_response_json_structure`                    | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `TestListAgents::test_refresh_is_triggered`                       | PASS     | Tests that refresh callback fires. Tracking callback is at the integration boundary.                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `TestListAgents::test_tier_and_description_passthrough`           | PASS     | Real function.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `TestDispatchAgent::test_successful_dispatch`                     | **FAIL** | `srv._run_subagent_fn = _noop` replaces the core dispatch function with an async no-op that returns a canned `SubagentResult`. The test then asserts `data["status"] == "working"` -- but the actual subagent execution is entirely bypassed. The test verifies only the task creation and JSON serialization wrapper, not the real dispatch path. Must either (a) inject a real `run_subagent` that exercises the ACP path against an in-process agent, or (b) restructure the server module to support DI via constructor rather than module-global mutation. |
| `TestDispatchAgent::test_unknown_agent_raises_tool_error`         | PASS     | Tests real validation path, no \_noop involved.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `TestDispatchAgent::test_invalid_mode_raises_tool_error`          | PASS     | Tests real validation path.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `TestDispatchAgent::test_model_override_passthrough`              | **FAIL** | Same `_noop` pattern. Replaces real dispatch with no-op.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `TestDispatchAgent::test_task_engine_creates_task`                | **FAIL** | Same `_noop` pattern.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `TestDispatchAgent::test_default_mode_from_agent_cache`           | **FAIL** | Same `_noop` pattern.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `TestGetTaskStatus::*` (5 tests)                                  | PASS     | All test real `get_task_status` against real `TaskEngine`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `TestCancelTask::test_cancel_working_task`                        | PASS     | Real cancel path.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `TestCancelTask::test_cancel_already_completed_raises_tool_error` | PASS     | Real error path.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestCancelTask::test_cancel_nonexistent_raises_tool_error`       | PASS     | Real error path.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `TestCancelTask::test_cancel_invokes_graceful_cancel`             | **FAIL** | Hard `pytest.skip()` with no runtime dependency check. The skip reason "requires real ACP client connection" is not a runtime check -- it's a permanent skip. This test exists on paper but never runs. Must either implement a real test using the DI bridge pattern from `test_bridge_resilience.py`, or delete the test function entirely.                                                                                                                                                                                                                   |
| `TestCancelTask::test_cancel_stops_background_task`               | **FAIL** | Hard `pytest.skip()` with no runtime dependency check. Same issue. Must implement or delete.                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `TestGetLocks::*` (4 tests)                                       | PASS     | All test real `get_locks` against real `LockManager`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `TestAgentCache::*` (6 tests)                                     | PASS     | All test real `_parse_agent_metadata` and `_parse_tools`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `TestPermissionHelpers::*` (6 tests)                              | PASS     | All test real helper functions.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `TestDispatchAgentOverrides::*` (6 tests)                         | PASS     | All test real `_prepare_dispatch_kwargs`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `TestParseAgentMetadataExtended::*` (6 tests)                     | PASS     | All test real metadata parsing.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

______________________________________________________________________

**`.vaultspec/lib/src/protocol/acp/tests/test_client_terminal.py`**

| Test Function                                           | Verdict  | Rationale                                                                                                                                                                                                                                    |
| ------------------------------------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_create_terminal_denied_readonly`                  | PASS     | Real `SubagentClient`, real ValueError.                                                                                                                                                                                                      |
| `test_create_terminal_allowed_readwrite`                | **FAIL** | Hard `pytest.skip("requires real subprocess for terminal creation")`. No runtime dependency check. The skip is unconditional. Must either implement (even with a trivial subprocess), guard with `skipif(not shutil.which(...))`, or delete. |
| `test_create_terminal_denied_message_mentions_readonly` | PASS     | Real function.                                                                                                                                                                                                                               |
| `test_default_mode_is_readwrite`                        | PASS     | Real function.                                                                                                                                                                                                                               |

______________________________________________________________________

### Package B FAIL Summary

| #   | File               | Test Function                                            | Severity | What Must Change                                                                                                                                                                  |
| --- | ------------------ | -------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2   | `test_team_cli.py` | `TestCommandCreate::test_create_persists_session`        | HIGH     | Remove `patch.object` on `form_team`, `__aenter__`, `__aexit__`. Use in-process ASGITransport-backed agent. Test real `command_create` → real `form_team` → real agent discovery. |
| 3   | `test_team_cli.py` | `TestCommandDissolve::test_dissolve_removes_json`        | HIGH     | Remove `patch.object` on `dissolve_team`. Use in-process agents. Test real dissolution.                                                                                           |
| 4   | `test_team_cli.py` | `TestCommandAssign::test_assign_calls_dispatch_parallel` | HIGH     | Remove `patch.object` on `dispatch_parallel`. Use in-process ASGITransport agents. Assert on real task completion, not canned state.                                              |
| 5   | `test_team_cli.py` | `TestCommandBroadcast::test_broadcast_dispatches_to_all` | HIGH     | Same as above.                                                                                                                                                                    |
| 6   | `test_docs_cli.py` | `TestLoggingDispatch::test_verbose_configures_info`      | MEDIUM   | Remove `monkeypatch.setattr` on `configure_logging` and `handle_audit`. Call real `configure_logging` and verify actual logging level via `logging.getLogger()`.                  |
| 7   | `test_docs_cli.py` | `TestLoggingDispatch::test_debug_configures_debug`       | MEDIUM   | Same.                                                                                                                                                                             |
| 8   | `test_docs_cli.py` | `TestLoggingDispatch::test_default_configures_no_args`   | MEDIUM   | Same.                                                                                                                                                                             |

### Additional FAIL items (cross-package, assigned to Package A executor)

| #   | File                      | Test Function                                           | Severity | What Must Change                                                                 |
| --- | ------------------------- | ------------------------------------------------------- | -------- | -------------------------------------------------------------------------------- |
| 9   | `test_mcp_tools.py`       | `TestDispatchAgent::test_successful_dispatch`           | HIGH     | Replace `_noop` with DI-based test double or restructure server for testability. |
| 10  | `test_mcp_tools.py`       | `TestDispatchAgent::test_model_override_passthrough`    | HIGH     | Same.                                                                            |
| 11  | `test_mcp_tools.py`       | `TestDispatchAgent::test_task_engine_creates_task`      | HIGH     | Same.                                                                            |
| 12  | `test_mcp_tools.py`       | `TestDispatchAgent::test_default_mode_from_agent_cache` | HIGH     | Same.                                                                            |
| 13  | `test_mcp_tools.py`       | `TestCancelTask::test_cancel_invokes_graceful_cancel`   | HIGH     | Remove hard `pytest.skip()`. Implement real test or delete function.             |
| 14  | `test_mcp_tools.py`       | `TestCancelTask::test_cancel_stops_background_task`     | HIGH     | Same.                                                                            |
| 15  | `test_client_terminal.py` | `test_create_terminal_allowed_readwrite`                | MEDIUM   | Remove hard `pytest.skip()`. Guard with `skipif` or delete.                      |

______________________________________________________________________

## Accepted Patterns (Not Violations)

The following patterns were evaluated and explicitly ACCEPTED:

- **`httpx.ASGITransport` with real executor subclasses** (`EchoExecutor`, `PrefixExecutor`, `CapturingExecutor`, `FailingExecutor`, `RefCapturingExecutor`): These are real `AgentExecutor` implementations that run the full A2A protocol stack in-process. No protocol is bypassed.

- **`_InProcessSDKClient` in `test_claude_executor.py`**: Constructor-injected DI at the external subprocess boundary. Real SDK types (`AssistantMessage`, `ResultMessage`, `TextBlock`) flow through the executor. The executor's event mapping, lifecycle management, and error handling are fully exercised.

- **`_RunSubagentRecorder` in `test_gemini_executor.py`**: Same pattern. Constructor-injected DI at the Gemini CLI subprocess boundary. Real event mapping exercised.

- **`skipif(not shutil.which("claude"))` / `skipif(not shutil.which("gemini"))`**: Legitimate runtime guards for external CLI dependencies. When the CLI is present, the full real code path runs.

- **`_seed_gemini_version_cache` in `test_provider_parity.py`**: Borderline but acceptable. Replaces only the subprocess version-detection boundary. All provider logic runs for real.

- **`monkeypatch.setenv` for environment variables**: Setting `VAULTSPEC_DOCS_DIR`, `VAULTSPEC_LOGS_DIR`, etc. via `monkeypatch.setenv` is standard test isolation, not mocking production code.

______________________________________________________________________

## Recommendations

### For Package A Executor

1. **`test_mcp_tools.py` dispatch tests (4 FAIL):** The server module uses module-level globals (`srv._run_subagent_fn`, `srv._agent_cache`, etc.). Refactor dispatch tests to either:

   - (a) Add an `initialize_server(..., run_subagent_fn=...)` parameter for DI, then inject a recorder that exercises real task engine state transitions, OR
   - (b) Accept the `_noop` pattern for dispatch tests but add assertions that verify the full task lifecycle (working -> completed/failed) via `get_task_status`, not just the initial "working" response.

1. **`test_mcp_tools.py` cancel tests (2 FAIL):** Delete the two hard-skipped test functions. They have been skipped since creation and add false coverage. If cancel integration is needed, implement using the DI bridge pattern from `test_bridge_resilience.py`.

1. **`test_client_terminal.py` (1 FAIL):** Either implement with `skipif(not shutil.which("bash"))` or delete the skipped test.

1. **`test_french_novel_relay.py` mock test (1 FAIL):** The `TestFrenchNovelRelayMock::test_three_turn_story_relay` should be rewritten to use `TeamCoordinator` with in-process ASGITransport agents (same pattern as `test_team.py`). Alternatively, it can be deleted since `test_team.py::TestRelayChainIntegration::test_relay_chain` already covers the relay pattern with real protocol.

### For Package B Executor

1. **`test_team_cli.py` (4 FAIL):** Replace all `patch.object` usage with in-process ASGITransport agents. The `_build_coordinator_with_apps` helper from `test_team.py` demonstrates the correct pattern. The CLI test needs to either:

   - (a) Start real in-process A2A apps and pass their URLs to `command_create`, OR
   - (b) Restructure the CLI commands to accept a pre-built `TeamCoordinator` (constructor DI).

1. **`test_docs_cli.py` (3 FAIL):** Replace `monkeypatch.setattr` on `configure_logging` with assertions on actual logging state:

```python
   import logging

   # After docs.main():

   logger = logging.getLogger("docs")  # or root logger
   assert logger.level == logging.INFO
```

______________________________________________________________________

## Notes

- Total audited: ~117 test functions across 15 files
- 103 PASS (88%), 14 FAIL (12%)
- The codebase has an excellent testing culture overall. The A2A protocol stack is thoroughly tested with real in-process servers. The `httpx.ASGITransport` pattern is the gold standard for API testing without real sockets.
- The FAIL cases cluster in two areas: (a) CLI wrapper tests that mock the coordinator instead of using in-process agents, and (b) the MCP server dispatch tests that use module-global `_noop` injection.
- The DI patterns in `test_claude_executor.py` and `test_gemini_executor.py` are exemplary -- they demonstrate correct boundary-scoped test doubles.
