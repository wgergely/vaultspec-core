---
tags:
  - "#exec"
  - "#system-prompt-injection"
date: "2026-02-22"
related:
  - "[[2026-02-22-system-prompt-injection-plan.md]]"
---
# Execution Summary: System Prompt Injection

## Overview
Successfully refactored `src/vaultspec/cli.py` to use XML-based system prompt injection for skills and sub-agents, complying with the `agentskills` standard.

## Actions Taken
1.  **Refactoring:**
    - Modified `src/vaultspec/cli.py` to import `skills_ref.prompt.to_prompt`.
    - Updated `_collect_skill_listing` to use `to_prompt` for generating `<available_skills>` XML blocks with absolute file paths (`<location>`).
    - Updated `_collect_agent_listing` to programmatically generate `<available_subagents>` XML blocks.
    - **Refinement:** Updated sub-agent description to clarify they are "specialized expert agents" rather than "tools".
2.  **Verification:**
    - Ran `system sync` to update local system prompts.
    - Verified `.gemini/SYSTEM.md` contains correctly formatted XML blocks for both skills and sub-agents.

## Outcome
The system prompt now follows the structured XML format favored by Claude/Gemini models, enabling better tool parsing and progressive disclosure of skill instructions.
