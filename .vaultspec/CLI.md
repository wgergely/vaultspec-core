# vaultspec-core CLI Reference

Complete command reference for `vaultspec-core`. See the [framework manual](./README.md) for workflows and concepts.

## Entry Points

| Command                                          | Description                                                                                            |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `vaultspec-core`                                 | Workspace management, vault operations, resource sync.                                                 |
| `vaultspec-mcp`                                  | Console script that launches the stdio MCP server.                                                     |
| `uv run python -m vaultspec_core.mcp_server.app` | Module invocation of the MCP server (avoids binary locking on Windows). See [MCP reference](./MCP.md). |

## Global Options

These options apply at the top level and on most subcommands. `--debug` and `--version` are top-level only; `--target` and `--json` are accepted by almost every subcommand.

| Option         | Short | Default | Description                                                                                                                |
| -------------- | ----- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `--target DIR` | `-t`  | cwd     | Target workspace directory. Overrides `VAULTSPEC_TARGET_DIR`. Defaults to the current working directory if neither is set. |
| `--debug`      | `-d`  | off     | Enable DEBUG-level logging (top-level flag).                                                                               |
| `--version`    | `-V`  | -       | Print version and exit (top-level flag).                                                                                   |
| `--json`       | -     | off     | Emit machine-readable output. Supported on nearly every subcommand.                                                        |

## Workspace Commands

### install

```bash
vaultspec-core install [PROVIDER] [OPTIONS]
```

Deploy the vaultspec framework into the target directory.

#### Arguments

| Argument   | Default | Description                                               |
| ---------- | ------- | --------------------------------------------------------- |
| `PROVIDER` | `all`   | `all`, `core`, `claude`, `gemini`, `antigravity`, `codex` |

#### Options

| Option      | Default | Description                             |
| ----------- | ------- | --------------------------------------- |
| `--upgrade` | off     | Re-sync builtins without re-scaffolding |
| `--dry-run` | off     | Preview without writing                 |
| `--force`   | off     | Overwrite existing installation         |
| `--skip`    | `[]`    | Skip specific sync passes (repeatable)  |
| `--json`    | off     | Emit machine-readable output            |

`core` installs `.vaultspec/` only, without any provider config.

______________________________________________________________________

### uninstall

```bash
vaultspec-core uninstall [PROVIDER] [OPTIONS]
```

Remove the vaultspec framework from the target directory.

#### Arguments

| Argument   | Default | Description                                               |
| ---------- | ------- | --------------------------------------------------------- |
| `PROVIDER` | `all`   | `all`, `core`, `claude`, `gemini`, `antigravity`, `codex` |

#### Options

| Option           | Default | Description                                    |
| ---------------- | ------- | ---------------------------------------------- |
| `--remove-vault` | off     | Also remove `.vault/`                          |
| `--dry-run`      | off     | Preview without deleting                       |
| `--force`        | off     | Required to execute (uninstall is destructive) |
| `--skip`         | `[]`    | Skip specific removal passes (repeatable)      |
| `--json`         | off     | Emit machine-readable output                   |

`.vault/` is preserved by default. Pass `--remove-vault` to delete it.

______________________________________________________________________

### sync

```bash
vaultspec-core sync [PROVIDER] [OPTIONS]
```

Sync rules, skills, agents, system prompts, and config from `.vaultspec/` to provider directories.

#### Arguments

| Argument   | Default | Description                                       |
| ---------- | ------- | ------------------------------------------------- |
| `PROVIDER` | `all`   | `all`, `claude`, `gemini`, `antigravity`, `codex` |

`core` is not a valid sync target.

#### Options

| Option      | Default | Description                                           |
| ----------- | ------- | ----------------------------------------------------- |
| `--dry-run` | off     | Preview changes without writing                       |
| `--force`   | off     | Prune stale files and overwrite user-authored content |
| `--skip`    | `[]`    | Skip specific sync passes (repeatable)                |
| `--json`    | off     | Emit machine-readable output                          |

## Vault Commands

Group command: `vaultspec-core vault COMMAND`

### vault add

```bash
vaultspec-core vault add DOC_TYPE [OPTIONS]
```

