---
tags:
  - "#research"
date: 2026-02-13
related:
  - "[[2026-02-12-rag-implementation-plan]]"
---

# RAG Stack Benchmark Research

Performance baseline and competitive analysis for the vault RAG pipeline:
nomic-embed-text-v1.5 embeddings, LanceDB vector store, hybrid BM25+ANN search
with graph-based re-ranking.

## Our Benchmark Numbers

Measured on Windows 11, NVIDIA GeForce RTX 4080 SUPER (16GB VRAM),
PyTorch 2.10.0+cu130, CUDA 13.0, 214-document vault corpus.

### Embedding Throughput (synthetic short texts)

| Batch Size | Time (s) | Throughput (docs/sec) |
|------------|----------|----------------------|
| 10         | 0.21     | 49                   |
| 50         | 0.05     | 948                  |
| 100        | 0.09     | 1070                 |

Model: nomic-embed-text-v1.5 (137M params, 768-dim vectors).
Throughput improves dramatically with batch size due to GPU parallelism.
First batch is slow due to CUDA kernel warmup (~0.2s).

### Full Index Throughput (real vault documents)

| Corpus Size | Time (s) | Throughput (docs/sec) | Device |
|-------------|----------|----------------------|--------|
| 214 docs    | 6.36     | 33.6                 | CUDA   |

Includes: vault scanning, metadata parsing, embedding (truncated at 8000 chars),
LanceDB upsert. Length-sorted batching minimizes GPU padding waste.

**Optimization impact**: Before truncation + sorting: 200-463s. After: 6.36s (31-73x faster).

### Incremental Index (No-op)

When no documents have changed, incremental indexing completes in **23ms**.
Validates the mtime-based change detection avoids re-embedding.

### Search Latency (20 queries, hybrid BM25+ANN with graph re-ranking)

| Percentile | Latency (ms) |
|------------|-------------|
| p50        | 36.0        |
| p95        | 38.6        |
| p99        | 38.6        |
| mean       | 33.1        |

stdev: 4.5ms. Includes: query embedding, hybrid search, graph re-ranking,
snippet extraction.

### Resource Usage

| Resource           | Value       |
|--------------------|-------------|
| GPU                | RTX 4080 SUPER |
| LanceDB disk       | 4.7 MB      |
| GPU VRAM allocated | 538.8 MB    |
| GPU VRAM reserved  | 15962.0 MB  |
| Model load time    | ~10s        |

## Competitive Comparison

### Vector Store: LanceDB vs Alternatives

**LanceDB** (our choice): Embedded, zero-config, disk-based columnar store built
on Apache Arrow / Lance format. Supports hybrid BM25+ANN search natively.

- Strengths: No server process, sub-millisecond overhead for small corpora,
  built-in full-text search, GPU-accelerated index building (IVF).
- Weaknesses: No built-in replication, limited concurrent write support,
  lance data files can corrupt under concurrent connections.

**FAISS** (Meta): Industry standard for GPU-accelerated vector search.
FAISS v1.10 with NVIDIA cuVS achieves up to 4.7x faster IVF indexing and
8.1x lower search latency compared to classical GPU implementations.
However, FAISS is a library (not a database) -- no persistence, no metadata
filtering, no FTS. Requires custom persistence layer.

**ChromaDB**: Embedded vector DB with zero network latency. Good for
prototyping and small corpora (<100K vectors). Retrieval time is 0.01-0.4%
of end-to-end RAG latency for small datasets.

**Qdrant/Pinecone/Milvus**: Server-based solutions. Overkill for our
embedded use case (213 docs, single-user). Pinecone achieves p95 <23ms,
Milvus p95 <30ms at million-vector scale.

**Verdict**: LanceDB is the right choice for an embedded, single-user vault
with <1K documents. It provides hybrid search without needing a separate
FTS engine and requires zero operational overhead.

### Embedding Model: nomic-embed-text-v1.5 vs Alternatives

**nomic-embed-text-v1.5** (our choice): 137M params, 768-dim vectors.
Strong retrieval quality on MTEB benchmarks. Supports Matryoshka
representation learning (can truncate to 256/512 dims with minimal
quality loss).

- Strengths: High retrieval quality, variable dimensionality, open-source,
  good instruction-following for search vs classification tasks.
- Weaknesses: Larger than MiniLM (137M vs 22M params), slower inference,
  higher VRAM usage (~200MB).

**all-MiniLM-L6-v2**: 22M params, 384-dim vectors. 6x smaller and faster.
Adequate quality for simple keyword-style queries but weaker on semantic
understanding and cross-lingual tasks.

**BGE-small-en-v1.5**: 33M params, 384-dim vectors. Good quality/speed
tradeoff. Faster than nomic but lower quality on complex queries.

**nomic-embed-text-v2-moe** (newer): Mixture-of-experts architecture.
Improved quality but requires more compute.

**Verdict**: nomic-embed-text-v1.5 is well-suited for our vault where
retrieval quality matters more than throughput. With only ~50 docs/sec
needed and GPU available, the inference cost is acceptable. If we needed
to support CPU-only or edge deployment, all-MiniLM-L6-v2 would be the
fallback.

### Search Pipeline: Hybrid vs Vector-Only

Our pipeline uses hybrid BM25+ANN with Reciprocal Rank Fusion (RRF),
plus a graph-based authority boost (score *= 1 + 0.1* in_links).

- Hybrid search improves precision on exact keyword queries (e.g.,
  "DisplayMap", "SetWindowCompositionAttribute") where pure vector
  search would miss lexical matches.
- Graph re-ranking surfaces well-connected documents (architectural
  decisions, master plans) over orphan documents, which aligns with
  how developers navigate documentation.

## Test Suite Optimization Summary

| Metric           | Before  | After   | Improvement |
|------------------|---------|---------|-------------|
| Fast path time   | 20+ min | ~2 min  | ~10x        |
| Docs indexed     | 213     | 13      | 16x fewer   |
| Fixture scope    | module  | session | 8x fewer    |
| Fast tests       | 86      | 74      | -           |
| Slow tests       | 0       | 12      | -           |

The fast path indexes a curated 13-document subset covering all 5 doc_types
(adr, exec, plan, reference, research) and key features (editor-demo,
dispatch, displaymap, main-window). Slow tests requiring the full 213-doc
corpus are marked `@pytest.mark.slow` and excluded from the default run.
