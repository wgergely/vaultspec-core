---
tags:
  - '#audit'
  - '#documentation'
date: 2026-03-11
---

# README Wrapper and User-Facing Documentation Audit

## Scope

This audit covers the user-facing documentation surface for `vaultspec-core`:
the root `README.md`, `.vaultspec/docs/concepts.md`,
`.vaultspec/docs/cli-reference.md`, `.vaultspec/docs/hooks-guide.md`,
`.vaultspec/README.md`, package metadata documentation pointers, and the minimum
install and MCP setup guidance required to run the shipped product.

This artifact records drift, target shape, and sequencing. It is not a README
rewrite and does not expand into contributor or internal implementation
documentation.

## Live Product Boundary

`vaultspec-core` currently ships a Python package for spec-driven workspace
management.

The live user-facing executables are:

1. `vaultspec`
1. `vaultspec-mcp`

The live CLI surface is narrower than several current docs imply.

`vaultspec` exposes:

- `vault`
- `rules`
- `skills`
- `agents`
- `config`
- `system`
- `hooks`
- `sync-all`
- `test`
- `doctor`
- `init`
- `readiness`

The `vault` namespace is itself limited. `vault_cli.py` owns only:

- `vault add`
- `vault audit`

There is no live root `vaultspec mcp` command, and there are no registered root
subcommands for `subagent`, `team`, or the broader ACP/A2A orchestration surface
described in older materials.

The MCP server exists as a separate console script, `vaultspec-mcp`, not as a
subcommand of `vaultspec`. The live MCP tool surface is vault-centric:

- `query_vault`
- `feature_status`
- `create_vault_document`
- `list_spec_resources`
- `get_spec_resource`
- `workspace_status`
- `audit_vault`

The operational model is workspace-bound. Users either run inside a workspace
that contains `.vaultspec/` or create one with `vaultspec init`. Target
selection uses `--target`, and runtime configuration is centered on
`VAULTSPEC_TARGET_DIR` plus a small set of directory and editor variables, not
the larger environment matrix currently documented in the CLI reference.

## Current Documentation Surface Map

`README.md`

- Should act as the package landing page.

- Must define what `vaultspec-core` ships, how to install it, how to start a
  workspace, how to access the CLI and MCP server, and where deeper docs live.

- Currently overstates capability boundaries and lacks essential install and
  setup guidance.

`.vaultspec/docs/concepts.md`

- Should own the SDD mental model, vault topology, and one worked end-to-end
  example.

- Must be rewritten around the surfaces that still exist.

- Currently centers removed ACP/A2A and subagent topology.

`.vaultspec/docs/cli-reference.md`

- Should be the exact reference for the live `vaultspec` CLI plus a separate
  section for `vaultspec-mcp`.

- Is currently the most stale user-facing document.

`.vaultspec/docs/hooks-guide.md`

- Should own hook schema, supported events, examples, and failure behavior for
  the runtime that actually ships.

- Currently documents capabilities beyond the live hook engine.

`.vaultspec/README.md`

- Should be the framework manual for `.vaultspec/` source-of-truth structure,
  sync behavior, and generated tool-config relationships.

- Should not serve as the primary public CLI manual.

## Findings

### Documentation Drift

1. Product identity drift: parts of the current docs still describe
   `vaultspec-core` as the broader agent orchestration platform rather than the
   narrower workspace-management package that is actually shipped.

1. CLI topology drift: the CLI reference documents removed or non-registered
   command groups, stale environment variables, and a root command structure
   that does not match the live `vaultspec` surface.

1. Vault namespace drift: user-facing documentation implies additional `vault`
   operations such as create, index, and search, but the live namespace exposes
   only `vault add` and `vault audit`.

1. MCP entrypoint drift: current documentation does not clearly state that the
   MCP server is started via `vaultspec-mcp`, not `vaultspec mcp`.

1. Workspace and configuration drift: current guidance uses the wrong targeting
   model and over-documents environment variables that are not part of the live
   operational contract.

1. Hooks capability drift: the hooks guide and README overstate hook behavior,
   including event coverage and action types, while the runtime supports shell
   actions on only three events.

1. Documentation ownership drift: the root README, concept guide, CLI
   reference, hooks guide, and `.vaultspec/README.md` do not currently enforce
   clean boundaries between package entry, user operation, conceptual model, and
   framework-internal structure.

### User Impact

1. A new user cannot reliably infer what package to install, which executable to
   run first, or whether a workspace must already exist.

