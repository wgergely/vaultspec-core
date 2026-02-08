---
name: task-skills
---

# Task Skills

This project mandates sub-agent based development and `<ADR>`-backed `<Plan>`s.

The workflow persists the following documents:

- `.docs/plan/yyyy-mm-dd-<feature>-<phase>-plan.md`: The `<Plan>` to execute.
- `.docs/research/yyyy-mm-dd-<feature>-<phase>-research.md`: The `<Research>` findings.
- `.docs/adr/yyyy-mm-dd-<feature>-<phase>-adr.md`: Research-derived `<ADR>`.
- `.docs/reference/yyyy-mm-dd-<feature>-reference.md`: The implementation `<Reference>`.
- `.docs/exec/yyyy-mm-dd-<feature>/yyyy-mm-dd-<feature>-<phase>-<step>.md`: The individual `<Step Record>`.
- `.docs/exec/yyyy-mm-dd-<feature>/yyyy-mm-dd-<feature>-<phase>-summary.md`: The `<Phase Summary>`.

Where appropriate, load and use the following skills:

- `task-research`
- `task-adr`
- `task-reference`
- `task-write`
- `task-execute`

Make sure to utilize the sub-agents defined in `.rules/agents`. Dispatch them using the `task-subagent` skill.
