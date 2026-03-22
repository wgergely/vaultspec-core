---
tags:
  - '#audit'
  - '#code-health'
date: '2026-02-18'
---

# Code Health Audit: Core, Vault, Orchestration, Hooks

## Executive Summary

All four modules (core, vault, orchestration, hooks) are well-structured and follow consistent Python best practices with proper type hints and clean separation of concerns. Test integrity is high across the board — zero mocking of production behavior was found, tests exercise real code paths with real file I/O and real subprocess execution. The primary critical findings are: a structural misplacement of tests (vault/tests/test_core.py spans orchestration code and does not belong in the vault test directory), a duplicate fixture (`test_agent_md`) defined in both `vault/tests/conftest.py` and `lib/tests/conftest.py`, a suspicious cross-module import in `vault/tests/conftest.py` (`from protocol.providers.base import GeminiModels`), and two placeholder integration tests that `pytest.skip()` unconditionally (test_interactive.py).

______________________________________________________________________

## Module: core

### Code Quality

`core/config.py` is the sole production file (config.py + __init__.py).

__Strengths:__

- `get_config()` singleton is cleanly separated from `reset_config()` — good for testing.
- Validation is thorough: option lists, min/max ranges, type parsing, all with graceful fallback to defaults rather than crashes.
- Stdlib-only — no third-party dependencies.
  \_\_

__Weaknesses / Smells:__

- `CONFIG_REGISTRY` is a module-level mutable list (`list[ConfigVariable]`). Tests mutate it in-place (`CONFIG_REGISTRY.clear()` / `CONFIG_REGISTRY.extend(original)`) inside try/finally blocks. This is fragile — if `from_environment()` raises before the finally, cleanup still runs, but the pattern is risky with threading or session-level fixtures. A context manager or fixture factory would be safer.
- `_parse_raw()` has deeply nested if/elif chains; refactoring to a dispatch dict would reduce cognitive complexity.
- `get_config()` does not document that it is not thread-safe for the singleton initialization (TOCTOU race between `if _cached_config is None` and the assignment). Fine for current usage but worth noting.

### Test Integrity

__ore/tests/test_config.__\` — 436 lines, comprehensive.

__Assessment: EXCELLENT.__ No mocks. Tests directly call `VaultSpecConfig()`, `VaultSpecConfig.from_environment()`, `get_config()`, and `reset_config()` with real env var manipulation via `monkeypatch`.

- `_clean_env_and_singleton` autouse fixture correctly strips all `VAULTSPEC_*` env vars before each test and resets the singleton.
- `TestDefaults` — verifies all defaults against hardcoded expected values. Meaningful: will catch silent drift if defaults change.
- `TestEnvVarLoading` — uses `monkeypatch.setenv` and calls `from_environment()`. Real behavior tested.
- `TestOverrideDict` — tests override dict priority. Real behavior.
- `TestIntParsing`, `TestFloatParsing`, `TestCsvListParsing`, `TestPathParsing` — real parsing, not mocked.
- `TestOptionValidation`, `TestRangeValidation` — explicitly test fallback-to-default on invalid values.
- `TestRequiredVars` — mutates `CONFIG_REGISTRY` directly. Covered by try/finally cleanup. Meaningful test for real error path.
- `TestSingleton` — tests caching identity, cache miss afte\_\_reset, override bypass.\_\_
- `TestIsolation` — tests that env var changes don't leak between tests (relies on autouse fixture).
- `TestRegistry` — hardcodes `len(CONFIG_REGISTRY) == 34`. __This is a fragile count assertion__ — adding a new config var will break this test with no descriptive failure message.
  __\`TestHelperParser__ — unit tests for standalone helper functions.

__Missing coverage:__

- No test for `_parse_raw()` with `_OptionalInt` parsing failure (e.g., `VAULTSPEC_MAX_TURNS=abc`).
- `test_registry_count` is a fragile count assertion (will break silently-differently from what you'd expect when a var is added).

______________________________________________________________________

### \_\_ssues\_\_ound

______________________________________________________________________

1. __[LOW]__ `test_registry_count` hardcodes `34` — maintenance trap. Better: test structural invariants rather than count.
1. __[LOW]__ `CONFIG_REGISTRY` mutation in tests is fragile (try/finally pattern in test body; should be a fixture).
1. __[LOW]__ `get_config()` singleton initialization is not thread-safe (minor, since called from single-threaded CLI startup).

______________________________________________________________________

## Module: vault

### Code Quality

\_\_

Five production files: `models.py`, `links.py`, `scanner.py`, `parser.py`, `hydration.py`.

__models.py:__

\_\_`DocType(__rEnum)` — clean, self-documenting, leverages `StrEnum` correctly.

- `DocumentMetadata.validate()` — returns `list[str]` errors rather than raising. Good pattern.

- `VaultConstants` — awkward design: has a class-level `DOCS_DIR = ".vault"` constant labeled "backwards-compat default", and a `_get_docs_dir()` staticmethod that hits `get_config()`. This split creates a maintenance burden — callers must know which to use. The comment "prefer \_get_docs_dir()" is buried and easy to miss.

- Clean, minimal, correct regex for wiki-links with alias support.

- Handles malformed links gracefully with debug/warning logging.

__scanner.py__\_

- No error handling for `docs_dir.rglob()` failures (e.g., permission errors).
  \_\_

__parser.py:__

- PyYAML optional with stdlib fallback — smart.

- The custom `parse_vault_metadata()` is a hand-rolled YAML state machine for lists. It duplicates logic that `parse_frontmatter()` + PyYAML would handle. The two parser functions coexist and callers must choose — a unified entry point would reduce surface area.

- The fallback `_simple_yaml_load` does not handle multi-line values or lists — these silently produce wrong results rather than raising.
  \_\_
  __hydration.py:__
  \_\_

- Very simple string replacement. Works, but fragile for complex templates. The comment "In a real system, we might use a more robust template engine" acknowledges this.
  \_\_`get_template_path()` returns\_\_None`if file doesn't exist but returns a`Path`if the`doc_type\` mapping exists and the file is present. Callers must null-check.

