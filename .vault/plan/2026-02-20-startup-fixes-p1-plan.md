---
tags:
  - '#plan'
  - '#startup-fixes'
date: '2026-02-20'
related:
  - '[[2026-02-20-containerization-research]]'
  - '[[2026-02-12-rag-mcp-api-adr]]'
  - '[[2026-02-12-rag-embeddings-adr]]'
  - '[[2026-02-20-startup-fixes-adr]]'
---

# `startup-fixes` `p1` plan

Address four identified startup and deployment bottlenecks discovered during
the containerization feasibility research (\[[2026-02-20-containerization-research]\]).
No containerization; targeted in-process fixes only.

## Proposed Changes

Four independent workstreams, each assignable to a separate agent:

**Fix 1 — `mcp` import overhead (~600ms)**
Profile and reduce the dominant cold-start cost. `mcp.server.fastmcp` triggers
heavy pydantic schema generation at import time for every `@mcp.tool`-decorated
function. Investigate whether deferred/lazy tool registration (building schemas
only when the tool is first called, not at import) drops this below 100ms.
Files: `subagent_server/server.py`, MCP tool decorators (`@mcp.tool` at lines
361, 392, 553, 595, 631).

**Fix 2 — ACP handshake resilience**
`run_subagent()` in `orchestration/subagent.py` calls `conn.initialize()` bare,
with no `asyncio.wait_for()` guard. The underlying `acp` library imposes a
30-second timeout, causing the entire `dispatch_agent` MCP tool call to hang
for 30 seconds before failing. Two sub-fixes:

- Wrap `conn.initialize()` with a configurable `asyncio.wait_for()` and raise
  a structured `SubagentError` with actionable message on timeout.

- Add a pre-warm hook in `_server_lifespan()` (`subagent_server/server.py`) that
  launches a dry-run of the claude process on MCP server startup so the binary
  is warm when the first real `dispatch_agent` call arrives.

**Fix 3 — `torch` initialization guard**
`vault.py index` and `vault.py search` call `from rag.api import index` which
transitively imports `torch`. On CUDA 13.0 + PyTorch 2.10+cu130, `import torch`
hangs indefinitely (observed: never returns after 26+ minutes). Wrap the RAG
import in a subprocess with a configurable timeout (default 60s). If the
subprocess fails or times out, surface a clear error message pointing the user
to environment requirements, rather than hanging silently.
Files: `vault.py` (index handler ~line 371, search handler ~line 423),
`rag/embeddings.py` (GPU init logic).

**Fix 4 — Documentation: `[rag]` as explicit opt-in**
`README.md` and installation docs do not clearly communicate that
`pip install vaultspec` is the standard (PyTorch-free) path and that RAG
features require `pip install vaultspec[rag]` with a CUDA-capable environment.
Update `README.md` installation section; add a "RAG requirements" callout box;
update `pyproject.toml` `[project.optional-dependencies]` descriptions if
absent. No code changes.

## Tasks

- `Fix 1: mcp import profiling and lazy registration`

  1. Benchmark current import time with `python -X importtime` to identify the
     exact pydantic callsite adding the 600ms cost.

  1. Investigate FastMCP's internal tool-registration API: determine whether
     `@mcp.tool` schema generation can be deferred until first tool invocation.

  1. If deferral is feasible: refactor tool declarations in `server.py` to use
     lazy registration; confirm schemas are still generated correctly.

  1. If deferral is not feasible: profile whether moving `from mcp.server.fastmcp import FastMCP` to a background thread (while the process accepts the stdio
     pipe) reduces perceived startup latency.

  1. Re-benchmark and record the new cold-start time.

