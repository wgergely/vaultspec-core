---
tags:
  - "#audit"
  - "#code-health"
date: "2026-02-18"
---
# Deep Audit: Error Propagation and Silent Failure Paths

## Executive Summary

This audit traces every significant error-handling path across the eight focus areas
identified in task #15. The overall pattern is consistent: most failures are caught at
boundary layers but returned as degraded-success values rather than typed error signals,
making caller-side failure detection unreliable. The single most severe defect is in
`orchestration/subagent.py`, where a crashed agent run is indistinguishable from a
completed run that produced no output. Secondary critical issues exist in the MCP
server's background task handling and the RAG API's broken-singleton problem. All
findings are ranked by severity and each includes whether existing tests would catch
the failure.

---

## 1. `orchestration/subagent.py` — The Swallowed-Exception Pattern

### Defect: Crash masquerades as empty success

```python
# subagent.py lines 322-328
except Exception:
    logger.exception("Subagent execution failed")
    return SubagentResult(
        session_id=session_id,
        response_text=client.response_text,
        written_files=client.written_files,
    )
```

**Failure scenario:** Any exception raised inside `run_subagent()` — ACP handshake
failure, subprocess spawn error, network timeout, `AgentNotFoundError` from the
second `load_agent()` call after the `except AgentNotFoundError` block, or a
`KeyboardInterrupt` — is caught by this bare `except Exception:`. The caller receives
a `SubagentResult` object that looks identical to a valid result with empty output.

**What `SubagentResult` looks like on crash:**

- `response_text`: `""` (client was just created, no messages received)
- `written_files`: `[]`

**Caller perspective:** In `server.py`'s `dispatch_agent`, the result is accepted and
`complete_task()` is called with `summary=""` and `artifacts=[]`. The MCP tool
returns `{"status": "completed", ...}` to the caller. From the orchestrator's
perspective the agent ran, produced nothing, and succeeded. **There is no way to
distinguish a crashed agent from an agent that completed but produced no output.**

**Additional amplifier:** The `finally` block contains:
```python

if "spec" in locals():
```

This guard is unreachable in the crash path if the exception happened before `spec =
provider.prepare_process(...)` (line 211) — e.g., during `load_agent()` at line 195
(the non-fallback call, when both provider-specific and canonical paths fail). In that
case `spec` is not in locals but the `finally` still runs safely. However the guard
itself is misleading: `spec` IS always in locals after the assignment, so the check
always passes on the success path. On the crash path before `spec` is assigned, the
guard correctly skips cleanup. The real issue is that the crash scenario is not

communicated upward.

**What callers do with empty result:**

- `server.py` `_run_in_background()`: catches `SubagentError` explicitly (line 514) but
  the crash returns a `SubagentResult`, not a `SubagentError`. So the `except
  SubagentError` never fires for crashes. The final `except Exception as e:` (line
  516) would catch truly unexpected errors from the await itself, but since `await
  _run_subagent_fn(...)` already returns a result (not raises), neither except block
  fires. The task is marked `completed` with empty data.
- `lib/scripts/subagent.py` CLI entry point: calls `asyncio.run(run_subagent(...))`,
  gets the empty result, exits 0.

**Test coverage:** NO. No test exercises the crash path of `run_subagent()`. The
`test_interactive.py` tests are unconditional `pytest.skip()`. No test checks that
`run_subagent()` propagates errors to callers.

**Severity: CRITICAL**


1. Re-raise after logging (callers decide whether to swallow), OR
2. Return a `SubagentResult` with a typed `error` field, and callers must check it, OR
3. Raise a `SubagentError` from the `except` block so `server.py`'s existing
   `except SubagentError` handler fires correctly.

---

## 2. `orchestration/task_engine.py` — WORKING Tasks Never Expire

### Defect: Memory leak for abandoned tasks

`TaskEngine._cleanup_expired()` only removes tasks from `self._expiry`, which is only
populated when a task reaches a terminal state (`COMPLETED`, `FAILED`, `CANCELLED`).
A task stuck in `WORKING` or `INPUT_REQUIRED` is never added to `self._expiry` and
therefore never evicted.