__# Test Integrity__

__vault/tests/test_types.p__\_ —\_\_OOD. Real be\_\_vior, no mocks. Tests `DocType` enum, `DocumentMetadata.validate()`, `VaultConstants.validate_filename()`, and `parse_vault_metadata()` with inline YAML strings.

__vault/tests/test_links.py__ — GOOD. Pure unit tests for regex-based link extraction. No mocks, meaningful edge cases covered.
__vault/tests/test_hydration.py__ — GOOD. Real string replacement tests. `TestGetTemplatePath` uses `PROJECT_ROOT` (real filesystem) to verify templates exist. Meaningful.
__vault/tests/test_scanne\_\_py__\_— GOOD.\_\_ests against real `TEST_PROJECT` vault. Uses `autouse` fixture to reset config singleton. Tests are meaningful — they verify actual file counts, known file names, and doc type inference.

__vault/tests/test_core.py__ — __PROBLEMATIC.__ This file is mislocated and has a scope problem:\_\_\_\_

- It tests `TestParseFrontmatter`, `TestSafeReadText`, and `TestLoadAgent` — the latter two have nothing to do with vault.
- __These tests belong in `orchestration/tests/`, not `vault/tests/`.__

______________________________________________________________________

__v\_\_t/tests\_\_onftest.py__ — __ISSUES:__

______________________________________________________________________

