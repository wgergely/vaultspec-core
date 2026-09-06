# vaultspec-core CLI reference (bundled)

Machine-facing command reference for `vaultspec-core`, bundled into every consumer
project on install and seeded to `.vaultspec/reference/cli.md`. This is a
locally-resident lookup for AI agents: command inventory, options, argument
enumerations, exit codes, and environment variables. The human-facing prose reference is
`docs/CLI.md` in the source repository.

This reference serves two roles. It is the CLI-fallback command lookup for agents and
sessions where the vaultspec MCP server is not connected, resolving verbs, options, and
argument shapes from one local read. It is also the authoritative verb-existence source
the MCP `discover` and `invoke` gateway parses: the `vaultspec:generated`
command-inventory block below enumerates every leaf command the gateway will accept.

This file is a reference document, not a rule. It is not assembled into any provider
configuration.

## Entry points

| Command | Purpose | | ------------------------------------------------ |
--------------------------------------------------- | | `vaultspec-core` | Workspace
management, vault operations, sync. | | `vaultspec-mcp` | Console script launching the
stdio MCP server. | | `uv run --no-sync python -m vaultspec_core.mcp_server.app` |
Module invocation of the MCP server (Windows-safe, never syncs). |

## Global options

| Option | Short | Default | Description | | -------------- | ----- | ------- |
-------------------------------------------------- | | `--target DIR` | `-t` | cwd |
Target workspace directory. Overrides the env var. | | `--debug` | `-d` | off | Enable
DEBUG-level logging (top-level only). | | `--version` | `-V` | - | Print version and
exit (top-level only). | | `--help` | - | - | Show help for any command or group. |

`--target` is accepted by workspace commands and by every `vaultspec-core vault`,
`vaultspec-core spec`, and `vaultspec-core migrations` subcommand. `--json` is
command-specific.

## Command inventory

Every leaf-command signature, matching the live Typer usage lines. This block is
generator-owned: run `vaultspec-core spec reference generate` to refresh it. Do not
hand-edit between the markers.

<!-- vaultspec:generated:begin command-inventory -->

### Top-level commands

- `vaultspec-core install` - Install Vaultspec resources for the selected providers.
- `vaultspec-core uninstall` - Remove the vaultspec framework from the target directory.
- `vaultspec-core sync` - Sync rules, skills, agents, configs, system prompts, and MCPs.
- `vaultspec-core doctor` - Diagnose overall workspace and vault health.
- `vaultspec-core status` - Orient in a vaultspec vault: rollup, or a grounding trace
  for a target.

### Vault

- `vaultspec-core vault set-body` - Replace only the body prose of a document, keeping
  its frontmatter.
- `vaultspec-core vault set-frontmatter` - Edit selected frontmatter fields, keeping the
  body byte-for-byte.
- `vaultspec-core vault edit` - Set body and/or frontmatter in one atomic write (single
  round-trip).
- `vaultspec-core vault rename` - Rename a document's file and re-point incoming related
  references.
- `vaultspec-core vault add` - Create a new .vault/ document from a template.
- `vaultspec-core vault stats` - Show vault statistics and metrics.
- `vaultspec-core vault list` - List vault documents, optionally filtered by type.
- `vaultspec-core vault graph` - Render the vault document graph.
- `vaultspec-core vault repair` - Run the operator repair pipeline for vault content.

#### Feature

- `vaultspec-core vault feature list` - List all feature tags in the vault.
- `vaultspec-core vault feature index` - Generate or update feature index documents.
- `vaultspec-core vault feature archive` - Archive all documents for a feature tag.
- `vaultspec-core vault feature unarchive` - Restore all archived documents for a
  feature tag.
- `vaultspec-core vault feature rename` - Atomically rename a feature tag across every
  vault surface.

#### Check

- `vaultspec-core vault check all` - Run all vault health checks.
- `vaultspec-core vault check body-links` - Find wiki-links and markdown path links in
  document body text.
- `vaultspec-core vault check exec-mapping` - Pair ledger rows with plan Steps and flag
  closed Steps without evidence.
- `vaultspec-core vault check body-sections` - Check document bodies carry the sections
  their template mandates.
- `vaultspec-core vault check annotations` - Find generated template annotations in
  vault documents.
- `vaultspec-core vault check markdown` - Check and optionally fix markdown hygiene
  (whitespace, blank runs, newline).
- `vaultspec-core vault check placeholders` - Find unreplaced {...} template
  placeholders in document body prose.
- `vaultspec-core vault check dangling` - Find wiki-links in related: frontmatter that
  resolve to no document.
- `vaultspec-core vault check orphans` - Find documents with no incoming wiki-links.
- `vaultspec-core vault check frontmatter` - Validate document frontmatter against vault
  schema.
- `vaultspec-core vault check modified-stamp` - Validate and reconcile the modified
  recency stamp on every document.
- `vaultspec-core vault check links` - Check wiki-links follow Obsidian convention (no
  .md extension).
- `vaultspec-core vault check features` - Check feature tag completeness - missing doc
  types.
- `vaultspec-core vault check references` - Check for missing cross-references within
  features.
- `vaultspec-core vault check schema` - Enforce schema rules: ADRs must ref research,
  plans must ref ADRs.
- `vaultspec-core vault check adr-status` - Validate ADR status against the canonical
  taxonomy.
- `vaultspec-core vault check code-boundary` - Scan source files for references to the
  project's own vault records.
- `vaultspec-core vault check structure` - Check vault directory structure and filename
  conventions.
- `vaultspec-core vault check rename-integrity` - Check name/filename integrity for
  rules, skills, and agents.
- `vaultspec-core vault check encoding` - Surface .vault/ documents that are not valid
  UTF-8 (detection only).
