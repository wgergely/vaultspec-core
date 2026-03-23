---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - '#audit'
  - '#mcp-cli-interface'
date: '2026-03-11'
related:
  - '[[2026-02-22-cli-ecosystem-factoring-adr]]'
  - '[[2026-02-22-mcp-consolidation-adr]]'
  - '[[2026-02-22-mcp-testing-adr]]'
  - '[[2026-03-05-cli-architecture-audit]]'
---

# `mcp-cli-interface` audit: `surface-alignment`

## Scope

Audit the current MCP and CLI interfaces for:

- surface compatibility
- logical consistency between layers
- terminology consistency across rules, docs, and exposed APIs
- conformance with the semantic intent of core `.vaultspec` rules
- documentation quality and freshness
- suitability for agentic usage
- existence and quality of test coverage
- absence of test shortcuts around these interfaces

This audit synthesizes parallel subagent reviews of:

- live CLI and MCP surface mapping
- terminology and documentation alignment
- test coverage and automation-boundary quality

## Findings

### High

- The documented root CLI topology does not match the live CLI topology.
  The live root router exposes `vault`, `rules`, `skills`, `agents`,
  `config`, `system`, `hooks`, plus top-level `sync-all`, `test`, `doctor`,
  `init`, and `readiness` in
  `src/vaultspec_core/cli.py`. The docs still advertise `vaultspec subagent`,
  `vaultspec team`, and `vaultspec mcp` as active root namespaces in
  `.vaultspec/docs/cli-reference.md`. This is hard interface drift, not minor
  wording drift.

- The documented MCP surface is not the implemented MCP surface.
  The current MCP server exposes vault/spec workspace tools only:
  `query_vault`, `feature_status`, `create_vault_document`,
  `list_spec_resources`, `get_spec_resource`, `workspace_status`, and
  `audit_vault` in `src/vaultspec_core/mcp_server/vault_tools.py`.
  The docs and concepts pages still describe an older orchestration-facing MCP
  with `list_agents`, `dispatch_agent`, `get_task_status`, `cancel_task`,
  team tools, and subagent dispatch semantics. The edge API and the published
  API are different products.

- `init` scaffolds `.mcp.json` against a route that the root CLI does not
  register.
  `src/vaultspec_core/core/commands.py` writes `["-m", "vaultspec_core", "mcp"]`, while `src/vaultspec_core/cli.py` does not register `mcp`.
  The router still contains a dead special-case branch for `mcp`, which
  strongly suggests incomplete refactor residue.

- Core framework semantics and edge documentation are no longer aligned on
  dispatch.
  The framework language in `.vaultspec/rules/system/framework.md` is now more
  abstract and environment-dependent, while surrounding docs and bootstrap
  material still present `vaultspec-subagent`, team dispatch, and MCP dispatch
  as concrete built-in runtime interfaces. Core rules remain semantically
  coherent at the methodology level, but docs and edge APIs are not compatible
  with that intent.

- The MCP server's real automation boundary is effectively untested.
  MCP tests cover tool behavior through in-memory connected sessions, but do
  not validate the actual stdio JSON-RPC entrypoint, stdout purity, stderr log
  isolation, workspace bootstrap behavior, or the server process contract in
  `src/vaultspec_core/mcp_server/app.py`. For agentic usage, that is the real
  boundary that matters.

### Medium

- CLI and MCP overlap only partially even where they target the same domain.
  `vault add` roughly maps to `create_vault_document`, but argument contracts
  differ. `vault audit` maps to `audit_vault`, but MCP exposes only a reduced
  subset. This means the layers are not interchangeable and do not form a
  coherent paired interface.

- Several CLI surfaces have no MCP equivalents, and several MCP surfaces have
  no CLI equivalents.
  CLI-only surfaces include `config/*`, `system/*`, `hooks/*`, `sync-all`,
  `test`, `init`, and others. MCP-only surfaces include `query_vault`,
  `feature_status`, and `workspace_status`. This may be intentional in part,
  but the hierarchy is not documented as an intentional split.

- Terminology is unstable across the topological layers.
  The repository mixes `sub-agents`, `agent personas`, `load persona`,
  `delegated`, `team`, `unified MCP server`, `vault create`, and `vault add`
  without a stabilized semantic map. The most immediate break is the doc use of
  `vaultspec vault create` while the implementation exposes `vault add`.

- Documentation paths and source references are stale.
  `.vaultspec/docs/cli-reference.md` still points readers at `src/vaultspec/`
  while the actual package is `src/vaultspec_core`. This increases friction for
  both humans and agents trying to verify behavior from source.

- Hook and concepts docs still teach stale execution paths.
  `.vaultspec/docs/hooks-guide.md` still describes `vaultspec subagent run`.
  `.vaultspec/docs/concepts.md` still teaches an orchestration product shape
  that is no longer exposed as first-class CLI/MCP API in this tree.

- CLI tests are broad but shallow.
  A meaningful portion of the CLI test suite validates help text, substring
  output, or direct handler dispatch rather than the full user-facing CLI
  contract. This weakens confidence in hierarchy correctness and automation
  reliability.

- Static MCP config tests appear drift-prone.
  Existing tests assert a hard-coded `mcp.json` contract that does not appear
  to validate the generated or current runtime-facing setup path.

### Low

- The inspected CLI/MCP interface tests did not surface widespread use of
  mocks, stubs, patches, `skip`, or `xfail` in these interface areas.
  The primary quality issue is boundary avoidance and shallow assertions rather
  than fake-heavy testing.

- The testing surface still contains weak signals such as placeholder coverage
  and minimal key-exists assertions, which reduce audit confidence even when
  they do not violate the anti-fake standard.

