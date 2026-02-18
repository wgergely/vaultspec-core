---
tags: ["#audit", "#roadmap"]
date: 2026-02-17
related:
  - "[[2026-02-17-audit-summary-audit]]"
---

# Documentation UX Audit

**Date**: 2026-02-17
**Auditor**: MarketingLead (Documentation UX Expert)
**Scope**: All project documentation assessed against modern documentation standards (Diataxis, progressive disclosure, information architecture)
**Benchmarks**: Stripe Docs, Vercel Docs, Tailwind CSS Docs

---

## Executive Summary

vaultspec's documentation tells two stories: an **excellent internal reference system** for agent definitions, skills, and templates, and a **nearly absent external-facing onboarding experience**. The framework's core user manual (`.vaultspec/README.md`) is genuinely well-written, but it is buried inside a hidden directory, unreachable from the sparse top-level README. There is no installation guide, no quickstart tutorial, no conceptual explainer, and no progressive onboarding path.

By the standards of Stripe, Vercel, or Tailwind -- where a new developer can go from zero to productive in under 10 minutes -- vaultspec has no defined path at all. The documentation that exists is high-quality reference material. What is entirely missing is the scaffolding that gets people to that reference material.

Documentation UX Score: 4.2/10

---

## 1. Diataxis Framework Assessment

