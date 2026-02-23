# CLI Reference

vaultspec provides a unified CLI entry point (`vaultspec`) plus dedicated
namespace CLIs (`vaultspec vault`, `vaultspec subagent`, `vaultspec team`,
`vaultspec mcp`). Source: `src/vaultspec/`.

## vaultspec -- Framework Manager

Manages rules, agents, skills, config, and system
prompts across tool destinations (`.claude/`, `.gemini/`,
`.agent/`).

```text
vaultspec \
  [global-flags] <resource> <command> [options]
```

### Global Flags

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root ROOT | Path | cwd | Override workspace root |
| --content-dir | Path | none | Content source directory |
| --verbose, -v | flag | off | Verbose output (INFO) |
| --debug | flag | off | Debug logging (DEBUG) |
| --quiet, -q | flag | off | Suppress info output (WARNING) |
| --version, -V | flag | -- | Show version and exit |

---

### rules

Manage behavioral constraint files in
`.vaultspec/rules/`.

#### `rules list`

List all rules (built-in and custom).

```bash
vaultspec rules list
```

```text
Name                            Source
----------------------------------------------
vaultspec-skills.builtin.md     Built-in
my-custom-rule.md               Custom
```

#### `rules add`

Create a new custom rule. Opens `$EDITOR` if no
`--content` is provided.

```bash
vaultspec rules add \
  --name my-rule \
  --content "Always use snake_case."
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Rule name |
| --content | string | none | Rule content |
| --force | flag | off | Overwrite existing |

#### `rules show`

Display a rule's metadata and content.

```bash
vaultspec \
  rules show vaultspec-skills.builtin
```

#### `rules edit`

Open a rule in `$EDITOR`.

```bash
vaultspec \
  rules edit my-rule
```

#### `rules remove`

Delete a rule and its synced copies. Prompts for
confirmation unless `--force`.

```bash
vaultspec \
  rules remove my-rule --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --force | flag | off | Skip confirmation |

#### `rules rename`

Rename a rule and update synced copies.

```bash
vaultspec \
  rules rename old-rule new-rule
```

#### `rules sync`

Sync rules to tool destinations (`.claude/rules/`,
`.gemini/rules/`, etc.).

```bash
vaultspec \
  rules sync --dry-run
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown files |
| --dry-run | flag | off | Preview without writing |

---

### agents

Manage agent definitions in `.vaultspec/rules/agents/`.

#### `agents list`

List all agents with their tiers and resolved models.

```bash
vaultspec agents list
```

```text
Name                      Tier   Claude
--------------------------------------------
vaultspec-adr-researcher  HIGH   claude-s-4-5
vaultspec-researcher      MED    claude-s-4-5
vaultspec-simple-executor LOW    claude-h-4-5
```

#### `agents add`

Create a new agent definition. Opens `$EDITOR` after
scaffolding.

```bash
vaultspec agents add \
  --name my-agent --tier HIGH \
  --description "My agent"
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Agent name |
| --description | string | "" | Description |
| --tier | choice | MEDIUM | LOW, MEDIUM, HIGH |
| --force | flag | off | Overwrite existing |
| --template | string | none | Template to use |

#### `agents show`

Display an agent's metadata and content.

```bash
vaultspec \
  agents show vaultspec-researcher
```

#### `agents edit`

Open an agent definition in `$EDITOR`.

```bash
vaultspec \
  agents edit vaultspec-researcher
```

#### `agents remove`

Delete an agent and its synced copies. Prompts for
confirmation unless `--force`.

```bash
vaultspec \
  agents remove my-agent --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --force | flag | off | Skip confirmation |

#### `agents rename`

Rename an agent and update synced copies.

```bash
vaultspec \
  agents rename old-agent new-agent
```

#### `agents sync`

Sync agent definitions to tool destinations with
tier-to-model resolution.

```bash
vaultspec \
  agents sync --prune --dry-run
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown agents |
| --dry-run | flag | off | Preview without writing |

#### `agents set-tier`

Update an agent's capability tier.

