---
tags:
  - "#research"
  - "#framework"
date: "2026-02-17"
related:
  - "[[2026-02-17-bootstrap-prompt-adr]]"
---
# Bootstrap Prompt Engineering Research

**Date**: 2026-02-17
**Author**: prompt-researcher agent
**Purpose**: Authoritative research on designing a system/bootstrap prompt that cold-starts an LLM agent with zero prior knowledge of the vaultspec framework

---

## Key Principles

These are the actionable principles distilled from all sources, ordered by importance:

### 1. Context Engineering > Prompt Engineering

The paradigm has shifted. As Anthropic states: "intelligence is not the bottleneck — context is." The question is no longer "how do I craft the perfect prompt?" but "which configuration of context leads to the desired behavior?" For our bootstrap prompt, this means: curate the minimal set of high-signal tokens that maximize the likelihood of correct agent behavior. (Source: [Anthropic - Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))

### 2. Be Explicit and Direct — Never Assume Inference

Claude 4.x models follow instructions more precisely and literally than predecessors. If you want "above and beyond" behavior, explicitly request it. If you want conservative behavior, say so. Vague prompts produce vague results. (Source: [Anthropic Claude 4 Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices))

### 3. Provide Context/Motivation, Not Just Rules

"Explaining to Claude why such behavior is important can help Claude better understand your goals and deliver more targeted responses." Rules with rationale outperform rules alone. Example: instead of "NEVER use ellipses," say "Your response will be read aloud by TTS, so never use ellipses since TTS cannot pronounce them." (Source: [Anthropic Claude 4 Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices))

### 4. Use Structured Formatting — But Model-Appropriately

