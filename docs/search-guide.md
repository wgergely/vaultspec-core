# Search Guide

vaultspec includes a semantic search engine over your `.vault/` documents, powered by GPU-accelerated embeddings and hybrid retrieval.

## Basic Search

```bash
python .vaultspec/lib/scripts/docs.py search "protocol integration patterns"
```

Returns the top 5 most relevant documents by default. Use `--limit` to change:

```bash
python .vaultspec/lib/scripts/docs.py search "agent dispatch" --limit 10
```

Use `--json` for machine-readable output:

```bash
python .vaultspec/lib/scripts/docs.py search "embedding model" --json
```

## Filter Tokens

Add structured filters to narrow results. Filters are extracted from the query and applied as SQL WHERE clauses on document metadata.

| Filter | Column | Example |
|--------|--------|---------|
| `type:<value>` | `doc_type` | `type:adr` -- only ADRs |
| `feature:<value>` | `feature` | `feature:rag` -- only RAG-related docs |
| `date:<value>` | `date` | `date:2026-02` -- docs from February 2026 |
| `tag:<value>` | tags | `tag:#protocol` -- docs tagged with #protocol |

### Examples

```bash
# Find ADRs about search
python .vaultspec/lib/scripts/docs.py search "type:adr search implementation"

# Find all RAG-related research
python .vaultspec/lib/scripts/docs.py search "type:research feature:rag embeddings"

# Find recent execution records
python .vaultspec/lib/scripts/docs.py search "type:exec date:2026-02 results"

# Combine multiple filters
python .vaultspec/lib/scripts/docs.py search "type:plan feature:protocol integration steps"
```

The filter tokens are removed from the query text before semantic matching, so the natural language portion searches independently of the metadata filters.

## How Search Works

Search uses a three-stage hybrid retrieval pipeline:

### Stage 1: BM25 (Keyword Matching)

Traditional keyword search using term frequency-inverse document frequency. Good for exact term matches and specific identifiers.

### Stage 2: ANN (Approximate Nearest Neighbor)

Vector similarity search using document embeddings. The query is embedded with the same model used for indexing, then compared against all document vectors using cosine similarity. Good for semantic meaning even when exact terms differ.

### Stage 3: RRF (Reciprocal Rank Fusion)

The results from BM25 and ANN are combined using Reciprocal Rank Fusion:

```
score(doc) = sum(1 / (k + rank_i)) for each retriever i
```

This produces a final ranking that balances keyword precision with semantic recall. Documents that rank highly in both retrievers get the strongest boost.

## GPU Requirements

The search engine requires an NVIDIA GPU with CUDA support:

- **CUDA**: 13.0+
- **VRAM**: ~539MB allocated for the embedding model
- **Model**: `nomic-ai/nomic-embed-text-v1.5` (768-dimensional embeddings)

vaultspec does not support CPU-only operation. If no GPU is available, the system raises `GPUNotAvailableError`.

## Building the Index

Before searching, you must build the vector index:

```bash
# Incremental index (default) -- only processes new/changed files
python .vaultspec/lib/scripts/docs.py index

# Full re-index -- reprocesses all documents
python .vaultspec/lib/scripts/docs.py index --full
```

### How Incremental Indexing Works

The indexer uses mtime-based change detection:

1. On first run, all `.vault/` markdown files are indexed and their modification times recorded in `.lance/index_meta.json`
2. On subsequent runs, only files with newer mtimes are re-embedded and upserted
3. Documents are sorted by length before batching to minimize GPU padding overhead
4. Long documents are truncated to 8000 characters (`VAULTSPEC_MAX_EMBED_CHARS`) before embedding

### Performance

On an RTX 4080 SUPER (16GB VRAM):

- Full index of 214 documents: ~6.4 seconds (33.6 docs/sec)
- Search latency: p50=36ms, p95=38.6ms
- VRAM: 538.8MB allocated

## Configuration

Search behavior can be tuned with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VAULTSPEC_EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | Embedding model |
| `VAULTSPEC_EMBEDDING_BATCH_SIZE` | `64` | GPU batch size for embedding |
| `VAULTSPEC_MAX_EMBED_CHARS` | `8000` | Max characters per document |
| `VAULTSPEC_GRAPH_TTL_SECONDS` | `300.0` | Graph cache TTL for re-ranking |
| `VAULTSPEC_LANCE_DIR` | `.lance` | Vector store directory |

See [Configuration](configuration.md) for the full reference.
