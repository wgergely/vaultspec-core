---
tags:
  - '#reference'
  - '#rules-path-audit'
date: '2026-02-20'
related:
  - '[[2026-02-15-provider-parity-reference]]'
---

# Reference: `.vaultspec/rules/` Path Audit

Crate(s): N/A (documentation audit)
File(s): All `.md` files under `.vaultspec/rules/`
Related: N/A

______________________________________________________________________

## Executive Summary

39 files were audited under `.vaultspec/rules/`. All rules, agents, skills,
templates, and system prompts now reside under `.vaultspec/rules/` (confirmed
by filesystem check — no bare `.vaultspec/agents/`, `.vaultspec/skills/`,
`.vaultspec/templates/`, or `.vaultspec/system/` directories exist at the
top level).

**Two categories of stale references were found:**

1. **Old bare paths** — references to `.vaultspec/agents/`, `.vaultspec/templates/`
   etc. that omit the `rules/` segment. These are the primary stale findings.

1. **Structural inconsistency** — `system/framework.md` contains a directory
   table that lists `agents/`, `skills/`, `templates/`, `system/` as top-level
   folders under `.vaultspec/`, without mentioning that they now live under
   `.vaultspec/rules/`.

No `@rules/...` include syntax is used anywhere — there are zero occurrences.
No YAML frontmatter `skill_file:`, `agent_file:`, or `template:` path fields
exist in any file. Wiki-links (`[[...]]`) are all used as artifact cross-
references (e.g., `[[yyyy-mm-dd-feature-plan]]`), not as filesystem path
references — they are all correct by convention.

______________________________________________________________________

## Finding 1 — Stale `.vaultspec/agents/` references

These references should read `.vaultspec/rules/agents/`.

### `.vaultspec/rules/rules/vaultspec-skills.builtin.md`

- **Line 36:** `.vaultspec/agents`

  ```
  Make sure to utilize the sub-agents defined in
  `.vaultspec/agents`. Dispatch them using the
  `vaultspec-subagent` skill.
  ```

  STATUS: STALE — omits `rules/` segment. Correct path is `.vaultspec/rules/agents/`.

### `.vaultspec/rules/skills/vaultspec-subagent.md`

- **Line 33:** `.vaultspec/agents/`

  ```
  > `--agent`: The name of the agent to load from `.vaultspec/agents/`
  ```

  STATUS: STALE — omits `rules/` segment. Correct path is `.vaultspec/rules/agents/`.

______________________________________________________________________

## Finding 2 — Stale `.vaultspec/templates/` references

These references should read `.vaultspec/rules/templates/`.

### `.vaultspec/rules/skills/vaultspec-research.md`

- **Line 36:** `.vaultspec/templates/research.md`

  ```

  - You MUST read and use the template at `.vaultspec/templates/research.md`.
  ```

  STATUS: STALE — omits `rules/` segment. Correct path is `.vaultspec/rules/templates/research.md`.

### `.vaultspec/rules/skills/vaultspec-adr.md`

- **Line 36:** `.vaultspec/templates/adr.md`

  ```

  - You MUST read and use the template at `.vaultspec/templates/adr.md`.
  ```

  STATUS: STALE — omits `rules/` segment.

- **Line 59:** `.vaultspec/templates/adr.md`

```
    the findings in `[[...-research]]`. Use the template at
    `.vaultspec/templates/adr.md`."
```

STATUS: STALE — omits `rules/` segment.

### `.vaultspec/rules/skills/vaultspec-write-plan.md`

- **Line 48:** `.vaultspec/templates/plan.md`

  ```

  - You MUST read and use the template at `.vaultspec/templates/plan.md`.
  ```

  STATUS: STALE — omits `rules/` segment.

- **Line 70:** `.vaultspec/templates/plan.md`

```
    `[[...-adr]]`. Use the template at `.vaultspec/templates/plan.md`."
```

STATUS: STALE — omits `rules/` segment.

### `.vaultspec/rules/skills/vaultspec-execute.md`

- **Line 47:** `.vaultspec/templates/exec-step.md`

  ```

  - **Template**: You MUST read and use the template at
    `.vaultspec/templates/exec-step.md`.
  ```

  STATUS: STALE — omits `rules/` segment.

- **Line 79:** `.vaultspec/templates/exec-summary.md`

