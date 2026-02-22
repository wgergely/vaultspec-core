---
tags: ["#research", "#system-prompt-injection"]
related: []
date: 2026-02-22
---

# Research: System Prompt Injection of Skill Skeletons

## Goal
Understand the standard mechanism for injecting skill definitions (skeletons/metadata) into the agent's system prompt and compare it with the current `vaultspec` implementation.

## Current Implementation (`src/vaultspec/cli.py`)
Currently, `vaultspec` generates a system prompt by assembling various Markdown parts. Specifically, `_generate_system_prompt` calls `_collect_skill_listing`, which produces a simple Markdown list:

```markdown
## Available Skills

- **skill-name**: description
...
```

This is appended to the system prompt. This format is human-readable but does not follow the structured XML format recommended by the `agentskills` reference implementation for Anthropic/Claude models.

## Standard Specification (`agentskills` / `skills-ref`)
The `skills-ref` library (`skills_ref.prompt.to_prompt`) generates an XML block specifically designed for Claude-like models.

**Format:**
```xml
<available_skills>
  <skill>
    <name>skill-name</name>
    <description>Skill description</description>
    <location>/path/to/skill/SKILL.md</location>
  </skill>
  ...
</available_skills>
```

**Key Differences:**
1.  **Format:** `vaultspec` uses Markdown list; `skills-ref` uses XML tags.
2.  **Structure:** `skills-ref` wraps the list in `<available_skills>`.
3.  **Fields:** `skills-ref` includes a `<location>` field pointing to the `SKILL.md` file, which is critical for the "progressive disclosure" pattern (the agent knows *where* to read the full instructions). `vaultspec` currently omits the location.
4.  **Parsing:** XML is generally more robustly parsed by Claude models for tool/skill definitions than unstructured Markdown lists.

## Gap Analysis
The current `vaultspec` implementation is non-compliant with the `agentskills` best practices for prompt injection.
- **Missing `<available_skills>` wrapper.**
- **Missing XML structure.**
- **Missing `<location>` field.**

## Recommendations
Refactor `_collect_skill_listing` in `src/vaultspec/cli.py` to generate the compliant XML format.

1.  **Change Output Format:** Switch from Markdown list to XML.
2.  **Include Location:** Resolve the absolute or relative path to `SKILL.md` for each skill.
3.  **Use `skills-ref` logic:** Mimic the logic from `skills_ref.prompt.to_prompt`.

## Sub-Agent Injection
Similarly, `_collect_agent_listing` produces a Markdown list. While `agentskills` focuses on "skills", `vaultspec` treats sub-agents as a distinct resource. Consistency suggests we might want to wrap these in XML as well (e.g., `<available_subagents>`), matching the pattern seen in the `system_framework` prompt context I've observed in this session.

## Next Steps
1.  Create an ADR to formalize the decision to switch to XML prompt injection for skills.
2.  Plan the refactor of `src/vaultspec/cli.py`.
