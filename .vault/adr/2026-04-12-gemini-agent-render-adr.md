---
tags:
  - '#adr'
  - '#gemini-agent-render'
date: 2026-04-12
related:
  - '[[2026-04-12-gemini-agent-render-research]]'
  - '[[2026-04-12-gemini-agent-render-plan]]'
---

# gemini-agent-render adr

## status

Accepted - 2026-04-12.

## context

See \[[2026-04-12-gemini-agent-render-research]\]. Gemini CLI rejects all
managed agent files because the current `transform_agent` is a no-op
passthrough that emits Claude-flavoured frontmatter (`tier`, `mode`,
Claude tool names, no `name`). The renderer must produce per-provider
output: Gemini's strict schema differs from Claude's permissive one,
and the source-of-truth schema is authored against Claude.

## decision

Introduce a small per-provider **agent renderer registry** in
`src/vaultspec_core/core/agents.py` and replace the body of
`transform_agent` with a dispatch into that registry. Each entry in
the registry is a pure function
`(name: str, meta: dict, body: str) -> str` returning the final file
content (frontmatter + body) for one provider.

Three renderers ship in this PR:

- **`_render_claude_agent`** - canonical Claude shape: stamps `name`
  from the filename stem, preserves `description`, preserves the
  source `tools` list verbatim (Claude tool names), drops vaultspec
  authoring keys (`tier`, `mode`) so Claude's view of the
  agent is clean rather than merely tolerated.
- **`_render_gemini_agent`** - Gemini shape: stamps `name`, preserves
  `description`, **maps** `tools` from Claude vocabulary to Gemini
  vocabulary via a static lookup table, drops vaultspec authoring
  keys, and drops any unknown source tool with a warning recorded on
  `SyncResult.warnings`.
- **`_render_passthrough_agent`** - default fallback for any
  provider not explicitly registered (mirrors today's behaviour).

The Codex path is **not** touched. `_render_codex_agent` continues to
own its TOML rendering and is dispatched explicitly in `agents_sync`
exactly as it is today.

### tool mapping (claude -> gemini)

| Source (Claude) | Gemini equivalent |
| --------------- | ----------------- |
| `Read`          | `ReadFile`        |
| `Write`         | `WriteFile`       |
| `Edit`          | `Edit`            |
| `Glob`          | `FindFiles`       |
| `Grep`          | `SearchText`      |
| `Bash`          | `RunShellCommand` |
| `WebFetch`      | `WebFetch`        |
| `WebSearch`     | `GoogleSearch`    |

The mapping is a module-level `frozenset`/dict so it is trivially
introspectable from tests and from a future `vaultspec-core spec agents list --tool gemini` command.

### warnings, not errors

Unknown source tool names are dropped and recorded as warnings on
`SyncResult.warnings`. A single typo in one of ten source agents
must not break the whole sync. This mirrors the parse-warning flow
already used by `collect_agents`.

## alternatives considered

- **Rewrite source-of-truth agents in a neutral schema.** Rejected:
  expands blast radius to 10 source files, breaks the user's
  Claude-centric authoring workflow, and still leaves the same
  Gemini-mapping problem (just moved upstream).
- **Per-provider subclasses on `ExecutionProvider`.** Rejected for
  this PR as scope creep. The execution-protocol providers under
  `protocol/providers/` own runtime prompt assembly, not file
  emission. Adding agent rendering to that surface would couple two
  unrelated concerns. A factory in `core/agents.py` keeps the
  emission concern in the same module that already owns
  `_render_codex_agent`.
- **Inline branching in `transform_agent` (`if tool is GEMINI: ...`)**.
  Rejected because Codex precedent already shows branching with a
  dedicated render function reads better and tests cleaner than an
  if/elif chain inside a single transform.

## consequences

- **Positive.** Gemini agents load. Claude output gets cleaner as a
  side benefit. The renderer registry is the natural extension point
  for Antigravity, future Anthropic schema changes, etc.
- **Positive.** The fix is contained to one module
  (`core/agents.py`) plus tests. No protocol/provider, sync engine,
  manifest, or CLI changes.
- **Neutral.** A static tool mapping must be maintained as Gemini's
  tool vocabulary evolves. The mapping lives next to the renderer
  for visibility; the test suite asserts every source-tool used in
  `.vaultspec/rules/agents/` has an entry, so an unmapped tool fails
  CI rather than silently dropping at sync time.
- **Negative.** This PR does not address agent rendering for
  Antigravity (which today shares the passthrough path with
  Claude). Antigravity's agent schema is not validated by this work
  - tracked separately if it surfaces.

## scope guard

Only the agent rendering surface is in scope. Out of scope:

- Antigravity / Codex rendering changes.
- `agents_add` / `agents_list` CLI behaviour.
- Source-schema redesign.
- Renaming or moving any existing public symbol.
