---
tags:
  - "#research"
  - "#marketing-and-documentation"
date: "2026-02-20"
related:
  - "[[2026-02-17-marketing-ux-audit]]"
  - "[[2026-02-17-roadmap-plan]]"
  - "[[2026-02-18-marketing-audit-documentation-quality]]"
---
# `marketing-and-documentation` research: Gap analysis after Wave 2

Audit of all documentation produced in Wave 2 (onboarding pass) against prior
marketing audit recommendations. Identifies what was completed, what gaps remain,
and scopes the `marketing-and-documentation` feature.

## Findings

### Wave 2 Completion Status

All eight Wave 2 items are substantially complete as of 2026-02-20:

| Item | File | Status |
| :--- | :--- | :--- |
| 2.1 Rewrite README.md | `README.md` | ✅ Rewritten — badges, problem statement, GPU escape hatch, quick start |
| 2.2 Getting Started guide | `docs/getting-started.md` | ✅ Complete — venv, doctor, troubleshooting, full workflow example |
| 2.3 Concepts document | `docs/concepts.md` | ✅ Complete — SDD, governance, protocol stack, Mermaid diagrams |
| 2.4 CLI Reference | `docs/cli-reference.md` | ✅ Complete — all three CLIs documented with flags and examples |
| 2.5 Configuration Reference | `docs/configuration.md` | ✅ Complete |
| 2.6 RAG Query Syntax | `docs/search-guide.md` | ✅ Complete |
| 2.7 Architecture diagrams | `docs/concepts.md` | ✅ Config sync flow + agent dispatch flow as Mermaid |
| 2.8 Human/agent doc separation | `.vaultspec/rules/agents/*.md` | ⚠️ Not verified — agent files still contain stale Rust language |

Beyond Wave 2, additional content was also produced:

| File | Content |
| :--- | :--- |
| `docs/api.md` | Python library API reference — all 9 modules documented |
| `docs/tutorials/first-governed-feature.md` | Complete 5-phase tutorial with the `/health` endpoint example, real sample artifacts |
| `docs/guides/team-lead.md` | Team setup, shared vault, governance/compliance angle |
| `docs/guides/enterprise-evaluator.md` | Enterprise persona guide (~6KB) |
| `docs/guides/individual-developer.md` | Individual developer persona guide (~4KB) |
| `docs/blog/spec-driven-development.md` | Long-form SDD explainer with TDD/BDD comparison, industry momentum (~12KB) |
| `docs/blog/why-governance.md` | Governance-focused marketing piece (~11KB) |

The documentation corpus has expanded substantially since the Feb 17 audit.

---

### Critical Gaps Remaining

The following marketing audit recommendations are **not yet addressed**:

#### Gap 1: README marketing punch (HIGH priority)

The Feb 18 audit scored the README 5/10 and cited: "no emotional hook, no screenshot,
no demo GIF, no 'here is what this solves for you today.'" The rewritten README has
improved the structure significantly — it now has a problem statement, GPU escape hatch,
and quick start. However, it still lacks:

- **Demo GIF / asciicast**: No terminal recording showing the tool in action. This is
  the single highest-ROI documentation investment per the competitor analysis (Aider,
  Cline, Cursor all lead with a visual demo).
- **Before / After framing**: No "without vaultspec / with vaultspec" concrete contrast.
  The "The Problem" section describes the problem but does not show it.
- **Social proof**: No stars badge, no "used by N teams", no testimonials. Acceptable
  for alpha but will matter at public launch.
- **Call to action**: The quick start block is good but the README ends without a hook
  to the full tutorial or the blog posts.

#### Gap 2: Tutorial corpus is thin (HIGH priority)

Only one tutorial exists (`first-governed-feature.md`). The Feb 18 audit listed five
high-priority tutorials. The remaining four are absent:

1. **"Adding vaultspec to an Existing Project"** — how to adopt mid-project, import
   existing decisions into the vault, seed the RAG index from an existing codebase
2. **"Running vaultspec with Gemini CLI"** — ACP integration walkthrough; ACP is a
   key differentiator and the tutorial corpus should demonstrate it
3. **"Multi-Agent Workflow: Research Agent Calls Executor"** — shows the MCP subagent
   server in action, the most technically impressive feature
