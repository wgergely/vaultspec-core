---
description: "Skill to conduct a formal code review. Audits code for safety, intent, and quality. Mandates dispatching the code-reviewer agent."
---

# Task Review Skill (task-review)

When to use this skill:
- **Mandatory:** At the end of every `task-execute` cycle (before marking a feature as "Done").
- **Ad-hoc:** When you need a second pair of eyes on a specific module or PR.
- **Safety Check:** When you suspect a safety violation (e.g., `unsafe` usage).

**Announce at start:** "I'm using the `task-review` skill to audit the implementation."

## Workflow

### 1. Context Gathering
- Identify the `<Plan>` (`.docs/plan/...`) and the specific files modified.

### 2. Dispatch Reviewer
Invoke the `task-subagent` skill with `code-reviewer`. Instruct it to:
> "Perform a comprehensive code review of [feature/files]. Verify safety (no-crash policy), intent (alignment with [[...-plan.md]]), and code quality. Persist the report to .docs/exec/...-review.md."

### 3. Analysis of Report
- **Pass:** If the reviewer finds no critical issues, you may proceed.
- **Fail:** If the reviewer flags issues, you **MUST** invoke `task-execute` (or dispatch an executor) to fix the issues, then re-run `task-review`.

## Persistence
- **Template:** You MUST read and use the template at `.rules/templates/CODE_REVIEW.md`.
- **Location:** `.docs/exec/yyyy-mm-dd-<feature>/yyyy-mm-dd-<feature>-review.md`.
- **Tags:** Ensure it uses the `#exec` and `#<feature>` tags.
