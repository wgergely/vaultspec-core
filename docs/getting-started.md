# Getting Started

This guide walks you through installing vaultspec, running your first
commands, and completing a full workflow cycle.

## Prerequisites

- **Python 3.13+** -- verify with `python --version`
- **NVIDIA GPU with CUDA 13.0+ and compute capability >= 7.5** (Turing+: RTX 2000+, T4+, A-series, H-series) -- required for the RAG index backend (`[rag]` extras) only. Verify with `nvidia-smi`

  > **Note:** `nvidia-smi` shows the driver's maximum CUDA compatibility version, not the installed toolkit version. Run `nvcc --version` to confirm the actual CUDA toolkit version installed on your system.
- **pip** -- Python package manager

> **No GPU?** Search and indexing require an NVIDIA GPU with CUDA 13.0+.
> All other vaultspec features — rules, skills, agents, config sync, document
> management — work without a GPU. Install without `[rag]` and skip the index
> step.

## Installation

```bash
# Clone the repository
git clone https://github.com/wgergely/vaultspec
cd vaultspec

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows

# Install with RAG and development dependencies
pip install -e ".[rag,dev]" --extra-index-url https://download.pytorch.org/whl/cu130
```

> **Important:** Always use `--extra-index-url` (not `--index-url`) when installing the `[rag]` extras. Without this flag, pip resolves PyTorch from the default PyPI index and installs the CPU-only build. A CPU-only PyTorch installation will appear to succeed but fail at runtime with `GPUNotAvailableError` when you run `docs.py index` or `docs.py search`.

The `rag` extra installs PyTorch (CUDA), sentence-transformers, and LanceDB.
The `dev` extra installs testing tools (pytest, ruff, etc.).

Without a GPU, omit `[rag]`:

```bash
pip install -e ".[dev]"
```

## Verify Your Setup

After installation, run the doctor command to confirm everything is working:

```bash
python .vaultspec/lib/scripts/cli.py doctor
```

Expected output (with GPU):

```text
vaultspec doctor
  Python:      3.13.x  OK
  PyTorch:     2.x.x+cu130  OK
  CUDA:        13.0  OK
  GPU:         NVIDIA GeForce RTX ...  OK
  LanceDB:     OK
  Agents:      9 found
  Rules:       3 found
  Skills:      14 found
```

