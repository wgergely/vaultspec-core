<img src="docs/assets/logo.png" width="150" alt="vaultspec-core logo">

# vaultspec-core

Decision-driven harness for coding agents, and humans.

Vaultspec is a coding harness: it implements a structured coding workflow focused on
#features, decision records and the documents grounding them. It bundles rules, agents,
skills, and tools to author the documents that describe and track a feature's
development.

The harness supports Claude Code, Codex, Gemini CLI, and Antigravity.

[![build](https://img.shields.io/github/actions/workflow/status/nevenincs/vaultspec-core/ci.yml?branch=main&style=flat&label=build&logo=githubactions&logoColor=white&labelColor=24292f&color=57606a)](https://github.com/nevenincs/vaultspec-core/actions/workflows/ci.yml)
[![release](https://img.shields.io/pypi/v/vaultspec-core?style=flat&label=release&logo=pypi&logoColor=white&labelColor=24292f&color=57606a)](https://pypi.org/project/vaultspec-core/)
[![runtime](https://img.shields.io/badge/runtime-Python%203.13%20%7C%203.14-57606a?style=flat&logo=python&logoColor=white&labelColor=24292f)](https://www.python.org/downloads/)
[![license](https://img.shields.io/github/license/nevenincs/vaultspec-core?style=flat&label=license&logo=opensourceinitiative&logoColor=white&labelColor=24292f&color=57606a)](https://github.com/nevenincs/vaultspec-core/blob/main/LICENSE)

[Install](#install) · [Start a feature](#start-a-feature) ·
[Documentation](#documentation)

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run this
from your repository root:

```bash
uvx vaultspec-core install
```

Vaultspec supports Python 3.13 and 3.14. uv downloads a supported interpreter if needed.

The installer writes rules, skills, and agent configuration into your project and
configures a Model Context Protocol (MCP) server so your agent can call the tools.

Workflow documents live in `.vault/`; the policy lives in `.vaultspec/`. Commit both so
teammates share the records and rules. Installation also manages ignore rules for local
state and writes pre-commit configuration. Activating commit hooks is a
[separate choice](docs/framework.md#decisions-you-make-once).

Keep the `uvx` prefix when running commands yourself. For persistent or project-local
installation, see [installation options](docs/framework.md#installation-options).
[Homebrew and Scoop](docs/channels.md) provide standalone binaries.

## Start a feature

Open your repository in your coding agent and describe the work:

> Start a new vaultspec pipeline to research options for adding full-text search to the
> API.

The workflow covers research, an architecture decision record (ADR), an implementation
plan, execution, and review. The ADR records the chosen approach and its consequences.
Review the decisions and approve the plan before implementation.

The agent creates documents through the tools, then writes the research and other prose.
Records stay in the repository as Markdown. The installed rules tell the agent to
consult existing records when continuing work.

You can also create the first research document yourself:

```bash
uvx vaultspec-core vault add research --feature search-api
```

This creates a scaffold. Fill in the research before moving on to the decision record.
Follow the [workflow guide](docs/framework.md#begin-a-pipeline) for the remaining
stages.

## Documentation

- [Documentation index](docs/README.md): choose a guide for your task.
- [Framework manual](docs/framework.md): run the workflow and customize its rules.
- [Document syntax](docs/syntax.md): edit prose and manage document structure.
- [Verifying a workspace](docs/verification.md): check the setup and repair errors.
- [CLI reference](docs/CLI.md) and [MCP reference](docs/MCP.md): commands, tools, and
  configuration.

Open `.vault/` in [Obsidian](https://obsidian.md) to browse its linked documents. The
optional [vaultspec-rag](https://github.com/nevenincs/vaultspec-rag) package adds
semantic search across the vault and your code.

## Support and license

vaultspec-core is in beta. Report bugs, ask questions, or propose changes on the
[issue tracker](https://github.com/nevenincs/vaultspec-core/issues). For contributions
and releases, see [maintainer documentation](docs/README.md#for-maintainers).

Released under the [MIT License](LICENSE).
