---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#audit"
  - "#mcp-cli-interface"
date: "2026-03-17"
related:
  - "[[2026-03-11-mcp-cli-interface-audit]]"
  - "[[2026-02-22-mcp-consolidation-adr]]"
  - "[[2026-02-22-mcp-testing-adr]]"
  - "[[2026-03-05-cli-architecture-audit]]"
---

# `mcp-cli-interface` audit: `domain-alignment`

## Scope

Audit the current MCP tool surface against the refactored Python CLI to:

- Map the full MCP command interface as a matrix
- Identify scope violations (dev commands, namespace pollution)
- Verify alignment with the CLI domain/subdomain hierarchy
- Propose a domain-aligned MCP redesign that mirrors the CLI

This audit follows the 2026-03-11 surface-alignment audit and reflects
the completed CLI refactor into `root.py`, `spec_cmd.py`, `vault_cmd.py`.

## Current MCP Tool Surface (7 tools)

| # | Tool Name | Domain | Params |
|---|-----------|--------|--------|
| 1 | `query_vault` | vault | `query?`, `feature?`, `type?`, `related_to?`, `recent?`, `limit?` |
| 2 | `feature_status` | vault | `feature` |
| 3 | `create_vault_document` | vault | `type`, `feature`, `title`, `extra_context?` |
| 4 | `list_spec_resources` | spec | `resource` (rules/skills/agents) |
| 5 | `get_spec_resource` | spec | `resource`, `name` |
| 6 | `workspace_status` | vault | (none) |
| 7 | `audit_vault` | vault | `summary?`, `verify?`, `fix?` |

## CLI \u2192 MCP Alignment Matrix

### Root Domain (Lifecycle)

| CLI Command | MCP Tool | Status |
|---|---|---|
| `install [provider]` | -- | No MCP (correct: lifecycle) |
| `uninstall [provider]` | -- | No MCP (correct: destructive) |
| `sync [provider]` | -- | No MCP (debatable) |

### Spec Domain (Framework Resources)

| CLI Command | MCP Tool | Status |
|---|---|---|
| `spec rules list` | `list_spec_resources("rules")` | Partial: domain collapsed |
| `spec rules show <name>` | `get_spec_resource("rules", name)` | Partial: domain collapsed |
| `spec rules add` | -- | No MCP |
| `spec rules edit` | -- | No MCP (correct: interactive) |
| `spec rules remove` | -- | No MCP (correct: destructive) |
| `spec rules rename` | -- | No MCP |
| `spec rules sync` | -- | No MCP |
| `spec rules revert` | -- | No MCP |
| `spec skills list` | `list_spec_resources("skills")` | Partial: domain collapsed |
| `spec skills show <name>` | `get_spec_resource("skills", name)` | Partial: domain collapsed |
| `spec skills add/edit/remove/rename/sync/revert` | -- | No MCP |
| `spec agents list` | `list_spec_resources("agents")` | Partial: domain collapsed |
| `spec agents show <name>` | `get_spec_resource("agents", name)` | Partial: domain collapsed |
| `spec agents add/edit/remove/rename/sync/revert` | -- | No MCP |
| `spec system show` | -- | No MCP (gap) |
| `spec system sync` | -- | No MCP |
| `spec hooks list` | -- | No MCP (gap) |
| `spec hooks run <event>` | -- | No MCP |

### Vault Domain (Documentation)

| CLI Command | MCP Tool | Status |
|---|---|---|
| `vault add <type>` | `create_vault_document` | Partial: different arg contract |
| `vault list [type]` | `query_vault(type=...)` | Partial: overloaded into query |
| `vault stats` | `audit_vault(summary=True)` | Partial: buried in multi-tool |
| `vault doctor` | `workspace_status` | Partial: different return shape |
| `vault graph` | -- | No MCP (gap) |
| `vault feature list` | -- | No MCP (gap) |
| `vault feature archive` | -- | No MCP (correct: destructive) |
| `vault check all` | `workspace_status` | Partial |
| `vault check <name>` | -- | No MCP (covered by doctor) |
| -- | `query_vault` | MCP-only (text search, recent, related) |
| -- | `feature_status` | MCP-only (lifecycle derivation) |

## Findings

### High

- **Flat namespace**: All 7 tools sit at root level with no domain prefix.
  An LLM agent sees `query_vault`, `list_spec_resources`, `workspace_status`
  as unrelated operations. The CLI cleanly separates `vault.*` and `spec.*`;
  the MCP does not mirror this.

- **`audit_vault` conflates three operations**: `summary` (stats), `verify`
  (health checks), and `fix` (auto-repair) are three boolean flags on one
  tool. The CLI keeps `vault stats`, `vault check all`, and
  `vault check all --fix` as distinct commands. Overloaded tools increase
  cognitive load for agents and humans.

- **`workspace_status` duplicates `audit_vault(verify=True)`**: Both call
  `run_all_checks()` and return diagnostics. Two tools doing the same thing
  in a 7-tool surface is 14% redundancy.

