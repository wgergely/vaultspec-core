---
tags:
  - "#plan"
  - "#cli-test-coverage"
date: "2026-02-23"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# cli-test-coverage plan

Comprehensive CLI test coverage across all 4 vaultspec CLI entry points:
`__main__.py` (unified router), `spec_cli.py` (resource management),
`subagent_cli.py` (agent dispatch), and `team_cli.py` (team lifecycle). The
audit identified zero test coverage for the unified router and spec_cli,
minimal coverage for subagent_cli, and two missing command tests in team_cli.

## Proposed Changes

The recent CLI ecosystem factoring ([[2026-02-22-cli-ecosystem-factoring-adr]])
consolidated shared infrastructure into `cli_common.py` and decomposed the
monolithic `cli.py` into `spec_cli.py` plus `vaultspec.core` domain modules.
That restructuring explicitly noted that CLI-level test coverage gaps persist
and are out of scope for the refactoring. This plan fills those gaps.

All tests follow project constraints:

- **No mocking ever.** No `unittest.mock`, no `monkeypatch.setattr`, no
  stubbing. Tests exercise real code paths with real dependencies.
- `monkeypatch.setenv`/`delenv` are permitted for env-var testing.
- Tests use either subprocess invocation (`subprocess.run` with
  `sys.executable`) or direct function calls with real `argparse.Namespace`
  objects.
- The `test-project/` fixture directory provides a seeded `.vault/` corpus.
- For commands requiring live agents, use the in-process ASGI transport pattern
  from `test_team_cli.py` (`httpx.ASGITransport` with `EchoExecutor` /
  `PrefixExecutor`).

### Test infrastructure reused

- `src/vaultspec/tests/cli/conftest.py` -- `cleanup_test_project()`,
  `setup_rules_dir()`, `make_ns()`, auto-isolate `_isolate_cli` fixture
- `tests/constants.py` -- `TEST_PROJECT`, `TEST_VAULT`, port constants,
  timeout constants
- `test_vault_cli.py` pattern -- `run_vault(*args)` subprocess helper +
  direct parser access via `_make_parser()`
- `test_team_cli.py` pattern -- `_build_coordinator_with_apps()`,
  `_make_session()`, `_args()` helpers using real ASGI transports
- `src/vaultspec/protocol/a2a/tests/helpers.py` -- `EchoExecutor`,
  `PrefixExecutor` (real `AgentExecutor` subclasses)
- `src/vaultspec/protocol/a2a/tests/conftest.py` -- `_make_card()`,
  `make_request_context()`, `a2a_server_factory` fixture

### Source files under test

| CLI | Module path | Current test | Coverage gap |
|:----|:------------|:-------------|:-------------|
| Unified router | `src/vaultspec/__main__.py` | None | All routing logic |
| Spec CLI | `src/vaultspec/spec_cli.py` | None | All 11 resource groups |
| Subagent CLI | `src/vaultspec/subagent_cli.py` | `test_integration.py` (2 tests) | Arg parsing for `run`, `a2a-serve`; validation |
| Team CLI | `src/vaultspec/team_cli.py` | `test_team_cli.py` (6/8 commands) | `message` and `spawn` commands |

## Tasks

<!-- IMPORTANT: This document must be updated between execution runs to
     track progress. -->

### Phase 1: `__main__.py` unified router tests