- `vaultspec-core vault check feature-rename-integrity` - Surface exec folders whose
  feature disagrees with their records' tag.

#### Sanitize

- `vaultspec-core vault sanitize annotations` - Strip generated template annotations
  from vault documents.

#### Rule

- `vaultspec-core vault rule promote` - Promote an audit finding to a team-shared rule.

#### Adr

- `vaultspec-core vault adr supersede` - Supersede an old ADR with a new ADR.

#### Plan

- `vaultspec-core vault plan status` - Report plan health, structure, and completion.
- `vaultspec-core vault plan check` - Validate convention compliance; with `--fix`,
  apply autofixes.
- `vaultspec-core vault plan query` - Filter Step rows by container scope and
  open/closed predicate.
- `vaultspec-core vault plan step toggle` - Flip the Step's checkbox state.
- `vaultspec-core vault plan step check` - Mark the Step closed (idempotent).
- `vaultspec-core vault plan step uncheck` - Mark the Step open (idempotent).
- `vaultspec-core vault plan step add` - Append a new Step at the next-available
  canonical id.
- `vaultspec-core vault plan step insert` - Insert a Step at a named position relative
  to an existing anchor.
- `vaultspec-core vault plan step edit` - Edit the Step's action and / or scope without
  changing its identifier.
- `vaultspec-core vault plan step move` - Re-parent and / or re-position a Step per the
  move-flag precedence rule.
- `vaultspec-core vault plan step remove` - Remove a Step; its identifier is retired and
  never reused.
- `vaultspec-core vault plan phase add` - Append a new Phase at the next-available
  canonical id.
- `vaultspec-core vault plan phase insert` - Insert a Phase at a named position; parent
  Wave inferred from anchor.
- `vaultspec-core vault plan phase edit` - Edit the Phase's title and / or intent
  paragraph in place.
- `vaultspec-core vault plan phase move` - Re-parent and / or re-position a Phase.
- `vaultspec-core vault plan phase renumber` - Reassign a Phase's canonical id;
  descendant Step display paths recompute.
- `vaultspec-core vault plan phase remove` - Remove a Phase; descendant Step ids
  cascade-retire.
- `vaultspec-core vault plan wave add` - Append a new Wave at the next-available
  canonical id (L3+ only).
- `vaultspec-core vault plan wave insert` - Insert a Wave at a named position relative
  to an existing anchor.
- `vaultspec-core vault plan wave edit` - Edit the Wave's title and / or intent
  paragraph in place.
- `vaultspec-core vault plan wave move` - Re-position a Wave in document order.
- `vaultspec-core vault plan wave remove` - Remove a Wave; descendant Phase and Step ids
  cascade-retire.
- `vaultspec-core vault plan epic intent show` - Print the Epic intent paragraph (L4
  plans only).
- `vaultspec-core vault plan epic intent edit` - Replace the Epic intent paragraph (L4
  plans only).
- `vaultspec-core vault plan tier show` - Print the plan's declared tier.
- `vaultspec-core vault plan tier promote` - Promote the plan tier transitively (L1 ->
  ... -> L4).
- `vaultspec-core vault plan tier demote` - Demote the plan tier; refuses multi-child
  collapse without `--force`.
- `vaultspec-core vault plan trailer emit` - Print a well-formed commit-linkage trailer
  line.
- `vaultspec-core vault plan trailer validate` - Validate the commit-linkage trailers in
  a commit-message file.

#### Link

- `vaultspec-core vault link list` - List related: edges in the vault document graph.
- `vaultspec-core vault link add` - Add a related: edge from *src* to *dst*.
- `vaultspec-core vault link remove` - Remove a related: edge from *src* to *dst*.

#### Exec

- `vaultspec-core vault exec relink` - Relink one execution record to a live Step in its
  existing parent plan.
- `vaultspec-core vault exec retire` - Archive one record only when its current Step is
  retired by its parent plan.
- `vaultspec-core vault exec detach` - Remove a Step claim only when it resolves to
  neither a live nor retired Step.
- `vaultspec-core vault exec log` - Append a Step's rows to its plan's ledger.
- `vaultspec-core vault exec fold` - Fold a feature's per-Step execution records into
  its plan's ledger.

#### Archive

- `vaultspec-core vault archive documents` - Archive exactly the documents named in a
  UTF-8 manifest.
- `vaultspec-core vault archive restore` - Restore exactly the archived documents named
  in a UTF-8 manifest.

### Spec

- `vaultspec-core spec doctor` - Diagnose workspace health and report issues.

#### Rules

- `vaultspec-core spec rules list` - List all available rules.
- `vaultspec-core spec rules add` - Add a new custom rule source under .vaultspec/.
- `vaultspec-core spec rules show` - Display a rule's content.
- `vaultspec-core spec rules edit` - Open a rule in the configured editor.
- `vaultspec-core spec rules remove` - Delete a rule.
- `vaultspec-core spec rules rename` - Rename an existing rule atomically.
- `vaultspec-core spec rules sync` - Sync only rule files; use vaultspec-core sync for
  complete refresh.
- `vaultspec-core spec rules restore` - Restore a rule to its snapshotted original.
- `vaultspec-core spec rules status` - Report rules sync status against provider
  destinations.

#### Skills

- `vaultspec-core spec skills list` - List all available skills.
- `vaultspec-core spec skills add` - Add a new skill.
- `vaultspec-core spec skills show` - Display a skill's content.
- `vaultspec-core spec skills edit` - Open a skill in the configured editor.
- `vaultspec-core spec skills remove` - Delete a skill.
- `vaultspec-core spec skills rename` - Rename an existing skill atomically.
- `vaultspec-core spec skills sync` - Sync only skill files; use vaultspec-core sync for
  complete refresh.
