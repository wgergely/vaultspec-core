---
tags:
  - '#audit'
  - '#roadmap'
date: '2026-02-17'
related:
  - '[[2026-02-17-audit-summary-audit]]'
---

# UX Simulation Report: First-Time User Experience

**Agent**: JohnDoe (simulated brand-new user)
**Date**: 2026-02-17
**Scope**: End-to-end first-time user journey through vaultspec documentation, CLI tools, and framework structure

______________________________________________________________________

## Executive Summary

vaultspec is a governed development framework for AI agents that enforces a Research -> Specify -> Plan -> Execute -> Verify workflow. As a first-time user, the framework shows strong architectural vision and well-designed tooling, but suffers from critical gaps in onboarding documentation, missing CRUD operations, and a broken CLI entry point that would immediately block new users attempting certain workflows.

**Overall Rating: 6.5/10** -- Strong conceptual foundation, incomplete user experience.

______________________________________________________________________

## 1. First Contact: README and Top-Level Documentation

### What I Found

The top-level `README.md` (7 lines) is extremely terse. It describes vaultspec as "a governed development framework for AI agents" and lists four bullet points about core components. The file ends with a **CAUTION** block warning developers not to run `cli.py config sync` in the framework development repo itself.

### Assessment

| Aspect                    | Rating | Notes                                                                                                       |
| ------------------------- | ------ | ----------------------------------------------------------------------------------------------------------- |
| Clarity of purpose        | 5/10   | "Governed development framework for AI agents" is vague. What does "governed" mean? What kind of AI agents? |
| Installation instructions | 0/10   | **Completely absent.** No pip install, no prerequisites, no quickstart guide.                               |
| Getting started guide     | 0/10   | No step-by-step guide for new users.                                                                        |
| Value proposition         | 4/10   | I can tell it involves workflows and templates, but not WHY I would want it.                                |

### Specific Issues

1. **No installation instructions at all.** A new user has no idea they need Python 3.13, PyTorch with CUDA, or what optional dependencies exist (`rag`, `dev`, `dev-rag` from pyproject.toml).
1. **No quickstart.** What is the first command I should run? `cli.py sync-all`? `vault.py create`? I have to discover this myself.
1. **No "What is this?" section.** The tagline doesn't explain the problem being solved. Compare: "vaultspec enforces documentation-backed decision trails for AI-assisted development, ensuring every code change is traceable to research, architectural decisions, and approved plans."
1. **CAUTION block is confusing for newcomers.** If I'm reading the README for the first time, I don't yet understand what `cli.py config sync` does or why it would be dangerous.

> **Cross-reference for TechAuditor (02-tech-audit.md):** Verify that pyproject.toml dependencies match documented requirements. Confirm the `rag` optional dependency group actually needs GPU/CUDA.

______________________________________________________________________

## 2. Framework Documentation (.vaultspec/README.md)

### What I Found

The `.vaultspec/README.md` is the **actual user manual** and is substantially better than the top-level README. It contains:

- Detailed skill descriptions with usage examples
- Agent reference table with tiers
- Two Mermaid diagrams (overview and detailed workflow)
- Context management section explaining config sync
- File responsibilities table

### Assessment

| Aspect           | Rating | Notes                                                         |
| ---------------- | ------ | ------------------------------------------------------------- |
| Workflow clarity | 8/10   | Very clear step-by-step with agent assignments                |
| Agent reference  | 9/10   | Excellent table with tiers, roles, and usage guidance         |
| Diagrams         | 7/10   | Helpful but the detailed workflow diagram is complex          |
| Discoverability  | 3/10   | Hidden inside `.vaultspec/` -- a new user might never find it |

### Specific Issues

1. **This file should be linked prominently from the top-level README.** Currently the top-level README says "See `.vaultspec/README.md`" only indirectly through FRAMEWORK.md.
1. **The User Manual is excellent but assumes too much context.** It jumps straight into skills and agents without explaining what `.vault/` is, what artifacts are, or what the expected directory structure looks like after setup.
1. **Typo on line 4:** "developmment" (double m).
1. **Missing "Prerequisites" section.** What tools need to be installed? (Python, CUDA, fd, rg, sd, sg, etc.)

______________________________________________________________________

## 3. CLI Tool Experience

### 3.1 Main CLI (`cli.py`)