Fix any items flagged before proceeding. Common issues are listed in the
[Troubleshooting](#troubleshooting) section below.

## First Commands

vaultspec provides three CLI entry points:

| CLI | Purpose |
| :--- | :--- |
| `cli.py` | Manage agents, rules, skills, and config sync |
| `docs.py` | Vault operations: create, audit, index, search |
| `subagent.py` | Run sub-agents and MCP server |

All scripts live in `.vaultspec/lib/scripts/`.

### List available agents

```bash
python .vaultspec/lib/scripts/cli.py agents list
```

This shows all agent definitions in `.vaultspec/agents/`, each with a tier
(HIGH, MEDIUM, LOW) that maps to model capability.

### List rules and skills

```bash
python .vaultspec/lib/scripts/cli.py rules list
python .vaultspec/lib/scripts/cli.py skills list
```

Rules constrain agent behavior. Skills map user intents to agent workflows.

### Audit the vault

```bash
python .vaultspec/lib/scripts/docs.py audit --summary
```

Shows document counts by type (ADR, audit, exec, plan, reference, research)
and feature coverage.

## Create Your First Document

Use `docs.py create` to scaffold a new document from a template:

```bash
python .vaultspec/lib/scripts/docs.py create --type research --feature my-feature
```

This creates `.vault/research/YYYY-MM-DD-my-feature-research.md` with proper
frontmatter (tags, date, related links) pre-filled from the research template.

Available types: `adr`, `audit`, `exec`, `plan`, `reference`, `research`.

## Build the Search Index

The search index enables semantic search over your vault documents.
It requires a GPU.

```bash
# Incremental index (only new/changed files)
python .vaultspec/lib/scripts/docs.py index

# Full re-index
python .vaultspec/lib/scripts/docs.py index --full
```

First run downloads the embedding model (~270MB) and indexes all documents.
Subsequent runs use incremental mtime-based change detection.

## Search the Vault

```bash
# Basic search
python .vaultspec/lib/scripts/docs.py search "protocol integration"

# With filters
python .vaultspec/lib/scripts/docs.py search "type:adr feature:rag search results"

# Limit results
python .vaultspec/lib/scripts/docs.py search "agent dispatch" --limit 10

# JSON output
python .vaultspec/lib/scripts/docs.py search "embedding model" --json
```

Search uses hybrid retrieval: BM25 keyword matching + ANN vector similarity,
fused with Reciprocal Rank Fusion (RRF). See the [Search Guide](search-guide.md)
for full syntax.

## Full Workflow Example

Here is a concrete example of the 5-phase workflow for "adding a new CLI
command":

### Phase 1: Research

Tell your AI assistant:

> "Activate `vaultspec-research` to investigate best practices for CLI
> argument parsing in Python, focusing on argparse subcommand patterns."

This dispatches the `vaultspec-adr-researcher` agent, which produces a
research artifact at `.vault/research/YYYY-MM-DD-cli-commands-research.md`.

**Verify:** The file exists and contains a `## Findings` section with
populated content. If the agent reported no findings, re-run with a more
specific prompt.

### Phase 2: Specify

> "Activate `vaultspec-adr` to formalize our decision on the CLI command
> structure."

This creates an Architecture Decision Record at
`.vault/adr/YYYY-MM-DD-cli-commands-adr.md`, documenting the chosen approach
with rationale and tradeoffs.

**Verify:** The ADR exists and contains `## Rationale` and `## Consequences`
sections. The `related:` frontmatter field should link to the research
artifact from Phase 1.

### Phase 3: Plan

> "Activate `vaultspec-write` to create an implementation plan for the new
> CLI commands."

The `vaultspec-writer` agent produces a step-by-step plan at
`.vault/plan/YYYY-MM-DD-cli-commands-plan.md`, referencing the ADR and
research.

**Verify:** The plan exists and lists numbered steps. The agent will present
the plan for your approval — review it before proceeding. Type "approve" or
request changes.

### Phase 4: Execute

> "Activate `vaultspec-execute` to implement the plan."

Executor agents (simple, standard, or complex depending on task difficulty)
implement each step. Execution records are saved to
`.vault/exec/YYYY-MM-DD-cli-commands/`.

**Verify:** Step records exist in `.vault/exec/YYYY-MM-DD-cli-commands/` for
each completed phase. Each file should list modified files and a description
of what was done.

### Phase 5: Verify

> "Activate `vaultspec-review` to audit the implementation."

The `vaultspec-code-reviewer` agent validates the code against the plan,
checking for safety violations and intent compliance.

**Verify:** A review artifact exists at
`.vault/exec/YYYY-MM-DD-cli-commands/YYYY-MM-DD-cli-commands-review.md`.
Its `**Status:**` field should read `PASS`. If it reads `FAIL` or
`REVISION REQUIRED`, the agent will list what needs to be fixed before the
feature is considered complete.

## Troubleshooting

### `GPUNotAvailableError` on startup

vaultspec requires a CUDA-capable NVIDIA GPU for RAG features. If you see
this error when running `docs.py index` or `docs.py search`:

```text
GPUNotAvailableError: No CUDA-capable GPU detected.
```

Options:

- Verify your GPU is detected: `nvidia-smi`
- Verify CUDA is installed: `nvcc --version`
- Reinstall PyTorch with the correct CUDA index URL:

```bash
pip install torch --extra-index-url https://download.pytorch.org/whl/cu130
```

- If you don't have a GPU, skip `[rag]` in your install and avoid `index`
  and `search` commands. All other features work without a GPU.

### PyTorch installed but CUDA not found

This usually means PyTorch was installed from the default PyPI index (CPU
build) instead of the CUDA build. Reinstall with the CUDA index URL:

```bash
pip uninstall torch torchvision torchaudio
pip install torch --extra-index-url https://download.pytorch.org/whl/cu130
```

Verify the installation: `python -c "import torch; print(torch.cuda.is_available())"`
should print `True`.

### Agent not found

If `cli.py agents list` shows fewer agents than expected, or a dispatch fails
with "agent not found":

```bash
python .vaultspec/lib/scripts/cli.py doctor
```

The doctor will report whether the agents directory is correctly located.
Ensure you are running commands from the project root (the directory
containing `.vaultspec/`).

## Next Steps

- [Concepts](concepts.md) -- understand the SDD methodology, agent tiers,
  and protocol stack
- [Configuration](configuration.md) -- customize vaultspec with environment
  variables
- [Search Guide](search-guide.md) -- master the search syntax and understand
  GPU requirements
- [Framework Manual](../.vaultspec/README.md) -- deep dive into workflows,
  agents, and diagrams
