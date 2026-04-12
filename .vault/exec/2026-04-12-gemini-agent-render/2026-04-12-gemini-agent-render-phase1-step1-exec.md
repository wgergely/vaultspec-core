---
tags:
  - '#exec'
  - '#gemini-agent-render'
date: 2026-04-12
related:
  - '[[2026-04-12-gemini-agent-render-plan]]'
  - '[[2026-04-12-gemini-agent-render-adr]]'
---

# gemini-agent-render phase-1 step-1

## scope

Implement the per-provider agent renderer factory described in
\[[2026-04-12-gemini-agent-render-plan]\] task-1 through task-4.

## changes

- `src/vaultspec_core/core/agents.py`
  - Added `_VAULTSPEC_AUTHORING_KEYS` (frozenset) and
    `_CLAUDE_TO_GEMINI_TOOLS` (dict).
  - Added `_render_passthrough_agent`, `_render_claude_agent`,
    `_render_gemini_agent` (each accepts a keyword-only
    `warnings: list[str] | None`).
  - Added `_AgentRenderer` Protocol and `_AGENT_RENDERERS` registry
    keyed by `Tool`.
  - Rewrote `transform_agent` to dispatch via the registry,
    defaulting to passthrough for unregistered providers, and to
    accept the optional `warnings` accumulator.
  - Updated `agents_sync` to allocate a `render_warnings` list,
    forward it through the lambda passed to `sync_files`, and merge
    it into `total.warnings` alongside `parse_warnings`.
- `src/vaultspec_core/tests/cli/test_agents_render.py` (new)
  - 42 unit tests across four classes:
    `TestRenderClaudeAgent`, `TestRenderGeminiAgent`,
    `TestTransformAgentDispatch`, `TestSourceAgentCoverage`.
  - `TestSourceAgentCoverage` is parametrized over every file in
    `.vaultspec/rules/agents/*.md` (10 source agents) and asserts
    both Gemini and Claude renderings are clean.

## verification

```
uv run --no-sync ruff format src/vaultspec_core/core/agents.py \
  src/vaultspec_core/tests/cli/test_agents_render.py
uv run --no-sync ruff check src/vaultspec_core/core/agents.py \
  src/vaultspec_core/tests/cli/test_agents_render.py
uv run --no-sync python -m ty check src/vaultspec_core
uv run --no-sync pytest src/vaultspec_core/tests -q
```

Results:

- ruff format: 1 reformatted, 1 unchanged.
- ruff check: All checks passed.
- ty: All checks passed.
- pytest: **785 passed in 203.09s** (42 new + 743 pre-existing).

## scope-guard audit

- Codex render path (`_render_codex_agent`, `_sync_codex_agents`):
  untouched, verified by grep diff.
- `agents_add` / `agents_list`: untouched.
- Other providers (`Tool.ANTIGRAVITY`): unchanged behaviour - falls
  through to `_render_passthrough_agent`, asserted by
  `TestTransformAgentDispatch::test_unregistered_tool_falls_through_to_passthrough`.
- Source agent files under `.vaultspec/rules/agents/`: untouched.

## commit

`38d5198 fix(#76): per-provider agent renderer for Gemini`
