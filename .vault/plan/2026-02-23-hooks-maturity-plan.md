---
tags:
  - "#plan"
  - "#hooks-maturity"
date: "2026-02-23"
related:
  - "[[2026-02-23-hooks-maturity-adr]]"
  - "[[2026-02-23-hooks-maturity-research]]"
---
# hooks-maturity implementation plan

Harden the hooks system from prototype (2/5) to production-ready (4/5). Fix
safety-critical engine bugs, wire automatic lifecycle triggers, improve test
coverage, and create user-facing documentation. All changes follow the
accepted [[2026-02-23-hooks-maturity-adr]].

## Proposed Changes

Three phases, ordered by dependency and risk. Phase 1 fixes engine bugs that
would propagate through auto-triggers. Phase 2 wires the triggers. Phase 3
validates and documents.

## Tasks

- Phase 1 — Engine Hardening
    1. Task 1a: Process safety — kill timed-out subprocesses
    2. Task 1b: Platform safety — fix shlex for Windows
    3. Task 1c: Agent dispatch — fix broken subagent invocation
    4. Task 1d: Remove YAML fallback parser
    5. Task 1e: Deduplicate yaml/yml hook loading
    6. Task 1f: Re-entrant trigger safety guard
- Phase 2 — Auto-Trigger Wiring
    1. Task 2a: Wire lifecycle hook triggers into CLI commands
    2. Task 2b: Remove dead vault.document.modified event
- Phase 3 — Tests and Documentation
    1. Task 3a: Test hardening
    2. Task 3b: Documentation

---

### Task 1a: Process safety — kill timed-out subprocesses

**File:** `src/vaultspec/hooks/engine.py`

**What:** In `_execute_shell()` (line ~365) and `_execute_agent()` (line ~431),
the `subprocess.TimeoutExpired` handler catches the exception but does not kill
the child process. This leaks zombie processes.

**Changes:**
- In `_execute_shell()`: change `subprocess.run()` to `subprocess.Popen()` so
  we have a handle to the process. Wrap in try/finally. On `TimeoutExpired`,
  call `process.kill()` then `process.communicate()` before returning the
  failure result.
- Apply the same pattern in `_execute_agent()`.

**Acceptance criteria:**
- Timed-out shell processes are killed (no zombies)
- Timed-out agent processes are killed (no zombies)
- Existing `test_shell_execution` and `test_context_interpolation` still pass

---

### Task 1b: Platform safety — fix shlex for Windows

**File:** `src/vaultspec/hooks/engine.py`

**What:** `shlex.split(cmd)` at line ~352 uses POSIX tokenization by default.
On Windows, backslash-containing paths are incorrectly split.

**Changes:**
- Replace `shlex.split(cmd)` with `shlex.split(cmd, posix=(os.name != "nt"))`
  in `_execute_shell()`.
- Add `import os` at the top of the file.

**Acceptance criteria:**
- Shell hooks with Windows-style paths (backslashes) tokenize correctly
- POSIX systems still use POSIX tokenization
- Existing shell execution tests still pass

---

### Task 1c: Agent dispatch — fix broken subagent invocation

**File:** `src/vaultspec/hooks/engine.py`

**What:** `_execute_agent()` (lines ~404-418) hardcodes a path to
`framework_dir/lib/scripts/subagent.py` which does not exist. It also uses
`--task` but the actual subagent CLI expects `--goal`.

**Changes:**
- Replace the entire command construction block (lines ~404-418) with:
  ```python
  cmd = [
      sys.executable, "-m", "vaultspec", "subagent", "run",
      "--agent", action.agent_name,
      "--goal", task_text,
  ]
  ```
- Remove the `from ..config import get_config` import and the
  `fw = Path(get_config().framework_dir)` line since they are no longer needed.
- Keep using `subprocess.Popen` (or `run`) with `timeout=300`.

**Acceptance criteria:**
- Agent hooks invoke `vaultspec subagent run --agent <name> --goal <task>`
- No hardcoded filesystem paths remain in `_execute_agent()`
- `--task` flag is replaced with `--goal`

---

### Task 1d: Remove YAML fallback parser

**File:** `src/vaultspec/hooks/engine.py`

**What:** `_parse_yaml()` (lines ~126-134) has an `except ImportError` fallback
that implements a line-by-line key-value parser. This fallback silently produces
broken hooks because it cannot parse YAML lists. PyYAML is already a hard
dependency.

**Changes:**
- Delete the `except ImportError` block (lines ~126-134).
- The function should simply be:
  ```python
  def _parse_yaml(text: str) -> dict[str, Any]:
      import yaml
      return yaml.safe_load(text) or {}
  ```
- Update the docstring to remove mention of fallback parsing.

**Acceptance criteria:**
- `_parse_yaml` uses only `yaml.safe_load`
- No fallback parser code remains
- All existing `TestLoadHooks` tests still pass