Create a new `.vault/` document from a template.

#### Arguments

| Argument   | Description                                             |
| ---------- | ------------------------------------------------------- |
| `DOC_TYPE` | `adr`, `audit`, `exec`, `plan`, `reference`, `research` |

#### Options

| Option          | Short | Default         | Description                                                                          |
| --------------- | ----- | --------------- | ------------------------------------------------------------------------------------ |
| `--feature TAG` | `-f`  | None (required) | Feature tag (kebab-case)                                                             |
| `--date DATE`   | -     | today           | Override date (ISO 8601)                                                             |
| `--title TITLE` | -     | None            | Document title                                                                       |
| `--related DOC` | `-r`  | None            | Related document(s). Accepts path, filename, stem, or `[[wiki-link]]`. Repeatable.   |
| `--tags TAG`    | -     | None            | Additional freeform tags beyond the required directory and feature tags. Repeatable. |
| `--force`       | -     | off             | Overwrite an existing document at the resolved path.                                 |
| `--dry-run`     | -     | off             | Preview without writing.                                                             |
| `--json`        | -     | off             | Emit machine-readable output.                                                        |

______________________________________________________________________

### vault list

```bash
vaultspec-core vault list [DOC_TYPE] [OPTIONS]
```

List vault documents.

#### Arguments

| Argument   | Default | Description             |
| ---------- | ------- | ----------------------- |
| `DOC_TYPE` | None    | Filter by document type |

#### Options

| Option          | Short | Default | Description                   |
| --------------- | ----- | ------- | ----------------------------- |
| `--feature TAG` | `-f`  | None    | Filter by feature tag         |
| `--date DATE`   | -     | None    | Filter by date                |
| `--json`        | -     | off     | Emit machine-readable output. |

______________________________________________________________________

### vault stats

```bash
vaultspec-core vault stats [OPTIONS]
```

Show vault statistics and document counts.

#### Options

| Option          | Short | Default | Description                            |
| --------------- | ----- | ------- | -------------------------------------- |
| `--feature TAG` | `-f`  | None    | Filter by feature tag                  |
| `--date DATE`   | -     | None    | Filter by date                         |
| `--type TYPE`   | -     | None    | Filter by document type                |
| `--invalid`     | -     | off     | Show only documents with invalid links |
| `--orphaned`    | -     | off     | Show only orphaned documents           |
| `--json`        | -     | off     | Emit machine-readable output.          |

______________________________________________________________________

### vault graph

```bash
vaultspec-core vault graph [OPTIONS]
```

Outputs a hierarchical tree grouped by feature and type.

#### Options

| Option          | Short | Default | Description                          |
| --------------- | ----- | ------- | ------------------------------------ |
| `--feature TAG` | `-f`  | None    | Scope to a single feature            |
| `--json`        | -     | off     | Output as networkx node-link JSON    |
| `--metrics`     | `-m`  | off     | Show aggregate graph metrics         |
| `--ascii`       | -     | off     | Render ASCII topology                |
| `--body`        | -     | off     | Include document body in JSON output |

______________________________________________________________________

### vault feature list

```bash
vaultspec-core vault feature list [OPTIONS]
```

List all feature tags in the vault.

#### Options

| Option        | Default | Description                               |
| ------------- | ------- | ----------------------------------------- |
| `--date DATE` | None    | Filter by date                            |
| `--orphaned`  | off     | Show only features with no incoming links |
| `--type TYPE` | None    | Filter by document type                   |
| `--json`      | off     | Emit machine-readable output.             |

______________________________________________________________________

### vault feature index

```bash
vaultspec-core vault feature index [OPTIONS]
```

Generate or update `<feature>.index.md` files at the vault root. Each index links to every document sharing that feature tag, making implicit feature clusters explicit in the graph.

#### Options

| Option          | Short | Default | Description                           |
| --------------- | ----- | ------- | ------------------------------------- |
| `--feature TAG` | `-f`  | None    | Generate index for a specific feature |
| `--json`        | -     | off     | Emit machine-readable output.         |

______________________________________________________________________

### vault feature archive

```bash
vaultspec-core vault feature archive FEATURE_TAG [OPTIONS]
```

