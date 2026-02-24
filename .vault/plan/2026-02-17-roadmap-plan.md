---
tags:
  - "#plan"
  - "#roadmap"
date: "2026-02-17"
related:
  - "[[2026-02-17-audit-summary-audit]]"
---
# vaultspec Roadmap: Wave-Based Rollout Plan

## Context

Six Opus agents conducted a comprehensive audit of vaultspec on 2026-02-17, producing 7 interlinked reports in `.vault/audit/`. The audit scored the project **6.6/10 overall** — Technical 9.0, Tests 8.5, UX 3.5, Docs 3.0, Market 7.5, Protocol 8.0. The core thesis: "the engineering is ahead of the competition; the presentation is behind it." This roadmap addresses every finding across all reports, organized into dependency-ordered waves.

### Audit Discrepancies Resolved

1. **AGENTS.md**: `cli.py config sync` already generates AGENTS.md — but in vaultspec's custom format, NOT the agents.md standard. Gap is **format compliance**, not generation.
2. **Hybrid Search**: Fully implemented (BM25+ANN+RRF in `rag/store.py`). Protocol research was incorrect. **Struck from gap list.**
3. **subagent.py bug**: Confirmed — missing `from _paths import ROOT_DIR` bootstrap.

---

## Wave 0: Critical Blocking Bugs

**Scope**: Fix issues that prevent core features from working.
**Effort**: Hours.
**Sources**: 01-ux-simulation.md S3.3, S7; 03-test-verification.md Failures 1-5

| # | Item | File(s) | Fix |
|---|------|---------|-----|
| 0.1 | subagent.py crashes on import | `subagent.py:1-16` | Add `from _paths import ROOT_DIR` before logging_config import |
| 0.2 | CLI test runner wrong path | `cli.py:1111` | Change `.vaultspec/tests` to `.vaultspec/lib/tests` |
| 0.3 | A2A e2e tests lack skip markers | `test_e2e_a2a.py` | Add `@pytest.mark.claude`/`@pytest.mark.gemini` with `skipUnless` |
| 0.4 | Typo "developmment" | `.vaultspec/README.md:4` | Fix to "development" |

---

## Wave 1: Self-Dogfooding & Credibility

**Effort**: 1-3 days. **Depends on**: Wave 0

| # | Item | Details |
|---|------|---------|
| 1.1 | Fix 93 vault verification errors | Naming violations, missing tags, broken links, orphaned docs |
| 1.2 | Resolve workflows/ phantom directory | Create or remove references |
| 1.3 | Populate PROJECT.md | Example project-specific context |
| 1.4 | Remove stale Rust-specific language | adr-researcher.md, complex-executor.md |
| 1.5 | Rename templates/readme.md | -> documentation-standards.md |

---

## Wave 2: Onboarding Documentation

**Effort**: 1-2 weeks. **Depends on**: Wave 1

| # | Item | File |
|---|------|------|
| 2.1 | Rewrite top-level README.md | `README.md` |
| 2.2 | Getting Started guide | `docs/getting-started.md` |
| 2.3 | Concepts document | `docs/concepts.md` |
| 2.4 | CLI Reference | `docs/cli-reference.md` |
| 2.5 | Configuration Reference | `docs/configuration.md` |
| 2.6 | RAG Query Syntax | `docs/search-guide.md` |
| 2.7 | Architecture diagrams | Embedded in docs/concepts.md |
| 2.8 | Human/agent doc separation | `.vaultspec/agents/*.md`, `.vaultspec/skills/*.md` |

---

## Wave 3: CLI Completeness

**Effort**: 1-2 weeks. **Depends on**: Wave 0. Parallel with Wave 2.

| # | Item | CLI |
|---|------|-----|
| 3.1 | `init` command | `cli.py init` |
| 3.2 | `remove` commands | `cli.py {rules,agents,skills} remove <name>` |
| 3.3 | `show` commands | `cli.py {rules,agents,skills} show <name>` |
| 3.4 | `rename` commands | `cli.py {rules,agents,skills} rename <old> <new>` |
| 3.5 | `edit` command | `cli.py {rules,agents,skills} edit <name>` |
| 3.6 | `--version` flag | All 3 CLIs |
| 3.7 | `doctor` command | `cli.py doctor` |
| 3.8 | `--template` flag | `cli.py {agents,skills} add` |
| 3.9 | GPU/CUDA in help text | `vault.py index/search --help` |

---

## Wave 4: Ecosystem Integration

**Effort**: 2-4 weeks. **Depends on**: Waves 2, 3

| # | Item |
|---|------|
| 4.1 | AGENTS.md standard compliance |
| 4.2 | Embedding model upgrade (Qwen3-0.6B primary, nomic fallback) |
| 4.3 | ACP SDK upgrade (0.8.0 -> 0.8.1) |
| 4.4 | MCP security baseline (OWASP MCP01, MCP05, MCP07) |

---

## Wave 5: Test Coverage & CI

**Effort**: 1-2 weeks. **Depends on**: Waves 0, 3. Parallel with Wave 4.

| # | Item |
|---|------|
| 5.1 | vault.py CLI tests |
| 5.2 | logging_config tests |
| 5.3 | Fix RAG test timeouts |
| 5.4 | Metrics test expansion |
| 5.5 | mcp.json config loading tests |
| 5.6 | Include benchmarks in markers |
| 5.7 | CI pipeline (GitHub Actions) |

---

## Wave 6: Strategic Features

**Effort**: 1-2 months. **Depends on**: Waves 2-5

| # | Item | Inspired By |
|---|------|-------------|
| 6.1 | Agent Readiness Assessment | Factory AI |
| 6.2 | Event-driven hooks | Kiro |
| 6.3 | Constitution layer | GitHub Spec Kit |
| 6.4 | Register in ACP Registry | Zed/JetBrains |
| 6.5 | Interactive add modes | UX best practice |
| 6.6 | `vault.py audit --fix` | UX best practice |

---

## Wave 7: Advanced Features

**Effort**: Quarter+. **Depends on**: Waves 4-6

| # | Item |
|---|------|
| 7.1 | Agentic RAG |
| 7.2 | GraphRAG |
| 7.3 | A2A v0.3 features (gRPC, security signing) |
| 7.4 | MCP Registry integration |
| 7.5 | Agent eval framework |
| 7.6 | Policy Engine with tiers |
| 7.7 | Compliance dashboard |
| 7.8 | Parallel agent execution |
| 7.9 | Spec Registry |
| 7.10 | Reverse spec generation |
| 7.11 | Token optimization |
| 7.12 | Documentation site |
| 7.13 | Migration guide |

---

## Wave Dependency Graph

```
Wave 0 (Blocking Bugs)
  ├── Wave 1 (Self-Dogfooding)
  │     └── Wave 2 (Documentation) ──┐
  ├── Wave 3 (CLI Completeness) ─────┤
  │                                   ├── Wave 4 (Ecosystem Integration)
  ├── Wave 5 (Tests & CI) ───────────┤
  │                                   └── Wave 6 (Strategic Features)
  │                                         └── Wave 7 (Advanced Features)
```

**Total: 56 items across 8 waves. Every audit finding addressed.**
