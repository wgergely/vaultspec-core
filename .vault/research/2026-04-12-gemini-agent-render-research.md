---
tags:
  - '#research'
  - '#gemini-agent-render'
date: 2026-04-12
related:
---

# gemini-agent-render research

## context

Issue [wgergely/vaultspec-core#76](https://github.com/wgergely/vaultspec-core/issues/76):
Gemini CLI rejects every managed agent file synced into `.gemini/agents/`
with three classes of validation error:

- `name: Required` - the rendered file has no top-level `name` key.
- `tools.N: Invalid tool name` - the rendered file passes Claude tool names
  (`Glob`, `Grep`, `Read`, `WebFetch`, `WebSearch`, `Bash`, `Write`, `Edit`)
  through unchanged; Gemini CLI expects its own tool vocabulary.
- `Unrecognized key(s) in object: 'tier', 'mode'` - vaultspec's authoring
  schema includes capability/permission hints that Gemini's strict zod
  schema rejects.

## current behaviour

`src/vaultspec_core/core/agents.py` defines `transform_agent` as a no-op
passthrough for every non-Codex tool:

```python
def transform_agent(_tool: Tool, _name: str, meta: dict[str, Any], body: str) -> str:
    return build_file(meta, body)
```

`agents_sync` then iterates installed tools and writes the same rendered
content under each tool's `agents_dir`. Codex has its own dedicated
`_render_codex_agent` path that emits TOML and reshapes frontmatter into
Codex-specific keys (`approval_policy`, `sandbox_mode`, `tools`, etc).
Claude happens to tolerate the extra `tier`/`mode` keys, but Gemini does
not, so the bug surfaces only on `gemini` destinations.

The canonical agent sources under `.vaultspec/rules/agents/` use a
unified Claude-flavoured schema:

```yaml
---
description: ...
tier: HIGH | MEDIUM | LOW
mode: read-only | read-write
tools: [Glob, Grep, Read, Write, Edit, Bash, WebFetch, WebSearch]
---
```

There are 10 source agents: `vaultspec-adr-researcher`,
`vaultspec-code-reviewer`, `vaultspec-docs-curator`,
`vaultspec-high-executor`, `vaultspec-low-executor`,
`vaultspec-project-coordinator`, `vaultspec-reference-auditor`,
`vaultspec-researcher`, `vaultspec-standard-executor`,
`vaultspec-writer`.

The full Claude tool surface used across these is:
`Glob, Grep, Read, Write, Edit, Bash, WebFetch, WebSearch`.

## prior art in-repo

`rules.py::transform_rule` already injects `name` and `trigger` and
discards inbound `_meta` - precedent for "rebuild frontmatter rather than
pass it through". `skills.py::transform_skill` does similar shaping and
stamps a `name` derived from the directory name.

Codex shows the per-tool render precedent: `_render_codex_agent` uses a
distinct rendering function and is dispatched explicitly when
`tool_type is Tool.CODEX` in `agents_sync`. The pattern is "fall through
to the generic `transform_agent` for markdown providers, branch to a
dedicated renderer for native-config providers".

## gemini cli agent schema

The Gemini CLI local agent loader requires:

- `name: <string>` - top-level, required.
- `description: <string>` - free text.
- `tools: [<gemini tool name>, ...]` - validated against an enum of
  Gemini tool identifiers, not Claude identifiers.
- No unknown keys; the validator uses `.strict()` so any extra key
  (e.g. `tier`, `mode`) is rejected.

Gemini's first-party tool identifiers (used in built-in agents and
docs) are: `ReadFile`, `WriteFile`, `Edit`, `ReadFolder`, `FindFiles`,
`SearchText`, `RunShellCommand`, `GoogleSearch`, `WebFetch`, `SaveMemory`.

## tool mapping (claude -> gemini)

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

Unknown source tools should be dropped (logged via the existing
`SyncResult.warnings`) so a single typo in a source agent does not break
the whole sync.

## constraints

- Source-of-truth agents must keep their Claude-flavoured authoring
  schema (the user authors against Claude tool names today; rewriting
  10 source files would expand the blast radius unnecessarily).
- The renaming must happen at sync time, per provider, and must not
  modify the source files on disk.
- The fix must not regress Claude (which currently works because it
  ignores unknown keys).
- The Codex render path must be left untouched; it already owns its
  own rendering.

## open questions

- Should the renderer also strip vaultspec-internal keys (`tier`,
  `mode`, `model`) for Claude as well, even though Claude tolerates
  them? (Decided in ADR: yes - clean output regardless of tolerance.)
- Should an unknown Claude tool fail the sync or skip with a warning?
  (Decided in ADR: skip with warning, mirroring how parse warnings
  flow through `SyncResult.warnings`.)