- `vaultspec-core spec skills restore` - Restore a skill to its snapshotted original.
- `vaultspec-core spec skills status` - Report skills sync status against provider
  destinations.

#### Agents

- `vaultspec-core spec agents list` - List all available agents.
- `vaultspec-core spec agents add` - Add a new agent definition.
- `vaultspec-core spec agents show` - Display an agent's content.
- `vaultspec-core spec agents edit` - Open an agent in the configured editor.
- `vaultspec-core spec agents remove` - Delete an agent definition.
- `vaultspec-core spec agents rename` - Rename an existing agent definition atomically.
- `vaultspec-core spec agents sync` - Sync only agent files; use vaultspec-core sync for
  complete refresh.
- `vaultspec-core spec agents restore` - Restore an agent to its snapshotted original.
- `vaultspec-core spec agents status` - Report agents sync status against provider
  destinations.

#### System

- `vaultspec-core spec system show` - Display system prompt parts and targets.
- `vaultspec-core spec system sync` - Sync only system prompts; use vaultspec-core sync
  for complete refresh.

#### Hooks

- `vaultspec-core spec hooks list` - List all defined hooks.
- `vaultspec-core spec hooks add` - Add a new declarative hook under .vaultspec/.
- `vaultspec-core spec hooks show` - Display a hook's content.
- `vaultspec-core spec hooks edit` - Open a hook in the configured editor.
- `vaultspec-core spec hooks rename` - Rename an existing hook atomically.
- `vaultspec-core spec hooks remove` - Delete a hook.
- `vaultspec-core spec hooks restore` - Restore a hook to its snapshotted original (not
  supported for custom hooks).
- `vaultspec-core spec hooks sync` - Sync only hooks files; use vaultspec-core sync for
  complete refresh.
- `vaultspec-core spec hooks status` - Report declarative hooks parsing and taxonomy
  compliance status.
- `vaultspec-core spec hooks run` - Trigger hooks for a specific event.
- `vaultspec-core spec hooks trust` - Approve this workspace's hooks to run their shell
  commands as you.

#### Precommit

- `vaultspec-core spec precommit disable` - Decline vaultspec-managed
  .pre-commit-config.yaml scaffolding.
- `vaultspec-core spec precommit enable` - Restore vaultspec-managed
  .pre-commit-config.yaml scaffolding.
- `vaultspec-core spec precommit migrate` - Transplant the canonical vaultspec hooks
  into prek.toml.

#### Gitignore

- `vaultspec-core spec gitignore disable` - Decline the vaultspec-managed .gitignore
  block for the whole project.
- `vaultspec-core spec gitignore enable` - Restore the vaultspec-managed .gitignore
  block for the whole project.

#### Gitattributes

- `vaultspec-core spec gitattributes disable` - Decline the vaultspec-managed
  .gitattributes block for the whole project.
- `vaultspec-core spec gitattributes enable` - Restore the vaultspec-managed
  .gitattributes block for the whole project.

#### Mcps

- `vaultspec-core spec mcps list` - List canonical MCP server definitions.
- `vaultspec-core spec mcps status` - Inspect provider-native MCP enrollment status.
- `vaultspec-core spec mcps add` - Add or replace a canonical MCP server definition.
- `vaultspec-core spec mcps remove` - Remove a canonical MCP server definition.
- `vaultspec-core spec mcps sync` - Reconcile canonical definitions into provider-native
  enrollment.
- `vaultspec-core spec mcps uninstall` - Remove Vaultspec-owned provider-native MCP
  enrollment.

#### Reference

- `vaultspec-core spec reference generate` - Regenerate the generator-owned regions of
  the bundled CLI reference.

### Migrations

- `vaultspec-core migrations status` - Show registered migrations and which entries are
  pending.
- `vaultspec-core migrations run` - Run pending schema migrations and bump the manifest
  version.

### Config

- `vaultspec-core config get` - Read a local configuration value.
- `vaultspec-core config set` - Write a local configuration value.
- `vaultspec-core config unset` - Clear a local configuration entry.
- `vaultspec-core config list` - Enumerate all known configuration entries and current
  values.

<!-- vaultspec:generated:end command-inventory -->

## Workspace commands

### vaultspec-core install

Deploy the framework into the target directory.

`PROVIDER` (default `all`): `all`, `core`, `claude`, `gemini`, `antigravity`, `codex`.
`core` installs `.vaultspec/` only.

| Option | Default | Description | | ----------- | ------- |
---------------------------------------- | | `--upgrade` | off | Re-sync builtins
without re-scaffolding. | | `--dry-run` | off | Preview without writing. | | `--force` |
off | Overwrite an existing installation. | | `--skip` | `[]` | Skip a component
(repeatable). | | `--mode` | auto | Provisioning mode: `tool` (uvx), `dependency`
(project venv, ships in built distributions), or `dev` (default dev group, renders like
dependency but does not ship); auto-detected from pyproject.toml. | | `--json` | off |
Emit machine-readable output. |

### vaultspec-core uninstall

Remove the framework from the target directory.

`PROVIDER` (default `all`): `all`, `core`, `claude`, `gemini`, `antigravity`, `codex`.

| Option | Default | Description | | ---------------- | ------- |
---------------------------------- | | `--remove-vault` | off | Also remove `.vault/`. |
| `--dry-run` | off | Preview without deleting. | | `--force` | off | Required to
execute (destructive). | | `--skip` | `[]` | Skip a component (repeatable). | | `--json`
| off | Emit machine-readable output. |

### vaultspec-core sync

Authoritative complete sync from `.vaultspec/` to enrolled provider outputs.