**Available subcommands:** rules, agents, skills, config, system, sync-all, test

#### List Commands -- Working Well

\`
i.py rules list -> Clean table: 2 builtin rules
i.py agents list -> Clean table: 9 agents with tiers and model mappings
cli.py skills list -> Clean table: 12 skills with descriptions

i.py rules add --name NAME [--content CONTENT] [--force]
i.py agents add --name NAME [--description DESC] [--tier TIER] [--force]
cli.py skills add --name NAME [--description DESC] [--force]

```

- **No `--template` flag** for agents/skills. Creating an agent with just `--name` and `--description` gives a minimal file. Users need to know the agent file format by example.

#### Missing CRUD Operations -- Critical Gap

| Operation | rules | agents | skills |
|-----------|-------|--------|--------|
| list | Yes | Yes | Yes |
| add | Yes | Yes | Yes |
| remove | **NO** | **NO** | **NO** |
| rename | **NO** | **NO** | **NO** |
| edit | **NO** | **NO** | **NO** |
| show (single) | **NO** | **NO** | **NO** |

**Verdict: 3/10.** There is no way to remove, rename, or inspect individual resources through the CLI. Users must manually delete files from `.vaultspec/agents/`, `.vaultspec/rules/`, or `.vaultspec/skills/`. This is a significant gap for a "managed" framework.

> **Cross-reference for TechAuditor (02-tech-audit.md):** Verify that `--prune` on sync commands is the only mechanism for cleanup. Confirm whether manual file deletion is documented anywhere.

#### Sync Commands -- Working Well

```

cli.py sync-all --dry-run

**Verdict: 8/10.** The `--dry-run` flag is excellent, showing exactly what will be added to `.claude/`, `.gemini/`, and `.agent/` directories. The `--prune` flag for removing stale files is well-designed.

\`
cli.py config show -> Shows framework + project content and per-tool references

```
cli.py agents set-tier <name> --tier {LOW,MEDIUM,HIGH}

```

### 3.2 Docs CLI (`vault.py`)

**Available subcommands:** audit, create, index, search

#### Audit -- Excellent Feature

\`
cs.py audit --summary -> Clean stats (22 docs, 16 features)
cs.py audit --features -> Lists all feature tags

vault.py audit --verify -> Full validation (93 errors found!)

vault.py audit --graph -> Graph hotspots, orphan detection, invalid links

```

**Verdict: 9/10.** This is the crown jewel of the CLI. The verification catches naming violations, missing tags, broken links, and orphaned documents. The graph hotspot analysis is genuinely useful for understanding documentation structure.

**Issue noted:** Running `--verify` against the project's own `.vault/` directory shows 93 errors, meaning the framework's own documentation doesn't pass its own validation. This is concerning for first impressions.

> **Cross-reference for TechTester (03-test-verification.md):** Run `vault.py audit --verify` and confirm the 93 error count. Verify whether these are real violations or false positives.

#### Create -- Well-Designed

```

vault.py create --type {adr,exec,plan,reference,research} --feature FEATURE [--title TITLE]

**Verdict: 8/10.** Creates properly templated files with correct frontmatter, dates, and directory placement. The generated template includes helpful inline comments explaining each field.

**Issue noted:** The template includes `"`\<yyyy-mm-dd-\*>`"` as a placeholder related link, which would fail the verifier if not replaced. This is a known pattern but could be a trap for new users.

The index and search commands require the `rag` optional dependency (PyTorch, sentence-transformers, lancedb) which in turn requires an NVIDIA GPU with CUDA. This is not documented in the CLI help.

**Verdict: 5/10 (for documentation).** Running `vault.py index` without the RAG dependencies installed would presumably fail, but the help text doesn't mention this prerequisite.

> **Cross-reference for TechTester (03-test-verification.md):** Attempt `vault.py index` and `vault.py search "test"` to verify they work with proper GPU setup.

### 3.3 Subagent CLI (`subagent.py`)

```

$ subagent.py --help
Traceback (most recent call last):

```

**Verdict: 1/10.** The subagent CLI crashes immediately on import with `ModuleNotFoundError: No module named 'logging_config'`. This is a **blocking bug** that prevents any user from accessing subagent functionality through the CLI.

> **Cross-reference for TechAuditor (02-tech-audit.md):** Investigate the missing `logging_config` module. Is it a missing file, a path issue, or a dependency problem?
> **Cross-reference for TechTester (03-test-verification.md):** Confirm whether `subagent.py` tests pass or if this is a known failure.

______________________________________________________________________

```