1. \_\_ports\_\_from protocol.providers.base import GeminiModels`to construct the`test_agent_md`fixture content. This creates a cross-module dependency from a vault test fixture into the protocol module — tests in`vault/`should not depend on`protocol/\`.

1. \_\_e `te___agent_md` fixture is defined here AND in `lib/tests/conftest.py` with identical content. This is a __duplicate fixture__.

1. The `test_root_dir` fixture creates a `.vaultspec/agents/` directory and a `.vault/adr/` directory — clearly designed to support `TestLoadAgent` in `test_core.py`, confirming that those orchestration tests were moved to the wrong file.

### Issues Found

1. __[HIGH]__ `vault/tests/test_core.py` is mislocated — it tests `orchestration.subagent` (load_agent) and `orchestration.utils` (safe_read_text) but lives in `vault/tests/`. Tests should be in `orchestration/tests/`.
1. __[MEDIUM]__ `vault/tests/conftest.py` imports `from protocol.providers.base import GeminiModels` — cross-module coupling violates test isolation (vault tests should not import from protocol).
1. __[MEDIUM]__ `test_agent_md` fixture is duplicated between `vault/tests/conftest.py` and `lib/tests/conftest.py`.
1. __[LOW]__ `VaultConstants.DOCS_DIR` class attribute vs. `_get_docs_dir()` method creates confusing dual-path for callers.
1. __[LOW]__ `parse_vault_metadata()` and `parse_frontmatter()` serve overlapping purposes — two custom parsers for the same input format increases maintenance burden.
   \_\_ __[LOW]__ `__imple_yaml_load` fallback silently produces wrong results for multi-line/list values.

______________________________________________________________________

## \_\_odule:\_\_rchestration

### Code Quality

Four production files: `subagent.py`, `task_engine.py`, `utils.py`, `constants.py`.
\_\_

__subagent.py:__

- `load_agent()` and `get_provider_for_model()` are clean, readable, well-typed.

- `run_subagent()` is large (170+ lines) but appropriately complex given the ACP lifecycle it manages. The AsyncExitStack pattern is correct for multi-resource cleanup.

- __Issue:__ `session_id = resume_session_id or str(asyncio.get_event_loop().time())` — using `asyncio.get_event_loop()` is deprecated in Python 3.10+. Should use `asyncio.get_running_loop()` inside an async context.

- __Issue:__ The bare `except Exception:` at line 322 swallows all errors and returns a `SubagentResult` with empty fields. This means callers cannot distinguish "agent ran and produced no output" from "agent crashed". The `logger.exception()` call only helps if logs are visible.

- __Issue:__ `finally` block uses `if "spec" in locals():` — this is a code smell. The `spec` variable should always be bound (it's in the normal path before the try), or the guard is unnecessary and misleading.
  \_\_`_interac__ve_loop()` uses `asyncio.get_event_loop()` (deprecated in 3.10+) at line 141.

- Unused assignments: `_ = agent_name` and `_ = logger_instance` at lines 118-119 are silent discard patterns — these parameters are declared but never used in `_interactive_loop`. The function signature should be trimmed or the variables actually used.

__task_engine.py:__

\_\_`TaskEngine`\_\_d `LockManager` are well-designed, thread-safe (using `threading.Lock`).

- State machin via `_VALID_TRANSITIONS` dict is clear and auditable.
- `is_terminal()` and `generate_task_id()` are good standalone helpers.
- `wait_for_update()` / `_notify()` properly use `asyncio.Event` for async coordination.
- __Issue:__ `create_task()` does not set a TTL expiry for the working task — only terminal states get TTL. Tasks that stay `WORKING` indefinitely will never be evicted. This could be a memory leak for long-running or abandoned tasks.
  ____Issue:__ `_cleanup_expired()` is call__ inside the lock in `create_task()`, `get_task()`, and `list_tasks()` — but NOT in `update_status()`, `complete_task()`, or `fail_task()`. Inconsistent cleanup trigger.

__utils.py:__

- `safe_read_text()` correctly uses `Path.resolve()` and `is_relative_to()` for security.

- Both functions are concise and well-documented.

__constants.py:__

\_\_Single constant `READONLY_PERMISSION_PR__PT`__Clean.__

### Test Integrity

- Tests actual state transitions, lock acquisition/release, TTL eviction with real `time.sleep()`.
- `__st_locks__eleased_on_*` tests verify the integration between `TaskEngine` and `LockManager`.

______________________________________________________________________

__o\_\_hestrati__/tests/test_utils.py\_\_ — GOOD. Real filesystem access.

______________________________________________________________________

- `__st_re__s_nested_file` uses a real file from `TEST_PROJECT`.

- `test_raises_security_error_for_path_outside_workspace` tests real security enforcement.

- `test_finds_git_root` uses `monkeypatch.chdir(TEST_PROJECT)` and expects real `.git` discovery.

__orchestration/tests/test_interactive.py__ — __PROBLEMATIC.__ Two tests that unconditionally call `pytest.skip()`. These are placeholders with no value:

- They are marked `@pytest.mark.integration` and `@pytest.mark.asyncio` but skip immediately.
- They occupy test infrastructure (collection, async setup) without providing coverage.
- Either delete them or provide real integration test implementations.

\_\_# Issues F\_\_nd

1. __[HIGH]__ `test_interactive.py` — two tests unconditionally `pytest.skip()`. These are dead placeholders and should be removed or implemented.
1. __[MEDIUM]__ `asyncio.get_event_loop()` deprecated usage in `run_subagent()` (line ~221) and `_interactive_loop()` (line 141). Should be `asyncio.get_running_loop()`.
1. __[LOW]__ `_interactive_loop()` has unused parameters `agent_name` and `logger_instance` that are silently discarded.
1. __[LOW]__ `finally` block `if "spec" in locals():` is a code smell — `spec` is always bound before the try block in the success path.
   \_\_

______________________________________________________________________

## Module: hooks

### Code Quality

One production file: `engine.py`.
\_\_
__Strengths:__

- Clean dataclass hierarchy: `HookAction`, `Hook`, `HookResult`.
- `load_hooks()` handles both `.yaml` and `.yml` extensions.
- `_parse_yaml()` has a graceful fallback for missing PyYAML.
- `trigger()` correctly filters by event and `enabled` flag.
- `_interpolate()` is a safe, explicit string replacement (no eval/format risks).
- Error handling: timeouts, exceptions, and failures all produce `__okResult` objects rather t\_\_n raising — good for non-fatal hook execution.

__Weaknesses / Smells:__

- `_execute_agent()` uses a hardcoded relative path computation: `scripts = _Path(__file__).resolve().parent.parent.parent` — fragile if the file moves or the project layout changes. Should use `core.config.get_config().framework_dir` instead.
  \_\_`load_hooks()` si\_\_ntly logs and continues on parse failures (line 108, 116). This is intentional for robustness, but there is no summary count of skipped hooks at info level — only individual warnings per failure.

- No type annotation on `_parse_yaml()` return type (it's `dict[str, Any]` but not declared).

- `shell=True` in `subprocess.run()` (line 232) is a security concern when `command` contains user-controlled content from YAML files. Template interpolation via `_interpolate()` partially mitigates this, but if a YAML hook file contains shell metacharacters in the command string, injection is possible.

### Test Integrity

## hooks/tests/test_hooks.py - GOOD. No mocks. Tests exercise real behavior

- `__stSuppor__dEvents` — verifies frozenset contents. Meaningful.

- `__stPar__Action` — tests real parsing logic with dict inputs.

- `__stPar__Hook` — uses real `tmp_path` for path construction. No mocking of file I/O.

- `TestLoadHooks` — writes real YAML files to `tmp_path` and loads them. Real behavior.

- `TestInterpolate` — pure function unit tests.

- `TestTrigger`:

  - `test_shell_execution` runs `echo hello` and verifies output. __Real subprocess execution.__

  - `test_context_interpolation` runs `echo {root}`. Real execution.

  - `test_failing_command` runs `exit 1`. Real failure assertion.

  - All good — no mocks, real subprocess calls.

__Missing coverage:__

- No test for `_execute_agent()` — the agent dispatch path is entirely untested.
- No test for shell timeout (60s timeout in `_execute_shell()`).

### Issues Found

1. __[MEDIUM]__ `_execute_agent()` uses hardcoded path traversal (`parent.parent.parent`) to locate `subagent.py` — fragile coupling to filesystem layout.

1. __[MEDIUM]__ `shell=True` with user-controlled YAML content creates potential shell injection risk.

1. __[LOW]__ `_execute_agent()` is entirely untested.

1. __[LOW]__ `_parse_yaml()` missing return type annotation.

______________________________________________________________________

## --\_\_\_

## conftest.py Audit

### lib/conftest.py (common ancestor)

______________________________________________________________________

- Clean. Re-exports `PROJECT_ROOT`, `TEST_PROJECT`, `TEST_VAULT` from `tests.constants`.
- No fixtures defined here. Appropriate for a root conftest.

### lib/tests/conftest.py (functional test conftest)

- Defines session-scoped `rag_components` and `rag_components_full` fixtures — correct scope for GPU-heavy setup.
- Defines `test_agent_md` fixture (function-scoped). __DUPLICATE__ — same fixture exists in `vault/tests/conftest.py`.
- D\_\_ines `vaultspec_config`\_\_`config_override`, `clean_config` — config management fixtures. These are not used in any of the modules under audit but are available to all functional tests.
- `_vault_snapshot_reset` autouse session fixture runs `git checkout -- test-project/.vault/` after the full session — good practice for preserving seed corpus.
- N\_\_unsupported markers used.\_\_

### __ore/tests/conftest.py__

- E\_\_ty (just a docstring). Cor\_\_ct — core tests use `monkeypatch` from pytest builtins, no additional fixtures needed.

### __ault/tests/conftest.py__

- \___SSUE 1:__ Imports `from protoco__providers.base import GeminiModels` to build `test_agent_md` fixture. This cross-module import is inappropriate for a vault test conftest.
- __ISSUE 2:__ `test_agent_md` is duplicated from `lib/tests/conftest.py`.
- \___SSUE 3:__ `test_root_dir` fixture creates `.__ultspec/agents/` and `.vault/adr/` — this is agent/orchestration test infrastructure, not vault infrastructure. Confirms that `test_core.py` (which uses this fixture for orchestration tests) is mislocated.

### __rchestration/tests/conftest.py__

- E\_\_ty (just a docstring). Appropriate —chestration tests either self-contain or use `tmp_path`.
- __Note:__ Given that `vault/tests/test_core.py` tests orchestration behavior and uses `vault/tests/conftest.py` fixtures, moving those tests to `orchestration/tests/` would require moving the `test_root_dir` and `test_agent_md` fixtures here as well.

______________________________________________________________________

______________________________________________________________________

## Critical Findings

Ranked by severity:

1. __[HIGH] Mislocated tests__ — `vault/tests/test_core.py` tests `orchestration.subagent.load_agent` and `orchestration.utils.safe_read_text`. These belong in `orchestration/tests/`. The file name ("core") is misleading — it imports nothing from vault.models or vault.core.

1. __[HIGH] Dead placeholder tests__ — `orchestration/tests/test_interactive.py` contains two tests that unconditionally `pytest.skip()`. They waste collection time and create false impressions of test coverage.

1. __[MEDIUM] Cross-module import in vault conftest__ — `vault/tests/conftest.py` imports `from protocol.providers.base import GeminiModels`. Vault tests should not depend on protocol internals.

1. __[MEDIUM] Duplicate fixture__ — `test_agent_md` is defined in both `vault/tests/conftest.py` and `lib/tests/conftest.py`. Pytest will use the closer-scope one in practice, but this creates confusion and maintenance risk if they diverge.

1. __[MEDIUM] Broad exception swallowing in run_subagent()__ — bare `except Exception:` in `orchestration/subagent.py` makes failures invisible to callers. Should at minimum re-raise after logging, or propagate a typed error.

1. __[MEDIUM] Deprecated asyncio API__ — `asyncio.get_event_loop()` used in `subagent.py` and `_interactive_loop()`. Deprecated since Python 3.10, raises `DeprecationWarning` in Python 3.12+.

1. __[MEDIUM] TaskEngine working-task memory leak__ — tasks that never reach a terminal state have no TTL. A task that gets stuck in `WORKING` will never be evicted by `_cleanup_expired()`.

1. __[MEDIUM] Shell injection risk in hooks__ — `subprocess.run(cmd, shell=True)` in `hooks/engine.py` where `cmd` is assembled from user-authored YAML files via template interpolation. Context values could contain shell metacharacters.

1. \_\_[LOW] _execute_agent() hardcoded path_\_ — uses `parent.parent.parent` to find `subagent.py` instead of using `get_config().framework_dir`.

1. __[LOW] test_registry_count hardcodes 34__ — fragile count assertion in `core/tests/test_config.py`. Prefer structural integrity tests over count checks.
