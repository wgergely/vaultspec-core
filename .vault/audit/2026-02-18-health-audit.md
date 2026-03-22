---
tags:
  - '#audit'
  - '#concurrency'
date: '2026-02-18'
related:
  - '[[2026-02-18-health-audit-deep-contracts-abstractions-audit]]'
  - '[[2026-02-18-health-audit-deep-error-propagation-audit]]'
  - '[[2026-02-18-health-audit-investigator1-core-vault-orch-audit]]'
  - '[[2026-02-18-health-audit-investigator2-protocol-subagent-audit]]'
  - '[[2026-02-18-health-audit-investigator3-data-functional-audit]]'
  - '[[2026-02-18-health-audit-summary-audit]]'
---

# Deep Audit: Concurrency, Resource Lifecycle, and State Management

**Auditor:** investigator2
**Date:** 2026-02-18
**Mandate:** READ-ONLY. Full concurrency, lifecycle, and state analysis.

______________________________________________________________________

## Executive Summary

Ten focus areas were analyzed. **Three functional bugs** and **one security
vulnerability** were identified. The most critical finding is a **command
injection vulnerability** in `hooks/engine.py` via `shell=True` on
user-controlled input. Additional findings include a `WORKING` task leak in
`TaskEngine` (no TTL for in-flight tasks), a race condition between
`execute()` and `cancel()` on `_active_clients` in `ClaudeA2AExecutor`, and
`VaultRAG` lazy property initialization not being thread-safe.

______________________________________________________________________

## Finding Index

| ID    | Severity        | Module                    | Description                                                              |
| ----- | --------------- | ------------------------- | ------------------------------------------------------------------------ |
| CC-1  | HIGH (security) | hooks/engine.py           | `shell=True` + unsanitized context → command injection                   |
| CC-2  | MEDIUM (bug)    | task_engine.py            | WORKING tasks never expire — permanent memory leak                       |
| CC-3  | MEDIUM (bug)    | claude_executor.py        | `_active_clients` dict race: execute/cancel on same task_id              |
| CC-4  | MEDIUM (bug)    | rag/api.py                | `VaultRAG` lazy properties not thread-safe — double init                 |
| CC-5  | LOW (design)    | task_engine.py            | threading.Lock + asyncio.Event: safe, but usage pattern fragile          |
| CC-6  | LOW (design)    | subagent.py               | AsyncExitStack: cleanup exception could swallow SubagentResult           |
| CC-7  | LOW (design)    | rag/search.py             | Graph TTL check+rebuild not atomic — stale graph served during rebuild   |
| CC-8  | LOW (design)    | rag/api.py                | `get_document()` creates standalone VaultStore — violates singleton rule |
| CC-9  | INFO            | subagent_server/server.py | Module-level globals are asyncio-safe but lack documentation             |
| CC-10 | INFO            | protocol/acp/client.py    | Zombie terminal risk if agent crashes before `release_terminal`          |

______________________________________________________________________

## Detailed Findings

______________________________________________________________________

### CC-1 — HIGH (security): Command Injection via `shell=True`

**File:** `hooks/engine.py`, `_execute_shell()`, line 231

```python
def _execute_shell(hook_name, action, ctx):
    cmd = _interpolate(action.command, ctx)   # user-controlled {path}, {root}, etc.
    result = subprocess.run(
        cmd,
        shell=True,          # ← executes through /bin/sh
        capture_output=True,
        text=True,
        timeout=60,
    )
```

**`_interpolate` is NOT safe for `shell=True`:**

```python
def _interpolate(template: str, ctx: dict[str, str]) -> str:
    result = template
    for key, value in ctx.items():
        result = result.replace(f"{{{key}}}", value)
    return result
```

The `ctx` dict values are literal replacements — no shell escaping is applied.
Hook context values come from caller-controlled data. For example:

```python

# In vault.py or cli.py:

trigger(hooks, "vault.document.created", {"path": str(doc_path)})
```

