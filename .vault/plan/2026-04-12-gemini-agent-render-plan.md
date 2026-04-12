---
tags:
  - '#plan'
  - '#gemini-agent-render'
date: 2026-04-12
related:
  - '[[2026-04-12-gemini-agent-render-research]]'
  - '[[2026-04-12-gemini-agent-render-adr]]'
---

# gemini-agent-render plan

## objective

Land the per-provider agent renderer factory described in
\[[2026-04-12-gemini-agent-render-adr]\] so Gemini CLI loads every
managed agent without validation errors, while keeping Claude and
Codex untouched in observable behaviour.

## phase-1 implementation

### task-1: introduce renderer factory

File: `src/vaultspec_core/core/agents.py`.

- Add module-level constant `_CLAUDE_TO_GEMINI_TOOLS: dict[str, str]`
  with the eight mappings from the ADR.
- Add `_render_passthrough_agent(name, meta, body)` returning
  `build_file(meta, body)` (today's behaviour).
- Add `_render_claude_agent(name, meta, body)` that builds a fresh
  frontmatter dict containing only `name`, `description` (if set),
  `tools` (preserved verbatim), and `model` (if set). All other keys
  are dropped.
- Add `_render_gemini_agent(name, meta, body, *, warnings)` that does
  the same as Claude but maps each `tools` entry through
  `_CLAUDE_TO_GEMINI_TOOLS`. Unmapped entries are dropped and a
  warning string is appended to *warnings*.
- Add `_AGENT_RENDERERS: dict[Tool, Callable]` registry mapping
  `Tool.CLAUDE -> _render_claude_agent` and
  `Tool.GEMINI -> _render_gemini_agent`. Codex is intentionally
  absent (its TOML path is dispatched separately).
- Rewrite `transform_agent(tool, name, meta, body)` to look up the
  registry, defaulting to `_render_passthrough_agent` for unknown
  tools. Add an optional `warnings: list[str] | None = None` keyword
  arg threaded through to the Gemini renderer.

### task-2: thread warnings through `agents_sync`

File: `src/vaultspec_core/core/agents.py`.

- In `agents_sync`, allocate a `render_warnings: list[str] = []`
  alongside `parse_warnings`.
- Update the per-tool sync loop so the lambda passed as `transform_fn`
  forwards `warnings=render_warnings` into `transform_agent`.
- After the loop, extend `total.warnings` with `render_warnings`
  alongside the existing `parse_warnings.extend`.

### task-3: tests

File: `src/vaultspec_core/tests/cli/test_agents_render.py` (new).

Mark with `pytestmark = [pytest.mark.unit]`. Use `parse_frontmatter`
from `vaultspec_core.vaultcore` to inspect rendered output. No mocks,
no patches, no skips.

Test classes:

- `TestRenderClaudeAgent`
  - injects `name` from filename stem
  - preserves `description`
  - preserves `tools` verbatim
  - drops `tier`, `mode`
  - preserves `model` if present
- `TestRenderGeminiAgent`
  - injects `name`
  - maps every entry in `_CLAUDE_TO_GEMINI_TOOLS`
  - drops unknown tool + records warning
  - empty `tools` list yields empty `tools` list (no crash)
  - drops `tier`, `mode`
- `TestTransformAgentDispatch`
  - `Tool.CLAUDE` dispatches to claude renderer
  - `Tool.GEMINI` dispatches to gemini renderer
  - unknown / non-registered tool falls through to passthrough
- `TestSourceAgentCoverage`
  - parametrize over every file in `.vaultspec/rules/agents/*.md`
  - for each, render under `Tool.GEMINI` and assert: `name` present,
    every `tools` entry is in the Gemini value-set, no `tier`/`mode`
    keys leak into the rendered frontmatter
  - this is the regression guard against future source-agent typos

### task-4: lint, format, type-check

- `uv run --no-sync ruff format src/vaultspec_core/core/agents.py src/vaultspec_core/tests/cli/test_agents_render.py`
- `uv run --no-sync ruff check src/vaultspec_core/core/agents.py src/vaultspec_core/tests/cli/test_agents_render.py`
- `uv run --no-sync python -m ty check src/vaultspec_core`
- `uv run --no-sync pytest src/vaultspec_core/tests/cli/test_agents_render.py -q`
- `uv run --no-sync pytest src/vaultspec_core/tests -q -x` (full
  unit run, no regressions)

### task-5: commit + push + refresh PR body

- Commit message: `fix(#76): per-provider agent renderer for Gemini`
- Push to `fix/76-gemini-agent-render`.
- `gh pr edit 77` with refreshed body: latest commit list, test
  counts, checked test-plan boxes.

## phase-2 verification

### task-6: code review

Invoke `vaultspec-code-review` (high-tier reviewer agent) over the
diff against the ADR. Persist review at
`.vault/exec/2026-04-12-gemini-agent-render/2026-04-12-gemini-agent-render-phase1-review.md`.

### task-7: phase summary + audit

Write phase summary at
`.vault/exec/2026-04-12-gemini-agent-render/2026-04-12-gemini-agent-render-phase1-summary.md`
referencing each step record + the review.

## acceptance

- All four task-3 test classes green.
- Full unit suite green.
- `gemini` row in test plan checked: every source agent renders into
  a Gemini-loadable shape (asserted by `TestSourceAgentCoverage`).
- PR body up-to-date with commit list, test counts, review link.

## non-goals

- Antigravity-specific renderer.
- Codex render changes.
- Source-schema redesign.
- Live integration test against an actual Gemini CLI install.