```

  - **Template**: You MUST read and use the template at
    `.vaultspec/templates/exec-summary.md`.
```

STATUS: STALE — omits `rules/` segment.

### `.vaultspec/rules/skills/vaultspec-code-review.md`

- **Line 51:** `.vaultspec/templates/code-review.md`

  ```

  - **Template:** You MUST read and use the template at
    `.vaultspec/templates/code-review.md`.
  ```

  STATUS: STALE — omits `rules/` segment.

### `.vaultspec/rules/agents/vaultspec-writer.md`

- **Line 41:** `.vaultspec/templates/plan.md`

  ```
  You must use the template at `.vaultspec/templates/plan.md` and persist `<Plan>`
  ```

  STATUS: STALE — omits `rules/` segment.

- **Line 60:** `.vaultspec/templates/plan.md`

```
  **Template**: Read `.vaultspec/templates/plan.md` and populate the YAML
```

STATUS: STALE — omits `rules/` segment.

### `.vaultspec/rules/agents/vaultspec-simple-executor.md`

- **Line 39:** `.vaultspec/templates/exec-step.md`

  ```

      - **Template**: You MUST read and use the template at
        `.vaultspec/templates/exec-step.md`.
  ```

  STATUS: STALE — omits `rules/` segment.

### `.vaultspec/rules/agents/vaultspec-code-reviewer.md`

- **Line 75:** `.vaultspec/templates/code-review.md`

  ```

  - **Template:** You MUST read and use the template at
    `.vaultspec/templates/code-review.md`.
  ```

  STATUS: STALE — omits `rules/` segment.

### `.vaultspec/rules/agents/vaultspec-adr-researcher.md`

- **Line 77:** `.vaultspec/templates/research.md`

  ```

  - You MUST read and use the template at `.vaultspec/templates/research.md`.
  ```

  STATUS: STALE — omits `rules/` segment.

______________________________________________________________________

## Finding 3 — Structural inconsistency in framework.md

### `.vaultspec/rules/system/framework.md`

- **Lines 74–78:** Directory table lists bare sub-folder names as if they are
  direct children of `.vaultspec/`, without acknowledging the `rules/`
  consolidation:

  ```
  | rules/     | Persistent behavioral rules, always loaded into sessions |
  | skills/    | Activatable workflow recipes, invoked by name            |
  | agents/    | Sub-agent persona definitions, dispatched by skills      |
  | templates/ | Structural schemas for .vault/ artifacts                 |
  | system/    | Composable system prompt fragments                       |
  ```

  STATUS: STALE / MISLEADING — `skills/`, `agents/`, `templates/`, and `system/`
  are not top-level children of `.vaultspec/`; they are sub-folders under
  `.vaultspec/rules/`. The table implies a flat layout that no longer exists.

- **Line 81:** `.vaultspec/templates/`

```
  research/). Each artifact follows a template from `.vaultspec/templates/` with
```

STATUS: STALE — omits `rules/` segment. Correct path is `.vaultspec/rules/templates/`.

______________________________________________________________________

## Finding 4 — Stale `.vaultspec/logs/` reference

### `.vaultspec/rules/skills/vaultspec-subagent.md`

- **Line 72:** `.vaultspec/logs/yyyy-mm-dd-{session_id}.log`

  ```

  - Session logs are written to
    `.vaultspec/logs/yyyy-mm-dd-{session_id}.log`.
  ```

  STATUS: SUSPECT — `.vaultspec/logs/` is not a documented directory in the
  framework layout (not under `rules/`, `lib/`, or any canonical path defined
  in the conventions). This may be aspirational/stale documentation from a
  prior design. Needs verification against actual runtime behavior in
  `subagent.py`.

______________________________________________________________________

## Finding 5 — Correct references (confirmed good)

These `.vaultspec/` paths correctly go through `rules/`:

- `.vaultspec/rules/skills/vaultspec-curate.md` lines 13, 90:
  `.vaultspec/rules/rules/vaultspec-documentation.builtin.md` — CORRECT.

- `.vaultspec/rules/agents/vaultspec-docs-curator.md` lines 28, 87:
  `.vaultspec/rules/rules/vaultspec-documentation.builtin.md` — CORRECT.