If `doc_path` contains a file named `foo; rm -rf /` (or on Windows
`foo & del /f /q C:\`), the shell command becomes:

```
echo 'New document: foo; rm -rf /'
```

...which executes `rm -rf /` as a separate command.

**Attack surface:** Vault document paths are the primary context values.
On a system where `.vault/` is writable by untrusted agents or external
processes, an adversarial agent could create a document at a crafted path
and trigger a hook that runs arbitrary shell commands.

**Likelihood:** Medium — requires an adversarial agent or path with shell
metacharacters (spaces, semicolons, backticks, `&`, `|`, `$`). Normal vault
document filenames (`2026-02-18-feature-plan.md`) are safe. But the system
has no enforcement preventing unusual filenames.

**Impact:** High — arbitrary code execution on the host system.

**Test coverage:** `test_hooks.py` tests `_interpolate` with
`{"root": "/tmp/test"}` — a safe value. No test exercises a shell
metacharacter in context values. **Zero injection test coverage.**

**Fix:** Replace `shell=True` with a list-based `subprocess.run`:

```python
import shlex
cmd_list = shlex.split(cmd)   # or build the list before interpolation
subprocess.run(cmd_list, shell=False, ...)
```

Or sanitize context values by rejecting any value containing shell
metacharacters (`;`, `|`, `&`, `` ` ``, `$`, `(`, `)`, `<`, `>`, `!`).

Note: `_execute_agent` correctly uses a list `[sys.executable, str(subagent_script), ...]`
with `shell=False` — the fix should mirror that pattern.

______________________________________________________________________

### CC-2 — MEDIUM (bug): WORKING Tasks Never Expire — Permanent Memory Leak

**File:** `orchestration/task_engine.py`, `_cleanup_expired()`, lines 260–268

```python
def _cleanup_expired(self) -> None:
    now = time.monotonic()
    expired = [tid for tid, exp in self._expiry.items() if now >= exp]
    for tid in expired:
        self._release_lock(tid)
        self._tasks.pop(tid, None)
        self._expiry.pop(tid, None)
        self._events.pop(tid, None)
```

TTL expiry is set **only when a task reaches a terminal state** (completed,
failed, cancelled):

```python

# In update_status(), complete_task(), fail_task():

if is_terminal(status):
    self._expiry[task_id] = task.updated_at + self._ttl_seconds
```

A task stuck in `WORKING` status (e.g., when the background coroutine
crashes without calling `fail_task()` or `complete_task()`) **never enters
`self._expiry`** and therefore **never gets cleaned up.**

`_cleanup_expired` only iterates `self._expiry.items()`, so tasks not in
`_expiry` are completely invisible to cleanup. They remain in `self._tasks`
forever.

**Scenario:** The MCP server `dispatch_agent` creates a background asyncio
task. If that task panics after `task_engine.create_task()` but before
`task_engine.fail_task()`, the task object leaks. Over days of operation
with many dispatched agents, `self._tasks` grows without bound.

**Likelihood:** Medium — the background task's except clause covers
`SubagentError` and generic `Exception`, but an unhandled `BaseException`
(e.g., `asyncio.CancelledError` from `bg_task.cancel()` during
`cancel_task`) could bypass `task_engine.fail_task()`. Additionally, if
`_run_subagent_fn` raises `KeyboardInterrupt` or `SystemExit`, neither is
caught by `except Exception`.

**Impact:** Medium — unbounded memory growth in long-running MCP server.
Orphaned tasks in WORKING state are never visible to callers (no TTL expiry
notification), and the associated advisory lock is never released.

**Test coverage:** `test_ttl_eviction` only tests a completed task.
No test covers a permanently-working task (stuck in WORKING state).

**Fix:** Add a creation-time TTL cap for WORKING tasks:

```python

# In create_task():

# Set a maximum working TTL (e.g., 2x the normal TTL or a config value)

self._expiry[tid] = now + self._max_working_ttl
```

Or track `created_at` separately and evict WORKING tasks older than a
configurable `max_working_seconds`.

______________________________________________________________________

### CC-3 — MEDIUM (bug): `_active_clients` Race in ClaudeA2AExecutor

**File:** `protocol/a2a/executors/claude_executor.py`, lines 88–168

```python

# execute() — stores client

self._active_clients[task_id] = sdk_client

# cancel() — reads and removes

client = self._active_clients.pop(task_id, None)
```

`_active_clients` is a plain `dict[str, Any]`. In the A2A server context,
the `A2AStarletteApplication` may dispatch `execute()` and `cancel()` from
concurrent async tasks running on the same event loop. Although Python's
GIL makes individual dict operations (`pop`, `__setitem__`) thread-safe at
the bytecode level, there are two problems:

**Problem 1: TOCTOU between `pop` and disconnect in `cancel()`.**

```python
client = self._active_clients.pop(task_id, None)  # removes from dict
if client is not None:
    client.interrupt()          # sync — may block
    client.disconnect()         # NOT awaited (bug from CC audit #1)
```

Between `pop` and `interrupt()`, `execute()` is still running and may be
iterating `sdk_client.receive_messages()`. Calling `interrupt()` while the
`async for` loop is active is safe only if `interrupt()` is thread/async
safe. No documentation or code comment confirms this.

**Problem 2: execute() checks `_active_clients` implicitly (via finally).**

```python

# In execute() finally:

self._active_clients.pop(task_id, None)
```

If `cancel()` already popped `task_id`, `execute()`'s `pop(task_id, None)`
is a harmless no-op. But the `disconnect()` in `execute()`'s finally block
will still run even after `cancel()` already called `disconnect()`. This
means **`disconnect()` is called twice on the same client** — once in
`cancel()` (sync, no await) and once in `execute()`'s finally
(`await sdk_client.disconnect()`). Whether double-disconnect is safe depends
entirely on the SDK implementation.

**Likelihood:** Low in normal operation (cancel is rare), Medium in stress
testing or when the orchestrator sends rapid cancel signals.

**Impact:** Medium — potential double-disconnect causing protocol errors or
resource corruption in the SDK client.

**Test coverage:** `test_claude_executor.py` does not test concurrent
execute + cancel scenarios. No concurrent call test exists.

**Fix:** Use asyncio.Lock to serialize access:

```python
self._active_clients_lock = asyncio.Lock()

async def execute(self, ...):
    async with self._active_clients_lock:
        self._active_clients[task_id] = sdk_client
    ...
    async with self._active_clients_lock:
        self._active_clients.pop(task_id, None)
```

______________________________________________________________________

### CC-4 — MEDIUM (bug): `VaultRAG` Lazy Properties Not Thread-Safe

**File:** `rag/api.py`, `VaultRAG` class, lines 37–65

```python
@property
def model(self) -> EmbeddingModel:
    if self._model is None:           # ← check
        from rag.embeddings import EmbeddingModel as _EmbeddingModel
        self._model = _EmbeddingModel()   # ← set
    return self._model
```

This is the classic double-checked locking anti-pattern without any lock.
In a multi-threaded context (Python threads, not asyncio), two threads can
both observe `self._model is None` simultaneously and both instantiate
`EmbeddingModel`, which allocates GPU VRAM:

```
Thread A: model is None? yes → start loading (14s GPU init) →
Thread B: model is None? yes (A hasn't finished) → start loading →
Thread A: assigns self._model = <model A>
Thread B: assigns self._model = <model B>   # ← A's model leaked
```

`EmbeddingModel` loads a BERT model to GPU. Double-initialization wastes
~538MB VRAM (full model allocation) and may cause CUDA OOM errors.

The same pattern exists for `store`, `indexer`, and `searcher` properties.

**Module-level singleton (`_engine`)** has the same issue in `get_engine()`:

```python
def get_engine(root_dir) -> VaultRAG:
    global _engine
    if _engine is None or _engine.root_dir != root_dir:   # ← not locked
        if _engine is not None:
            _engine.close()
        _engine = VaultRAG(root_dir)
```

Two concurrent calls to `get_engine()` with the same `root_dir` can both
enter the `if _engine is None` branch and create two `VaultRAG` objects.

**Current usage context:** The RAG system is called from the CLI (single
thread) and from vault.py (single thread). The MCP server is single-threaded
asyncio, so this is NOT currently a problem in production. However, if a
future MCP tool calls `search()` and `index()` concurrently, or if the
`get_status()` function creates a standalone `VaultStore` (CC-8) while
`get_engine()` also holds a `VaultStore`, the risk materializes.

**Likelihood:** Low in current architecture, Medium if async MCP tools
for RAG are added.

**Fix:** Add a `threading.Lock` at the module level:

```python
_engine_lock = threading.Lock()

def get_engine(root_dir):
    global _engine
    with _engine_lock:
        if _engine is None or _engine.root_dir != root_dir:
            ...
```

______________________________________________________________________

### CC-5 — LOW (design): threading.Lock + asyncio.Event — Safe but Fragile

**File:** `orchestration/task_engine.py`

`TaskEngine` uses `threading.Lock` for all dict mutations and `asyncio.Event`
for async notifications. This is the correct pattern when the same object
is accessed from both sync (threading) and async (asyncio event loop) code.

The specific concern: can `threading.Lock.acquire()` block the asyncio event
loop?

**Analysis:** All `with self._lock:` blocks in `TaskEngine` are called from:

non-blocking if uncontested (GIL + CPython lock fast path).

1. `wait_for_update()` — acquires `self._lock` briefly to register the
   event, then awaits `event.wait()` *outside* the lock.

**Potential deadlock scenario:**

- `LockManager.release_lock()` also uses `threading.Lock` internally.
- These are two different lock objects, so no deadlock is possible here.
  calls `event.set()` outside the lock. If `event.set()` is called from a
  non-asyncio thread, it may not wake up asyncio waiters until the event loop
  next polls. In the current architecture, `_notify()` is always called from
  the asyncio event loop thread, so this is safe.

**Verdict:** No deadlock. The pattern is correct but relies on the
invariant that `_notify()` is always called from the event loop thread.
This is undocumented. Adding a comment noting this invariant would reduce
future maintenance risk.

**Test coverage:** No concurrent access tests exist. The `test_task_engine.py`
file tests only sequential operations.

______________________________________________________________________

### CC-6 — LOW (design): AsyncExitStack — Exception Swallowing Risk

**File:** `orchestration/subagent.py`, lines 238–342

The resource lifecycle in `run_subagent()`:

```python
try:
    async with contextlib.AsyncExitStack() as stack:
        async with spawn_agent_process(client, ...) as (conn, _proc):

            # ... work ...

            return SubagentResult(...)   # ← return inside nested context managers

except Exception:
    logger.exception("Subagent execution failed")
    return SubagentResult(
        session_id=session_id,
        response_text=client.response_text,
        written_files=client.written_files,
    )
finally:

    # Cleanup spec.cleanup_paths

    # Clear callbacks

    gc.collect()
```

**Issue 1: Return inside context manager.**
`return SubagentResult(...)` on line 316 is inside `async with spawn_agent_process(...)`.
When Python exits a context manager via `return`, it calls `__aexit__`. If
`spawn_agent_process.__aexit__` raises an exception (e.g., process cleanup
error), the `return` value is discarded and the exception propagates. The
caller (`_run_in_background` in server.py) then catches `SubagentError` or
`Exception` — but since the error is from process cleanup, not from the
actual agent, the `task_engine.fail_task()` error message will be misleading.

**Issue 2: `except Exception` broad catch — may mask `CancelledError`.**
`asyncio.CancelledError` is a subclass of `BaseException`, NOT `Exception`
in Python 3.8+. So `except Exception` does NOT catch it. If the asyncio
task is cancelled mid-execution (from `cancel_task` → `bg_task.cancel()`),
`CancelledError` propagates out of `run_subagent()` and is caught by the
background task's outer `except Exception` handler in `server.py`:

```python
except Exception as e:
    logger.exception("Unexpected error in background subagent")
    task_engine.fail_task(task_id, f"Unexpected error: {e}")
```

But `CancelledError` is not `Exception` — so it propagates further up and
the background task is cancelled without calling `task_engine.fail_task()`.
The task stays in WORKING state (CC-2). The `finally` block runs, which
calls `gc.collect()` and cleans up callbacks — this is correct. But the
task engine state is not updated.

**Likelihood:** Medium — every `cancel_task` call cancels the background
asyncio task, which triggers `CancelledError` inside `run_subagent()`.

**Fix:** In `_run_in_background` (server.py), catch `CancelledError`
explicitly:

```python
except asyncio.CancelledError:
    task_engine.cancel_task(task_id)
    raise   # re-raise so asyncio knows the task was cancelled
except SubagentError as e:
    task_engine.fail_task(task_id, str(e))
except Exception as e:
    task_engine.fail_task(task_id, f"Unexpected error: {e}")
```

