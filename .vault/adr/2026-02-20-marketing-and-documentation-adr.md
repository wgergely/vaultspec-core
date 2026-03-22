---
tags:
  - '#adr'
  - '#marketing-and-documentation'
date: '2026-02-20'
related:
  - '[[2026-02-20-marketing-and-documentation-research]]'
  - '[[2026-02-20-marketing-and-documentation-p1-plan]]'
---

# marketing-and-documentation adr | (**status:** accepted)

## Problem Statement

The documentation corpus was scattered across a root `docs/` folder with marketing content, persona-targeted guides, and operational documentation mixed together. This made it difficult to maintain, deploy, and discover relevant documentation.

## Decision

Restructure the documentation by eliminating the root `docs/` folder. All operational documentation moves to `.vaultspec/docs/` so it deploys with the framework. Marketing and persona content is retired. The root `README.md` absorbs the install/setup flow and an abbreviated 5-phase worked example.

## Considerations

- Documentation should ship with the framework, not live in a separate `docs/` folder
- Marketing and persona-targeted guides (enterprise evaluator, team lead, individual developer) add maintenance burden without proportional value
- The tutorial content in `docs/tutorials/first-governed-feature.md` is high-quality and should be preserved
- CLI reference and search guide are operational docs that belong alongside the framework

## Rationale

Moving operational docs to `.vaultspec/docs/` ensures they are version-controlled alongside the framework code and deploy together. Retiring marketing content reduces maintenance scope. Absorbing the install flow into `README.md` gives users a single entry point.

## Consequences

- 9 files retired from `docs/`
- 3 sub-chapter files created in `.vaultspec/docs/`: `concepts.md`, `cli-reference.md`, `search-guide.md`
- Root `README.md` becomes the primary onboarding surface
- `.vaultspec/README.md` serves as the framework manual overview
