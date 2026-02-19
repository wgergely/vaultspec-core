# Configuration Reference

vaultspec is configured through `VAULTSPEC_*`
environment variables. All variables are optional
and have sensible defaults.

Configuration is resolved in priority order:

- Explicit overrides (for dependency injection
  or testing)
- `VAULTSPEC_*` environment variable
- Dataclass default

Source: `.vaultspec/lib/src/core/config.py`

## Agent Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_ROOT_DIR | Path | cwd() |

Workspace root directory.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_AGENT_MODE | string | read-write |

Agent permission mode. Options: read-write,
read-only.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_SYSTEM_PROMPT | string | none |

Custom system prompt for agent sessions.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_MAX_TURNS | int | none |

Maximum conversation turns for agent sessions
(min: 1).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_BUDGET_USD | float | none |

Budget cap in USD for agent sessions (min: 0).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_ALLOWED_TOOLS | csv list | [] |

Comma-separated list of allowed tool names.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_DISALLOWED_TOOLS | csv list | [] |

Comma-separated list of disallowed tool names.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_EFFORT | string | none |

Effort level hint for agent sessions.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_OUTPUT_FORMAT | string | none |

Output format for agent responses.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_FALLBACK_MODEL | string | none |

Fallback model identifier for agent sessions.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_INCLUDE_DIRS | csv list | [] |

Comma-separated list of directories to include.

## MCP Server Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_MCP_ROOT_DIR | Path | none |

Root directory for MCP server (required when
MCP server starts).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_MCP_PORT | int | 10010 |

Port for MCP server (1-65535).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_MCP_HOST | string | 0.0.0.0 |

Host address for MCP server.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_MCP_TTL_SECONDS | float | 3600.0 |

Task TTL in seconds for MCP server (min: 0).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_MCP_POLL_INTERVAL | float | 5.0 |

Agent file polling interval in seconds
(min: 0.5).

## A2A Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_A2A_DEFAULT_PORT | int | 10010 |

Default port for A2A agent cards (1-65535).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_A2A_HOST | string | localhost |

Default host for A2A agent cards.

## Storage Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_DOCS_DIR | string | .vault |

Documentation vault directory name.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_FRAMEWORK_DIR | string | .vaultspec |

Framework directory name.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_LANCE_DIR | string | .lance |

LanceDB vector store directory name.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_INDEX_METADATA_FILE | string | index_meta.json |

Index metadata filename within lance directory.

## Tool Directory Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_CLAUDE_DIR | string | .claude |

Claude tool directory name.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_GEMINI_DIR | string | .gemini |

Gemini tool directory name.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_AGENT_DIR | string | .agent |

Agent tool directory name.

## Orchestration Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_TASK_ENGINE_TTL_SECONDS | float | 3600.0 |

Task engine TTL in seconds (min: 0).

## RAG Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_EMBEDDING_MODEL | string | (see below) |

Sentence-transformer model name for embeddings.
Default: `nomic-ai/nomic-embed-text-v1.5`.

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_EMBEDDING_BATCH_SIZE | int | 64 |

Batch size for GPU embedding inference
(min: 1).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_MAX_EMBED_CHARS | int | 8000 |

Max characters per document for embedding
truncation (min: 100).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_GRAPH_TTL_SECONDS | float | 300.0 |

Graph cache TTL in seconds for search
re-ranking (min: 0).

## I/O Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_IO_BUFFER_SIZE | int | 8192 |

I/O read buffer size in bytes (min: 1).

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_TERMINAL_OUTPUT_LIMIT | int | 1000000 |

Terminal output byte limit for subprocess
capture (min: 1).

## Editor Settings

| Var | Type | Default |
| --- | ---- | ------- |
| VAULTSPEC_EDITOR | string | zed -w |

Default editor command for creating
rules, agents, and skills.

## Type Reference

- **string** -- Plain text value
- **int** -- Integer number
- **float** -- Decimal number
- **Path** -- Filesystem path (absolute or
  relative)
- **csv list** -- Comma-separated values, parsed
  into a Python list
  (e.g., `"tool1,tool2,tool3"`)

Optional values (marked "none" as default) are
not set unless explicitly provided.
