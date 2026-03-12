# Hooks Guide

`vaultspec-core` supports simple local hooks for a small set of runtime
events. Hooks are defined as YAML files, loaded from the workspace, and
executed in order when their event fires.

## What Hooks Are

A hook file becomes a runtime hook object with:

- `name`: derived from the filename stem
- `event`: required
- `enabled`: optional, defaults to `true`
- `actions`: ordered list of actions

Today, the only shipped action type is `shell`. It requires a `command`.
Unknown action types are ignored with a warning rather than failing hook
loading.

## Where Hook Files Live

Hooks live in:

```text
.vaultspec/rules/hooks/
```

The loader scans both:

- `*.yaml`
- `*.yml`

If both files exist with the same stem, the `.yaml` file wins and the `.yml`
duplicate is ignored.

Hook names come from the filename stem, not from a YAML field.

Example:

```text
.vaultspec/rules/hooks/on-doc-created.yaml
```

This loads as the hook named `on-doc-created`.

## Hook Schema

The live schema is:

```yaml
event: vault.document.created
enabled: true
actions:
  - type: shell
    command: "echo created {path}"
```

Notes:

- `event` is required.
- `enabled` is optional. If omitted, the hook is enabled.
- `actions` run in the order listed.
- Each action must currently be `type: shell` with a `command`.

## Supported Events

These are the only supported events at runtime:

| Event | Fired by | Context |
| --- | --- | --- |
| `vault.document.created` | `vaultspec-core vault add --type <doc-type> --feature <feature> [--title ...]` | `path`, `root`, `event` |
| `config.synced` | `vaultspec-core sync-all` | `root`, `event` |
| `audit.completed` | `vaultspec-core vault audit [--summary\|--features\|--verify\|--graph\|...]` | `root`, `event` |

There is no live trigger for `vault.index.updated`.

## Shell Action Behavior

`shell` actions are plain command strings with simple placeholder
interpolation.

### Interpolation

Interpolation is direct string replacement of `{key}` with the matching value
from the event context.

Example:

```yaml
actions:
  - type: shell
    command: "echo {event} {path}"
```

For `vault.document.created`, the available context keys are:

- `{event}`
- `{path}`
- `{root}`

For `config.synced` and `audit.completed`, the available keys are:

- `{event}`
- `{root}`

Interpolation is simple string replacement, not a richer template language.

### Execution Environment

Shell commands run with:

- `cwd` set to the resolved target workspace
- `VAULTSPEC_TARGET_DIR` set in the environment
- a `60s` timeout per command

Write hook commands as workspace-relative operations.

## Manual Testing

List loaded hooks:

```bash
vaultspec-core hooks list
```

Run hooks for a specific event:

```bash
vaultspec-core hooks run vault.document.created --path .vault/research/example.md
```

Behavior of `hooks run`:

- Unsupported events exit with code `1` and print the supported event set.
- If no enabled hooks match the event, the command exits `0` quietly.

## Commands That Naturally Fire Hooks

Create a vault document:

```bash
vaultspec-core vault add --type research --feature hooks --title "Hook Notes"
```

Sync configuration:

```bash
vaultspec-core sync-all
```

Run a vault audit:

```bash
vaultspec-core vault audit --summary
```

A practical document-created hook:

```yaml
event: vault.document.created
actions:
  - type: shell
    command: "echo created {path} in {root}"
```

## Non-Features And Pitfalls

Keep these constraints in mind:

- only three events are supported: `vault.document.created`, `config.synced`, and `audit.completed`
- only `shell` actions are supported in the live schema
- there is no subagent hook runtime, task field, or `vault.index.updated` trigger
- examples should use `vaultspec-core` command names and top-level target selection such as `--target`
- hook failure behavior is not fully hidden; write commands so failures are explicit and debuggable

## See Also

- [CLI Reference](./cli-reference.md)
- [Vault Query Guide](./vault-query-guide.md)
