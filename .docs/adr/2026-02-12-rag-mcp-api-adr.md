---
tags:
  - "#adr"
  - "#rag"
date: "2026-02-12"
related:
  - "[[2026-02-11-rag-retrieval-adr]]"
  - "[[2026-02-11-rag-vectordb-adr]]"
  - "[[2026-02-11-rag-embeddings-adr]]"
  - "[[2026-02-11-rag-plan]]"
---

# RAG MCP API Design

## Problem

The RAG system has 4 internal modules (embeddings, store, indexer, search) but no
unified public API. Consumers must manually wire up 3-4 classes with specific
initialization sequences. The `__init__.py` is empty. There is no way to retrieve a
single document by ID, list available documents, or discover the vault schema.

More importantly, the vault is designed to be consumed by LLMs via the Model Context
Protocol (MCP). The API must be designed as a future MCP server surface -- meaning tool
schemas, return shapes, and progressive disclosure patterns must be optimized for LLM
tool selection and context-window efficiency.

## Research Findings

### MCP Protocol Constraints

- **Tools** = model-driven function calls (LLM decides when to invoke). Best for
  dynamic operations like search, where the LLM formulates a query.
- **Resources** = application-driven, URI-addressable, read-only data. Best for
  known-document access where the client preloads context.
- **Resource templates** (e.g., `vault://docs/{doc_id}`) bridge the gap between
  static resources and dynamic tools.

### LLM Tool Selection Research

- **5-7 tools is the practical upper limit** for consistent accuracy. Beyond that,
  selection errors increase exponentially. (Benchmark: 50+ tools = 60% success;
  5-7 tools = 92% success.)
- **Tool descriptions are THE routing mechanism.** Rich, action-oriented descriptions
  that say WHEN to use the tool (not just WHAT it does) improve selection by 15-20%.
- **Fewer, more versatile tools beat many specialized tools.** A single
  `search(query, type?)` is better than `search_adrs()`, `search_plans()`, etc.
- **Optional parameters with defaults** outperform required parameters. Parameter
  hallucination increases with parameter count.
- **Progressive disclosure is critical:** search returns lightweight summaries (title,
  type, snippet); full content requires a follow-up `get` call. This preserves context
  window budget.

### Anti-Patterns to Avoid

- Ambiguous tool names causing wrong selection (e.g., `get_status` vs `fetch_status`)
- Too many required parameters
- Mixing narrative text with structured JSON in returns
- Generic descriptions like "query a database" with no content-specific guidance
- Frontloading all tool definitions (causes "context rot")

## Decision

### Core Tool Set: 6 MCP Tools

Constrained to the 5-7 tool sweet spot. Each tool has a clear, non-overlapping purpose. Includes an `index` tool because LLMs are the primary producers of vault content and must be able to trigger index rebuilds after writing documents.

#### Tool 1: `vault_search`

Primary discovery tool. Semantic search with optional structured filters.

```json
{
  "name": "vault_search",
  "description": "Search the project documentation vault for architecture decisions (ADRs), implementation plans, execution records, research notes, and reference docs. Use this when you need to find information about project features, technical decisions, or implementation details. Returns ranked results with relevance scores and content snippets. Supports optional filters by document type and feature tag.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language search query describing what you're looking for. Example: 'vector database selection criteria'"
      },
      "doc_type": {
        "type": "string",
        "enum": ["adr", "plan", "exec", "research", "reference"],
        "description": "Filter by document type. 'adr' = architecture decisions, 'plan' = implementation plans, 'exec' = execution records."
      },
      "feature": {
        "type": "string",
        "description": "Filter by feature tag (kebab-case). Example: 'rag', 'vault-api'"
      },
      "limit": {
        "type": "integer",
        "default": 5,
        "description": "Maximum number of results to return (1-20)."
      }
    },
    "required": ["query"]
  }
}
```

**Returns:** Array of `{ id, title, doc_type, feature, date, score, snippet }`

**Maps to:** `VaultSearcher.search()` with `parse_query()` filter extraction.

**Design rationale:** Filters are explicit parameters (not inline `type:adr` syntax)
because structured parameters give LLMs type safety and enum validation. The inline
filter syntax remains supported internally but the MCP surface uses proper schema.

#### Tool 2: `vault_get`

Retrieve full document content after discovery via search. The "read" step in
search-then-read progressive disclosure.

```json
{
  "name": "vault_get",
  "description": "Retrieve the full content of a specific vault document by its ID. Use this after vault_search to read the complete text of a relevant result. Returns the document's metadata, full markdown content, and relationship links.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "doc_id": {
        "type": "string",
        "description": "Document ID (the stem name returned by vault_search). Example: '2026-02-11-rag-retrieval-adr'"
      }
    },
    "required": ["doc_id"]
  }
}
```