```bash
vaultspec \
  agents set-tier vaultspec-researcher \
  --tier HIGH
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --tier | choice | **required** | LOW, MEDIUM, HIGH |

---

### skills

Manage skill definitions in `.vaultspec/rules/skills/`.

#### `skills list`

List all managed skills (directories matching
`vaultspec-*`).

```bash
vaultspec skills list
```

```text
Name                  Description
-------------------------------------------
vaultspec-research    Use it when unsure...
vaultspec-execute     Skill to execute...
```

#### `skills add`

Create a new skill. Names are automatically prefixed
with `vaultspec-` if needed.

```bash
vaultspec skills add \
  --name my-skill \
  --description "Does something"
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Skill name |
| --description | string | "" | Description |
| --force | flag | off | Overwrite existing |
| --template | string | none | Template to use |

Names are auto-prefixed with `vaultspec-`.

#### `skills show`

Display a skill's metadata and content.

```bash
vaultspec \
  skills show vaultspec-research
```

#### `skills edit`

Open a skill in `$EDITOR`.

```bash
vaultspec \
  skills edit vaultspec-research
```

#### `skills remove`

Delete a skill and its synced copies. Prompts for
confirmation unless `--force`.

```bash
vaultspec \
  skills remove vaultspec-my-skill --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --force | flag | off | Skip confirmation |

#### `skills rename`

Rename a skill and update synced copies.

```bash
vaultspec \
  skills rename vaultspec-old vaultspec-new
```

#### `skills sync`

Sync skills to tool destinations. Each skill becomes a
`<name>/SKILL.md` directory.

```bash
vaultspec \
  skills sync --prune
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown dirs |
| --dry-run | flag | off | Preview without writing |

---

### config

Manage tool configuration files (`CLAUDE.md`,
`GEMINI.md`, `AGENTS.md`).

#### `config show`

Display framework and project configuration content,
plus generated rule references per tool.

```bash
vaultspec config show
```

#### `config sync`

Sync configuration to tool-specific files. Skips files
with custom content unless `--force`.

```bash
vaultspec \
  config sync --force --dry-run
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown files |
| --dry-run | flag | off | Preview without writing |
| --force | flag | off | Overwrite custom content |

---

### system

Manage system prompt assembly from
`.vaultspec/rules/system/` parts.

#### `system show`

Display system prompt parts and their generation
targets.

```bash
vaultspec system show
```

```text
Name          Tool Filter    Lines
-----------------------------------
base          -              42
project       -              15
```

#### `system sync`

Assemble and sync system prompts to tool destinations
(e.g., `.gemini/SYSTEM.md`).

```bash
vaultspec \
  system sync --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown files |
| --dry-run | flag | off | Preview without writing |
| --force | flag | off | Overwrite custom content |

---

### sync-all

Sync all resources (rules, agents, skills, system,
config) in one command.

```bash
vaultspec \
  sync-all --prune --dry-run
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown files |
| --dry-run | flag | off | Preview without writing |
| --force | flag | off | Force overwrite custom |

---

### test

Run the project test suite via pytest.

```bash
vaultspec \
  test unit --module rag
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| category | choice | all | all, unit, api, etc. |
| --module, -m | choice | none | cli, rag, vault, ... |
| extra_args | list | [] | Extra args to pytest |

Categories: `all`, `unit`, `api`, `search`, `index`,
`quality`.

Modules: `cli`, `rag`, `vault`, `protocol`,
`orchestration`, `subagent`, `core`, `mcp_tools`.

```bash
# Run only unit tests for the vault module
vaultspec \
  test unit --module vault -v
```

---

### doctor

Check prerequisites and system health: Python version,
CUDA/GPU availability, optional dependencies, and
`.lance` index status.

```bash
vaultspec doctor
```

```text
Python: 3.13.11 [OK]
CUDA: 13.0 [OK]
GPU: NVIDIA RTX 4080 SUPER (16 GB) [OK]
lancedb: installed [OK]
sentence_transformers: installed [OK]
pytest: installed [OK]
ruff: installed [OK]
.lance index: 12.3 MB [OK]

All checks passed.
```

---

### init

Bootstrap the `.vaultspec/` and `.vault/` directory
structure in a new project.

```bash
vaultspec init
```

Creates:

- `.vaultspec/` subdirectories: `agents/`, `rules/`,
  `skills/`, `templates/`, `system/`
