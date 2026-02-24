---
tags:
  - "#research"
  - "#marketing-audit"
date: "2026-02-18"
---
## Marketing Audit: Documentation Quality

**Date**: 2026-02-18
**Auditor**: MarketingAgent2
**Scope**: Root README, `.vaultspec/README.md`, and all `docs/` files
**Status**: Complete

---

## Executive Summary

vaultspec's documentation is technically accurate and well-structured for a developer who already understands the project's purpose. However, it significantly underserves two critical audiences: first-time evaluators deciding whether to adopt the framework, and new users trying to go from zero to working in under 15 minutes.

### Overall score: 6/10

The docs excel at reference material (CLI reference, configuration, search guide) and are serviceable for concepts. They fail at marketing (the README does not sell the product), onboarding (the getting-started guide assumes too much), and tutorials (there are none beyond the quickstart). The GPU-only requirement is a significant adoption barrier that is mentioned but not contextualized or mitigated. There are no worked examples showing real artifacts, no video or screenshots, and no content targeting team leads or enterprise evaluators.

---

## 1. README First Impression

### Score: 5/10

### What works

- The tagline "A governed development framework for AI agents" is precise and differentiating.
- The five bullet points under "Why vaultspec?" efficiently hit the key positioning pillars.
- The workflow diagram (`Research -> Specify -> Plan -> Execute -> Verify`) is immediately legible.
- The agent reference table is a good quick-reference artifact.

### What fails

**The README does not sell the product.** Comparing against top competitors:

- **Cursor's README** leads with a screenshot and a one-sentence value proposition ("The AI Code Editor"). Zero friction to understanding what it is.
- **Aider's README** opens with a GIF demo showing the tool in action, then a benchmark chart.
- **Cline's README** has a badge grid, a screenshot, and a 3-sentence value pitch.
- **Kiro's README** uses a hero banner and a visual of the spec workflow.

vaultspec's README starts with a tagline and immediately drops into a bullet list of technical properties. There is no emotional hook, no screenshot, no demo GIF, no "here is what this solves for you today." The "Why vaultspec?" bullets are accurate but read like engineering notes, not marketing copy.

**Missing elements:**

- A compelling opening hook (who is this for? what problem does it solve in concrete terms?)
- A screenshot, demo GIF, or asciicast showing the tool in action
- A "Before / After" framing — what does AI development look like without vaultspec vs. with it?
- Social proof (stars, users, organizations using it)
- A clear call-to-action ("Try it now: ...")
- A distinguishing statement relative to alternatives ("Unlike Cursor rules or `.clinerules/`, vaultspec...")

**The GPU-only requirement** (`NVIDIA GPU with CUDA 13.0+ required for RAG/search features`) appears in Prerequisites with no context. For a developer on macOS or with AMD hardware, this is an immediate dealbreaker. There is no mention of whether the framework is usable without the GPU (answer: yes, for most features), nor is there a note that the GPU is only needed for semantic search. This alone likely causes a significant portion of evaluators to bounce.

---

## 2. Getting Started Flow

### Score: 6/10

### What works

- The three CLIs are clearly introduced with a purpose table.
- The five-phase workflow example is concrete and shows actual prompts to paste.
- The "First Commands" section provides copy-paste-ready examples.
- Incremental vs. full index is explained clearly.

### What fails

**The 15-minute test:** A new developer following this guide will likely stall at step 1.

```bash
git clone <repository-url>
```

The placeholder `<repository-url>` is never filled in. If vaultspec is not yet on GitHub or the URL is not public, this should say so. If it is, the URL should be here.

```bash
pip install -e ".[rag,dev]"
```

No virtual environment creation step. A developer on a shared machine or with Python environment hygiene habits (pyenv, conda, venv) will want to know where to set this up. The omission is minor but adds friction.

**The GPU requirement again:** "Build the Search Index requires a GPU" appears mid-guide without an escape hatch. There is no "If you don't have a GPU, skip to Step X" or "The framework is fully usable without the search index." This is a blockers for ~40% of developers (macOS users, AMD GPU users, Linux users with no NVIDIA hardware).