`PROVIDER` (default `all`): `all`, `claude`, `gemini`, `antigravity`, `codex`. `core` is
not a valid sync target.

| Option | Default | Description | | ----------- | ------- |
--------------------------------------------------- | | `--dry-run` | off | Preview
changes without writing. | | `--force` | off | Prune stale files; overwrite
user-authored content. | | `--skip` | `[]` | Skip a component (repeatable). | | `--json`
| off | Emit machine-readable output. |

### vaultspec-core doctor

Diagnose overall workspace and vault health: runs `vaultspec-core spec doctor` and
`vaultspec-core vault check all` under one exit code. Options: `--target` / `-t`,
`--json`. Exit codes: `0` = all ok, `1` = warnings, `2` = errors.

### Sync output vocabulary

Sync-shaped results (`vaultspec-core install`, `vaultspec-core sync`,
`vaultspec-core spec <resource> sync`, `vaultspec-core migrations run`) share one
vocabulary: `created`, `updated`, `unchanged`, `removed`, `restored`, `skipped`,
`failed`. `unchanged` is a successful no-op, not a failure; `skipped` always carries a
reason worth reading; only `failed` stops the pipeline. With `--json`, the payload
declares schema `vaultspec.sync.v1` and the top-level `status` is the run's aggregate
outcome (`mixed` when items disagree).

## Vault commands

### vaultspec-core vault add

Create a `.vault/` document from a template.

`DOC_TYPE`: `adr`, `audit`, `plan`, `reference`, `research`. `exec` is refused:
execution is logged with `vaultspec-core vault exec log`.

| Option | Short | Default | Description | | --------------- | ----- | ------- |
-------------------------------------------------------------------- | | `--feature TAG`
| `-f` | None | Feature tag (kebab-case). | | `--date DATE` | - | today | Override date
(ISO 8601). | | `--title TITLE` | - | None | Document title. | | `--topic TOPIC` | - |
None | Narrative filename infix (kebab-case) producing
`{date}-{feature}-{topic}-{type}.md`; adr, audit, reference, and research only. | |
`--related DOC` | `-r` | None | Related document(s). Repeatable. | | `--tags TAG` | - |
None | Additional freeform tags. Repeatable. | | `--force` | - | off | Overwrite an
existing document. | | `--dry-run` | - | off | Preview without writing. | | `--json` | -
| off | Emit machine-readable output. | | `--no-hints` | - | off | Suppress next-step
advisory hints. | | `--tier TIER` | - | `L1` | Plan tier (`L1`..`L4`). Ignored for
non-plan document types. |

### vaultspec-core vault exec log

Append one Step's rows to its plan's ledger, the only execution artifact, creating the
ledger on first use. Append-only and idempotent; concurrent appends serialise on the
docs-domain lock and the managed `.gitattributes` block declares `merge=union` on
ledgers.

| Option           | Default | Description                                                                         |
| ---------------- | ------- | ----------------------------------------------------------------------------------- |
| `--feature TAG`  | None    | Feature tag, with or without `#`. Required.                                         |
| `--related STEM` | None    | Parent plan stem. Required.                                                         |
| `--step ID`      | None    | Canonical Step id or display path. Required.                                        |
| `--row SPEC`     | None    | `A:path`, `M:path`, `D:path`, or `R:old->new`; repeatable.                          |
| `--verify SPEC`  | None    | A check that ran, `<command>=pass` or `<command>=fail`; written as a `verify:` row. |
| `--by PERSONA`   | None    | The persona that closed the Step; written as a `by:` row.                           |
| `--note TEXT`    | None    | Exception note under the Step id in `## Notes`; repeatable.                         |
| `--dry-run`      | off     | Resolve the ledger without writing.                                                 |
| `--json`         | off     | Emit machine-readable output.                                                       |

### vaultspec-core vault edit

Set body and/or frontmatter in one atomic write, with one validation pass. At least one
edit must be supplied. Body channels: `--body-file PATH`, `--body-stdin`. Frontmatter
flags: `--date DATE`, `--tags TAG` (repeatable, replaces the list), `--related DOC` /
`-r` (repeatable, replaces the list). Also accepts `--expected-blob-hash OID` (refuse
the write unless the on-disk blob matches), `--check` / `--no-check` (conformance checks
before writing, default on), `--dry-run`, and `--json`.

### vaultspec-core vault set-body

Replace only the body prose, preserving the frontmatter block byte-for-byte and
refreshing `modified:`. Options: `--body-file PATH`, `--body-stdin`,
`--expected-blob-hash OID`, `--check` / `--no-check` (default on), `--dry-run`,
`--json`.

### vaultspec-core vault set-frontmatter

Edit selected frontmatter fields, preserving the body byte-for-byte. Only the fields
passed change; metadata is validated before writing and the write is refused on any
violation. Options: `--date DATE`, `--tags TAG` (repeatable, replaces the list),
`--related DOC` / `-r` (repeatable, replaces the list), `--expected-blob-hash OID`,
`--dry-run`, `--json`. There is no `--title`: the title is the body H1.

### vaultspec-core vault rename

`vaultspec-core vault rename [OPTIONS] REF` - rename one document's file and re-point
every incoming `related:` reference. Options: `--to STEM` (required, new
identity-bearing stem), `--expected-blob-hash OID`, `--check` / `--no-check` (default
on), `--dry-run`, `--json`. Use `vaultspec-core vault feature rename` to rename a whole
feature.

### vaultspec-core status

Signature: `vaultspec-core status [OPTIONS] [TARGET]`. Orient in a vaultspec vault:
rollup or a grounding trace for a target. This is the top-level zeroth move. Read-only -
it never writes and produces no artifact.

