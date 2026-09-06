# vaultspec framework manual

Commit your feature documents in `.vault/` and your project rules, skills, agents, and
workspace policy in `.vaultspec/`. Include `.vaultspec/workspace.json` so the policy
travels with the project. The managed `.gitignore` entries exclude local caches, logs,
and state.

<p id="what-an-absent-managed-file-means"></p>

## Manage generated files

Use the [Gitignore](CLI.md#vaultspec-core-spec-gitignore),
[Gitattributes](CLI.md#vaultspec-core-spec-gitattributes), and
[Precommit](CLI.md#vaultspec-core-spec-precommit) controls to set project policy for
those files.

Enabling or disabling changes only workspace policy; it doesn't edit or remove existing
files. Disabling Precommit also leaves any active Git hook installed.

Deleting a managed Git block or the pre-commit YAML stops ordinary sync from managing
that output locally. Install or upgrade can recreate it unless project policy disables
generation.

For [Model Context Protocol (MCP)](MCP.md), edit the canonical JSON server definitions.
Core merges Vaultspec-owned entries into enabled provider configurations and preserves
unrelated entries.

## How a feature flows into the vault

You begin a pipeline with one request, and the framework drives five stages plus an
optional code-grounding step. A skill runs each stage and writes a document to
`.vault/`:

| Stage                                 | Skill                      | Writes to           |
| ------------------------------------- | -------------------------- | ------------------- |
| Research                              | `/vaultspec-research`      | `.vault/research/`  |
| Reference *(alternative to Research)* | `/vaultspec-code-research` | `.vault/reference/` |
| Decide                                | `/vaultspec-adr`           | `.vault/adr/`       |
| Plan                                  | `/vaultspec-write`         | `.vault/plan/`      |
| Execute                               | `/vaultspec-execute`       | `.vault/exec/`      |
| Review                                | `/vaultspec-code-review`   | `.vault/audit/`     |

The `/vaultspec-*` names identify skills for your coding agent, not shell commands.

Not every request enters the pipeline. The agent sizes the work first: a change that
finishes in the current session, needs no handoff, stays in one package, and touches at
most ten files is done directly, with one line saying no plan was needed. Work that
outlives the session gets a plan; a decision that is costly to reverse (a dependency,
schema, protocol, or public interface) gets an ADR at any size. The record types and
their dependencies never change; sizing only decides which stages a feature enters.

The agent runs the stages. Your part is two approvals, the ADR and the plan, and
stepping in where judgment is needed: shaping the decision, sizing the plan, and
deciding when work is done.

## Orient: see what is in flight

From your repository, check current plan progress, next open steps, and recent changes:

```bash
vaultspec-core status
```

Once a feature has a plan, use its feature tag to trace its plans, steps, and recorded
execution evidence. Replace `search-api` with your feature tag:

```bash
vaultspec-core status search-api
```

To narrow the view to one plan, supply its stem or path instead.

The `>` marker identifies the next open step. If an open step shows `no rows`, it lacks
recorded execution evidence; that doesn't prove no work occurred.

See the [status reference](CLI.md#vaultspec-core-status) for output details and options.

## Begin a pipeline

Tell your coding agent what to build, in plain language:

> "Begin a vaultspec pipeline to implement full-text search for the API."

To enter at one stage instead, invoke its skill directly, for example
`/vaultspec-research`.

The agent stops to present the ADR and then the plan. Approving is a plain reply that
names the record. To redirect, say what is wrong and it revises that stage's document
rather than moving on, so a rejected research note gets rewritten before any decision is
built on it.

## Find a feature's documents

List a feature's records, optionally by type:

```text
$ vaultspec-core vault list --feature search-api
Vault documents
  2026-06-26-search-api-research research #search-api 2026-06-26
  2026-06-26-search-api-adr adr #search-api 2026-06-26
  2026-06-26-search-api-plan plan #search-api 2026-06-26
```

When you do not know the name, search by meaning instead. That needs
[vaultspec-rag](https://github.com/nevenincs/vaultspec-rag), a separate package which is
not installed with vaultspec-core:

```bash
vaultspec-rag search "full-text ranking and tokenizer" --type vault
```

## Find and amend an ADR

A decision lives in an Architecture Decision Record (ADR). Find it by feature:

```bash
vaultspec-core vault list adr --feature search-api
```

You can amend one two ways. Ask the agent to revise the decision, and if the direction
changes it supersedes the old ADR rather than overwriting it. Or edit the ADR's body
prose yourself, then reconcile its frontmatter and links:

```bash
vaultspec-core vault check all --fix
```

A plan is built on its ADR, so changing a decision can invalidate work already planned
against it. After amending, run `vaultspec-core status <feature>` to see which plan
steps are still open, and revise the plan before executing further.

## Make a plan

From an approved ADR, `/vaultspec-write` produces the plan in `.vault/plan/`:

> "Write the implementation plan from the ADR."

Before approving the plan, review its scope, work order, affected files, and
verification steps. If it doesn't match the approved decision, ask for revisions before
execution.

For the plan's structure and Step syntax, see [tiers](syntax.md#tiers) and
[row format](syntax.md#row-format).

## Change a plan safely

Use `vaultspec-core vault plan` to add, move, or remove Steps and their containers. Keep
structural edits out of your text editor.

Before reorganizing existing work, review the [identifier rules](syntax.md#identifiers).
See [plan commands](CLI.md#vaultspec-core-vault-plan) for arguments and examples.

## Execute a plan

After approving the plan, ask your agent to use `/vaultspec-execute`. It starts from the
next open Step and records changes in the plan's execution ledger.

To resume interrupted work, ask the agent to continue or specify a Step. Use
[status](CLI.md#vaultspec-core-status) to check progress and the next open Step.

If a closed Step is incomplete, reopen it with `vaultspec-core vault plan step uncheck`
and keep its execution records. See the
[plan commands](CLI.md#vaultspec-core-vault-plan) for arguments and other state changes.

## Review the result

Ask your agent to use `vaultspec-code-review` to compare the implementation with the
approved decision and plan. Follow the [review guide](./correctness.md) to record
findings, agree on fixes, and check the resulting changes.

<p id="everyday-commands"></p>

## Check records and project health

Before committing feature records, run:

```bash
vaultspec-core vault check all
```

If it reports problems, follow
[validation and repair](verification.md#check-records-before-committing).

After installation or an upgrade, check workspace configuration and vault records:

```bash
vaultspec-core doctor
```

To check only workspace configuration, use `vaultspec-core spec doctor`.

To inspect a feature's document links, replace `search-api` with its feature tag:

```bash
vaultspec-core vault graph --feature search-api
```

See the [graph reference](CLI.md#vaultspec-core-vault-graph) for filtering and output
options.

## Customize the policy

Add a project rule with its instructions:

```bash
vaultspec-core spec rules add enforce-newline --body "All workspace source files must end with a single trailing newline."
```

Edit `.vaultspec/rules/enforce-newline.md` to change the instructions. Then update the
enabled coding-agent integrations:

```bash
vaultspec-core sync
```

Review and commit the policy changes. For skills, agents, and other rule operations, see
the
[resource commands](CLI.md#vaultspec-core-spec-rules--vaultspec-core-spec-skills--vaultspec-core-spec-agents).

For setup and upgrades, see [installation options](#installation-options). To remove
Core from a project, follow the [uninstall reference](CLI.md#uninstall).

## Installation options

The quickstart uses `uvx vaultspec-core install`. When using this route, keep the `uvx`
prefix for later commands.

To install the CLI once and run it from any project:

```bash
uv tool install vaultspec-core
vaultspec-core install
```

To manage it as a project dependency:

```bash
uv add vaultspec-core
uv run vaultspec-core install
```

Contributors then use `uv sync` to install dependencies and `uv run vaultspec-core` to
run the CLI. Configure generated launchers under
[project integrations](#configure-project-integrations). For standalone binaries, see
[Homebrew and Scoop](channels.md).

After updating the package, run `vaultspec-core install --upgrade` in each project to
update its bundled rules, skills, and agents. Use `uvx` or `uv run` as appropriate for
your installation route.

<p id="decisions-you-make-once"></p>

## Configure project integrations

**Install mode.** Choose how generated hooks and MCP configuration launch Core with
`vaultspec-core install --mode`. See the [install reference](CLI.md#install) for modes
and selection rules.

**Pre-commit hooks.** Generated configuration doesn't activate a Git hook. If you use
pre-commit, run `pre-commit install` to activate it. Vault checks and annotation cleanup
aren't limited to staged files; cleanup modifies documents. Review changes before
committing.

Use the [pre-commit controls](CLI.md#vaultspec-core-spec-precommit) to enable or disable
configuration generation. These settings don't remove an existing configuration or
deactivate an installed hook.

**MCP clients.** Check enrollment with `vaultspec-core spec mcps status --json`. See the
[MCP tool reference](./MCP.md#tools) for the available tools.

## Machine-global runtime state

`~/.vaultspec/` is a per-account directory shared by vaultspec tools across every
repository on the machine. It is separate from a repository's `.vaultspec/`, which holds
that project's policy. You do not manage it by hand:

```text
~/.vaultspec/
├── mcp-ownership.json
└── procs/
    └── leases/
```

`procs/` holds process records and lease markers that coordinate concurrent sessions. A
record is stale when the process id it names is no longer alive.
`vaultspec-core spec doctor` reports the registry without changing it: an absent
`procs/` is informational, a live process id is healthy, and a dead one produces a
warning naming the stale record. The command never repairs or removes records. Reclaim a
stale record only through the tool that wrote it, and attach
`vaultspec-core spec doctor --json` when reporting a problem.

Tools that write into this namespace own their own record schemas, heartbeats, and
cleanup; vaultspec-core owns only the paths and the staleness rule, and its sync, prune,
and uninstall operations never rewrite the namespace. If you are building such a tool,
resolve the paths through `vaultspec_core.core.core_home_layout()` rather than spelling
them out, write records atomically, claim leases with an exclusive-creation primitive,
and keep credentials out of them.

## Related documentation

| Document                                               | What it covers                                     |
| ------------------------------------------------------ | -------------------------------------------------- |
| [Repository README](../README.md)                      | What vaultspec-core is, and installing it          |
| [Document syntax](./syntax.md)                         | Frontmatter, tags, links, and the plan row grammar |
| [Verifying a workspace and a vault](./verification.md) | The health commands and what each check proves     |
| [Review a feature implementation](./correctness.md)    | Review scope, findings, fixes, and test evidence   |
| [CLI reference](./CLI.md)                              | Every command, flag, and option                    |
| [MCP reference](./MCP.md)                              | The MCP server tools, setup, and configuration     |

For bug reports and feature requests, open an issue on the
[vaultspec-core issue tracker](https://github.com/nevenincs/vaultspec-core/issues).