**The workflow example is not truly worked.** The "Full Workflow Example" shows prompts to type to an AI assistant but does not show:

- What the output looks like
- What a created `.vault/research/` file looks like
- How to tell if it worked

A new user following this guide has no way to verify they did it correctly until they have already gone through all five phases.

**Missing onboarding steps:**

- `cli.py doctor` — this command is documented in the CLI reference but not mentioned in getting-started. It is exactly the right first command to run after installation.
- How to verify the framework loaded into Claude Code or Gemini CLI (e.g., "open Claude Code in your project and type 'activate vaultspec-research' — you should see...")
- Troubleshooting section (common errors, especially GPU-related)

---

## 3. Conceptual Documentation

### Score: 8/10

`docs/concepts.md` is the strongest document in the set. The SDD explanation is clear and accessible to a developer unfamiliar with the methodology. The "key insight" framing ("AI agents are fast but forgetful") is the best marketing copy in any of the docs.

### What works

- The governance mechanisms (rules, skills, templates) are explained concisely.
- The `.vault/` knowledge base table is excellent — shows what goes where.
- The agent tier table is clear.
- The protocol stack section demystifies MCP/ACP/A2A with clear direction labels.
- The Mermaid diagrams are effective.

### What could improve

- The tag taxonomy section explains the two-tag system but does not explain why exactly two tags. The rationale (prevents tag explosion, enables precise search filtering) would strengthen understanding.
- The "Config Sync Flow" diagram is technically accurate but will confuse a new user who does not yet understand the `.vaultspec/` vs. tool destination relationship. A simpler version of this diagram should appear in getting-started.
- No worked example of a real research document. Showing an actual snippet of `.vault/research/YYYY-MM-DD-example-research.md` would make the vault concept tangible.

---

## 4. CLI Reference

### Score: 9/10

The CLI reference is thorough and well-formatted. Every command is documented with flags, types, defaults, and examples. The `doctor` command output example is particularly well done.

### Minor gaps

- `subagent.py list` and `subagent.py run --interactive` flags are documented but there is no example of a multi-turn interactive session.
- The `vaultspec-fd`, `vaultspec-rg`, `vaultspec-sg`, `vaultspec-sd` skills visible in `.vaultspec/skills/` do not appear in any documentation. These appear to be utility skills (ripgrep, fd, etc.) that should either be documented or removed from the skills directory if internal-only.
- No mention of the `--root` flag's behavior when ROOT_DIR environment variable is also set (priority resolution).

---

## 5. Configuration Guide

### Score: 9/10

The configuration reference is complete, clearly tabulated, and includes the type system description. The priority order (explicit > env var > default) is clearly stated.

### Minor gaps

- No examples of how to set env vars across platforms (`.env` file, shell export, direnv).
- `VAULTSPEC_ALLOWED_TOOLS` and `VAULTSPEC_DISALLOWED_TOOLS` have no examples of valid tool names.
- The `VAULTSPEC_MCP_ROOT_DIR` is marked "required when MCP server starts" but the condition under which the MCP server starts is not explained inline (user must cross-reference to CLI reference).

---

## 6. Search Guide

### Score: 8/10

The search guide is technically excellent. The three-stage hybrid retrieval pipeline explanation (BM25 + ANN + RRF) is clear and includes the formula. Performance numbers are specific and credible.

### What fails

**The GPU requirement is explained but not mitigated.** The guide states:

> vaultspec does not support CPU-only operation. If no GPU is available, the system raises `GPUNotAvailableError`.

This is the only place in any doc where the consequence of not having a GPU is spelled out. But there is no:

- Alternative for non-GPU users ("use `vault.py audit` for metadata-only search")
- Roadmap mention ("CPU support is planned for v0.2")
- Workaround ("run on a cloud GPU instance with...")

