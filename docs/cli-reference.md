# CLI Reference

vaultspec provides three CLI entry points, all located
in `.vaultspec/lib/scripts/`.

## cli.py -- Framework Manager

Manages rules, agents, skills, config, and system
prompts across tool destinations (`.claude/`, `.gemini/`,
`.agent/`).

```text
python .vaultspec/lib/scripts/cli.py \
  [global-flags] <resource> <command> [options]
```

### Global Flags

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root ROOT | Path | cwd | Override workspace root |
| --verbose, -v | flag | off | Verbose output (INFO) |
| --debug | flag | off | Debug logging (DEBUG) |
| --version, -V | flag | -- | Show version and exit |

---

### rules

Manage behavioral constraint files in
`.vaultspec/rules/`.

#### `rules list`

List all rules (built-in and custom).

```bash
python .vaultspec/lib/scripts/cli.py rules list
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
python .vaultspec/lib/scripts/cli.py rules add \
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
python .vaultspec/lib/scripts/cli.py \
  rules show vaultspec-skills.builtin
```

#### `rules edit`

Open a rule in `$EDITOR`.

```bash
python .vaultspec/lib/scripts/cli.py \
  rules edit my-rule
```

#### `rules remove`

Delete a rule and its synced copies. Prompts for
confirmation unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py \
  rules remove my-rule --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --force | flag | off | Skip confirmation |

#### `rules rename`

Rename a rule and update synced copies.

```bash
python .vaultspec/lib/scripts/cli.py \
  rules rename old-rule new-rule
```

#### `rules sync`

Sync rules to tool destinations (`.claude/rules/`,
`.gemini/rules/`, etc.).

```bash
python .vaultspec/lib/scripts/cli.py \
  rules sync --dry-run
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown files |
| --dry-run | flag | off | Preview without writing |

---

### agents

Manage agent definitions in `.vaultspec/agents/`.

#### `agents list`

List all agents with their tiers and resolved models.

```bash
python .vaultspec/lib/scripts/cli.py agents list
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
python .vaultspec/lib/scripts/cli.py agents add \
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
python .vaultspec/lib/scripts/cli.py \
  agents show vaultspec-researcher
```

#### `agents edit`

Open an agent definition in `$EDITOR`.

```bash
python .vaultspec/lib/scripts/cli.py \
  agents edit vaultspec-researcher
```

#### `agents remove`

Delete an agent and its synced copies. Prompts for
confirmation unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py \
  agents remove my-agent --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --force | flag | off | Skip confirmation |

#### `agents rename`

Rename an agent and update synced copies.

```bash
python .vaultspec/lib/scripts/cli.py \
  agents rename old-agent new-agent
```

#### `agents sync`

Sync agent definitions to tool destinations with
tier-to-model resolution.

```bash
python .vaultspec/lib/scripts/cli.py \
  agents sync --prune --dry-run
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --prune | flag | off | Remove unknown agents |
| --dry-run | flag | off | Preview without writing |

#### `agents set-tier`

Update an agent's capability tier.

```bash
python .vaultspec/lib/scripts/cli.py \
  agents set-tier vaultspec-researcher \
  --tier HIGH
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --tier | choice | **required** | LOW, MEDIUM, HIGH |

---

### skills

Manage skill definitions in `.vaultspec/skills/`.

#### `skills list`

List all managed skills (files matching
`vaultspec-*.md`).

```bash
python .vaultspec/lib/scripts/cli.py skills list
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
python .vaultspec/lib/scripts/cli.py skills add \
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
python .vaultspec/lib/scripts/cli.py \
  skills show vaultspec-research
```

#### `skills edit`

Open a skill in `$EDITOR`.

```bash
python .vaultspec/lib/scripts/cli.py \
  skills edit vaultspec-research
```

#### `skills remove`

Delete a skill and its synced copies. Prompts for
confirmation unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py \
  skills remove vaultspec-my-skill --force
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --force | flag | off | Skip confirmation |

#### `skills rename`

Rename a skill and update synced copies.

```bash
python .vaultspec/lib/scripts/cli.py \
  skills rename vaultspec-old vaultspec-new
```

#### `skills sync`

Sync skills to tool destinations. Each skill becomes a
`<name>/SKILL.md` directory.

```bash
python .vaultspec/lib/scripts/cli.py \
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
python .vaultspec/lib/scripts/cli.py config show
```

#### `config sync`

Sync configuration to tool-specific files. Skips files
with custom content unless `--force`.

```bash
python .vaultspec/lib/scripts/cli.py \
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
`.vaultspec/system/` parts.

#### `system show`

Display system prompt parts and their generation
targets.

```bash
python .vaultspec/lib/scripts/cli.py system show
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
python .vaultspec/lib/scripts/cli.py \
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
python .vaultspec/lib/scripts/cli.py \
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
python .vaultspec/lib/scripts/cli.py \
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
`orchestration`, `subagent`.

Example -- run only unit tests for the vault module
with verbose output:

```bash
python .vaultspec/lib/scripts/cli.py \
  test unit --module vault -v
```

---

### doctor

Check prerequisites and system health: Python version,
CUDA/GPU availability, optional dependencies, and
`.lance` index status.

```bash
python .vaultspec/lib/scripts/cli.py doctor
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
python .vaultspec/lib/scripts/cli.py init
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