1. A user attempting MCP setup can follow obsolete instructions and fail before
   transport initialization.

1. A user reading the current docs can reasonably expect commands and
   capabilities that do not exist.

1. Repo boundary ambiguity makes it unclear whether `vaultspec-core` is a
   package, a framework source tree, or a larger orchestration platform.

## README Target Shape

The root `README.md` should be a wrapper document with this information
architecture:

1. What `vaultspec-core` is.
   State the package boundary in one short paragraph: spec-driven workspace
   management, vault artifact operations, framework resource syncing, hooks,
   readiness and doctoring, and a separate vault-oriented MCP server.

1. What it installs.
   State that installation exposes two executables: `vaultspec` and
   `vaultspec-mcp`.

1. Requirements and recommended install path.
   Lead with the recommended standalone install path, `pipx install vaultspec-core`. Include the Python version requirement. Include source
   install as a secondary path using `python -m pip install .`. Do not document
   deprecated `setup.py` flows.

1. Quickstart: CLI.
   Show the minimum runnable path: initialize a workspace, sync framework
   resources, add a vault artifact, audit the vault, and inspect hooks.

1. CLI overview.
   Provide a compact command-group map only. Do not paste full `--help` output.
   Link outward to the CLI reference for exact syntax.

1. Quickstart: MCP server.
   Show the actual server entrypoint, label it as a local stdio MCP server, and
   link to deeper MCP documentation.

1. Documentation map.
   Link, in order, to concepts/tutorial, CLI reference, hooks guide, and the
   `.vaultspec` framework manual.

1. Repo boundary note.
   State explicitly what this package does not currently ship: the legacy
   subagent, team, and broader A2A/ACP surface described in older docs.

1. Support / where to get help.
   Keep this short and place it after the runnable user path.

The README should avoid:

- badge-heavy or marketing-heavy material above the first runnable command
- full CLI reference content
- a full MCP client matrix
- deep architecture or packaging internals before install and first run
- equal-weight install paths with no recommended default
- contributor workflow in the main user path

## Packaging and Distribution Gaps

1. There is no clear user-facing install section in the current landing
   documentation.

1. The documentation does not recommend a default install path for end users.
   The preferred default should be `pipx install vaultspec-core`.

1. There is no explicit quickstart explaining the workspace precondition and the
   role of `vaultspec init`.

1. The current user-facing surface does not explain that `vaultspec-mcp` is a
   separate installed executable.

1. MCP setup guidance does not currently document the required environment,
   especially `VAULTSPEC_TARGET_DIR`.

1. Package metadata points the Documentation URL at a missing top-level `docs/`
   directory even though the live documentation lives under `.vaultspec/docs/`.

1. Build guidance, if included anywhere user-facing, should use `python -m build` rather than legacy packaging flows.

## MCP Documentation Requirements

Any MCP documentation for `vaultspec-core` should state the following
unambiguously:

1. The server is a local stdio MCP server.

1. The executable is `vaultspec-mcp`.

1. Client configuration must document `command`, `args`, required `env`, and
   optional `cwd`.

1. Paths should be absolute where path resolution matters.

1. The minimum required environment should include `VAULTSPEC_TARGET_DIR` when
   the client process is not already rooted in the intended workspace.

1. The docs should briefly explain that the client launches the server as a
   subprocess and exchanges JSON-RPC messages over stdin/stdout.

1. The docs should warn that non-protocol stdout breaks the transport and that
   logs belong on stderr.

1. The root README should include one minimal client example only, with deeper
   client-specific guidance moved to linked documentation.

1. Verification guidance should include a concrete path such as MCP Inspector.

1. The documented tool list should match the live vault-oriented MCP surface
   and should not imply a root CLI `mcp` subcommand.

## Non-Documentation Defects

The following issues are runtime or packaging defects, not documentation drift,
though they directly affect what documentation can truthfully claim:

1. `init_run()` scaffolds `.mcp.json` with `python -m vaultspec_core mcp`, but
   that command does not exist.

1. `cli.py` contains dead special-case logic for `mcp`.

1. `doctor_run()` crashes on Windows `cp1252` consoles because of Unicode
   checkmark output.

1. The hooks engine docstring path differs from the runtime path wiring.

These defects should be fixed in code, then reflected in the user-facing docs.
They should not be silently papered over in README copy.

## Recommended Next Documentation Sequence

1. Fix the root `README.md` first so the package landing page states the correct
   product boundary, install path, quickstart, MCP entrypoint, and documentation
   map.

