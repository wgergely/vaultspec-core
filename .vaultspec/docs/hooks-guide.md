# Hooks Guide

Hooks let you attach automated actions to vaultspec lifecycle events. They fire
automatically when the framework completes a lifecycle operation — no manual
invocation required. Hook failures are always silent to the parent command:
errors are logged at debug level and never interrupt your workflow.

---

## Overview

Hooks are YAML files stored in `.vaultspec/rules/hooks/`. Each file defines:

- **Which event** triggers the hook
- **Whether the hook is enabled** (default: `true`)
- **A list of actions** to execute in order — shell commands or agent dispatches

The engine loads all `*.yaml` and `*.yml` files in the hooks directory when a
lifecycle event fires. If a stem name appears in both `.yaml` and `.yml`, the
`.yaml` file takes precedence and a warning is logged.

---

## Supported Events

| Event | Fires After | Context Variables |
| ----- | ----------- | ----------------- |
| `vault.document.created` | `vaultspec vault create` | `{path}`, `{root}`, `{event}` |
| `vault.index.updated` | `vaultspec vault index` | `{root}`, `{event}` |
| `config.synced` | `vaultspec sync-all` | `{root}`, `{event}` |
| `audit.completed` | `vaultspec vault audit` | `{root}`, `{event}` |

Context variables are available as `{placeholder}` strings inside `command` and
`task` fields. Unrecognized placeholders are left unchanged.

---

## YAML Schema

```yaml
event: <event-name>      # required — one of the 4 supported events above
enabled: true            # optional — default true; set false to disable without deleting
actions:
  - type: shell
    command: "echo {root}"          # supports {root}, {event}, {path} placeholders

  - type: agent
    name: vaultspec-docs-curator    # vaultspec agent name (must exist in .vaultspec/rules/agents/)
    task: "Curate docs at {root}"   # goal string passed to the agent; supports placeholders
```

All fields at the top level are the same for every hook. The `actions` list is
ordered — actions execute sequentially.

---

## Shell Actions

Shell actions run an arbitrary command in a subprocess.

- **Timeout:** 60 seconds. If exceeded, the process is killed and the action is
  recorded as failed.
- **Security:** The command is tokenized with `shlex.split` (POSIX mode on Linux/macOS,
  Windows-safe mode on Windows). It is never passed to a shell interpreter
  (`shell=False`), so shell metacharacters like `&&`, `|`, and `$()` are not
  interpreted. Use a wrapper script if you need shell composition.
- **Exit code:** Non-zero exit is recorded as a failure in the result, but
  never raises an exception in the parent command.

```yaml
actions:
  - type: shell
    command: "vaultspec vault audit --verify --root {root}"
```

---

## Agent Actions

Agent actions dispatch a vaultspec sub-agent via `vaultspec subagent run`.

- **Timeout:** 300 seconds. If exceeded, the process is killed and the action
  is recorded as failed.
- **Invocation:** `python -m vaultspec subagent run --agent <name> --goal <task>`
- **Agent name:** Must match an agent definition in `.vaultspec/rules/agents/`.
- **Task string:** Supports `{placeholder}` interpolation.

```yaml
actions:
  - type: agent
    name: vaultspec-docs-curator
    task: "A new vault document was created at {path}. Review it for tag compliance and broken wiki-links."
```

---

## Error Behavior

Hook failures are completely transparent to the parent lifecycle command:

- Shell action fails (non-zero exit, timeout, or missing executable) — logged
  at `WARNING` level, parent command continues.
- Agent action fails (non-zero exit or timeout) — logged at `WARNING` level,
  parent command continues.
- YAML parse error — logged at `WARNING` level, that hook file is skipped.
- Any unhandled exception inside `fire_hooks()` — caught and logged at `DEBUG`
  level, parent command continues.

To see hook output, run with `--verbose` or `--debug`:

```bash
vaultspec --verbose vault create --type research --feature my-feature
```

---

## Manual Testing

Use `vaultspec hooks` subcommands to test hooks without running a full
lifecycle command.

**List all loaded hooks:**

```bash
vaultspec hooks list
```

```text
Name                        Event                      Enabled
--------------------------------------------------------------
example-audit-on-create     vault.document.created     false
notify-on-sync              config.synced              true
```

**Trigger hooks for a specific event:**

```bash
vaultspec hooks run vault.document.created \
  --path .vault/research/2026-02-23-my-feature-research.md
```

```text
Triggering hooks for event 'vault.document.created'
  [example-audit-on-create] shell: OK (0.4s)
```

The `--path` flag sets the `{path}` context variable in hook templates. The
`{root}` and `{event}` variables are always set automatically.

---

## Creating a Hook

1. Create a YAML file in `.vaultspec/rules/hooks/`:

   ```bash
   touch .vaultspec/rules/hooks/my-hook.yaml
   ```

2. Choose one of the 4 supported events and set it:

   ```yaml
   event: vault.document.created
   ```

3. Add one or more actions:

   ```yaml
   actions:
     - type: shell
       command: "echo 'New doc created: {path}'"
   ```

4. Set `enabled: true` (or omit it, since `true` is the default):

   ```yaml
   enabled: true
   ```

5. Verify the hook loads correctly:

   ```bash
   vaultspec hooks list
   ```

6. Test it manually before relying on the lifecycle trigger:

   ```bash
   vaultspec hooks run vault.document.created --path /path/to/doc.md
   ```

---

## Full Example

```yaml
# .vaultspec/rules/hooks/curate-on-create.yaml
#
# Dispatches the docs-curator agent every time a new vault document is created.

event: vault.document.created
enabled: true
actions:
  - type: shell
    command: "vaultspec vault audit --verify --root {root}"

  - type: agent
    name: vaultspec-docs-curator
    task: "A new vault document was created at {path} (event: {event}). Review the document for tag compliance and broken wiki-links, and fix any issues found."
```
