---
tags:
  - "#adr"
  - "#rag"
date: "2026-02-12"
related:
  - "[[2026-02-12-rag-plan]]"
  - "[[2026-02-12-rag-vectordb-adr]]"
  - "[[2026-02-12-rag-embeddings-adr]]"
  - "[[2026-02-08-vault-api-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# rag-retrieval adr: Hybrid Search with Graph-Aware Re-Ranking | (**status:** accepted)

## Problem Statement

The vault semantic search system needs a retrieval strategy that combines keyword precision with semantic understanding. Pure vector search misses exact term matches critical in technical documentation (identifiers like "DisplayMap", "BlockMap", "tree-sitter"). Pure keyword search misses conceptual relationships ("layout engine" should find "DisplayMap" docs). The retrieval pattern must also leverage the vault's existing structure -- wiki-links between documents, feature tags, and document type hierarchy -- to boost authoritative and contextually relevant results.

## Considerations

- **Hybrid Search**: Combining BM25 (sparse) and ANN vector (dense) retrieval captures both exact terminology and semantic similarity. LanceDB supports this natively via Tantivy full-text indexing alongside vector ANN.
- **Score Fusion**: Reciprocal Rank Fusion (RRF) is simple, parameter-free, and consistently outperforms learned score combinations at small scale. No tuning required.
- **Graph Structure**: The vault already maintains a link graph via wiki-links (`[[doc-name]]`) and the existing `VaultGraph` API (from [[2026-02-08-vault-api-adr]]). Documents with high in-link counts are more authoritative. Link neighborhood overlap signals topical relevance.
- **Metadata Filtering**: YAML frontmatter provides structured metadata (doc_type, feature, date, tags) that can be used for hard pre-filtering before vector search, reducing the search space and improving precision.
- **No External Framework**: LlamaIndex, LangChain, and Haystack were evaluated but rejected. They introduce hundreds of transitive dependencies and abstraction layers for a problem solvable in ~400 lines of focused Python. The vault's existing modular API provides all the building blocks needed.

Patterns evaluated:

- **Hybrid BM25 + ANN with RRF** (selected): Simple, effective, natively supported by LanceDB. Combines keyword precision with semantic recall.
- **Pure vector search**: Misses exact keyword matches critical for technical identifiers. Rejected.
- **LLM-based re-ranking (cross-encoder)**: Adds latency and GPU memory for marginal gains at <1000 docs. Deferred as a future optimization for 10K+ doc scale.
- **Microsoft GraphRAG (LLM-extracted knowledge graph)**: The vault already has an explicit graph via wiki-links. Building a parallel LLM-extracted graph is redundant and expensive. Rejected.
- **Multi-hop agentic RAG**: Document relationships are already explicit via wiki-links and `related:` frontmatter. Multi-hop adds latency without clear benefit at this scale. Deferred.

## Constraints

- Must complete end-to-end search (filter + hybrid search + re-rank) in under 100ms on GPU. CPU is not supported.
- Must not introduce dependencies beyond those already required by LanceDB and sentence-transformers.
- Must leverage the existing `VaultGraph` API for graph-aware boosting without duplicating graph logic.
- Must support structured query syntax for metadata filtering alongside natural language queries.

## Implementation

The retrieval pipeline has three stages:

### Stage 1: Metadata Pre-Filtering

Before any vector or text search, apply hard filters from structured metadata extracted from YAML frontmatter. These map directly to LanceDB column predicates (predicate pushdown on Lance format).

Supported filters:

- `type:adr` -- filter by document type
- `feature:vault-api` -- filter by feature tag
- `date:2026-02` -- filter by date prefix
- `tag:#research` -- filter by any tag

Example query: `type:adr feature:editor-demo layout engine` extracts filters `doc_type=adr, feature=editor-demo` and searches for `layout engine` in the remaining documents.

### Stage 2: Hybrid Search (BM25 + ANN)

