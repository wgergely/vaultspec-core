---
tags:
  - '#research'
  - '#hooks-maturity'
date: '2026-02-23'
---

# hooks-maturity research: production-readiness audit

Comprehensive audit of the vaultspec hooks system conducted by a 4-agent team
(impl-auditor, adoption-auditor, docs-auditor, design-assessor). The hooks
engine was evaluated across implementation quality, codebase adoption,
documentation coverage, and design goal achievement.

## Findings

### 1. Critical Gap: Zero Automatic Hook Triggers

All 5 declared events are never fired automatically by lifecycle commands.
The `trigger()` function is called from exactly one place — the manual
`vaultspec hooks run <event>` CLI command at `src/vaultspec/core/commands.py:629`.

| Event                     | Expected Trigger Point         | Status                  |
| ------------------------- | ------------------------------ | ----------------------- |
| `vault.document.created`  | `vault_cli.py:handle_create`   | **Not wired**           |
| `vault.document.modified` | vault doc edits                | **No edit path exists** |
| `vault.index.updated`     | `vault_cli.py:handle_index`    | **Not wired**           |
| `config.synced`           | `spec_cli.py:sync-all` handler | **Not wired**           |
| `audit.completed`         | `vault_cli.py:handle_audit`    | **Not wired**           |

This renders the hooks system functionally inert — it has the right shape but
no nervous system.

### 2. Implementation Bugs

#### HIGH Severity

- **H1 — Windows shlex breakage** (`engine.py:352`): `shlex.split()` uses
  POSIX tokenization rules. Windows paths with backslashes are incorrectly
  split. The project runs on Windows 11.

- **H2 — Agent dispatch broken** (`engine.py:408`): `_execute_agent()`
  hardcodes `framework_dir/lib/scripts/subagent.py` which does not exist.
  All agent-type hook actions silently fail. Also uses `--task` flag but the
  actual subagent CLI expects `--goal`.

#### MEDIUM Severity

- **M1/M2 — Zombie processes** (`engine.py:365-371`, `431-438`): Timed-out
  subprocesses are never killed. `subprocess.TimeoutExpired` is caught but
  `process.kill()` is never called. Shell timeout is 60s, agent timeout 300s.

- **M3 — Duplicate hook loading** (`engine.py:155-172`): Two glob passes for
  `*.yaml` and `*.yml` with no deduplication. A hook named `my-hook.yaml` and
  `my-hook.yml` would execute twice.

- **M4 — Space-in-path argument corruption** (`engine.py:285-299`): Context
  values are interpolated into command strings before `shlex.split()`. Paths
  containing spaces produce incorrect argument tokenization.

#### LOW Severity

- **L1 — Broken YAML fallback** (`engine.py:127-133`): Fallback parser for
  missing PyYAML cannot handle YAML lists. The `actions:` key silently becomes
  an empty string, producing hooks with zero actions.

- **L2 — Misleading test** (`test_hooks.py:268`): `test_failing_command` uses
  `exit 1` with `shell=False`. Since `exit` is a shell builtin (not an
  executable), the test catches `FileNotFoundError` instead of testing non-zero
  exit codes as intended.

### 3. Dead Code

- `vault.document.modified` event — no trigger path exists anywhere
- `Hook.source_path` field — populated during `load_hooks()`, never read
- `_execute_agent()` — only reachable via manual `hooks run`, and broken
- `HookResult.output`/`.error` — only consumed by CLI output formatting
- `framework_tools.py` MCP stub — Phase 3 TODO, currently a no-op

### 4. Test Coverage Gaps

- **Zero tests** for agent action execution (entire `_execute_agent` path)
- **Zero integration tests** for the CLI → load → trigger → side-effect flow
- `test_failing_command` tests wrong failure mode (see L2)
- No Windows path handling tests
- No timeout behavior tests
- No duplicate `.yaml`/`.yml` deduplication tests
- `vault.document.modified` never appears in any test