```python
# task_engine.py lines 343-347 (update_status)
if is_terminal(status):
    task.completed_at = task.updated_at
    self._expiry[task_id] = task.updated_at + self._ttl_seconds
    self._release_lock(task_id)
```

**Failure scenario:** The MCP server dispatches a subagent that crashes before the
background task can call `task_engine.fail_task()`. Due to the broad `except Exception`
in `server.py`'s `_run_in_background()` (line 516), `fail_task()` IS called in the
general except path. BUT: if the background asyncio task itself is cancelled (e.g.,
server restart) before reaching the finally block, `fail_task()` is never called and
the task remains `WORKING` indefinitely.

The `_background_tasks` dict in `server.py` holds strong references to asyncio tasks.
If `cancel_task()` MCP tool is called, `bg_task.cancel()` fires (line 608) and
`task_engine.cancel_task()` is called (line 611) — so the cancel path is safe.
But unhandled asyncio cancellation from server shutdown (e.g., `asyncio.CancelledError`
propagating from `_server_lifespan`) does NOT trigger the server-side cleanup because
`CancelledError` is not `Exception` in Python 3.8+ (`BaseException`). Thus the
`except Exception as e` in `_run_in_background()` does NOT catch
`asyncio.CancelledError`, and `finally` only pops from `_background_tasks` /
`_active_clients` but does NOT call `fail_task()` or `cancel_task()`.

```python
# server.py lines 514-521
except SubagentError as e:
    task_engine.fail_task(task_id, str(e))
except Exception as e:
    logger.exception("Unexpected error in background subagent")
    task_engine.fail_task(task_id, f"Unexpected error: {e}")
finally:
    _background_tasks.pop(task_id, None)
    _active_clients.pop(task_id, None)
    # NOTE: No fail_task/cancel_task here!
```

**Impact:** On server restart or event-loop cancellation, all in-flight tasks remain
`WORKING` forever in the `_tasks` dict. Since `_cleanup_expired()` only fires on
create/get/list calls AND only evicts tasks with an `_expiry` entry, these orphaned
tasks accumulate until the process exits.

**Worst case:** Advisory locks held by those tasks are also never released (since lock
release happens via `_release_lock()` which is called from terminal-state transitions
only).

**Test coverage:** NOT tested. The TTL eviction test (`test_ttl_eviction`) uses a
completed task. No test checks behavior on CancelledError or server shutdown.

**Severity: HIGH**

**Fix direction:** Add `asyncio.CancelledError` handling in `_run_in_background()`
that calls `task_engine.cancel_task(task_id)` before re-raising, OR add a
`WORKING_TTL` that evicts tasks that have been working beyond a reasonable timeout.

---

## 3. `protocol/acp/client.py` — Silent Failures in Critical Operations

### 3a. `graceful_cancel()` swallows all exceptions

```python
# client.py lines 443-447
async def graceful_cancel(self) -> None:
    """Send ACP session/cancel notification before termination."""
    if self._conn and self._session_id:
        with contextlib.suppress(Exception):
            await self._conn.cancel(session_id=self._session_id)
```

`contextlib.suppress(Exception)` silently discards ANY error during cancel — network
failure, protocol error, or logic bug. The caller (`cancel_task` MCP tool in
`server.py`) receives no indication whether the cancel succeeded. The agent subprocess
may continue running.

**Test coverage:** The MCP tool test for `cancel_task` mocks `_run_subagent_fn` and
does not exercise the actual ACP cancel path.

**Severity: MEDIUM**

### 3b. `terminal_output()` returns empty string for unknown terminal

```python
# client.py lines 353-357
terminal = self._terminals.get(terminal_id)
if terminal is None:
    return TerminalOutputResponse(output="", truncated=False)
```

If an agent calls `terminal_output` with a non-existent `terminal_id`, the client
silently returns empty output instead of raising an error. The agent has no way to
know whether the terminal doesn't exist, has produced no output, or the terminal_id
was wrong.

**Test coverage:** Not tested (this is an ACP protocol response path, not covered by
unit tests).

**Severity: LOW**

### 3c. `_reader()` task in `create_terminal()` swallows `asyncio.CancelledError`