## Recommendations

- Decide and document the product boundary explicitly:
  either the project still exposes orchestration-first CLI/MCP interfaces, or
  it has intentionally narrowed to vault/spec-core interfaces. The docs,
  scaffolding, and router must reflect one model, not both.

- Repair the broken MCP bootstrap path first.
  `init` must scaffold a command that actually exists, or the root CLI must
  expose a real `mcp` route again. This is the highest-risk setup defect.

- Rewrite `.vaultspec/docs/cli-reference.md` against the live codebase.
  It currently contains the highest density of dead topology, stale verbs,
  stale source paths, and wrong MCP tool inventory.

- Rewrite `.vaultspec/docs/hooks-guide.md` and `.vaultspec/docs/concepts.md`
  after the topology decision is made. They currently propagate obsolete mental
  models and command examples.

- Stabilize the terminology model in one place.
  Define the canonical meaning of `agent persona`, `sub-agent`, `team`,
  `dispatch`, `vault add`, `vault audit`, and `MCP server`, then force docs and
  exposed APIs to follow that vocabulary.

- Add real automation-boundary tests for the MCP server.
  Validate server startup, stdio transport behavior, stdout/stderr discipline,
  and configuration/bootstrap correctness.

- Strengthen interface tests from contract level rather than handler level.
  Replace shallow CLI assertions and stale config-shape tests with end-to-end
  interface checks that validate real entrypoints and real command/tool
  semantics.

## Compatibility map

| CLI surface                                                   | MCP surface                                    | Status                                            |
| ------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------- |
| `vault add`                                                   | `create_vault_document`                        | Partial: same domain, different argument contract |
| `vault audit`                                                 | `audit_vault`                                  | Partial: MCP exposes reduced capability           |
| `readiness` + `doctor`                                        | `workspace_status`                             | Partial: related but not structurally equivalent  |
| `rules list/show`                                             | `list_spec_resources` / `get_spec_resource`    | Partial: naming hierarchy differs                 |
| `skills list/show`                                            | `list_spec_resources` / `get_spec_resource`    | Partial: naming hierarchy differs                 |
| `agents list/show`                                            | `list_spec_resources` / `get_spec_resource`    | Partial: naming hierarchy differs                 |
| `config/*`, `system/*`, `hooks/*`, `sync-all`, `test`, `init` | none                                           | No MCP bridge                                     |
| none                                                          | `query_vault`                                  | MCP-only                                          |
| none                                                          | `feature_status`                               | MCP-only                                          |
| documented `vaultspec mcp`                                    | actual `vaultspec-mcp` script / current router | Drifted                                           |
| documented `subagent` and `team` CLI                          | none in live root CLI                          | Drifted                                           |
| documented MCP agent/team tools                               | none in live MCP source                        | Drifted                                           |

## Priority docs to revise

- `.vaultspec/docs/cli-reference.md`
- `.vaultspec/docs/hooks-guide.md`
- `.vaultspec/docs/concepts.md`
- `.vaultspec/README.md`
- `.vaultspec/rules/system/framework.md`

## Addendum: runtime-docstring sweep confirmation

During the module-docstring sweep on 2026-03-11, the MCP bootstrap defect was
reconfirmed in live runtime code rather than only in stale documentation.

- `src/vaultspec_core/core/commands.py` still scaffolds `.mcp.json` with
  `["-m", "vaultspec_core", "mcp"]` in `init_run`.

- `src/vaultspec_core/cli.py` still does not register an `mcp` command on the
  root Typer application, even though `main()` retains a special-case branch
  for `ctx.invoked_subcommand == "mcp"`.

- `src/vaultspec_core/mcp_server/app.py` remains the actual MCP process
  entrypoint, which reinforces that the scaffolded root-CLI route and the live
  MCP runtime entry boundary are still out of alignment.

## Addendum: protocol-test integrity

During the remaining module-docstring sweep on 2026-03-11, the protocol test
surface was also checked for unreconciled non-documentation issues.

- `src/vaultspec_core/protocol/tests/test_providers.py` contains tautological
  API-parity checks that validate structure more than behavior, including
  `hasattr` checks, abstract-method presence checks, and signature-equality
  checks.

- These tests do not appear to rely on mocks or skips, but they still weaken
  confidence because they can pass while exercising little real provider
  behavior.

- This is a test-quality issue, not only a documentation issue, and should be
  addressed in a later repair pass if the project intends to enforce the
  non-tautological testing standard consistently.

## Addendum: verification-test semantics

During the same sweep, the verification layer exposed two additional
non-documentation issues that remain unresolved in code.

- `VerificationError` is named and exported like an exception, but the live
  API uses it as a record-like validation result rather than an `Exception`
  subtype. That creates semantic ambiguity in the verification surface.

- `src/vaultspec_core/verification/tests/test_verification.py` includes a test
  against a known-nonconformant fixture vault that only proves the call
  returns a list, not that a valid known directory actually passes
  verification.

These are not docstring problems. They should be handled as follow-up API and
test-integrity work.

## Addendum: vaultcore-hydration test drift

The vaultcore kernel test surface also contains an unreconciled test-to-code
contract mismatch.

- `src/vaultspec_core/vaultcore/tests/test_hydration.py` no longer matches the
  live `hydrate_template` signature in
  `src/vaultspec_core/vaultcore/hydration.py`.

- The tests expect placeholder and defaulting behavior that the current
  implementation does not provide, including `type` placeholder handling and
  feature/title defaults.

- The Researcher reported that a targeted run of the hydration test module
  fails all three tests, which indicates real drift rather than a purely
  documentary mismatch.

This should be treated as follow-up repair work in the vaultcore kernel, not
as a documentation issue.
