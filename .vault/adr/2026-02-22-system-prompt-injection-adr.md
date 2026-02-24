---
tags:
  - "#adr"
  - "#system-prompt-injection"
date: "2026-02-22"
related:
  - "[[2026-02-22-system-prompt-injection-research.md]]"
---
# ADR: XML-Based System Prompt Injection

## Context
The current implementation of `vaultspec` injects skills and sub-agents into the system prompt as simple Markdown lists. This format is human-readable but suboptimal for LLMs (particularly Claude) when parsing structured tool definitions. The `agentskills` reference implementation recommends an XML-based format (`<available_skills>`) that includes precise `<location>` paths to enable progressive disclosure.

## Decision
We will update `src/vaultspec/cli.py` to generate compliant XML blocks for both skills and sub-agents in the system prompt.

### Specific Changes
1.  **Skills Injection:** Use the official `skills-ref` library directly.
    *   **Function:** `skills_ref.prompt.to_prompt`
    *   **Implementation:** Import `skills_ref.prompt.to_prompt` in `cli.py` and call it with the list of skill directories. This ensures perfect compliance with the XML output format (`<available_skills>`) as defined by the standard tooling.

2.  **Sub-Agent Injection:** Since `skills-ref` is specific to skills, we will programmatically generate a parallel XML structure for sub-agents to maintain consistency.
    *   **Wrapper:** `<available_subagents>`
    *   **Wrapper:** `<available_subagents>`
    *   **Element:** `<subagent>`
    *   **Fields:**
        *   `<name>`: The agent name.
        *   `<description>`: From frontmatter.
        *   `<tier>`: The capability tier (LOW/MEDIUM/HIGH).

## Consequences
*   **Positive:**
    *   **Compliance:** Aligns with `agentskills` best practices.
    *   **Robustness:** XML is less ambiguous for models to parse than Markdown lists.
    *   **Functionality:** Enables the "progressive disclosure" pattern by providing file paths (`<location>`) that agents can read on demand.
*   **Negative:**
    *   **verbosity:** XML consumes slightly more tokens than a simple list.

## Validation
*   Verify that `cli.py system sync` generates `SYSTEM.md` files containing valid XML blocks.
*   Verify that agents can successfully parse and use the location paths.