1. Rewrite `.vaultspec/docs/cli-reference.md` against the live CLI and MCP
   surfaces. This is the highest-drift reference document and should become the
   source of truth for command behavior.

1. Rewrite `.vaultspec/docs/concepts.md` so the mental model and walkthrough use
   only live workspace, vault, hook, and MCP-adjacent surfaces.

1. Rewrite `.vaultspec/docs/hooks-guide.md` to match the runtime hook model:
   actual events, shell-only action model, examples, and failure behavior.

1. Reframe `.vaultspec/README.md` as the framework-structure manual rather than
   a public product overview.

1. Correct the package Documentation URL so repository metadata points users to
   the real documentation surface.

1. After the runtime defects above are fixed, add one verified MCP setup example
   and one verified workspace initialization path to prevent further drift.

## Audit Addendum: CLI Naming Mismatch

The project currently presents a naming split across distribution, import, and
CLI surfaces: the distribution name is `vaultspec-core`, the import/package
name is `vaultspec_core`, and the shipped console scripts are `vaultspec` and
`vaultspec-mcp`. In addition, CLI help text and examples are hardcoded to
`vaultspec`.

Because the installed root console script is still `vaultspec`, documentation
cannot yet truthfully switch command examples to `vaultspec-core` without
creating a mismatch between published guidance and actual installed behavior.
This is therefore not only a documentation issue, but also a packaging and
public interface issue.

If `vaultspec-core` is the intended public CLI name, the following surfaces
must change first:

- Package console script definitions
- Hardcoded CLI help and example text
- Generated guidance that currently emits `vaultspec` usage examples

## Audit Addendum: Post-Rename Drift Outside The Root Wrapper Docs

The root package wrapper now exposes `vaultspec-core` and `vaultspec-mcp`, but
several repository documentation surfaces still describe commands and runtime
behaviors that the live codebase does not ship. This is no longer a simple
token-rename problem; parts of the documentation tree describe retired or
nonexistent interfaces.

- `.vaultspec/docs/search-guide.md` documents `vault search` and `vault index`
  commands, but the current CLI does not expose either command family.

- `.vaultspec/docs/hooks-guide.md` documents a `vault create` command, an
  unsupported `vault.index.updated` event, `agent` hook actions, and a
  `subagent` CLI surface. The runtime only exposes `vault add`, `vault audit`,
  `hooks list`, and `hooks run`, and the hook engine currently supports only
  `shell` actions.

- `.vaultspec/docs/concepts.md` still contains stale command examples and a
  `vaultspec sync` label even though the live CLI exposes `sync-all` and the
  per-resource `... sync` groups instead.

- `.vaultspec/README.md`, `.agents/skills/vaultspec-subagent/SKILL.md`,
  `.claude/skills/vaultspec-subagent/SKILL.md`, `.agents/rules/vaultspec-subagents.md`,
  and `.claude/rules/vaultspec-subagents.builtin.md` still portray a
  `subagent` CLI path that is not registered by the current packaged CLI.

- `.claude/settings.local.json` had pre-rename worktree paths and legacy probe
  commands/imports. The path and package probes have now been updated to the
  current `vaultspec-core` / `vaultspec_core` surfaces, but the surrounding
  local policy set should still be treated as an environment-specific config
  surface rather than project documentation.

### Audit Addendum: Hooks Runtime Drift

Focused verification confirms that the current hooks runtime and root CLI
diverge from stale expectations reflected in existing tests and documentation.
The live implementation supports a narrower event and action surface than some
audit assumptions currently imply.

- The live hook runtime supports exactly `vault.document.created`,
  `config.synced`, and `audit.completed`; there is no live
  `vault.index.updated` trigger in `src/vaultspec_core/hooks/engine.py`.

- `vault.document.created` is emitted from `vault add`, not `vault create`.

- The hook engine supports only `shell` actions; `agent` actions are not
  implemented.

- The root CLI does not register a `subagent` command, and
  `src/vaultspec_core/hooks/tests/test_hooks.py` still contains a stale
  expectation tied to `vault.index.updated`.

## Removed Search Surface Drift

The retired search guide described CLI `search` and `index` behavior that is
not part of the shipped product. The replacement should point users to the
live MCP `query_vault(...)` surface and remove the stale page entirely.

- Remove `.vaultspec/docs/search-guide.md` instead of renaming or leaving a
  compatibility stub.

- Add `.vaultspec/docs/vault-query-guide.md` to the root README documentation
  list.

- Treat any mention of CLI `search` or `index` as documentation drift unless a
  live shipped surface is added.