**Rollup mode** (no `TARGET`): reports plans in flight, each with a one-line overview
(tier, completed waves and phases, step completion, and the next open step); plans
recently completed; recent changes grouped by type with ledgers collapsed per feature;
active features; and vault totals. Advisory hints point at the targeted mode and at
`vaultspec-core spec doctor` for health checks.

**Targeted mode** (`TARGET` is a plan stem, plan path, or feature handle): renders the
grounding trace for that target - a plan-line header, then each step (display path,
checkbox state, a cursor on the next open step) mapped to its evidence: `ledger N rows`
plus the last `verify:` result, `no rows` for an open step without any, or `unlinked`
for a closed step without any; exec documents that reference the plan but name no step
are listed as unlinked records. Grounding documents are grouped by type beneath the step
list. A feature handle traces every plan under the feature. Advisory hints point at
`vaultspec-core vault graph` for full graph exploration and at
`vaultspec-core vault plan status` for deep single-plan validation.

`vaultspec-core status` is orientation, not auditing: it describes what exists without
judging conformance. Use `vaultspec-core vault check` to audit and
`vaultspec-core spec doctor` for framework health.

| Option | Short | Default | Description | | ---------------- | ----- | ------- |
------------------------------------------------- | | `--limit N` | - | `10` | Recently
modified documents to show, per type. | | `--since N` | - | None | Show documents
modified within the last N days. | | `--paths` | - | off | Show each referenced
document's path (targeted). | | `--verbose-exec` | - | off | List ledgers instead of
collapsing them per feature.| | `--json` | - | off | Emit machine-readable output. | |
`--no-hints` | - | off | Suppress next-step advisory hints. |

`--limit` and `--since` apply only in rollup mode; in targeted mode they are accepted
but have no effect. `--limit` and `--since` are mutually exclusive in rollup mode:
`--since` switches from last-N to a day-window query.

`--json` emits the versioned envelope with schema id `vaultspec.vault.status.v1` and
`unchanged` outcome semantics (status rollup is always a read-only, no-mutation
operation). The `data` payload carries `plans_in_flight`, `recent_documents`,
`active_features`, and `hints` under stable keys. Schema bumps follow the standard
version integer convention.

### vaultspec-core vault list

List vault documents. `DOC_TYPE` filters by type.

| Option | Short | Default | Description | | --------------- | ----- | ------- |
----------------------------- | | `--feature TAG` | `-f` | None | Filter by feature tag.
| | `--date DATE` | - | None | Filter by date. | | `--json` | - | off | Emit
machine-readable output. | | `--limit N` | - | 50 | Maximum documents to return. | |
`--offset N` | - | 0 | Documents to skip, for paging. |

### vaultspec-core vault stats

Show vault statistics and document counts.

| Option | Short | Default | Description | | --------------- | ----- | ------- |
--------------------------------------- | | `--feature TAG` | `-f` | None | Filter by
feature tag. | | `--date DATE` | - | None | Filter by date. | | `--type TYPE` | - | None
| Filter by document type. | | `--invalid` | - | off | Show only documents with invalid
links. | | `--orphaned` | - | off | Show only orphaned documents. | | `--json` | - | off
| Emit machine-readable output. |

### vaultspec-core vault graph

Signature: `vaultspec-core vault graph [OPTIONS]`. Hierarchical dependency tree grouped
by feature and type.

| Option | Short | Default | Description | | ------------------------ | ----- | -------
| ------------------------------------------------- | | `--feature TAG` | `-f` | None |
Scope to a single feature. | | `--json` | - | off | Output as networkx node-link JSON. |
| `--metrics` | `-m` | off | Show aggregate graph metrics. | | `--ascii` | - | off |
Render ASCII topology. | | `--body` | - | off | Include document body in JSON output. |
| `--node STEM` | - | None | Scope JSON to a node's local (ego) neighbourhood. | |
`--depth N` | - | 1 | Ego-graph radius in hops; only used with --node. | |
`--derived/--no-derived` | - | off | Include the derived relatedness edge set in JSON;
it is a computed similarity ranking, not vault state. | | `--derived-limit N` | - | None
| Maximum derived edges to return. | | `--derived-offset N` | - | 0 | Derived edges to
skip, for paging. | | `--ref REF` | - | None | Read the corpus from this git ref via the
object database, with no working-tree checkout. |

The `--json` payload (schema `vaultspec.vault.graph.v2`) carries typed weighted explicit
edges (`kind`, `multiplicity`, `weight`), node-size hints (`pagerank`, `in_degree`), and
a separate `derived_edges` array of implicit relatedness edges that is never mixed into
the canonical `edges` array. A missing `--node` stem fails with exit code 1 and a
`failed` envelope.

### vaultspec-core vault repair

Operator repair pipeline for `.vault/` content. Broader than
`vaultspec-core vault check all --fix`: owns generated index refresh, post-fix graph
rebuild, and final delta reporting.

| Option | Short | Default | Description | | ---------------------------- | ----- |
------- | --------------------------------------- | | `--dry-run` | - | off | Preview
repair actions without writing. | | `--include-index/--no-index` | - | on | Refresh
generated feature indexes. | | `--feature TAG` | `-f` | None | Scope repair and index
refresh. | | `--verbose` | `-v` | off | Show INFO-level diagnostics. | | `--json` | - |
off | Emit machine-readable payloads. |

Phases: `preflight`, `check`, `fix`, `index`, `postcheck`, `summary`.

### vaultspec-core vault sanitize annotations

Strip generated template annotations from `.vault/` documents.

| Option | Short | Default | Description | | --------------- | ----- | ------- |
----------------------------------- | | `--feature TAG` | `-f` | None | Sanitize
documents for one feature. | | `--dry-run` | - | off | Preview annotation removals. | |
`--verbose` | `-v` | off | Show stripped files. | | `--json` | - | off | Emit
machine-readable payloads. |

