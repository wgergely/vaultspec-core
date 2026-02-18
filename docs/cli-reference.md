# CLI Reference

vaultspec provides three CLI entry points, all located in `.vaultspec/lib/scripts/`.

## cli.py -- Framework Manager

Manages rules, agents, skills, config, and system prompts across tool destinations (`.claude/`, `.gemini/`, `.antigravity/`).

```
python .vaultspec/lib/scripts/cli.py [global-flags] <resource> <command> [options]
```

### Global Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--root ROOT` | Path | cwd | Override workspace root directory |
| `--verbose`, `-v` | flag | off | Enable verbose output (INFO level) |
| `--debug` | flag | off | Enable debug logging (DEBUG level) |
| `--version`, `-V` | flag | -- | Show version and exit |

---

### rules

Manage behavioral constraint files in `.vaultspec/rules/`.

#### `rules list`

List all rules (built-in and custom).

```bash
python .vaultspec/lib/scripts/cli.py rules list
```

```
Name                                     Source
-------------------------------------------------------
vaultspec-skills.builtin.md              Built-in
my-custom-rule.md                        Custom
```

#### `rules add`

Create a new custom rule. Opens `$EDITOR` if no `--content` is provided.

```bash
python .vaultspec/lib/scripts/cli.py rules add --name my-rule --content "Always use snake_case."
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--name` | string | **required** | Rule name |
| `--content` | string | none | Rule content (opens editor if omitted) |
| `--force` | flag | off | Overwrite existing rule |

#### `rules show`

Display a rule's metadata and content.

```bash
python .vaultspec/lib/scripts/cli.py rules show vaultspec-skills.builtin
```

#### `rules edit`

Open a rule in `$EDITOR`.

```bash
python .vaultspec/lib/scripts/cli.py rules edit my-rule
```

#### `rules remove`

Delete a rule and its synced copies. Prompts for confirmation unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py rules remove my-rule --force
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force` | flag | off | Skip confirmation prompt |

#### `rules rename`

Rename a rule and update synced copies.

```bash
python .vaultspec/lib/scripts/cli.py rules rename old-rule new-rule
```

#### `rules sync`

Sync rules to tool destinations (`.claude/rules/`, `.gemini/rules/`, etc.).

```bash
python .vaultspec/lib/scripts/cli.py rules sync --dry-run
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--prune` | flag | off | Remove unknown files from destinations |
| `--dry-run` | flag | off | Preview changes without writing |

---

### agents

Manage agent definitions in `.vaultspec/agents/`.

#### `agents list`

List all agents with their tiers and resolved models.

```bash
python .vaultspec/lib/scripts/cli.py agents list
```

```
Name                      Tier     Claude                    Gemini
-----------------------------------------------------------------------------------
vaultspec-adr-researcher  HIGH     claude-sonnet-4-5-20250929 gemini-2.5-pro
vaultspec-researcher      MEDIUM   claude-sonnet-4-5-20250929 gemini-2.5-flash
vaultspec-simple-executor LOW      claude-haiku-4-5-20251001  gemini-2.5-flash
```

#### `agents add`

Create a new agent definition. Opens `$EDITOR` after scaffolding.

```bash
python .vaultspec/lib/scripts/cli.py agents add --name my-agent --tier HIGH --description "My agent"
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--name` | string | **required** | Agent name |
| `--description` | string | `""` | Agent description |
| `--tier` | choice | `MEDIUM` | Capability tier: `LOW`, `MEDIUM`, `HIGH` |
| `--force` | flag | off | Overwrite existing agent |
| `--template` | string | none | Template name from `.vaultspec/templates/` to pre-populate |

#### `agents show`

Display an agent's metadata and content.

```bash
python .vaultspec/lib/scripts/cli.py agents show vaultspec-researcher
```

#### `agents edit`

Open an agent definition in `$EDITOR`.

```bash
python .vaultspec/lib/scripts/cli.py agents edit vaultspec-researcher
```

#### `agents remove`

Delete an agent and its synced copies. Prompts for confirmation unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py agents remove my-agent --force
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force` | flag | off | Skip confirmation prompt |

#### `agents rename`