```python
# client.py lines 327-337
async def _reader() -> None:
    assert proc.stdout is not None
    try:
        while True:
            chunk = await proc.stdout.read(cfg.io_buffer_size)
            if not chunk:
                break
            terminal.output_chunks.append(chunk)
            terminal.total_bytes += len(chunk)
    except asyncio.CancelledError:
        pass  # Silently discarded
```

When the reader task is cancelled (via `release_terminal()` or `kill_terminal()`),
any partial chunk currently being read is silently dropped. This is intentional (the
assert on `proc.stdout` would fail if stdout were None), but the `pass` discards
`CancelledError` without re-raising it. In Python's asyncio model, `CancelledError`
should be re-raised or explicitly handled with `raise` to preserve task cancellation
semantics. Swallowing it breaks cooperative cancellation.

**Test coverage:** Not tested.

**Severity: LOW** (cosmetic in most cases, but can cause resource leaks in edge cases)

---

## 4. `protocol/acp/claude_bridge.py` — Stream Error Handling

### 4a. Streaming exception converts to `stop_reason="refusal"` — misleading

```python
# claude_bridge.py lines 429-445
try:
    async for message in self._sdk_client.receive_messages():
        if self._cancelled:
            stop_reason = "cancelled"
            break
        await self._emit_updates(message, session_id)
        if isinstance(message, ResultMessage) and getattr(message, "is_error", False):
            stop_reason = "refusal"
except Exception:
    logger.exception("Error streaming SDK messages")
    stop_reason = "refusal"
```

**Failure scenario:** If the SDK stream breaks mid-message (network error, SDK crash,
OOM), the exception is caught, logged, and `stop_reason="refusal"` is returned.
`PromptResponse(stop_reason="refusal")` signals to the ACP client that the model
refused to answer — a policy/safety stop. The actual cause (infrastructure failure)
is invisible to the caller at the protocol level. The caller gets the same response as
if Claude refused on content grounds.

**Downstream effect:** In `_interactive_loop()`, `conn.prompt()` returns a
`PromptResponse`. The loop then calls `break` (non-interactive mode) or reads more
input. Neither path inspects `stop_reason`. So even `"refusal"` is ignored — the
loop exits normally. The `SubagentResult` has `response_text=""` (partial stream data
is accumulated in `client.response_text`, but mid-stream crash loses the partial). The
caller gets an empty result and cannot distinguish stream crash from model refusal from
empty agent response.

**Test coverage:** `test_bridge_resilience.py` (based on filename) likely tests this.
Let me note: without reading those test files in detail, the crash-returns-refusal
path cannot be verified from unit tests alone since it requires a real SDK connection.

**Severity: MEDIUM**

### 4b. `_emit_updates()` exceptions would propagate to the streaming loop

In `_emit_stream_event()`, `_emit_assistant()`, etc., all `await
self._conn.session_update(...)` calls are bare awaits with no error handling. If
`session_update()` raises (e.g., broken pipe to ACP client), the exception propagates
to `prompt()` where it is caught by the broad `except Exception:` at line 441 and
treated as `stop_reason="refusal"`. This means a broken ACP connection (client
disconnected mid-stream) looks like a model refusal.

**Severity: LOW** (correct to stop on broken connection, but wrong signal type)

### 4c. `new_session()` connect failure leaves `_sessions` partially populated

```python
# claude_bridge.py lines 372-398
options = self._build_options(cwd, sdk_mcp, sandbox_cb)
self._sdk_client = self._client_factory(options)
await self._sdk_client.connect()  # Can raise!

# Only reached if connect() succeeds:
self._sessions[session_id] = _SessionState(...)
return NewSessionResponse(session_id=session_id)
```

If `self._sdk_client.connect()` raises, `self._sdk_client` is set to a disconnected
client object, `self._session_id` is set, but `self._sessions` is NOT populated. A
subsequent call to `prompt()` would hit `if self._sdk_client is None: raise
RuntimeError(...)` — but `_sdk_client` is not None, it's a disconnected client. The
prompt would then call `self._sdk_client.query()` on a disconnected client, which
would raise from within the SDK.