### 5. Documentation Assessment — FAILING

| Document                                 | Hooks Mention                                           |
| ---------------------------------------- | ------------------------------------------------------- |
| `README.md`                              | None                                                    |
| `.vaultspec/README.md`                   | None                                                    |
| `.vaultspec/docs/concepts.md` (tutorial) | None                                                    |
| `.vaultspec/docs/cli-reference.md`       | Partial — lists commands, omits schema/events/variables |
| `.vaultspec/docs/search-guide.md`        | None                                                    |

Missing documentation:

- No dedicated hooks guide
- YAML schema not documented outside source code
- No agent action type example
- Supported event names not listed in CLI reference
- Context variable contract (`{path}`, `{root}`, `{event}`) undocumented
- Timeout limits (60s shell, 300s agent) undocumented
- No error/debugging guidance

### 6. Design Assessment

**Maturity: 2/5 — Prototype**

**Strengths:**

- Clean, minimal public API (`load_hooks`, `trigger`, `SUPPORTED_EVENTS`)
- Good security posture (`shell=False`, no shell metacharacter injection)
- Correct error containment (failed hooks don't crash the system)
- Well-factored dataclasses (`Hook`, `HookAction`, `HookResult`)

**Weaknesses:**

- Core value proposition (automatic lifecycle hooks) not implemented
- Agent action type entirely broken
- No platform safety (Windows compatibility)
- No process lifecycle management (zombie cleanup)
- Feature is invisible to users (no documentation path to discovery)

### 7. Comparison to Similar Systems

| Dimension         | vaultspec hooks  | Git hooks     | Husky / pre-commit |
| ----------------- | ---------------- | ------------- | ------------------ |
| Trigger mechanism | Manual CLI only  | Automatic     | Automatic          |
| Config format     | YAML             | Shell scripts | YAML               |
| Action types      | shell, agent     | shell         | shell              |
| Auto-execution    | **None**         | Full          | Full               |
| Context passing   | `{key}` template | Env vars      | Env vars           |

### 8. Recommended Fix Categories

1. **Auto-trigger wiring** — wire `load_hooks()`+`trigger()` into all 4 lifecycle commands
1. **Agent dispatch fix** — use `vaultspec subagent run` CLI, fix `--task`→`--goal`
1. **Process safety** — kill timed-out subprocesses, prevent zombies
1. **Platform safety** — fix Windows path handling in shell actions
1. **Deduplication** — prevent `.yaml`/`.yml` double-loading
1. **Remove dead code** — drop `vault.document.modified` or implement it, remove YAML fallback
1. **Fix tests** — add agent action tests, fix `test_failing_command`, add integration tests
1. **Documentation** — hooks guide, README mention, CLI reference expansion, example improvements

### 9. Files Involved

| File                                                  | Role                                  |
| ----------------------------------------------------- | ------------------------------------- |
| `src/vaultspec/hooks/engine.py`                       | Core engine (447 lines)               |
| `src/vaultspec/hooks/__init__.py`                     | Public API                            |
| `src/vaultspec/hooks/tests/test_hooks.py`             | Unit tests (275 lines)                |
| `src/vaultspec/core/commands.py`                      | `hooks_list`, `hooks_run`             |
| `src/vaultspec/core/types.py`                         | `HOOKS_DIR` path                      |
| `src/vaultspec/spec_cli.py`                           | CLI routing                           |
| `src/vaultspec/__main__.py`                           | Entry point                           |
| `src/vaultspec/vault_cli.py`                          | Lifecycle commands (missing triggers) |
| `src/vaultspec/mcp_server/framework_tools.py`         | MCP stub                              |
| `.vaultspec/rules/hooks/example-audit-on-create.yaml` | Example hook                          |
| `.vaultspec/docs/cli-reference.md`                    | CLI docs                              |
| `.vaultspec/docs/concepts.md`                         | Tutorial                              |
| `README.md`                                           | Project README                        |
