---
tags:
  - "#audit"
  - "#naming-surface"
date: 2026-03-11
---

# Naming And Shipped-Surface Audit

## Canonical Names Actually Shipped

- Distribution package: `vaultspec-core`
- Python import package: `vaultspec_core`
- Installed CLI executable: `vaultspec-core`
- Installed MCP executable: `vaultspec-mcp`
- MCP server key scaffolded into `mcp.json`: `vaultspec-core`

Programmatic evidence:
- [pyproject.toml](../../pyproject.toml#L38)
- [pyproject.toml](../../pyproject.toml#L50)
- [mcp.json](../../mcp.json#L3)
- [src/vaultspec_core/cli/root.py](../../src/vaultspec_core/cli/root.py#L43)
- [src/vaultspec_core/mcp_server/app.py](../../src/vaultspec_core/mcp_server/app.py#L44)
- [tests/test_package_metadata.py](../../tests/test_package_metadata.py#L17)
- [tests/test_mcp_config.py](../../tests/test_mcp_config.py#L25)

## Acceptable Versus Stale Uses Of `vaultspec`

Acceptable:
- `vaultspec_core` as the Python import/package namespace.
- `.vaultspec/` as the framework resource directory.
- `vaultspec-*` internal skill, rule, and agent identifiers when they name
  framework resources rather than installed executables.
- prose such as "vaultspec workspace" or "vaultspec framework" when referring
  to the concept, not the shipped CLI command.

Stale or contract-significant drift:
- bare `vaultspec` used as the user-invoked CLI executable
- `vaultspec` used as the MCP server command surface
- any docs or rules claiming the MCP server provides team-thread orchestration,
  `dispatch_agent`, or `list_agents`
- env/config examples that still document removed runtime variables or old MCP
  topology as if they are live

## Findings

### High Severity

1. Hook example still teaches the removed `vaultspec` CLI and removed hook event.
   Type: documentation/config defect

   Evidence:
   - [.vaultspec/rules/hooks/example-audit-on-create.yaml](../../.vaultspec/rules/hooks/example-audit-on-create.yaml#L3)

   Problems:
   - uses `vaultspec vault audit --verify`
   - uses `vaultspec vault create`
   - documents removed `vault.index.updated`
   - documents an `agent` action block even though the live runtime is shell-only

2. Core framework rules still claim a team-thread MCP orchestration surface that the shipped product does not expose.
   Type: documentation/rule defect with contract implications

   Evidence:
   - [.vaultspec/rules/system/03-vaultspec.md](../../.vaultspec/rules/system/03-vaultspec.md#L63)
   - [.vaultspec/rules/skills/vaultspec-execute/SKILL.md](../../.vaultspec/rules/skills/vaultspec-execute/SKILL.md#L5)
   - [.vaultspec/rules/skills/vaultspec-execute/SKILL.md](../../.vaultspec/rules/skills/vaultspec-execute/SKILL.md#L27)
   - [.vaultspec/rules/skills/vaultspec-research/SKILL.md](../../.vaultspec/rules/skills/vaultspec-research/SKILL.md#L25)
   - [.vaultspec/rules/skills/vaultspec-team/SKILL.md](../../.vaultspec/rules/skills/vaultspec-team/SKILL.md#L26)
   - [.vaultspec/rules/agents/vaultspec-adr-researcher.md](../../.vaultspec/rules/agents/vaultspec-adr-researcher.md#L18)
   - [.vaultspec/rules/agents/vaultspec-high-executor.md](../../.vaultspec/rules/agents/vaultspec-high-executor.md#L18)
   - [.vaultspec/rules/agents/vaultspec-low-executor.md](../../.vaultspec/rules/agents/vaultspec-low-executor.md#L18)
   - [.vaultspec/rules/agents/vaultspec-standard-executor.md](../../.vaultspec/rules/agents/vaultspec-standard-executor.md#L18)

   Problem:
   - these files describe a shipped MCP capability that is not present in the
     current `vaultspec-mcp` surface

3. `.env.example` still documents an older runtime model and stale product name.
   Type: config/documentation defect

   Evidence:
   - [.env.example](../../.env.example#L1)

   Problems:
   - header still brands the file as `vaultspec`
   - documents stale variables such as `VAULTSPEC_MCP_ROOT_DIR`,
     `VAULTSPEC_MCP_PORT`, `VAULTSPEC_MCP_HOST`, `VAULTSPEC_MCP_TTL_SECONDS`,
     `VAULTSPEC_A2A_*`, and task-engine knobs that do not match the current
     config registry/runtime boundary

### Medium Severity

4. Generated/internal framework surfaces still use `vaultspec` as the framework identity in ways that blur product name versus framework name.
   Type: documentation defect

   Evidence:
   - `.agents/GEMINI.md` (removed)
   - [src/vaultspec_core/config/config.py](../../src/vaultspec_core/config/config.py#L1)
   - [src/vaultspec_core/config/workspace.py](../../src/vaultspec_core/config/workspace.py#L1)
   - [src/vaultspec_core/core/helpers.py](../../src/vaultspec_core/core/helpers.py#L1)

   Note:
   - most of these are concept/framework references, not executable-name bugs
   - they still need editorial review so users do not confuse the framework
     noun `vaultspec` with the shipped command `vaultspec-core`

5. CLI reference still contains known-drift notes that must be reconciled with code fixes, not left as permanent wrapper text.
   Type: documentation defect

   Evidence:
   - `.vaultspec/docs/cli-reference.md` (removed)

   Note:
   - these notes are currently truthful, but they identify unresolved product
     inconsistencies rather than stable reference material

### Low Severity

6. Some prose still says "vaultspec workspace" or "vaultspec framework."
   Type: editorial only

   Examples:
   - `.vaultspec/docs/cli-reference.md` (removed)
   - `.vaultspec/docs/concepts.md` (removed)

   This is acceptable when it clearly refers to the conceptual framework rather
   than the executable name.

## Recommended Repair Order

1. Fix the hook example and `.env.example`.
   Reason:
   - both are direct user-facing setup/config surfaces
   - both currently teach incorrect commands or obsolete runtime contracts

2. Rewrite the framework/rule files that still promise MCP team-thread orchestration.
   Reason:
   - these create semantic drift in the project brain, not just stale docs

3. Re-audit generated/internal framework outputs after the source-rule repair.
   Reason:
   - `.agents/` and `.claude/` should inherit the corrected semantics

4. Do a final wrapper-doc pass over README and CLI/MCP docs only after the
   contract-level rule surfaces are corrected.

## Classification Summary

- Code/config/test defects:
  - `.env.example` stale runtime variable surface
- Documentation-only defects:
  - hook example command/event drift
  - wrapper-doc and framework-doc stale naming
- Rule/contract defects:
  - `.vaultspec/rules/system/framework.md`
  - `.vaultspec/rules/skills/vaultspec-execute/SKILL.md`
  - `.vaultspec/rules/skills/vaultspec-research/SKILL.md`
  - `.vaultspec/rules/skills/vaultspec-team/SKILL.md`
  - related executor/researcher agent personas that still describe nonexistent
    MCP orchestration behavior

## Addendum: Root CLI `mcp` Dead Branch

- The special-case `ctx.invoked_subcommand == "mcp"` branch in
  [src/vaultspec_core/cli/root.py](../../src/vaultspec_core/cli/root.py#L1)
  was dead compatibility code for an older root-CLI MCP path.
- The live packaged surface ships MCP through the separate
  `vaultspec-mcp` executable, not through `vaultspec-core mcp`.
- The dead branch has been removed and root CLI coverage now asserts that
  `mcp` is not a live root subcommand.
