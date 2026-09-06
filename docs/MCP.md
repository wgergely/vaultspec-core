# vaultspec MCP server

The server exposes Vaultspec document and workflow tools to Model Context Protocol (MCP)
clients using JSON-RPC over standard input and output.

For the workflow and document types, see
[workflow stages](./framework.md#workflow-stages).

## Setup

vaultspec keeps provider-neutral MCP definitions in `.vaultspec/mcps/*.json`.
Installation and `vaultspec-core spec mcps sync` render those definitions into each
selected provider's native configuration:

| Provider    | Project scope             | Broader scope                                                            |
| ----------- | ------------------------- | ------------------------------------------------------------------------ |
| Claude      | `.mcp.json`               | Local or user enrollment in `~/.claude.json`                             |
| Codex       | `.codex/config.toml`      | User enrollment in `$CODEX_HOME/config.toml`; local scope is unsupported |
| Antigravity | `.agents/mcp_config.json` | Broader scopes are unsupported                                           |

Project scope is the safe default. Select user or local scope explicitly. Native host
files contain only host-valid configuration; vaultspec records project and local
ownership in the workspace's `.vaultspec/mcp-ownership.json` and user ownership in
`~/.vaultspec/mcp-ownership.json`, so unrelated host entries remain external. Use
`vaultspec-core install --skip mcp` if you manage enrollment yourself.

The server resolves its workspace from the client's current working directory.
Editor-integrated clients such as Claude Code and Cursor already set the working
directory to the project root, so this configuration needs no further changes to run
there.

The config invokes the server as a Python module
(`python -m vaultspec_core.mcp_server.app`) rather than the `vaultspec-mcp` console
script. On Windows, MCP clients lock the console-script executable in `.venv/Scripts/`,
which blocks `uv sync` and other package operations while the client is connected.
Module invocation avoids the lock.

> The module path above is the canonical invocation for this reason. The `vaultspec-mcp`
> console script itself remains core-owned; other packages in the vaultspec family name
> their own console scripts distinctly (for example, vaultspec-a2a's is
> `vaultspec-a2a-mcp`) rather than colliding with it.

This is the entry the installer renders into `.mcp.json` on a project installed the
default way. Antigravity's `.agents/mcp_config.json` is byte-identical:

```json
{
  "mcpServers": {
    "vaultspec-core": {
      "command": "uvx",
      "args": [
        "--from",
        "vaultspec-core",
        "python",
        "-m",
        "vaultspec_core.mcp_server.app"
      ]
    }
  }
}
```

Codex takes the same invocation as TOML, inside a marked region the installer owns:

```toml
# <vaultspec type="mcps">
[mcp_servers."vaultspec-core"]
args = ["--from", "vaultspec-core", "python", "-m", "vaultspec_core.mcp_server.app"]
command = "uvx"
# </vaultspec>
```

The launch shape follows the install mode rather than being fixed: a project that
carries vaultspec-core as a dependency gets `uv run --no-sync` with no `--from`, because
the environment already has the package. Compare against these when you manage
enrollment yourself, and read the markers as ownership boundaries: edit inside them and
the next sync declines to touch the entry rather than repairing it.

### Serving a read-only surface

Use `--read-only` to limit the tools the server advertises:

```bash
vaultspec-mcp --read-only
```

This exposes only `status`, `find`, `check`, and `discover` to connected clients. In
this mode, `check` has no `fix` parameter.

### Install modes

For Core's generated MCP entry, the install mode determines how the server starts:

- **Tool:** `uvx` uses an isolated tool environment and may download dependencies or
  create that environment at launch. See
  [uv's tool environments](https://docs.astral.sh/uv/concepts/tools/#tool-environments).
- **Dev or dependency:** `uv run --no-sync` skips project environment synchronization.
  Prepare that environment using your project's `uv sync` procedure before connecting.

See [install mode selection](CLI.md#install) for precedence and dependency declarations.

### Convergence on upgrade

Launch entries that vaultspec wrote converge to the current standard automatically. A
managed entry whose bytes still match the fingerprint recorded when vaultspec last wrote
it is provably untouched, so `vaultspec-core sync`, `vaultspec-core spec mcps sync`, and
`vaultspec-core install --upgrade` all refresh it in place - no `--force` required - and
print exactly what changed: the entry name, the old launch command, the new launch
command, and why. A registered migration applies the same refresh the first time any
`vaultspec-core vault ...` command runs in a workspace provisioned by an earlier
release, so a launch rendered before the `--no-sync` guard existed (a bare `uv run`
shape) converges on the workspace's next contact with the CLI, whatever its provisioned
version.

Two kinds of entry never converge automatically. An entry you edited by hand (its bytes
no longer match the recorded fingerprint) is skipped with a warning and requires an
explicit `vaultspec-core spec mcps sync --force`, which overwrites your edit. An entry
recorded by a release that predates fingerprinting cannot be verified as untouched and
keeps the same `--force`-only behavior. External entries vaultspec never wrote are never
adopted or modified without `--force`. To opt out of enrollment management entirely,
provision with `vaultspec-core install --skip mcp`; a workspace without recorded
enrollment is never touched by the convergence migration.

`vaultspec-core spec doctor` additionally warns - without failing - about two states
vaultspec cannot converge itself: canonical hooks that cannot be refreshed because
`prek.toml` is present (transplant the entries manually), and a package-bundled seed
definition still in a static pre-mode shape (re-run that package's installer with
`--upgrade`).

Select a mode with `vaultspec-core install --mode tool`,
`vaultspec-core install --mode dependency`, or `vaultspec-core install --mode dev`.
vaultspec consumes the package, module, and optional tool requirement while rendering;
that metadata never reaches native host configuration.

The chosen mode is recorded per package in the workspace's committed `workspace.json`,
which keys each provisioned package to its own mode and version floor. A workspace that
provisions both vaultspec-core and a companion package can therefore declare each in a
different mode - one as a dependency, the other as a tool - without either overwriting
the other's choice.

A workspace set up before install modes existed carries no recorded choice. Running
`vaultspec-core install --upgrade` infers the mode from how the workspace already runs -
a `uv run`-shaped setup that lists vaultspec-core as a dependency stays in dependency
mode, and anything else moves to tool mode - and records it, so the launch command stays
stable from then on.

### Point the server at a different workspace

When the client's working directory isn't the workspace you want - for example in a
standalone setup outside an editor - set `VAULTSPEC_TARGET_DIR` in the canonical MCP
definition's `env` map, then run `vaultspec-core spec mcps sync`. The provider adapter
renders normalized `command`, `args`, and `env` fields into each selected native target.

`VAULTSPEC_TARGET_DIR` is the environment equivalent of the CLI's `--target` flag.

### Your first call

Claude reads project enrollment from `.mcp.json`. Codex reads `.codex/config.toml` for a
trusted project. Antigravity uses `.agents/mcp_config.json`. Reload or reconnect the
provider as required by that host. vaultspec writes enrollment only: it does not start
the server, grant trust, or bypass provider approval.

Call the `status` tool with no arguments. It returns a rollup report:
`tool_schema_version`, the workspace's features with document counts and lifecycle
status, and any plans in flight with their completion and next open step. A populated
report confirms the server found the workspace.

Call `find` with no arguments. It returns the feature listing, for example
`[{"name": "auth", "doc_count": 4, "weight": 7}, ...]`. A non-empty listing confirms the
vault is readable. Follow up with `find(feature=...)` to fetch a feature's documents,
each with a `blob_hash` ready for a later `edit` call.

## Environment

| Variable                   | Default                   | Controls                                                                                                             |
| -------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `VAULTSPEC_TARGET_DIR`     | current working directory | The workspace root containing `.vault/` and `.vaultspec/`. Equivalent to `--target` on the CLI.                      |
| `VAULTSPEC_STDIO_WATCHDOG` | enabled                   | Set to `0`, `false`, `off`, or `no` to disable the stdio lifetime watchdog. See [Server lifetime](#server-lifetime). |

Those are the two `VAULTSPEC_` variables the MCP server reads directly. See
[CLI reference](./CLI.md) for the full `VAULTSPEC_` variable family.

## Verification

```console
vaultspec-core spec mcps status
vaultspec-core spec mcps status codex --scope project
vaultspec-core spec mcps status --json
```

Status reports aggregate and per-provider configuration health. It identifies managed,
missing, drifted, stale managed, and external entries, plus warnings. It does not start
or probe an MCP process. The command exits 0 only when aggregate status is `"ok"`.

If status isn't `"ok"`, inspect the `missing`, `drifted`, `stale_managed`, and
`warnings` fields, run `vaultspec-core spec mcps sync` to reconcile enrollment, then
re-run the status check. Project scope is the default; user or local enrollment must be
requested explicitly, and unsupported provider/scope combinations fail.

Run `vaultspec-core spec doctor --json` for a broader workspace diagnosis.

## Tools

The server exposes ten tools. Eight cover the everyday path: `status` orients you in the
workspace, `find` locates documents, `create` scaffolds new ones, `edit` makes
body-prose changes, `check` validates and repairs the vault, `plan_progress` marks steps
complete, `plan_edit` authors step content, and `log` appends a step's rows to the
plan's execution ledger. Two more, `discover` and `invoke`, form a gateway that reaches
every remaining CLI verb.

| Tool            | Purpose                                                                                        | Annotations                     |
| --------------- | ---------------------------------------------------------------------------------------------- | ------------------------------- |
| `status`        | Get a project rollup or trace a feature or plan to its steps and records                       | read-only, idempotent           |
| `find`          | Search documents or list features, with blob hashes and resource links                         | read-only, idempotent           |
| `create`        | Batch-scaffold `.vault/` documents from templates and regenerate affected feature indexes      | non-destructive, not idempotent |
| `edit`          | Batch body-prose edits through section-addressed operations, guarded by optimistic concurrency | destructive, not idempotent     |
| `check`         | Run vault health checks, optionally with repair                                                | non-destructive, idempotent     |
| `plan_progress` | Batch-mark plan steps checked or unchecked                                                     | non-destructive, idempotent     |
| `plan_edit`     | Batch add, insert, edit, or remove step-authoring operations on a plan                         | destructive, not idempotent     |
| `log`           | Append one step's rows (paths, verify, persona, notes) to the plan's execution ledger          | non-destructive, idempotent     |
| `discover`      | Search the long-tail verb catalog for ranked verbs and their parameter schemas                 | read-only, idempotent           |
| `invoke`        | Run one cataloged long-tail verb as a validated subprocess                                     | destructive, not idempotent     |

Two bands of operations sit outside these ten tools.

The gateway reaches some operations, but a CLI command carries them by default:
synchronizing generated surfaces (`vaultspec-core sync`,
`vaultspec-core spec <resource> sync`) and restructuring a plan above the step level
(`vaultspec-core vault plan tier promote`, `tier demote`, and the `wave`, `phase`, and
`epic intent` verbs). Every `invoke` call carries the destructive-operation annotation,
so a connected host still asks you to confirm each one; the CLI skips that round-trip.

Other operations have no MCP path at all. Regenerating a feature index runs through
`vaultspec-core vault feature index`. For MCP configuration, `list`, `add`, and `remove`
inspect or mutate canonical definitions; `status` inspects native enrollment and
ownership health; `sync` reconciles definitions into selected targets; and `uninstall`
removes vaultspec-owned enrollment while preserving canonical definitions and external
host entries. Removing vaultspec from a workspace runs through
`vaultspec-core uninstall`.

### Terms

- **Canonical identifier**: the stable `W##`, `P##`, or `S##` label a plan container
  keeps for its entire life. A retired identifier is never reused, so gaps in the
  sequence are expected. The display path you see, such as `P01.S02`, is computed for
  reading; the canonical identifier is the durable handle underneath it.
- **Body prose versus CLI-owned structure**: frontmatter, filenames, and plan-table
  structure belong to the CLI and its owning verbs. Body prose in a scaffolded document
  is the surface you edit by hand.
- **Feature index**: an auto-generated document at `.vault/index/<feature>.index.md`
  that lists every document belonging to a feature. It regenerates automatically when a
  `create` batch succeeds.
- **Destructive-operation annotation**: the MCP `destructiveHint` marked on a tool. A
  connected host reads this hint and asks you to confirm before it runs a call carrying
  it.

### `find`

Find vault documents or list features. Read-only, idempotent.

With no arguments, `find` lists features: each row gives a feature's name, document
count, and graph weight. Pass any filter (`feature`, `type`, `date`, or `text`) and
`find` switches to search mode, returning matching documents instead.

| Parameter | Type                         | Default | Description                                                                                                                                                                                                                                                                                        |
| --------- | ---------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `feature` | string or null               | `null`  | Feature filter, without the `#` prefix. Passing it switches `find` to search mode.                                                                                                                                                                                                                 |
| `type`    | list of strings or null      | `null`  | Document-type filter (for example, `adr`, `plan`, `research`, `reference`). Passing it switches `find` to search mode. In search mode with no `type` given, the default set is `adr`, `plan`, `research`, and `reference`; `exec` and `audit` documents appear only when you name them explicitly. |
| `date`    | string or null               | `null`  | Exact ISO-8601 date filter. Passing it switches `find` to search mode.                                                                                                                                                                                                                             |
| `text`    | string or null               | `null`  | Case-insensitive substring over the document stem and feature tag. Composes with the other filters, and matches identifiers rather than body prose. Passing it switches `find` to search mode.                                                                                                     |
| `body`    | `none`, `excerpt`, or `full` | `none`  | In search mode, how much document text to inline in each row. This is an enum, not a boolean: passing `true` is rejected by schema validation.                                                                                                                                                     |
| `json`    | boolean                      | `false` | In feature-listing mode, enrich each row with `status`, `types`, `earliest_date`, and `has_plan`.                                                                                                                                                                                                  |
| `limit`   | integer, 1 to 100            | `20`    | Maximum number of rows to return.                                                                                                                                                                                                                                                                  |

Behavior notes:

- Feature-listing rows report `name`, `doc_count`, and `weight` (a graph-ranking score).
  `weight` is `0` when the dependency graph can't be built, and the row notes that the
  ranking is unavailable.
- Document-search rows report `name` (the file stem), `type`, `feature`, `date`, `path`
  (relative to the vault), `blob_hash` (the git blob object ID (OID) of the document's
  current bytes, or `null` if the file can't be read), `resource_uri` (a `file://`
  link), and `body` when you set `body` to `excerpt` or `full`.
- In search mode, `limit` is a global cap applied across all matched types combined, not
  a per-type cap. If an early type fills the cap, later types can be crowded out
  entirely. Call `find` once per type when you need a fair spread across types.
- `find` never raises an error for filters that match nothing; an empty result comes
  back as an empty list.

Example feature-listing response:

```json
[
  {"name": "auth", "doc_count": 4, "weight": 7},
  {"name": "search-api", "doc_count": 2, "weight": 3}
]
```

Example document-search response row:

```json
{
  "name": "2026-07-11-search-api-research",
  "type": "research",
  "feature": "search-api",
  "date": "2026-07-11",
  "path": ".vault/research/2026-07-11-search-api-research.md",
  "blob_hash": "<git blob OID>",
  "resource_uri": "file:///.../2026-07-11-search-api-research.md"
}
```

______________________________________________________________________

### The batch envelope

`create`, `edit`, `plan_progress`, and `plan_edit` take a list and return one envelope
describing the whole call:

| Field           | Type                    | Meaning                                                                                      |
| --------------- | ----------------------- | -------------------------------------------------------------------------------------------- |
| `status`        | `ok`, `mixed`, `failed` | `ok` when every item succeeded, `failed` when every item failed, `mixed` when they disagree. |
| `items`         | list                    | Item rows. See the sampling rule below.                                                      |
| `counts`        | object                  | How many items landed in each status. Exact regardless of sampling.                          |
| `submitted`     | integer                 | How many items were in the request.                                                          |
| `items_omitted` | integer                 | Uneventful successes left out of `items`.                                                    |

**`items` is a sample, not the full list.** It carries every failure and every item that
produced a warning, plus some plain successes; the rest are counted in `items_omitted`.
A client that tallies `items` to learn what happened will undercount on a large batch.
Read `counts` for the outcome and `items` for the detail.

A partially failed batch is still a successful call. It returns `status: "mixed"` and
reports each item's outcome rather than raising a protocol error. Only a malformed
request fails the call itself.

______________________________________________________________________

### `create`

Scaffold one or more vault documents from templates. Mutates the vault; not idempotent.

`create` takes a single parameter, `documents`, a list of document specifications with
at least one entry.

| Field     | Type                    | Default            | Description                                                                                                                                                                                                                                          |
| --------- | ----------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `feature` | string                  | none               | **Required.** Feature tag, in kebab-case. A leading `#` is stripped if present.                                                                                                                                                                      |
| `type`    | string or null          | `"research"`       | Document type: `research`, `adr`, `plan`, `reference`, or `audit`. `create` rejects `index` (auto-generated) and `exec` (execution is logged with `log`).                                                                                            |
| `title`   | string or null          | `null`             | Rendered into the document's heading.                                                                                                                                                                                                                |
| `date`    | string or null          | today's date (UTC) | ISO-8601 date.                                                                                                                                                                                                                                       |
| `content` | string or null          | `null`             | Seed prose, appended under a `## Context` heading. If seeding fails, `create` still creates the document and reports the failure as a warning rather than an error.                                                                                  |
| `related` | list of strings or null | `null`             | Documents to link in the `related:` frontmatter, resolved to `[[wiki-link]]` entries. Accepts a path, filename, stem, or an existing `[[wiki-link]]`.                                                                                                |
| `tags`    | list of strings or null | `null`             | Only the document's required directory and feature tags. Duplicates are ignored; other tags fail the item before writing. Omit for ordinary creation.                                                                                                |
| `tier`    | string or null          | `"L1"` for plans   | Plan complexity tier, one of `L1` through `L4`. Ignored for non-plan document types.                                                                                                                                                                 |
| `topic`   | string or null          | `null`             | Kebab-case filename infix that distinguishes a second document of the same type for one feature (`{date}-{feature}-{topic}-{type}.md`). Valid only for `adr`, `audit`, `reference`, and `research`. Mirrors `--topic` on `vaultspec-core vault add`. |

Behavior notes:

- `create` reads the template at `.vaultspec/templates/{type}.md`, fills its
  placeholders, and writes the document to `.vault/{type}/{date}-{feature}-{type}.md`;
  you don't set the filename directly.
- Items in a batch apply in order, and one item's failure doesn't abort the rest of the
  batch. Because each item validates against a vault that already includes the batch's
  earlier writes, a single call can create a full dependency chain, such as a research
  document followed by the ADR and plan that depend on it.
- On success, `create` regenerates the feature index for every feature that received at
  least one successfully created document.
- An empty `documents` list is a whole-call error, distinct from a per-item failure.

`create` can fail an item for these reasons:

- an invalid feature tag, extra tag, tier, or document type
- a request for type `index` (index documents are auto-generated; use the feature-index
  verb instead)
- an unresolvable `related` reference
- a lifecycle-dependency error (for example, requesting an `exec` document before its
  plan exists)
- a missing template
- a file that already exists

Example item, from the `items` list:

```json
{
  "index": 0,
  "target": "adr:search-api",
  "status": "created",
  "path": ".vault/adr/2026-07-12-search-api-adr.md",
  "blob_hash": "<oid>",
  "error": null,
  "warnings": []
}
```

Example failure item, in a batch whose overall status is `"mixed"`:

```json
{
  "index": 1,
  "target": "exec:search-api",
  "status": "failed",
  "path": null,
  "blob_hash": null,
  "error": {"message": "... requires a plan ..."},
  "warnings": []
}
```

______________________________________________________________________

### `edit`

Apply one or more body-prose edits to existing vault documents. Mutates the vault; not
idempotent, and `set_body` and `replace_section` overwrite existing prose.

`edit` takes a single parameter, `operations`, a list of edit operations with at least
one entry.

| Field                | Type           | Default | Description                                                                                                                              |
| -------------------- | -------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `target`             | string         | none    | **Required.** The document to edit: a stem, filename, path, or `[[wiki-link]]`. Any address form valid in a `related:` field works here. |
| `operation`          | string         | none    | **Required.** One of `append_section`, `replace_section`, or `set_body`.                                                                 |
| `content`            | string         | none    | **Required.** For `set_body`, the document's full body. For the section operations, the prose to insert or substitute.                   |
| `section`            | string or null | `null`  | Exact heading-line text, for example `"## Context"`. **Required** for `append_section` and `replace_section`.                            |
| `expected_blob_hash` | string or null | `null`  | Optimistic-concurrency guard. If the document's current blob hash doesn't match, the item fails as a conflict and `edit` makes no write. |

`edit` changes body prose only: it strips frontmatter before composing the new body,
never touches frontmatter, and never renames files. `set_body` replaces the whole body
while preserving frontmatter. `append_section` inserts `content` after the matched
section; `replace_section` keeps the heading and swaps the prose beneath it. Section
matching is exact against the heading-line text; a heading that doesn't match fails the
item with `"section_not_found": true`.

Batches apply sequentially, and one item's failure doesn't abort the rest. Multiple
operations against the same document chain correctly: only the first operation needs
`expected_blob_hash`, and each later operation validates against what the prior
operation just wrote, so a `blob_hash` returned by one call can guard a later call.

`edit` can fail an item for these reasons:

- an unknown operation
- a missing `section` field on a section operation
- an unresolvable target (reported as `"Cannot resolve document: '...'"`)
- a blob-hash conflict (reported with `"conflict": true`, and the file left untouched)

An empty `operations` list is a whole-call error, distinct from a per-item failure.

Example success item:

```json
{
  "index": 0,
  "target": "2026-07-12-search-api-adr",
  "status": "updated",
  "path": ".vault/adr/2026-07-12-search-api-adr.md",
  "blob_hash": "<post-write oid>",
  "error": null,
  "warnings": []
}
```

Example conflict item:

```json
{
  "index": 0,
  "target": "...",
  "status": "failed",
  "blob_hash": null,
  "error": {"message": "...", "conflict": true},
  "warnings": []
}
```

______________________________________________________________________

### `status`

Orient in a vaultspec project, project-wide or targeted at one feature or plan.
Read-only, idempotent.

| Parameter | Type           | Default | Description                                                           |
| --------- | -------------- | ------- | --------------------------------------------------------------------- |
| `target`  | string or null | `null`  | A feature tag or a plan stem/path. Omit it for a project-wide rollup. |

Call `status` without a target to get a rollup: the features in the vault (name,
document count, latest activity, whether a plan exists, lifecycle status, plan tier, and
plan completion percent), the plans currently in flight (stem, feature, tier, open and
closed step counts, completion percent, and the next open step), and vault-wide totals.
Every response carries a `tool_schema_version` field so a client can detect a server
upgrade.

Pass a target to trace one plan or feature instead. The response then reports each
plan's steps in full detail (canonical ID, display path, checked state, the ledger stem
when rows exist, the row count, and the last `verify:` result), the grounding documents
behind the plan (grouped by document type), and any exec documents that name no step. A
target that resolves to no plan or feature fails the whole call with a protocol error.
`status` returns no hashes; get a `blob_hash` from `find` to guard an edit.

Rollup example, captured against this project's own vault and cut to one feature and one
plan of the eleven and four it returned:

```json
{
  "tool_schema_version": "0.1.73",
  "kind": "rollup",
  "features": [
    {
      "name": "docs-site",
      "doc_count": 115,
      "latest_activity": "2026-09-02",
      "has_plan": true,
      "status": "In Progress",
      "plan_tier": "L3",
      "plan_completion_percent": 99.1
    }
  ],
  "features_total": 11,
  "plans_in_flight": [
    {
      "stem": "2026-08-28-docs-site-plan",
      "feature": "docs-site",
      "tier": "L3",
      "open_steps": 1,
      "closed_steps": 110,
      "total_steps": 111,
      "completion_percent": 99.1,
      "next_open_step": "W09.P18.S109"
    }
  ],
  "totals": {
    "total_docs": 394,
    "total_features": 11,
    "counts_by_type": { "adr": 14, "audit": 15, "plan": 11, "exec": 327 },
    "orphaned_count": 0,
    "dangling_link_count": 0
  },
  "plans": []
}
```

`status` on a feature is written for a person - `In Progress`, `Completed` - rather than
as a slug, so match it exactly rather than assuming a lowercase hyphenated form.
`counts_by_type` above is cut to four of its seven keys.

Trace example:

```json
{
  "kind": "trace",
  "trace_kind": "feature",
  "target": "search-api",
  "plans": [
    {
      "stem": "2026-07-12-search-api-plan",
      "steps": [
        { "canonical_id": "S01", "display_path": "S01", "checked": true, "record_stem": null }
      ]
    }
  ]
}
```

______________________________________________________________________

### `check`

Run the vault health-check suite and, when asked, apply safe repairs. Not read-only, not
destructive, idempotent - a repair never overwrites authored prose, so running it again
converges on the same clean state.

| Parameter | Type           | Default | Description                                                    |
| --------- | -------------- | ------- | -------------------------------------------------------------- |
| `feature` | string or null | `null`  | Restrict the check to one feature tag, without the `#` prefix. |
| `fix`     | boolean        | `false` | Apply safe auto-corrections instead of only reporting them.    |

The response reports an overall `status`: `"ok"` when the total error count is zero,
`"failed"` otherwise. Warnings alone don't fail a check. Alongside `status`, the
response carries `fixed` (whether a repair ran), `total_errors`, `total_warnings`,
`total_fixed`, a `checks` array with one summary row per validator (error, warning,
info, and fixed counts, plus a `clean` flag), and a `findings` array listing every error
and warning (informational diagnostics are dropped). Each finding names the check that
raised it, the affected path, a message, its severity, and whether it's `fixable`.

Set `fix` to `true` to apply safe corrections in the same call. The response then
reports `fixed: true`, and if every issue found was auto-fixable, `status` returns to
`"ok"`.

Clean example:

```json
{
  "status": "ok",
  "fixed": false,
  "total_errors": 0,
  "total_warnings": 0,
  "total_fixed": 0,
  "checks": [{ "check": "dangling", "error_count": 0, "warning_count": 0, "info_count": 0, "fixed_count": 0, "clean": true }],
  "findings": []
}
```

Finding example:

```json
{
  "check": "dangling",
  "path": ".vault/adr/2026-07-01-search-api-adr.md",
  "message": "wiki-link target not found",
  "severity": "error",
  "fixable": false
}
```

______________________________________________________________________

### `plan_progress`

Mark plan steps checked or unchecked by canonical identifier. There's no toggle
operation - each step change states its target explicitly, which keeps the tool
idempotent. Not read-only, not destructive, idempotent.

| Parameter | Type                       | Default                          | Description                                                                                                                                                                                                     |
| --------- | -------------------------- | -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `plan`    | string                     | - (required)                     | A feature tag or a plan stem/path.                                                                                                                                                                              |
| `steps`   | list of step-state changes | - (required, at least one entry) | Each entry is `{step_id, state}`, where `state` is `"checked"` or `"unchecked"`. `step_id` accepts a canonical leaf ID (`S01`) or a full display path (`P01.S01`, `W01.P01.S01`) when disambiguation is needed. |

Plan resolution follows one rule across every tool that accepts a `plan` parameter: an
exact stem or path match wins first; failing that, a feature tag resolves only when it
matches exactly one plan. A feature with several plans refuses the call and lists the
candidate stems rather than guessing. An unresolvable or ambiguous plan fails the whole
call with a protocol error, as does an empty `steps` list.

Each step change reports its own outcome:

- `"updated"` - the step changed to the target state
- `"unchanged"` - the step was already at the target state, which counts as a success
- `"failed"` - an unknown step, an ambiguous ID, or an invalid state, with an
  `error.message`

A failure in one step change doesn't abort the batch - the aggregate `status` becomes
`"ok"`, `"mixed"`, or `"failed"` depending on the outcomes. The plan file is written
once, at the end of the batch, and only if a step changed. That write refreshes the
plan's `modified` stamp.

Every response ends with the plan's post-batch state: `total_steps`, `steps_completed`,
`completion_percent`, and `next_open_step` (a display path, or `null` when every step is
closed).

```json
{
  "status": "ok",
  "plan": "2026-07-12-search-api-plan",
  "items": [{ "step_id": "S01", "state": "checked", "status": "updated" }],
  "total_steps": 2,
  "steps_completed": 1,
  "completion_percent": 50.0,
  "next_open_step": "S02"
}
```

______________________________________________________________________

### `plan_edit`

Author plan steps: add, insert, edit, or remove step rows. Not read-only, destructive -
removing a step retires its ID permanently - and not idempotent.

| Parameter    | Type                         | Default                          | Description                                                                     |
| ------------ | ---------------------------- | -------------------------------- | ------------------------------------------------------------------------------- |
| `plan`       | string                       | - (required)                     | A feature tag or a plan stem/path, resolved the same way as in `plan_progress`. |
| `operations` | list of plan-edit operations | - (required, at least one entry) | See the operation fields below.                                                 |

Each operation has these fields. Omit a field that does not apply rather than sending
`null`:

| Field       | Type           | Default      | Description                                                                              |
| ----------- | -------------- | ------------ | ---------------------------------------------------------------------------------------- |
| `operation` | string         | **required** | One of `"add"`, `"insert"`, `"edit"`, or `"remove"`.                                     |
| `action`    | string or null | `null`       | The step's imperative statement. Required for `add` and `insert`; optional for `edit`.   |
| `scope`     | string or null | `null`       | The file or area the step touches. Required for `add` and `insert`; optional for `edit`. |
| `phase_id`  | string or null | `null`       | The `P##` anchor to add under, for plans at tier L2 or higher.                           |
| `before`    | string or null | `null`       | The `S##` anchor to insert before.                                                       |
| `after`     | string or null | `null`       | The `S##` anchor to insert after.                                                        |
| `step_id`   | string or null | `null`       | The target step for `edit` or `remove`.                                                  |

Operations apply in order against a single parsed plan, so an earlier `add` in the same
call is visible to a later `edit` or `remove`. A failure in one operation doesn't abort
the batch; the aggregate `status` can come back `"mixed"`. An empty `operations` list
fails the whole call with a protocol error.

Identifier guarantees belong to the plan core, not this tool:

- `add` allocates the next free ID in sequence.
- `insert` always allocates a new ID, even when inserting before an existing step.
  Nothing is ever renumbered.
- `remove` retires an ID permanently. Later `add` operations skip past retired IDs
  rather than reusing them.

A write guard refuses any write that would retire identifiers the operation didn't
intend to touch.

`plan_edit` covers step rows only. Restructuring above the step level - tiers, waves,
phases, or the epic frame - is gateway-or-CLI territory and isn't a first-class
operation here.

Add example:

```json
{
  "status": "ok",
  "plan": "2026-07-12-search-api-plan",
  "items": [{ "operation": "add", "status": "created", "step_id": "S03" }],
  "total_steps": 3,
  "steps_completed": 1,
  "next_open_step": "S02"
}
```

______________________________________________________________________

### `log`

Append one step's evidence to its plan's execution ledger. Not read-only, not
destructive (append-only), idempotent: re-logging a row changes nothing. The ledger is
one document per plan, created on the first call; it is the only execution artifact, and
this tool and `vaultspec-core vault exec log` share one writer.

| Parameter | Type                    | Default      | Description                                                                                    |
| --------- | ----------------------- | ------------ | ---------------------------------------------------------------------------------------------- |
| `feature` | string                  | - (required) | Feature tag, with or without `#`.                                                              |
| `plan`    | string                  | - (required) | The parent plan's stem.                                                                        |
| `step`    | string                  | - (required) | Canonical step id (`S01`) or display path (`P01.S01`).                                         |
| `rows`    | list of strings or null | `null`       | One `OP:path` per path touched: `A:` added, `M:` modified, `D:` deleted, `R:old->new` renamed. |
| `verify`  | string or null          | `null`       | A check that ran, as `<command>=pass` or `<command>=fail`.                                     |
| `by`      | string or null          | `null`       | The persona that closed the step.                                                              |
| `notes`   | list of strings or null | `null`       | Exception notes only (data loss, skipped work, a scaffold left in code, a persistent failure). |

A malformed row or verify spec, or a feature, plan, or step that does not resolve, fails
the whole call with a protocol error and writes nothing.

```json
{
  "path": ".vault/exec/2026-07-12-search-api/2026-07-12-search-api-ledger.md",
  "step": "S01",
  "rows": 3,
  "notes": 0,
  "changed": true,
  "created": true
}
```

______________________________________________________________________

### `discover` and `invoke`

`discover` and `invoke` are the gateway pair for everything else. The eight hot tools
cover the verbs a client reaches for constantly; `discover` and `invoke` reach the rest
of the CLI - the long tail of verbs that don't earn a dedicated tool but still need to
run. `discover` searches that catalog and returns ranked schemas. `invoke` runs one of
the verbs the catalog names.

#### `discover`: search the verb catalog

Read-only, idempotent.

| Parameter | Type    | Default      | Description                                                 |
| --------- | ------- | ------------ | ----------------------------------------------------------- |
| `query`   | string  | **required** | Verb words or an intent phrase to rank the catalog against. |
| `limit`   | integer | `10`         | Maximum number of ranked verbs to return.                   |

It returns the query echoed back, a count, and a list of ranked verb schemas.

Each verb schema carries:

- `verb` - the space-joined verb path, for example `"vault list"`
- `description` - the verb's help text
- `score` - a relevance score; results are ranked by relevance, highest first
- `supports_json` - whether the verb accepts a `--json` flag
- `flags` - the verb's flags, each with a name, whether it takes a value, and its help
  text
- `arguments` - the verb's positional arguments, each with a name, whether it's
  required, and whether it's variadic

A `discover` call looks like this:

```json
{
  "query": "list vault documents"
}
```

And the response:

```json
{
  "query": "list vault documents",
  "count": 1,
  "verbs": [
    {
      "verb": "vault list",
      "description": "List or filter vault documents.",
      "score": 7.5,
      "supports_json": true,
      "flags": [
        { "name": "--feature", "takes_value": true, "help": "Filter by feature tag." }
      ],
      "arguments": []
    }
  ]
}
```

#### `invoke`: run a cataloged verb

Not read-only. Destructive, because the catalog reaches mutating verbs. Idempotency
depends on the verb invoked.

| Parameter     | Type                    | Default      | Description                                                                                       |
| ------------- | ----------------------- | ------------ | ------------------------------------------------------------------------------------------------- |
| `verb`        | string                  | **required** | The space-joined verb path returned by `discover`, for example `"vault list"`.                    |
| `arguments`   | object or null          | `null`       | The verb's flags as a mapping. A list value repeats the flag; a boolean passes `true` or `false`. |
| `positionals` | list of strings or null | `null`       | The verb's positional operands, in CLI order.                                                     |
| `timeout`     | number                  | `60`         | Subprocess wall-clock budget in seconds.                                                          |

Three flags are reserved for the server: `--target`, `--json`, and `--help`. Do not pass
them in `arguments`. The server sets `--target` to the resolved workspace and adds
`--json` automatically when the verb supports it, and supplying a reserved flag fails
the call before any process starts.

At the user level, `invoke` runs the named verb as a subprocess of the installed
`vaultspec-core` binary against the resolved workspace. When the verb supports `--json`,
`invoke` parses the output into the response's `data` field; otherwise it returns the
raw standard output as text. Because the catalog mixes mutating and read-only verbs,
`invoke` carries the destructive-operation annotation unconditionally: the host prompts
for confirmation on every call, not just the ones that change state.

A successful call looks like this:

```json
{
  "verb": "vault add",
  "positionals": ["research"],
  "arguments": { "feature": "search-api" }
}
```

```json
{
  "verb": "vault add",
  "ok": true,
  "exit_code": 0,
  "format": "json",
  "data": { "path": ".vault/research/2026-07-11-search-api-research.md" },
  "stdout": null,
  "error": null,
  "command": ["vaultspec-core", "--target", "<root>", "vault", "add", "research", "--feature", "search-api", "--json"]
}
```

#### Two kinds of failure

`invoke` distinguishes a failed call from a failed verb. Three checks run before any
process spawns and raise a protocol error: an unknown verb path, a denylisted verb, or
an invalid argument (a reserved or undeclared flag, or a malformed positional). Nothing
runs when one of these fires.

Once the verb runs, its outcome is a per-call result, not a protocol error. The
response's `ok` field is `true` only when the process exits zero and its output parses
successfully. A verb that runs and exits non-zero returns `ok: false` with a populated
`error`, and the call itself still succeeds:

```json
{
  "verb": "vault plan status"
}
```

```json
{
  "verb": "vault plan status",
  "ok": false,
  "exit_code": 2,
  "format": "text",
  "data": null,
  "stdout": null,
  "error": {
    "kind": "nonzero_exit",
    "exit_code": 2,
    "stderr": "Error: missing argument 'PLAN'",
    "message": "verb exited with status 2"
  },
  "command": ["vaultspec-core", "--target", "<root>", "vault", "plan", "status", "--json"]
}
```

`error.kind` takes one of three values: `nonzero_exit` (the process exited with a
non-zero status), `json_parse` (the process exited zero, but its declared JSON output
didn't parse), or `timeout` (the process didn't finish within the timeout budget).

#### The denylist

A verb never reaches a subprocess if it's on the denylist. `discover` excludes
denylisted verbs from its results, and `invoke` rejects them before spawning. The
denylist covers:

- `uninstall` - tears down the framework
- `vaultspec-core spec mcps add`, `vaultspec-core spec mcps remove`,
  `vaultspec-core spec mcps sync`, and `vaultspec-core spec mcps uninstall` - MCP
  definition or enrollment mutation, owned by the `vaultspec-core spec mcps` lifecycle
  (the read-only `vaultspec-core spec mcps list` and `vaultspec-core spec mcps status`
  stay available)
- `vaultspec-core vault feature index` - index documents stay uncreatable through the
  MCP surface

## Server lifetime

The server's lifetime is its client connection. It exits when stdin reaches EOF, and a
lifetime watchdog backstops the cases where EOF never arrives - on Windows, a client
that restarts or dies can leave the server's stdin pipe held open by inherited handles,
which would otherwise leave orphaned server processes running indefinitely.

The watchdog anchors shutdown to the client process itself. On Windows it identifies the
process that created the server's stdin pipe and exits the moment that process
terminates; when stdin is not a client-created pipe (a console launch, for example) it
watches the server's ancestor process chain instead, ignoring short-lived launcher
processes. On other platforms a coarse poll exits the server if it is ever orphaned.
When the watchdog fires, one JSON event line (`"event": "stdio_watchdog_exit"`) is
written to stderr before the server exits cleanly. Its `reason` field says why:
`watched_process_exit` when the client died, `unanchored_orphan` when the server reaped
itself as described below.

On Windows the watchdog can also lose track of the client entirely - every launcher in
the chain exits before it looks, and stdin is not a pipe it can trace. Rather than give
up for the rest of the run, it keeps looking on an interval and re-anchors as soon as a
live ancestor appears. Only if repeated checks agree that no live process is left to
serve does it write a `"stdio_watchdog_disarmed"` event and then exit as an orphan.

Two knobs control it:

- `VAULTSPEC_STDIO_WATCHDOG` - set to `0`, `false`, `off`, or `no` to disable the
  watchdog entirely; the server then exits only on stdin EOF.
- `--parent-pid <PID>` - names an explicit client process to watch in addition to the
  detected one. Useful for hosts that spawn the server through wrappers the detection
  cannot see through.

A watchdog that cannot start never prevents the server from serving, and an ambiguous
reading is never treated as a dead client: the server exits only when a check confirms
the client is gone, never when a check is inconclusive.

## Logging

All server logs go to stderr. Stdout is reserved exclusively for the JSON-RPC protocol
stream, so nothing but protocol data can be written there without breaking the client
connection.

## Getting help

If the server misbehaves, start with the commands in the Verification section - they
diagnose the most common configuration problems without leaving the terminal. For
anything they don't explain, file bugs and questions on the
[vaultspec-core issue tracker](https://github.com/nevenincs/vaultspec-core/issues).

## Related documentation

| Document                           | What it covers                                          |
| ---------------------------------- | ------------------------------------------------------- |
| [Repository README](../README.md)  | What vaultspec is, why it exists, and getting started   |
| [Framework manual](./framework.md) | The development workflow the tools serve                |
| [CLI reference](./CLI.md)          | Every command the gateway can reach, with flags & codes |