Rename an agent and update synced copies.

```bash
python .vaultspec/lib/scripts/cli.py agents rename old-agent new-agent
```

#### `agents sync`

Sync agent definitions to tool destinations with tier-to-model resolution.

```bash
python .vaultspec/lib/scripts/cli.py agents sync --prune --dry-run
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--prune` | flag | off | Remove unknown agents from destinations |
| `--dry-run` | flag | off | Preview changes without writing |

#### `agents set-tier`

Update an agent's capability tier.

```bash
python .vaultspec/lib/scripts/cli.py agents set-tier vaultspec-researcher --tier HIGH
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--tier` | choice | **required** | New tier: `LOW`, `MEDIUM`, `HIGH` |

---

### skills

Manage skill definitions in `.vaultspec/skills/`.

#### `skills list`

List all managed skills (files matching `vaultspec-*.md`).

```bash
python .vaultspec/lib/scripts/cli.py skills list
```

```
Name                           Description
------------------------------------------------------------------------------------------
vaultspec-research             Use it when unsure about how to proceed with a complex ...
vaultspec-execute              Skill to execute implementation plans. Delegates to spec...
```

#### `skills add`

Create a new skill. Names are automatically prefixed with `vaultspec-` if needed.

```bash
python .vaultspec/lib/scripts/cli.py skills add --name my-skill --description "Does something"
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--name` | string | **required** | Skill name (auto-prefixed with `vaultspec-`) |
| `--description` | string | `""` | Skill description |
| `--force` | flag | off | Overwrite existing skill |
| `--template` | string | none | Template name from `.vaultspec/templates/` to pre-populate |

#### `skills show`

Display a skill's metadata and content.

```bash
python .vaultspec/lib/scripts/cli.py skills show vaultspec-research
```

#### `skills edit`

Open a skill in `$EDITOR`.

```bash
python .vaultspec/lib/scripts/cli.py skills edit vaultspec-research
```

#### `skills remove`

Delete a skill and its synced copies. Prompts for confirmation unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py skills remove vaultspec-my-skill --force
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force` | flag | off | Skip confirmation prompt |

#### `skills rename`

Rename a skill and update synced copies.

```bash
python .vaultspec/lib/scripts/cli.py skills rename vaultspec-old vaultspec-new
```

#### `skills sync`

Sync skills to tool destinations. Each skill becomes a `<name>/SKILL.md` directory.

```bash
python .vaultspec/lib/scripts/cli.py skills sync --prune
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--prune` | flag | off | Remove unknown `vaultspec-*` skill dirs from destinations |
| `--dry-run` | flag | off | Preview changes without writing |

---

### config

Manage tool configuration files (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`).

#### `config show`

Display framework and project configuration content, plus generated rule references per tool.

```bash
python .vaultspec/lib/scripts/cli.py config show
```

#### `config sync`

Sync configuration to tool-specific files. Skips files with custom content unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py config sync --force --dry-run
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--prune` | flag | off | Remove unknown files |
| `--dry-run` | flag | off | Preview changes without writing |
| `--force` | flag | off | Overwrite files with custom (non-CLI-managed) content |

---

### system

Manage system prompt assembly from `.vaultspec/system/` parts.

#### `system show`

Display system prompt parts and their generation targets.

```bash
python .vaultspec/lib/scripts/cli.py system show
```

```
Name                      Tool Filter      Lines
------------------------------------------------
base                      -               42
project                   -               15
```

#### `system sync`

Assemble and sync system prompts to tool destinations (e.g., `.gemini/SYSTEM.md`).

```bash
python .vaultspec/lib/scripts/cli.py system sync --force
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--prune` | flag | off | Remove unknown files |
| `--dry-run` | flag | off | Preview changes without writing |
| `--force` | flag | off | Overwrite files with custom content |

---

### sync-all

Sync all resources (rules, agents, skills, system, config) in one command.

```bash
python .vaultspec/lib/scripts/cli.py sync-all --prune --dry-run
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--prune` | flag | off | Remove unknown files from all destinations |
| `--dry-run` | flag | off | Preview changes without writing |
| `--force` | flag | off | Force overwrite of custom content |

---

### test

Run the project test suite via pytest.

```bash
python .vaultspec/lib/scripts/cli.py test unit --module rag
```

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `category` | choice | `all` | Test category: `all`, `unit`, `api`, `search`, `index`, `quality` |
| `--module`, `-m` | choice | none | Filter by module: `cli`, `rag`, `vault`, `protocol`, `orchestration`, `subagent` |
| `extra_args` | list | `[]` | Additional arguments passed to pytest |

Example -- run only unit tests for the vault module with verbose output:

```bash
python .vaultspec/lib/scripts/cli.py test unit --module vault -v
```

---

### doctor

Check prerequisites and system health: Python version, CUDA/GPU availability, optional dependencies, and `.lance` index status.

```bash
python .vaultspec/lib/scripts/cli.py doctor
```

```
Python: 3.13.11 [OK]
CUDA: 13.0 [OK]
GPU: NVIDIA GeForce RTX 4080 SUPER (16.0 GB) [OK]
lancedb: installed [OK]
sentence_transformers: installed [OK]
pytest: installed [OK]
ruff: installed [OK]
.lance index: 12.3 MB [OK]

