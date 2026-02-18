---
tags: ["#adr", "#framework"]
date: 2026-02-17
related:
  - "[[2026-02-17-bootstrap-prompt-engineering-research]]"
---

# bootstrap-prompt adr: framework bootstrap prompt redesign | (**status:** accepted)

## Problem Statement

The current `.vaultspec/FRAMEWORK.md` is a 9-line stub that fails to bootstrap an LLM agent with operational knowledge of the vaultspec framework. An agent receiving only FRAMEWORK.md (via `config sync` into CLAUDE.md/GEMINI.md) cannot translate user intent into skill/agent invocations, does not know the artifact dependency chain, and has no understanding of the dispatch mechanism.

## Design Decisions

All decisions were made collaboratively with the user based on findings from:

- Internal audit of the full `.vaultspec/` rule system (Task 1)
- External prompt engineering research across Anthropic, Google, OpenAI sources (Task 2)

### D1: Identity Framing — Agent-Role-Centric

The bootstrap addresses the agent directly, establishing its role within the framework rather than describing vaultspec objectively. This follows the CrewAI Role-Goal pattern (R7) and Anthropic's guidance to be explicit and direct (Principle 2).

### D2: Section Boundaries — XML Tags

Use XML tags (`<identity>`, `<pipeline>`, `<dispatch>`, `<conventions>`) for structural section boundaries. Markdown for content within sections. This is optimal for Claude (specifically tuned for XML attention) and compatible with Gemini and GPT models (R2, Principle 4).

### D3: Pipeline Description — Structured Table

A compact table mapping Phase -> Skill -> Artifact -> Dependency. No narrative prose wrapper. Tables are unambiguous, scannable, and match the decision-table pattern that improves tool parameter accuracy (R3).

### D4: Intent-to-Action Mapping — Compact Decision Table Only

6-8 row decision table mapping user intent patterns to the correct skill. No few-shot examples — the table IS the example. Saves ~300 tokens. The research shows exhaustive edge-case lists underperform principles + diverse examples (Principle 8, AP4).

### D5: Trivial Task Exemption — Explicit Rule

One sentence explicitly exempting trivial fixes from the full pipeline: "Trivial fixes and direct edits do not require the full pipeline. Use judgment based on scope and risk." Prevents the framework from being applied to every single-line fix.

### D6: Dispatch Mechanism — Reference Only

One line pointing to the `vaultspec-subagent` skill for dispatch details. Progressive disclosure (Principle 11) — the dispatch mechanism is loaded on demand when the skill activates, avoiding duplication.

### D7: Startup Ritual — Lightweight Check

One sentence: "Check for existing `.vault/` artifacts before starting new pipeline phases." Prevents duplicate work without adding a multi-step checklist to the bootstrap (R9).

### D8: Token Budget — ~2,000 Tokens Core

The core bootstrap stays under ~2,000 tokens. Everything beyond that is accessible via progressive disclosure through skill files, agent definitions, and template references.

## Structure

The bootstrap prompt will use this XML-structured layout:

```xml
<identity>
  2-3 sentences: what vaultspec is, agent's role, core principle
</identity>

<pipeline>
  Table: Phase | Skill | Artifact | Requires
  5 rows (Research, Specify, Plan, Execute, Verify)
  + 1 row for Reference (optional sub-phase)
  + 1 row for Curate (maintenance)
  Trivial-task exemption line
</pipeline>

<dispatch>
  How user intent maps to skill invocation (decision table, ~8 rows)
  Reference to vaultspec-subagent skill for dispatch mechanism
  Lightweight startup check
</dispatch>

<conventions>
  Key file paths and folder roles (rules/, skills/, agents/, templates/)
  Artifact location: .vault/
  Template location: .vaultspec/templates/
  Brief note on approval gates
</conventions>
```

## Principles Applied

From the prompt engineering research:

| Principle | How Applied |
|-----------|------------|
| P1: Context engineering > prompt engineering | Minimal high-signal tokens; progressive disclosure for details |
| P2: Be explicit and direct | Agent-role-centric identity; direct skill references |
| P3: Provide motivation, not just rules | Identity explains WHY (auditable artifacts, governed development) |
| P4: Structured formatting | XML section boundaries + Markdown content |
| P5: Layered hierarchy | Identity -> Pipeline -> Dispatch -> Conventions |
| P8: Few-shot > exhaustive rules | Decision table as implicit few-shot; no edge-case trees |
| P9: Positive instructions | "Use judgment based on scope" not "Do NOT use pipeline for..." |
| P11: Progressive disclosure | Dispatch details deferred to skill files |

## Anti-Patterns Avoided

| Anti-Pattern | How Avoided |
|--------------|------------|
| AP1: Context dumping | ~2,000 token budget; details in skill/agent/template files |
| AP4: Over-specifying edge cases | Decision table, not if-else tree |
| AP5: Burying critical info | Identity and pipeline are the first two sections |
| AP6: ALL-CAPS aggressive language | Calm, direct language throughout |
| AP8: Vague tool descriptions | Each skill explicitly named with purpose |

## Integration Plan

1. The new bootstrap content replaces the body of `.vaultspec/FRAMEWORK.md`
2. `cli.py config sync` continues to serialize it into `system_framework` YAML frontmatter
3. No changes needed to `_generate_config()` — the pipeline is format-agnostic
4. `PROJECT.md` remains as the user-editable companion (body content in generated files)
5. Backward-compat warnings for `INTERNAL.md` -> `FRAMEWORK.md` rename remain unchanged

## Consequences

- Agents bootstrapped via `config sync` will understand the framework without needing to read README.md
- The `See .vaultspec/README.md` redirect is eliminated — the bootstrap is self-sufficient
- README.md becomes documentation for humans, not a crutch for agents
- Individual skill/agent files remain the source of detailed procedural knowledge (progressive disclosure)
- Token budget is respected — the bootstrap is dense but not bloated