### vaultspec-core vault feature list

List feature tags in the vault.

| Option | Default | Description | | ------------- | ------- |
------------------------------------------ | | `--date DATE` | None | Filter by date. |
| `--orphaned` | off | Show only features with no incoming links. | | `--type TYPE` |
None | Filter by document type. | | `--stale-days N` | None | Show only features whose
latest activity is older than N days. | | `--json` | off | Emit machine-readable output.
| | `--limit N` | - | 50 | Maximum features to return. | | `--offset N` | - | 0 |
Features to skip, for paging. |

### vaultspec-core vault feature index

Generate or update `<feature>.index.md` files in `.vault/index/`.

| Option | Short | Default | Description | | --------------- | ----- | ------- |
-------------------------------------- | | `--feature TAG` | `-f` | None | Generate
index for a specific feature. | | `--json` | - | off | Emit machine-readable output. |

### vaultspec-core vault feature archive

`vaultspec-core vault feature archive [OPTIONS] FEATURE_TAG` - move all documents for a
feature tag to the archive. Options: `--dry-run` (preview planned changes), `--json`,
`--no-hints` (suppress next-step advisory hints).

### vaultspec-core vault feature unarchive

`vaultspec-core vault feature unarchive [OPTIONS] FEATURE_TAG` - restore all archived
documents for a feature tag. Options: `--dry-run` (preview planned changes), `--json`.
The `--no-hints` flag is not accepted here.

### vaultspec-core vault archive documents

`vaultspec-core vault archive documents [OPTIONS]` archives exactly the live documents
listed by `--manifest PATH`. The manifest is UTF-8, one repository-relative
`.vault/*.md` path per line. The command validates the entire manifest before moving
anything; `--dry-run` previews the destination paths and `--json` emits the standard
envelope.

### vaultspec-core vault archive restore

`vaultspec-core vault archive restore [OPTIONS]` is the inverse: it restores exactly the
archived documents listed by `--manifest PATH`, one repository-relative
`.vault/_archive/*.md` path per line. The whole manifest is validated before anything
moves. `--deduplicate-identical` drops an archived copy whose live counterpart is
byte-identical instead of failing on the collision, while differing contents are still
reported as conflicts; `--dry-run` previews the destination paths and `--json` emits the
standard envelope.

### vaultspec-core vault exec

`vaultspec-core vault exec relink` takes `--record PATH` and `--step STEP` to repair one
record's mapping to a live Step. `retire` takes `--record PATH` and archives it only
when its parent plan retired the claimed Step. `detach` takes `--record PATH` and
removes its Step claim only when the claim resolves to neither a live nor a retired
Step. `log` takes `--feature`, `--related`, `--step`, and a repeatable `--row`
(`A:path`, `M:path`, `D:path`, or `R:old->new`) to append one Step's mechanical rows to
its plan's append-only consolidated ledger, creating the ledger on first use. `fold`
takes `--feature` and migrates a `body-v1` corpus by folding a feature's per-Step
records into one ledger, recovering each record's Scope paths as `T` (touched) rows and
removing the folded records; it is destructive and refuses to write without `--force`.
Every verb accepts `--dry-run` and `--json`.

### vaultspec-core vault feature rename

`vaultspec-core vault feature rename [OPTIONS] OLD_FEATURE NEW_FEATURE` - atomically
rename a feature tag across filenames, the exec folder and its records, the `#feature`
tag, `related:` wiki-links, and the regenerated index. Body prose is never rewritten. A
reverse journal rolls the vault back if the apply phase fails. Options: `--dry-run`,
`--force` (merge into an existing target feature; per-file path collisions still
refuse), `--json`, `--no-hints`.

### vaultspec-core vault adr supersede

`vaultspec-core vault adr supersede [OPTIONS] OLD_ADR` - mark an ADR superseded by a
newer one. Options: `--by STEM` (the superseding ADR), `--dry-run`, `--json`.

### vaultspec-core vault rule promote

`vaultspec-core vault rule promote [OPTIONS]` - promote an audit finding to a
project-level rule. Options: `--from STEM` (audit to promote from, required),
`--as NAME` (kebab-case rule name, required), `--force`, `--dry-run`, `--json`.

### vaultspec-core vault link

`vaultspec-core vault link list [OPTIONS] [SRC]` lists `related:` edges; with `SRC` the
listing is scoped to that node's out-links and in-links. Options: `--feature TAG` /
`-f`, `--json`.

`vaultspec-core vault link add [OPTIONS] SRC DST` adds an edge from `SRC` to `DST`.
Refuses a dangling target unless `--force` is passed. Options: `--dry-run`, `--force`,
`--json`. Exits `0` when added or already present, `1` on resolution failure or dangling
refusal.

`vaultspec-core vault link remove [OPTIONS] SRC DST` removes an edge. A missing edge is
reported as unchanged, not an error. Options: `--dry-run`, `--json`.

### vaultspec-core vault check

Signature: `vaultspec-core vault check [OPTIONS] COMMAND [ARGS]...`. Run health checks
on `.vault/`. Exits `1` if errors are found.

Shared options: `--fix` (apply auto-fixes), `--feature TAG` / `-f` (limit to a feature),
`--verbose` / `-v` (INFO diagnostics).

