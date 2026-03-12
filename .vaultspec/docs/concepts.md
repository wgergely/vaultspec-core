# Concepts

`vaultspec-core` is a workspace runtime. It installs a structured framework into a project, keeps that framework synchronized, and helps you create and audit the project record stored alongside it.

The core boundary is simple:

- `.vaultspec/` holds the framework resources that shape how work is done.
- `.vault/` holds the durable project record created inside that framework.
- `vaultspec-core` manages and audits both inside a workspace.
- `vaultspec-mcp` exposes that same workspace to MCP clients for query, status, and create operations.

This is the mental model to keep in mind as you learn the product. `vaultspec-core` is not a packaged agent orchestrator. It is the local runtime that makes a workspace legible, consistent, and automatable.

## Workspace Anatomy

A vaultspec workspace has two major directories with different roles.

### `.vaultspec/`: Framework Resources

`.vaultspec/` is the source of truth for framework content in the workspace. It contains the rules, skills, agents, system content, templates, and related resources that define how the workspace behaves.

You customize `.vaultspec/` when you want to change framework behavior for that workspace. These files are part of the project's operating model, not disposable cache.

### `.vault/`: Durable Project Record

`.vault/` stores the project record generated while work happens. This is where structured documents live: research notes, ADRs, plans, execution records, references, audits, and related artifacts.

If `.vaultspec/` defines the framework, `.vault/` captures the history of decisions and work performed within it.

## Vault Document Model

Vault documents are durable markdown records organized by type. Common document families include:

- `research`
- `adr`
- `plan`
- `exec`
- `reference`
- `audit`

These documents are meant to be inspected, updated, and audited over time. They are not temporary prompts or hidden runtime state.

### Tags

Vault documents follow a two-tag model:

- one directory tag that identifies the document family
- one feature tag that ties the document to a specific feature or effort

This keeps the vault browsable by both document type and feature lifecycle.

### Filenames and Lifecycle

Filenames should stay stable, readable, and aligned with the feature they describe. A feature typically accumulates multiple vault documents over time: research leads to decisions, decisions lead to plans, plans lead to execution and review artifacts. The vault preserves that trail.

## Managing Framework Resources and Syncing Outputs

`vaultspec-core` keeps the workspace coherent by syncing framework-managed resources and auditing the resulting workspace state.

A typical pattern is:

1. initialize the workspace
2. sync framework-managed content
3. customize local rules, skills, agents, system content, templates, or hooks as needed
4. create vault documents as work progresses
5. audit the vault and workspace state regularly

The important concept is that sync and audit operate on real workspace files. They keep the framework side and the project-record side aligned without turning this product into a hidden orchestration layer.

## Hooks

Hooks are local automation attached to workspace events. They are shell actions only.

The runtime supports three workspace events. When those events fire, configured hook actions can run inside the workspace. Hooks are useful for lightweight local automation such as validation, notifications, or follow-up commands tied to normal workspace activity.

Hooks should be treated as local, explicit workspace behavior. They are not a remote agent runtime and they should not be modeled as a hidden orchestration layer.

## MCP Surface

`vaultspec-mcp` is the local MCP server for a vaultspec workspace.

Its job is to expose the workspace through MCP so clients can inspect status, query vault content, and create or update workspace artifacts using MCP tools. Typical tools include:

- `query_vault(...)`
- `feature_status(...)`
- `workspace_status(...)`

Use `vaultspec-mcp` when you want an MCP client to work against the same `.vaultspec/` and `.vault/` content that `vaultspec-core` manages on disk.

The MCP server extends the local workspace into MCP; it does not redefine the product as a hosted orchestration system.

## First Steps

A truthful first-time path looks like this:

1. Install the package.
2. Run `vaultspec-core init` in your workspace.
3. Run `vaultspec-core sync-all`.
4. Inspect and customize `.vaultspec/` resources if your workspace needs local conventions.
5. Create your first vault document with `vaultspec-core vault add`.
6. Audit the result with `vaultspec-core vault audit`.
7. Optionally connect an MCP client to `vaultspec-mcp` and use tools such as `query_vault(...)`, `feature_status(...)`, and `workspace_status(...)`.

Start with the workspace. Learn the difference between framework resources and vault documents. Everything else builds from that split.

## See Also

- [CLI Reference](./cli-reference.md)
- [Hooks Guide](./hooks-guide.md)
- [Vault Query Guide](./vault-query-guide.md)