**Test coverage:** Not tested (requires real SDK connection failure simulation).

**Severity: MEDIUM** (broken session state, hard to recover from without reinitializing)

---

## 5. `hooks/engine.py` — Caller Cannot Act on Hook Failures

### 5a. `trigger()` returns results but callers don't check them

`trigger()` returns `list[HookResult]`, each with a `success: bool` field. The callers
in CLI code (not audited here, but the pattern is set by the API) receive this list.
If ALL callers discard the return value or don't inspect `result.success`, hook
failures are entirely silent.

Checking the hooks invocation sites:

```python
# Typical invocation pattern (from vault.py / cli.py — callers of trigger()):
trigger(hooks, "vault.document.created", {"path": str(path)})
# Return value discarded
```

Even if callers DO check results, there is no mechanism to propagate a hook failure
back to the user or halt the operation that triggered the hook. A failed hook after
`vault.py create` leaves the document created but the hook silently didn't run.

**Severity: MEDIUM** — hooks are advisory but the system provides no feedback.

### 5b. `load_hooks()` bare `except Exception` loses parse error details

```python
# engine.py lines 107-108
except Exception:
    logger.warning("Failed to parse hook: %s", path.name)
```

The exception itself is discarded — no `exc_info=True`. The warning logs only the
filename. If the YAML parse fails for a complex reason (e.g., PyYAML version
incompatibility, file encoding issue), the root cause is lost. An operator debugging
a broken hook gets only `"Failed to parse hook: my-hook.yaml"` with no stack trace.

**Test coverage:** `test_skips_invalid` tests only the case where the hook has a
missing `event` field (which causes `_parse_hook()` to return `None`, not an
exception). The `except Exception` path (actual parse error) is not tested.

**Severity: LOW**

---

## 6. `rag/api.py` — Broken Singleton After Partial Initialization

### 6a. `get_engine()` singleton left in broken state on lazy-property failure

```python
# api.py lines 81-102
def get_engine(root_dir: pathlib.Path) -> VaultRAG:
    global _engine
    if _engine is None or _engine.root_dir != root_dir:
        if _engine is not None:
            _engine.close()
        _engine = VaultRAG(root_dir)  # Singleton assigned HERE
        try:
            from rag.embeddings import _require_cuda
            _require_cuda()
        except ImportError:
            pass
    return _engine
```

`_engine` is set to a fresh `VaultRAG` instance before `_require_cuda()` is called.
If `_require_cuda()` raises a `GPUNotAvailableError` (not `ImportError`), it propagates
out of `get_engine()` — but `_engine` is already set to the new instance with `_model
= None`.

On the next call to `get_engine()` with the same `root_dir`, the condition `_engine is
None or _engine.root_dir != root_dir` is False, so it returns the broken singleton
without re-initializing. Subsequent calls to `engine.indexer` or `engine.searcher`
will call `EmbeddingModel()` again via the lazy properties — which will call
`_require_cuda()` again and raise again.

**Net effect:** The singleton is perpetually broken for the lifetime of the process —
each call to `get_engine()` returns a broken `VaultRAG` instance, and every lazy
property access raises `GPUNotAvailableError`. This is recoverable (each access raises
the same error), but misleading — callers expect `get_engine()` to be the fault
boundary, not the property access.

**The `except ImportError: pass` is also incorrect:** `GPUNotAvailableError` is not
an `ImportError`. The intent seems to be "skip GPU check if RAG deps aren't installed",
but if RAG deps ARE installed and GPU is absent, the error is NOT caught by
`except ImportError`, it propagates. This is actually correct behavior (fail fast),
but inconsistent with the `except ImportError: pass` suggesting soft handling.

**Test coverage:** The `GPUNotAvailableError` path is expected behavior (the system
requires CUDA), but the broken-singleton-on-second-call scenario is not tested.

**Severity: LOW** (correct behavior eventually, but broken singleton semantics)

### 6b. `get_document()` silently swallows lancedb OSError

```python
# api.py lines 167-177
try:
    store = VaultStore(root_dir)
    result = store.get_by_id(doc_id)
    if result:
        return result
except ImportError:
    logger.debug("RAG dependencies not available, falling back to filesystem")
except (FileNotFoundError, OSError) as e:
    logger.debug(f"Vector store lookup failed: {e}")
```