---

### Task 1e: Deduplicate yaml/yml hook loading

**File:** `src/vaultspec/hooks/engine.py`

**What:** `load_hooks()` (lines ~155-172) runs two separate glob passes for
`*.yaml` and `*.yml`. If both `hook.yaml` and `hook.yml` exist, the hook
executes twice.

**Changes:**
- Merge the two glob passes into a single collection. Gather all `.yaml` and
  `.yml` files, group by stem name, prefer `.yaml` over `.yml`, and log a
  warning if a duplicate is found.
- Implementation approach:
  ```python
  seen: dict[str, Path] = {}
  for ext in ("*.yaml", "*.yml"):
      for path in sorted(hooks_dir.glob(ext)):
          if path.stem in seen:
              logger.warning(
                  "Duplicate hook '%s': using %s, ignoring %s",
                  path.stem, seen[path.stem].name, path.name,
              )
              continue
          seen[path.stem] = path
  for path in seen.values():
      # parse each...
  ```

**Acceptance criteria:**
- Only one hook is loaded per stem name
- `.yaml` takes precedence over `.yml`
- A warning is logged for duplicate stems
- Existing `test_loads_yaml` and `test_loads_yml` still pass

---

### Task 1f: Re-entrant trigger safety guard

**File:** `src/vaultspec/hooks/engine.py`

**What:** No guard exists against recursive hook triggers. If a hook action
causes an event that re-fires the same hook, infinite recursion occurs.

**Changes:**
- Add a module-level `_triggering: set[str] = set()` variable.
- In `trigger()`, check `if event in _triggering` and return early with a
  warning. Add the event to `_triggering` before execution, remove it in a
  `finally` block.

**Acceptance criteria:**
- Recursive trigger of the same event is blocked with a warning log
- Normal (non-recursive) triggering is unaffected
- The `_triggering` set is cleaned up even if an exception occurs

---

### Task 2a: Wire lifecycle hook triggers into CLI commands

**Files:**
- `src/vaultspec/hooks/engine.py` — add `fire_hooks()` public helper
- `src/vaultspec/hooks/__init__.py` — re-export `fire_hooks`
- `src/vaultspec/vault_cli.py` — wire into `handle_create`, `handle_index`,
  `handle_audit`
- `src/vaultspec/spec_cli.py` — wire into `sync-all` handler

**What:** The core value proposition of the hooks system — automatic lifecycle
triggers — is not implemented. Zero events fire automatically.

**Changes:**
- Add a `fire_hooks(event, ctx)` function in `engine.py` that wraps
  `load_hooks()` + `trigger()` in a blanket try/except that logs at debug
  level but never raises:
  ```python
  def fire_hooks(event: str, context: dict[str, str] | None = None) -> None:
      try:
          from ..core import types as _t
          hooks = load_hooks(_t.HOOKS_DIR)
          trigger(hooks, event, context)
      except Exception:
          logger.debug("Hook trigger failed for %s", event, exc_info=True)
  ```
- Re-export `fire_hooks` from `__init__.py`.
- Wire into four lifecycle points:
  - `vault_cli.py:handle_create` — after `create_vault_doc()` succeeds, call
    `fire_hooks("vault.document.created", {"path": str(doc_path), "root": str(args.root), "event": "vault.document.created"})`
  - `vault_cli.py:handle_index` — after `result = index(...)` succeeds, call
    `fire_hooks("vault.index.updated", {"root": str(root_dir), "event": "vault.index.updated"})`
  - `vault_cli.py:handle_audit` — at the end of `handle_audit`, call
    `fire_hooks("audit.completed", {"root": str(root_dir), "event": "audit.completed"})`
  - `spec_cli.py` sync-all block (line ~365-372) — after all syncs complete
    and before the "Done." log, call
    `fire_hooks("config.synced", {"root": str(_t.ROOT_DIR), "event": "config.synced"})`

**Acceptance criteria:**
- `vault create` fires `vault.document.created` after doc creation
- `vault index` fires `vault.index.updated` after indexing
- `vault audit` fires `audit.completed` after audit
- `sync-all` fires `config.synced` after all syncs
- Hook failures never crash the parent command (blanket except)
- `fire_hooks` is exported from `vaultspec.hooks`

---

### Task 2b: Remove dead vault.document.modified event

**File:** `src/vaultspec/hooks/engine.py`

**What:** `vault.document.modified` has no trigger path — no edit command
exists. It misleads users.

**Changes:**
- Remove `"vault.document.modified"` from the `SUPPORTED_EVENTS` frozenset.
- Update the module docstring to remove the `vault.document.modified` line.

**Acceptance criteria:**
- `vault.document.modified` is not in `SUPPORTED_EVENTS`
- Module docstring lists only 4 events
- `TestSupportedEvents.test_expected_events` is updated to match (coordinate
  with Task 3a)

