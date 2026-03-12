# vaultspec Framework Manual

## Scope

This manual describes the current shipped product boundary for a `vaultspec` workspace.

- `vaultspec-core` manages the workspace on disk.
- `vaultspec-mcp` exposes that same workspace to MCP clients.
- `.vaultspec/` is the framework resource tree: the source material the runtime reads, validates, and syncs into tool-facing surfaces.
- `.vault/` is the durable project record: research, decisions, plans, execution records, reviews, and related artifacts created within the framework.

This README focuses on what lives under `.vaultspec/`, how the runtime consumes it, and what gets synced out of it.

## Directory Map

```text
.vaultspec/
├─ docs/                  Human-facing reference material for operators and contributors
└─ rules/                 Runtime-managed framework sources
   ├─ rules/              Behavioral rules and policy text consumed by generated surfaces
   ├─ skills/             Task-specific workflow instructions and reusable procedures
   ├─ agents/             Agent/persona inventory as framework content
   ├─ system/             Composable system fragments for context, responsibility, and sync outputs
   ├─ templates/          Templates for durable artifacts written under .vault/
   └─ hooks/              Hook definitions and hook runtime resources
```

### What each subtree is for

| Path | Purpose |
| --- | --- |
| `.vaultspec/docs/` | Reference documentation for humans: concepts, command usage, hooks, querying the vault, and related guides. |
| `.vaultspec/rules/rules/` | Stable rule text that shapes generated instructions and workspace behavior. |
| `.vaultspec/rules/skills/` | Reusable skill definitions for focused workflows. |
| `.vaultspec/rules/agents/` | The current inventory of agent/persona definitions as source content under the framework tree. |
| `.vaultspec/rules/system/` | System-level prompt fragments and responsibility boundaries assembled into synced outputs. |
| `.vaultspec/rules/templates/` | Canonical templates for records written into `.vault/`. |
| `.vaultspec/rules/hooks/` | Hook definitions and resources used by the runtime hook system. |

## How The Runtime Uses `.vaultspec/`

`vaultspec-core` treats `.vaultspec/` as a resource tree. It reads these sources, shows the effective state, validates them, and syncs generated outputs for the local workspace.

### Bootstrap and full sync

Use `init` to create or normalize the framework tree, and `sync-all` to refresh generated surfaces from the source resources.

```bash
vaultspec-core init
vaultspec-core sync-all
```

### Inspect resource inventories

Use the list/show commands to inspect what the runtime currently sees.

```bash
vaultspec-core rules list
vaultspec-core skills list
vaultspec-core agents list
vaultspec-core config show
vaultspec-core system show
vaultspec-core hooks list
```

### Preview sync effects

Use dry runs when you want to inspect planned changes before writing synced outputs.

```bash
vaultspec-core config sync --dry-run
vaultspec-core system sync --dry-run
```

### Run hooks from the managed hook tree

Hooks are sourced from `.vaultspec/rules/hooks/`, not from a legacy top-level hooks directory.

```bash
vaultspec-core hooks run vault.document.created --path .vault/research/example.md
```

## Synced Outputs And Tool Surfaces

The framework source tree is not the same thing as the generated tool surfaces it produces.

`vaultspec-core` can project `.vaultspec/` into workspace-facing outputs such as:

- `AGENTS.md`
- `.claude/...`
- `.gemini/...`
- `.agents/...`

These synced outputs are derived artifacts. The editable source of truth remains under `.vaultspec/`, especially `.vaultspec/rules/` and `.vaultspec/docs/`. When framework resources change, resync the workspace rather than hand-maintaining generated copies.

`vaultspec-mcp` is separate from those synced files. It does not define a second framework tree. Instead, it serves the same workspace model to MCP clients by pointing at the target workspace directory.

Example client configuration:

```json
{
  "mcpServers": {
    "vaultspec-core": {
      "command": "vaultspec-mcp",
      "env": {
        "VAULTSPEC_TARGET_DIR": "/path/to/workspace"
      }
    }
  }
}
```

## Relationship To `.vault/`

`.vaultspec/` and `.vault/` serve different roles:

- `.vaultspec/` contains framework resources: rules, skills, agents, system fragments, templates, hooks, and reference docs.
- `.vault/` contains durable project records created within that framework.

Typical `.vault/` operations use the framework resources defined in `.vaultspec/`:

```bash
vaultspec-core vault add --type research --feature example-feature --title "Initial research"
vaultspec-core vault audit --summary
vaultspec-core readiness
vaultspec-core doctor
```

In practice:

- `.vaultspec/rules/templates/` shapes how new records are created.
- synced system and rule outputs shape how tools interact with those records.
- audits and readiness checks help verify that the workspace remains coherent.

## Documentation Map

Use `.vaultspec/docs/` as the human-facing reference set for the framework. The key documents are:

- [Concepts](./docs/concepts.md)
- [CLI Reference](./docs/cli-reference.md)
- [Hooks Guide](./docs/hooks-guide.md)
- [Vault Query Guide](./docs/vault-query-guide.md)

This README is the entry point. The detailed operator documentation lives in `.vaultspec/docs/`.

## Non-Goals

This manual does not cover:

- a `subagent` CLI or any `vaultspec-subagent` command surface
- packaged team or orchestration walkthroughs
- historical ACP or A2A diagrams
- stale artifact-choreography diagrams that do not match the current shipped runtime boundary
- legacy flat `system/...` or `.vaultspec/hooks/` path layouts