Subcommands: `all`, `annotations`, `markdown`, `placeholders`, `body-links`, `dangling`,
`frontmatter`, `modified-stamp`, `links`, `orphans`, `features`, `references`, `schema`,
`structure`, `rename-integrity`. The `structure` subcommand does not support
`--feature`. The `rename-integrity` subcommand checks name/filename integrity for rules,
skills, and agents; `--fix` is filename-wins (rewrite the frontmatter name) and
`--fix-frontmatter-wins` is the inverse (rename the file). The `modified-stamp`
subcommand flags missing, unparseable, or stale `modified:` stamps; with `--fix` it
normalizes parsed values to canonical `yyyy-mm-dd` form. The `markdown` subcommand
checks markdown hygiene (trailing whitespace, blank-line runs, final newline) and
repairs it with `--fix`. The `placeholders` subcommand finds unreplaced `{...}` template
placeholders left in document body prose (detection only).

### vaultspec-core vault plan

Signature: `vaultspec-core vault plan [OPTIONS] COMMAND [ARGS]...`. Inspect and
manipulate plan documents. Every mutating operation goes through this surface; canonical
identifiers (`S##`, `P##`, `W##`) are append-only and gap-no-reuse.

Read commands: `status`, `check` (accepts `--fix`), `query` (accepts `--phase`,
`--wave`, `--open`, `--closed`).

Every mutating plan verb accepts `--dry-run` (preview changes without writing to disk)
and `--canonicalise` (strip unknown prose blocks during serialization; off by default,
so authored prose sections are preserved).

Step commands operate on `PATH STEP_ID`: `add`, `insert`, `edit`, `move`, `remove`,
`check`, `uncheck`, `toggle`. The `add` command requires `--action` and `--scope`, and
takes `--phase` (parent Phase id, required at `L2`+, omitted at `L1`). The `insert`
command takes `--before` / `--after`. The `edit` command takes `--action` and/or
`--scope`. The `move` command takes `--to-phase`, `--before`, `--after`.

Phase commands operate on `PATH PHASE_ID`: `add`, `insert`, `edit`, `move`, `renumber`,
`remove`. The `add` command requires `--title` and `--intent`, and takes `--wave`
(parent Wave id, `L3`+ only). The `edit` command takes `--title` and/or `--intent`. The
`move` command takes `--to-wave`, `--before`, `--after`. The `renumber` command takes
`--to`.

Wave commands operate on `PATH WAVE_ID`: `add`, `insert`, `edit`, `move`, `remove`. Same
flag shape as Phase minus the re-parent flag. Wave operations require tier `L3` or `L4`.

Epic intent (`L4` only): `epic intent show`, `epic intent edit`. The `intent edit`
command takes `--text`.

Tier commands: `tier show`, `tier promote`, `tier demote`. The `promote` command takes
`--phase-title`, `--phase-intent`, `--wave-title`, `--wave-intent`, `--epic-intent` for
synthesized containers. The `demote` command takes `--force`.

Trailer commands: `trailer emit` (takes exactly one of `--step` or `--feature`; prints a
well-formed `Vaultspec-Step` or `Vaultspec-Feature` commit-linkage trailer line),
`trailer validate MESSAGE_FILE` (reports malformed trailers in a commit-message file and
always exits `0`, so it is safe as an opt-in `commit-msg`-stage pre-commit hook). The
trailer convention is advisory enrichment only: absence or malformation never blocks a
commit or fails a core command.

## Spec commands

Signature: `vaultspec-core spec [OPTIONS] COMMAND [ARGS]...`. Framework resource
management.

### vaultspec-core spec doctor

Run diagnostic collectors across the framework, providers, builtins, `.gitignore`, vault
content, and configuration files.

| Option | Short | Default | Description | | ---------------- | ----- | ------- |
--------------------------- | | `--target DIR` | `-t` | cwd | Diagnose another
directory. | | `--json` | - | off | Emit the diagnosis as JSON. | | `--gate-errors` | -
| off | Fold the warning exit (1) to 0 so only errors (exit 2) fail; used by the
`spec-check` pre-commit hook so expected provider-mirror lag does not deadlock commits.
|

### vaultspec-core spec rules

The `vaultspec-core spec rules`, `vaultspec-core spec skills`, and
`vaultspec-core spec agents` groups share an identical CRUD subcommand shape:

| Subcommand | Signature | Description | | ---------- |
---------------------------------- | --------------------------------- | | `list` | - |
List all resources. | | `add` | `NAME [--force] [--dry-run]` | Create a resource. | |
`show` | `NAME` | Print resource content to stdout. | | `edit` | `NAME [--editor CMD]` |
Open in the resolved editor. | | `remove` | `NAME [--yes` / `-y` / `--force]` | Delete a
resource (prompts). | | `rename` | `OLD_NAME NEW_NAME` | Rename a resource. | | `sync` |
`[PROVIDER] [--dry-run] [--force]` | Resource-scoped sync. | | `restore` | `FILENAME` |
Restore to snapshotted original. |

Body-content flags on `add` vary by resource: `vaultspec-core spec rules add` takes
`--body TEXT`; `vaultspec-core spec skills add` takes `--description TEXT` and
`--template TEXT`; `vaultspec-core spec agents add` takes `--description TEXT`. All
three also accept `--from-file PATH`. `edit` accepts `--editor CMD` to override the
editor binary for one invocation; resolution order is `--editor`, project config,
`$VISUAL`, `$EDITOR` / `VAULTSPEC_EDITOR`, `vi`. `status` accepts `--json` and reports
the missing, drifted, and stale rows of a prune-enabled dry-run sync.

### vaultspec-core spec system

The `vaultspec-core spec system show` command displays system prompt parts and
generation targets. The `vaultspec-core spec system sync` command
(`[--dry-run] [--force]`) runs a resource-scoped system prompt sync.

### vaultspec-core spec hooks