Move all documents for a feature tag to the archive.

#### Options

| Option   | Default | Description                   |
| -------- | ------- | ----------------------------- |
| `--json` | off     | Emit machine-readable output. |

______________________________________________________________________

### vault check

```bash
vaultspec-core vault check COMMAND [OPTIONS]
```

Run health checks on `.vault/`. Exits with code `1` if errors are found.

#### Shared Options

| Option          | Short | Default | Description                      |
| --------------- | ----- | ------- | -------------------------------- |
| `--fix`         | -     | off     | Apply auto-fixes where supported |
| `--feature TAG` | `-f`  | None    | Limit to a specific feature      |
| `--verbose`     | `-v`  | off     | Show INFO-level diagnostics      |

#### Sub-Commands

| Sub-command   | `--fix` | `--feature` | Description                                                      |
| ------------- | ------- | ----------- | ---------------------------------------------------------------- |
| `all`         | partial | yes         | Run every check in sequence                                      |
| `body-links`  | no      | yes         | Find wiki-links and markdown path links in document body text    |
| `dangling`    | yes     | yes         | Find `related:` wiki-links that resolve to no document           |
| `frontmatter` | yes     | yes         | Validate frontmatter against vault schema                        |
| `links`       | yes     | yes         | Check wiki-links follow Obsidian convention (no `.md` extension) |
| `orphans`     | no      | yes         | Find documents with no incoming wiki-links                       |
| `features`    | no      | yes         | Check feature tag completeness (missing doc types)               |
| `references`  | yes     | yes         | Check cross-references within features                           |
| `schema`      | yes     | yes         | Enforce dependency rules (ADR refs research, plan refs ADR)      |
| `structure`   | yes     | no          | Check directory structure and filename conventions               |

`yes` = fully supported, `partial` = only the sub-checks that accept `--fix` will apply fixes (`all` dispatches to every check), `no` = flag rejected with error. `structure` does not support `--feature` filtering.

## Spec Commands

Group command: `vaultspec-core spec COMMAND`

Every spec sub-command below also accepts the global `--target / -t DIR` and `--json` flags on top of the signatures shown.

### spec doctor

```bash
vaultspec-core spec doctor [OPTIONS]
```

Run diagnostic collectors across the framework, providers, builtins, `.gitignore`, and configuration files. Reports findings and exits with the highest severity observed.

#### Options

| Option         | Short | Default | Description                                      |
| -------------- | ----- | ------- | ------------------------------------------------ |
| `--target DIR` | `-t`  | cwd     | Diagnose a directory other than the current one. |
| `--json`       | -     | off     | Emit the diagnosis as JSON.                      |

Exit codes: `0` = all ok, `1` = warnings, `2` = errors.

______________________________________________________________________

### spec rules / spec skills / spec agents

CRUD operations for framework resources. All three groups share the same sub-command structure.

```bash
vaultspec-core spec rules COMMAND
vaultspec-core spec skills COMMAND
vaultspec-core spec agents COMMAND
```

#### Sub-Commands

| Sub-command | Signature                           | Description                                                      |
| ----------- | ----------------------------------- | ---------------------------------------------------------------- |
| `list`      | -                                   | List all resources                                               |
| `add`       | `--name NAME [--force] [--dry-run]` | Create a resource. Extra options vary per resource type (below). |
| `show`      | `NAME`                              | Print resource content to stdout                                 |
| `edit`      | `NAME`                              | Open in configured editor (`VAULTSPEC_EDITOR`)                   |
| `remove`    | `NAME [--yes\|--force]` (`-y`)      | Delete a resource. Prompts unless confirmed.                     |
| `rename`    | `OLD_NAME NEW_NAME`                 | Rename a resource                                                |
| `sync`      | `[--dry-run] [--force]`             | Sync resources to provider directories                           |
| `revert`    | `FILENAME`                          | Revert to snapshotted original                                   |

`add` accepts different body-content flags per resource type:

- `spec rules add` accepts `--content TEXT`.
- `spec skills add` accepts `--description TEXT` and `--template TEXT`.
- `spec agents add` accepts `--description TEXT`.

______________________________________________________________________

### spec system