All checks passed.
```

---

### init

Bootstrap the `.vaultspec/` and `.vault/` directory structure in a new project.

```bash
python .vaultspec/lib/scripts/cli.py init
```

Creates:

- `.vaultspec/` subdirectories: `agents/`, `rules/`, `skills/`, `templates/`, `system/`
- `.vault/` subdirectories: `adr/`, `audit/`, `exec/`, `plan/`, `reference/`, `research/`
- Stub files: `system/framework.md`, `system/project.md`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force` | flag | off | Overwrite existing structure |

---

## docs.py -- Vault Manager

Manages the `.vault/` documentation vault: creation, auditing, indexing, and semantic search.

```
python .vaultspec/lib/scripts/docs.py [global-flags] <command> [options]
```

### Global Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--verbose`, `-v` | flag | off | Enable verbose output (INFO level) |
| `--debug` | flag | off | Enable debug logging (DEBUG level) |
| `--version`, `-V` | flag | -- | Show version and exit |

---

### audit

Audit the vault for document counts, feature coverage, verification errors, and graph hotspots.

```bash
python .vaultspec/lib/scripts/docs.py audit --summary --features --verify
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--summary` | flag | off | Show document counts by type |
| `--features` | flag | off | List all feature tags |
| `--verify` | flag | off | Run full frontmatter and integrity verification |
| `--graph` | flag | off | Show link-graph hotspots |
| `--root` | Path | cwd | Vault root directory |
| `--limit` | int | `10` | Limit number of items in reports |
| `--type` | string | none | Filter hotspots by DocType (e.g., `adr`) |
| `--feature` | string | none | Filter hotspots by feature tag |
| `--json` | flag | off | Output results in JSON format |

Example -- JSON summary:

```bash
python .vaultspec/lib/scripts/docs.py audit --summary --json
```

---

### create

Create a new document from a template with pre-filled frontmatter.

```bash
python .vaultspec/lib/scripts/docs.py create --type research --feature my-feature
```

Creates `.vault/research/YYYY-MM-DD-my-feature-research.md` from the research template.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--type` | choice | **required** | Document type: `adr`, `audit`, `exec`, `plan`, `reference`, `research` |
| `--feature` | string | **required** | Feature name (kebab-case) |
| `--title` | string | none | Document title |
| `--root` | Path | cwd | Vault root directory |

---

### index

Build or update the vector search index over `.vault/` documents.

**Requires NVIDIA GPU with CUDA.**

```bash
# Incremental index (default -- only new/changed files)
python .vaultspec/lib/scripts/docs.py index

# Full re-index
python .vaultspec/lib/scripts/docs.py index --full
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--root` | Path | cwd | Vault root directory |
| `--full` | flag | off | Force full re-index (default: incremental via mtime) |
| `--json` | flag | off | Output result as JSON |

Example output:

```
Device: cuda (NVIDIA GeForce RTX 4080 SUPER, 16376MB VRAM)

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

Semantic search over vault documents using hybrid BM25 + ANN retrieval.

**Requires NVIDIA GPU with CUDA.**