- `Fix 2: ACP handshake resilience`

  1. Locate the `conn.initialize()` call in `run_subagent()` (subagent.py:293).

  1. Wrap it with `asyncio.wait_for(conn.initialize(...), timeout=cfg.acp_handshake_timeout)`
     where `acp_handshake_timeout` is a new config key (default: 30s, configurable).

  1. On `asyncio.TimeoutError`: raise `SubagentError` with message
     `"ACP handshake timed out after {N}s — is the claude/gemini binary installed?"`.

  1. Log the timeout event via `logger_instance` as `handshake_timeout` with
     `elapsed` and `timeout` fields (matches the existing JSONL schema observed
     in `.vault/logs/`).

  1. Add pre-warm in `_server_lifespan()`: on MCP server startup, spawn the
     configured agent binary (`claude --version` or equivalent no-op) to load
     the binary into OS file cache before the first real dispatch.

  1. Add a `acp_handshake_timeout` key to `core/config.py` with default 30.0.

  1. Write/update unit tests in `subagent_server/tests/` covering timeout path.

- `Fix 3: torch initialization guard`

  1. In `vault.py`, replace the bare `from rag.api import index` with a
     subprocess-based probe: run `python -c "import torch"` via
     `asyncio.create_subprocess_exec` with a 60-second timeout.

  1. If the probe times out or exits non-zero, print a user-friendly error
     (CUDA environment issue, point to install docs) and exit early.

  1. If probe succeeds, proceed with the regular `from rag.api import index`
     import (which will now be fast, since torch is warm in the OS).

  1. Alternatively: move the torch import into a `concurrent.futures.ThreadPoolExecutor`
     call with `timeout=60` to allow the main thread to remain responsive.

  1. Add `rag_timeout` config key (default: 60s) to `core/config.py`.

  1. Update `rag/embeddings.py` to call `torch.cuda.init()` explicitly and
     catch any `RuntimeError` to fall back to CPU mode gracefully.

  1. Write a test in `lib/tests/` or `rag/tests/` that verifies the timeout
     path raises the expected error (mock torch as hanging).

- `Fix 4: documentation update`

  1. Update `README.md` installation section: add two-tier install instructions
     (`pip install vaultspec` for core, `pip install vaultspec[rag]` for RAG).

  1. Add a "RAG / GPU Requirements" callout: Python 3.13+, CUDA-capable GPU,
     matching PyTorch CUDA wheel.

  1. Add MCP server startup section to README: clarify the MCP server has no
     PyTorch dependency and starts in ~1s.

  1. Review `pyproject.toml` optional-deps comments for clarity.

## Parallelization

All four fixes are fully independent — no shared files between Fix 1, Fix 3,
and Fix 4. Fix 2 touches `subagent.py` and `server.py`; Fix 1 also touches
`server.py` — these two should be assigned to different agents but must not
edit the same lines concurrently. Assign Fix 1 to one agent (server-side tool
registration only) and Fix 2 to a second agent (subagent.py + lifespan hook
only), then merge.

Recommended team composition:

- **Agent A** (standard-executor): Fix 1 + Fix 3 (profiling + subprocess guard)
- **Agent B** (standard-executor): Fix 2 (ACP timeout + pre-warm)
- **Agent C** (simple-executor): Fix 4 (docs)

Agents A and B can run in parallel. Agent C is independent and can run
concurrently with both.

## Verification

**Fix 1**: Cold-start benchmark before/after. Target: MCP server `import`
chain ≤ 200ms (down from 630ms). Measure with `python -X importtime` and with
the subprocess timing test in `subagent_server/tests/`.

**Fix 2**: Unit test: mock `conn.initialize()` to hang; assert `SubagentError`
raised within `acp_handshake_timeout + 1s`. Integration smoke test: dispatch
a minimal agent task and observe `handshake_timeout` NOT appearing in the JSONL
log (i.e., a successful handshake completes in time after pre-warm).

**Fix 3**: Unit test: mock `import torch` to hang for > 60s; assert the
timeout path produces the expected error output. Manual: run `vault.py index`
and confirm it fails fast with a clear error rather than hanging indefinitely.

**Fix 4**: Visual review of rendered `README.md`. Confirm `pip install vaultspec` produces a working MCP server with no `torch`/`lancedb` installed.

All existing tests (`python .vaultspec/lib/scripts/cli.py test unit`) must
continue to pass after each fix. No regressions to the subagent dispatch happy
path.