.vaultspec/
  agents/          (9 agent definitions)
  skills/          (12 skill definitions)

  system/          (4 system prompt parts)
  templates/       (8 document templates)
  workflows/       (DOES NOT EXIST -- empty)
  lib/             (Python library and scripts)
  FRAMEWORK.md     (4 lines)
  PROJECT.md       (empty - 1 line)

```

### Issues

1. **`workflows/` directory is referenced in the README layout but does not exist.** This is confusing -- are workflows different from skills? The README mentions workflows but the directory is missing.
1. **`FRAMEWORK.md` is only 4 lines** referencing `.vaultspec/README.md`. It feels like a redirect rather than a standalone document.
1. **`PROJECT.md` is completely empty.** This is the "user-editable" file for project-specific context, but there's no example or guidance on what to put there.

______________________________________________________________________

## 5. Skills and Agent Definitions

### Skills (12 total)

| Skill                    | Purpose                             | Quality                            |
| ------------------------ | ----------------------------------- | ---------------------------------- |
| vaultspec-research       | Structured research & brainstorming | 9/10 -- Clear, well-documented     |
| vaultspec-adr            | Architecture Decision Records       | 8/10 -- Good template reference    |
| vaultspec-code-reference | Reference auditing                  | 7/10 -- Specialized but clear      |
| vaultspec-write-plan     | Plan writing                        | 8/10 -- Good integration guidance  |
| vaultspec-execute        | Plan execution                      | 9/10 -- Excellent delegation model |
| vaultspec-code-review    | Code review                         | 8/10 -- Clear audit criteria       |
| vaultspec-curate         | Vault maintenance                   | 7/10 -- Useful but niche           |
| vaultspec-subagent       | Agent dispatch (internal)           | 8/10 -- Good MCP integration docs  |
| vaultspec-fd/rg/sd/sg    | CLI tool wrappers                   | 6/10 -- Useful but feel bolted-on  |

**Overall Verdict: 8/10.** The workflow skills (research through review) form a coherent pipeline. The CLI tool wrapper skills (fd, rg, sd, sg) feel like they belong in a separate "utilities" category rather than alongside workflow skills.

Agent definitions are well-structured with:

- YAML frontmatter (description, tier, mode, tools)
- Clear persona descriptions
- Specific output format requirements

**Overall Verdict: 8/10.** Well-defined agent personas with clear boundaries. The tier system (LOW/MEDIUM/HIGH) maps cleanly to model capabilities.

______________________________________________________________________

## 6. Templates

All 8 templates follow a consistent pattern:

- YAML frontmatter with inline comments

- Placeholder values with clear replacement instructions

- Section headings matching the expected document structure

- `<!-- DO NOT -->` warnings about frontmatter placement

**Overall Verdict: 8/10.** Templates are well-designed and self-documenting. The inline YAML comments are particularly helpful.

______________________________________________________________________

## 7. Pain Points (Ranked by Severity)

### Critical

1. **No installation or setup documentation.** A new user has zero guidance on how to install vaultspec, what Python version is needed, or what dependencies to install. There is no `pip install vaultspec` command, no `vaultspec init` command, and no quickstart guide.

1. **`subagent.py` crashes on import** with `ModuleNotFoundError: No module named 'logging_config'`. This completely blocks subagent dispatch via CLI, which is a core feature described throughout the documentation.

1. **No remove/rename/delete CLI commands** for rules, agents, or skills. The framework positions itself as a "managed" system but only provides half of CRUD operations.

### Major

1. **The actual user manual (`.vaultspec/README.md`) is buried** inside a hidden directory. New users reading the top-level `README.md` get a 7-line summary that doesn't explain how to get started.

1. **The framework's own `.vault/` fails its own verification** with 93 errors (naming violations, missing tags, broken links, orphaned documents). This is a bad first impression -- "eat your own dog food."

1. **No `init` or `bootstrap` command** for setting up a new project. Users must manually create the `.vaultspec/` and `.vault/` directory structures, or copy them from somewhere undocumented.

1. **`vault.py index` and `vault.py search` require GPU/CUDA** but this prerequisite is not documented in the CLI help text or anywhere user-facing.

### Minor

1. **`workflows/` directory is referenced but doesn't exist.** This creates confusion about what workflows are vs. skills.

1. **`PROJECT.md` is empty** with no example content or guidance.

1. **Typo in README.md:** "developmment" (line 4 of `.vaultspec/README.md`).

1. **System prompt parts (`system/`) include Gemini-specific PowerShell instructions** that would be confusing if synced to a non-Windows environment.

1. **No version or changelog** visible to users. The pyproject.toml shows `0.1.0` but this isn't surfaced anywhere in CLI output or docs.

______________________________________________________________________

## 8. Highlights (What Works Well)

1. **`vault.py audit` is excellent.** The `--verify`, `--graph`, and `--summary` flags provide genuine value. The graph hotspot analysis with orphan detection and invalid link reporting is a standout feature.

1. **Agent tier system with model mapping** is well-designed. The `agents list` output showing both Claude and Gemini model assignments per tier is immediately useful.

1. **Template quality is high.** Self-documenting YAML frontmatter with inline comments, strict tagging rules, and consistent structure across all 8 templates.

1. **`sync-all --dry-run` is confidence-inspiring.** Users can preview exactly what files will be created/modified before committing to the operation.

1. **Multi-tool support** (Claude, Gemini, Antigravity) with clean separation. The sync system properly handles tool-specific paths (`.claude/`, `.gemini/`, `.agent/`).

1. **`vault.py create` generates ready-to-use files** with correct dates, directory placement, and pre-filled frontmatter.

1. **The mermaid diagrams** in `.vaultspec/README.md` effectively communicate the workflow architecture.

1. **Skills are well-documented** with clear activation instructions, output specifications, and template references.

______________________________________________________________________

## 9. Recommendations

### Immediate (Must-Have for Launch)

1. Write a comprehensive top-level `README.md` with: purpose, installation, prerequisites, quickstart, and link to the full user manual.
1. Fix `subagent.py` import error.
1. Add `remove` commands for rules, agents, and skills (`cli.py agents remove <name>`).
1. Add a `vaultspec init` or `cli.py init` command that bootstraps `.vaultspec/` and `.vault/` in a new project.
1. Fix the 93 verification errors in the framework's own `.vault/` directory.

### Short-Term (Should-Have)

1. Add `show` commands for individual resources (`cli.py agents show <name>`).
1. Add `rename` commands for resources.
1. Document GPU/CUDA requirements for RAG features in CLI help text.
1. Add a `--version` flag to all CLI tools.
1. Create a `workflows/` directory with at least one example workflow, or remove references to it.

### Nice-to-Have

1. Interactive mode for `agents add` with guided prompts.
1. Tab completion for CLI commands.
1. Colored output for audit results (errors in red, warnings in yellow).
1. `vault.py audit --fix` to auto-repair common violations (missing tags, wrong suffixes).

______________________________________________________________________

## 10. Summary Scorecard

| Category                  | Score      | Notes                                                   |
| ------------------------- | ---------- | ------------------------------------------------------- |
| Documentation (top-level) | 3/10       | Missing installation, setup, quickstart                 |
| Documentation (framework) | 8/10       | Excellent user manual, just poorly discoverable         |
| CLI: cli.py               | 7/10       | Good list/add/sync, missing remove/rename/show          |
| CLI: vault.py             | 9/10       | Standout feature, especially audit                      |
| CLI: subagent.py          | 1/10       | Broken on import                                        |
| Templates                 | 8/10       | Consistent, self-documenting                            |
| Agent definitions         | 8/10       | Well-structured with clear personas                     |
| Skill definitions         | 8/10       | Coherent pipeline with good docs                        |
| Setup/Onboarding          | 1/10       | No init command, no setup guide                         |
| Error messages            | 6/10       | argparse defaults are okay, but missing custom guidance |
| **Weighted Average**      | **5.9/10** |                                                         |

______________________________________________________________________

*Report generated by JohnDoe UX simulation agent. All CLI commands were executed live against the repository at `Y:\code\task-worktrees\main` on 2026-02-17.*
*Report generated by JohnDoe UX simulation agent. All CLI commands were executed live against the repository at `Y:\code\task-worktrees\main` on 2026-02-17.*