For an open-source framework targeting individual developers, GPU-only is a significant adoption barrier. The search guide documents the constraint accurately but does nothing to reduce its friction.

---

## 7. API Documentation

### Score: 2/10 (largely absent)

There is no API documentation for the Python library in `.vaultspec/lib/src/`. Developers wanting to use the library programmatically — to integrate vaultspec into their own tools, CI pipelines, or workflows — have no reference beyond reading source code.

This is a moderate gap now but will become critical if vaultspec positions as a framework others build on.

**What should exist:**

- Module-level docstrings or a `docs/api/` section documenting the public surface of key modules (`vault`, `rag`, `orchestration`, `protocol`)
- A guide on embedding vaultspec programmatically (e.g., "use `VaultStore` in your CI pipeline to query vault documents")

---

## 8. Tutorials and Worked Examples

### Score: 2/10 (absent)

There are no tutorials beyond the getting-started quickstart. No recipe-style guides exist.

**High-value tutorial ideas (in priority order):**

1. **"From Scratch: Your First Governed Feature"** — Full worked tutorial showing actual artifact content, from research document through code review.
2. **"Adding vaultspec to an Existing Project"** — How to adopt vaultspec mid-project, import existing decisions into the vault, seed the RAG index.
3. **"Running vaultspec with Gemini CLI"** — ACP integration walkthrough, since ACP is a differentiator.
4. **"Multi-Agent Workflow: Research Agent Calls Executor"** — Shows the MCP subagent server in action.
5. **"Customizing Agents: Creating Your Own Executor"** — How to define a new agent with custom rules and tier.

The `.vault/` directory itself contains real example artifacts (ADRs, research documents, plans) that could be referenced from tutorials as worked examples. This is an underused resource.

---

## 9. User Personas

### Score: 3/10

The documentation addresses a single implicit persona: a developer who is already convinced vaultspec is worth using and wants to understand how it works. It does not address:

**Individual developer (the primary target):** Documentation assumes they understand why they need governance (they often don't). There is no "here is the pain you feel without this" framing.

**Team lead:** No guidance on how to introduce vaultspec to a team, how to enforce rules across a team, or how to track compliance.

**Enterprise evaluator:** No security model explanation, no compliance/audit trail documentation, no deployment considerations (self-hosted? cloud?), no enterprise feature roadmap.

**Developer using macOS or AMD GPU:** The GPU requirement is documented but there is no persona-specific path for this user ("use vaultspec without search features," "deploy the search component to a cloud GPU").

---

## 10. Visual Aids

### Score: 6/10

The Mermaid diagrams in `.vaultspec/README.md` and `docs/concepts.md` are effective for explaining workflow flow. The config sync flow and agent dispatch flow diagrams in concepts.md are the best technical aids in the documentation set.

**What is missing:**

- **Screenshots** — No screenshot of the CLI in action. The `doctor` command output in the CLI reference is the closest thing.
- **Animation or demo** — A terminal recording (asciinema/GIF) of a complete research -> specify -> plan workflow would dramatically improve first impressions.
- **Architecture diagram** — A single diagram showing how `.vaultspec/`, `.vault/`, and the tool destinations (`.claude/`, `.gemini/`) relate to each other, suitable for inclusion in the README.
- The large workflow diagram in `.vaultspec/README.md` (the 30-node flowchart) is detailed but dense for a first-time reader. A simplified version with 5 boxes should precede it.

---

## 11. Cross-Referencing and Navigation

### Score: 7/10

### What works

- Every `docs/` file ends with a "Next Steps" or cross-reference section.
- The root README links to all docs files.
- The getting-started guide links to all relevant follow-up docs.

### What fails

- The `.vaultspec/README.md` does not link to `docs/` files — it exists in isolation.
- `docs/concepts.md` references the agent dispatch flow but does not link to the CLI reference section on `subagent.py run`.
- The CLI reference does not link to the search guide for `vault.py search` commands.
- There is no navigation index or table of contents for the `docs/` directory as a whole.
- The skills and agents in `.vaultspec/` are mentioned in documentation but there are no links from the docs into those files (understandable for skills, but agent definitions serve as documentation).

---

## 12. Competitor Documentation Comparison

Comparing vaultspec's documentation against relevant competitors:

### Aider (aider.chat)

- Full website with animated demos, blog, leaderboards, benchmarks

- Getting started in 3 commands
- FAQ section addressing common objections
- **Lesson**: Demo GIF on the README homepage is the single highest-ROI documentation investment

### Cursor (cursor.com/docs)

- Searchable documentation site (not just GitHub README)
- "Quickstart in 5 minutes" framing
- Separate guides for different user types (individual, team, enterprise)
- **Lesson**: Persona-specific onboarding paths dramatically reduce abandonment

### Kiro (kiro.dev)

- Visual workflow diagram on the homepage
- "Try it" CTA above the fold
- Side-by-side before/after comparison
- **Lesson**: Show, don't tell — concrete before/after reduces explanation burden

### Cline (github.com/cline/cline)

- README has a video embed
- "What can Cline do?" section with concrete examples
- **Lesson**: Video demos convert evaluators more effectively than text

### LangGraph (langchain-ai.github.io/langgraph)

- Full documentation site with search
- Conceptual, how-to, reference, and tutorial sections (Diátaxis framework)
- **Lesson**: Separate conceptual from how-to from reference — vaultspec conflates these

---

## Summary of Findings

### Strengths

- CLI reference and configuration guide are excellent — thorough, accurate, example-rich
- Concepts documentation clearly explains SDD and the governance model
- Cross-references between `docs/` files are consistent
- The `.vault/` example corpus is rich and could be leveraged as tutorial material

### Critical Gaps

1. **README does not sell the product** — needs a compelling hook, demo GIF/screenshot, and concrete "before/after" framing

2. **GPU barrier is unmitigated** — the GPU-only requirement needs a clear escape hatch for non-GPU users

3. **No tutorials** — worked examples beyond the quickstart are entirely absent
4. **No persona targeting** — single audience assumption leaves team leads and enterprise evaluators unserved
5. **No API documentation** — programmatic use of the library is completely undocumented
6. **Onboarding blockers** — placeholder URLs, no `venv` step, no verification steps, no `doctor` in getting-started

### Priority Recommendations

**Immediate (highest ROI):**

- Add a terminal recording (asciinema or GIF) to the README showing a 2-minute workflow

- Add a "GPU-not-required" note to README/getting-started: "Search requires NVIDIA GPU; all other features work without it"
- Add `cli.py doctor` as step 1 in getting-started
- Fill in `<repository-url>` placeholder

**Short-term:**

- Write one complete worked tutorial showing actual artifact content
- Add a "Before vaultspec / After vaultspec" section to README
- Create a simple 5-box architecture diagram for README

**Medium-term:**

- Adopt Diátaxis documentation structure (conceptual, how-to, reference, tutorial)
- Add persona-specific onboarding paths (individual, team lead, enterprise)
- Document the Python library API (at minimum: vault, rag, orchestration modules)
- Build a documentation site (mkdocs or similar) for searchability

---

## Appendix: Files Audited

- `Y:\code\task-worktrees\main\README.md`
- `Y:\code\task-worktrees\main\.vaultspec\README.md`
- `Y:\code\task-worktrees\main\docs\getting-started.md`
- `Y:\code\task-worktrees\main\docs\concepts.md`
- `Y:\code\task-worktrees\main\docs\configuration.md`
- `Y:\code\task-worktrees\main\docs\search-guide.md`
- `Y:\code\task-worktrees\main\docs\cli-reference.md`
- `.vaultspec/agents/*.md` (9 agent definitions — scanned)
- `.vaultspec/skills/*.md` (14 skill definitions — scanned)
- `.vault/` (40+ artifacts — selectively reviewed for tutorial potential)
- `.vault/audit/2026-02-17-competitive-landscape-audit.md` (competitor reference)