- `.vault/` subdirectories: `adr/`, `audit/`, `exec/`,
  `plan/`, `reference/`, `research/`
- Stub files: `system/framework.md`,
  `system/project.md`

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --force | flag | off | Overwrite existing |

---

### readiness

Assess codebase governance readiness. Scans the project
and reports on vault coverage, rule presence, and
overall SDD adoption.

```bash
vaultspec readiness
vaultspec readiness --json
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --json | flag | off | Output as JSON |

---

### hooks

Manage and trigger event-driven hooks defined in
`.vaultspec/rules/hooks/`.

**Supported events:**

| Event | Fires After |
| ----- | ----------- |
| `vault.document.created` | `vaultspec vault create` |
| `vault.index.updated` | `vaultspec vault index` |
| `config.synced` | `vaultspec sync-all` |
| `audit.completed` | `vaultspec vault audit` |

#### `hooks list`

List all registered hooks with their events and enabled state.

```bash
vaultspec hooks list
```

```text
Name                        Event                      Enabled
--------------------------------------------------------------
example-audit-on-create     vault.document.created     false
notify-on-sync              config.synced              true
```

#### `hooks run`

Trigger hooks for a named event manually. Useful for testing
hooks without running the full lifecycle command.

```bash
vaultspec hooks run vault.document.created \
  --path .vault/research/my-research.md
```

```text
Triggering hooks for event 'vault.document.created'
  [example-audit-on-create] shell: OK (0.3s)
```

| Arg/Flag | Type | Default | Desc |
| -------- | ---- | ------- | ---- |
| event | string | **required** | Event name to trigger |
| --path | string | none | Sets the `{path}` context variable for hook interpolation |

The `--path` flag populates the `{path}` placeholder in hook
command and task templates. For events that carry a document
path (`vault.document.created`), this is the path to the
affected document. Other context variables (`{root}`,
`{event}`) are always set automatically.

---

## vault -- Vault Manager

Manages the `.vault/` documentation vault: creation,
auditing, indexing, and semantic search.

```text
vaultspec vault \
  [global-flags] <command> [options]
```

### Global Flags (vault)

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root | Path | cwd | Override workspace root |
| --content-dir | Path | none | Content source directory |
| --verbose, -v | flag | off | Verbose output (INFO) |
| --debug | flag | off | Debug logging (DEBUG) |
| --quiet, -q | flag | off | Suppress info output (WARNING) |
| --version, -V | flag | -- | Show version and exit |

---

### audit

Audit the vault for document counts, feature coverage,
verification errors, and graph hotspots.

```bash
vaultspec vault \
  audit --summary --features --verify
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --summary | flag | off | Show doc counts by type |
| --features | flag | off | List all feature tags |
| --verify | flag | off | Run full verification |
| --fix | flag | off | Auto-repair common violations |
| --graph | flag | off | Show link-graph hotspots |
| --root | Path | cwd | Vault root directory |
| --limit | int | 10 | Limit report items |
| --type | string | none | Filter by DocType |
| --feature | string | none | Filter by feature tag |
| --json | flag | off | Output as JSON |

```bash
vaultspec vault \
  audit --summary --json
```

---

### create

Create a new document from a template with pre-filled
frontmatter.

```bash
vaultspec vault create \
  --type research --feature my-feature
```

Creates `.vault/research/YYYY-MM-DD-my-feature-research.md`
from the research template.

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --type | choice | **required** | adr, audit, etc. |
| --feature | string | **required** | Feature (kebab) |
| --title | string | none | Document title |
| --root | Path | cwd | Vault root directory |

Types: `adr`, `audit`, `exec`, `plan`, `reference`,
`research`.

---

### index

Build or update the vector search index over `.vault/`
documents.

**Requires NVIDIA GPU with CUDA.**

```bash
# Incremental index (default — new/changed files)
vaultspec vault index

# Full re-index
vaultspec vault index --full
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root | Path | cwd | Vault root directory |
| --full | flag | off | Force full re-index |
| --json | flag | off | Output result as JSON |

```text
Device: cuda (NVIDIA RTX 4080 SUPER)

