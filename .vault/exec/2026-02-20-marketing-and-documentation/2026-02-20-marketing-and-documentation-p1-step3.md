---
tags:
  - "#exec"
  - "#marketing-and-documentation"
date: 2026-02-20
related:
  - "[[2026-02-20-marketing-and-documentation-p1-plan]]"
---

# `marketing-and-documentation` `phase1` `step3`

Rewrote root `README.md` with expanded quick start and abbreviated worked example.

- Modified: `README.md`

## Description

Three targeted edits:

1. **Quick Start expansion**: Added `cli.py doctor` as the first command in the post-install
   block, so the verification step is immediately visible to new users.

2. **Worked Example section**: Added a new `## Worked Example` section between "The Workflow"
   and "Documentation" blocks. Shows the five skill invocations and their resulting artifact
   paths using a plain text code block. Links to `.vaultspec/docs/concepts.md` for the full
   worked tutorial with sample output.

3. **Documentation links updated**: Replaced `docs/*.md` links with `.vaultspec/docs/*.md`
   links for concepts, cli-reference, and search-guide. Collapsed four links (getting-started,
   concepts, configuration, search-guide) to three (concepts & tutorial, cli-reference,
   search-guide) matching the new file structure.

## Tests

All three links in the Documentation section point to files that exist:
- `.vaultspec/docs/concepts.md` ✓
- `.vaultspec/docs/cli-reference.md` ✓
- `.vaultspec/docs/search-guide.md` ✓
