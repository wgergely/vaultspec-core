---
order: 3
---

# Vaultspec Framework

- You're operating within `vaultspec`: a spec-driven development framework.
- You **must translate user requests into structured workflows** using the provided
  vaultpsec-* skills and agent personas.
- **MUST read before starting a new pipeline phase** relevant `.vault/` documents.
  Check for any previous audit or adr overlap. All records are stored in
  `.vault/` in `adr/`, `audit/`, `exec/`, `plan/`, `reference/` and `research/`.


All significant work must follow this pipeline:

| Phase       | Skill               | Artifact              | Requires          |
|-------------|---------------------|-----------------------|-------------------|
| 1 Research  | vaultspec-research  | .vault/research/...   | —                 |
| 1 Reference | vaultspec-code-reference | .vault/reference/...  | —                 |
| 2 Specify   | vaultspec-adr       | .vault/adr/...        | Research artifact |
| 3 Plan      | vaultspec-write-plan     | .vault/plan/...       | ADR artifact      |
| 4 Execute   | vaultspec-execute   | .vault/exec/.../steps | Approved plan     |
| 5 Verify    | vaultspec-code-review    | .vault/exec/.../review| Completed step(s) |

Supporting skills, invoke when appropriate:

| Curate        | vaultspec-curate        | Maintain .vault/ hygiene — links, tags |
| Documentation | vaultspec-documentation | Write project documentation            |

- **Utilize vaultspec- skills** to interpret user intent:

| Example User Intent                | Invoke                  |
|------------------------------------|-------------------------|
| "Research X" / "Investigate"       | vaultspec-research      |
| "Decide on X" / "Create an ADR"    | vaultspec-adr           |
| "How does [codebase] implement X?" | vaultspec-code-reference     |
| "Plan the implementation"          | vaultspec-write-plan         |
| "Execute the plan" / "Build it"    | vaultspec-execute       |
| "Review the code" / "Verify"       | vaultspec-code-review        |
| "Clean up docs" / "Curate"         | vaultspec-curate        |
| "Start a new feature" (broad)      | vaultspec-research      |
| "Write documentation for {subject}"| vaultspec-documentation |

## Agents

Agent personas are defined in `.vaultspec/rules/agents/`. Two mechanisms are
available depending on task complexity:

- **Parallel sub-agents** for focused, managed work
- **Agent teams** for self-orchestrating complex challanges using the team dispatch
  tools.



Artifacts are persisted in `.vault/`.
The user must approve plans before execution proceeds. Code review via
vaultspec-code-review is mandatory after execution.

<!-- end conventions -->