______________________________________________________________________

### CC-7 — LOW (design): Graph TTL Not Atomic — Stale Graph During Rebuild

**File:** `rag/search.py`, `VaultSearcher._get_graph()`, lines 176–188

```python
def _get_graph(self) -> VaultGraph | None:
    now = time.monotonic()
    if self._cached_graph is None or (now - self._graph_built_at) > self._graph_ttl:
        try:
            self._cached_graph = _VaultGraph(self.root_dir)   # ← may take 1-5s
            self._graph_built_at = now
        except Exception as e:
            logger.error(...)
            return None
    return self._cached_graph
```

**Race scenario (asyncio, same event loop):**
In the current architecture `_get_graph()` is called synchronously (no
`await`), so it blocks the event loop for the duration of `VaultGraph()`
construction. This means no other coroutine can run during graph rebuild.
Therefore, there is NO concurrent stale-graph risk in asyncio.

**However:** If `VaultGraph()` construction fails (raises an exception),
`self._cached_graph` is set to `None` (the assignment never happens), but
`self._graph_built_at` is also not updated. On the next call, the TTL check
triggers again immediately (since `_graph_built_at` is still the old
timestamp), causing repeated failed graph rebuilds on every search call.

This is not a race condition but a **retry-storm**: a broken VaultGraph
causes every search to attempt a rebuild, logging an error each time.

**Likelihood:** Low — VaultGraph construction fails only if `.vault/` is
corrupted or inaccessible.

**Impact:** Low — degraded search performance during graph failures.

**Fix:** On exception, set `self._graph_built_at = now` to back off:

```python
except Exception as e:
    logger.error("Search failed: %s", e, exc_info=True)
    self._graph_built_at = now   # ← backoff: don't retry immediately
    return None
```

______________________________________________________________________

### CC-8 — LOW (design): `get_document()` Creates Standalone VaultStore

**File:** `rag/api.py`, `get_document()`, lines 167–176

```python
def get_document(root_dir, doc_id):
    try:
        from rag.store import VaultStore
        store = VaultStore(root_dir)    # ← creates new LanceDB connection
        result = store.get_by_id(doc_id)
```

And `get_status()`, lines 289–291:

```python
store = VaultStore(root_dir)    # ← another standalone connection
result["index"]["indexed_count"] = store.count()
```

The memory note warns: "DON'T create multiple VaultStore instances for same
.lance dir". These standalone `VaultStore` instances are NOT the singleton
instance held by `_engine`. If `get_engine()` is active and holds a
`VaultStore` while `get_document()` also opens one, two LanceDB connections
coexist on the same `.lance/` directory.

LanceDB supports multiple readers, but concurrent writes from two handles
can cause corruption. In the current codebase, `get_document()` only reads
(no writes), so there is no immediate data corruption risk. However, this is
a fragile design that could break if `get_document()` is extended to cache
or update data.

Neither `get_document()` nor `get_status()` call `store.close()` — the
`VaultStore` is garbage collected when the function returns, which closes the
LanceDB connection implicitly. This is acceptable but unclean.

**Fix:** Route `get_document()` through `get_engine()`:

```python
def get_document(root_dir, doc_id):
    try:
        engine = get_engine(root_dir)
        result = engine.store.get_by_id(doc_id)
```

______________________________________________________________________

### CC-9 — INFO: Module-Level Globals in `subagent_server/server.py`

**File:** `subagent_server/server.py`, lines 69–80

```python
ROOT_DIR: pathlib.Path
AGENTS_DIR: pathlib.Path
lock_manager: LockManager
task_engine: TaskEngine
_agent_cache: dict[str, dict[str, object]] = {}
_background_tasks: dict[str, asyncio.Task[None]] = {}
_active_clients: dict[str, list] = {}
```

**Thread-safety analysis:**
The MCP server uses FastMCP which runs on a single asyncio event loop.
All MCP tool handlers (`list_agents`, `dispatch_agent`, etc.) are coroutines
that run on the same event loop thread. There is no multi-threading.

Therefore, all dict accesses (`_agent_cache.get()`, `_background_tasks[id] =`,
`_active_clients.pop()`) are safe — asyncio cooperative multitasking ensures
that only one coroutine runs at a time, and dict operations do not yield.