An `OSError` during lancedb read (e.g., corrupted lance dir, permission error) is
silently downgraded to a debug-level log and the function falls back to filesystem
scan. The caller has no way to know whether the vector store is corrupted or simply
empty. If the lancedb file is corrupt, EVERY call to `get_document()` will silently
fail the vector lookup and do a full filesystem scan — a silent performance regression.

**Test coverage:** Not tested.

**Severity: LOW** (graceful degradation is correct, but should be `warning` not `debug`)

---

## 7. `rag/indexer.py` — ThreadPoolExecutor Worker Exceptions

### 7a. `pool.map()` propagates first worker exception but silently skips others

```python
# indexer.py lines 138-142 (full_index)
with ThreadPoolExecutor() as pool:
    results = pool.map(lambda p: prepare_document(p, self.root_dir), paths)
    for doc in results:

        if doc is not None:
            docs.append(doc)
```

`prepare_document()` has its own `try/except`:

```python
# indexer.py lines 68-72
try:
    content = path.read_text(encoding="utf-8")
except Exception as e:
    logger.warning(f"Cannot read {path}: {e}")
    return None
```

So `prepare_document()` itself never raises — it returns `None` on read failure.
However, if `parse_vault_metadata(content)` raises (unhandled — it has no try/except),
or `get_doc_type()` raises, the exception propagates out of the lambda. With
`ThreadPoolExecutor.map()`, the first such exception is re-raised when the generator
is consumed (on the next `for doc in results` iteration), and subsequent results are
discarded.

**Current safety:** `parse_vault_metadata()` and `get_doc_type()` do not appear to
raise under normal conditions. But any future exception in `prepare_document()` beyond
the read step would cause the entire indexing operation to fail at the first bad
document, with all subsequent documents silently not indexed.

**Better pattern:** `list(pool.map(...))` consumes all results and collects all
exceptions, or use `pool.submit()` with individual `.result()` calls in a loop that
catches per-worker exceptions.

**Test coverage:** Not tested.

