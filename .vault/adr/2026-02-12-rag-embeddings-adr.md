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
  - "[[2026-02-12-rag-vectordb-adr]]"
  - "[[2026-02-12-rag-retrieval-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# rag-embeddings adr: nomic-embed-text-v1.5 as Embedding Model | (**status:** accepted)

## Problem Statement

The vault semantic search system requires a local embedding model to convert documents and queries into dense vector representations. The model must handle technical documentation well (ADRs, architecture decisions, implementation plans) and run locally on a CUDA-enabled GPU. CPU is NOT supported -- all operations require a CUDA GPU. If no GPU is available, the system fails fast with `GPUNotAvailableError`. The model must balance embedding quality, VRAM consumption, and inference throughput.

## Considerations

- **Domain Fit**: The vault contains technical prose about software architecture, not source code. Models trained on diverse technical documentation outperform code-specific models (CodeBERT, StarEncoder) for this content.
- **MTEB Retrieval Performance**: The model must rank highly on MTEB retrieval benchmarks, particularly on technical/scientific document subsets.
- **GPU Requirement**: Must leverage CUDA for all embedding operations. CPU is not supported -- the system requires a CUDA-enabled GPU and fails fast with `GPUNotAvailableError` if none is detected.
- **Matryoshka Embeddings**: Variable-dimension output allows trading precision for speed at query time without re-indexing.
- **Task Prefixes**: Models supporting `search_document:` and `search_query:` prefixes improve retrieval accuracy by distinguishing document encoding from query encoding.

Candidates evaluated:

- **nomic-embed-text-v1.5** (768-dim): Strong MTEB retrieval scores on technical content, Matryoshka support (768/512/256/128), task prefixes, ~550MB, ~1.5GB VRAM at fp16. Production-proven, actively maintained.
- **all-MiniLM-L6-v2** (384-dim): Fast and tiny (~80MB) but 384-dim embeddings produce insufficient quality for nuanced technical document retrieval. Cannot distinguish between similar ADRs addressing different concerns.
- **e5-large-v2** (1024-dim): Competent but older architecture, superseded by newer models on MTEB benchmarks.
- **e5-mistral-7b-instruct** (4096-dim): 7B parameters, ~14GB VRAM. Absurd overkill for embedding <1000 short markdown documents.
- **BGE-M3**: Strong multilingual model, but the vault is English-only technical documentation. Nomic is more focused and efficient for this domain.
- **OpenAI text-embedding-3**: Cloud-only. Contradicts the local-first requirement.

## Constraints

- Must run via `sentence-transformers` library (standard ecosystem, well-tested).
- Must fit in <2GB VRAM at fp16 to leave headroom for other GPU workloads.
- Must encode the full vault (<1000 docs) in under 60 seconds on GPU.
- Must be pip-installable as part of the `[rag]` optional dependency group.
- Must support Python 3.13+ (requires PyTorch >= 2.5.0 with CUDA 12.x).

## Implementation

The embedding model is loaded via `sentence-transformers` and wrapped in a thin abstraction layer at `vault/embeddings.py`.

**Encoding Strategy:**

- **Documents**: Prepend `search_document:` prefix. Encode full document body (title + content). No chunking -- vault documents are short, single-topic markdown files (typically 200-2000 words) that fit within the model's 8192-token context window.
- **Queries**: Prepend `search_query:` prefix. Encode the user's natural language query as-is.
- **Dimension**: Use 768-dim (full precision) for storage. Matryoshka truncation to 256-dim available as a future optimization lever if index size becomes a concern.

**GPU Performance (CUDA required):**

| Operation | GPU (CUDA) |
|---|---|
| Model loading | ~3s, ~1.5GB VRAM |
| Batch embed (1000 docs) | ~20-30s |
| Single query embed | <10ms |
| Incremental re-embed (10 docs) | <1s |

A CUDA-enabled GPU is required. If no GPU is detected, the system raises `GPUNotAvailableError` at initialization. CPU is NOT supported -- there is no fallback, no degraded mode.

**Model Caching:**

The model is downloaded once from HuggingFace Hub and cached locally in the standard `~/.cache/huggingface/` directory. Subsequent loads are from local disk.

## Rationale

nomic-embed-text-v1.5 provides the best balance of retrieval quality, model size, and feature set for this use case. Its Matryoshka embedding support provides a free scaling lever. Task prefixes measurably improve retrieval accuracy on technical documentation. The 768-dim output at ~1.5GB VRAM is a sweet spot -- high quality without the VRAM demands of larger models.

Code-specific embedding models were rejected because the vault content is technical prose about code (architecture decisions, plans, research), not source code itself. A general-purpose document embedding model trained on diverse technical content is the correct fit.

## Consequences

- **New Dependencies**: `torch>=2.5.0` and `sentence-transformers>=3.0.0` added as optional dependencies. These are heavy (~2GB installed with CUDA) but isolated to the `[rag]` extras group.
- **PyTorch on Windows**: PyTorch CUDA on Windows 11 requires explicit index URL targeting (`pip install torch --index-url https://download.pytorch.org/whl/cu124`). This must be documented in the install instructions.
- **First-Run Latency**: Initial model download is ~550MB. Subsequent loads from cache are fast (~3-5s).
- **Embedding Lock-in**: Changing the embedding model later requires full re-indexing of the vault. This is a low-cost operation (<60s on GPU) but must be considered when evaluating future model upgrades.
- **GPU Requirement**: A CUDA-enabled GPU is mandatory. The system fails fast with `GPUNotAvailableError` if no GPU is available. CPU is not supported.
