# vaultspec MCP Server

`vaultspec-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes vault document discovery and authoring as JSON-RPC tools over stdio transport. It allows any MCP-capable client (e.g. Claude Desktop, editor extensions) to query and create `.vault/` documents in a vaultspec-managed workspace.

## Setup

`vaultspec-core install` scaffolds a `.mcp.json` automatically:

```json
{
  "mcpServers": {
    "vaultspec-core": {
      "command": "uv",
      "args": ["run", "python", "-m", "vaultspec_core.mcp_server.app"]
    }
  }
}
```

The server resolves its workspace from the current working directory by default. IDE-integrated MCP clients (Claude Code, Cursor) set the working directory to the project root, so this works without additional configuration.

This invocation uses module-based execution (`python -m`) rather than the `vaultspec-mcp` console script entry point. On Windows, MCP clients lock the `.exe` binary in `.venv/Scripts/`, which blocks `uv sync` and other package operations. Module invocation avoids this entirely.

For standalone setups where the working directory isn't the workspace, set `VAULTSPEC_TARGET_DIR` to an absolute path:

```json
{
  "mcpServers": {
    "vaultspec-core": {
      "command": "uv",
      "args": ["run", "python", "-m", "vaultspec_core.mcp_server.app"],
      "env": {
        "VAULTSPEC_TARGET_DIR": "/path/to/workspace"
      }
    }
  }
}
```

## Environment

| Variable               | Default | Description                                                                                                                                                 |
| ---------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VAULTSPEC_TARGET_DIR` | cwd     | Path to the workspace root containing `.vault/` and `.vaultspec/`. Equivalent to `--target` on the CLI. Defaults to the current working directory if unset. |

See the [CLI reference](./CLI.md) for all `VAULTSPEC_` environment variables.

**Note:** `vaultspec-core install` always scaffolds `.mcp.json` regardless of which provider is selected. MCP configuration is part of the core install and is not tied to any specific provider.

## Tools

### `find`

Read-only, idempotent. Discovers vault documents or lists features.

**With no arguments**, returns all features with document count and graph weight score (based on incoming link count via `VaultGraph`).

**With filters**, returns matching documents.

| Parameter | Type               | Default | Description                                                                                                                                                                 |
| --------- | ------------------ | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `feature` | `string \| null`   | `null`  | Filter to documents tagged with this feature.                                                                                                                               |
| `type`    | `string[] \| null` | `null`  | Document types to include. Defaults to `["adr", "plan", "research", "reference"]` when filtering by feature/date. `exec` and `audit` are excluded unless explicitly listed. |
| `date`    | `string \| null`   | `null`  | Filter to documents with this ISO-8601 date.                                                                                                                                |
| `body`    | `boolean`          | `false` | Include full markdown body text in each result.                                                                                                                             |
| `json`    | `boolean`          | `false` | Include extended fields in feature listing (`status`, `types`, `earliest_date`, `has_plan`).                                                                                |
| `limit`   | `integer`          | `20`    | Maximum number of results to return.                                                                                                                                        |

**Feature listing response** (no filters):

```json
[
  { "name": "auth", "doc_count": 4, "weight": 7 },
  ...
]
```

With `json: true`, adds `"status"`, `"types"`, `"earliest_date"`, `"has_plan"` fields.

**Document search response** (with filters):

```json
[
  {
    "name": "2025-01-15-auth-adr",
    "type": "adr",
    "feature": "auth",
    "date": "2025-01-15",
    "path": ".vault/adr/2025-01-15-auth-adr.md"
  },
  ...
]
```

With `body: true`, adds a `"body"` field containing the full file content.

______________________________________________________________________

### `create`

Non-destructive, idempotent. Creates a new vault document from a type template.

| Parameter | Type               | Default      | Description                                                                                                         |
| --------- | ------------------ | ------------ | ------------------------------------------------------------------------------------------------------------------- |
| `feature` | `string`           | —            | **Required.** Feature tag for the document (leading `#` is stripped).                                               |
| `type`    | `string \| null`   | `"research"` | Document type. Must be one of: `adr`, `audit`, `exec`, `plan`, `reference`, `research`.                             |
| `date`    | `string \| null`   | today        | ISO-8601 date (`YYYY-MM-DD`). Defaults to the current date.                                                         |
| `title`   | `string \| null`   | `null`       | Document title / topic slug. Defaults to `feature` when omitted.                                                    |
| `content` | `string \| null`   | `null`       | Optional additional content appended under a `## Context` heading.                                                  |
| `related` | `string[] \| null` | `null`       | Related document(s). Accepts path, filename, stem, or `[[wiki-link]]`. Resolved to wiki-link format in frontmatter. |
| `tags`    | `string[] \| null` | `null`       | Additional freeform tags beyond the required directory and feature tags.                                            |

The tool reads the template at `.vaultspec/rules/templates/{type}.md`, replaces `{feature}`, `{yyyy-mm-dd}`, `{topic}`, and `{title}` placeholders, then writes to `.vault/{type}/{filename}`.

**Filename format:**

- Standard: `{date}-{feature}-{type}.md`
- For `exec` type: `{date}-{feature}-exec-{title}.md`

**Success response:**

```json
{
  "success": true,
  "path": ".vault/research/2025-01-15-auth-research.md",
  "message": "Document created successfully."
}
```

**Failure response:**

```json
{
  "success": false,
  "message": "Template not found: ..."
}
```

Possible failure reasons: invalid `type`, missing template, filename validation error, destination directory not found, file already exists, write failure.

## Logging

All server logs are written to **stderr**. **stdout is reserved for the JSON-RPC protocol stream** and must not receive non-protocol output. This separation is enforced at startup by `configure_logging()`.

## See Also

| Document                          | What it covers                                        |
| --------------------------------- | ----------------------------------------------------- |
| [Repository README](../README.md) | Project overview, installation, and getting started   |
| [Framework Manual](./README.md)   | Development workflow, skills, and customization       |
| [CLI Reference](./CLI.md)         | All commands, flags, and options for `vaultspec-core` |

For bug reports and feature requests, open an issue on the [vaultspec-core issue tracker](https://github.com/wgergely/vaultspec-core/issues).