**Returns:** `{ id, path, title, doc_type, feature, date, tags[], related[], content }`

**Maps to:** New `VaultStore.get_by_id()` method (falls back to file read if not indexed).

**Design rationale:** Separate from search to enable progressive disclosure. Search
returns snippets (compact, preserves context budget); get returns full content (expensive
but targeted). LLMs learn this two-step pattern quickly.

#### Tool 3: `vault_list`

Browse available documents with optional filters. For questions like "what ADRs exist?"
or "what docs cover the rag feature?"

```json
{
  "name": "vault_list",
  "description": "List available documents in the vault with optional filtering by type or feature. Use this to browse what documentation exists, discover document types, or find all docs for a specific feature. Does not require the search index -- works directly from the vault filesystem.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "doc_type": {
        "type": "string",
        "enum": ["adr", "plan", "exec", "research", "reference"],
        "description": "Filter by document type."
      },
      "feature": {
        "type": "string",
        "description": "Filter by feature tag (kebab-case)."
      }
    },
    "required": []
  }
}
```

**Returns:** Array of `{ id, path, title, doc_type, feature, date, tags[] }`

**Maps to:** `scan_vault()` + `parse_vault_metadata()` + optional filtering. Zero RAG
dependencies (Tier 1).

**Design rationale:** This is the "browse the filesystem" tool. Critical for schema
discovery ("what document types exist?") and targeted enumeration. Works even when the
RAG index is not built. Vault is small (<1000 docs), so listing all is viable.

#### Tool 4: `vault_related`

Graph-aware relationship traversal. Find documents linked to a given document.

```json
{
  "name": "vault_related",
  "description": "Find documents related to a specific vault document via wiki-links and cross-references. Use this to explore decision chains (ADR -> Plan -> Exec), understand context around a document, or discover related architecture decisions. Returns both incoming links (docs that reference this one) and outgoing links (docs this one references).",
  "inputSchema": {
    "type": "object",
    "properties": {
      "doc_id": {
        "type": "string",
        "description": "Document ID to find relationships for."
      }
    },
    "required": ["doc_id"]
  }
}
```

**Returns:** `{ doc_id, outgoing: [{ id, title, doc_type }], incoming: [{ id, title, doc_type }] }`

**Maps to:** `VaultGraph` with node `out_links` and `in_links`. Zero RAG dependencies.

**Design rationale:** The vault's wiki-link graph is a unique asset. LLMs can traverse
decision chains (ADR -> Plan -> Exec) to understand full context. This is the graph
equivalent of "see also" and is critical for comprehensive answers.

#### Tool 5: `vault_status`

Health check and schema discovery. Lightweight, no heavy dependencies.

```json
{
  "name": "vault_status",
  "description": "Get vault status including document counts by type, available features, search index health, and device info. Use this to understand what's available before searching, or to diagnose why search returns no results.",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

**Returns:**

```json
{
  "total_docs": 6,
  "types": { "adr": 4, "plan": 2, "exec": 0, "research": 0, "reference": 0 },
  "features": ["rag", "vault-api"],
  "index": { "exists": true, "indexed_count": 6, "device": "cuda", "gpu_name": "RTX 4090" }
}
```

**Maps to:** `get_vault_metrics()` + `list_features()` + `VaultStore.count()` +
`get_device_info()`.

**Design rationale:** Combines schema discovery (types, features) with health check
(index status) in one lightweight call. Helps LLMs understand the vault landscape before
querying. The `index` field gracefully degrades if RAG deps are missing.

#### Tool 6: `vault_index`

Trigger index rebuilds after writing vault documents. Critical for LLM-driven workflows
where the LLM is the producer of vault content (ADRs, plans, exec records) and needs
the search index to reflect newly written documents.

```json
{
  "name": "vault_index",
  "description": "Rebuild the vault search index after adding or modifying documents. Use this after writing new ADRs, plans, or other vault documents to ensure they appear in search results. Supports full re-index or incremental update (default). Returns indexing statistics including document counts and timing. Requires a CUDA-enabled GPU.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "full": {
        "type": "boolean",
        "default": false,
        "description": "Force a full re-index instead of incremental. Use after bulk changes or if incremental results seem stale."
      }
    },
    "required": []
  }
}
```

**Returns:** `{ total, added, updated, removed, duration_ms, device }`

**Maps to:** `rag.api.index(root_dir, full=False)` which wraps `VaultIndexer.incremental_index()` or `VaultIndexer.full_index()`.

**Design rationale:** LLMs are the primary producers of vault content. After writing a
new ADR or plan, the LLM needs to trigger an index rebuild so subsequent `vault_search`
calls return the newly written document. Without this tool, the LLM would need to shell
out to the CLI, which breaks the MCP tool-calling workflow. This is a critical design
requirement, not optional.

### MCP Resources (2)

Resources provide direct URI-based access for application-driven context loading.

#### Resource: `vault://docs/{doc_id}`