```bash
python .vaultspec/lib/scripts/docs.py search "protocol integration patterns"
```

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `query` | string | **required** | Search query (supports filter tokens) |
| `--root` | Path | cwd | Vault root directory |
| `--limit` | int | `5` | Number of results to return |
| `--json` | flag | off | Output results as JSON |

Filter tokens can be embedded in the query:

```bash
# Only ADRs about search
python .vaultspec/lib/scripts/docs.py search "type:adr search implementation"

# Only RAG-related research
python .vaultspec/lib/scripts/docs.py search "type:research feature:rag embeddings"

# Docs from a specific month
python .vaultspec/lib/scripts/docs.py search "date:2026-02 protocol changes"
```

See the [Search Guide](search-guide.md) for full filter syntax.

---

## subagent.py -- Agent Runner

Launches sub-agents via ACP (Agent Client Protocol), runs the MCP server, or starts an A2A HTTP server.

```
python .vaultspec/lib/scripts/subagent.py [global-flags] <command> [options]
```

### Global Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--root` | Path | cwd | Workspace root directory |
| `--version`, `-V` | flag | -- | Show version and exit |

---

### run

Execute a sub-agent with a goal, task, or plan.

```bash
python .vaultspec/lib/scripts/subagent.py run --agent vaultspec-adr-researcher --goal "Research embedding models for RAG"
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--agent`, `-a` | string | **required** | Agent name from `.vaultspec/agents/` |
| `--goal` | string | none | Primary objective (preferred over `--task`) |
| `--task`, `-t` | string | none | Task description (legacy, prefer `--goal`) |
| `--plan` | Path | none | Path to a plan file to execute |
| `--context` | Path | none | Context file path (repeatable for multiple files) |
| `--model`, `-m` | string | none | Override the tier-resolved model |
| `--provider`, `-p` | choice | none | Force provider: `gemini` or `claude` |
| `--mode` | choice | `read-write` | Permission mode: `read-write` or `read-only` |
| `--interactive`, `-i` | flag | off | Keep session open for multi-turn interaction |
| `--verbose`, `-v` | flag | off | Enable verbose output (INFO level) |
| `--debug` | flag | off | Enable debug logging (DEBUG level) |
| `--task-file`, `-f` | Path | none | Path to markdown task file (legacy) |

Examples:

```bash
# Research with context files
python .vaultspec/lib/scripts/subagent.py run \
  --agent vaultspec-adr-researcher \
  --goal "Analyze trade-offs of Pattern A vs B" \
  --context .vault/research/2026-02-07-patterns-research.md

# Code review in read-only mode
python .vaultspec/lib/scripts/subagent.py run \
  --agent vaultspec-code-reviewer \
  --goal "Review the unsafe block in src/utils.py" \
  --mode read-only

# Execute a plan with Gemini
python .vaultspec/lib/scripts/subagent.py run \
  --agent vaultspec-standard-executor \
  --plan .vault/plan/2026-02-10-feature-phase1-plan.md \
  --provider gemini
```

---

### serve

Start the subagent MCP server (`vs-subagent-mcp`). Exposes 5 tools: `list_agents`, `dispatch_agent`, `get_task_status`, `cancel_task`, `get_locks`.

```bash
python .vaultspec/lib/scripts/subagent.py serve
```

The server runs over stdio transport. Configure it in `mcp.json` for use with Claude or other MCP clients.

---

### a2a-serve

Start an A2A (Agent-to-Agent) HTTP server for peer communication between agents.

```bash
python .vaultspec/lib/scripts/subagent.py a2a-serve --executor gemini --port 10010
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--executor`, `-e` | choice | `claude` | Executor backend: `claude` or `gemini` |
| `--port` | int | `10010` | Port to listen on |
| `--agent`, `-a` | string | `vaultspec-researcher` | Agent name to serve |
| `--model`, `-m` | string | none | Override default model |
| `--mode` | choice | `read-only` | Permission mode: `read-write` or `read-only` |

---

### list

List all available agents in the workspace.

```bash
python .vaultspec/lib/scripts/subagent.py list
```

```
Agents in .vaultspec/agents:
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