The `vaultspec-core spec hooks list` command lists hooks with name, status, event, and
action count. The signature `vaultspec-core spec hooks run [OPTIONS] EVENT` triggers
enabled hooks; it takes `--path PATH`. Valid events: `vault.document.created`,
`config.synced`, `audit.completed`.

The group shares the resource CRUD shape (`list`, `add`, `show`, `edit`, `rename`,
`remove`, `restore`, `sync`, `status`) plus `run`. `vaultspec-core spec hooks add NAME`
takes `--event EVENT` (default `vault.document.created`) and `--command CMD` alongside
the shared `--body`, `--from-file`, `--force`, and `--dry-run` flags; `edit` takes
`--editor CMD`.

### vaultspec-core spec precommit

Manage the project's pre-commit integration. `vaultspec-core spec precommit disable`
records `hooks.pre_commit = false` in the committed `.vaultspec/workspace.json`, so no
later `install` or `sync` scaffolds `.pre-commit-config.yaml` and the managed
`.gitignore` block starts ignoring it; `enable` clears that declaration. Both are
idempotent, take `--json`, and leave any existing `.pre-commit-config.yaml` on disk.
`vaultspec-core spec precommit migrate` converts a legacy `.pre-commit-config.yaml` to
`prek.toml`, and takes `--remove-yaml` to delete the superseded YAML once the canonical
hooks are verifiably present in `prek.toml`, plus `--dry-run` and `--json`.

### vaultspec-core spec reference

`vaultspec-core spec reference generate` rewrites the generator-owned regions of this
reference and of the source-tree handbook from the live command tree. It takes `--check`
to render in memory and diff against the committed files, exiting non-zero on mismatch
without writing, plus `--json`.

### vaultspec-core spec mcps

Signature: `vaultspec-core spec mcps [OPTIONS] COMMAND [ARGS]...`. Manage canonical
definitions in `.vaultspec/mcps/*.json` and reconcile them into provider-native
enrollment. Providers are `all`, `claude`, `antigravity`, and `codex`; scopes are
`project`, `local`, and `user`. Unsupported provider/scope combinations fail.

| Subcommand  | Signature                                                                             | Description                                                         |
| ----------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `list`      | -                                                                                     | List canonical MCP server definitions.                              |
| `status`    | `[PROVIDER] [--scope SCOPE] [--json] [--target PATH]`                                 | Inspect configuration and ownership state; does not probe runtimes. |
| `add`       | `--name NAME [--config JSON] [--force]`                                               | Add or replace a canonical definition.                              |
| `remove`    | `NAME [--force]`                                                                      | Remove a canonical definition.                                      |
| `sync`      | `[PROVIDER] [--scope SCOPE] [--dry-run] [--force] [--prune] [--json] [--target PATH]` | Reconcile canonical definitions into native enrollment.             |
| `uninstall` | `[PROVIDER] [--scope SCOPE] [--dry-run] [--force] [--json] [--target PATH]`           | Remove only Vaultspec-owned native enrollment.                      |

The default provider is `all` and the default scope is `project`.
`vaultspec-core spec mcps sync --force` adopts or replaces a same-name external entry;
`vaultspec-core spec mcps sync --prune` removes owned enrollment whose canonical source
was deleted. `uninstall` preserves canonical definitions and external host entries.

## Migration commands

Signature: `vaultspec-core migrations [OPTIONS] COMMAND [ARGS]...`. Schema migration
registry. Both subcommands accept `--target` / `-t` and `--json`.

The `vaultspec-core migrations status` command lists registered migrations and pending
entries; it is read-only.

The `vaultspec-core migrations run` command applies every pending migration in version
order and bumps the manifest version.

## Exit codes

| Command | Codes | | ---------------------------------- |
------------------------------------------------------ | | `vaultspec-core vault check`
| `0` clean, `1` errors found. | | `vaultspec-core vault plan check` | `0` clean, `1` at
least one ERROR-severity finding. | | `vaultspec-core spec doctor` | `0` all ok, `1`
warnings, `2` errors (`--gate-errors` folds `1` to `0`). | |
`vaultspec-core spec mcps status` | `0` config status ok, `1` otherwise. | |
`vaultspec-core migrations status` | `0` up to date or no manifest, `1` migrations
pending. | | `vaultspec-core migrations run` | `0` success (including no-op), `1` a
migration failed. |

## Environment variables

All prefixed `VAULTSPEC_`. Env vars override defaults but are overridden by `--target`.

| Variable | Type | Default | Description | | --------------------------------- | ---- |
------------ | ------------------------------------ | | `VAULTSPEC_TARGET_DIR` | path |
cwd | Root workspace directory. | | `VAULTSPEC_DOCS_DIR` | str | `.vault` | Vault
directory name. | | `VAULTSPEC_FRAMEWORK_DIR` | str | `.vaultspec` | Framework directory
name. | | `VAULTSPEC_CLAUDE_DIR` | str | `.claude` | Claude tool directory name. | |
`VAULTSPEC_GEMINI_DIR` | str | `.gemini` | Gemini tool directory name. | |
`VAULTSPEC_ANTIGRAVITY_DIR` | str | `.agents` | Antigravity directory name. | |
`VAULTSPEC_IO_BUFFER_SIZE` | int | `8192` | I/O read buffer size in bytes. | |
`VAULTSPEC_TERMINAL_OUTPUT_LIMIT` | int | `1000000` | Subprocess stdout capture limit. |
| `VAULTSPEC_LOG_LEVEL` | str | `INFO` | Root log level for the CLI. | |
`VAULTSPEC_EDITOR` | str | `zed -w` | Editor command for resource editing. | |
`VAULTSPEC_STDIO_WATCHDOG` | str | on | MCP server lifetime watchdog;
`0`/`false`/`off`/`no` disables it (EOF-only exit). |