---

### Task 3a: Test hardening

**File:** `src/vaultspec/hooks/tests/test_hooks.py`

**What:** Fix broken tests and add coverage for new functionality. All tests
must exercise real code paths — no mocking allowed.

**Changes:**
- **Fix `test_failing_command`** (line ~268): Replace `command="exit 1"` with
  `command='python -c "import sys; sys.exit(1)"'` — this is a real executable
  that returns non-zero.
- **Update `test_expected_events`**: Remove `vault.document.modified` from the
  expected set (matches Task 2b).
- **Add `TestDeduplication`**: Create both `hook.yaml` and `hook.yml` in
  `tmp_path`, call `load_hooks()`, assert only one hook is loaded.
- **Add `TestReentrantGuard`**: Create a hook, verify that calling `trigger()`
  while already inside a trigger for the same event returns `[]`.
- **Add `TestProcessTimeout`**: Create a hook with a long-running command
  (e.g., `python -c "import time; time.sleep(120)"`), set a short timeout,
  verify the process is killed (may need to override the timeout constant or
  make it configurable for testing).
- **Add `TestFireHooks`**: Integration test calling `fire_hooks()` with a
  real hook YAML in a temp dir, asserting the shell side-effect occurs.

**Acceptance criteria:**
- `test_failing_command` actually tests non-zero exit code (not FileNotFoundError)
- `test_expected_events` matches the 4-event `SUPPORTED_EVENTS`
- Deduplication is tested
- Re-entrant guard is tested
- `fire_hooks()` is tested end-to-end
- All tests use real code paths — no mocks

---

### Task 3b: Documentation

**Files:**
- `README.md` — add hooks section
- `.vaultspec/docs/hooks-guide.md` — new dedicated guide
- `.vaultspec/docs/cli-reference.md` — expand hooks section
- `.vaultspec/docs/concepts.md` — add hooks subsection
- `.vaultspec/rules/hooks/example-audit-on-create.yaml` — improve example

**What:** The hooks system is invisible in all documentation. A new user cannot
discover, understand, or implement hooks.

**Changes:**
- **README.md**: Add a "Hooks" section (3-4 sentences) after the existing
  feature sections, pointing to the dedicated guide.
- **hooks-guide.md** (new): Dedicated guide covering:
  - What hooks are and when they fire
  - YAML schema with all fields explained
  - Shell action example with all context variables
  - Agent action example
  - Supported events table (4 events with trigger descriptions)
  - Timeout limits (60s shell, 300s agent)
  - Error behavior (hooks never block parent commands)
  - Debugging tips (`--verbose`, `vaultspec hooks run` for manual testing)
- **cli-reference.md**: Expand the hooks section with:
  - Full list of supported event names
  - `--path` semantics explained
  - Example `hooks list` output
  - Example `hooks run` invocation and output
- **concepts.md**: Add a subsection in the workflow section explaining that
  hooks automate post-phase actions.
- **example-audit-on-create.yaml**: Add a commented-out agent action example,
  fix naming guidance, add clear activation instructions.

**Acceptance criteria:**
- README mentions hooks with pointer to guide
- Dedicated guide covers schema, both action types, events, timeouts, errors
- CLI reference lists all 4 event names and explains --path
- Tutorial mentions hooks exist
- Example hook demonstrates both shell and agent actions

## Parallelization

**Phase 1 tasks (1a-1f)** all modify `engine.py` but touch independent
functions. They can be executed by a single agent sequentially, or split across
agents with merge coordination. Recommended: **2 agents** — one handles
1a+1b+1c (execution functions), another handles 1d+1e+1f (parsing/loading/trigger).

**Phase 2 tasks (2a, 2b)** depend on Phase 1 completion (triggers must use the
fixed engine). Task 2b is a subset of 2a changes. Recommended: **1 agent**
handles both sequentially.

**Phase 3 tasks (3a, 3b)** depend on Phases 1+2 completion. They are fully
independent of each other. Recommended: **2 agents in parallel** — one for
tests, one for documentation.

**Optimal team:** 2 agents for Phase 1 (parallel), then 1 agent for Phase 2,
then 2 agents for Phase 3 (parallel). Total: 3-4 agents.

## Verification

- All existing tests pass after Phase 1 (except `test_expected_events` and
  `test_failing_command` which are fixed in Phase 3)
- `vaultspec hooks list` still works after all phases
- `vaultspec hooks run vault.document.created --path /tmp/test` works with a
  real shell hook
- New tests in Phase 3 exercise real subprocesses, real YAML parsing, and real
  hook triggering — no mocks
- Documentation can be manually reviewed for completeness against the schema
  and event list in the engine
- Integration test proves that a lifecycle command (`vault create` or similar)
  actually fires its hook automatically
