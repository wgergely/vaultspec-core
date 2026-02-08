# Research, Design, Task Driven Development

This folder contains the rule and template collection mandating the research, reference, ADR, and sub-agent based developmment process.
The rules are compatible with Google Antigravity, Gemini CLI and Claude Code.

## User Manual

### 1. The Workflow

The system enforces a strict **Research → Decide → Plan → Execute** cycle. You do not simply "write code"; you build a trail of documentation that ensures quality and context preservation.

**High-Level Summary:**
*   **Research (`task-research`)** & **Reference (`task-reference`)** gather the data.
*   **ADR (`task-adr`)** formalizes the choice.
*   **Plan (`task-write`)** defines the steps.
*   **Execute (`task-execute`)** builds it.
*   **Review (`task-review`)** validates it.
*   **Curate (`docs-curator`)** cleans up.

#### Detailed Steps

1.  **Research (`task-research`)**:
    *   **Goal:** Understand the problem, explore libraries, and find "frontier" patterns.
    *   **Agent:** `adr-researcher` (High Tier).
    *   **Output:** `.docs/research/...` artifact.
    *   *Usage:* "Activate `task-research` to investigate [topic]."

2.  **Architect (`task-adr`)**:
    *   **Goal:** Make binding technical decisions based on your research.
    *   **Output:** `.docs/adr/...` artifact.
    *   *Usage:* "Activate `task-adr` to formalize our decision on [topic]."

3.  **Plan (`task-write`)**:
    *   **Goal:** Convert the ADR into a step-by-step implementation plan.
    *   **Agent:** `task-writer` (High Tier).
    *   **Output:** `.docs/plan/...` artifact.
    *   *Usage:* "Activate `task-write` to create a plan for [feature]."

4.  **Execute (`task-execute`)**:
    *   **Goal:** Implement the plan using specialized sub-agents.
    *   **Agent:** Orchestrator (You) + Executors (`simple-executor`, `complex-executor`).
    *   **Output:** Code changes + `.docs/exec/...` logs.
    *   *Usage:* "Activate `task-execute` to implement the plan."

5.  **Curate (`docs-curator`)**:
    *   **Goal:** Maintain the hygiene of the `.docs/` vault.
    *   **Agent:** `docs-curator` (Medium Tier).
    *   *Usage:* "Run the `docs-curator` agent to audit the vault."

### 2. Agent Reference

| Agent | Tier | Role | When to use |
| :--- | :--- | :--- | :--- |
| **`adr-researcher`** | HIGH | Lead Researcher | When exploring new technologies, libraries, or complex architectural problems. |
| **`task-writer`** | HIGH | Planner | After an ADR is approved. Converts decisions into actionable steps. |
| **`docs-curator`** | MEDIUM | Librarian & Orchestrator | To fix broken links, bad tags, and strictly enforce documentation schema rules. |
| **`reference-auditor`** | MEDIUM | Code Auditor | To scan the codebase or reference implementations (e.g., Zed) for patterns to copy. |
| **`complex-executor`** | HIGH | Senior Engineer | For difficult logic, refactors, or "blank slate" implementations requiring deep reasoning. |
| **`standard-executor`** | MEDIUM | Engineer | For typical feature work, component implementation, and standard logic. |
| **`simple-executor`** | LOW | Junior Engineer | For rote tasks, text updates, simple fixes, and menial labor dispatched by other agents. |
| **`code-reviewer`** | HIGH | Reviewer & Safety Officer | To audit code for safety, intent compliance, and quality. Replaces the legacy safety-auditor. |

## Overview Diagram

> **Note:** The `task-subagent` skill is a **utility task** used internally by other agents. It should **not** be called directly by the user.

```mermaid
flowchart TD
    %% Core Nodes
    Feature["&lt;Feature&gt;<br/>The glue that binds them all"]
    Research["&lt;Research&gt;<br/>Brainstorming & research<br/>(no routes)"]
    Reference["&lt;Reference&gt;<br/>Technical implementation<br/>from specialist source"]
    ADR["&lt;ADR&gt;<br/>Conclusion based on<br/>&lt;Research&gt; + &lt;Reference&gt;"]
    Plan{"**&lt;Plan&gt;**<br/>Actionable Steps based on codebase and &lt;ADR&gt;, &lt;Research&gt;, &lt;Reference&gt;"}
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

Workflows, agents, skills, and templates are defined in their respective subfolders without any tool specific yaml configuration headers or metadata.
Tools reference relatively the `.rules` folder. and define their tool specific yaml configuration headers.

## Example Workflow

A possible workflow might look something like this disregarding loopbacks and descision reversals:

```mermaid
flowchart TD
    %% NODES
    START["Start: User Prompt"]
    
    %% Phase 1: Research
    SK_RES["Skill: task-research<br/>Announce"]
    SK_SUB_RES["Skill: task-subagent<br/>Run Command: acp_dispatch.py"]
    SA_RES["Agent: adr-researcher<br/>Search<br/>Write Artifact"]
    PH1_END["Phase 1 Complete"]
    
    %% Phase 2: ADR
    SK_ADR["Skill: task-adr<br/>Announce<br/>Write ADR<br/>Notify"]
    PH2_END["Phase 2 Complete"]
    
    %% Phase 3: Reference & Planning
    SK_REF["Skill: task-reference<br/>Announce"]
    SK_SUB_REF["Skill: task-subagent<br/>Run Command: acp_dispatch.py"]
    SA_REF["Agent: reference-auditor<br/>Audit Ref<br/>Write Artifact"]
    
    SK_WRITE["Skill: task-write<br/>Announce"]
    SK_SUB_WRITE["Skill: task-subagent<br/>Run Command: acp_dispatch.py"]
    SA_WRITER["Agent: task-writer<br/>Plan Codebase<br/>Write Artifact"]
    PH3_END["Phase 3 Complete"]
    
    %% Phase 4: Execution
    SK_EXEC["Skill: task-execute<br/>Announce"]
    SK_SUB_EXEC["Skill: task-subagent<br/>Run Command: acp_dispatch.py"]
    SA_EXEC["Agent: complex-executor<br/>Edit Code<br/>Validate"]
    
    %% Review Phase (Gatekeeper)
    SK_REV["Skill: task-review<br/>Announce"]
    SK_SUB_REV["Skill: task-subagent<br/>Run Command: acp_dispatch.py"]
    SA_REV["Agent: code-reviewer<br/>Audit Safety/Intent<br/>Report"]
    
    EXEC_RET["Execution Return"]
    PH4_END["Phase 4 Complete"]
    
    %% Phase 5: Revision (if needed)
    SK_FIX["Skill: task-execute (Fixes)<br/>Announce"]
    SK_SUB_FIX["Skill: task-subagent<br/>Run Command: acp_dispatch.py"]
    SA_FIX["Agent: standard-executor<br/>Fix Code<br/>Verify"]
    PH5_END["Phase 5 Complete"]
    
    %% Phase 6: Conclusion
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