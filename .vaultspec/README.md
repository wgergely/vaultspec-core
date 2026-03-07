# Spec-Driven Development (SDD)

vaultspec is a language-agnostic development framework. Rules, skills, and
templates work with any language and toolchain. Agent personas reference the
project's established conventions rather than prescribing specific tools.

This folder contains the rule and template collection mandating the research,
reference, ADR, and agent-based development process.
The rules are compatible with Google Antigravity, Gemini CLI and Claude Code.

## User Manual

### The Workflow

The system enforces a strict **Research -> Specify -> Plan -> Execute ->
Verify** cycle. You do not simply "write code"; you build a trail of
documentation that ensures quality and context preservation.

**High-Level Summary:**

- **Research (`vaultspec-research`)** & **Reference (`vaultspec-reference`)**
  gather the data.
- **Specify (`vaultspec-adr`)** formalizes the choice.
- **Plan (`vaultspec-write`)** defines the steps.
- **Execute (`vaultspec-execute`)** builds it.
- **Verify (`vaultspec-review`)** validates it.
- **Curate (`vaultspec-curate`)** cleans up.

#### Detailed Steps

- **Research (`vaultspec-research`)**:
  - **Goal:** Understand the problem, explore libraries, and find "frontier"
    patterns.
  - **Agent:** `vaultspec-adr-researcher` (High Tier).
  - **Output:** `.vault/research/...` artifact.
  - *Usage:* "Activate `vaultspec-research` to investigate `{topic}`."

- **Specify (`vaultspec-adr`)**:
  - **Goal:** Make binding technical decisions based on your research.
  - **Output:** `.vault/adr/...` artifact.
  - *Usage:* "Activate `vaultspec-adr` to formalize our decision on
    `{topic}`."

- **Plan (`vaultspec-write`)**:
  - **Goal:** Convert the ADR into a step-by-step implementation plan.
  - **Agent:** `vaultspec-writer` (High Tier).
  - **Output:** `.vault/plan/...` artifact.
  - *Usage:* "Activate `vaultspec-write` to create a plan for `{feature}`."

- **Execute (`vaultspec-execute`)**:
  - **Goal:** Implement the plan using specialized sub-agents.
  - **Agent:** Orchestrator (You) + Executors (`vaultspec-low-executor`,
    `vaultspec-high-executor`).
  - **Output:** Code changes + `.vault/exec/...` logs.
  - *Usage:* "Activate `vaultspec-execute` to implement the plan."

- **Verify (`vaultspec-review`)**:
  - **Goal:** Validate the implementation against the plan and safety
    standards.
  - **Agent:** `vaultspec-code-reviewer` (High Tier).
  - *Usage:* "Activate `vaultspec-review` to audit the implementation."

- **Curate (`vaultspec-curate`)**:
  - **Goal:** Maintain the hygiene of the `.vault/` vault.
  - **Agent:** `vaultspec-docs-curator` (Medium Tier).
  - *Usage:* "Activate `vaultspec-curate` to audit the vault."

### Agent Reference

| Agent | Tier | Role | When to use |
| :--- | :--- | :--- | :--- |
| `vaultspec-adr-researcher` | HIGH | Researcher | New tech, architecture |
| `vaultspec-writer` | HIGH | Planner | After ADR approval |
| `vaultspec-docs-curator` | MED | Librarian | Links, tags, schema |
| `vaultspec-reference-auditor` | MED | Auditor | Codebase patterns |
| `vaultspec-high-executor` | HIGH | Sr. Engineer | Refactors, new logic |
| `vaultspec-standard-executor` | MED | Engineer | Feature work |
| `vaultspec-low-executor` | LOW | Jr. Engineer | Rote tasks, fixes |
| `vaultspec-code-reviewer` | HIGH | Reviewer | Safety, quality |

## Context Management

The system context is managed through config sync and system prompt assembly
in `.vaultspec/`:

- **`system/framework.md` (Bootstrap Prompt):** The XML-structured bootstrap
  prompt that cold-starts an LLM agent with operational knowledge of
  vaultspec — identity, pipeline phases, intent-to-skill mapping, dispatch
  references, and folder conventions. Lives in `system/` with
  `pipeline: config` frontmatter so it feeds into `config sync` output only
  (not `system sync`).
- **`system/project.md` (User-Editable):** A placeholder for
  project-specific instructions, extra context, or user preferences. This
  content is appended verbatim to the generated config files.
- **`vaultspec config sync`:** This command synchronizes `system/framework.md`
  and `system/project.md` into the root `AGENTS.md` and tool-specific files
  (`CLAUDE.md`, `GEMINI.md`).
- **`vaultspec system show`:** Displays the composable system prompt parts and
  their generation targets.
- **`vaultspec system sync`:** Assembles parts from `system/` into `SYSTEM.md`
  and syncs it to tool destinations (e.g., `.gemini/SYSTEM.md`).

**Syntactic Stability:**
Framework context is stored in the **YAML frontmatter** (under the
`system_framework` key) of the generated files to ensure it remains
syntactically stable and separated from user-provided content.

### File Responsibilities

| File | Purpose | Managed By |
| :--- | :--- | :--- |
| `system/framework.md` | Bootstrap prompt | `config sync` |
| `system/project.md` | Project context | User |
| `AGENTS.md` | Root AI entry point | `vaultspec` |
| `CLAUDE.md` | Claude Code config | `vaultspec` |
| `GEMINI.md` | Gemini CLI config | `vaultspec` |
| `system/` | Composable prompts | Developer |
| `SYSTEM.md` | Gemini system prompt | `vaultspec` |

## Overview Diagram

> **Note:** The `vaultspec-subagent` skill is a **utility task** used
> internally by other agents. It should **not** be called directly by the
> user.

```mermaid
flowchart TD
    %% Core Nodes
    Feature["&lt;Feature&gt;<br/>The glue that binds them all"]
    Research["&lt;Research&gt;<br/>Brainstorming & research<br/>(no routes)"]
    Reference["&lt;Reference&gt;<br/>Technical audit"]
    ADR["&lt;ADR&gt;<br/>Decision record"]
    Plan{"**&lt;Plan&gt;**<br/>Actionable steps"}
    StepRecord["&lt;Step Record&gt;<br/>&lt;Plan&gt; execution artifact"]
    PhaseSummary["&lt;Phase Summary&gt;<br/>Summary after &lt;Steps&gt;"]
    TaskSummary["&lt;Task Summary&gt;<br/>Summary after &lt;Phases&gt;"]
    FinalFeature["&lt;Feature&gt; Implemented Code"]

    %% Relationships
    Feature --> Research
    Feature --> Reference
    Research --> ADR
    Feature --> ADR
    Reference --> ADR
    ADR --> Plan
    Plan --> StepRecord
    StepRecord --> PhaseSummary
    PhaseSummary --> TaskSummary
    TaskSummary --> FinalFeature
    FinalFeature -- Testing & Auditing --> Plan
```

## Markdown Files

Workflows, agents, skills, and templates are defined in their respective
subfolders without any tool specific yaml configuration headers or metadata.
Tools reference relatively the `.vaultspec` folder and define their own
tool-specific yaml configuration headers.

## Example Workflow

A possible workflow might look something like this, disregarding loopbacks
and decision reversals:

```mermaid
flowchart TD
    %% NODES
    START["Start: User Prompt"]

    %% Phase 1: Research
    SK_RES["Skill: vaultspec-research<br/>Announce"]
    SK_SUB_RES["Skill: vaultspec-subagent<br/>Run Command: vaultspec subagent"]
    SA_RES["Agent: vaultspec-adr-researcher<br/>Search<br/>Write Artifact"]
    PH1_END["Phase 1 Complete"]

    %% Phase 2: Specify
    SK_ADR["Skill: vaultspec-adr<br/>Announce<br/>Write ADR<br/>Notify"]
    PH2_END["Phase 2 Complete"]

    %% Phase 3: Plan
    SK_REF["Skill: vaultspec-reference<br/>Announce"]
    SK_SUB_REF["Skill: vaultspec-subagent<br/>Run Command: vaultspec subagent"]
    SA_REF["Agent: vaultspec-reference-auditor<br/>Audit Ref<br/>Write Artifact"]

    SK_WRITE["Skill: vaultspec-write<br/>Announce"]
    SK_SUB_WRITE["Skill: vaultspec-subagent<br/>Run Command: vaultspec subagent"]
    SA_WRITER["Agent: vaultspec-writer<br/>Plan Codebase<br/>Write Artifact"]
    PH3_END["Phase 3 Complete"]

    %% Phase 4: Execute
    SK_EXEC["Skill: vaultspec-execute<br/>Announce"]
    SK_SUB_EXEC["Skill: vaultspec-subagent<br/>Run Command: vaultspec subagent"]
    SA_EXEC["Agent: vaultspec-high-executor<br/>Edit Code<br/>Validate"]

    %% Phase 5: Verify
    SK_REV["Skill: vaultspec-review<br/>Announce"]
    SK_SUB_REV["Skill: vaultspec-subagent<br/>Run Command: vaultspec subagent"]
    SA_REV["Agent: vaultspec-code-reviewer<br/>Audit Safety/Intent<br/>Report"]

    EXEC_RET["Execution Return"]
    PH4_END["Phase 4 Complete"]

    %% Revision (if needed)
    SK_FIX["Skill: vaultspec-execute (Fixes)<br/>Announce"]
    SK_SUB_FIX["Skill: vaultspec-subagent<br/>Run Command: vaultspec subagent"]
    SA_FIX["Agent: vaultspec-standard-executor<br/>Fix Code<br/>Verify"]
    PH5_END["Phase 5 Complete"]

    %% Conclusion
    ACTION_GIT["Action: Commit<br/>git add<br/>git commit"]
    END_NODE["End"]

    %% EDGES
    START --> SK_RES

    %% Phase 1 Branching
    SK_RES -- Main Flow --> PH1_END
    SK_RES -- Invokes --> SK_SUB_RES
    SK_SUB_RES -- Dispatches --> SA_RES
    SA_RES -- Reconnects --> PH1_END

    PH1_END --> SK_ADR
    SK_ADR --> PH2_END

    %% Phase 3 Branching
    PH2_END --> SK_REF
    SK_REF -- Main Flow --> SK_WRITE
    SK_REF -- Invokes --> SK_SUB_REF
    SK_SUB_REF -- Dispatches --> SA_REF
    SA_REF -- Reconnects --> SK_WRITE

    SK_WRITE -- Main Flow --> PH3_END
    SK_WRITE -- Invokes --> SK_SUB_WRITE
    SK_SUB_WRITE -- Dispatches --> SA_WRITER
    SA_WRITER -- Reconnects --> PH3_END

    %% Phase 4 Execution
    PH3_END --> SK_EXEC
    SK_EXEC -- Main Flow --> SK_REV
    SK_EXEC -- Invokes --> SK_SUB_EXEC
    SK_SUB_EXEC -- Dispatches --> SA_EXEC
    SA_EXEC -- Reconnects --> SK_REV

    %% Review Loop
    SK_REV -- Invokes --> SK_SUB_REV
    SK_SUB_REV -- Dispatches --> SA_REV
    SA_REV -- Reconnects --> SK_REV

    SK_REV -- "Pass" --> PH4_END
    SK_REV -- "Fail/Revision" --> SK_FIX

    %% Fix Loop
    SK_FIX -- Invokes --> SK_SUB_FIX
    SK_SUB_FIX -- Dispatches --> SA_FIX
    SA_FIX -- Reconnects --> SK_REV

    PH4_END --> ACTION_GIT
    ACTION_GIT --> END_NODE
```
