---
tags:
  - '#adr'
  - '#hooks-maturity'
date: '2026-02-23'
related:
  - '[[2026-02-23-hooks-maturity-research]]'
---

# hooks-maturity adr: production-readiness hardening | (**status:** `accepted`)

## Problem Statement

The vaultspec hooks system (maturity 2/5) is architecturally sound but
functionally inert. Zero of 5 declared lifecycle events fire automatically,
agent-type hooks are broken, the engine has platform-safety and process-safety
bugs, test coverage is incomplete, and the feature is invisible in
documentation. The system must be hardened to production-ready status.

## Considerations

- The engine's core abstractions (`Hook`, `HookAction`, `HookResult`,
  `load_hooks`, `trigger`) are clean and should be preserved

- `shell=False` security posture must be maintained

- Hook failures must never block or crash parent CLI commands

- The project runs on Windows 11 — platform safety is mandatory

- The project strictly bans all mocking in tests — real code paths only

- PyYAML is already a hard dependency across the codebase

- The subagent CLI uses `--goal` (not `--task`) and is accessed via
  `vaultspec subagent run`

## Constraints

- Hook execution must be synchronous within the parent command (no background
  threads for v1) to maintain predictable ordering

- Auto-triggers must be safe for concurrent/re-entrant execution (a hook must
  not trigger itself)

- Changes must not alter the public API surface (`__init__.py` exports)

- Documentation must cover all features present in the implementation

- All new code paths must have corresponding tests exercising real execution

## Implementation

Eight work streams, organized into three phases:

### Phase 1 — Engine Hardening (safety-critical fixes)

**1a. Process safety — kill timed-out subprocesses**
In both `_execute_shell()` and `_execute_agent()`, replace the bare
`except subprocess.TimeoutExpired` with proper process cleanup:

```python
except subprocess.TimeoutExpired:
    process.kill()
    process.communicate()
    logger.warning(...)
    return HookResult(hook_name=..., action_type=..., success=False, ...)
```

Files: `engine.py` (~lines 365-371, 431-438)

**1b. Platform safety — fix Windows path handling**
Replace `shlex.split(cmd)` with a platform-aware approach. Pass context
values as separate subprocess arguments instead of interpolating them into
the command string before splitting. Introduce a `_build_command()` helper:

```python
def _build_command(template: str, ctx: dict[str, str]) -> list[str]:
    """Build command args list, passing context values as trailing args."""
    base_parts = shlex.split(template, posix=(os.name != 'nt'))
    return base_parts
```

For the interpolation path, use `shlex.split(cmd, posix=(os.name != 'nt'))`
to respect Windows quoting conventions.
Files: `engine.py` (~lines 285-299, 350-355)

**1c. Agent dispatch fix**
Replace the hardcoded `lib/scripts/subagent.py` path with a
`sys.executable` + module invocation pattern:

```python
cmd = [sys.executable, "-m", "vaultspec", "subagent", "run",
       "--agent", action.agent_name, "--goal", interpolated_task]
```

This uses the same Python interpreter and avoids path resolution issues.
Fix `--task` → `--goal` to match the actual subagent CLI.
Files: `engine.py` (~lines 400-430)

**1d. Remove YAML fallback parser**
Delete the `except ImportError` fallback in `_parse_yaml()`. PyYAML is a
hard dependency (in `pyproject.toml`). The fallback silently produces
broken hooks. Let the `ImportError` propagate naturally.
Files: `engine.py` (~lines 127-133)

**1e. Deduplication — prevent double-loading**
Merge the two glob passes into one, collecting files by stem name. If both
`hook.yaml` and `hook.yml` exist, prefer `.yaml` and log a warning about
the duplicate.
Files: `engine.py` (~lines 155-172)

**1f. Re-entrant safety guard**
Add a module-level `_triggering: set[str]` guard to prevent a hook from
re-triggering the same event recursively:

```python
_triggering: set[str] = set()

def trigger(hooks, event, ctx):
    if event in _triggering:
        logger.warning("Re-entrant hook trigger blocked: %s", event)
        return []
    _triggering.add(event)
    try:
        ...
    finally:
        _triggering.discard(event)
```

Files: `engine.py`

### Phase 2 — Auto-Trigger Wiring + Dead Code Cleanup

**2a. Wire lifecycle triggers**
Add `_fire_hooks(event, ctx)` helper in `src/vaultspec/core/commands.py`
(or a new `hooks/integration.py`) that wraps `load_hooks()` + `trigger()`
in a try/except that logs but never raises:

```python
def _fire_hooks(event: str, ctx: dict[str, str]) -> None:
    try:
        hooks = load_hooks(HOOKS_DIR)
        trigger(hooks, event, ctx)
    except Exception:
        logger.debug("Hook trigger failed for %s", event, exc_info=True)
```

Wire this into four lifecycle points:

- `vault_cli.py:handle_create` → `vault.document.created` after doc write
- `vault_cli.py:handle_index` → `vault.index.updated` after index completes
- `vault_cli.py:handle_audit` → `audit.completed` after audit finishes
- `spec_cli.py` sync-all handler → `config.synced` after all syncs complete

Context dict for each: `{"path": str(path), "root": str(ROOT_DIR), "event": event_name}`

Files: `vault_cli.py`, `spec_cli.py`, `core/commands.py`

**2b. Dead code cleanup**

- Remove `vault.document.modified` from `SUPPORTED_EVENTS` (no trigger
  path exists; re-add when an edit command is implemented)

- Keep `Hook.source_path` (useful for debugging output in `hooks list`)

- Keep `HookResult.output`/`.error` (used by CLI formatting)

Files: `engine.py`

### Phase 3 — Tests + Documentation

**3a. Test hardening**
Fix and add tests (all exercising real code paths, no mocking):

- Fix `test_failing_command`: use a real executable that returns non-zero
  (e.g., `python -c "import sys; sys.exit(1)"`)

- Add `test_agent_action_dispatch`: test `_execute_agent` with a real
  `vaultspec subagent run` invocation (or a known agent that exits quickly)

- Add `test_deduplication`: create both `.yaml` and `.yml` and assert only
  one is loaded

- Add `test_reentrant_guard`: verify that recursive trigger calls are blocked

- Add integration test: write a temp hook YAML, call the lifecycle command,
  assert the hook's shell side-effect occurred (e.g., a file was created)

Files: `hooks/tests/test_hooks.py`

**3b. Documentation**

- **README.md**: Add a "Hooks" section (3-4 lines) with pointer to the
  dedicated guide

- **`.vaultspec/docs/hooks-guide.md`** (new): Dedicated guide covering YAML
  schema, both action types with examples, supported events, context
  variables, timeout limits, error behavior, debugging tips

- **`.vaultspec/docs/cli-reference.md`**: Expand the hooks section with
  supported event names, `--path` semantics, example output

- **`.vaultspec/docs/concepts.md`**: Add a hooks subsection in the
  workflow overview

- **`.vaultspec/rules/hooks/example-audit-on-create.yaml`**: Add an agent
  action example, fix the naming guidance comment, set `enabled: false`
  with clear instructions on activation

Files: `README.md`, `.vaultspec/docs/hooks-guide.md` (new),
`.vaultspec/docs/cli-reference.md`, `.vaultspec/docs/concepts.md`,
`.vaultspec/rules/hooks/example-audit-on-create.yaml`

## Rationale

**Phase ordering:** Safety-critical engine fixes first (Phase 1) because
auto-trigger wiring (Phase 2) would propagate existing bugs to all
lifecycle commands. Tests and docs last (Phase 3) because they validate
the final implementation.

**`_fire_hooks` wrapper with blanket try/except:** Hook failures must never
block the parent command. A logging-only failure mode is the safest
approach for a v1 auto-trigger system. Users can observe failures via
`--verbose` or `--debug` log levels.

**`sys.executable -m vaultspec` for agent dispatch:** Avoids filesystem path
resolution issues, works on all platforms, uses the same Python environment,
and aligns with how the rest of the codebase invokes vaultspec commands.

**Platform-aware shlex:** `shlex.split(cmd, posix=False)` on Windows handles
backslash-in-path correctly without requiring users to escape paths. This is
the minimal-change fix that preserves the existing interpolation model.

**Removing `vault.document.modified`:** No edit command exists. Keeping a
dead event misleads users. It can be re-added when the capability is built.

**Re-entrant guard:** Prevents infinite hook loops (e.g., a hook that creates
a vault document, which fires `vault.document.created`, which triggers
the same hook). Simple set-based guard is sufficient for synchronous
execution.

## Consequences

- All lifecycle commands will gain ~10ms overhead for hook loading (YAML
  parsing of hook files in `.vaultspec/rules/hooks/`)

- Agent-type hooks will now work but add subprocess overhead (up to 300s
  timeout)

- Removing `vault.document.modified` is a breaking change for anyone who
  has hooks targeting it (mitigated: the event never fired anyway)

- The re-entrant guard blocks legitimate recursive patterns (unlikely in
  practice; can be relaxed with a depth counter in v2)

- New documentation file (`.vaultspec/docs/hooks-guide.md`) adds to
  maintenance surface

- Test suite will grow by ~5-7 test functions
