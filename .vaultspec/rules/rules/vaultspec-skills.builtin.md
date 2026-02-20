---
name: vaultspec-skills
---

# Spec Skills

This project mandates sub-agent based development and
`<ADR>`-backed `<Plan>`s.

The workflow persists the following documents:

- `.vault/plan/yyyy-mm-dd-<feature>-<phase>-plan.md`:
  The `<Plan>` to execute.
- `.vault/research/yyyy-mm-dd-<feature>-<phase>-research.md`:
  The `<Research>` findings.
- `.vault/adr/yyyy-mm-dd-<feature>-<phase>-adr.md`:
  Research-derived `<ADR>`.
- `.vault/reference/yyyy-mm-dd-<feature>-reference.md`:
  The implementation `<Reference>`.
- `.vault/audit/yyyy-mm-dd-<feature>-audit.md`:
  The `<Audit>` report.
- `.vault/exec/yyyy-mm-dd-<feature>/.../<step>.md`:
  The individual `<Step Record>`.
- `.vault/exec/yyyy-mm-dd-<feature>/...-summary.md`:
  The `<Phase Summary>`.

Where appropriate, load and use the following skills:

- `vaultspec-research`
- `vaultspec-adr`
- `vaultspec-reference`
- `vaultspec-write`
- `vaultspec-execute`

Make sure to utilize the sub-agents defined in
`.vaultspec/rules/agents`. Dispatch them using the
`vaultspec-subagent` skill.
