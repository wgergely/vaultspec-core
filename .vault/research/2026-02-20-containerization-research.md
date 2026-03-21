---
tags:
  - '#research'
  - '#containerization'
date: '2026-02-20'
related:
  - '[[2026-02-12-rag-mcp-api-adr]]'
  - '[[2026-02-12-rag-embeddings-adr]]'
---

# `containerization` research: `deployment isolation and startup overhead`

Investigation into whether containerizing vaultspec's PyTorch/RAG stack into a
Docker image would eliminate the reported ~60-second startup overhead and simplify
deployment on vanilla systems.

______________________________________________________________________

## Findings

### 1. What actually causes the startup overhead?

Empirical profiling on the current system (Windows 11, RTX 4080 SUPER, CUDA 13.0,
PyTorch 2.10.0+cu130):

**MCP server cold-start chain (no RAG):**

| Module                        | Import time |
| ----------------------------- | ----------- |
| `mcp.server.fastmcp`          | ~600ms      |
| `acp` (agent-client-protocol) | ~113ms      |
| `orchestration.subagent`      | ~352ms      |
| `vault.parser`                | ~15ms       |
| **Total MCP server startup**  | **~1.0s**   |

**RAG dependency imports:**

| Package                 | Import time            |
| ----------------------- | ---------------------- |
| `torch` (cu130)         | **Hangs indefinitely** |
| `sentence_transformers` | ~4.9s (after torch)    |
| `lancedb`               | ~1.1s                  |
| `einops`                | ~5ms                   |

**Critical finding**: `torch` import hangs completely in the current environment
(CUDA 13.0 + PyTorch 2.10+cu130). This is the source of the 60-second (and
longer) overhead — not MCP server startup per se.

**Root cause analysis:**

- The `mcp` package alone contributes 600ms — the dominant import on every cold
  start, regardless of RAG

- `torch` import either hangs (CUDA driver init stall) or, on first-use of the
  GPU stack, triggers CUDA JIT kernel compilation that blocks the process

- On Windows with CUDA 13.0, the PyTorch 2.10+cu130 wheel may perform on-import
  CUDA capability checks or cuDNN initialization that blocks for 30-60+ seconds

**Where does torch get imported from the CLI?**

- `cli.py`: `import torch` inside `health` and `status` subcommands — always
  deferred, never at module level

- `vault.py`: `from rag.api import index` / `from rag.api import search` — deferred
  inside command handlers only

- `subagent_server/server.py`: **zero** PyTorch imports, direct or transitive

- `subagent.py`: **zero** PyTorch imports

**Conclusion**: The MCP server itself does not import PyTorch. The reported
60-second overhead is most likely the ACP handshake timeout (30s default) when
the `dispatch_agent` tool attempts to spawn a `claude --experimental-acp` child
process that fails to respond. This is an ACP protocol issue, not a PyTorch issue.
When RAG tooling IS triggered (e.g., `vault.py index`), torch initialization hangs
indefinitely on this CUDA 13.0 system.

______________________________________________________________________

### 2. Is containerization solving the right problem?

**No** — for three reasons:

1. **MCP server is already PyTorch-free.** Containerizing to eliminate PyTorch from
   the MCP startup path provides zero benefit because PyTorch is never imported on
   that path.

1. **The real 60s overhead is ACP handshake timeout.** The subagent dispatch via
   `run_subagent()` spawns `claude --experimental-acp`. If Claude Code's ACP mode
   fails to handshake within 30 seconds, the orchestrator times out. A Docker
   container does not help here — the container would still run the same ACP
   subprocess and face the same timeout.

1. **torch import hangs (not just slow).** This suggests a CUDA 13.0 driver
   compatibility issue with PyTorch 2.10+cu130, not a solvable-by-containerization
   problem. A Docker image using the same CUDA version would reproduce the hang;
   a CPU-only image would work but loses GPU acceleration entirely.

______________________________________________________________________

### 3. Architecture options evaluated