- **Claude**: Specifically tuned to pay attention to XML tags. Use `<section_name>` tags for structural boundaries. (Source: [Anthropic Prompt Engineering Docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview))
- **Gemini**: Responds well to XML tags OR Markdown headings, with priority constraints placed at the beginning. (Source: [Google Gemini Prompting Strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies))
- **GPT models**: Later instructions take precedence over earlier ones when they conflict; use delimiters (markdown, XML, section headings). (Source: [OpenAI GPT-4.1 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide))
- **Cross-model**: No single format is universally optimal. Research shows performance can vary up to 40% based on formatting alone. (Source: [Does Prompt Formatting Have Any Impact on LLM Performance?](https://arxiv.org/html/2411.10541v1))

### 5. Structure as Layered Hierarchy

Instruction hierarchy explicitly defines behavior when instructions at different priority levels conflict. The accepted model:

1. **System instructions** (highest priority — developer/framework)
2. **User instructions** (task-level directives)
3. **Data/context** (retrieved information, tool outputs)

OpenAI research shows models trained with hierarchical instruction awareness demonstrate up to 63% better resistance to instruction conflicts. (Source: [OpenAI - The Instruction Hierarchy](https://openai.com/index/the-instruction-hierarchy/), [ICLR 2025 Paper](https://proceedings.iclr.cc/paper_files/paper/2025/file/ea13534ee239bb3977795b8cc855bacc-Paper-Conference.pdf))

### 6. Start Minimal, Then Add Based on Observed Failures

Anthropic's own guidance: "Start minimal, then add clarity based on observed failures. Note: minimal does not mean short; provide sufficient detail for proper agent behavior." This is an iterative process — over-specifying upfront leads to contradictions and bloat. (Source: [Anthropic - Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))

### 7. Curate the Minimal Viable Toolset

"If a human engineer can't definitively say which tool should be used in a given situation, an AI agent can't be expected to do better." Each tool must justify its existence. Avoid overlap. Use clear, unambiguous names and detailed descriptions. (Source: [Anthropic - Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))

### 8. Few-Shot Examples Are Worth a Thousand Words of Rules

"Examples are the pictures worth a thousand words" for LLM learning. Provide diverse, canonical examples rather than exhaustive edge case lists. Claude 4.x pays close attention to details and examples — ensure examples align with desired behavior. (Source: [Anthropic Claude 4 Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices), [Anthropic - Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use))

### 9. Tell the Model What TO DO, Not What NOT to Do

Positive instructions outperform negative constraints. Instead of "Do not use markdown," say "Your response should be composed of smoothly flowing prose paragraphs." (Source: [Anthropic Claude 4 Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices))

### 10. Plan Before Acting — But Don't Over-Plan

All three major providers agree: agents should plan before executing tool calls. OpenAI recommends: "plan extensively before each function call, and reflect extensively on the outcomes." But Claude 4.6 can over-plan if prompted to — Anthropic advises removing explicit "use the think tool to plan your approach" instructions. (Source: [OpenAI GPT-4.1 Guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide), [Anthropic Claude 4 Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices))

### 11. Use Progressive Disclosure for Complex Frameworks

Don't dump everything into the prompt at once. Use lightweight identifiers (file paths, references) and load details on demand. Claude Code demonstrates this: CLAUDE.md loads upfront while grep/glob enable just-in-time access to codebase details. (Source: [Anthropic - Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))

### 12. Design for State Persistence Across Context Windows

For long-horizon tasks: use structured formats (JSON) for state data, freeform text for progress notes, and git for checkpointing. Each new context window should have a startup ritual: check state, review progress, then continue. (Source: [Anthropic - Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents))

---

## Sources

### Primary (Official Model Provider Documentation)

1. **[Anthropic - Claude 4 Prompting Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)** — Official best practices for Claude 4.x models covering instruction following, tool use, thinking, formatting, and migration guidance.

2. **[Anthropic - Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)** — Comprehensive guide on context window optimization: system prompts, tool design, data retrieval, long-horizon task management, compaction, sub-agent architectures.

3. **[Anthropic - Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)** — Tool Search Tool, Programmatic Tool Calling, Tool Use Examples. Advanced patterns for large tool libraries and complex parameter handling.

4. **[Anthropic - Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)** — Dual-prompt architecture (initializer vs. coding agent), state management, multi-window workflows, feature-driven testing.

5. **[Google - Gemini Prompting Strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies)** — Official Gemini guide: system instructions, few-shot learning, prompt chaining, temperature settings, behavioral dimension configuration.

6. **[OpenAI - GPT-4.1 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide)** — Agentic tool use patterns, system prompt structure (role/objective/instructions/reasoning/output/examples), persistence reminders, tool definition best practices.

7. **[OpenAI - GPT-5 Prompting Guide](https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide)** — Plan tasks thoroughly, provide tool preambles, use TODO tools for workflow tracking, define safe vs. unsafe actions.

### Secondary (Research Papers)

8. **[OpenAI - The Instruction Hierarchy](https://openai.com/index/the-instruction-hierarchy/)** — Training LLMs to prioritize privileged instructions. Up to 63% improvement in conflict resolution.

9. **[Does Prompt Formatting Have Any Impact on LLM Performance?](https://arxiv.org/html/2411.10541v1)** — Research showing format-dependent performance variation up to 40%, model-specific format preferences (GPT-3.5 prefers JSON, GPT-4 prefers Markdown).

10. **[ICLR 2025 - Improving LLM Safety with Instruction Hierarchy](https://proceedings.iclr.cc/paper_files/paper/2025/file/ea13534ee239bb3977795b8cc855bacc-Paper-Conference.pdf)** — Instructional Segment Embedding (ISE) for distinguishing system/user/data instruction layers.

### Tertiary (Framework & Community Sources)

11. **[Context Engineering Secrets from Claude](https://01.me/en/2025/12/context-engineering-from-claude/)** — Deep dive on Anthropic's four pillars of context engineering, tool design principles, skills system patterns.

12. **[Claude Code System Prompts (GitHub)](https://github.com/Piebald-AI/claude-code-system-prompts)** — Complete extraction of Claude Code's system prompt, 18 built-in tool descriptions, sub-agent prompts, CLAUDE.md patterns.

13. **[Claude Code Memory Documentation](https://code.claude.com/docs/en/memory)** — CLAUDE.md layering hierarchy, auto-memory system, context window management (190k tokens).

14. **[DataCamp - CrewAI vs LangGraph vs AutoGen](https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen)** — Comparative analysis of multi-agent frameworks: role-based (CrewAI), graph-based (LangGraph), conversational (AutoGen) dispatch patterns.

15. **[Intent Recognition and Auto-Routing in Multi-Agent Systems](https://gist.github.com/mkbctrl/a35764e99fe0c8e8c00b2358f55cd7fa)** — DAG-based intent classification, semantic routing, hybrid LLM+embedding approaches.

16. **[Anthropic Prompt Engineering Blog](https://claude.com/blog/best-practices-for-prompt-engineering)** — High-level best practices overview.

---

## Recommendations

### R1: Prompt Architecture — Use a 4-Layer Structure

Based on the converging guidance from all three providers, our bootstrap prompt should use this layered architecture:

```
Layer 1: IDENTITY & PERSONA
  - What is vaultspec? (1-2 sentences)
  - Agent role and capabilities
  - Core behavioral constraints

Layer 2: FRAMEWORK KNOWLEDGE
  - Pipeline phases (Research → Specify → Plan → Execute → Verify)
  - Available skills/agents and their purposes
  - Documentation artifact templates
  - Key file paths and conventions

Layer 3: OPERATIONAL RULES
  - How to interpret user requests (intent → action mapping)
  - When to use which skill/agent
  - Output format requirements
  - Quality gates and verification steps

Layer 4: DYNAMIC CONTEXT (loaded at runtime)
  - Current project state
  - Recently accessed files
  - Task-specific instructions
```

**Rationale**: This mirrors Claude Code's own architecture (system prompt → CLAUDE.md → rules → user message) and aligns with the instruction hierarchy research showing layered approaches improve both compliance and conflict resolution.

### R2: Formatting — Use XML Tags for Structure, Markdown for Content

**For structural boundaries** between sections: use XML tags (`<identity>`, `<framework>`, `<rules>`, `<context>`). This is optimal for Claude (specifically tuned for XML attention) and compatible with Gemini and GPT models which also recognize XML delimiters.

**For content within sections**: use Markdown (headers, bullets, code blocks). This is the most token-efficient format and is well-supported across all models.

**Avoid**: JSON for instruction formatting (too verbose, worse for Claude), plain text without delimiters (boundary confusion), nested XML (adds tokens without benefit).

### R3: Intent-to-Action Mapping — Use Decision Table + Few-Shot Examples

Rather than embedding complex if-else logic or abstract rules, use a decision table format that maps user intent patterns to concrete actions:

```
| User Says (pattern)           | Phase    | Action                        |
|-------------------------------|----------|-------------------------------|
| "research X" / "what is X"   | Research | Invoke vaultspec-researcher   |
| "write a spec for X"         | Specify  | Invoke ADR template workflow  |
| "plan how to build X"        | Plan     | Invoke planning workflow      |
| "implement X" / "build X"    | Execute  | Invoke execution workflow     |
| "verify X" / "test X"        | Verify   | Invoke verification workflow  |
```

Follow this with 2-3 concrete few-shot examples showing the full intent → action → output chain. Research shows few-shot examples improve tool parameter accuracy from 72% to 90%. (Source: Anthropic Advanced Tool Use)

### R4: Keep the Prompt Under 2,000 Tokens of Core Instructions

Based on context engineering research:

- Context rot increases with window size
- Claude Code's CLAUDE.md files are designed to stay under ~200 lines (~1,500-2,000 tokens)
- The bootstrap prompt should contain only what the agent MUST know to begin working
- Everything else should be progressive disclosure via file references or tool access

**Target**: Core bootstrap = 1,500-2,000 tokens. Extended reference material = loaded on demand.

### R5: Explain WHY, Not Just WHAT

Every significant rule should include its rationale. Examples from our research:

- BAD: "Always create ADRs before implementation."
- GOOD: "Always create ADRs before implementation. ADRs capture architectural decisions so that future agents (or humans) can understand the reasoning behind choices without re-deriving them."

This aligns with Anthropic's finding that Claude generalizes better from motivations than from bare rules.

### R6: Design for Multi-Model Compatibility

Based on cross-model research:

1. **Use XML tags for section boundaries** — works across Claude (best), Gemini (good), GPT (good)
2. **Use Markdown for content** — universally understood, token-efficient
3. **Avoid model-specific features** in the bootstrap prompt (no Claude-specific prefill patterns, no Gemini-specific thinking_level)
4. **Keep instructions clear and literal** — GPT-4.1+ follows literally; Claude 4.x follows precisely; Gemini 3 reduces need for micro-instructions
5. **Test the prompt on each target model** before finalizing — performance can vary up to 40% based on formatting alone

### R7: Agent Dispatch — Use the CrewAI Pattern (Role-Based Specialization)

Among the major frameworks, CrewAI's role-based dispatch is closest to vaultspec's agent architecture. Each agent should be defined with:

- **Role**: Clear, specific title (e.g., "vaultspec-researcher")
- **Goal**: What success looks like
- **Capabilities**: What tools/skills it can access
- **Constraints**: What it should NOT do

This is more intuitive and maintainable than LangGraph's graph-based routing or AutoGen's conversation-based dispatch for our use case.

### R8: Remove Anti-Laziness and Aggressive Tool Language

Claude 4.6 and Gemini 3 are both MORE proactive than their predecessors. Anthropic explicitly warns:

- Remove "be thorough," "think carefully," "do not be lazy" — these amplify already-proactive behavior
- Replace "You MUST use this tool" with "Use this tool when..."
- Remove "use the think tool to plan your approach" — Claude 4.6 thinks effectively without being told to

### R9: Include a Startup Ritual

Based on Anthropic's long-running agent harness research, include a standard startup sequence:

1. Identify the current project root and working directory
2. Check for existing state (progress files, git log, previous artifacts)
3. Read the project's CLAUDE.md / rules files
4. Determine current pipeline phase
5. Then — and only then — engage with the user's request

This prevents the "cold start" problem where agents make assumptions about project state.

### R10: Define Clear Stop Conditions and Handoff Points

OpenAI's GPT-5 guide emphasizes: "clearly state the stop conditions of agentic tasks, outline safe versus unsafe actions, and define when it's acceptable for the model to hand back to the user."

For vaultspec, this means explicitly defining:

- When a phase is "done" and what artifacts mark completion
- What actions require user confirmation (e.g., executing code, modifying production files)
- When the agent should ask for clarification vs. proceed with best guess

---

## Anti-Patterns to Avoid

### AP1: Information Overload / Context Dumping

**Problem**: Loading the entire framework specification into the system prompt.
**Why it fails**: Context rot — performance degrades as context grows. The transformer attention mechanism struggles with n-squared pairwise token relationships in long sequences.
**Fix**: Progressive disclosure. Load core identity + pipeline + dispatch table. Load details via file references.

### AP2: Contradictory Instructions

**Problem**: Rules in one section that conflict with rules in another.
**Why it fails**: Models resolve conflicts unpredictably. GPT resolves later-over-earlier; Claude tries to satisfy all; Gemini may hallucinate a compromise.

**Fix**: Single source of truth for each behavior. Use the layered hierarchy: more specific overrides more general.

### AP3: Negative Instructions Without Positive Alternatives

**Problem**: Lists of "DO NOT" without specifying what TO do.

**Why it fails**: Models are better at following instructions toward a target than away from one.
**Fix**: Frame every constraint as a positive action. "Never use bullet lists" → "Write in flowing prose paragraphs."

### AP4: Over-Specifying Edge Cases

**Problem**: Exhaustive if-else trees covering every possible user input.
**Why it fails**: Wastes tokens. Creates brittle behavior. Modern models generalize well from principles + examples.
**Fix**: State principles clearly. Provide 3-5 diverse examples. Trust the model to generalize.

### AP5: Burying Critical Information

**Problem**: Placing the most important instructions deep in a long prompt.
**Why it fails**: Positional encoding weakening — some LLMs pay less attention to tokens far from the generation point. Known as the "lost in the middle" effect.
**Fix**: Place the most critical behavioral constraints at the BEGINNING of the system prompt. Repeat critical rules at the end if the prompt is long.

### AP6: Using ALL-CAPS, "CRITICAL", and "Bribes"

**Problem**: Using aggressive emphasis hoping the model will pay more attention.
**Why it fails**: With Claude 4.6, this causes overtriggering and amplified behavior. OpenAI's guide explicitly says "avoid unnecessary ALL-CAPS or bribes — clarity suffices."
**Fix**: Use clear, direct language. If a rule is truly critical, explain WHY rather than SHOUTING.

### AP7: Assuming Model Memory Across Sessions

**Problem**: Assuming the agent remembers previous conversations or implicit conventions.
**Why it fails**: Each context window starts fresh. Without explicit state, agents cannot maintain continuity.

**Fix**: Use structured state files, git history, and explicit progress tracking. Include a startup ritual that loads state.

### AP8: Vague Tool Descriptions

**Problem**: Tool names like "helper" or "utils" with minimal descriptions.
**Why it fails**: "If humans can't definitively say which tool should be used, an AI agent can't be expected to do better."
**Fix**: Each tool gets a unique, descriptive name + detailed description of what it does, when to use it, and what it returns.

### AP9: Mixing Data with Instructions

**Problem**: No clear delimiters between what is an instruction vs. what is data/context.
**Why it fails**: LLMs process everything as one stream. Without delimiters, data can be interpreted as instructions (prompt injection vector) or instructions can be ignored as data.
**Fix**: Use XML tags or clear section headers to separate instruction layers from data layers.

### AP10: One-Size-Fits-All Prompts Without Testing

**Problem**: Writing a prompt for Claude and assuming it works for Gemini/GPT.
**Why it fails**: Research shows up to 40% performance variation across models for the same prompt format.
**Fix**: Test the bootstrap prompt on each target model. Maintain a model-specific adaptation layer if needed.

---

## Framework-Specific Patterns Worth Emulating

### From Claude Code

- **CLAUDE.md hierarchy**: Project root → child directories → user settings. More specific overrides more general.
- **Auto-memory**: Persistent learning stored in topic files, loaded into context at session start.
- **Skills system**: Reusable knowledge in `SKILL.md` files (< 500 lines) with progressive disclosure via separate reference files.
- **Tool layering**: 18 built-in tools with clear, distinct purposes and descriptions.

### From CrewAI

- **Role-Goal-Backstory-Tools**: Each agent defined by its specialization, not by a generic "you are a helpful assistant."
- **Hierarchical delegation**: A manager agent routes tasks to specialized workers.
- **Task dependencies**: Explicit task ordering with input/output contracts.

### From LangGraph

- **State machine routing**: Conditional edges based on current state, enabling dynamic workflow adaptation.
- **Checkpoint/resume**: State serialization for long-running workflows.

### From OpenAI Agent Patterns

- **Persistence reminder**: "Keep going until the user's query is completely resolved."
- **Tool preamble**: Explain reasoning before each tool call.
- **TODO tracking**: Agents maintain a structured task list for complex workflows.

---

## Summary of Cross-Provider Consensus

All three providers (Anthropic, Google, OpenAI) agree on these core principles:

1. **Be explicit** — modern models follow instructions literally; vagueness produces vague output
2. **Provide examples** — few-shot demonstrations outperform verbose rule descriptions
3. **Structure with delimiters** — XML tags and/or Markdown headers separate instruction layers
4. **Plan before acting** — agents should reason about approach before executing tools
5. **Manage context carefully** — context rot is real; minimize, compress, and use progressive disclosure
6. **Define clear boundaries** — what the agent should do, should not do, and when to ask for help
7. **Test and iterate** — no prompt is perfect on first draft; measure and refine

Where they disagree:

- **Conflict resolution**: GPT favors later instructions; Claude tries to satisfy all; Gemini varies
- **Formatting preference**: Claude favors XML; GPT favors Markdown/JSON; Gemini is flexible
- **Thinking guidance**: Claude 4.6 should NOT be told to "think carefully" (overtriggers); Gemini 3 benefits from thinking_level parameter; GPT-5 benefits from explicit "plan your approach" instructions