Running incremental index...
Index complete:
  Total documents: 214
  Added:           3
  Updated:         1
  Removed:         0
  Duration:        1842ms
  Device:          cuda
```

---

### search

Semantic search over vault documents using hybrid
BM25 + ANN retrieval.

**Requires NVIDIA GPU with CUDA.**

```bash
vaultspec vault \
  search "protocol integration patterns"
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| query | string | **required** | Search query |
| --root | Path | cwd | Vault root directory |
| --limit | int | 5 | Number of results |
| --json | flag | off | Output as JSON |

Filter tokens can be embedded in the query:

```bash
# Only ADRs about search
vaultspec vault \
  search "type:adr search implementation"

# Only RAG-related research
vaultspec vault \
  search "type:research feature:rag embeddings"
```

See the [Search Guide](search-guide.md) for full filter
syntax and retrieval pipeline details.

---

## subagent -- Agent Runner

Launches sub-agents via ACP (Agent Client Protocol),
runs the MCP server, or starts an A2A HTTP server.

```text
vaultspec subagent \
  [global-flags] <command> [options]
```

### Global Flags (subagent)

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root | Path | cwd | Workspace root dir |
| --content-dir | Path | none | Content source directory |
| --verbose, -v | flag | off | Verbose output (INFO) |
| --debug | flag | off | Debug logging (DEBUG) |
| --quiet, -q | flag | off | Suppress info output (WARNING) |
| --version, -V | flag | -- | Show version, exit |

---

### run

Execute a sub-agent with a goal, task, or plan.

```bash
vaultspec subagent run \
  --agent vaultspec-adr-researcher \
  --goal "Research embedding models for RAG"
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --agent, -a | string | **required** | Agent name |
| --goal | string | none | Primary objective |
| --task, -t | string | none | Task string (legacy) |
| --task-file, -f | Path | none | Markdown task file (legacy) |
| --plan | Path | none | Plan file path |
| --context | Path | none | Context file(s), repeatable |
| --model, -m | string | none | Override model |
| --provider, -p | choice | none | gemini or claude |
| --mode | choice | read-write | Permission mode |
| --interactive, -i | flag | off | Multi-turn mode |
| --resume-session | string | none | Resume session by ID |
| --max-turns | int | none | Maximum agent turns |
| --budget | float | none | Token budget limit |
| --effort | choice | none | low, medium, or high |
| --output-format | choice | none | text, json, or stream-json |
| --mcp-servers | string | none | MCP server config as JSON |

Permission modes: `read-write` or `read-only`.

```bash
# Research with context files
vaultspec subagent run \
  --agent vaultspec-adr-researcher \
  --goal "Analyze trade-offs: A vs B" \
  --context .vault/research/patterns.md

# Code review in read-only mode
vaultspec subagent run \
  --agent vaultspec-code-reviewer \
  --goal "Review unsafe block in utils.py" \
  --mode read-only

# Execute a plan with Gemini
vaultspec subagent run \
  --agent vaultspec-standard-executor \
  --plan .vault/plan/feature-plan.md \
  --provider gemini
```

---

### serve

Start the subagent MCP server (`vaultspec-mcp`).
Exposes 5 tools: `list_agents`, `dispatch_agent`,
`get_task_status`, `cancel_task`, `get_locks`.

```bash
vaultspec subagent serve
```

The server runs over stdio transport. Configure it in
`mcp.json` for use with Claude or other MCP clients.

---

### a2a-serve

Start an A2A (Agent-to-Agent) HTTP server for peer
communication between agents.

```bash
vaultspec subagent \
  a2a-serve --executor gemini --port 10010
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --executor, -e | choice | claude | claude or gemini |
| --port | int | 10010 | Listen port |
| --agent, -a | string | vaultspec-researcher | Agent to serve |
| --model, -m | string | none | Override model |
| --mode | choice | read-only | Permission mode |

---

### list

List all available agents in the workspace.

```bash
vaultspec subagent list
```

```text
Agents in .vaultspec/rules/agents:
  vaultspec-adr-researcher
  vaultspec-code-reviewer
  vaultspec-complex-executor
  vaultspec-docs-curator
  vaultspec-reference-auditor
  vaultspec-researcher
  vaultspec-simple-executor
  vaultspec-standard-executor
  vaultspec-writer
```

