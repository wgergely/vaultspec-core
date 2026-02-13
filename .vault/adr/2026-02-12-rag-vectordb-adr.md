---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #exec #plan #reference #research #rag
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/adr/ location)
# Feature tag (replace vault-api with your feature name, e.g., #editor-demo)
tags:
  - "#adr"
  - "#rag"
# ISO date format (e.g., 2026-02-06)
date: 2026-02-12
# Related documents as quoted wiki-links (e.g., "[[2026-02-04-feature-research]]")
related:
  - "[[2026-02-12-rag-plan]]"
  - "[[2026-02-12-rag-embeddings-adr]]"
  - "[[2026-02-12-rag-retrieval-adr]]"
  - "[[2026-02-08-vault-api-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# rag-vectordb adr: LanceDB as Embedded Vector Store | (**status:** accepted)

## Problem Statement

The `.vault/` vault requires a persistent vector store for semantic search over ADRs, plans, research, and exec documents. The previous Synthetic RAG approach (rejected) used LLM dispatch for both indexing and querying, introducing unacceptable latency, cost, and external service dependency. We need a vector database that runs locally, leverages CUDA GPU acceleration, and fits the embedded CLI model of `docs.py`. CPU is NOT supported -- all RAG operations require a CUDA-enabled GPU.

## Considerations

- **Embedded vs Server**: The `docs.py` CLI is a standalone script with no daemon processes. A server-based database (Milvus, Qdrant, Weaviate) would require Docker or a background service, violating the existing architectural model.
- **GPU Requirement**: Must leverage CUDA for fast index building and ANN search. A CUDA-enabled GPU is required -- CPU is not supported.
- **Hybrid Search**: The vault uses specific identifiers (e.g., "DisplayMap", "BlockMap") that pure vector search misses. Native BM25 + vector hybrid search is essential.
- **Incremental Indexing**: Documents are added and modified over time. The store must support efficient upserts without full re-indexing.
- **Windows 11 + Python 3.13+**: Must install cleanly via pip on the target platform.

Candidates evaluated:

- **LanceDB**: Embedded, Lance columnar format (Arrow-based), native hybrid search via Tantivy, GPU-accelerated IVF-PQ indexes, pip-installable, ~50MB footprint.
- **FAISS**: Low-level index library. Powerful GPU support but no metadata filtering, no persistence abstraction, no hybrid search. Wrong abstraction level.
- **Milvus / Qdrant / Weaviate**: Server-based databases designed for millions-to-billions of vectors. Unnecessary complexity (gRPC, Docker, REST APIs) for an embedded CLI tool with <1000 docs.
- **ChromaDB**: Simpler embedded option but lacks native GPU acceleration and has weaker hybrid search capabilities.
- **pgvector**: Requires PostgreSQL. Incompatible with the embedded CLI model.

## Constraints

- Must be pip-installable as an optional dependency (`pip install .[rag]`).
- Must not require Docker, background services, or system-level database installations.
- Storage directory (`.lance/`) must coexist with `.vault/` at the vault root and be `.gitignore`-friendly.
- Must require a CUDA-enabled GPU. CPU is not supported -- the system fails fast with `GPUNotAvailableError` if no GPU is detected.

## Implementation

LanceDB runs in-process as a Python library. Data persists as Lance files on disk at `{vault_root}/.lance/`.

**Schema:**

```
id: str              # document stem name
path: str            # relative path from vault root
doc_type: str        # adr, plan, exec, research, reference
feature: str         # feature tag (e.g., "vault-api")
date: str            # ISO date from frontmatter
tags: list[str]      # all tags from frontmatter
related: list[str]   # wiki-link targets from frontmatter
title: str           # H1 heading
content: str         # full body text (for BM25)
vector: vector[768]  # embedding from nomic-embed-text-v1.5
```

**GPU Performance (CUDA required):**

| Operation | GPU (CUDA) |
|---|---|
| Index build (IVF-PQ) | Sub-second for <1000 docs |
| ANN search | <5ms |
| BM25 full-text search | CPU (Tantivy -- this component is inherently CPU-based) |
| Hybrid search (BM25 + ANN) | <10ms total |

A CUDA-enabled GPU is required. The system fails fast with `GPUNotAvailableError` at initialization if no GPU is detected. CPU-only operation is NOT supported.

**Disk footprint:** ~10MB for 1000 documents at 768 dimensions.

## Rationale

LanceDB is the only candidate that simultaneously satisfies all constraints: embedded (no server), GPU-accelerated (when available), native hybrid search (BM25 + vector), pip-installable, and Windows-compatible. Its Apache Arrow foundation provides a stable, well-tested data layer. The serverless model is a direct architectural match for the `docs.py` CLI pattern established in [[2026-02-08-vault-api-adr]].

FAISS was rejected because it is an index primitive, not a database -- we would need to build persistence, metadata filtering, and hybrid search ourselves. Server-based databases were rejected because they violate the embedded CLI model and introduce operational complexity disproportionate to the vault's scale.

## Consequences

- **New Dependency**: `lancedb>=0.15.0` added as an optional dependency in the `[rag]` extras group. Core vault tools remain dependency-free.
- **Storage Artifact**: `.lance/` directory at vault root must be added to `.gitignore`.
- **Version Risk**: LanceDB is pre-1.0 (v0.x as of early 2026). The Lance columnar format itself is stable (Arrow-based), and the embedding layer is database-agnostic, so migrating to an alternative store (ChromaDB, flat numpy) is straightforward if needed.
- **GPU Required**: A CUDA-enabled GPU is mandatory for all RAG operations. The system fails fast with `GPUNotAvailableError` if no GPU is available. CPU is not supported.