```bash
vaultspec-core spec system COMMAND
```

#### Sub-Commands

| Sub-command | Options                 | Description                                        |
| ----------- | ----------------------- | -------------------------------------------------- |
| `show`      | -                       | Display system prompt parts and generation targets |
| `sync`      | `[--dry-run] [--force]` | Sync system prompts to provider destinations       |

______________________________________________________________________

### spec hooks

```bash
vaultspec-core spec hooks COMMAND
```

#### Sub-Commands

| Sub-command | Signature             | Description                                                                                                           |
| ----------- | --------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `list`      | -                     | List hooks with name, status, event, and action count                                                                 |
| `run`       | `EVENT [--path PATH]` | Trigger enabled hooks for the given event. Valid events: `vault.document.created`, `config.synced`, `audit.completed` |

______________________________________________________________________

### spec mcps

```bash
vaultspec-core spec mcps COMMAND
```

Manage MCP server definitions and the synced `.mcp.json` entries deployed into provider directories.

#### Sub-Commands

| Sub-command | Signature                               | Description                                                    |
| ----------- | --------------------------------------- | -------------------------------------------------------------- |
| `list`      | -                                       | List all registered MCP server definitions                     |
| `add`       | `--name NAME [--config JSON] [--force]` | Add a new custom MCP server definition                         |
| `remove`    | `NAME [--force]`                        | Remove an MCP server definition (`--force` skips confirmation) |
| `sync`      | `[--dry-run] [--force]`                 | Sync MCP definitions to `.mcp.json`                            |

## Environment Variables

All variables are prefixed `VAULTSPEC_`. Environment variables override defaults but are overridden by the `--target` flag.

| Variable                          | Type | Default      | Description                                                                                                                                                                                                       |
| --------------------------------- | ---- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VAULTSPEC_TARGET_DIR`            | path | cwd          | Root workspace directory (where `.vault/` and `.vaultspec/` live). Equivalent to `--target` on the CLI. Also used by `vaultspec-mcp` to locate the workspace. Defaults to the current working directory if unset. |
| `VAULTSPEC_DOCS_DIR`              | str  | `.vault`     | Vault directory name                                                                                                                                                                                              |
| `VAULTSPEC_FRAMEWORK_DIR`         | str  | `.vaultspec` | Framework directory name                                                                                                                                                                                          |
| `VAULTSPEC_CLAUDE_DIR`            | str  | `.claude`    | Claude tool directory name                                                                                                                                                                                        |
| `VAULTSPEC_GEMINI_DIR`            | str  | `.gemini`    | Gemini tool directory name                                                                                                                                                                                        |
| `VAULTSPEC_ANTIGRAVITY_DIR`       | str  | `.agents`    | Antigravity directory name                                                                                                                                                                                        |
| `VAULTSPEC_IO_BUFFER_SIZE`        | int  | `8192`       | I/O read buffer size in bytes                                                                                                                                                                                     |
| `VAULTSPEC_TERMINAL_OUTPUT_LIMIT` | int  | `1000000`    | Subprocess stdout capture limit in bytes                                                                                                                                                                          |
| `VAULTSPEC_LOG_LEVEL`             | str  | `INFO`       | Root log level for the CLI (e.g. `DEBUG`, `INFO`, `WARNING`). Overridden by `--debug` when set.                                                                                                                   |
| `VAULTSPEC_ALLOW_DEV_WRITES`      | bool | unset        | Bypass the development-write guard that blocks source-repo writes. Accepts `1`/`true`/`yes`. Use with care - intended for fixture and test automation only.                                                       |
| `VAULTSPEC_EDITOR`                | str  | `zed -w`     | Editor command for `spec {rules\|skills\|agents} edit`. Set to your preferred editor (e.g. `code -w`, `vim`).                                                                                                     |

## See Also

| Document                        | What it covers                                  |
| ------------------------------- | ----------------------------------------------- |
| [Framework Manual](./README.md) | Development workflow, skills, and customization |
| [MCP Reference](./MCP.md)       | MCP server tools, setup, and configuration      |

For bug reports and feature requests, open an issue on the [vaultspec-core issue tracker](https://github.com/wgergely/vaultspec-core/issues).
