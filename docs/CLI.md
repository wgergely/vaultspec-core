# vaultspec-core CLI reference

Complete command-line interface (CLI) reference for `vaultspec-core`. See the
[framework manual](./framework.md) for workflows and concepts.

## Contents

- [Entry points](#entry-points) - invoking the CLI and the MCP server.
- [Global options](#global-options) - flags accepted across commands.
- [Outcome vocabulary](#outcome-vocabulary) - the words and glyphs that report results.
- [JSON output envelope](#json-output-envelope) - the shape of `--json` output.
- [Command index](#command-index) - every command, grouped, with a one-line summary.
- [Workspace commands](#workspace-commands) - install, uninstall, and sync.
- [Vault commands](#vault-commands) - create, query, and edit vault documents and plans.
- [Spec commands](#spec-commands) - manage rules, skills, agents, hooks, MCPs, and the
  system prompt.
- [Migration commands](#migration-commands) - inspect and run schema migrations.
- [Config commands](#config-commands) - read and write local project settings.
- [Environment variables](#environment-variables) - the `VAULTSPEC_` settings.

## Entry points

- `vaultspec-core` - Workspace management, vault operations, resource sync.
- `vaultspec-mcp` - Console script that launches the stdio Model Context Protocol (MCP)
  server.
- `uv run --no-sync python -m vaultspec_core.mcp_server.app` - Module invocation of the
  MCP server (avoids binary locking on Windows; `--no-sync` keeps a client connect from
  mutating the environment). See [MCP reference](./MCP.md).

## Global options

These options apply at the top level unless noted. `--debug` and `--version` are
top-level only. `--target` is accepted by target-aware workspace commands,
`vaultspec-core vault ...`, `vaultspec-core spec ...`, and
`vaultspec-core migrations ...`. `--json` is command-specific and appears only on
commands that support JavaScript Object Notation (JSON) output.

- `--target DIR` (`-t`, default cwd) - Target workspace directory. Overrides
  `VAULTSPEC_TARGET_DIR`. Defaults to the current working directory if neither is set.
- `--debug` (`-d`, default off) - Enable DEBUG-level logging (top-level flag).
- `--version` (`-V`) - Print version and exit (top-level flag).

## Outcome vocabulary

Commands that change files report what happened to each one with the same set of words,
so results read the same no matter which command ran. The sync-style commands -
`vaultspec-core install`, `vaultspec-core sync`, the
`vaultspec-core spec <resource> sync` commands, and `vaultspec-core migrations run` -
print one line per file, each marked with its glyph, then a count of each outcome. With
`--json`, those per-file outcomes appear under `data.items`, and the envelope's
top-level `status` is the outcome for the whole run.

- `created` (`+`) - A new file or directory was written.
- `updated` (`~`) - An existing file was changed.
- `unchanged` (`=`) - The file already matched its source, so nothing was written.
- `removed` (`-`) - An existing file was deleted.
- `restored` (`*`) - A file was reset to its original version.
- `skipped` (`s`) - A file was left untouched because a rule or precondition excluded
  it; the reason is always reported.
- `failed` (`x`) - A write was attempted and failed.

A `--json` `status` of `mixed` means one run produced more than one outcome. `unchanged`
is a successful no-op, not a failure. Only `failed` stops a pipeline.

## JSON output envelope

Every command that accepts `--json` emits one uniform envelope, so a consumer parses one
shape regardless of which command produced it:

```json
{
  "schema": "vaultspec.<command>.v1",
  "status": "<outcome word>",
  "data": { },
  "hints": { }
}
```

- `schema` (required) - Namespaced identifier of the command plus a monotonic version
  integer.
- `status` (required) - The canonical outcome word for the whole invocation (one of the
  seven words above, or `mixed`).
- `data` (required) - The command-specific payload. Read-only commands report their
  content here under stable keys.
- `hints` (optional) - Structured next-step guidance. Absent when no hint applies; its
  presence never changes `status`.

The `schema` value follows the convention `vaultspec.<dotted-command-path>.v1` - for
example `vaultspec.sync.v1`, `vaultspec.vault.stats.v1`, or
`vaultspec.spec.rules.add.v1`. Every schema is at version `v1` except
`vaultspec.vault.graph.v2`, documented with `vaultspec-core vault graph` below. Adding
new keys under `data` is additive and does not bump the version; renaming or removing a
key bumps the integer (`v2`, ...). Schema bumps are recorded in the release notes.

Failures under `--json` emit the same envelope with the fixed schema
`vaultspec.error.v1` and `status` set to `failed`; `data.message` carries the
human-readable reason and `data.hint` carries remediation guidance when one is
available. A `status` of `failed` always pairs with a non-zero exit code.

Under `--json`, stdout contains only the envelope; diagnostics go to stderr. Output is
compact by default. For indentation, see
[environment variables](#environment-variables). Use the top-level `status` field to
check success.

## Command index

Every `vaultspec-core` command with its arguments. Run any command with `--help` for its
full options.

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

### install

```bash
vaultspec-core install [OPTIONS] [PROVIDER]
```

Deploy the vaultspec framework into the target directory.

#### Arguments

- `PROVIDER` (default `all`) - `all`, `core`, `claude`, `gemini`, `antigravity`,
  `codex`.

#### Options

- `--upgrade` (default off) - Re-sync builtins without re-scaffolding.
- `--dry-run` (default off) - Preview without writing.
- `--force` (default off) - Overwrite existing installation.
- `--skip` (default `[]`) - Skip specific sync passes (repeatable).
- `--mode` (default auto) - Select generated hook and MCP launchers: `tool` uses `uvx`;
  `dependency` and `dev` use `uv run --no-sync`. Selection order: explicit `--mode`,
  saved mode in `.vaultspec/workspace.json`, dependency detection in `pyproject.toml`,
  then `tool`. This option doesn't change package dependency declarations.
- `--no-hints` (default off) - Suppress next-step advisory hints.
- `--json` (default off) - Emit machine-readable output.

`core` installs `.vaultspec/` only, without any provider config.

#### Examples

- **Install the framework for all supported provider layers in the current directory**:

  ```bash
  vaultspec-core install all
  ```

______________________________________________________________________

### uninstall

```bash
vaultspec-core uninstall [OPTIONS] [PROVIDER]
```

Remove the vaultspec framework from the target directory.

#### Arguments

- `PROVIDER` (default `all`) - `all`, `core`, `claude`, `gemini`, `antigravity`,
  `codex`.

#### Options

- `--remove-vault` (default off) - Also remove `.vault/`.
- `--dry-run` (default off) - Preview without deleting.
- `--force` (default off) - Required to execute (uninstall is destructive).
- `--skip` (default `[]`) - Skip specific removal passes (repeatable).
- `--json` (default off) - Emit machine-readable output.

`.vault/` is preserved by default. `--remove-vault` deletes it; commit or back up its
records first.

#### Examples

- **Preview removal while keeping feature records**:

  ```bash
  vaultspec-core uninstall all --dry-run
  ```

- **After reviewing the preview, remove the harness and keep feature records**:

  ```bash
  vaultspec-core uninstall all --force
  ```

______________________________________________________________________

### sync

```bash
vaultspec-core sync [OPTIONS] [PROVIDER]
```

Authoritative complete sync from `.vaultspec/` to enrolled provider outputs: rules,
skills, agents, system prompts, provider config stubs, and MCP entries. After editing or
adding framework source files, this is the normal propagation command.

#### Arguments

- `PROVIDER` (default `all`) - `all`, `claude`, `gemini`, `antigravity`, `codex`.

`core` is not a valid sync target because sync reads from `.vaultspec/`. Use
`vaultspec-core install --upgrade` or `vaultspec-core install --force` for
framework/provider scaffolding repair, not as the normal propagation path after source
edits.

#### Options

- `--dry-run` (default off) - Preview changes without writing.
- `--force` (default off) - Prune stale files and overwrite user-authored content.
- `--skip` (default `[]`) - Skip specific sync passes (repeatable).
- `--json` (default off) - Emit machine-readable output.

#### Examples

- **Synchronize modified rule and agent source files to all provider workspaces**:

  ```bash
  vaultspec-core sync all
  ```

______________________________________________________________________

### doctor

```bash
vaultspec-core doctor [OPTIONS]
```

Diagnose overall workspace and vault health. This is the single health command: it runs
the workspace diagnosis of `vaultspec-core spec doctor` and the full vault sweep of
`vaultspec-core vault check all`, then reports both under one exit code. Reach for it
when you want a yes-or-no answer about the whole project; reach for the two narrower
commands when you already know which half you are investigating.

#### Options

- `--target DIR` (`-t`, default cwd) - Diagnose a directory other than the current one.
- `--json` (default off) - Output as JSON.

Exit codes: `0` = all ok, `1` = warnings, `2` = errors.

Not every line the diagnosis prints is weighed. The tool-server configuration line, the
process registry, and stale package seeds are reported for your attention and do not
raise the code, so a run can print `warn` and still exit `0`. Do not infer failure from
the word `warn` in the output: read the exit code, or read `status` under `--json`. The
conditions that do raise it are the framework layout, the provider directories, the
builtins, `.gitignore` and `.gitattributes`, migrations, the pre-commit hooks, rename
integrity, vault content, and an install-mode or version-floor mismatch on any declared
package.

#### Examples

- **Check the health of the whole project, framework and vault together**:

  ```bash
  vaultspec-core doctor
  ```

- **Diagnose another checkout and capture the result for a script**:

  ```bash
  vaultspec-core doctor --target ../other-project --json
  ```

## Vault commands

Group command: `vaultspec-core vault [OPTIONS] COMMAND [ARGS]...`

### vaultspec-core vault add

```bash
vaultspec-core vault add [OPTIONS] DOC_TYPE
```

Create a new `.vault/` document from a template.

#### Arguments

- `DOC_TYPE` - `adr`, `audit`, `exec`, `plan`, `reference`, `research`.

#### Options

- `--feature TAG` (`-f`) - Feature tag (kebab-case, lowercase letters, digits, hyphens).
  Required.
- `--date DATE` (default today) - Override date (ISO 8601, e.g., YYYY-MM-DD).
- `--title TITLE` - Document title.
- `--topic TOPIC` - Kebab-case filename infix that distinguishes a second document of
  the same type for one feature, producing `{date}-{feature}-{topic}-{type}.md`. Only
  valid for `adr`, `audit`, `reference`, and `research`.
- `--related DOC` (`-r`) - Related document(s). Accepts path, filename, stem, or
  `[[wiki-link]]`. Repeatable.
- `--tags TAG` - Accepts only the document's required directory and feature tags.
  Repeatable; duplicates are ignored. Other tags are rejected before writing, including
  with `--force` or `--dry-run`. Omit this option for ordinary creation.
- `--force` (default off) - Overwrite an existing document at the resolved path.
- `--dry-run` (default off) - Preview without writing files.
- `--json` (default off) - Emit machine-readable JSON output in standard envelope.
- `--tier TIER` (default L1) - Plan tier (`L1`, `L2`, `L3`, `L4`). Ignored for non-plan
  types.
- `--no-hints` (default off) - Suppress next-step advisory hints.

`exec` is not a scaffold type. `vaultspec-core vault add exec` exits 1 with the message
"execution is logged with vault exec log"; the ledger is the only execution artifact and
`vaultspec-core vault exec log` its only writer.

______________________________________________________________________

### vaultspec-core vault edit

```bash
vaultspec-core vault edit [OPTIONS] REF
```

Set body and/or frontmatter in one atomic write. This is the primary editing surface for
a scaffolded document: the body channel (`--body-file` or `--body-stdin`) and the
frontmatter flags are applied together in a single write with a single validation pass,
so a document never lands on disk with new prose and stale metadata. At least one edit -
a body channel or a frontmatter flag - must be supplied.

`--expected-blob-hash` requires the full 40-character hash of the document version you
reviewed. Compute it with `git hash-object --no-filters <document-path>`. The write is
refused if the file's raw bytes have changed. After a conflict, reread the document
before computing a new hash.

#### Arguments

- `REF` - Document to edit. Accepts stem, filename, path, or `[[wiki-link]]`. Required.

#### Options

- `--body-file FILE` - Read the new body text from this file.
- `--body-stdin` (default off) - Read the new body text from stdin.
- `--date DATE` - Set the date field (`YYYY-MM-DD`).
- `--tags TAG` - Set the tags list. Repeatable; replaces the whole list.
- `--related DOC` (`-r`) - Set the related list. Repeatable; replaces the whole list.
  Each input is resolved to `[[wiki-link]]` form.
- `--expected-blob-hash HASH` - Refuse the write unless the on-disk blob OID matches.
- `--check` / `--no-check` (default `--check`) - Run conformance checks before writing.
- `--dry-run` (default off) - Preview without writing.
- `--json` (default off) - Output as JSON.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **Replace a document's prose and relink it in one write**:

  ```bash
  vaultspec-core vault edit 2026-05-17-test-feature-research --body-file draft.md --related 2026-05-17-test-feature-adr
  ```

- **Pipe generated prose in and preview the result before committing to it**:

  ```bash
  cat draft.md | vaultspec-core vault edit 2026-05-17-test-feature-research --body-stdin --dry-run
  ```

______________________________________________________________________

### vaultspec-core vault set-body

```bash
vaultspec-core vault set-body [OPTIONS] REF
```

Replace a document's body prose and update `modified` and `body_hash`. With `--check`
(the default), the proposed content is validated first and the write is refused if any
diagnostic is an error.

Use this when the metadata is already right and you only want to swap the prose; use
`vaultspec-core vault edit` when the same change also touches frontmatter.

#### Arguments

- `REF` - Document to edit. Accepts stem, filename, path, or `[[wiki-link]]`. Required.

#### Options

- `--body-file FILE` - Read the new body text from this file.
- `--body-stdin` (default off) - Read the new body text from stdin.
- `--expected-blob-hash HASH` - Refuse the write unless the on-disk blob OID matches.
- `--check` / `--no-check` (default `--check`) - Run conformance checks before writing.
- `--dry-run` (default off) - Preview without writing.
- `--json` (default off) - Output as JSON.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **Swap in a rewritten body from a file**:

  ```bash
  vaultspec-core vault set-body 2026-05-17-test-feature-research --body-file rewrite.md
  ```

To reject stale writes, use [`--expected-blob-hash`](#vaultspec-core-vault-edit).

______________________________________________________________________

### vaultspec-core vault set-frontmatter

```bash
vaultspec-core vault set-frontmatter [OPTIONS] REF
```

Edit selected frontmatter fields, keeping the body byte for byte. Only the fields you
pass are changed and every other key is preserved. The proposed metadata is validated
before writing and the write is refused on any violation, so a malformed tag set or date
never reaches disk. The `modified:` stamp is refreshed automatically.

There is no `--title` flag: a document's title is its body heading, not a frontmatter
field. Both `--tags` and `--related` replace the whole list rather than appending, so
pass every value you want to keep. To add or drop a single edge instead, use
`vaultspec-core vault link add` and `vaultspec-core vault link remove`.

#### Arguments

- `REF` - Document to edit. Accepts stem, filename, path, or `[[wiki-link]]`. Required.

#### Options

- `--date DATE` - Set the date field (`YYYY-MM-DD`).
- `--tags TAG` - Set the tags list. Repeatable; replaces the whole list.
- `--related DOC` (`-r`) - Set the related list. Repeatable; replaces the whole list.
  Each input is resolved to `[[wiki-link]]` form.
- `--expected-blob-hash HASH` - Refuse the write unless the on-disk blob OID matches.
- `--dry-run` (default off) - Preview without writing.
- `--json` (default off) - Output as JSON.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **Repoint a document's related list at its governing decision record**:

  ```bash
  vaultspec-core vault set-frontmatter 2026-05-17-test-feature-plan --related 2026-05-17-test-feature-adr
  ```

- **Correct a document's date without touching a word of its prose**:

  ```bash
  vaultspec-core vault set-frontmatter 2026-05-17-test-feature-plan --date 2026-05-18
  ```

______________________________________________________________________

### vaultspec-core vault rename

```bash
vaultspec-core vault rename [OPTIONS] REF
```

Rename a document's file and re-point incoming references. The document is renamed to
`<--to>.md` in the same directory, every other document's `related: [[old-stem]]` entry
is rewritten to the new stem, and the `modified:` stamp is refreshed. Pre-checks for
blob hash, stem grammar, and filename collision run before anything is written, and the
renamed document's conformance diagnostics come back with the result.

This renames one document. To rename a whole feature - its documents, its exec folder,
its tags, and its index - use `vaultspec-core vault feature rename`.

#### Arguments

- `REF` - Document to rename. Accepts stem, filename, path, or `[[wiki-link]]`.
  Required.

#### Options

- `--to STEM` - New identity-bearing stem (filename without `.md`). Required.
- `--expected-blob-hash HASH` - Refuse the rename unless the on-disk blob OID matches.
- `--check` / `--no-check` (default `--check`) - Report conformance checks on the
  renamed document.
- `--dry-run` (default off) - Preview without writing.
- `--json` (default off) - Output as JSON.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **Give a document a clearer stem and fix every link that pointed at it**:

  ```bash
  vaultspec-core vault rename 2026-05-17-test-feature-research --to 2026-05-17-test-feature-intake-research
  ```

- **See which documents a rename would rewrite before running it**:

  ```bash
  vaultspec-core vault rename 2026-05-17-test-feature-research --to 2026-05-17-test-feature-intake-research --dry-run
  ```

______________________________________________________________________

### vaultspec-core status

```bash
vaultspec-core status [OPTIONS] [TARGET]
```

Orient in a vaultspec vault: rollup or a grounding trace for a target. This is the
top-level zeroth move. Read-only - it never writes and produces no artifact.

**Rollup mode** (no `TARGET`): reports plans in flight, each with a one-line overview
(tier, completed waves and phases, step completion, and the next open step); plans
recently completed; recent changes grouped by type with ledgers collapsed per feature;
active features; and vault totals. Outcome semantics: always `unchanged` (read-only
verb). Advisory hints point at the targeted form and at `vaultspec-core spec doctor` for
framework health.

**Targeted mode** (`TARGET` is a plan stem, plan path, or feature handle): renders the
grounding trace - a plan-line header, then each step (display path, checkbox state, a
cursor on the next open step) mapped to its evidence: `ledger N rows` plus the last
`verify:` result for a step with ledger rows, `no rows` for an open step without any, or
`unlinked` for a closed step without any. Exec documents that reference the plan but
name no step are listed as unlinked records. Grounding documents are grouped by type
beneath the step list. A feature handle traces every plan under that feature.

`vaultspec-core status` is orientation, not auditing: it describes what exists without
judging conformance. Use `vaultspec-core vault check` to audit and
`vaultspec-core spec doctor` for framework health.

#### Options

- `--limit N` (default `10`) - Recently modified documents to show, per type.
- `--since N` - Show documents modified within the last N days.
- `--paths` (default off) - Show each referenced document's path (targeted mode).
- `--verbose-exec` (default off) - List ledgers instead of collapsing them per feature.
- `--json` (default off) - Emit machine-readable output (`vaultspec.vault.status.v1`).
- `--no-hints` (default off) - Suppress next-step advisory hints.

`--limit` and `--since` apply only in rollup mode. `--since` switches from a last-N
count to a day-window query.

#### Examples

- **Get a vault-wide orientation rollup (in-flight plans and recent changes)**:

  ```bash
  vaultspec-core status
  ```

- **Trace a specific plan to its ledger rows and grounding documents**:

  ```bash
  vaultspec-core status 2026-05-17-test-feature-plan
  ```

- **Show only documents modified in the last 7 days**:

  ```bash
  vaultspec-core status --since 7
  ```

______________________________________________________________________

### vaultspec-core vault list

```bash
vaultspec-core vault list [OPTIONS] [DOC_TYPE]
```

List vault documents.

#### Arguments

- `DOC_TYPE` - Filter by document type.

#### Options

- `--feature TAG` (`-f`) - Filter by feature tag.
- `--date DATE` - Filter by date.
- `--json` (default off) - Emit machine-readable output.
- `--limit N` (default 50) - Maximum documents to return.
- `--offset N` (default 0) - Documents to skip, for paging.

#### Examples

- **List all plans in the vault for a specific feature**:

  ```bash
  vaultspec-core vault list plan --feature test-feature
  ```

______________________________________________________________________

### vaultspec-core vault stats

```bash
vaultspec-core vault stats [OPTIONS]
```

Show vault statistics and document counts.

#### Options

- `--feature TAG` (`-f`) - Filter by feature tag.
- `--date DATE` - Filter by date.
- `--type TYPE` - Filter by document type.
- `--invalid` (default off) - Show only documents with invalid links.
- `--orphaned` (default off) - Show only orphaned documents.
- `--json` (default off) - Emit machine-readable output.

#### Examples

- **Display vault-wide statistics with details for orphaned and invalid-link
  documents**:

  ```bash
  vaultspec-core vault stats --invalid --orphaned
  ```

______________________________________________________________________

### vaultspec-core vault graph

```bash
vaultspec-core vault graph [OPTIONS]
```

Outputs a hierarchical tree grouped by feature and type.

#### Options

- `--feature TAG` (`-f`) - Scope to a single feature.
- `--json` (default off) - Output as networkx node-link JSON.
- `--metrics` (`-m`, default off) - Show aggregate graph metrics.
- `--ascii` (default off) - Render ASCII topology.
- `--body` (default off) - Include document body in JSON output.
- `--node STEM` - Scope JSON to a node's local (ego) neighbourhood.
- `--depth N` (default 1) - Ego-graph radius in hops; only used with --node.
- `--derived/--no-derived` (default off) - Include the derived relatedness edge set in
  JSON.
- `--derived-limit N` (default none) - Maximum derived edges to return. The per-node
  fan-out cap bounds edges per node, not the total.
- `--derived-offset N` (default 0) - Derived edges to skip, for paging.
- `--ref REF` - Read the vault corpus from this git ref (branch, tag, or commit) through
  the object database, without checking it out into the working tree.

The `--json` payload (schema `vaultspec.vault.graph.v2`) carries typed weighted explicit
edges (`kind`, `multiplicity`, `weight`), node-size hints (`pagerank`, `in_degree`), and
a separate `derived_edges` array of implicit relatedness edges kept out of the canonical
`edges` array. A missing `--node` stem exits 1 with a `failed` envelope.

#### Examples

- **Visualize the vault hierarchy and structure as an ASCII tree scoped to a feature**:

  ```bash
  vaultspec-core vault graph --feature test-feature --ascii
  ```

______________________________________________________________________

### vaultspec-core vault repair

```bash
vaultspec-core vault repair [OPTIONS]
```

Run the operator repair pipeline for `.vault/` content. This is the guided recovery
surface for degraded vaults. It reports preflight and migration state, runs the health
checks, applies supported mechanical fixes unless `--dry-run` is set, refreshes
generated feature indexes unless `--no-index` is set, rebuilds graph state, and runs a
postcheck pass.

`vaultspec-core vault repair` is broader than `vaultspec-core vault check all --fix`.
The check-level fixer remains available for compatibility, but it does not own generated
index refresh, post-fix graph rebuild, root-cause grouping, or final delta reporting. It
also strips standalone annotation comments during the fix phase. Inline HTML comments
embedded in prose are preserved.

#### Options

- `--dry-run` (default off) - Preview repair actions without writing.
- `--include-index/--no-index` (default on) - Refresh generated feature indexes during
  repair.
- `--feature TAG` (`-f`) - Scope repair and index refresh to one feature.
- `--verbose` (`-v`, default off) - Show INFO-level diagnostics and detailed paths.
- `--json` (default off) - Emit machine-readable phase and summary payloads.

#### Phases

- `preflight` - Report migration status and platform path behavior.
- `check` - Run the current vault health suite without mutation.
- `fix` - Apply supported safe check-level fixes, or report planned fixes.
- `index` - Refresh or preview generated `.vault/index/<feature>.index.md` files.
- `postcheck` - Rebuild graph state and rerun checks after mutation.
- `summary` - Report changed files, generated indexes, unresolved work, root causes.

Dry-run mode never writes generated indexes or check fixes. If migrations are pending,
dry-run reports that state instead of entering the vault scan path that would apply lazy
migrations on first use.

#### Examples

- **Scan and apply all safe automatic repairs to a degraded vault**:

  ```bash
  vaultspec-core vault repair
  ```

______________________________________________________________________

### vaultspec-core vault sanitize annotations

```bash
vaultspec-core vault sanitize annotations [OPTIONS]
```

Strip generated template annotations from `.vault/` documents. Template hydration keeps
agent-facing instructions in newly created documents; this command removes those
instructions only when explicitly requested. Use `--dry-run` to see which files would be
stripped without mutating the vault. The sanitizer removes YAML frontmatter comment
directives, standalone HTML comment blocks, and malformed standalone `<-- ... -->`
annotation blocks. It preserves fenced examples, inline HTML comments embedded in prose,
and machine-owned comments such as retired plan markers.

#### Options

- `--feature TAG` (`-f`) - Sanitize documents for one feature.
- `--dry-run` (default off) - Preview annotation removals.
- `--verbose` (`-v`, default off) - Show stripped files.
- `--json` (default off) - Emit machine-readable check payloads.
- `--limit N` (default 50) - Maximum findings to return.
- `--offset N` (default 0) - Findings to skip, for paging.

#### Examples

- **Strip all default template instructions and annotations from a feature's
  documents**:

  ```bash
  vaultspec-core vault sanitize annotations --feature test-feature
  ```

______________________________________________________________________

### vaultspec-core vault feature list

```bash
vaultspec-core vault feature list [OPTIONS]
```

List all feature tags in the vault.

#### Options

- `--date DATE` - Filter by date.
- `--orphaned` (default off) - Show only features with no incoming links.
- `--type TYPE` - Filter by document type.
- `--stale-days N` - Show only features whose latest activity is older than N days.
- `--json` (default off) - Emit machine-readable output.
- `--limit N` (default 50) - Maximum features to return.
- `--offset N` (default 0) - Features to skip, for paging.

#### Examples

- **List all active feature tags in the vault**:

  ```bash
  vaultspec-core vault feature list
  ```

______________________________________________________________________

### vaultspec-core vault feature index

```bash
vaultspec-core vault feature index [OPTIONS]
```

Generate or update `<feature>.index.md` files in `.vault/index/`. Each index links to
every document sharing that feature tag, making implicit feature clusters explicit in
the graph. Indexes carry the `#index` directory tag plus the feature tag and are
auto-managed.

#### Options

- `--feature TAG` (`-f`) - Generate index for a specific feature.
- `--json` (default off) - Emit machine-readable output.

#### Examples

- **Rebuild or generate the index document for a specific feature**:

  ```bash
  vaultspec-core vault feature index --feature test-feature
  ```

______________________________________________________________________

### vaultspec-core vault feature archive

```bash
vaultspec-core vault feature archive [OPTIONS] FEATURE_TAG
```

Move all documents for a feature tag to the archive.

#### Options

- `--dry-run` (default off) - Preview planned changes.
- `--no-hints` (default off) - Suppress next-step advisory hints.
- `--json` (default off) - Emit machine-readable output.
- `--target` (`-t`) - Target directory (defaults to current working directory).

#### Examples

- **Archive all documents for a completed feature tag**:

  ```bash
  vaultspec-core vault feature archive test-feature
  ```

______________________________________________________________________

### vaultspec-core vault feature unarchive

```bash
vaultspec-core vault feature unarchive [OPTIONS] FEATURE_TAG
```

Restore all archived documents for a feature tag.

#### Options

- `--dry-run` (default off) - Preview planned changes.
- `--json` (default off) - Emit machine-readable output.
- `--target` (`-t`) - Target directory (defaults to current working directory).

#### Examples

- **Restore and unarchive all documents for a previously archived feature**:

  ```bash
  vaultspec-core vault feature unarchive test-feature
  ```

______________________________________________________________________

### vaultspec-core vault archive documents

```bash
vaultspec-core vault archive documents [OPTIONS]
```

Archive exactly the live vault documents listed in a UTF-8 manifest. Each line must be a
repository-relative `.vault/*.md` path. The command validates every source and
destination before it moves anything, so a bad line cannot produce a partial archive.

#### Options

- `--manifest PATH` - Required UTF-8 manifest of repository-relative vault Markdown
  paths, one per line.
- `--dry-run` (default off) - Validate and show the archive destinations without
  writing.
- `--json` (default off) - Emit the standard machine-readable result envelope.

#### Examples

- **Preview the archival of explicitly selected historical records**:

  ```bash
  vaultspec-core vault archive documents --manifest .vault/archive-manifest.txt --dry-run
  ```

______________________________________________________________________

### vaultspec-core vault archive restore

```bash
vaultspec-core vault archive restore [OPTIONS]
```

Bring archived documents back into the live vault. Each manifest line must be a
repository-relative `.vault/_archive/*.md` path. This is the inverse of
`vaultspec-core vault archive documents`: every source and destination is validated
before anything moves, so a bad line cannot produce a partial restore.

#### Options

- `--manifest PATH` - Required UTF-8 manifest of repository-relative archived Markdown
  paths, one per line.
- `--dry-run` (default off) - Validate and show the restore destinations without
  writing.
- `--deduplicate-identical` (default off) - When an archived document already has a live
  counterpart with byte-identical content, drop the archived copy instead of failing on
  the collision. Documents whose contents differ are still reported as conflicts.
- `--json` (default off) - Emit the standard machine-readable result envelope.

#### Examples

- **Preview restoring a set of archived records**:

  ```bash
  vaultspec-core vault archive restore --manifest .vault/restore-manifest.txt --dry-run
  ```

- **Restore, clearing archived copies that already match the live document**:

  ```bash
  vaultspec-core vault archive restore --manifest .vault/restore-manifest.txt --deduplicate-identical
  ```

______________________________________________________________________

### vaultspec-core vault exec relink

```bash
vaultspec-core vault exec relink [OPTIONS]
```

Relink one execution record to a live Step in its existing parent plan. The record body
is preserved; only the validated Step mapping can change.

#### Options

- `--record PATH` - Required live execution-record path.
- `--step STEP` - Required live Step identifier or display path in the parent plan.
- `--dry-run` (default off) - Preview the recovery without writing.
- `--json` (default off) - Emit the standard machine-readable result envelope.

______________________________________________________________________

### vaultspec-core vault exec retire

```bash
vaultspec-core vault exec retire [OPTIONS]
```

Archive one execution record only when its current Step is retired by its parent plan.

#### Options

- `--record PATH` - Required live execution-record path.
- `--dry-run` (default off) - Preview the recovery without writing.
- `--json` (default off) - Emit the standard machine-readable result envelope.

______________________________________________________________________

### vaultspec-core vault exec detach

```bash
vaultspec-core vault exec detach [OPTIONS]
```

Remove one record's Step claim only when it resolves to neither a live nor a retired
Step.

#### Options

- `--record PATH` - Required live execution-record path.
- `--dry-run` (default off) - Preview the recovery without writing.
- `--json` (default off) - Emit the standard machine-readable result envelope.

______________________________________________________________________

### vaultspec-core vault exec fold

```bash
vaultspec-core vault exec fold [OPTIONS]
```

Fold a feature's per-Step execution records, from before 0.1.74, into its plan's ledger.
The folded records are removed once the ledger carrying their content is on disk; the
upgrade migration runs the same fold on its own.

A `body-v1` record's `## Scope` paths become rows carrying the `T` (touched) operation,
because that schema never recorded whether a path was added, modified, or deleted and
none is invented; `T` stays distinguishable from a natively logged `A`/`M`/`D`/`R`. A
`body-v2` record's `## Changes` rows fold with their operations and `verify:` line
intact, and its `## Notes` lines are carried under the Step id. A flat
`<date>-<feature>-exec.md` record carrying a `step_id` folds too. Other prose is
discarded; it is recoverable from the commit preceding the fold, since `.vault/` is
tracked, but no forward command undoes it.

A Phase Summary is removed once every Step of its Phase has rows in the ledger, and left
intact otherwise. A record with no `step_id` cannot be attributed to a Step and is left
intact.

#### Options

- `--feature FEATURE` - Required feature tag, with or without a leading `#`.
- `--dry-run` (default off) - Report the fold plan without writing.
- `--force` (default off) - Required to apply; the fold removes records.
- `--json` (default off) - Emit the standard machine-readable result envelope.

______________________________________________________________________

### vaultspec-core vault exec log

```bash
vaultspec-core vault exec log [OPTIONS]
```

Append one Step's rows to its plan's ledger, creating the ledger on first use. The
ledger is one document per plan and the only execution artifact; it is append-only:
existing rows are never rewritten, and re-logging an identical row is idempotent rather
than duplicating it. Concurrent appends to one ledger are serialised by an advisory
lock, and the managed `.gitattributes` block declares `merge=union` on ledgers so two
branches appending different Steps merge without a conflict.

#### Options

- `--feature FEATURE` - Required feature tag, with or without a leading `#`.
- `--related PLAN_STEM` - Required stem of the parent plan this ledger records.
- `--step STEP` - Required canonical Step identifier or display path being logged.
- `--row SPEC` - Row to append, repeatable. `A:path` added, `M:path` modified, `D:path`
  deleted, `R:old->new` renamed. The verb never infers an operation from disk state.
- `--verify SPEC` - A check that ran, as `<command>=pass` or `<command>=fail`; written
  as a `verify:` row.
- `--by PERSONA` - The persona that closed the Step; written as a `by:` row.
- `--note TEXT` - Exception note, repeatable; written as a `## Notes` line under the
  Step id, the section created on first use.
- `--dry-run` (default off) - Resolve and report the target ledger without writing.
- `--json` (default off) - Emit the standard machine-readable result envelope.

______________________________________________________________________

### vaultspec-core vault feature rename

```bash
vaultspec-core vault feature rename [OPTIONS] OLD_FEATURE NEW_FEATURE
```

Atomically rename a feature tag across every vault surface. The rename rewrites document
filenames, the exec folder and the execution-record filenames inside it, the `#feature`
frontmatter tag, `related:` wiki-links, and the regenerated feature index. Free-form
body prose is never touched, so a sentence that happens to mention the old name stays as
you wrote it.

The apply phase keeps a reverse journal. If anything fails part way through, the changes
made so far are rolled back to the pre-rename state, so the vault is never left half
renamed. By default the command refuses when the target feature already exists;
`--force` merges the source feature into it, and per-file path collisions still refuse.
Preview first with `--dry-run` - this command touches many files at once.

#### Arguments

- `OLD_FEATURE` - Current feature tag to rename. Required.
- `NEW_FEATURE` - New feature tag name. Required.

#### Options

- `--dry-run` (default off) - Preview planned changes without writing.
- `--force` (default off) - Merge the source into an existing target feature.
- `--json` (default off) - Output as JSON.
- `--no-hints` (default off) - Suppress next-step advisory hints.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **Preview the full set of files a feature rename would rewrite**:

  ```bash
  vaultspec-core vault feature rename test-feature editor-demo --dry-run
  ```

- **Fold one feature's documents into another existing feature**:

  ```bash
  vaultspec-core vault feature rename test-feature editor-demo --force
  ```

______________________________________________________________________

### vaultspec-core vault adr supersede

```bash
vaultspec-core vault adr supersede [OPTIONS] OLD_ADR
```

Supersede an old ADR with a new ADR.

#### Arguments

- `OLD_ADR` - Old ADR stem to supersede.

#### Options

- `--by` - New ADR stem that supersedes the old one.
- `--dry-run` (default off) - Preview without writing.
- `--json` (default off) - Output as JSON.
- `--target` (`-t`) - Target directory (defaults to current working directory).

#### Examples

- **Supersede an outdated ADR with a newly created one**:

  ```bash
  vaultspec-core vault adr supersede 2026-05-17-old-adr-stem --by 2026-05-26-new-adr-stem
  ```

______________________________________________________________________

### vaultspec-core vault rule promote

```bash
vaultspec-core vault rule promote [OPTIONS]
```

Promote an audit finding to a project-level rule.

#### Options

- `--from` - Audit stem to promote from. Required.
- `--as` - Kebab-case name of the promoted rule. Required.
- `--force` (default off) - Overwrite existing rule source.
- `--dry-run` (default off) - Preview without writing.
- `--json` (default off) - Output as JSON.
- `--target` (`-t`) - Target directory (defaults to current working directory).

#### Examples

- **Promote a specific finding from an audit file into a project-shared rule**:

  ```bash
  vaultspec-core vault rule promote --from 2026-05-17-feature-audit --as project-rule-name
  ```

______________________________________________________________________

### vaultspec-core vault check

```bash
vaultspec-core vault check [OPTIONS] COMMAND [ARGS]...
```

Run health checks on `.vault/`. Exits with code `1` if errors are found.

#### Shared options

- `--fix` (default off) - Apply auto-fixes where supported.
- `--feature TAG` (`-f`) - Limit to a specific feature.
- `--verbose` (`-v`, default off) - Show INFO-level diagnostics.
- `--json` (default off) - Emit machine-readable output.
- `--limit N` (default 50) - Maximum findings to return per check. The per-check and
  aggregate counts are never windowed, so severity totals stay exact on any page.
- `--offset N` (default 0) - Findings to skip, for paging.

`vaultspec-core vault check all` additionally accepts `--no-hints` to suppress the
next-step advisory hints it prints after a run.

`rename-integrity` adds a second repair flag, because a name mismatch can be resolved
from either side: `--fix` is filename-wins and rewrites the frontmatter name to match
the file, while `--fix-frontmatter-wins` is the inverse and renames the file to match
the frontmatter name. Pick the one whose side you trust.

#### Subcommands

- `all` (`--fix`: partial, `--feature`: yes) - Run every check in sequence.
- `structure` (`--fix`: yes, `--feature`: no) - Check vault directory structure and
  filename conventions.
- `frontmatter` (`--fix`: yes, `--feature`: yes) - Validate document frontmatter against
  vault schema.
- `modified-stamp` (`--fix`: yes, `--feature`: yes) - Validate and reconcile the
  `modified:` recency stamp on every document.
- `annotations` (`--fix`: yes, `--feature`: yes) - Find generated template annotations
  in vault documents.
- `markdown` (`--fix`: yes, `--feature`: yes) - Check and optionally fix markdown
  hygiene (whitespace, blank runs, trailing newline).
- `links` (`--fix`: yes, `--feature`: yes) - Check wiki-links follow Obsidian convention
  (no `.md` extension).
- `dangling` (`--fix`: yes, `--feature`: yes) - Find `related:` frontmatter wiki-links
  that resolve to no document.
- `body-links` (`--fix`: yes, `--feature`: yes) - Find wiki-links and markdown path
  links in document body text.
- `placeholders` (`--fix`: no, `--feature`: yes) - Find unreplaced `{...}` template
  placeholders in document body prose.
- `orphans` (`--fix`: no, `--feature`: yes) - Find documents with no incoming
  wiki-links.
- `features` (`--fix`: no, `--feature`: yes) - Check feature tag completeness - missing
  doc types.
- `exec-mapping` (`--fix`: no, `--feature`: yes) - Pair ledger rows with plan Steps: a
  per-Step record or a closed Step with no row in an existing ledger is an error; a
  closed Step with no row in a plan without a ledger, a row for an open or unknown Step,
  is a warning; a row for a retired Step is clean.
- `body-sections` (`--fix`: no, `--feature`: yes) - Check document bodies carry the
  sections their template mandates.
- `feature-rename-integrity` (`--fix`: no, `--feature`: yes) - Surface exec folders
  whose feature disagrees with their records' tag.
- `references` (`--fix`: yes, `--feature`: yes) - Check for missing cross-references
  within features.
- `schema` (`--fix`: yes, `--feature`: yes) - Enforce schema rules: ADRs must ref
  research, plans must ref ADRs.
- `adr-status` (`--fix`: yes, `--feature`: yes) - Validate ADR status against the
  canonical taxonomy.
- `rename-integrity` (`--fix`: yes, `--feature`: no) - Check name/filename integrity for
  rules, skills, and agents.
- `encoding` (`--fix`: no, `--feature`: yes) - Surface `.vault/` documents that are not
  valid UTF-8 (detection only).
- `code-boundary` (`--fix`: no, `--feature`: yes) - Scan source files for references to
  the project's own vault records (opt-in; findings are advisory).

`yes` = fully supported, `partial` = only the sub-checks that accept `--fix` apply fixes
(`all` dispatches to every check it runs), `no` = flag rejected with error. `all` runs
nineteen of the twenty checks above: `code-boundary` is opt-in and runs only when named,
so an exit-0 `all` makes no claim about it. `structure` does not support `--feature`
filtering.

Use `vaultspec-core vault repair` when the operator goal is end-to-end recovery with
generated index refresh, post-fix validation, and a final delta report.

#### Examples

- **Run all vault health checks to verify link integrity and directory structure**:

  ```bash
  vaultspec-core vault check all
  ```

- **Audit and automatically repair dangling wiki-links**:

  ```bash
  vaultspec-core vault check dangling --fix
  ```

- **Check feature completeness for a specific feature tag**:

  ```bash
  vaultspec-core vault check features --feature test-feature
  ```

- **Scan for and report any generated template instructions or annotations**:

  ```bash
  vaultspec-core vault check annotations --feature test-feature
  ```

- **Verify Obsidian-style wiki links in body text resolved against the vault**:

  ```bash
  vaultspec-core vault check body-links
  ```

- **Audit rule, skill, and agent filenames for matching name tags**:

  ```bash
  vaultspec-core vault check rename-integrity
  ```

- **Find all unreferenced (orphaned) documents in the vault**:

  ```bash
  vaultspec-core vault check orphans
  ```

- **Validate document frontmatter fields against required templates**:

  ```bash
  vaultspec-core vault check frontmatter --fix
  ```

- **Check wiki-link formats (ensuring no .md file extensions are used)**:

  ```bash
  vaultspec-core vault check links
  ```

- **Enforce architectural schema dependency rules**:

  ```bash
  vaultspec-core vault check schema
  ```

- **Verify all external references are valid and up to date**:

  ```bash
  vaultspec-core vault check references
  ```

- **Check directory structure and naming conventions for rules, skills, and agents**:

  ```bash
  vaultspec-core vault check structure
  ```

### vaultspec-core vault plan

```bash
vaultspec-core vault plan [OPTIONS] COMMAND [ARGS]...
```

Inspect and manipulate plan documents per the plan-hardening convention. Plans declare a
complexity tier (`L1`, `L2`, `L3`, `L4`) in frontmatter and are structured as
`Epic > Wave > Phase > Step`. Every mutating operation goes through this surface.
Canonical identifiers (`S##`, `P##`, `W##`) remain append-only and gap-no-reuse.
`vaultspec-core vault plan check` flags hand-edits to checkbox glyphs or display paths.

#### Examples

- **Query all open steps in a plan**:

  ```bash
  vaultspec-core vault plan query .vault/plan/2026-05-17-test-feature-plan.md --open
  ```

- **Append a Step to Phase P01 of an L2 plan**:

  ```bash
  vaultspec-core vault plan step add --phase P01 --action "Implement login authentication handler" --scope "src/auth.py" .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Toggle completion checkbox of a step**:

  ```bash
  vaultspec-core vault plan step toggle .vault/plan/2026-05-17-test-feature-plan.md S01
  ```

- **Renumber a phase to resolve duplicate identifier conflicts**:

  ```bash
  vaultspec-core vault plan phase renumber --to P02 .vault/plan/2026-05-17-test-feature-plan.md P01
  ```

- **Validate the formatting and structure of an existing plan file**:

  ```bash
  vaultspec-core vault plan check .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Mark a plan step completed (idempotent check)**:

  ```bash
  vaultspec-core vault plan step check .vault/plan/2026-05-17-test-feature-plan.md S01
  ```

- **Mark a plan step incomplete (idempotent uncheck)**:

  ```bash
  vaultspec-core vault plan step uncheck .vault/plan/2026-05-17-test-feature-plan.md S01
  ```

- **Insert a new step before an existing anchor step**:

  ```bash
  vaultspec-core vault plan step insert --action "Validate input arguments" --before S02 .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Edit an existing step's action prose and code scope**:

  ```bash
  vaultspec-core vault plan step edit --action "New auth handler" --scope "src/auth.py" .vault/plan/2026-05-17-test-feature-plan.md S01
  ```

- **Move a step to a different phase inside the plan**:

  ```bash
  vaultspec-core vault plan step move --to-phase P02 .vault/plan/2026-05-17-test-feature-plan.md S01
  ```

- **Retire a plan step permanently**:

  ```bash
  vaultspec-core vault plan step remove .vault/plan/2026-05-17-test-feature-plan.md S01
  ```

- **Append a new phase to the current wave of a plan**:

  ```bash
  vaultspec-core vault plan phase add --title "Authentication Layer" --intent "Set up secure login/signup" .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Insert a phase before an existing anchor phase**:

  ```bash
  vaultspec-core vault plan phase insert --title "Database Setup" --before P02 .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Edit a phase's title or intent prose in place**:

  ```bash
  vaultspec-core vault plan phase edit --title "Updated Auth Setup" .vault/plan/2026-05-17-test-feature-plan.md P01
  ```

- **Move a phase to a different wave in the plan**:

  ```bash
  vaultspec-core vault plan phase move --to-wave W02 .vault/plan/2026-05-17-test-feature-plan.md P01
  ```

- **Retire a phase along with all of its descendant steps**:

  ```bash
  vaultspec-core vault plan phase remove .vault/plan/2026-05-17-test-feature-plan.md P01
  ```

- **Append a new wave to a plan**:

  ```bash
  vaultspec-core vault plan wave add --title "Advanced Features" --intent "Add full-text search" .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Insert a wave after an existing anchor wave**:

  ```bash
  vaultspec-core vault plan wave insert --title "Optimization Wave" --after W01 .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Edit a wave's title or intent prose in place**:

  ```bash
  vaultspec-core vault plan wave edit --title "Updated Core Wave" .vault/plan/2026-05-17-test-feature-plan.md W01
  ```

- **Move a wave to reposition it within the plan**:

  ```bash
  vaultspec-core vault plan wave move --after W02 .vault/plan/2026-05-17-test-feature-plan.md W01
  ```

- **Retire a wave along with all of its descendant phases and steps**:

  ```bash
  vaultspec-core vault plan wave remove .vault/plan/2026-05-17-test-feature-plan.md W01
  ```

- **Display the plan's high-level Epic intent paragraph**:

  ```bash
  vaultspec-core vault plan epic intent show .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Update the plan's Epic intent paragraph**:

  ```bash
  vaultspec-core vault plan epic intent edit --text "Epic intent text associating PM issues" .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Display the plan's current complexity tier**:

  ```bash
  vaultspec-core vault plan tier show .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Promote a plan's complexity tier to L4**:

  ```bash
  vaultspec-core vault plan tier promote --target L4 --epic-intent "Epic goal" .vault/plan/2026-05-17-test-feature-plan.md
  ```

- **Demote a plan's complexity tier to L1**:

  ```bash
  vaultspec-core vault plan tier demote --target L1 --force .vault/plan/2026-05-17-test-feature-plan.md
  ```

#### Shared mutation options

Every mutating plan verb - the step, phase, wave, epic-intent, and tier commands -
shares three flags:

- `--dry-run` (default off) - Preview the rewritten plan without writing it.
- `--json` (default off) - Output as JSON.
- `--canonicalise` (default off) - Strip unrecognized prose blocks while re-serializing
  the plan. Without it, prose the parser does not recognize is carried through
  untouched; with it, the plan is rewritten to the canonical structure only. Preview
  with `--dry-run` before using it on a plan that carries hand-written notes.

#### Read commands

- `status` - Report plan health, structure, and completion. `--json` emits a
  machine-readable payload.
- `check` - Validate convention compliance; with `--fix`, apply autofixable
  transformations.
- `query` - Filter Step rows by `--phase`/`--wave` scope and `--open`/`--closed`
  predicate.

`vaultspec-core vault plan check` exits `1` when at least one ERROR-severity finding is
present.

______________________________________________________________________

#### vaultspec-core vault plan status

```bash
vaultspec-core vault plan status [OPTIONS] PATH
```

Report plan health, structure, completion percentages, and identify missing execution
records.

##### Arguments

- `PATH` - Path to the `.vault/plan/...-plan.md` plan file.

##### Options

- `--json` (default off) - Emit machine-readable status payload.

##### General Output

When run without `--json`, the command renders a console summary displaying:

- **Plan Path & Complexity Tier**: Declared level (`L1` to `L4`).
- **Container Counts**: Total count of Epic, Waves, Phases, and Steps.
- **Completion Status**: Checked vs. unchecked steps and total progress percentage.

##### Ledger Coverage (`exec-missing`)

The status command pairs every checked step with the plan's ledger:

- If a step is checked (`[x]`) in the plan but the ledger has no row naming it, the CLI
  generates a yellow warning block:

  ```text
  ! exec-missing: checked steps lacking execution records: S01, S02
  ```

- This warning does not block execution or raise exit codes; the command still exits
  with code `0`.

##### Machine-Readable Output (`--json`)

When passed `--json`, the output utilizes the uniform `vaultspec.vault.plan.status.v1`
schema envelope:

```json
{
  "schema": "vaultspec.vault.plan.status.v1",
  "status": "unchanged",
  "data": {
    "path": ".vault/plan/2026-05-17-test-feature-plan.md",
    "tier": "L2",
    "waves": 0,
    "phases": 1,
    "steps": 5,
    "checked_steps": 2,
    "completion_pct": 40.0,
    "exec_missing_ids": ["S01", "S02"]
  }
}
```

##### Examples

- **Check the progress and ledger coverage of a plan**:

  ```bash
  vaultspec-core vault plan status .vault/plan/2026-05-17-test-feature-plan.md
  ```

______________________________________________________________________

#### Step commands

- `add` - Append a Step at the next-available `S##`. Requires `--action` and `--scope`.
  At L2 and above, also supply `--phase`; omit it at L1.
- `insert` - Insert at a named position with `--before`/`--after`; parent inferred from
  anchor.
- `edit` - Replace `--action`, `--scope`, or both without changing the canonical
  identifier.
- `move` - Re-parent (`--to-phase`), re-position (`--before`/`--after`), or both.
- `remove` - Retire the Step's canonical id permanently; the next-available counter
  skips it.
- `check` - Mark the Step closed (`[x]`); idempotent.
- `uncheck` - Mark the Step open (`[ ]`); idempotent.
- `toggle` - Flip the Step's checkbox state.

#### Phase commands

- `add` - Append a Phase at the next-available `P##`. Requires `--title` and `--intent`.
- `insert` - Insert at a named position with `--before`/`--after`.
- `edit` - Replace `--title`, `--intent`, or both in place.
- `move` - Re-parent (`--to-wave`), re-position (`--before`/`--after`), or both.
- `renumber` - Remediate a duplicated id via `--to <P##>`; refuses live / retired
  collisions.
- `remove` - Retire the Phase plus every descendant Step (cascading retirement).

`phase renumber` is the audited remediation surface for collisions inherited from legacy
plans. One example is a writer who treated `P##` as Wave-scoped rather than
per-document. The verb retires the old id so it cannot be reused, then recomputes every
descendant Step's display path against the new parent canonical id.

#### Wave commands

Identical shape to Phase, but the parent is implicit (Epic frame). Only
`--before`/`--after` re-position. No `--to-epic` flag exists. Wave operations require
`L3` or `L4`.

#### Epic intent (L4 only)

- `intent show` - Print the Epic intent paragraph.
- `intent edit` - Replace the Epic intent paragraph; `--text` must declare the
  project-management (PM) association.

#### Tier commands

- `show` - Print the plan's declared tier.
- `promote` - Advance the tier transitively, for example L1 -> L4 in one call.
  Synthesized containers use
  `--phase-title`/`--phase-intent`/`--wave-title`/`--wave-intent`/`--epic-intent` for
  placeholders.
- `demote` - Step the tier down. Refuses with an error when the collapsing layer holds
  more than one container; pass `--force` to retire the dropped ids and proceed.

#### Move-flag precedence

`step move` and `phase move` accept the re-parent flag (`--to-phase` / `--to-wave`) and
the position flags (`--before` / `--after`) independently or together:

- Re-parent flag alone re-parents and appends to the destination tail.
- Position flag alone re-positions within the current parent; the anchor must share that
  parent.
- Both flags re-parent and position the item; the anchor must reside in the destination
  post-move.

A self-referential move (`step move S01 --before S01`) is rejected with the relevant
`Move{Step,Phase,Wave}Error`.

#### Identifier retirement

`remove`, multi-step demotion, and Wave / Phase removal all add the retired canonical id
to a hidden `<!-- RETIRED: ... -->` ledger embedded in the plan body. `next_available_*`
consults this ledger so retired identifiers are never reused, even across
`parse / serialize` round-trips invoked by `--fix`.

#### Trailer commands

- `emit` - Print a well-formed `Vaultspec-Step` or `Vaultspec-Feature` commit-linkage
  trailer line. Takes exactly one of `--step` (a Step or Phase display path, e.g.
  `W01.P02.S06` or `P02`) or `--feature` (a kebab-case feature tag, leading `#`
  optional).
- `validate` - Validate the commit-linkage trailers found in a commit-message file.
  Always exits `0`.

The commit-linkage trailer is an opt-in, advisory convention (per the accepted
`commit-linkage` ADR): a malformed or absent trailer never blocks a commit and never
fails a core command. `validate` reports each malformed trailer to stderr and always
exits `0`, which makes it safe to wire up as a `commit-msg`-stage pre-commit hook. Teams
that want the check add a local hook entry to their `.pre-commit-config.yaml`; teams
that do not are unaffected:

```yaml
- repo: local
  hooks:
    - id: vaultspec-plan-trailer
      name: Validate vaultspec commit-linkage trailers
      language: system
      stages: [commit-msg]
      entry: uv run vaultspec-core vault plan trailer validate
```

At the `commit-msg` stage, pre-commit passes the path to the commit-message file (for
example `.git/COMMIT_EDITMSG`) as the hook's positional argument, which lines up with
`validate`'s `MESSAGE_FILE` argument - no extra flag is needed. Add uv's `--no-sync`
flag to the `uv run` wrapper when the environment is already resolved and the hook
should skip the dependency check.

##### Examples

- **Emit a Step trailer for a commit template**:

  ```bash
  vaultspec-core vault plan trailer emit --step P02.S06
  ```

- **Emit a feature trailer**:

  ```bash
  vaultspec-core vault plan trailer emit --feature commit-linkage
  ```

- **Validate a commit message file directly**:

  ```bash
  vaultspec-core vault plan trailer validate .git/COMMIT_EDITMSG
  ```

______________________________________________________________________

### vaultspec-core vault link list

```bash
vaultspec-core vault link list [OPTIONS] [SRC]
```

List `related:` edges in the vault document graph. Without `SRC` every edge in the graph
is listed. Given a `SRC`, the listing is scoped to that document: its out-links, meaning
the edges it declares, and its in-links, meaning the edges other documents point at it.
That in-link view is the quick way to answer "what would break if I retired this
document?".

Use `--feature` to restrict the listing to edges whose source carries a given feature
tag. For a whole-graph picture rather than an edge list, use
`vaultspec-core vault graph`.

#### Arguments

- `SRC` (optional) - Scope the listing to edges from or to this document. Accepts stem,
  filename, path, or `[[wiki-link]]`.

#### Options

- `--feature TAG` (`-f`) - Filter edges whose source has this feature tag.
- `--json` (default off) - Output as JSON.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **See everything one document links to and everything that links back to it**:

  ```bash
  vaultspec-core vault link list 2026-05-17-test-feature-adr
  ```

- **List only the edges declared by one feature's documents**:

  ```bash
  vaultspec-core vault link list --feature test-feature
  ```

______________________________________________________________________

### vaultspec-core vault link add

```bash
vaultspec-core vault link add [OPTIONS] SRC DST
```

Add a `related:` edge from `SRC` to `DST`. Both arguments are resolved to document stems
and the edge is written into the source document's `related:` frontmatter as a
`[[wiki-link]]`. Adding an edge that already exists is reported as unchanged, so the
command is safe to re-run.

By default a dangling edge - one whose target resolves to no real document - is refused;
pass `--force` when you deliberately want to link ahead to a document you have not
scaffolded yet. The command exits `0` when the edge was added or already existed, and
`1` when either argument fails to resolve or a dangling edge is refused.

#### Arguments

- `SRC` - Source document to add the edge from. Accepts stem, filename, path, or
  `[[wiki-link]]`. Required.
- `DST` - Target document to link to. Accepts stem, filename, path, or `[[wiki-link]]`.
  Required.

#### Options

- `--dry-run` (default off) - Preview the change without writing.
- `--force` (default off) - Allow creating a dangling edge whose target is not a real
  document.
- `--json` (default off) - Output as JSON.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **Link a plan to the decision record it carries out**:

  ```bash
  vaultspec-core vault link add 2026-05-17-test-feature-plan 2026-05-17-test-feature-adr
  ```

- **Check what a link would write before writing it**:

  ```bash
  vaultspec-core vault link add 2026-05-17-test-feature-plan 2026-05-17-test-feature-adr --dry-run
  ```

______________________________________________________________________

### vaultspec-core vault link remove

```bash
vaultspec-core vault link remove [OPTIONS] SRC DST
```

Remove a `related:` edge from `SRC` to `DST`. Only the source document is rewritten; the
target is left untouched. Removing an edge that does not exist is reported as unchanged
rather than as an error, so the command is safe to re-run and safe to script. It exits
`0` on success or on a no-op, and `1` when either argument fails to resolve or the write
fails.

#### Arguments

- `SRC` - Source document to remove the edge from. Accepts stem, filename, path, or
  `[[wiki-link]]`. Required.
- `DST` - Target document to unlink. Accepts stem, filename, path, or `[[wiki-link]]`.
  Required.

#### Options

- `--dry-run` (default off) - Preview the change without writing.
- `--json` (default off) - Output as JSON.
- `--target DIR` (`-t`, default cwd) - Target directory.

#### Examples

- **Drop a stale link between two documents**:

  ```bash
  vaultspec-core vault link remove 2026-05-17-test-feature-plan 2026-05-17-old-adr-stem
  ```

## Spec commands

Group command: `vaultspec-core spec [OPTIONS] COMMAND [ARGS]...`

Spec subcommands that operate on a workspace accept `--target / -t DIR`. `--json` is
command-specific and appears only on commands that support machine-readable output.

### vaultspec-core spec doctor

```bash
vaultspec-core spec doctor [OPTIONS]
```

Run diagnostic collectors across the framework, providers, builtins, `.gitignore`, vault
content, and configuration files. Reports findings and exits with the highest severity
observed. The vault content row is read-only; when generated template annotations are
present, doctor reports a warning and points to
`vaultspec-core vault sanitize annotations`. Unreadable vault markdown files are
reported as warnings and are not modified.

#### Options

- `--target DIR` (`-t`, default cwd) - Diagnose a directory other than the current one.
- `--json` (default off) - Emit the diagnosis as JSON.
- `--gate-errors` (default off) - Exit `0` on warnings and fail (exit `2`) only on
  errors. Intended for the pre-commit gate, where warning-level provider-mirror lag is
  an expected steady state that must not block a commit.

Exit codes: `0` = all ok, `1` = warnings, `2` = errors.

Not every line the diagnosis prints is weighed. The tool-server configuration line, the
process registry, and stale package seeds are reported for your attention and do not
raise the code, so a run can print `warn` and still exit `0`. Do not infer failure from
the word `warn` in the output: read the exit code, or read `status` under `--json`. The
conditions that do raise it are the framework layout, the provider directories, the
builtins, `.gitignore` and `.gitattributes`, migrations, the pre-commit hooks, rename
integrity, vault content, and an install-mode or version-floor mismatch on any declared
package.

#### Examples

- **Diagnose overall workspace health across configuration, git, and vault**:

  ```bash
  vaultspec-core spec doctor
  ```

______________________________________________________________________

### vaultspec-core spec rules / vaultspec-core spec skills / vaultspec-core spec agents

Create, read, update, and delete (CRUD) operations for framework resources. All three
groups share the same subcommand structure.

```bash
vaultspec-core spec rules [OPTIONS] COMMAND [ARGS]...
vaultspec-core spec skills [OPTIONS] COMMAND [ARGS]...
vaultspec-core spec agents [OPTIONS] COMMAND [ARGS]...
```

#### Subcommands

- `list` - List all resources.
- `add NAME [--body BODY] [--from-file FILE] [--force] [--dry-run]` - Create a resource.
  `skills add` and `agents add` also accept `--description TEXT` for the resource's
  frontmatter summary, and `skills add` additionally accepts `--template NAME` to
  scaffold from a named template instead of an empty body.
- `show NAME` - Print resource content to stdout.
- `edit NAME [--editor EDITOR]` - Open in configured editor. Resolution order: --editor
  flag, local config, VISUAL, EDITOR, vi.
- `remove NAME [--yes|--force]` (`-y`) - Delete a resource. Prompts unless confirmed.
- `rename OLD_NAME NEW_NAME` - Rename a resource.
- `sync` (`--dry-run`, `--force`) - Resource-scoped sync; use top-level
  `vaultspec-core sync` for a complete provider refresh.
- `restore FILENAME` - Restore to snapshotted original.
- `status` (`--json`) - Report dry-run sync with prune enabled, returning
  missing/drifted/stale status.

`edit` accepts the `--editor` option to override the editor binary for this invocation.
`add` accepts the unified `--body` flag for direct content or `--from-file` to read from
a file. Rules carry no description, so `rules add` has no `--description`; only skills
support `--template`.

`vaultspec-core spec <resource> sync` commands are narrow maintenance surfaces. They do
not guarantee that provider-facing config stubs such as `AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, or `.codex/config.toml` have been fully refreshed. Run
`vaultspec-core sync` after source-side changes when the goal is a complete
provider-facing workspace.

#### Examples

- **List all rules, skills, or agents configured in the current project**:

  ```bash
  vaultspec-core spec rules list
  ```

- **Create a new custom project-level rule**:

  ```bash
  vaultspec-core spec rules add enforce-newline --body "All workspace source files must end with a single trailing newline."
  ```

- **Create a new custom skill from a local template**:

  ```bash
  vaultspec-core spec skills add unit-test-runner --description "Run python pytest suite" --template "templates/skill_template.md"
  ```

- **Create a new custom agent persona**:

  ```bash
  vaultspec-core spec agents add database_expert --description "An expert database optimization agent"
  ```

- **Display the content of a project rule**:

  ```bash
  vaultspec-core spec rules show enforce-newline
  ```

- **Edit a project skill using a specified editor command**:

  ```bash
  vaultspec-core spec skills edit unit-test-runner --editor zed
  ```

- **Delete a project agent persona**:

  ```bash
  vaultspec-core spec agents remove database_expert --force
  ```

- **Rename a project-level rule atomically**:

  ```bash
  vaultspec-core spec rules rename old-rule-name new-rule-name
  ```

- **Synchronize local rules changes to enrolled provider output stubs**:

  ```bash
  vaultspec-core spec rules sync
  ```

- **Report parsing and synchronization status of project skills**:

  ```bash
  vaultspec-core spec skills status
  ```

- **Restore a default rule to its original snapshotted version**:

  ```bash
  vaultspec-core spec rules restore enforce-newline.builtin.md
  ```

______________________________________________________________________

### vaultspec-core spec system

```bash
vaultspec-core spec system [OPTIONS] COMMAND [ARGS]...
```

#### Subcommands

- `show` (`--json`) - Display system prompt parts and generation targets.
- `sync` (`--dry-run`, `--force`, `--json`) - Resource-scoped system prompt sync.

#### Examples

- **Display assembled system prompt configuration and composition**:

  ```bash
  vaultspec-core spec system show
  ```

- **Synchronize system prompts and stubs to provider workspaces**:

  ```bash
  vaultspec-core spec system sync
  ```

______________________________________________________________________

### vaultspec-core spec hooks

```bash
vaultspec-core spec hooks [OPTIONS] COMMAND [ARGS]...
```

#### Subcommands

- `list` - List hooks with name, status, event, and action count.
- `add [NAME] [--event EVENT] [--command CMD] [--body BODY] [--from-file FILE] [--force] [--dry-run]`
  \- Add a new custom hook definition.
- `show NAME` - Display a hook's content.
- `edit NAME [--editor EDITOR]` - Open a hook in the configured editor.
- `rename OLD_NAME NEW_NAME` - Rename an existing hook atomically.
- `remove NAME [--yes|--force]` - Delete a hook.
- `restore FILENAME` - Restore a hook (not supported for custom hooks, exits with error
  1).
- `sync` (`--dry-run`, `--force`) - Sync only hooks files.
- `status` (`--json`) - Report declarative hooks parsing and taxonomy compliance status.
- `run EVENT [--path PATH]` - Trigger enabled hooks for the given event. Valid events:
  `vault.document.created`, `config.synced`, `audit.completed`.

#### Examples

- **Run all hooks registered for the document creation event**:

  ```bash
  vaultspec-core spec hooks run vault.document.created
  ```

- **List all registered hooks and their enabled/disabled status**:

  ```bash
  vaultspec-core spec hooks list
  ```

- **Add a new custom hook triggered on document creation**:

  ```bash
  vaultspec-core spec hooks add log-created --event vault.document.created --command "echo Created"
  ```

- **Display the definition and command block of a hook**:

  ```bash
  vaultspec-core spec hooks show log-created
  ```

- **Edit an existing hook definition using a configured editor**:

  ```bash
  vaultspec-core spec hooks edit log-created
  ```

- **Rename an existing hook atomically**:

  ```bash
  vaultspec-core spec hooks rename log-created document-logger
  ```

- **Remove/delete an obsolete hook**:

  ```bash
  vaultspec-core spec hooks remove document-logger --force
  ```

- **Check and report overall parsing and compliance status of hooks**:

  ```bash
  vaultspec-core spec hooks status
  ```

- **Synchronize local hook definitions**:

  ```bash
  vaultspec-core spec hooks sync
  ```

- **Restore a default hook to its original snapshotted version**:

  ```bash
  vaultspec-core spec hooks restore some-default-hook.json
  ```

______________________________________________________________________

### vaultspec-core spec gitignore

`vaultspec-core spec gitignore` and `vaultspec-core spec gitattributes` are not
available in the 0.1.73 release.

```bash
vaultspec-core spec gitignore [OPTIONS] COMMAND [ARGS]...
```

#### Subcommands

- `disable` (`--json`) - Decline the vaultspec-managed `.gitignore` block for the whole
  project.
- `enable` (`--json`) - Allow management of the `.gitignore` block for the whole
  project.

`disable` records `blocks.gitignore = false` in `.vaultspec/workspace.json`; commit this
file to share the policy. `enable` clears that override. Neither command edits
`.gitignore`; remove an existing managed block yourself if needed.

Install and upgrade create or restore the managed block unless project policy disables
it. Ordinary sync leaves a manually removed block absent on that machine. To restore it,
enable management and run `vaultspec-core install`.

Both commands exit zero when the requested policy already holds.

#### Options

- `--json` (default off) - Emit the result as JSON.
- `--target DIR` (`-t`, default cwd) - Act on a directory other than the current one.

#### Examples

- **Decline the block for the whole project**:

  ```bash
  vaultspec-core spec gitignore disable
  ```

- **Resume managing it**:

  ```bash
  vaultspec-core spec gitignore enable
  ```

### vaultspec-core spec gitattributes

```bash
vaultspec-core spec gitattributes [OPTIONS] COMMAND [ARGS]...
```

#### Subcommands

- `disable` (`--json`) - Decline the vaultspec-managed `.gitattributes` block for the
  whole project.
- `enable` (`--json`) - Allow management of the `.gitattributes` block for the whole
  project.

These controls share the
[availability and policy behavior of `vaultspec-core spec gitignore`](#vaultspec-core-spec-gitignore),
using `blocks.gitattributes` in `.vaultspec/workspace.json`. The
[default entries](../src/vaultspec_core/core/gitattributes.py) control line endings and
union merging of execution ledgers.

#### Options

- `--json` (default off) - Emit the result as JSON.
- `--target DIR` (`-t`, default cwd) - Act on a directory other than the current one.

#### Examples

- **Disable managed Git attributes for the project**:

  ```bash
  vaultspec-core spec gitattributes disable
  ```

- **Resume managing it**:

  ```bash
  vaultspec-core spec gitattributes enable
  ```

### vaultspec-core spec precommit

```bash
vaultspec-core spec precommit [OPTIONS] COMMAND [ARGS]...
```

#### Subcommands

- `disable` (`--json`) - Decline vaultspec-managed `.pre-commit-config.yaml`
  scaffolding.
- `enable` (`--json`) - Restore vaultspec-managed `.pre-commit-config.yaml` scaffolding.
- `migrate` (`--remove-yaml`, `--dry-run`, `--json`) - Transplant the canonical
  vaultspec hooks into `prek.toml`.

`disable` records `hooks.pre_commit = false` in `.vaultspec/workspace.json` to stop YAML
scaffolding. Commit this file to share the policy; `enable` clears the override. Neither
command changes existing configuration or uninstalls an active Git hook.

Install and upgrade can recreate missing YAML unless `--skip precommit`, project policy,
or an owning `prek.toml` prevents scaffolding. Ordinary sync leaves manually deleted
YAML absent. After enabling management, run `vaultspec-core install` to restore it.

With this policy disabled, reconciled ignore entries include `/.pre-commit-config.yaml`.
Ignoring a file does not untrack an existing committed copy. Both policy commands exit
zero when the requested state already holds.

When `prek.toml` owns the hook boundary, sync no longer scaffolds
`.pre-commit-config.yaml` and prek silently ignores it. `migrate` renders the canonical
hook set into a vaultspec-managed block inside `prek.toml`. It is idempotent -
re-running with the hooks already present is a no-op - and the superseded YAML config is
never deleted unless `--remove-yaml` is passed and the canonical hooks are verified
present in `prek.toml`.

#### Options

- `--remove-yaml` (default off, `migrate` only) - Also delete the superseded
  `.pre-commit-config.yaml` once the canonical hooks are verifiably present in
  `prek.toml`.
- `--dry-run` (default off, `migrate` only) - Preview without writing.
- `--json` (default off) - Emit the result as JSON.

#### Examples

- **Stop vaultspec from ever writing the hook config again**:

  ```bash
  vaultspec-core spec precommit disable
  ```

- **Restore managed scaffolding**:

  ```bash
  vaultspec-core spec precommit enable
  ```

- **Preview the transplant without writing**:

  ```bash
  vaultspec-core spec precommit migrate --dry-run
  ```

- **Transplant hooks, then remove the superseded YAML**:

  ```bash
  vaultspec-core spec precommit migrate --remove-yaml
  ```

### vaultspec-core spec mcps

```bash
vaultspec-core spec mcps [OPTIONS] COMMAND [ARGS]...
```

Manage canonical MCP server definitions in `.vaultspec/mcps/*.json` and reconcile them
into provider-native enrollment files. Provider targets are `all`, `claude`,
`antigravity`, and `codex`; scopes are `project`, `local`, and `user`. Unsupported
provider/scope combinations fail instead of writing to a substitute location. Use
top-level `vaultspec-core sync` for a complete refresh across all provider-facing
outputs.

#### Subcommands

- `vaultspec-core spec mcps list` - List all registered MCP server definitions.
- `vaultspec-core spec mcps status [PROVIDER]` (`--scope SCOPE`, `--json`,
  `--target PATH`) - Inspect enrollment and ownership state without starting or probing
  MCP servers.
- `vaultspec-core spec mcps add --name NAME [--config JSON] [--force]` - Add a new
  custom MCP server definition.
- `vaultspec-core spec mcps remove NAME [--force]` - Remove an MCP server definition
  (`--force` skips confirmation).
- `vaultspec-core spec mcps sync [PROVIDER]` (`--scope SCOPE`, `--dry-run`, `--force`,
  `--prune`, `--json`, `--target PATH`) - Reconcile canonical definitions into
  provider-native enrollment.
- `vaultspec-core spec mcps uninstall [PROVIDER]` (`--scope SCOPE`, `--dry-run`,
  `--force`, `--json`, `--target PATH`) - Remove only vaultspec-owned provider-native
  enrollment.

`vaultspec-core spec mcps status` exits `0` only when MCP config status is `ok`,
otherwise `1`. It checks config health only and does not start or probe MCP server
processes. The default provider is `all` and the default scope is `project`. `--force`
on `sync` explicitly adopts or replaces same-name external enrollment; `--prune` removes
owned enrollment whose canonical source was deleted. `uninstall` preserves canonical
definitions and externally owned host entries.

#### Examples

- **Verify the health and synchronization status of MCP server definitions**:

  ```bash
  vaultspec-core spec mcps status
  ```

- **List all registered MCP server definitions**:

  ```bash
  vaultspec-core spec mcps list
  ```

- **Sync registered MCP definitions to deployment files**:

  ```bash
  vaultspec-core spec mcps sync
  ```

- **Inspect Codex project enrollment**:

  ```bash
  vaultspec-core spec mcps status codex --scope project
  ```

- **Preview removal of vaultspec-owned Claude user enrollment**:

  ```bash
  vaultspec-core spec mcps uninstall claude --scope user --dry-run
  ```

- **Register a new custom MCP server definition**:

  ```bash
  vaultspec-core spec mcps add --name sqlite-mcp --config "{\"command\": \"npx\", \"args\": [\"@modelcontextprotocol/server-sqlite\"]}"
  ```

- **Remove a registered MCP server definition**:

  ```bash
  vaultspec-core spec mcps remove sqlite-mcp --force
  ```

### vaultspec-core spec reference

```bash
vaultspec-core spec reference generate [OPTIONS]
```

Regenerate the generator-owned regions of the bundled machine-facing CLI reference
(`src/vaultspec_core/builtins/reference/cli.md`) from the live Typer command surface.
The reference is a hybrid of hand-written prose and generator-owned zones delimited by
`vaultspec:generated` HTML-comment markers; this verb rewrites only the managed zones
and leaves the prose untouched.

- `--check` (default off) - Render in memory, diff against the committed file, exit
  non-zero on mismatch without writing.
- `--json` (default off) - Emit machine-readable output.

Default (write) mode rewrites the bundled reference in place when the managed regions
have drifted. `--check` mode is the CI and pre-commit entry point: it renders into
memory, prints a unified diff on mismatch, and exits non-zero, leaving the file
untouched (exit 0 when already in sync).

- **Refresh the bundled reference after a command or flag change**:

  ```bash
  vaultspec-core spec reference generate
  ```

- **Verify the bundled reference is up to date (CI gate)**:

  ```bash
  vaultspec-core spec reference generate --check
  ```

## Migration commands

Group command: `vaultspec-core migrations [OPTIONS] COMMAND [ARGS]...`

Every migration subcommand also accepts the global `--target / -t DIR` and `--json`
flags.

The migration registry runs every entry whose target version exceeds the workspace
manifest's `vaultspec_version`, then bumps the manifest version on success. Migrations
are idempotent, and because they relocate, rewrite, and delete tracked `.vault/`
documents they only run for a caller that asked to change the workspace:

- `vaultspec-core install --upgrade`, `vaultspec-core migrations run`, and
  `vaultspec-core vault repair` - converging is what you invoked them for.
- `vaultspec-core vault add` and `vaultspec-core vault feature index` - the schema
  decides where their write lands, so they converge before authoring.

Every other command, including every read (`vaultspec-core vault list`,
`vaultspec-core vault graph`, `vaultspec-core vault check`, and the MCP query tools),
leaves the workspace exactly as it finds it and logs a warning naming the pending
entries instead. Run `vaultspec-core migrations status` to see them, and
`vaultspec-core migrations run` to apply them.

### vaultspec-core migrations status

```bash
vaultspec-core migrations status [OPTIONS]
```

List registered migrations and which entries are pending against the current workspace
manifest. Read-only; never mutates.

#### Options

- `--target DIR` (`-t`, default cwd) - Inspect a workspace other than the current
  directory.
- `--json` (default off) - Emit status, registered list, and pending list as JSON.

Exit codes: `0` when up to date or workspace has no manifest, `1` when migrations are
pending.

#### Examples

- **List all registered schema migrations and check for pending entries**:

  ```bash
  vaultspec-core migrations status
  ```

______________________________________________________________________

### vaultspec-core migrations run

```bash
vaultspec-core migrations run [OPTIONS]
```

Apply every pending migration in version order and bump the manifest's
`vaultspec_version`. A migration that fails stops the run and leaves the manifest
unchanged so the next invocation re-attempts it.

#### Options

- `--target DIR` (`-t`, default cwd) - Migrate a workspace other than the current
  directory.
- `--json` (default off) - Emit per-entry summaries and counts as JSON.

Exit codes: `0` on success (including the no-pending no-op), `1` if any migration
failed.

#### Examples

- **Execute all pending schema migrations and upgrade the workspace**:

  ```bash
  vaultspec-core migrations run
  ```

______________________________________________________________________

## Config commands

Group command: `vaultspec-core config [OPTIONS] COMMAND [ARGS]...`

Manage local project configuration settings stored in `.vaultspec/config.toml` at the
workspace root.

Every config subcommand also accepts the global `--target / -t DIR` and `--json` flags.

### vaultspec-core config get

```bash
vaultspec-core config get [OPTIONS] KEY
```

Read a local configuration value.

#### Options

- `--json` (default off) - Emit machine-readable output.

#### Examples

- **Retrieve the local project-level editor setting**:

  ```bash
  vaultspec-core config get editor
  ```

### vaultspec-core config set

```bash
vaultspec-core config set [OPTIONS] KEY VALUE
```

Write a local configuration value. Supported keys: `editor`.

#### Options

- `--json` (default off) - Emit machine-readable output.

#### Examples

- **Configure the local project-level editor command to Zed**:

  ```bash
  vaultspec-core config set editor zed
  ```

### vaultspec-core config unset

```bash
vaultspec-core config unset [OPTIONS] KEY
```

Clear a local configuration entry.

#### Options

- `--json` (default off) - Emit machine-readable output.

#### Examples

- **Clear the local project-level editor configuration**:

  ```bash
  vaultspec-core config unset editor
  ```

### vaultspec-core config list

```bash
vaultspec-core config list [OPTIONS]
```

Enumerate all known configuration entries and current values.

#### Options

- `--json` (default off) - Emit machine-readable output.

#### Examples

- **Enumerate all local project-level configuration settings and values**:

  ```bash
  vaultspec-core config list
  ```

______________________________________________________________________

## Environment variables

All variables are prefixed `VAULTSPEC_`. Environment variables override defaults but are
overridden by the `--target` flag.

- `VAULTSPEC_TARGET_DIR` (path, default cwd) - Root workspace directory (where `.vault/`
  and `.vaultspec/` live). Equivalent to `--target` on the CLI. Also used by
  `vaultspec-mcp` to locate the workspace. Defaults to the current working directory if
  unset.
- `VAULTSPEC_DOCS_DIR` (str, default `.vault`) - Vault directory name.
- `VAULTSPEC_INDEX_DIR` (str, default `index`) - Name of the subdirectory inside the
  vault that holds the auto-generated feature indexes (`<feature>.index.md`).
- `VAULTSPEC_FRAMEWORK_DIR` (str, default `.vaultspec`) - Framework directory name.
- `VAULTSPEC_CLAUDE_DIR` (str, default `.claude`) - Claude tool directory name.
- `VAULTSPEC_GEMINI_DIR` (str, default `.gemini`) - Gemini tool directory name.
- `VAULTSPEC_ANTIGRAVITY_DIR` (str, default `.agents`) - Antigravity directory name.
- `VAULTSPEC_IO_BUFFER_SIZE` (int, default `8192`) - I/O read buffer size in bytes.
- `VAULTSPEC_TERMINAL_OUTPUT_LIMIT` (int, default `1000000`) - Subprocess stdout capture
  limit in bytes.
- `VAULTSPEC_LOG_LEVEL` (str, default `INFO`) - Root log level for the CLI, for example
  `DEBUG`, `INFO`, or `WARNING`. Overridden by `--debug` when set.
- `VAULTSPEC_EDITOR` (str, default `zed -w`) - Editor command for
  `vaultspec-core spec {rules|skills|agents} edit`. Overridden by the project-local
  config `editor` value, and the `--editor` flag. Resolved in order: `--editor` flag,
  project config, `$VISUAL`, `$EDITOR`/`VAULTSPEC_EDITOR`, `vi`.
- `VAULTSPEC_JSON_PRETTY` (str, unset by default) - Indents `--json` output. Any value
  other than `0`, `false`, `no`, `off`, or the empty string turns it on; without it the
  envelope is written as one compact line.
- `VAULTSPEC_NO_HINTS` (str, unset by default) - Set to `1` to drop the `Next actions`
  block the commands print after their report. Equivalent to `--no-hints`. Only the
  exact value `1` counts; anything else leaves the hints in place.
- `VAULTSPEC_STDIO_WATCHDOG` (str, default on) - Lifetime watchdog for the MCP server.
  Set it to `0`, `false`, `off`, or `no` to disable it, which leaves the server to exit
  on stdin EOF alone. Read by `vaultspec-mcp` rather than by the CLI; see the
  [MCP reference](./MCP.md).

## See also

- [Framework manual](./framework.md) - Development workflow, skills, and customization.
- [MCP reference](./MCP.md) - MCP server tools, setup, and configuration.

For bug reports and feature requests, open an issue on the
[vaultspec-core issue tracker](https://github.com/nevenincs/vaultspec-core/issues).