Direct document access by ID. Applications can preload relevant docs into context.

```json
{
  "uri": "vault://docs/{doc_id}",
  "name": "Vault Document",
  "description": "Full content of a vault document by ID.",
  "mimeType": "text/markdown"
}
```

#### Resource: `vault://schema`

Vault schema summary. Applications load this once to understand the vault structure.

```json
{
  "uri": "vault://schema",
  "name": "Vault Schema",
  "description": "Document types, features, naming conventions, and metadata fields."
}
```

### Python API (`rag/api.py`)

The Python module that backs both the MCP server and the CLI. All functions accept a
`root_dir: pathlib.Path` and handle internal wiring.

```python
# Tier 1: Zero-dependency functions (no RAG deps needed)
def list_documents(root_dir, *, doc_type=None, feature=None) -> list[dict]
def get_document(root_dir, doc_id) -> dict | None
def get_related(root_dir, doc_id) -> dict
def get_status(root_dir) -> dict

# Tier 2: RAG-dependent functions
def index(root_dir, *, full=False) -> IndexResult
def search(root_dir, query, *, doc_type=None, feature=None, limit=5) -> list[SearchResult]

# Engine management (singleton, lazy init)
def get_engine(root_dir) -> VaultRAG
```

**Tier separation** is important: Tier 1 functions work with just the vault filesystem
and standard library. Tier 2 requires torch, sentence-transformers, lancedb. The MCP
server gracefully degrades -- if RAG deps are missing, `vault_search` returns an error
message while `vault_list`, `vault_get`, `vault_related`, and `vault_status` continue
working.

### Dependency Tiers

| Tier | Tools | Dependencies |
|------|-------|-------------|
| 1 (Core) | vault_list, vault_get, vault_related, vault_status | stdlib + vault/graph modules |
| 2 (RAG) | vault_search, vault_index | + torch, sentence-transformers, lancedb (CUDA GPU required) |

### Example LLM Interaction

```
User: "Where can I find information about how we chose our vector database?"

LLM thinks: This is about a technical decision -> likely an ADR about vector databases.

Step 1 - Search:
  vault_search(query="vector database selection", doc_type="adr")
  -> [{ id: "2026-02-11-rag-vectordb-adr", title: "RAG Vector Database Selection",
        score: 0.89, snippet: "Evaluates LanceDB, ChromaDB, and Qdrant for..." }]

Step 2 - Read:
  vault_get(doc_id="2026-02-11-rag-vectordb-adr")
  -> { content: "# RAG Vector Database Selection\n\n## Problem\n..." }

Step 3 - Explore related:
  vault_related(doc_id="2026-02-11-rag-vectordb-adr")
  -> { outgoing: [{ id: "2026-02-11-rag-plan", title: "RAG Master Plan" }],
       incoming: [{ id: "2026-02-12-rag-mcp-api-adr", title: "RAG MCP API Design" }] }

LLM: "The vector database decision is documented in the RAG Vector Database Selection
ADR. It evaluates LanceDB, ChromaDB, and Qdrant, ultimately selecting LanceDB for..."
```

## Constraints

- Tool count must stay at 6 (max 7) to maintain LLM selection accuracy
- All returns must be structured JSON with consistent field names
- Search results are snippets only; full content requires explicit `vault_get`
- Tier 1 tools must work without RAG dependencies installed
- LLMs MUST be able to manage the index via MCP calls (not just CLI), since LLMs are the primary producers of vault content and need to trigger index rebuilds after writing documents

## Implementation Plan

### Changes Required

| File | Change |
|------|--------|
| `.rules/lib/src/rag/api.py` | NEW - Python API facade (~150 lines) |
| `.rules/lib/src/rag/store.py` | Add `get_by_id()` method |
| `.rules/scripts/docs.py` | Simplify to use `rag.api` functions |
| `tests/test_rag_integration.py` | Add `TestRAGAPI` class (~10 tests) |

### Future: MCP Server

The Python API maps 1:1 to MCP tool definitions. The MCP server implementation
(Phase 4 per the RAG master plan) is a thin adapter:

```python
# Future: mcp_server.py
@server.tool("vault_search")
async def handle_search(query, doc_type=None, feature=None, limit=5):
    return rag.api.search(root_dir, query, doc_type=doc_type, feature=feature, limit=limit)
```

## Consequences

- LLMs get a clean 6-tool surface optimized for the search-then-read pattern, plus index management
- Progressive disclosure preserves context window (snippets first, full content on demand)
- Tier separation means vault browsing works even without RAG index being built
- The Python API is immediately useful for CLI and scripting before MCP server exists
- Tool descriptions are content-specific (mention ADRs, plans, features) not generic