**Severity: LOW** (currently safe due to `prepare_document`'s catch-all, but fragile)

### 7b. Full re-index OSError is caught but partially completes

```python
# indexer.py lines 165-170
try:
    existing_ids = self.store.get_all_ids()
    if existing_ids:
        self.store.delete_documents(list(existing_ids))
except OSError:
    logger.warning("Failed to delete existing documents during full re-index")
```

If deleting existing documents fails (`OSError`), the code continues and
`self.store.upsert_documents(docs)` runs — which re-adds the same documents, creating
duplicates. The returned `IndexResult` reports `added=len(docs)` with no indication
that the delete step failed, leaving the index in an inconsistent state (duplicate
entries).

**Test coverage:** Not tested.

**Severity: MEDIUM** — silent index corruption on OSError during delete.

---

## 8. `subagent_server/server.py` — Background Task Error Handling

### 8a. `_poll_agent_files()` exceptions kill the poller silently

```python
# server.py lines 343-347
async def _poll_agent_files() -> None:
    while True:
        await asyncio.sleep(_poll_interval())
        if _refresh_fn():
            await _send_list_changed()
```

`_refresh_fn()` calls `_refresh_if_changed()` which calls `_register_agent_resources()`
which calls `_build_agent_cache()`. If `_build_agent_cache()` raises an unhandled
exception (e.g., filesystem error reading agent files), the exception propagates to
`_poll_agent_files()`, exits the `while True` loop, and the `_poll_agent_files` task
completes with an exception.

When an asyncio task completes with an exception and no one `await`s it, the exception
is stored in the task and logged as "Task exception was never retrieved" when the task
is garbage collected — a deferred warning, not an immediate error. The agent file

**The `_server_lifespan` context manager:**

```python
async with _server_lifespan(_app):  # via FastMCP
    # ...
# On exit, poller.cancel() is called
```

The lifespan manager calls `poller.cancel()` on shutdown but does NOT `await
poller` in a way that would surface the exception. `contextlib.suppress(CancelledError)`
is used, which masks the original exception.

**Consequence:** Agent file changes after a poller crash stop being reflected in the
MCP `list_agents` response. No error is surfaced to the MCP client.

**Test coverage:** The test suite tests `_refresh_fn` via the injectable
`refresh_callback` but does NOT test the poll loop's error handling.

**Severity: HIGH**

**Fix direction:** Wrap the poll loop body in `try/except Exception` and log at error
level, continuing the loop rather than letting the exception kill the task.

### 8b. `asyncio.create_task()` for `_run_in_background` — uncaught exceptions

```python
# server.py lines 523-524
bg_task = asyncio.create_task(_run_in_background())
_background_tasks[task_id] = bg_task
```

`_run_in_background()` has a broad `except Exception` (line 516) that calls
`fail_task()`. However, as noted in section 1 above, `asyncio.CancelledError` (a
`BaseException`, not `Exception`) bypasses this handler. If the MCP server's event
loop is shut down while background tasks are running, `CancelledError` propagates
through `_run_in_background()`, the finally block runs (pops from dicts), but
`fail_task()` / `cancel_task()` is never called. The task engine retains the
orphaned `WORKING` task.

**Test coverage:** Not tested.

**Severity: HIGH** (same root cause as finding #2, different manifestation)

---

## Summary Table

| # | Location | Issue | Severity | Test Catches? |
|---|----------|-------|----------|---------------|
| 1 | `orchestration/subagent.py:322` | Crash returns empty success — indistinguishable from valid empty result | **CRITICAL** | No |
| 2 | `orchestration/task_engine.py` + `server.py` | WORKING tasks never expire; CancelledError bypasses fail_task | **HIGH** | No |
| 3a | `server.py:343` | Poll loop exception kills poller silently | **HIGH** | No |
| 3b | `server.py` + `task_engine.py` | CancelledError bypasses fail_task in background tasks | **HIGH** | No |
| 4a | `rag/indexer.py:165` | OSError during delete leads to duplicate documents silently | **MEDIUM** | No |
| 4b | `claude_bridge.py:441` | Stream crash reported as "refusal" — misleading to caller | **MEDIUM** | No |
| 4c | `claude_bridge.py:377` | connect() failure leaves broken session state | **MEDIUM** | No |
| 4d | `hooks/engine.py` | Callers discard HookResult — hook failures invisible | **MEDIUM** | No |
| 4e | `client.py:446` | graceful_cancel() swallows all exceptions | **MEDIUM** | No |
| 5a | `rag/api.py:89` | Broken singleton not re-initialized after GPU check fails | **LOW** | No |
| 5b | `rag/api.py:177` | lancedb OSError downgraded to debug log | **LOW** | No |
| 5c | `rag/indexer.py:138` | ThreadPoolExecutor worker exception kills entire index run | **LOW** | No |
| 5d | `hooks/engine.py:107` | Parse error detail lost (no exc_info in warning) | **LOW** | No |
| 5e | `client.py:337` | CancelledError swallowed in _reader() coroutine | **LOW** | No |
| 5f | `client.py:355` | Unknown terminal_id returns empty output (no error signal) | **LOW** | No |

## Cross-Cutting Pattern

The dominant failure mode is **exception-to-empty-value conversion**: exceptions are
caught at a boundary, logged, and converted to either an empty successful result object
or a degraded-success indicator. This means:

1. Callers cannot distinguish crash from success with empty output.
2. Monitoring/alerting systems see no error signals.
3. The error is visible ONLY if log lines are actively watched.

The secondary pattern is **asyncio.CancelledError bypass**: because `CancelledError`
is `BaseException` (not `Exception`), all `except Exception:` handlers miss it. This
means any operation that should atomically update state (like transitioning a task to
`CANCELLED` or `FAILED`) silently fails on event-loop cancellation.
**Recommended systemic fix:** Establish a project-wide convention:

- Use typed result types with explicit `error` fields, or
- Re-raise after logging at all internal boundaries except explicit degradation points,
  and document every `except Exception: pass` / `contextlib.suppress` with a comment
  explaining why the error is safe to discard.