The [Diataxis framework](https://diataxis.fr/) defines four documentation quadrants. Every mature documentation system should cover all four.

### 1.1 Tutorials (Learning-oriented) -- ABSENT

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Step-by-step guided walkthrough | Missing | No tutorial exists anywhere |
| "Hello World" equivalent | Missing | No quickstart, no `vaultspec init` |
| Builds toward a concrete outcome | Missing | No example project or worked example |
| Assumes no prior knowledge | N/A | Cannot assess what doesn't exist |

**Assessment**: There is zero tutorial content. A new user cloning the repository encounters a 7-line README that does not explain how to install, configure, or run anything. The `.vaultspec/README.md` user manual jumps directly into skill activation syntax ("Activate `vaultspec-research` to investigate [topic]") without establishing what skills are, how the CLI works, or what the expected environment looks like.

**Benchmark comparison**: Stripe's docs open with "Start with a 5-minute integration." Vercel's open with "Deploy your first project." Tailwind opens with "Get started with Tailwind CSS." vaultspec opens with a warning about not running `cli.py config sync`.

**Cross-reference**: 01-ux-simulation.md, Section 1 (Installation instructions: 0/10, Getting started: 0/10)

### 1.2 How-To Guides (Task-oriented) -- PARTIAL

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Problem-oriented structure | Partial | Skills describe "when to use" but not step-by-step procedures |
| Assumes working knowledge | Yes | All skill docs assume familiarity with the workflow |
| Provides concrete steps | Partial | `vaultspec-execute` has clear delegation steps; `vaultspec-research` less so |
| Addresses real-world scenarios | Weak | No "How to add a new feature", "How to onboard a new team member" |

**Assessment**: The 12 skill definition files function as implicit how-to guides -- each describes when to use the skill, what to announce, what template to use, and how to dispatch sub-agents. This is genuinely useful for someone who already understands the system. However, these are **agent instructions**, not user-facing how-to guides. They tell the AI what to do, not the human developer.

Missing how-to guides include:

- How to add a custom rule / agent / skill
- How to run your first research-to-execution cycle
- How to use the RAG search system
- How to configure multi-tool sync (Claude + Gemini)
- How to dispatch a sub-agent manually

**Cross-reference**: 01-ux-simulation.md, Section 3 (CLI add commands: 6/10 -- no `--template` flag, no interactive mode)

### 1.3 Reference (Information-oriented) -- STRONG

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Complete API/CLI documentation | Good | `02-tech-audit.md` documents all 46 features; CLI help text works |
| Structured and consistent | Strong | Agent table in `.vaultspec/README.md`; skill descriptions follow consistent format |
| Accurate and up-to-date | Good | All features have backing implementations (02-tech-audit.md, Section 2) |
| Searchable/navigable | Weak | No index, no cross-linking between docs, no search page |

**Assessment**: This is vaultspec's strongest documentation quadrant. The agent reference table in `.vaultspec/README.md` is excellent -- clear columns for agent name, tier, role, and usage guidance. The file responsibilities table maps source files to generated outputs cleanly. All 9 agent definitions follow a consistent YAML frontmatter + markdown body pattern. All 12 skill definitions follow a consistent structure.

However, the reference material is scattered across many files with no central index or navigation. A developer must know where to look. There is no generated API documentation, no `--help` that links to extended docs, and no searchable reference site.

**Cross-reference**: 02-tech-audit.md, Section 3 (CLI Command Reference -- comprehensive but not user-facing)

### 1.4 Explanation (Understanding-oriented) -- WEAK

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Explains "why" and design rationale | Partial | FRAMEWORK.md is 4 lines; README.md diagrams help but lack prose |
| Conceptual overviews | Weak | No explanation of what "governed development" means in practice |
| Architecture diagrams | Present | 2 Mermaid diagrams in `.vaultspec/README.md` |
| Decision context | Missing | No "why SDD?" or "why three protocols?" explanation |

**Assessment**: The two Mermaid diagrams in `.vaultspec/README.md` are the only conceptual content. They visualize the workflow but don't explain the reasoning behind it. There is no document explaining:

- Why spec-driven development matters (the "pitch")
- What problems vaultspec solves that alternatives don't
- How the three-protocol stack (MCP + ACP + A2A) works together
- Why the `.vault/` structure is designed the way it is
- What "governed" means in "governed development framework"

`FRAMEWORK.md` could be this document, but it is only 4 lines that redirect to `.vaultspec/README.md`. `PROJECT.md` is empty.

**Cross-reference**: 04-competitive-landscape.md, Market Positioning section -- vaultspec's unique position is well-articulated in the audit but not in any user-facing document

### 1.5 Diataxis Summary

| Quadrant | Coverage | Grade |
|----------|----------|-------|
| Tutorials | 0% | F |
| How-To Guides | 25% | D |
| Reference | 70% | B |
| Explanation | 15% | D- |

---

## 2. Progressive Disclosure Assessment

Progressive disclosure means layering information so beginners get the essentials first and can drill into details as needed.

### 2.1 Current State

The documentation has essentially **two layers with nothing in between**:

1. **Layer 0**: Top-level `README.md` -- 7 lines, too sparse to be useful
2. **Layer 2**: `.vaultspec/README.md` + 12 skill files + 9 agent files + 8 templates -- detailed reference for power users

**Missing Layer 1**: A "getting started" experience that bridges the gap. This should include:

| **Stripe** | 4 (Overview -> Quickstart -> Guides -> API Reference) | ~5 minutes to first API call |
| **Vercel** | 3 (Getting Started -> Framework Guides -> API/CLI Reference) | ~3 minutes to first deploy |
| **Tailwind** | 3 (Installation -> Core Concepts -> Utilities Reference) | ~2 minutes to first styled page |
| **vaultspec** | 2 (Sparse README -> Full Reference) | Undefined (no path exists) |

**Cross-reference**: 01-ux-simulation.md, Section 7 (Pain Point #1: "No installation or setup documentation")

---

## 3. Information Architecture Assessment

### 3.1 Navigation Structure

```
README.md                    <- 7 lines, barely a signpost
.vaultspec/
  README.md                  <- The real user manual (buried in hidden directory)
  FRAMEWORK.md               <- 4 lines, redirect to README.md
  PROJECT.md                 <- Empty
  agents/                    <- 9 agent definitions (well-structured)
  skills/                    <- 12 skill definitions (well-structured)
  templates/                 <- 8 document templates (well-structured)
    readme.md                <- The "master rulebook" for documentation standards
  system/                    <- 4 system prompt parts (not user-facing)
  workflows/                 <- DOES NOT EXIST (referenced in README)
  lib/                       <- Source code (not documentation)
```

### 3.2 Problems

1. **The primary entry point (README.md) is a dead end.** It describes four bullet points about the project and a CAUTION warning. A user's next action is unclear. The README says "Compatibility: Designed for use with AI coding assistants like Gemini CLI, Google Antigravity, and Claude Code" but doesn't explain how to use it with any of them.

2. **The real documentation is hidden.** `.vaultspec/` is a dotfile directory. On most operating systems, it is invisible by default. A developer who runs `ls` in the project root will not see it unless they use `ls -a`. The critical user manual at `.vaultspec/README.md` is two levels of indirection away from the project root.

3. **No cross-linking between documents.** The skill files reference templates ("You MUST read and use the template at `.vaultspec/templates/research.md`") but there is no reverse link from templates back to skills, no index page listing all skills with their templates, and no navigation sidebar or table of contents.

4. **Naming confusion.** `.vaultspec/templates/readme.md` is the "Master Rulebook" for documentation standards, but its filename (`readme.md`) suggests it's a README for the templates directory. This should be named `standards.md` or `documentation-standards.md` for clarity.

5. **Phantom directory.** `workflows/` is mentioned in the project layout (in MEMORY.md and conceptually in the README) but does not exist. This creates confusion about whether workflows are different from skills.

**Cross-reference**: 01-ux-simulation.md, Section 4 (Framework Structure Assessment -- `workflows/` missing, `FRAMEWORK.md` is 4 lines, `PROJECT.md` is empty)

### 3.3 Ideal Information Architecture

A well-organized documentation structure for vaultspec would look like:

```
README.md                         <- Overview, installation, quickstart, links
docs/
  getting-started.md              <- Prerequisites, install, first workflow
  concepts.md                     <- What is SDD? What is "governed"? The 5 phases
  cli-reference.md                <- All CLI commands with examples
  agent-reference.md              <- All agents with capabilities and use cases
  skill-reference.md              <- All skills with workflow context
  template-reference.md           <- All templates with usage examples
  architecture.md                 <- Protocol stack, design decisions, diagrams
  faq.md                          <- Common questions and troubleshooting
.vaultspec/                       <- Framework source (internal)
```

---

## 4. Onboarding Friction Analysis

### 4.1 Steps from Clone to First Productive Use

Attempting to reconstruct the onboarding path a new user would follow:

| Step | Action | Documented? | Friction |
|------|--------|-------------|----------|
| 1 | Clone repository | No | Low (standard git) |
| 2 | Read README.md | Partial | High -- 7 lines, no next step |
| 3 | Discover .vaultspec/ exists | No | High -- hidden directory |
| 4 | Read .vaultspec/README.md | No | Medium -- good content once found |
| 5 | Install Python 3.13 | No | High -- not mentioned anywhere |
| 6 | Install dependencies (`pip install -e ".[dev]"`) | No | High -- not documented |
| 7 | Install CUDA + PyTorch (for RAG) | No | Very High -- GPU requirement undocumented |
| 8 | Run first CLI command | Implicit | Medium -- `cli.py` path not obvious |
| 9 | Initialize .vault/ in target project | No | High -- no `init` command exists |
| 10 | Run first workflow cycle | No | High -- must read skill docs + README |

**Total undocumented steps: 8 out of 10.**

**Estimated time from clone to productive use**: Unknown (no defined path). An experienced developer who discovers `.vaultspec/README.md` could likely get the CLI working in 15-30 minutes. Setting up RAG could take an additional 30-60 minutes depending on CUDA familiarity. A less experienced developer could spend hours.

**Benchmark comparison**: Stripe: ~5 minutes. Vercel: ~3 minutes. Tailwind: ~2 minutes.

**Cross-reference**: 01-ux-simulation.md, Section 9, Recommendation #1 ("Write a comprehensive top-level README.md") and Recommendation #4 ("Add a `vaultspec init` command")

### 4.2 Onboarding Blockers

Three issues would completely stop a new user:

1. **No installation instructions** -- The pyproject.toml defines optional dependency groups (`rag`, `dev`, `dev-rag`) but these are not documented anywhere user-facing. (Cross-ref: 02-tech-audit.md, Section 6.2 -- Dependency Stack)

2. **`subagent.py` crashes on import** -- A user trying to dispatch their first sub-agent would hit `ModuleNotFoundError: No module named 'logging_config'`. (Cross-ref: 01-ux-simulation.md, Section 3.3; 03-test-verification.md, Failure 1-2)

3. **No `init` command** -- There is no way to bootstrap `.vaultspec/` and `.vault/` in a new project. Users must manually create the directory structure or copy it from somewhere undocumented. (Cross-ref: 01-ux-simulation.md, Section 7, Pain Point #6)

---

## 5. Discoverability Assessment

### 5.1 Feature Discoverability

| Feature | How User Discovers It | Discoverability Rating |
|---------|----------------------|----------------------|
| 5-phase workflow | `.vaultspec/README.md` (buried) | Low |
| CLI commands | `cli.py --help` (works) | Medium |
| Docs audit | `docs.py --help` (works) | Medium |
| RAG search | `docs.py search --help` (works, but GPU req undocumented) | Low |
| Agent definitions | `cli.py agents list` (excellent output) | High |
| Skills | `cli.py skills list` (excellent output) | High |
| Templates | Must browse `.vaultspec/templates/` manually | Low |
| Mermaid diagrams | Must find `.vaultspec/README.md` | Low |
| Multi-tool sync | `cli.py sync-all --dry-run` (excellent) | Medium |
| Subagent dispatch | `subagent.py --help` (currently broken) | Blocked |

### 5.2 Organic Discovery Paths

A well-designed system allows users to discover features while using it. vaultspec has some good patterns here:

**Good**: `cli.py agents list` produces a clean table showing all agents with their tiers and model mappings. This naturally leads to curiosity about what agents can do. (Cross-ref: 01-ux-simulation.md, Section 3.1 -- "Output is clean, aligned, and informative")

**Good**: `docs.py audit --summary` provides an immediate overview of vault health, naturally leading to `--verify` and `--graph` for deeper analysis. (Cross-ref: 01-ux-simulation.md, Section 3.2 -- "The crown jewel of the CLI")

**Bad**: There is no `--version` flag on any CLI tool, no `cli.py status` command showing current configuration state, and no `cli.py doctor` command that checks prerequisites.

**Bad**: Templates are only discoverable by browsing the `.vaultspec/templates/` directory. They are referenced in skill docs but not listed by any CLI command.

**Cross-reference**: 02-tech-audit.md, Section 5 (Capability Map -- comprehensive list of what exists but is not discoverable to users)

---

## 6. Documentation Completeness

### 6.1 Cross-Reference: Documented vs. Implemented

Using 02-tech-audit.md's feature matrix as the ground truth:

| Feature | Implemented | Documented (User-Facing) | Gap |
|---------|-------------|-------------------------|-----|
| Core Configuration (30+ vars) | Yes | No | Environment variables not listed |
| YAML Frontmatter Parsing | Yes | Yes (templates/readme.md) | Adequate |
| Vault Document Scanning | Yes | Implicit (via `docs.py audit`) | Implicit only |
| Wiki-link Extraction | Yes | Yes (templates/readme.md) | Adequate |
| Template Hydration | Yes | No | Users don't know about auto-hydration |
| GPU Embeddings | Yes | No | GPU/CUDA requirement undocumented |
| Full/Incremental Indexing | Yes | No | `docs.py index --help` only |
| Hybrid Search + Reranking | Yes | No | Search algorithm undocumented |
| Query Filter Syntax | Yes | No | `type:`, `feature:`, `date:`, `tag:` filters undocumented |
| LanceDB Vector Store | Yes | No | Implementation detail, acceptable |
| Document Graph | Yes | Implicit (`docs.py audit --graph`) | Implicit only |
| ACP Client/Bridge | Yes | No | Protocol integration undocumented |
| A2A Server | Yes | No | Protocol integration undocumented |
| MCP Server (5 tools) | Yes | Partial (`vaultspec-subagent` skill) | Tool surface undocumented |
| CLI: rules/agents/skills | Yes | Partial (README mentions sync) | Add/remove/show undocumented |
| CLI: sync-all | Yes | Yes (`cli.py sync-all --dry-run`) | Adequate |
| CLI: test runner | Yes (broken path) | No | Not documented at all |
| Subagent Orchestration | Yes | Partial (`vaultspec-subagent` skill) | Usage examples only |

Documentation coverage of implemented features: ~35%

Approximately two-thirds of vaultspec's capabilities are invisible to users because they are not documented in any user-facing location.

**Cross-reference**: 02-tech-audit.md, Section 2 (Feature Matrix: 46 features, all implemented); 03-test-verification.md, Section on Coverage Gaps

### 6.2 Configuration Documentation

The `core/config.py` module defines 30+ configurable variables with `VAULTSPEC_*` environment variable counterparts. None of these are documented:

- No config reference page
- No `.env.example` file
- No `cli.py config list-vars` command
- No explanation of which variables affect which features

This is a significant gap for a framework that emphasizes governance and configurability.

---

## 7. Visual Design Assessment

### 7.1 Diagrams

| Diagram | Location | Quality | Effectiveness |
|---------|----------|---------|--------------|
| Overview flowchart | `.vaultspec/README.md` (lines 98-123) | Good | Clear artifact dependency graph |
| Detailed workflow | `.vaultspec/README.md` (lines 134-228) | Overly complex | 40+ nodes, hard to parse visually |

**Missing diagrams**:

- Directory structure diagram showing `.vaultspec/` and `.vault/` layout
- Data flow diagram showing how documents move through the pipeline
- Agent interaction diagram showing which agents call which other agents
- Sync flow diagram showing source -> transform -> destination paths

The tool destination sync architecture from 02-tech-audit.md (Section 7.5) is documented in the audit but not in any user-facing document. This ASCII art is clear and would be valuable in the user manual.

### 7.2 Code Examples

The skill files contain bash usage examples (e.g., `vaultspec-subagent.md` has `python .vaultspec/lib/scripts/subagent.py run --agent vaultspec-adr-researcher --goal "..."`). These are helpful but:

- No expected output shown alongside commands
- No "before/after" examples showing what files are created
- No example `.vault/` directory tree showing the result of running a full workflow

### 7.3 Tables

Tables are used effectively in `.vaultspec/README.md` (agent reference, file responsibilities) and `templates/readme.md` (tag taxonomy, placeholder conventions). This is a strength.

---

## 8. Documentation Quality Metrics

### 8.1 Consistency

| Dimension | Consistency | Notes |
|-----------|-------------|-------|
| Skill file structure | High | All 12 follow same pattern: frontmatter, when-to-use, announce, template reference, frontmatter mandate, workflow |
| Agent file structure | High | All 9 follow same pattern: frontmatter (description, tier, mode, tools), persona, instructions |
| Template structure | High | All 8 follow same pattern: YAML frontmatter example, section headings, inline comments |
| Naming conventions | Medium | Skills use `vaultspec-*`, agents use `vaultspec-*`, but README titles vary in style |
| Cross-references | Low | Skills reference templates but not agents; agents reference skills but not templates; no bidirectional linking |

### 8.2 Accuracy

| Claim | Accuracy |
|-------|----------|
| "All features implemented" | True (02-tech-audit.md confirms 0 stubs) |
| Agent tier -> model mapping | True (CLI output confirms) |
| Template compliance rules | True (verification tool enforces them) |
| `workflows/` directory exists | **False** -- referenced but missing |
| `subagent.py` works from CLI | **False** -- crashes on import |
| 93 vault verification errors | True (01-ux-simulation.md; framework's own vault fails its own validator) |

### 8.3 Freshness

The documentation appears current as of the February 2026 codebase state. Agent definitions reference current model names (Opus 4.6, Sonnet 4.5, Gemini 3 Pro). No stale references to deprecated APIs were found in the documentation itself (though some were found and fixed in tests per 03-test-verification.md).

One notable stale reference: The `vaultspec-adr-researcher` and `vaultspec-complex-executor` agents contain Rust-specific language ("crate naming," "cargo-check," "thiserror," "anyhow") despite the project being a Python framework. This appears to be leftover from an earlier iteration when the project targeted Rust development.

---

## 9. Competitor Documentation Comparison

### 9.1 Kiro (AWS)

Kiro launches with a polished landing page, IDE download, and in-IDE guided experience. The spec workflow is visual: users see Requirements -> Design -> Tasks in a sidebar. Documentation is embedded in the product experience.

**vaultspec comparison**: vaultspec has no landing page, no guided experience, and no visual interface. The CLI is capable but undiscoverable.

### 9.2 GitHub Spec Kit

Spec Kit's README on GitHub is a model of clarity: short overview, installation in 3 steps, "Getting Started" with a worked example, concept explanation, then reference. The slash-command integration means users discover features organically while coding.

**vaultspec comparison**: vaultspec's README is 7 lines. Spec Kit's is ~500 lines of progressive, well-structured content.

### 9.3 Tailwind CSS (gold standard)

Tailwind's documentation site is the industry benchmark: search, sidebar navigation, code examples with live preview, version selector, and API reference for every utility. The "Installation" page supports 5 different frameworks with copy-paste commands.

**vaultspec comparison**: vaultspec has no documentation site, no search, no sidebar, and no framework-specific installation paths.

**Cross-reference**: 04-competitive-landscape.md, Category 1 (SDD Tools) and Category 2 (AI Coding Assistants)

---

## 10. Recommendations

### Tier 1: Immediate (Required for Any Public Release)

1. **Rewrite `README.md`** to include: one-paragraph value proposition, prerequisites, installation steps (with `pip install` variants), a 60-second quickstart showing the first CLI command, and prominent links to the full user manual.

2. **Create a "Getting Started" guide** covering: environment setup, first `cli.py agents list`, first `docs.py create`, first full Research-to-Verify cycle with a worked example.

3. **Add a "Concepts" document** explaining: what SDD is and why it matters, the 5-phase workflow with plain-language descriptions, what `.vault/` is and why it exists, how agents/skills/rules relate to each other.

4. **Fix or document the `subagent.py` import bug** -- users cannot dispatch sub-agents, which is the primary mechanism for executing the SDD workflow.

### Tier 2: High Priority (Needed for Developer Adoption)

5. **Create a CLI reference document** consolidating all three CLIs (cli.py, docs.py, subagent.py) with examples and expected output.

6. **Document the 30+ configuration variables** with a reference page listing each `VAULTSPEC_*` env var, its default, and what it controls.

7. **Document the RAG search query syntax** (`type:`, `feature:`, `date:`, `tag:` filters) -- this is a power feature that no user will discover on their own.

8. **Add architecture diagrams** for the protocol stack, sync flow, and agent interaction patterns.

9. **Separate human-facing docs from agent-facing instructions** in agent/skill files, or add a clear visual divider between "About this Agent" (human-readable) and "Agent Instructions" (AI-readable).

### Tier 3: Nice to Have (Polish for Community Growth)

10. **Create a documentation site** (even a simple MkDocs or Docusaurus deployment) with search, sidebar navigation, and versioning.

11. **Add expected output examples** to all CLI command documentation.

12. **Create a "Migration Guide"** for users coming from Kiro, Spec Kit, or plain Claude Code CLAUDE.md setups.

13. **Rename `.vaultspec/templates/readme.md`** to `documentation-standards.md` to avoid confusion with actual README files.

14. **Remove or create the `workflows/` directory** -- currently referenced but nonexistent.

---

## 11. Scorecard

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Diataxis Coverage (4 quadrants) | 3/10 | 20% | 0.6 |
| Progressive Disclosure | 2/10 | 15% | 0.3 |
| Information Architecture | 4/10 | 15% | 0.6 |
| Onboarding Experience | 1/10 | 20% | 0.2 |
| Feature Discoverability | 5/10 | 10% | 0.5 |
| Documentation Completeness | 3.5/10 | 10% | 0.35 |
| Visual Design & Examples | 5/10 | 10% | 0.5 |
| **Weighted Total** | | | **3.05/10** |

### By Diataxis Quadrant

| Quadrant | Score | Key Gap |
|----------|-------|---------|
| Tutorials | 0/10 | No tutorial exists |
| How-To Guides | 4/10 | Skill docs are implicit how-tos for agents, not users |
| Reference | 7/10 | Strong agent/skill/template reference, scattered |
| Explanation | 2/10 | No conceptual docs, no "why" documentation |

---

*Report generated by MarketingLead documentation UX audit agent. Assessment based on reading all project documentation files and comparison with industry documentation standards.*