#### a. Docker image (containerize all deps)

**Concept**: Single Docker image with Python, PyTorch, RAG deps pre-installed. MCP
server and CLI either run inside the container or communicate with it via HTTP/gRPC.

**Pro:**

- Reproducible environment across machines
- Eliminates pip install time on vanilla systems
- Isolates CUDA driver concerns

**Con:**

- CUDA in Docker requires `nvidia-container-toolkit` on Linux or WSL2 + Docker
  Desktop on Windows. On Windows 11, GPU passthrough to Docker requires WSL2
  backend — adds its own overhead and complexity

- Image size: `python:3.13-slim` + `torch+cu128` ≈ 8-10GB. Unacceptable for a
  developer tooling project

- Docker daemon must be running for any RAG operation — breaks offline/air-gapped
  use

- Claude Code's MCP server transport (`stdio`) can run inside a container
  (`docker run --rm -i vaultspec-mcp python ...`) but the container lifecycle is
  not managed by Claude Code — container exits when MCP session ends, losing any
  warm model state

- Does not fix the ACP handshake issue — the container would still try to spawn
  `claude --experimental-acp` from inside the container, which won't have access
  to the host's Claude Code binary

**Verdict**: High complexity, high cost, does not address root causes. Not
recommended.

#### b. Pre-warmed RAG service (long-running HTTP server)

**Concept**: `vault.py` gains a `serve` mode — an HTTP microservice that loads the
embedding model once, keeps it warm, and accepts `/index` and `/search` requests.
CLI and MCP tools call this service instead of importing RAG directly.

**Pro:**

- No Docker required — runs as a native process (`python vault.py serve`)
- Model loads once; subsequent searches in the same session are sub-100ms
- Clean separation: MCP server stays lightweight, RAG is a separate concern
- Could be managed by a systemd/launchctl service or started on demand

**Con:**

- Requires users to start the service before using RAG features
- Service management is an additional UX burden
- Port conflict management needed

**Verdict**: Valid for power users with heavy RAG usage. Does not solve the
ACP handshake problem. Medium complexity, medium benefit.

#### c. Fix the actual bottlenecks directly

Two separate problems need separate fixes:

**Problem A: `mcp` package takes 600ms to import.**

- `mcp` v1.26.0 has known slow import performance due to heavy pydantic schema
  generation. This is the single largest contributor to MCP server startup.

- Mitigation: lazy-load MCP tools using `@mcp.tool` deferred registration;
  investigate whether `mcp` can be imported in a background thread while the
  server begins accepting connections.

**Problem B: ACP handshake times out.**

- The `run_subagent()` function spawns `claude --experimental-acp` (or gemini)
  and waits for the ACP initialization handshake. If the child process is slow
  to start (e.g., first cold start of the Claude CLI itself, which must download
  or init its own runtime), the handshake times out at 30s.

- Mitigation: investigate whether the claude binary's cold-start can be
  pre-warmed; consider caching the ACP connection across MCP tool calls;
  increase the handshake timeout with exponential backoff for first-run.

**Problem C: `torch` hangs on CUDA 13.0.**

- This is environment-specific. The CUDA 13.0 + PyTorch 2.10+cu130 combination
  may have a CUDA capability detection stall.

- Mitigation: add an async/subprocess wrapper around torch initialization so it
  can be timeout-bounded; test with CUDA_VISIBLE_DEVICES='' to verify CPU
  fallback works; investigate `torch.cuda.init()` hanging vs import-time CUDA
  init.

#### d. Split package: `vaultspec` vs `vaultspec-rag`

**Concept**: Publish two PyPI packages. `vaultspec` (core) never requires torch.
`vaultspec-rag` is an optional addon.

**Pro:**

- Users who only need MCP/orchestration never install PyTorch
- Installation is fast for the common case
- Already structurally set up (optional `[rag]` extra in pyproject.toml)

**Con:**

- Dual-package maintenance overhead
- RAG features unavailable until `vaultspec-rag` is installed (clear UX guidance
  needed)