- `.vaultspec/rules/agents/vaultspec-docs-curator.md` line 29:
  `.vaultspec/rules/templates/*.md` — CORRECT.

- `.vaultspec/rules/rules/vaultspec-subagents.builtin.md` line 31:
  `.vaultspec/lib/scripts/subagent.py` — CORRECT (lib/ path, unaffected by
  migration).

- `.vaultspec/rules/skills/vaultspec-subagent.md` lines 28, 55, 63:
  `.vaultspec/lib/scripts/subagent.py` — CORRECT (lib/ path).

______________________________________________________________________

## Summary Table

| File (relative to repo root)                           | Line  | Exact Text (trimmed)                   | Status  |
| ------------------------------------------------------ | ----- | -------------------------------------- | ------- |
| `.vaultspec/rules/rules/vaultspec-skills.builtin.md`   | 36    | `.vaultspec/agents`                    | STALE   |
| `.vaultspec/rules/skills/vaultspec-subagent.md`        | 33    | `.vaultspec/agents/`                   | STALE   |
| `.vaultspec/rules/skills/vaultspec-research.md`        | 36    | `.vaultspec/templates/research.md`     | STALE   |
| `.vaultspec/rules/skills/vaultspec-adr.md`             | 36    | `.vaultspec/templates/adr.md`          | STALE   |
| `.vaultspec/rules/skills/vaultspec-adr.md`             | 59    | `.vaultspec/templates/adr.md`          | STALE   |
| `.vaultspec/rules/skills/vaultspec-write-plan.md`      | 48    | `.vaultspec/templates/plan.md`         | STALE   |
| `.vaultspec/rules/skills/vaultspec-write-plan.md`      | 70    | `.vaultspec/templates/plan.md`         | STALE   |
| `.vaultspec/rules/skills/vaultspec-execute.md`         | 47    | `.vaultspec/templates/exec-step.md`    | STALE   |
| `.vaultspec/rules/skills/vaultspec-execute.md`         | 79    | `.vaultspec/templates/exec-summary.md` | STALE   |
| `.vaultspec/rules/skills/vaultspec-code-review.md`     | 51    | `.vaultspec/templates/code-review.md`  | STALE   |
| `.vaultspec/rules/agents/vaultspec-writer.md`          | 41    | `.vaultspec/templates/plan.md`         | STALE   |
| `.vaultspec/rules/agents/vaultspec-writer.md`          | 60    | `.vaultspec/templates/plan.md`         | STALE   |
| `.vaultspec/rules/agents/vaultspec-simple-executor.md` | 39    | `.vaultspec/templates/exec-step.md`    | STALE   |
| `.vaultspec/rules/agents/vaultspec-code-reviewer.md`   | 75    | `.vaultspec/templates/code-review.md`  | STALE   |
| `.vaultspec/rules/agents/vaultspec-adr-researcher.md`  | 77    | `.vaultspec/templates/research.md`     | STALE   |
| `.vaultspec/rules/system/framework.md`                 | 75–78 | Directory table omits `rules/` prefix  | STALE   |
| `.vaultspec/rules/system/framework.md`                 | 81    | `.vaultspec/templates/`                | STALE   |
| `.vaultspec/rules/skills/vaultspec-subagent.md`        | 72    | `.vaultspec/logs/...`                  | SUSPECT |

**Total stale/suspect references: 18 across 8 files.**

**Files with zero findings (clean):**

- All template files under `.vaultspec/rules/templates/`
- `.vaultspec/rules/system/base.md`, `gemini.md`, `operations.md`, `operations-gemini.md`, `project.md`, `workflow.md`
- `.vaultspec/rules/rules/vaultspec-documentation.builtin.md`
- `.vaultspec/rules/rules/vaultspec-subagents.builtin.md`
- `.vaultspec/rules/agents/vaultspec-complex-executor.md`, `vaultspec-docs-curator.md`, `vaultspec-code-reference-agent.md`, `vaultspec-researcher.md`, `vaultspec-standard-executor.md`
- `.vaultspec/rules/skills/vaultspec-curate.md`, `vaultspec-fd.md`, `vaultspec-code-reference.md`, `vaultspec-rg.md`, `vaultspec-sd.md`, `vaultspec-sg.md`, `vaultspec-test-health.md`, `vaultspec-test-marketing.md`