## docs.py -- Vault Manager

Manages the `.vault/` documentation vault: creation,
auditing, indexing, and semantic search.

```text
python .vaultspec/lib/scripts/docs.py \
  [global-flags] <command> [options]
```

### Global Flags (docs.py)

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --verbose, -v | flag | off | Verbose output (INFO) |
| --debug | flag | off | Debug logging (DEBUG) |
| --version, -V | flag | -- | Show version and exit |

---

### audit

Audit the vault for document counts, feature coverage,
verification errors, and graph hotspots.

```bash
python .vaultspec/lib/scripts/docs.py \
  audit --summary --features --verify
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --summary | flag | off | Show doc counts by type |
| --features | flag | off | List all feature tags |
| --verify | flag | off | Run full verification |
| --graph | flag | off | Show link-graph hotspots |
| --root | Path | cwd | Vault root directory |
| --limit | int | 10 | Limit report items |
| --type | string | none | Filter by DocType |
| --feature | string | none | Filter by feature tag |
| --json | flag | off | Output as JSON |

Example -- JSON summary:

```bash
python .vaultspec/lib/scripts/docs.py \
  audit --summary --json
```

---

### create

Create a new document from a template with pre-filled
frontmatter.

```bash
python .vaultspec/lib/scripts/docs.py create \
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
# Incremental index (default -- new/changed files)
python .vaultspec/lib/scripts/docs.py index

# Full re-index
python .vaultspec/lib/scripts/docs.py index --full
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root | Path | cwd | Vault root directory |
| --full | flag | off | Force full re-index |
| --json | flag | off | Output result as JSON |

Example output:

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
python .vaultspec/lib/scripts/docs.py \
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
python .vaultspec/lib/scripts/docs.py \
  search "type:adr search implementation"

# Only RAG-related research
python .vaultspec/lib/scripts/docs.py \
  search "type:research feature:rag embeddings"

# Docs from a specific month
python .vaultspec/lib/scripts/docs.py \
  search "date:2026-02 protocol changes"
```

See the [Search Guide](search-guide.md) for full
filter syntax.

---

## subagent.py -- Agent Runner

Launches sub-agents via ACP (Agent Client Protocol),
runs the MCP server, or starts an A2A HTTP server.

```text
python .vaultspec/lib/scripts/subagent.py \
  [global-flags] <command> [options]
```

### Global Flags (subagent.py)

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --root | Path | cwd | Workspace root dir |
| --version, -V | flag | -- | Show version, exit |

---

### run

Execute a sub-agent with a goal, task, or plan.

```bash
python .vaultspec/lib/scripts/subagent.py run \
  --agent vaultspec-adr-researcher \
  --goal "Research embedding models for RAG"
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --agent, -a | string | **required** | Agent name |
| --goal | string | none | Primary objective |
| --task, -t | string | none | Task (legacy) |
| --plan | Path | none | Plan file path |
| --context | Path | none | Context file(s) |
| --model, -m | string | none | Override model |
| --provider, -p | choice | none | gemini or claude |
| --mode | choice | read-write | Permission mode |
| --interactive, -i | flag | off | Multi-turn mode |
| --verbose, -v | flag | off | Verbose (INFO) |
| --debug | flag | off | Debug (DEBUG) |
| --task-file, -f | Path | none | Task file (legacy) |

Permission modes: `read-write` or `read-only`.

Examples:

```bash
# Research with context files
python .vaultspec/lib/scripts/subagent.py run \
  --agent vaultspec-adr-researcher \
  --goal "Analyze trade-offs: A vs B" \
  --context .vault/research/patterns.md

# Code review in read-only mode
python .vaultspec/lib/scripts/subagent.py run \
  --agent vaultspec-code-reviewer \
  --goal "Review unsafe block in utils.py" \
  --mode read-only

# Execute a plan with Gemini
python .vaultspec/lib/scripts/subagent.py run \
  --agent vaultspec-standard-executor \
  --plan .vault/plan/feature-plan.md \
  --provider gemini
```

---

### serve

Start the subagent MCP server (`vs-subagent-mcp`).
Exposes 5 tools: `list_agents`, `dispatch_agent`,
`get_task_status`, `cancel_task`, `get_locks`.

```bash
python .vaultspec/lib/scripts/subagent.py serve
```

The server runs over stdio transport. Configure it in
`mcp.json` for use with Claude or other MCP clients.

---

### a2a-serve

Start an A2A (Agent-to-Agent) HTTP server for peer
communication between agents.

```bash
python .vaultspec/lib/scripts/subagent.py \
  a2a-serve --executor gemini --port 10010
```

| Flag | Type | Default | Desc |
| ---- | ---- | ------- | ---- |
| --executor, -e | choice | claude | claude or gemini |
| --port | int | 10010 | Listen port |
| --agent, -a | string | vs-researcher | Agent to serve |
| --model, -m | string | none | Override model |
| --mode | choice | read-only | Permission mode |

The `--agent` default is `vaultspec-researcher`.

---

### list

List all available agents in the workspace.

```bash
python .vaultspec/lib/scripts/subagent.py list
```

```text
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
