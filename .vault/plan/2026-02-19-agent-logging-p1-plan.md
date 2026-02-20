---
tags:
  - "#plan"
  - "#agent-logging"
date: "2026-02-19"
related:
  - "[[2026-02-15-cross-agent-bidirectional-communication]]"
---

# Agent Logging P1 Plan

Centralize agent session log management, fix naming conventions, bridge the
task engine to log files, add a `logs` directory to the vault structure, and
close the Claude provider logging gap. This plan addresses the seven gaps
identified during the logging audit and is informed by research into A2A,
Claude Code, CrewAI, AutoGen, LangGraph, OpenAI Agents SDK, and OTEL GenAI
semantic conventions.

## Proposed Changes

The `SessionLogger` in `protocol/acp/client.py` is the sole log writer. It
hardcodes `.vault/logs/` as the destination and uses monotonic clock floats as
filenames. The `TaskEngine` in `orchestration/task_engine.py` tracks tasks but
has no link to log files. The `DocType` enum in `vault/models.py` does not
recognize `logs/` as a valid vault directory. The `.gitignore` does not exclude
`.vault/logs/`. The Claude provider path emits partial ACP events (tool
arguments and results are not forwarded). Stderr from agent processes is
silently discarded unless `debug=True`.

This plan introduces centralized log path configuration, human-readable log
filenames, task-to-log correlation, vault structure recognition, gitignore
coverage, Claude bridge event completeness, and stderr persistence.

## Tasks

- Phase 1: Config & Vault Structure
    1. Add `logs_dir` to `VaultSpecConfig` — a new attribute `logs_dir: str = "logs"` representing the subdirectory name within `docs_dir`. Add a corresponding `VAULTSPEC_LOGS_DIR` entry to `CONFIG_REGISTRY`. The resolved log path becomes `root_dir / cfg.docs_dir / cfg.logs_dir`.
    2. Add `LOGS = "logs"` to `DocType` enum in `vault/models.py` so that `VaultConstants.validate_vault_structure()` accepts the `logs/` directory.
    3. Add `.vault/logs/` to `.gitignore` — logs are dynamic artifacts that must never be committed.

- Phase 2: SessionLogger Refactor
    1. Move `SessionLogger` out of `protocol/acp/client.py` into its own module at `lib/src/orchestration/session_logger.py`. It is an orchestration concern, not an ACP protocol concern. `SubagentClient` keeps a reference to it but no longer defines it.
    2. Replace the hardcoded path with config-derived path: `root_dir / cfg.docs_dir / cfg.logs_dir`. Import `get_config` to resolve at construction time.
    3. Change log filename convention from `{session_id}.log` to `{date}_{agent}_{task_id}.jsonl`. The format is `YYYY-MM-DDTHH-MM-SS_{agent_name}_{task_id_short}.jsonl` where `task_id_short` is the first 8 characters of the task UUID. This makes logs discoverable by date, agent, and task.
    4. Add a `log_path` read-only property to `SessionLogger` so callers can retrieve the resolved path for correlation.
    5. Add a structured header event: when `SessionLogger` is created, write an initial JSONL entry of type `session_start` containing `agent_name`, `task_id`, `model`, `mode`, `start_time` (ISO 8601), and `root_dir`. This makes each log file self-describing.

- Phase 3: Task-to-Log Correlation
    1. Add `log_file: str | None = None` field to `SubagentTask` dataclass in `task_engine.py`. This stores the workspace-relative path to the JSONL log file.
    2. In `run_subagent()`, pass `agent_name` and `task_id` (when available) to `SessionLogger` so it can construct the filename. When called from MCP `dispatch_agent`, the `task_id` is known; when called from CLI, generate a UUID.
    3. In MCP `dispatch_agent` (`server.py`), after creating the `SessionLogger`, store `logger_instance.log_path` on the task via a new `task_engine.set_log_file(task_id, path)` method.
    4. Expose log file path in `get_task_status` response: include `"log_file": task.log_file` in the JSON output so callers can locate the log.

- Phase 4: Claude Bridge Logging Completeness
    1. In `claude_bridge.py` `_emit_user_message()`: include tool result content in the `ToolCallProgress` update. Extract text from `ToolResultBlock` content and pass it as `raw_input` on the progress notification. This ensures tool outputs flow through ACP to `SubagentClient` and into the JSONL log.
    2. In `claude_bridge.py` `_emit_assistant()`: for `ToolUseBlock`, include `block.input` (the tool arguments) in the `ToolCallStart` notification metadata. ACP's `ToolCallStart` does not have a native field for this, so serialize it into the `title` field as `"{tool_name}: {truncated_args}"` or explore whether `ToolCallProgress` with `status="pending"` and `raw_input=json.dumps(block.input)` is the better fit.
    3. In `run_subagent()` `_read_stderr()`: remove the `if debug:` guard. Always write stderr lines to the `SessionLogger` as events of type `agent_stderr`. This captures diagnostic output from both Gemini CLI and Claude bridge processes regardless of debug mode.

- Phase 5: Log Lifecycle
    1. Add a `log_retention_days: int = 30` field to `VaultSpecConfig` with `VAULTSPEC_LOG_RETENTION_DAYS` env var.
    2. Add a `cleanup_old_logs(root_dir)` function in `session_logger.py` that scans the logs directory, parses the date prefix from filenames, and deletes files older than `log_retention_days`. This is a simple file-age-based cleanup.
    3. Call `cleanup_old_logs()` from two places: (a) `initialize_server()` in `server.py` on MCP server startup, and (b) the CLI `test` or `sync` commands as a maintenance hook.

- Phase 6: Tests
    1. Unit tests for `SessionLogger` in new `lib/src/orchestration/tests/test_session_logger.py`: construction with config, filename format, header event, log writing, `log_path` property.
    2. Unit tests for `SubagentTask.log_file` field and `TaskEngine.set_log_file()`.
    3. Unit tests for `cleanup_old_logs()` with mocked filesystem.
    4. Update existing `test_client.py` and `test_logging_config.py` to account for the `SessionLogger` relocation.
    5. Integration test: verify that `run_subagent()` with a mock provider creates a correctly-named JSONL file containing a `session_start` header and at least one `session_update` event.

## Parallelization

- Phase 1 (config + vault + gitignore) and Phase 4 (Claude bridge) are independent and can run in parallel.
- Phase 2 (SessionLogger refactor) must complete before Phase 3 (correlation) and Phase 5 (lifecycle).
- Phase 6 (tests) spans all phases but individual test groups can run as each phase completes.

Suggested parallel tracks:
- Track A: Phase 1 → Phase 2 → Phase 3 → Phase 5
- Track B: Phase 4 (independent)
- Track C: Phase 6 (continuous, per-phase)

## Verification

- All existing tests pass after refactor (no regressions from `SessionLogger` move).
- New unit tests cover: config-derived log path, filename format `{date}_{agent}_{task_id}.jsonl`, header event schema, task-to-log correlation, log cleanup by age.
- Integration test confirms end-to-end: `dispatch_agent` → `run_subagent` → JSONL file created with correct name → `get_task_status` returns `log_file` path → file contains `session_start` + `session_update` events.
- `DocType.LOGS` is recognized by `VaultConstants.validate_vault_structure()`.
- `.vault/logs/` is gitignored (verify with `git check-ignore .vault/logs/test.jsonl`).
- Claude bridge emits tool arguments and results in ACP updates (verify via mock bridge test checking `ToolCallProgress.raw_input` is populated).
- Agent stderr is captured in JSONL logs regardless of `debug` flag.