**Verdict**: Already mostly implemented via the `[rag]` optional extra. The bigger
win is documentation: clearly communicate that `pip install vaultspec` (without
`[rag]`) is the correct starting point, and that RAG features are opt-in.

#### e. Retire RAG from the MCP surface entirely

**Concept**: RAG (indexing/search) is already exclusively in `vault.py`. Remove any
remaining references to RAG from the MCP server and subagent dispatch path. The
MCP surface covers only: agent dispatch, task management, lock management.

**Verdict**: This is already the current state — no RAG imports exist in the MCP
server path. Confirm and document this boundary explicitly.

______________________________________________________________________

### 4. Migration cost

| Option                  | Code changes                                                      | User impact                     | Maintenance cost |
| ----------------------- | ----------------------------------------------------------------- | ------------------------------- | ---------------- |
| Docker image            | High (Dockerfile, HTTP bridge, CLI wrappers)                      | High (requires Docker)          | High             |
| Pre-warmed RAG service  | Medium (add `serve` mode to vault.py, HTTP client in RAG callers) | Medium (start service manually) | Medium           |
| Fix mcp import speed    | Low (profile + lazy-load)                                         | Transparent                     | Low              |
| Fix ACP handshake       | Low-Medium (timeout tuning, retry logic)                          | Transparent                     | Low              |
| Fix torch hang          | Low (subprocess guard, CUDA init wrapper)                         | Transparent                     | Low              |
| Document [rag] boundary | Minimal (README/docs update)                                      | Positive (clarity)              | Low              |

______________________________________________________________________

### 5. Docker-specific concerns

- **CUDA in Docker on Windows 11**: Requires Docker Desktop with WSL2 backend +
  `nvidia-container-toolkit` configured for WSL2. This is functional but adds
  significant setup complexity. GPU passthrough via WSL2 has known latency overhead
  (10-50ms per CUDA call vs native).

- **Image size**: `python:3.13-slim + torch 2.10 (cu128)` ≈ 8-10GB download and
  storage. For a developer tooling project, this is unacceptable as a default.

- **MCP + Docker transport**: Claude Code supports `docker run --rm -i image cmd`
  as an MCP server command. This works but: container starts fresh per session
  (loses warm model state), and container needs volume-mounts for vault access.
  A long-running Docker daemon + `docker exec` approach is more complex to manage.

- **ACP inside container**: `claude --experimental-acp` would need to be available
  inside the container, meaning the Claude Code binary must be installed there too.
  This creates a circular dependency or requires a network-accessible Claude API
  endpoint instead of the CLI.

______________________________________________________________________

## Recommendation

**Do not pursue containerization.** It addresses the wrong problem at high cost.

The correct intervention is a two-pronged targeted fix:

1. **Fix `mcp` package slow import** (~600ms): This is the real MCP server startup
   bottleneck. Profile whether lazy registration of MCP tools defers pydantic
   schema generation. Track the `mcp` GitHub for performance improvements in
   upcoming releases.

1. **Fix ACP handshake resilience**: The dispatch_agent timeout is the likely
   source of the user-perceived 60-second hang. Add retry/backoff logic,
   pre-warm the claude CLI process in the MCP server's lifespan hook, or consider
   migrating to native Anthropic API calls (bypassing ACP/CLI entirely for
   simpler dispatch patterns).

1. **Document the `[rag]` boundary**: Make explicit that `pip install vaultspec`
   (no RAG) is the standard install. RAG features (`vault.py index/search`) are
   opt-in and have their own CUDA environment requirements.

1. **Investigate torch hang on CUDA 13.0**: This is an environment-specific bug
   that warrants a dedicated fix (subprocess guard with timeout, fallback to CPU
   mode, or upgrade/downgrade PyTorch to a stable CUDA-compatible version).

The architectural principle of containerization is sound for long-term deployment
(e.g., a hosted vaultspec SaaS endpoint) but is not the right tool for the current
local developer tooling problem.
