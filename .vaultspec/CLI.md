# vaultspec-core CLI Reference

Complete command reference for `vaultspec-core`. See the [framework manual](./README.md) for workflows and concepts.

## Entry Points

| Command          | Description                                                |
| ---------------- | ---------------------------------------------------------- |
| `vaultspec-core` | Workspace management, vault operations, resource sync      |
| `vaultspec-mcp`  | stdio MCP server (documented in [MCP reference](./MCP.md)) |

## Global Options

These options apply to all `vaultspec-core` commands.

| Option         | Short | Default | Description                                                                                                                |
| -------------- | ----- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `--target DIR` | `-t`  | cwd     | Target workspace directory. Overrides `VAULTSPEC_TARGET_DIR`. Defaults to the current working directory if neither is set. |
| `--debug`      | `-d`  | off     | Enable DEBUG-level logging                                                                                                 |
| `--version`    | `-V`  | -       | Print version and exit                                                                                                     |

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

| Option          | Short | Default | Description           |
| --------------- | ----- | ------- | --------------------- |
| `--feature TAG` | `-f`  | None    | Filter by feature tag |
| `--date DATE`   | -     | None    | Filter by date        |

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

______________________________________________________________________

### vault feature archive

```bash
vaultspec-core vault feature archive FEATURE_TAG
```

Move all documents for a feature tag to the archive.

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

| Sub-command   | `--fix` | `--feature` | Description                                                 |
| ------------- | ------- | ----------- | ----------------------------------------------------------- |
| `all`         | partial | yes         | Run all checks in sequence                                  |
| `frontmatter` | yes     | yes         | Validate frontmatter against vault schema                   |
| `links`       | yes     | yes         | Check wiki-links follow Obsidian convention                 |
| `orphans`     | no      | yes         | Find documents with no incoming wiki-links                  |
| `features`    | no      | yes         | Check feature tag completeness                              |
| `references`  | yes     | yes         | Check cross-references within features                      |
| `schema`      | yes     | yes         | Enforce dependency rules (ADR refs research, plan refs ADR) |
| `structure`   | yes     | no          | Check directory structure and filename conventions          |

`yes` = fully supported, `partial` = some checks only, `no` = flag rejected with error. `structure` does not support `--feature` filtering.

## Spec Commands

Group command: `vaultspec-core spec COMMAND`

### spec rules / spec skills / spec agents

CRUD operations for framework resources. All three groups share the same sub-command structure.

```bash
vaultspec-core spec rules COMMAND
vaultspec-core spec skills COMMAND
vaultspec-core spec agents COMMAND
```

#### Sub-Commands

| Sub-command | Signature                                | Description                                    |
| ----------- | ---------------------------------------- | ---------------------------------------------- |
| `list`      | -                                        | List all resources                             |
| `add`       | `--name NAME [--content TEXT] [--force]` | Create a resource                              |
| `show`      | `NAME`                                   | Print resource content to stdout               |
| `edit`      | `NAME`                                   | Open in configured editor (`VAULTSPEC_EDITOR`) |
| `remove`    | `NAME [--force]`                         | Delete a resource. Prompts unless `--force`.   |
| `rename`    | `OLD_NAME NEW_NAME`                      | Rename a resource                              |
| `sync`      | `[--dry-run] [--force]`                  | Sync resources to provider directories         |
| `revert`    | `FILENAME`                               | Revert to snapshotted original                 |

The `add` sub-command accepts additional options per resource type:

- `spec skills add` also accepts `--description` and `--template`.
- `spec agents add` also accepts `--description`.

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
| `VAULTSPEC_EDITOR`                | str  | `zed -w`     | Editor command for `spec edit`. Set to your preferred editor (e.g. `code -w`, `vim`).                                                                                                                             |

## See Also

| Document                        | What it covers                                  |
| ------------------------------- | ----------------------------------------------- |
| [Framework Manual](./README.md) | Development workflow, skills, and customization |
| [MCP Reference](./MCP.md)       | MCP server tools, setup, and configuration      |

For bug reports and feature requests, open an issue on the [vaultspec-core issue tracker](https://github.com/wgergely/vaultspec-core/issues).