- Name: create test-main-cli test file
- Step summary: (`.vault/exec/2026-02-23-cli-test-coverage/2026-02-23-cli-test-coverage-phase1-step1.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]]

Create `src/vaultspec/tests/cli/test_main_cli.py` with these test classes:

**TestMainHelp** (subprocess-based)

- `test_help_flag` -- `python -m vaultspec --help` exits 0, output contains
  "vaultspec", lists all SPEC_COMMANDS keys and NAMESPACES keys.
- `test_help_no_args` -- `python -m vaultspec` (no arguments) exits 0, prints
  same help text as `--help`.
- `test_help_h_flag` -- `python -m vaultspec -h` exits 0.

**TestMainVersion** (subprocess-based)

- `test_version_long` -- `python -m vaultspec --version` exits 0, output
  contains the version string (match against `cli_common.get_version()`).
- `test_version_short` -- `python -m vaultspec -V` exits 0, same version in
  output.

**TestNamespaceRouting** (subprocess-based)

- `test_vault_namespace_help` -- `python -m vaultspec vault --help` exits 0,
  output contains "audit" and "create" (vault_cli subcommands).
- `test_team_namespace_help` -- `python -m vaultspec team --help` exits 0,
  output contains "create" and "dissolve" (team_cli subcommands).
- `test_subagent_namespace_help` -- `python -m vaultspec subagent --help`
  exits 0, output contains "run" and "list" (subagent_cli subcommands).
- `test_vault_namespace_version` -- `python -m vaultspec vault -V` exits 0.
- `test_subagent_namespace_version` -- `python -m vaultspec subagent -V`
  exits 0.

**TestSpecCliFallthrough** (subprocess-based)

- `test_rules_help` -- `python -m vaultspec rules --help` exits 0, output
  contains "list", "add", "show", "sync".
- `test_agents_help` -- `python -m vaultspec agents --help` exits 0.
- `test_skills_help` -- `python -m vaultspec skills --help` exits 0.
- `test_doctor_runs` -- `python -m vaultspec doctor` exits 0, output contains
  "Python:" (doctor always prints Python version).
- `test_unknown_command_prints_help` -- `python -m vaultspec nonexistent`
  exits 0 (falls through to spec_cli which prints help on unrecognized
  resource).

**Implementation notes:**

- Helper: `run_vaultspec(*args)` using
  `subprocess.run([sys.executable, "-m", "vaultspec", *args], ...)` with
  `capture_output=True, text=True, timeout=30`.
- The `_print_help()` function in `__main__.py` iterates `SPEC_COMMANDS` and
  `NAMESPACES` dicts; tests should verify at least a sample of keys appear in
  stdout.
- The `main()` function mutates `sys.argv` before delegating to namespace CLIs
  (`sys.argv = [f"vaultspec {first_arg}", *sys.argv[2:]]`). Subprocess
  invocation naturally exercises this path.

---

### Phase 2: `spec_cli.py` resource management tests

- Name: create test-spec-cli test file
- Step summary: (`.vault/exec/2026-02-23-cli-test-coverage/2026-02-23-cli-test-coverage-phase2-step1.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]]

Create `src/vaultspec/tests/cli/test_spec_cli.py` with these test classes:

**TestSpecCliHelp** (subprocess-based)

- Helper: `run_spec(*args)` using
  `subprocess.run([sys.executable, "-m", "vaultspec.spec_cli", *args], ...)`.
- `test_main_help` -- exits 0, contains "rules", "agents", "skills", "config",
  "system", "sync-all", "test", "doctor", "init", "readiness", "hooks".
- `test_rules_help` -- `rules --help` exits 0, contains "list", "add", "show",
  "edit", "remove", "rename", "sync".
- `test_agents_help` -- `agents --help` exits 0, contains "set-tier".
- `test_skills_help` -- `skills --help` exits 0.
- `test_config_help` -- `config --help` exits 0, contains "show", "sync".
- `test_system_help` -- `system --help` exits 0, contains "show", "sync".
- `test_test_help` -- `test --help` exits 0, contains "category".
- `test_hooks_help` -- `hooks --help` exits 0, contains "list", "run".
- `test_readiness_help` -- `readiness --help` exits 0, contains "--json".
- `test_init_help` -- `init --help` exits 0, contains "--force".

**TestSpecCliArgParsing** (direct parser access)

Instantiate the parser by calling `spec_cli.main` indirectly. Since
`spec_cli.py` does not expose `_make_parser()` like `vault_cli.py`, the test
should parse args using `argparse` invocation patterns. The approach:

- Import `spec_cli` module and call `parser.parse_args()` on the parser
  constructed inside `main()`. Since `main()` constructs the parser inline
  and immediately dispatches, the cleanest approach is to use subprocess
  for functional tests and direct `argparse.Namespace` construction for
  handler testing.

For each resource group, test that parsing produces the correct `args.resource`
and `args.command`:

- `test_rules_list_parse` -- `["rules", "list"]` -> `resource="rules"`,
  `command="list"`.
- `test_rules_add_requires_name` -- `["rules", "add"]` raises `SystemExit`
  (missing `--name`).
- `test_rules_add_with_name` -- `["rules", "add", "--name", "my-rule"]` ->
  `command="add"`, `name="my-rule"`.
- `test_agents_set_tier_requires_tier` -- `["agents", "set-tier", "my-agent"]`
  raises `SystemExit`.
- `test_agents_set_tier_valid` --
  `["agents", "set-tier", "my-agent", "--tier", "HIGH"]` -> `tier="HIGH"`.
- `test_agents_add_tier_choices` --
  `["agents", "add", "--name", "x", "--tier", "INVALID"]` raises `SystemExit`.
- `test_sync_all_flags` -- `["sync-all", "--prune", "--dry-run"]` ->
  `prune=True`, `dry_run=True`.
- `test_test_category_default` -- `["test"]` -> `category="all"`.
- `test_test_category_unit` -- `["test", "unit"]` -> `category="unit"`.
- `test_test_module_flag` -- `["test", "--module", "cli"]` -> `module="cli"`.
- `test_test_invalid_category` -- `["test", "invalid"]` raises `SystemExit`.
- `test_readiness_json_flag` -- `["readiness", "--json"]` -> `json=True`.
- `test_hooks_run_event` -- `["hooks", "run", "post-sync", "--path", "/x"]` ->
  `event="post-sync"`, `path="/x"`.
- `test_init_force_flag` -- `["init", "--force"]` -> `force=True`.

Note: To access the parser, either refactor `spec_cli.py` to expose a
`_make_parser()` function (preferred, matching `vault_cli.py` pattern), or
reconstruct the parser in the test file. The executor should extract parser
construction into `_make_parser()` as a minimal prerequisite refactor.

**TestSpecCliFunctional** (subprocess + test-project)

- `test_doctor_output` -- `python -m vaultspec.spec_cli doctor` exits 0,
  stdout contains "Python:".
- `test_readiness_text` -- `python -m vaultspec.spec_cli --root <TEST_PROJECT>
  readiness` exits 0, stdout contains "Readiness Assessment" and dimension
  names ("Documentation", "Framework", etc.).
- `test_readiness_json` -- `python -m vaultspec.spec_cli --root <TEST_PROJECT>
  readiness --json` exits 0, stdout is valid JSON with keys "dimensions",
  "overall", "recommendations".
- `test_init_creates_structure` -- Run `init --force` against a `tmp_path`,
  verify `.vaultspec/rules/rules/`, `.vaultspec/rules/agents/`,
  `.vault/adr/`, `.vault/plan/` directories are created.
- `test_rules_list_output` -- `python -m vaultspec.spec_cli --root
  <TEST_PROJECT> rules list` exits 0 (may print empty or rules from
  test-project).
- `test_hooks_list_empty` -- Run against a `tmp_path` with no hooks
  directory; verify graceful handling (exits 0 or prints "No hooks").

**TestSpecCliDispatchRouting** (direct handler invocation)

For each resource+command combination, verify the correct handler is called by
constructing a `Namespace` and calling the handler directly:

- `test_rules_list_handler` -- Call `rules_list(make_ns(root=TEST_PROJECT))`
  and verify it returns without error (exercises real code path).
- `test_rules_add_handler` -- Call `rules_add(make_ns(root=tmp_path,
  name="test-rule", content="Test content", force=False))` and verify the rule
  file is created at the expected path.