**Risk:** If FastMCP ever switches to a threaded executor model (e.g., via
`asyncio.to_thread`), these dicts would need `threading.Lock` protection.
This is undocumented.

**`_agent_cache` refresh:** `_refresh_fn()` is called at the start of both
`list_agents()` and `dispatch_agent()`. It updates `_agent_cache` and
`_agent_mtimes` (via `_register_agent_resources`). Since these are called
from coroutines on the same event loop, there is no concurrent access risk.

**Verdict:** Safe as currently implemented. No action required, but a
comment noting the single-event-loop assumption would prevent future bugs.

______________________________________________________________________

### CC-10 — INFO: Zombie Terminal Risk in `SubagentClient`

**File:** `protocol/acp/client.py`, `_Terminal` management, lines 65–425

`SubagentClient` manages subprocess terminals via `_terminals` dict.
Normal lifecycle: `create_terminal` → work → `release_terminal` (which
kills the process and cancels the reader task).

**Risk scenario:** If the agent process crashes or is killed before sending
`release_terminal`, the `_Terminal` entries in `_terminals` are never cleaned
up:

- `terminal.proc` — subprocess object with a running reader task
- `terminal.reader_task` — `asyncio.Task` reading stdout forever
- The subprocess itself — becomes a zombie waiting for `wait()`

The `_read_stderr` task in `subagent.py` is explicitly cancelled:

```python
t.cancel()
with contextlib.suppress(asyncio.CancelledError):
    await t
```

But the `_Terminal` reader tasks in `SubagentClient._terminals` are NOT
cancelled during normal `run_subagent()` teardown. The `SubagentClient`
object is garbage collected after `run_subagent()` returns, which eventually
cancels the reader tasks, but:

1. The subprocess may remain as a zombie until Python's GC runs.
1. Between GC and subprocess death, the subprocess holds a pipe open to
   the SubagentClient, keeping stdout alive.

**Likelihood:** Low in normal usage (agent sends `release_terminal` before
session end). Medium if the agent crashes mid-terminal.

**Fix:** Add a `close()` method to `SubagentClient` that kills all tracked
terminals:

```python
async def close(self) -> None:
    for terminal_id in list(self._terminals.keys()):
        await self.release_terminal(session_id="", terminal_id=terminal_id)
```

Call it in `run_subagent()`'s `finally` block alongside the callback cleanup.

______________________________________________________________________

## Test Coverage Summary for Concurrency

| Scenario                                         | Covered by Tests? |
| ------------------------------------------------ | ----------------- |
| Concurrent execute + cancel on same task         | NO                |
| WORKING task that never terminates               | NO                |
| Double-disconnect on SDK client                  | NO                |
| CancelledError through run_subagent              | NO                |
| Shell metacharacter injection in hook context    | NO                |
| Graph rebuild retry storm                        | NO                |
| Multiple VaultStore instances on same .lance dir | NO                |
| Terminal orphan on agent crash                   | NO                |
| Threading.Lock contention in TaskEngine          | NO                |
| AsyncExitStack cleanup exception                 | NO                |

**All 10 concurrency scenarios have zero test coverage.**

______________________________________________________________________

## Priority Recommendations

**Priority 1 — Fix immediately:**

`hooks/engine.py:_execute_shell()`. This is a security vulnerability.

- **CC-2:** Add creation-time TTL cap for WORKING tasks in `TaskEngine`.

- **CC-6:** Catch `asyncio.CancelledError` in `_run_in_background` in
  `subagent_server/server.py` and call `task_engine.cancel_task()`.

- **CC-3:** Add asyncio.Lock for `_active_clients` in `ClaudeA2AExecutor`.

- **CC-4:** Add threading.Lock for `get_engine()` singleton initialization.

- **CC-7:** Set `self._graph_built_at = now` in the exception handler to

  prevent retry storms.

- **CC-10:** Add `close()` to `SubagentClient` and call it in `run_subagent()`
  **Priority 4 — Document:**

- **CC-5:** Add comment in `TaskEngine._notify()` noting the event loop
  thread invariant.

- **CC-8:** Route `get_document()` and `get_status()` through `get_engine()`
  or add a `store.close()` call after use.

- **CC-9:** Add comment in `server.py` noting the single-event-loop assumption.
