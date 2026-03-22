---
tags:
  - '#adr'
  - '#startup-fixes'
date: '2026-02-20'
related:
  - '[[2026-02-20-containerization-research]]'
  - '[[2026-02-20-startup-fixes-p1-plan]]'
---

# startup-fixes adr | (**status:** accepted)

## Problem Statement

Containerization feasibility research identified four startup and deployment bottlenecks that degrade developer experience: slow MCP import overhead (~600ms from pydantic schema generation), unguarded ACP handshake hangs (30s timeout with no feedback), indefinite torch initialization hangs on CUDA environments, and unclear documentation around RAG opt-in requirements.

## Decision

Address all four bottlenecks with targeted in-process fixes rather than containerization. Each fix is independent and can be implemented in parallel by separate agents.

## Considerations

- MCP `@mcp.tool` decorator triggers heavy pydantic schema generation at import time - lazy registration may defer this cost
- ACP `conn.initialize()` has no `asyncio.wait_for()` guard, causing silent 30s hangs on failure
- `import torch` can hang indefinitely on CUDA 13.0 + PyTorch 2.10+cu130 environments
- Users have no clear guidance that RAG features require `pip install vaultspec[rag]` with CUDA

## Rationale

Containerization was investigated but adds operational complexity disproportionate to the problems. The four fixes are surgical, independent, and address root causes directly: lazy tool registration for import speed, timeout guards for handshake resilience, subprocess probes for torch safety, and documentation clarity for RAG opt-in.

## Consequences

- MCP server cold-start target drops from 630ms to under 200ms
- ACP handshake failures surface structured errors within configurable timeout
- Torch initialization hangs are caught within 60s with actionable error messages
- README clearly separates core install from RAG optional dependency
