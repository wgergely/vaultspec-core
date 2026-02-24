---
tags:
  - "#adr"
  - "#system-prompt"
date: "2026-02-18"
related:
  - "[[2026-02-18-system-prompt-architecture-research]]"
  - "[[2026-02-18-system-prompt-restructure-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# system-prompt adr: use append mode for Claude sub-agent system prompts | (**status:** accepted)

## Problem Statement

Claude sub-agents spawned via the ACP bridge (`claude_bridge.py`) currently pass
`system_prompt` as a plain string to `ClaudeAgentOptions`. The `claude-agent-sdk`
maps this to `--system-prompt`, which **completely replaces** Claude Code's default
system prompt. Sub-agents lose all built-in behavioral instructions: tool usage
documentation (Bash, Read, Edit, Write, Glob, Grep parameter guidance), safety
guardrails (commit protocols, sensitive file detection, force-push protection),
dynamic platform context (OS, shell, git status), and skill/slash-command
awareness.

The SDK exposes `SystemPromptPreset` — a dict-based alternative that maps to
`--append-system-prompt`, preserving Claude Code's defaults while appending custom
content.

## Considerations

- **`claude-agent-sdk` v0.1.36** provides `SystemPromptPreset` TypedDict:
  `{"type": "preset", "preset": "claude_code", "append": "..."}`. This maps to
  `--append-system-prompt` on the CLI.
- Passing `system_prompt` as a plain string maps to `--system-prompt` (full
  replacement). Passing `None` maps to `--system-prompt ""` (also clears default).
- The SDK's `setting_sources` parameter controls whether Claude Code natively
  loads `.claude/CLAUDE.md` and `.claude/rules/*.md`. When `None` (the default),
  **no filesystem settings are loaded** — the SDK provides isolation by default.
- Two viable paths exist:
  - **Path A**: Append persona-only, set `setting_sources=["project"]` for native
    CLAUDE.md/rules loading. Requires removing manual `load_system_prompt()` +
    `load_rules()` from `ClaudeProvider`.
  - **Path B**: Append the full composition (persona + CLAUDE.md + rules) as today,
    leave `setting_sources` at default. Claude Code provides tool instructions; we
    provide project context. No double-injection risk.
- The SDK also exposes `AgentDefinition` for native subagents (via `agents` param
  on `ClaudeAgentOptions`). This is a lighter-weight mechanism where subagents run
  within the same Claude Code process. Our ACP-based dispatch spawns separate
  processes and is better suited for isolated, sandboxed agent workloads.

## Constraints

- Must not change the content composition pipeline — `ClaudeProvider.construct_system_prompt()`
  continues to assemble persona + CLAUDE.md + rules as before.
- Must not introduce a dependency on `setting_sources` — we maintain explicit
  control over what project context reaches sub-agents.
- Must preserve backward compatibility: existing agent YAML frontmatter, environment
  variables, and CLI flags continue to work unchanged.
- The change must be confined to `_build_options()` in `claude_bridge.py`.

## Implementation

**Path B (Append + No Native Loading)**: Change one line in
`ClaudeACPBridge._build_options()` to wrap the existing `system_prompt` string
in a `SystemPromptPreset` dict instead of passing it raw.

Before:

```python
"system_prompt": self._system_prompt,
```

After:

```python
"system_prompt": (
    {"type": "preset", "preset": "claude_code", "append": self._system_prompt}
    if self._system_prompt
    else {"type": "preset", "preset": "claude_code"}
),
```

When `self._system_prompt` is a non-empty string (the common case), this produces
`--append-system-prompt <content>` instead of `--system-prompt <content>`. When
`self._system_prompt` is falsy, it produces no system prompt flag at all, letting
Claude Code use its unmodified default.

No changes to `ClaudeProvider`, `ProcessSpec`, `core.config`, agent YAML, or the
environment variable protocol.

## Rationale

**Why Path B over Path A:** Path A creates a coupling to Claude Code's native
settings loading mechanism and requires gutting `load_system_prompt()` +
`load_rules()` from `ClaudeProvider`. Path B is a single-line change that
preserves the existing composition pipeline while gaining Claude Code's built-in
tool instructions, safety guardrails, and platform awareness. Minor content overlap
between our rules and Claude Code's defaults is harmless.

**Why append over replace:** Sub-agents operate as Claude Code processes and
benefit from knowing how to use the tools correctly. The built-in system prompt
includes detailed parameter documentation, quoting rules, error handling patterns,
and platform-specific guidance that our custom prompt does not replicate. Losing
these instructions degrades sub-agent tool usage quality.

**Why not per-agent `prompt_mode`:** A feature flag adds complexity for a marginal
benefit. No current agent persona conflicts with Claude Code's defaults. If a
specific agent needs full replacement in the future, the flag can be added then.

## Consequences

- Sub-agents gain Claude Code's built-in tool instructions, safety guardrails,
  dynamic platform context, and skill awareness — previously lost entirely.
- Minor content duplication: our behavioral rules (git workflow, security, tone)
  may partially overlap with Claude Code's defaults. This is harmless and may
  even reinforce important behaviors.
- Total system prompt token count increases by the size of Claude Code's default
  prompt (~4-6K tokens). This is offset by improved tool usage quality and reduced
  need for retries due to malformed tool calls.
- If Anthropic updates Claude Code's default system prompt (new tools, changed
  safety rules), sub-agents automatically benefit without vaultspec code changes.
- Existing tests that assert on `captured["system_prompt"]` being a string need
  updating to expect a `SystemPromptPreset` dict.
