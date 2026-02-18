# Python Library API Reference

The vaultspec Python library lives under `.vaultspec/lib/src/` and is
split into several focused modules. Each module can be imported
independently; heavy dependencies (PyTorch, LanceDB) are guarded
behind lazy imports so the core vault tools remain usable without
the RAG stack.

- [core](#core) — configuration
- [vault](#vault) — document model and validation
- [rag](#rag) — vector indexing and semantic search
- [graph](#graph) — wiki-link relationship graph
- [metrics](#metrics) — vault statistics
- [verification](#verification) — structural integrity checks
- [orchestration](#orchestration) — sub-agent dispatch
- [protocol](#protocol) — ACP types and providers
- [subagent\_server](#subagent_server) — MCP server

---

## core

The `core` module provides centralised runtime configuration. A
single `VaultSpecConfig` instance is shared across the process via
a module-level singleton; the singleton is populated from environment
variables and optional caller-supplied overrides.

### core exports

| Name             | Type      | Description                    |
|------------------|-----------|--------------------------------|
| `VaultSpecConfig`| dataclass | Immutable configuration record |
| `get_config`     | function  | Return the global config       |
| `reset_config`   | function  | Clear the global singleton     |

### VaultSpecConfig

```python
from core.config import VaultSpecConfig
```

Fields (all have defaults or are resolved from `VAULTSPEC_*` env
vars):

| Field                 | Default        | Purpose       |
|-----------------------|----------------|---------------|
| `root_dir`            | `Path(".")`    | Project root  |
| `agent_mode`          | `"read-write"` | FS permission |
| `docs_dir`            | `".vault"`     | Vault dir     |
| `framework_dir`       | `".vaultspec"` | Framework dir |
| `lance_dir`           | `".lance"`     | LanceDB dir   |
| `embedding_model`     | `"nomic-..."`  | HF model ID   |
| `embedding_dimension` | `768`          | Vector dim    |
| `mcp_host`            | `"0.0.0.0"`    | MCP bind addr |
| `mcp_port`            | `10010`        | MCP port      |

### get\_config

```python
def get_config(
    overrides: dict[str, object] | None = None,
) -> VaultSpecConfig: ...
```

Returns the module-level singleton, creating it from environment
variables on first call. Pass `overrides` to patch specific fields
for the lifetime of the singleton.

### reset\_config

```python
def reset_config() -> None: ...
```

Clears the singleton so the next `get_config()` call re-reads the
environment. Primarily used in tests.

### core usage

```python
from core.config import get_config, reset_config

cfg = get_config()
print(cfg.docs_dir)   # ".vault"
print(cfg.lance_dir)  # ".lance"

# Override for testing
cfg = get_config(overrides={"docs_dir": "custom-vault"})
reset_config()
```

---

## vault

The `vault` module defines the document taxonomy and metadata schema
enforced across all `.vault/` files. It performs no I/O itself — it
is a pure model layer used by higher-level modules.

### vault exports

| Name               | Type      | Description               |
|--------------------|-----------|---------------------------|
| `DocType`          | StrEnum   | Recognised document types |
| `DocumentMetadata` | dataclass | Parsed YAML frontmatter   |
| `VaultConstants`   | class     | Structural validators     |

### DocType

```python
from vault.models import DocType
```

| Member      | Value         | Tag          |
|-------------|---------------|--------------|
| `ADR`       | `"adr"`       | `#adr`       |
| `AUDIT`     | `"audit"`     | `#audit`     |
| `EXEC`      | `"exec"`      | `#exec`      |
| `PLAN`      | `"plan"`      | `#plan`      |
| `REFERENCE` | `"reference"` | `#reference` |
| `RESEARCH`  | `"research"`  | `#research`  |

```python
dt = DocType.from_tag("#adr")  # DocType.ADR
print(dt.tag)                  # "#adr"
```

### DocumentMetadata

Parsed representation of the YAML frontmatter block. The vault
enforces a "Rule of Two": every document must have exactly two
tags — one directory tag (e.g. `#adr`) and one feature tag
(e.g. `#rag`).

```python
@dataclass
class DocumentMetadata:
    tags: list[str]
    date: str | None
    related: list[str]

    def validate(self) -> list[str]: ...
```

`validate()` returns a list of human-readable violation strings,
or an empty list when the metadata is valid.

### VaultConstants

```python
from vault.models import VaultConstants
```

| Method                        | Description           |
|-------------------------------|-----------------------|
| `is_supported_directory(d)`   | True if `d` is valid  |
| `get_tag_for_directory(d)`    | Return `#tag` or None |
| `validate_vault_structure(r)` | Check layout          |
| `validate_filename(f, t)`     | Check naming rules    |

---

## rag

The `rag` module provides semantic indexing and search over `.vault/`
documents using LanceDB for vector storage and
`nomic-embed-text-v1.5` for embeddings. All operations require a
CUDA-capable GPU; the system raises `GPUNotAvailableError` on
CPU-only machines.

The public surface is a small set of module-level functions backed
by a `VaultRAG` singleton engine.

### rag exports

| Name             | Type     | Description                |
|------------------|----------|----------------------------|
| `VaultRAG`       | class    | Lazy-init engine singleton |
| `get_engine`     | function | Return the singleton       |
| `list_documents` | function | List vault documents       |
| `get_document`   | function | Retrieve by stem ID        |
| `get_related`    | function | Wiki-link relationships    |
| `get_status`     | function | Vault + index status       |
| `index`          | function | Index documents            |
| `search`         | function | Semantic search            |

### get\_engine

```python
def get_engine(root_dir: pathlib.Path) -> VaultRAG: ...
```

Returns the module-level `VaultRAG` singleton, creating it if
necessary. Raises `GPUNotAvailableError` when no CUDA device is
detected.

### list\_documents

```python
def list_documents(
    root_dir: pathlib.Path,
    *,
    doc_type: str | None = None,
    feature: str | None = None,
) -> list[dict]: ...
```

Scans the vault filesystem (no RAG deps required). Each dict
contains: `id`, `path`, `title`, `doc_type`, `feature`, `date`,
`tags`.

### get\_document

```python
def get_document(
    root_dir: pathlib.Path,
    doc_id: str,
) -> dict | None: ...
```

Looks up a document by its stem (e.g. `"2026-02-12-rag-plan"`).
Tries the vector store first, falls back to filesystem scan.

### get\_related

```python
def get_related(
    root_dir: pathlib.Path,
    doc_id: str,
) -> dict | None: ...
```

Returns `{"doc_id": ..., "outgoing": [...], "incoming": [...]}`
using the vault graph.

### get\_status

```python
def get_status(root_dir: pathlib.Path) -> dict: ...
```

Returns a status dict with keys: `total_docs`, `types`, `features`,
and `index` (`exists`, `indexed_count`, `device`, `gpu_name`).

### index (function)

```python
def index(
    root_dir: pathlib.Path,
    *,
    full: bool = False,
) -> IndexResult: ...
```

Indexes vault documents. `full=False` (default) performs an
incremental update using mtime-based change detection. `full=True`
rebuilds from scratch.

### search (function)

```python
def search(
    root_dir: pathlib.Path,
    query: str,
    *,
    doc_type: str | None = None,
    feature: str | None = None,
    limit: int = 5,
) -> list[SearchResult]: ...
```

Runs a hybrid BM25 + ANN search with RRF reranking. `doc_type`
and `feature` narrow results to matching documents.

### rag usage

```python
from pathlib import Path
from rag.api import index, search

root = Path(".")
index(root)  # incremental index

results = search(
    root, "ADR governance workflow",
    doc_type="adr", limit=3,
)
for r in results:
    print(r.title, r.score)
```

---

## graph

The `graph` module builds an in-memory directed graph of vault
documents connected by Obsidian-style `[[wiki-links]]`. It is used
by the `rag` module to resolve relationship queries and by the
verification pipeline to detect orphaned or broken links.

### graph exports

| Name         | Type      | Description                    |
|--------------|-----------|--------------------------------|
| `DocNode`    | dataclass | A single node in the graph     |
| `VaultGraph` | class     | Directed graph from wiki-links |

### DocNode

```python
@dataclass
class DocNode:
    path: pathlib.Path
    name: str              # document stem
    doc_type: DocType | None
    tags: list[str]
    out_links: set[str]    # names this doc links to
    in_links: set[str]     # names linking here
```

### VaultGraph

```python
from graph.api import VaultGraph

graph = VaultGraph(root_dir)
```

| Method                  | Description              |
|-------------------------|--------------------------|
| `nodes`                 | All nodes by stem        |
| `get_hotspots(...)`     | Most-linked documents    |
| `get_feature_rankings()`| Features by doc count    |
| `get_orphaned()`        | No in-links or out-links |
| `get_invalid_links()`   | Broken `(src, target)`   |

### graph usage

```python
graph = VaultGraph(Path("."))
orphans = graph.get_orphaned()
hotspots = graph.get_hotspots(limit=10)
```

---

## metrics

The `metrics` module aggregates document counts and feature
statistics across the vault without requiring any RAG dependencies.

### metrics exports

| Name               | Type      | Description              |
|--------------------|-----------|--------------------------|
| `VaultSummary`     | dataclass | Aggregated vault stats   |
| `get_vault_metrics`| function  | Compute metrics          |

### VaultSummary

```python
@dataclass
class VaultSummary:
    total_docs: int
    counts_by_type: dict[DocType, int]
    total_features: int
```

### get\_vault\_metrics

```python
def get_vault_metrics(
    root_dir: pathlib.Path,
) -> VaultSummary: ...
```

Scans the vault and returns aggregate counts. No GPU or LanceDB
required.

### metrics usage

```python
from pathlib import Path
from metrics.api import get_vault_metrics

summary = get_vault_metrics(Path("."))
print(summary.total_docs)
print(summary.counts_by_type)
```

---

## verification

The `verification` module enforces structural integrity rules on
`.vault/` documents: frontmatter schema, filename conventions,
directory layout, and referential integrity of wiki-links.

### verification exports

| Name                          | Type      | Description   |
|-------------------------------|-----------|---------------|
| `VerificationError`           | dataclass | A violation   |
| `FixResult`                   | dataclass | Fix outcome   |
| `verify_vault_structure`      | function  | Full verify   |
| `verify_file`                 | function  | Single check  |
| `get_malformed`               | function  | All errors    |
| `list_features`               | function  | Feature tags  |
| `verify_vertical_integrity`   | function  | Cross-doc     |
| `fix_violations`              | function  | Auto-fix      |

### VerificationError

```python
@dataclass
class VerificationError:
    path: pathlib.Path
    message: str
```

### FixResult

```python
@dataclass
class FixResult:
    path: pathlib.Path
    action: str
    detail: str
```

### verification functions

```python
def verify_vault_structure(
    root_dir: pathlib.Path,
) -> list[VerificationError]: ...

def verify_file(
    path: pathlib.Path,
    root_dir: pathlib.Path,
) -> list[VerificationError]: ...

def get_malformed(
    root_dir: pathlib.Path,
) -> list[VerificationError]: ...

def list_features(
    root_dir: pathlib.Path,
) -> set[str]: ...

def verify_vertical_integrity(
    root_dir: pathlib.Path,
) -> list[VerificationError]: ...

def fix_violations(
    root_dir: pathlib.Path,
) -> list[FixResult]: ...
```

### verification usage

```python
from pathlib import Path
from verification.api import get_malformed, fix_violations

errors = get_malformed(Path("."))
if errors:
    fixes = fix_violations(Path("."))
    for f in fixes:
        print(f.action, f.path)
```

---

## orchestration

The `orchestration` module drives the sub-agent lifecycle: loading
agent definitions, building task prompts, spawning the agent process
via ACP (Agent Client Protocol), and returning structured results.

### orchestration exports

| Name                     | Type      | Description        |
|--------------------------|-----------|--------------------|
| `run_subagent`           | async fn  | Full agent session |
| `load_agent`             | function  | Load from disk     |
| `get_provider_for_model` | function  | Select provider    |
| `AgentNotFoundError`     | exception | Agent file missing |

### run\_subagent

```python
async def run_subagent(
    agent_name: str,
    root_dir: pathlib.Path,
    initial_task: str = "",
    context_files: list[pathlib.Path] | None = None,
    plan_file: pathlib.Path | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
    interactive: bool = False,
    debug: bool = False,
    quiet: bool = False,
    mode: str = "read-write",
    client_ref: list | None = None,
    resume_session_id: str | None = None,
    max_turns: int | None = None,
    budget: float | None = None,
    effort: str | None = None,
    output_format: str | None = None,
) -> SubagentResult: ...
```

Spawns an agent process, performs the ACP handshake, sends the
initial task prompt, and waits for completion. The returned
`SubagentResult` includes the agent's response text and any files
it wrote. Raises `SubagentError` on failure.

### load\_agent

```python
def load_agent(
    agent_name: str,
    root_dir: pathlib.Path,
    provider_name: str | None = None,
) -> tuple[dict[str, str], str]: ...
```

Searches for `<fw_dir>/agents/<provider>/<name>.md` then
`<fw_dir>/agents/<name>.md`. Returns `(metadata_dict, persona)`.
Raises `AgentNotFoundError` when neither path exists.

### orchestration usage

```python
import asyncio
from pathlib import Path
from orchestration.subagent import run_subagent

result = asyncio.run(run_subagent(
    agent_name="vaultspec-researcher",
    root_dir=Path("."),
    initial_task="Research LanceDB hybrid search",
))
print(result.response_text)
```

---

## protocol

The `protocol` package contains typed wrappers for the three
inter-agent communication protocols used by vaultspec.

### ACP types (protocol.acp.types)

ACP (Agent Client Protocol, Zed Industries) is the stdio protocol
used between the orchestrator and each spawned agent process.

| Name             | Type             | Description          |
|------------------|------------------|----------------------|
| `SubagentResult` | frozen dataclass | Session outcome      |
| `SubagentError`  | Exception        | Session failure      |

```python
@dataclass(frozen=True)
class SubagentResult:
    response_text: str
    written_files: list[str]
    session_id: str | None
```

### Provider base (protocol.providers.base)

| Name            | Type           | Description           |
|-----------------|----------------|-----------------------|
| `AgentProvider` | abstract class | Provider process spec |

Concrete implementations live in `protocol.providers.claude`
(`ClaudeProvider`) and `protocol.providers.gemini`
(`GeminiProvider`). Provider selection is automatic based on the
model name prefix (`claude-` or `gemini-`).

---

## subagent\_server

The `subagent_server` module exposes the sub-agent dispatch system
as an MCP (Model Context Protocol) server named `vs-subagent-mcp`.
It is implemented with FastMCP and communicates over stdio.

### Server entry point

Start the server via the CLI:

```text
python .vaultspec/lib/scripts/subagent.py serve
```

Or configure it in `.mcp.json` (already present in the project
root) for automatic connection by compatible MCP clients such as
Claude Code.

### Available tools

| Tool             | Description                       |
|------------------|-----------------------------------|
| `list_agents`    | Return all agent definitions      |
| `dispatch_agent` | Spawn agent with task             |
| `get_task_status`| Poll status of running task       |
| `cancel_task`    | Request cancellation              |
| `get_locks`      | Return held resource locks        |

### dispatch\_agent parameters

| Param   | Type   | Req | Description       |
|---------|--------|-----|-------------------|
| `agent` | string | yes | Agent name        |
| `task`  | string | yes | Task description  |
| `model` | string | no  | Model override    |
| `mode`  | string | no  | `read-write`/`ro` |

### MCP usage

When `vs-subagent-mcp` is connected, call `dispatch_agent`
directly from any MCP-capable client:

```text
dispatch_agent(
  agent="vaultspec-researcher",
  task="Research embedding model options",
)
```

The tool returns a JSON object with `session_id`,
`response_text`, and `written_files`.
