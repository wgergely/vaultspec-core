---
tags:
  - "#adr"
  - "#system-prompt"
date: "2026-02-18"
related:
  - "[[2026-02-18-system-prompt-architecture-research]]"
  - "[[2026-02-17-bootstrap-prompt-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# system-prompt adr: restructure system/ for tool-agnostic composition | (**status:** accepted)

## Problem Statement

The `.vaultspec/system/` prompt composition pipeline produces a Gemini-specific
assembled SYSTEM.md graded C+ and a Claude CLAUDE.md that contains zero
behavioral instructions. Two of the four "shared" files (`base.md`,
`operations.md`) contain Gemini-specific tool names and constructs without
`tool:` frontmatter, meaning any new tool added to the pipeline would inherit
Gemini-specific instructions. Claude Code receives only the vaultspec pipeline
bootstrap and two rule references -- none of the behavioral mandates, security
rules, git workflow, or tone guidelines reach it.

## Considerations

- Claude Code has `--append-system-prompt` for actual system prompt injection,
  but `.claude/rules/` is the persistent mechanism that integrates with the
  existing sync pipeline
- Gemini CLI's SYSTEM.md assembly works but suffers from ordering issues
  (alphabetical sort places workflow routing last) and disproportionate content
  (shell examples consume ~40% of the prompt)
- CLAUDE.md and `.claude/rules/` content is injected as `<system-reminder>` user
  context with a "may or may not be relevant" disclaimer (known issue #7571),
  not as actual system prompt -- this is a Claude Code platform limitation
- Gemini's GEMINI.md context is concatenated into the actual `systemInstruction`
  API field -- fundamentally different from Claude's approach
- The current "Jean-Claude" persona in base.md is tool-specific and conflicts
  with Claude Code's built-in identity
- Shell tool examples in gemini.md are well-written but consume excessive
  tokens on every conversation turn regardless of task relevance

## Constraints

- Cannot modify Claude Code's injection mechanism (platform constraint)
- Must maintain backward compatibility with existing `cli.py` sync commands
- Must not break the existing `pipeline: config` mechanism for framework.md
  and project.md
- Assembly logic changes must not require manual intervention from users
- All changes must pass the existing 87-test CLI test suite

## Implementation

### Phase 1: Make system/ files truly tool-agnostic

**1a. Split operations.md** into shared and Gemini-specific parts:

- `operations.md` (shared): Keep tone/style, security principles, git workflow.
  Replace all Gemini tool names with generic language or remove tool-specific
  instructions entirely. Remove `run_shell_command` -> "shell commands".
  Remove `save_memory`, `/help`, `/bug`, `read_file` references.
- `operations-gemini.md` (`tool: gemini`): Move all Gemini-specific tool
  references here: `run_shell_command` usage details, `save_memory` guidance,
  `/help` and `/bug` commands, `read_file` reminders.

**1b. Clean base.md:**

- Remove "Jean-Claude" persona name from line 1. Replace with a generic
  identity or remove the identity statement entirely (each tool has its own
  built-in identity).
- Move line 14 (`activate_skill` / `<activated_skill>` guidance) to `gemini.md`.

**1c. Fix small defects:**

- Remove `****` typo from operations.md line 33.
- Replace allcaps "IT IS CRITICAL" with a normal-case directive.
- Fix forward-reference in gemini.md line 64 (remove "above").
- Move "Do not use numbered lists" from base.md line 9 (Comments rule) to
  the Tone and Style section of operations.md.

### Phase 2: Generate Claude behavioral rules

**2a. Add Claude-specific rule generation** to `cli.py`:

- During `system sync`, if a ToolConfig has `rules_dir` but no `system_file`,
  generate behavioral rules into the rules directory from the shared system/
  parts.
- Produce a single `vaultspec-system.builtin.md` rule file in `.claude/rules/`
  containing the assembled shared behavioral content (base.md + shared
  operations.md + workflow.md).
- This rule file gets the `.builtin.md` suffix so it is managed by the sync
  engine (auto-updated, auto-pruned) and not confused with user-authored rules.

**2b. Frontmatter for generated rules:**

The generated rule file should have appropriate Claude Code rules frontmatter
(no `paths:` restriction so it applies globally).

### Phase 3: Assembly ordering

**3a. Add `order:` frontmatter key** to control assembly position:

- Lower numbers appear first. Files without `order:` default to 50.
- `base.md`: order 10 (always first -- already hardcoded, no change needed)
- `workflow.md`: add `order: 20` so it appears early in the assembly
- `operations.md`: no order key (defaults to 50)
- Tool-specific files: no change (already placed after base by the assembly
  logic)

**3b. Update `_generate_system_prompt`** to sort remaining shared parts by
`order` then by name, instead of by name only.

### Phase 4: Reduce shell example volume

**4a. Move detailed examples** from `gemini.md` to the corresponding skill
files (`vaultspec-fd`, `vaultspec-rg`, `vaultspec-sd`, `vaultspec-sg`).

**4b. Replace with concise descriptions** in `gemini.md`: one-line description
per tool with key flags, no multi-line code blocks.

## Rationale

**Why `.claude/rules/` over `--append-system-prompt`:**
The `--append-system-prompt` flag has higher priority but is session-only and
requires a wrapper script or launcher configuration. `.claude/rules/` integrates
with the existing sync pipeline, is persistent, and is the standard mechanism
for Claude Code project configuration. Despite the `<system-reminder>` disclaimer
issue, rules content is consistently followed in practice.

**Why split rather than add `tool: gemini` to operations.md:**
Some content in operations.md IS genuinely shared (tone/style, security
principles, git workflow). Adding `tool: gemini` would exclude this content
from Claude's rules generation. Splitting preserves the shared content for
all tools while isolating the Gemini-specific portions.

**Why `order:` frontmatter over hardcoded ordering:**
Hardcoding assembly order in cli.py couples content decisions to code. A
frontmatter key keeps ordering decisions with the content authors and is
easily adjustable without code changes.

**Why a single `vaultspec-system.builtin.md` rule rather than multiple:**
Claude Code loads all rules files with equal priority. Splitting into multiple
files (e.g., `vaultspec-security.builtin.md`, `vaultspec-git.builtin.md`)
would increase file count without changing behavior. A single file is simpler
to maintain and reduces sync overhead.

## Consequences

- **Breaking change to operations.md:** Existing content splits into two files.
  The sync engine handles this transparently -- old SYSTEM.md is regenerated.
- **New generated artifact:** `.claude/rules/vaultspec-system.builtin.md` is a
  new file that will be created during `system sync`. It is gitignored (all
  `.claude/rules/` builtin files are generated artifacts).
- **Shell example relocation:** Moving examples from gemini.md to skill files
  means they are only available when the skill is activated, not on every turn.
  This trades always-available reference for reduced per-turn token cost.
- **Test updates required:** Tests that assert on operations.md content or
  SYSTEM.md assembly order will need updating.
- **Disclaimer limitation:** Claude's behavioral rules will still carry the
  "may or may not be relevant" disclaimer. This is a Claude Code platform
  limitation that cannot be resolved at the vaultspec level. If Claude Code
  fixes #7571, the rules will automatically benefit.