- `test_config_show_handler` -- Call `config_show(make_ns(root=TEST_PROJECT))`
  and verify it prints without error.

---

### Phase 3: `subagent_cli.py` argument parsing and validation

- Name: extend subagent cli tests
- Step summary: (`.vault/exec/2026-02-23-cli-test-coverage/2026-02-23-cli-test-coverage-phase3-step1.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]]

Extend `src/vaultspec/tests/cli/test_integration.py` (or create
`src/vaultspec/tests/cli/test_subagent_cli.py` if the executor determines the
existing file is not the right home). Add these test classes:

**TestSubagentArgParsing** (direct parser access)

Since `subagent_cli.py` constructs the parser inline in `main()`, the executor
should either extract a `_make_parser()` function (matching `vault_cli.py`
pattern) or reconstruct a minimal parser in the test. The preferred approach is
to extract `_make_parser()`.

- `test_run_agent_flag` -- `["run", "--agent", "my-agent", "--goal", "do X"]`
  -> `agent="my-agent"`, `goal="do X"`.
- `test_run_model_override` -- `["run", "--agent", "x", "--goal", "y",
  "--model", "opus-4"]` -> `model="opus-4"`.
- `test_run_provider_choices` -- `["run", "--agent", "x", "--goal", "y",
  "--provider", "gemini"]` -> `provider="gemini"`. Also verify
  `--provider invalid` raises `SystemExit`.
- `test_run_mode_default` -- `["run", "--agent", "x", "--goal", "y"]` ->
  `mode="read-write"`.
- `test_run_mode_readonly` -- `["run", "--agent", "x", "--goal", "y",
  "--mode", "read-only"]` -> `mode="read-only"`.
- `test_run_interactive_flag` -- `["run", "--agent", "x", "--goal", "y", "-i"]`
  -> `interactive=True`.
- `test_run_resume_session` -- `["run", "--agent", "x", "--goal", "y",
  "--resume-session", "abc-123"]` -> `resume_session="abc-123"`.
- `test_run_max_turns` -- `["run", "--agent", "x", "--goal", "y",
  "--max-turns", "5"]` -> `max_turns=5`.
- `test_run_budget` -- `["run", "--agent", "x", "--goal", "y",
  "--budget", "100.0"]` -> `budget=100.0`.
- `test_run_effort_choices` -- `["run", "--agent", "x", "--goal", "y",
  "--effort", "high"]` -> `effort="high"`. Also verify `--effort invalid`
  raises `SystemExit`.
- `test_run_output_format` -- `["run", "--agent", "x", "--goal", "y",
  "--output-format", "json"]` -> `output_format="json"`.
- `test_run_context_append` -- `["run", "--agent", "x", "--goal", "y",
  "--context", "a.md", "--context", "b.md"]` -> `context=["a.md", "b.md"]`.
- `test_run_plan_flag` -- `["run", "--agent", "x", "--plan", "plan.md"]` ->
  `plan="plan.md"`.
- `test_run_mcp_servers` -- `["run", "--agent", "x", "--goal", "y",
  "--mcp-servers", '{"s":{"cmd":"x"}}']` -> `mcp_servers='{"s":{"cmd":"x"}}'`.

**TestSubagentA2aServeArgs** (direct parser access)

- `test_a2a_serve_defaults` -- `["a2a-serve"]` -> `executor="claude"`,
  `port=10010`, `agent="vaultspec-researcher"`, `mode="read-only"`.
- `test_a2a_serve_custom` -- `["a2a-serve", "--executor", "gemini", "--port",
  "9999", "--agent", "my-agent", "--model", "custom", "--mode", "read-write"]`
  -> all fields match.
- `test_a2a_serve_invalid_executor` -- `["a2a-serve", "--executor", "invalid"]`
  raises `SystemExit`.

**TestSubagentValidation** (subprocess-based)

- `test_run_without_agent_errors` -- `python -m vaultspec.subagent_cli run
  --goal "x"` exits non-zero (command_run checks `if not args.agent`).
- `test_run_without_goal_or_plan_errors` -- `python -m vaultspec.subagent_cli
  run --agent x` exits non-zero (requires `--goal`, `--task`, or `--plan`).
- `test_command_required` -- `python -m vaultspec.subagent_cli` (no subcommand)
  exits non-zero (subparsers have `required=True`).

---

### Phase 4: `team_cli.py` missing command tests

- Name: add message and spawn command tests
- Step summary: (`.vault/exec/2026-02-23-cli-test-coverage/2026-02-23-cli-test-coverage-phase4-step1.md`)
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-22-cli-ecosystem-factoring-adr]]

Extend `src/vaultspec/tests/cli/test_team_cli.py` with these test classes:

**TestCommandMessage** (in-process ASGI transport)

Uses the same `_build_coordinator_with_apps()` and `_make_session()` helpers
from the existing test file.

- `test_message_direct_dispatch` -- Build a coordinator with `EchoExecutor` on
  port 29910. Save session. Call `command_message(args)` with
  `to="echo-agent"`, `content="hello direct"`, `from_agent=None`. Verify task
  completes and the echo response contains "hello direct".

  Implementation detail: `command_message` loads the session via
  `load_session()` (from `orchestration.team_session`), then uses
  `restore_coordinator()` + `coordinator.dispatch_parallel()`. The test
  needs the session saved to disk AND a coordinator that can reach the
  in-process ASGI app. This requires either:
  (a) Calling `command_message()` after manually saving a session that points
      to the in-process app's URL, then using `restore_coordinator()` which
      recreates the coordinator from the session -- but `restore_coordinator()`
      creates a new `httpx.AsyncClient` that won't have the ASGI mounts.
  (b) Testing the async `_message()` logic directly by building the
      coordinator with ASGI mounts, saving the session, and then exercising
      the dispatch path.

  The correct approach is (b): replicate the pattern from `TestCommandAssign`.
  Build a real coordinator with ASGI mounts, call
  `coordinator.dispatch_parallel({"echo-agent": "hello direct"})`, verify the
  task result. This tests the same code path as `command_message` in direct
  mode.

- `test_message_relay_mode` -- Build a coordinator with two agents:
  `EchoExecutor` ("echo-agent", port 29911) and `PrefixExecutor("[R] ")`
  ("relay-agent", port 29912). First dispatch "initial payload" to echo-agent
  to get a completed task. Then call `coordinator.relay_output(src_task,
  "relay-agent", "relay context")`. Verify the relay-agent receives the
  relayed content.

- `test_message_missing_team_exits` -- Call `command_message` with a
  nonexistent team name. Verify `SystemExit` is raised.

- `test_message_relay_requires_src_task_id` -- The `_message()` closure checks
  `if not args.src_task_id` when `args.from_agent` is set. Verify that
  providing `--from` without `--src-task-id` logs an error and exits.

**TestCommandSpawn** (subprocess lifecycle)

The `command_spawn` function starts a real subprocess via
`coordinator.spawn_agent()`, waits for it to become ready, and persists PIDs.
Testing this requires a real script that starts an A2A server.

- `test_spawn_arg_parsing` -- Verify the argparse configuration:
  `["spawn", "--name", "my-team", "--agent", "new-agent", "--script",
  "/path/to/script.py", "--port", "12345"]` parses correctly with all
  required fields.

- `test_spawn_missing_required_args` -- Verify that omitting `--name`,
  `--agent`, `--script`, or `--port` raises `SystemExit`.

- `test_spawn_missing_team_exits` -- Call `command_spawn` with a nonexistent
  team name. Verify `SystemExit` is raised (same pattern as other missing-team
  tests).

- `test_spawn_session_persistence` -- Create a helper script that starts a
  minimal A2A server (using `EchoExecutor` + `uvicorn`). Spawn it via
  `coordinator.spawn_agent()`. Verify: (a) the process PID is captured,
  (b) the session is updated with the new member, (c) the spawned process is
  reachable. Clean up by terminating the process.

  Note: This test is more complex due to real subprocess management. If the
  executor determines it is too brittle for CI, the test should be marked
  `@pytest.mark.integration` and the scope limited to arg-parsing and
  session-not-found validation. The PID persistence logic is already covered
  by the `load_spawned_pids` / `save_session` functions tested elsewhere.

**TestMessageArgParsing** (direct parser verification)

- `test_message_parser_from_flag` -- Verify `--from` is stored as
  `from_agent` (not `from`, which is a Python keyword). Parse
  `["message", "--name", "t", "--to", "a", "--content", "x", "--from",
  "b"]` and assert `args.from_agent == "b"`.
- `test_message_parser_src_task_id` -- Parse with `--src-task-id abc` and
  verify `args.src_task_id == "abc"`.

## Parallelization

Phases 1 through 4 are fully independent and can execute in parallel. Each
phase creates or extends a different test file and tests a different CLI module:

- Phase 1: `test_main_cli.py` (new file, tests `__main__.py`)
- Phase 2: `test_spec_cli.py` (new file, tests `spec_cli.py`)
- Phase 3: `test_subagent_cli.py` or extends `test_integration.py`
  (tests `subagent_cli.py`)
- Phase 4: extends `test_team_cli.py` (tests `team_cli.py`)

All four phases touch separate test files and separate source modules.
No ordering dependency exists. A team of 4 sub-agents can execute all
phases simultaneously.

Within Phase 2, the spec_cli tests are the largest body of work (~30+ test
methods across 4 test classes). If Phase 2 needs further decomposition, split
into Phase 2a (help + arg parsing) and Phase 2b (functional + dispatch routing).

## Verification

**Per-phase gate:** Each phase must pass `python -m pytest
src/vaultspec/tests/cli/ -x -q` before being considered complete.

**Success criteria:**

- `test_main_cli.py` exists with at least 14 passing test methods covering
  --help, --version, all 4 namespace routes, and spec_cli fallthrough.
- `test_spec_cli.py` exists with at least 25 passing test methods covering
  all 11 resource groups (help text + arg parsing) and functional tests for
  `doctor`, `readiness`, `init`, `rules list`, and `hooks list`.
- `subagent_cli.py` arg parsing tests cover all flags on the `run` subcommand
  (14 flags), all flags on `a2a-serve` (5 flags), and 3 validation error
  paths. At least 20 new test methods.
- `test_team_cli.py` gains at least 8 new test methods covering `message`
  (direct + relay + error paths) and `spawn` (arg parsing + error paths).

**Coverage verification:**

After all phases complete, run the full test suite:
`python -m pytest src/vaultspec/tests/cli/ -v --tb=short`

All CLI entry points should have at least:
- Help text verification (every subcommand reachable via `--help`)
- Argument parsing verification (all flags parsed to correct types/defaults)
- Validation verification (missing required args produce `SystemExit`)
- At least one functional test per stateless command

**Known limitations:**

- Commands that require live API keys (`subagent run`, `team create` with real
  agents) cannot be tested without external services. These are covered by arg
  parsing and validation tests only.
- The `mcp` namespace route (`__main__.py` -> `mcp_server.app.main()`) is not
  tested by this plan because MCP server testing has its own dedicated test
  suite at `src/vaultspec/mcp_server/tests/`.
- `spec_cli.py`'s `sync-all`, `config sync`, `system sync`, `rules sync`,
  `agents sync`, and `skills sync` commands mutate the filesystem. Functional
  tests for these should use `tmp_path` isolation and are included in Phase 2
  handler tests where feasible.
- The `test` command in `spec_cli.py` invokes `subprocess.run(pytest ...)`.
  Testing it would create recursive pytest invocation. It is covered by arg
  parsing only.