- **`list_spec_resources` / `get_spec_resource` collapse 3 domains**: CLI
  separates rules, skills, and agents into distinct sub-apps. MCP collapses
  them behind a `resource` discriminator, breaking discoverability.

### Medium

- **Missing `vault graph` in MCP**: The graph JSON export is the most
  valuable agentic introspection tool. An agent cannot understand feature
  relationships without it.

- **Missing `vault feature list`**: `feature_status` only works for a single
  known feature. An agent cannot discover which features exist.

- **Missing `spec system show`**: An agent cannot inspect the assembled
  system prompt parts.

- **Arg contract drift**: `vault add` uses `--feature/-f` (named option);
  `create_vault_document` uses `feature` (positional). This prevents agents
  from learning one interface and applying it to the other.

### Low

- **No dev commands in MCP**: Confirmed. No just/dev surface leaked.
  This is correct and should be maintained.

- **MCP-only tools are intentional**: `query_vault` (text search) and
  `feature_status` (lifecycle) have no CLI equivalents. These are
  agent-oriented read operations that don't need CLI form.

## Proposed Redesign

### Design Principles

1. **Domain-prefixed names**: `vault_*`, `spec_*` — no root-level generics
2. **1:1 CLI parity**: same arg names, same semantics where possible
3. **Single-purpose tools**: each tool does one thing
4. **Prod-only**: no dev/build/test commands
5. **Read-heavy surface**: predominantly read/query; writes limited to `vault_add`
6. **No redundancy**: no duplicate tools for the same operation

### Vault Domain Tools

| Tool | CLI Equivalent | Args |
|---|---|---|
| `vault_add` | `vault add` | `type`, `feature`, `title`, `date?`, `extra_context?` |
| `vault_list` | `vault list` | `type?`, `feature?`, `date?` |
| `vault_query` | MCP-only | `query?`, `feature?`, `type?`, `related_to?`, `recent?`, `limit?` |
| `vault_stats` | `vault stats` | `feature?`, `type?` |
| `vault_doctor` | `vault doctor` + `vault check all` | `feature?`, `fix?` |
| `vault_graph` | `vault graph --json` | `feature?`, `metrics?`, `include_body?` |
| `vault_feature_list` | `vault feature list` | `date?`, `type?`, `orphaned?` |
| `vault_feature_status` | MCP-only | `feature` |

### Spec Domain Tools

| Tool | CLI Equivalent | Args |
|---|---|---|
| `spec_rules_list` | `spec rules list` | (none) |
| `spec_rules_show` | `spec rules show` | `name` |
| `spec_skills_list` | `spec skills list` | (none) |
| `spec_skills_show` | `spec skills show` | `name` |
| `spec_agents_list` | `spec agents list` | (none) |
| `spec_agents_show` | `spec agents show` | `name` |
| `spec_system_show` | `spec system show` | (none) |

### Migration Map

| Current Tool | Action |
|---|---|
| `query_vault` | Rename \u2192 `vault_query` |
| `feature_status` | Rename \u2192 `vault_feature_status` |
| `create_vault_document` | Rename \u2192 `vault_add` |
| `list_spec_resources` | Split \u2192 `spec_rules_list`, `spec_skills_list`, `spec_agents_list` |
| `get_spec_resource` | Split \u2192 `spec_rules_show`, `spec_skills_show`, `spec_agents_show` |
| `audit_vault` | Split \u2192 `vault_stats` + `vault_doctor` |
| `workspace_status` | Merge into `vault_doctor` (remove) |

### Intentionally Excluded from MCP

| CLI Command | Reason |
|---|---|
| `install` / `uninstall` | Lifecycle — human-initiated only |
| `sync` | Side-effectful rebuild — human-initiated |
| `spec * edit` | Interactive editor — requires TTY |
| `spec * remove` | Destructive — requires confirmation |
| `spec * add` | Authoring — debatable, defer to v2 |
| `spec * rename` | Refactoring — debatable, defer to v2 |
| `spec * revert` | Undo — debatable, defer to v2 |
| `vault feature archive` | Destructive — human confirmation |
| `vault check <specific>` | Granular checks covered by `vault_doctor` |
| `spec hooks *` | Runtime hooks — human-initiated |
| All `just dev *` | Dev-only, not prod surface |

### Tool Count

- **Current**: 7 tools (flat, overloaded, some redundant)
- **Proposed**: 15 tools (domain-grouped, single-purpose, no redundancy)
- **Net effect**: More tools but each is simpler and mirrors CLI hierarchy

## Implementation Priority

1. **Rename + domain-prefix** existing tools (non-breaking with deprecation)
2. **Split** `audit_vault` into `vault_stats` + `vault_doctor`
3. **Remove** `workspace_status` (absorbed by `vault_doctor`)
4. **Split** `list_spec_resources` / `get_spec_resource` into per-domain tools
5. **Add** `vault_graph`, `vault_feature_list`, `spec_system_show`
6. **Align** arg contracts with CLI (named params, same names)