Execute BM25 full-text search and ANN vector search in parallel via LanceDB's native hybrid search API:

- **BM25**: Searches the `content` column via Tantivy full-text index. Catches exact terminology matches.
- **ANN**: Searches the `vector` column via IVF-PQ index using the query embedding from nomic-embed-text-v1.5 (see [[2026-02-12-rag-embeddings-adr]]).
- **Fusion**: Combine results using Reciprocal Rank Fusion (RRF): `score = sum(1 / (k + rank_i))` where `k=60` (standard constant). RRF is parameter-free and robust.

### Stage 3: Graph-Aware Re-Ranking

Apply score boosts using the existing `VaultGraph` API:

- **Authority Boost**: Documents with high in-link counts (from `VaultGraph.get_hotspots()`) receive a score multiplier. Heavily referenced documents are more likely authoritative.
- **Neighborhood Boost**: If the query context includes a feature tag, documents whose wiki-link neighborhood overlaps with other documents of the same feature receive a boost. This surfaces related documents that the vector search alone might rank lower.
- **Recency Boost** (optional): For time-sensitive queries, more recent documents receive a mild boost via their `date` field.

The re-ranking uses only the existing graph API -- no new graph construction or LLM calls.

**GPU Performance (CUDA required):**

| Stage | Performance |
|---|---|
| Metadata pre-filter | <1ms (LanceDB predicate, CPU-side) |
| Query embedding | <10ms (CUDA) |
| BM25 search | <5ms (Tantivy, CPU-side) |
| ANN vector search | <5ms (CUDA) |
| Graph re-ranking | <1ms (in-memory graph, CPU-side) |
| **Total pipeline** | **<20ms** |

A CUDA-enabled GPU is required. The system fails fast with `GPUNotAvailableError` at initialization if no GPU is detected. Some pipeline stages (BM25 search, metadata filtering, graph re-ranking) are inherently CPU operations, but the embedding model and ANN search require CUDA. CPU-only operation is NOT supported.

## Rationale

Hybrid BM25 + ANN search is the minimum effective retrieval pattern for technical documentation. Pure vector search fails on exact identifiers; pure keyword search fails on semantic concepts. RRF fusion is simpler and more robust than learned score combination at this scale.

Graph-aware re-ranking is a unique advantage of this vault's architecture. The existing wiki-link graph and feature tag system provide structural signals that complement vector similarity. This is effectively "free" -- the `VaultGraph` API exists, and the re-ranking is a lightweight score adjustment, not a separate retrieval pass.

External orchestration frameworks (LlamaIndex, LangChain) were rejected because the entire retrieval pipeline is ~120 lines of Python. The frameworks would introduce dependency bloat and abstraction overhead for no architectural benefit at this scale. The vault's existing modular APIs (scanner, parser, graph, verification) provide a cleaner foundation than a generic framework.

## Consequences

- **No New Dependencies**: The retrieval pattern is implemented in pure Python using LanceDB's built-in hybrid search and the existing `VaultGraph`. No additional libraries required beyond those specified in [[2026-02-12-rag-vectordb-adr]] and [[2026-02-12-rag-embeddings-adr]].
- **Query Syntax**: Users must learn a simple filter syntax (`type:`, `feature:`, `date:`, `tag:`) for metadata filtering. Natural language queries work without filters but may be less precise.
- **Graph Dependency**: Re-ranking quality depends on the wiki-link graph being well-maintained. Orphaned documents (no incoming or outgoing links) receive no graph boost. This incentivizes proper wiki-linking practices.
- **Scale Ceiling**: The three-stage pipeline is optimized for <10K documents. Beyond that, consider adding a cross-encoder re-ranking stage (Stage 3.5) between hybrid search and graph re-ranking. This is explicitly deferred, not designed for now.
- **MCP Integration Path**: The search API (`search_vault(query, filters) -> list[SearchResult]`) maps directly to an MCP tool definition. No architectural changes needed for Phase 4 MCP integration.