---

## team -- Team Lifecycle Manager

Manages multi-agent teams: forming teams from A2A agent
URLs, assigning tasks, relaying messages, spawning new
agents, and dissolving sessions.

```text
vaultspec team \
  [global-flags] <command> [options]
```

### Global Flags (team)

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root | Path | cwd | Workspace root dir |
| --content-dir | Path | none | Content source directory |
| --verbose, -v | flag | off | Verbose output (INFO) |
| --debug | flag | off | Debug logging (DEBUG) |
| --quiet, -q | flag | off | Suppress info output (WARNING) |
| --version, -V | flag | -- | Show version, exit |

---

### team create

Form a new named team from one or more A2A agent URLs.
Contacts each agent, discovers its card, and persists
the team session.

```bash
vaultspec team create \
  --name my-team \
  --agents localhost:10010,localhost:10011
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Team name |
| --agents | string | **required** | Comma-separated host:port pairs |
| --api-key | string | none | API key for X-API-Key header |

---

### status

Print the status of a persisted team session and all its
member agents.

```bash
vaultspec team status --name my-team
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Team name |

---

### team list

List all persisted team sessions.

```bash
vaultspec team list
```

---

### assign

Dispatch a task description to a single named team
member.

```bash
vaultspec team assign \
  --name my-team \
  --agent researcher \
  --task "Summarize the latest ADRs"
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Team name |
| --agent | string | **required** | Agent name to assign |
| --task | string | **required** | Task description |
| --api-key | string | none | API key |

---

### broadcast

Send the same message to every team member in parallel.

```bash
vaultspec team broadcast \
  --name my-team \
  --message "Please summarize your last task"
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Team name |
| --message | string | **required** | Message text |
| --api-key | string | none | API key |

---

### message

Send a message to a specific team member, or relay output
from one agent to another.

```bash
# Direct message
vaultspec team message \
  --name my-team \
  --to writer \
  --content "Write a plan for the health endpoint"

# Relay output from another agent
vaultspec team message \
  --name my-team \
  --to writer \
  --content "Expand on this" \
  --from researcher \
  --src-task-id <task-id>
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Team name |
| --to | string | **required** | Destination agent name |
| --content | string | **required** | Message content |
| --from | string | none | Source agent (relay mode) |
| --src-task-id | string | none | Source task ID (required with --from) |
| --api-key | string | none | API key |

---

### spawn

Spawn a new agent subprocess and register it as a team
member.

```bash
vaultspec team spawn \
  --name my-team \
  --agent new-researcher \
  --script scripts/researcher.py \
  --port 10012
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Team name |
| --agent | string | **required** | Logical name for new agent |
| --script | Path | **required** | Python script that starts A2A server |
| --port | int | **required** | TCP port for the agent |
| --api-key | string | none | API key |

---

### dissolve

Dissolve a team session and terminate all spawned agent
processes. Prompts for confirmation unless `--force`.

```bash
vaultspec team dissolve --name my-team --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --name | string | **required** | Team name |
| --force | flag | off | Skip confirmation |
| --api-key | string | none | API key |

---

## mcp -- MCP Server

Start the unified vaultspec MCP server over stdio
transport. Exposes subagent dispatch tools and team
coordination tools.

```bash
vaultspec mcp
```

Requires `VAULTSPEC_MCP_ROOT_DIR` to be set. Configure
in `.mcp.json` for use with Claude Code or other MCP
clients.

**Registered tools:**

- `list_agents` — discover available agents
- `dispatch_agent` — run a sub-agent with a task
- `get_task_status` — check on a running task
- `cancel_task` — cancel a running task
- `get_locks` — view active advisory file locks
- `create_team`, `team_status`, `list_teams`,
  `dispatch_task`, `broadcast_message`, `send_message`,
  `spawn_agent`, `dissolve_team` — team coordination

---

## Configuration Reference

vaultspec is configured through `VAULTSPEC_*` environment variables. All
variables are optional and have sensible defaults.

Configuration is resolved in priority order:

1. Explicit overrides (for dependency injection or testing)
2. `VAULTSPEC_*` environment variable
3. Dataclass default

Source: `src/vaultspec/config/config.py`

### Agent Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_ROOT_DIR` | Path | cwd() | Workspace root directory |
| `VAULTSPEC_AGENT_MODE` | string | read-write | Agent permission mode (read-write, read-only) |
| `VAULTSPEC_SYSTEM_PROMPT` | string | none | Custom system prompt for agent sessions |
| `VAULTSPEC_MAX_TURNS` | int | none | Maximum conversation turns (min: 1) |
| `VAULTSPEC_BUDGET_USD` | float | none | Budget cap in USD (min: 0) |
| `VAULTSPEC_ALLOWED_TOOLS` | csv list | [] | Comma-separated list of allowed tool names |
| `VAULTSPEC_DISALLOWED_TOOLS` | csv list | [] | Comma-separated list of disallowed tool names |
| `VAULTSPEC_EFFORT` | string | none | Effort level hint for agent sessions |
| `VAULTSPEC_OUTPUT_FORMAT` | string | none | Output format for agent responses |
| `VAULTSPEC_FALLBACK_MODEL` | string | none | Fallback model identifier |
| `VAULTSPEC_INCLUDE_DIRS` | csv list | [] | Directories to include |

