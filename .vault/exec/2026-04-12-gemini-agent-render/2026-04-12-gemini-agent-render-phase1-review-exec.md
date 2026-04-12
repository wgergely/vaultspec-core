---
tags:
  - '#exec'
  - '#gemini-agent-render'
date: 2026-04-12
related:
  - '[[2026-04-12-gemini-agent-render-plan]]'
  - '[[2026-04-12-gemini-agent-render-phase1-step1-exec]]'
---

# gemini-agent-render phase-1 review

## reviewer

vaultspec-code-reviewer (delegated subagent, independent of authoring
context). Reviewed commits `afca64b..3e68e3e` against
\[[2026-04-12-gemini-agent-render-adr]\].

## verdict

**APPROVE** with five findings: two minor issues addressed in this
revision, three nits acknowledged.

## findings + dispositions

### 1. ADR/code drift on `model` key (minor)

ADR line 40 listed `model` among the dropped authoring keys, but
`_render_claude_agent` preserves `model`. Both behaviours are
defensible; preserving `model` is more correct (Claude honours
agent-level model selection).

**Disposition**: ADR updated to drop `model` from the dropped list.
Code unchanged.

### 2. dead `_VAULTSPEC_AUTHORING_KEYS` constant (minor)

The renderers build a fresh frontmatter dict from scratch rather
than filtering against the constant, so the constant was unused.

**Disposition**: removed the constant from `core/agents.py`.

### 3. lambda capturing `tool_type` is hard to read (nit)

`agents_sync` uses
`lambda _tool, n, m, b, _tt=tool_type: transform_agent(_tt, n, m, b, ...)`
which substitutes the captured tool over the positional one passed
by `sync_files`. A `functools.partial` would be clearer.

**Disposition**: deferred. The pattern matches existing rules/skills
sync sites; touching it would expand scope and break with the local
convention. Worth a follow-up sweep.

### 4. parametrized test silently produces zero cases if source dir empty (minor)

`_source_agent_files()` returns `[]` if `.vaultspec/rules/agents/`
is missing, which would silently disable the regression guard.

**Disposition**: added a module-level
`assert _SOURCE_AGENTS, ...` so the test file fails to import (and
collection fails loudly) if the source directory is empty or moved.

### 5. transform_agent dispatched for Codex? (nit, false alarm)

Reviewer self-checked: `agents_sync` skips Codex before reaching
`transform_agent`, and the docstring documents this. Confirmed
non-issue.

## what's good

- Codex render path (`_render_codex_agent`, `_build_codex_agents_body`,
  `_sync_codex_agents`) is byte-for-byte unchanged.
- `_CLAUDE_TO_GEMINI_TOOLS` covers 100% of tools used in
  `.vaultspec/rules/agents/` (verified by greping all source agent
  `tools:` lines against the dict keys).
- Test suite is mock-free, asserts on real `parse_frontmatter`
  output of real source files, and the parametrized
  `TestSourceAgentCoverage` will break CI if a new source agent
  introduces an unmapped tool or leaks `tier`/`mode`.

## post-review verification

```
uv run --no-sync ruff check src/vaultspec_core/core/agents.py \
  src/vaultspec_core/tests/cli/test_agents_render.py
uv run --no-sync python -m ty check src/vaultspec_core
uv run --no-sync pytest src/vaultspec_core/tests/cli/test_agents_render.py -q
```

- ruff: All checks passed.
- ty: All checks passed.
- pytest: 42 passed in 0.15s.