4. **"Customizing Agents: Creating Your Own Executor"** — how to define a new agent with
   custom rules and tier; critical for adoption by teams that want to extend the framework

These tutorials are the primary mechanism for converting evaluators into users. The
existing `/health` tutorial is excellent — the pattern and quality bar are established.

#### Gap 3: `.vaultspec/README.md` is a silo (MEDIUM priority)

The internal framework manual (`.vaultspec/README.md`) does not cross-link to the `docs/`
directory. A user who discovers the manual through `ls -a` (the likely path for developers
who know to look in dotfile directories) will not find the getting-started guide, concepts
document, or tutorials. The manual should be updated to include a "See Also" section
linking to `docs/`.

#### Gap 4: Stale Rust language in agent definitions (MEDIUM priority — Wave 1.4)

The Feb 17 roadmap flagged this as Wave 1 item 1.4: agent files `vaultspec-adr-researcher.md`
and `vaultspec-complex-executor.md` contain Rust-specific language ("crate naming,"
"cargo-check," "thiserror," "anyhow"). This is confusing for a Python framework and
may mislead agents operating with these definitions. This has not yet been addressed.

#### Gap 5: Utility skills not documented (LOW priority)

The `vaultspec-fd`, `vaultspec-rg`, `vaultspec-sg`, and `vaultspec-sd` skills appear in
`.vaultspec/rules/skills/` but are not mentioned in any user-facing documentation. The
Feb 18 CLI reference audit noted this gap. These utility skills should either be
documented in the CLI reference or clearly scoped as internal-only.

#### Gap 6: Missing navigation index for docs/ (LOW priority)

There is no `docs/index.md` or table of contents file. The README links to six top-level
`docs/` files but does not surface the `guides/`, `blog/`, or `tutorials/` subdirectories.
A reader who finds `docs/getting-started.md` has no easy path to the tutorials or guides
without returning to the README.

---

### What Has Improved vs. Feb 17 Audit

| Category | Feb 17 Score | Current Assessment |
| :--- | :--- | :--- |
| Tutorials (Diataxis) | 0/10 | ~5/10 — one strong tutorial, but the corpus remains thin |
| How-To Guides | 4/10 | ~7/10 — guides exist for all three personas |
| Reference | 7/10 | ~9/10 — CLI ref, config ref, API ref all present |
| Explanation | 2/10 | ~8/10 — concepts.md and two blog posts cover this well |
| Onboarding Experience | 1/10 | ~7/10 — GPU escape hatch, venv, doctor, troubleshooting |
| Progressive Disclosure | 2/10 | ~6/10 — README → getting-started → concepts → reference chain exists |
| README Marketing | 3/10 | ~5/10 — structured but no demo or visual hook |

The documentation score has moved from approximately 3/10 overall to approximately 6.5/10.
The structural deficiencies are resolved. The remaining gap is marketing polish and
tutorial depth.

---

### Prioritized Recommendations

**Tier 1: Marketing polish (prerequisite for public launch)**

1. Add an asciicast or terminal GIF to the README showing a 90-second research-to-plan
   workflow. Even a static code block with realistic output would be a significant
   improvement over the current placeholder-free commands.
2. Add a "Before / After" section to the README: show what AI development looks like
   without vaultspec (context loss, inconsistent decisions, no audit trail) vs. with it.
3. Ensure the README's documentation links section surfaces `docs/tutorials/` and
   `docs/guides/` — not just the top-level docs.

**Tier 2: Tutorial expansion (needed for developer adoption)**

4. Write "Adding vaultspec to an Existing Project" tutorial.
5. Write "Running vaultspec with Gemini CLI" tutorial (ACP differentiator showcase).

**Tier 3: Internal hygiene (needed for credibility)**

6. Strip Rust-specific language from `vaultspec-adr-researcher.md` and
   `vaultspec-complex-executor.md` (Wave 1.4).
7. Add a "See Also: Human Documentation" section to `.vaultspec/README.md` linking to
   `docs/getting-started.md`, `docs/concepts.md`, and `docs/tutorials/`.
8. Document or scope the four utility skills (`fd`, `rg`, `sg`, `sd`) in `cli-reference.md`.

**Tier 4: Navigation polish (nice to have)**

9. Add a `docs/README.md` index listing all documentation with one-line summaries and
   surfacing the guides and tutorials subdirectories.