### MCP Server Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_MCP_ROOT_DIR` | Path | none | Root directory for MCP server (required at startup) |
| `VAULTSPEC_MCP_PORT` | int | 10010 | MCP server port (1-65535) |
| `VAULTSPEC_MCP_HOST` | string | 0.0.0.0 | MCP server host address |
| `VAULTSPEC_MCP_TTL_SECONDS` | float | 3600.0 | Task TTL in seconds (min: 0) |
| `VAULTSPEC_MCP_POLL_INTERVAL` | float | 5.0 | Agent file polling interval in seconds (min: 0.5) |

### A2A Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_A2A_DEFAULT_PORT` | int | 10010 | Default port for A2A agent cards (1-65535) |
| `VAULTSPEC_A2A_HOST` | string | localhost | Default host for A2A agent cards |

### Storage Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_DOCS_DIR` | string | .vault | Documentation vault directory name |
| `VAULTSPEC_FRAMEWORK_DIR` | string | .vaultspec | Framework directory name |
| `VAULTSPEC_LANCE_DIR` | string | .lance | LanceDB vector store directory name |
| `VAULTSPEC_INDEX_METADATA_FILE` | string | index_meta.json | Index metadata filename |

### Tool Directory Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_CLAUDE_DIR` | string | .claude | Claude tool directory name |
| `VAULTSPEC_GEMINI_DIR` | string | .gemini | Gemini tool directory name |
| `VAULTSPEC_AGENT_DIR` | string | .agent | Agent tool directory name |

### RAG Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_EMBEDDING_MODEL` | string | nomic-ai/nomic-embed-text-v1.5 | Sentence-transformer model for embeddings |
| `VAULTSPEC_EMBEDDING_BATCH_SIZE` | int | 64 | GPU batch size for embedding inference (min: 1) |
| `VAULTSPEC_MAX_EMBED_CHARS` | int | 8000 | Max characters per document before truncation (min: 100) |
| `VAULTSPEC_GRAPH_TTL_SECONDS` | float | 300.0 | Graph cache TTL in seconds for search re-ranking |

### Orchestration Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_TASK_ENGINE_TTL_SECONDS` | float | 3600.0 | Task engine TTL in seconds (min: 0) |

### I/O Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_IO_BUFFER_SIZE` | int | 8192 | I/O read buffer size in bytes (min: 1) |
| `VAULTSPEC_TERMINAL_OUTPUT_LIMIT` | int | 1000000 | Terminal output byte limit for subprocess capture |

### Editor Settings

| Variable | Type | Default | Description |
| -------- | ---- | ------- | ----------- |
| `VAULTSPEC_EDITOR` | string | zed -w | Default editor command for rules, agents, and skills |

### Type Reference

- **string** — Plain text value
- **int** — Integer number
- **float** — Decimal number
- **Path** — Filesystem path (absolute or relative)
- **csv list** — Comma-separated values parsed into a list (`"tool1,tool2,tool3"`)

Optional values (marked "none" as default) are not set unless explicitly provided.
