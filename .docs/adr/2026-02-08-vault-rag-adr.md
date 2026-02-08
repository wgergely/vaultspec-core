---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #exec #plan #reference #research #vault-rag
# Directory tag (hardcoded - DO NOT CHANGE - based on .docs/adr/ location)
# Feature tag (replace vault-api with your feature name, e.g., #editor-demo)
tags:
  - "#adr"
  - "#vault-rag"
# ISO date format (e.g., 2026-02-06)
date: 2026-02-08
# Related documents as quoted wiki-links (e.g., "[[2026-02-04-feature-research]]")
related:
  - "[[2026-02-08-vault-api-adr]]"
  - "[[2026-02-08-vault-rag-plan]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# vault-rag adr: Semantic Search via Document Summarization | (**status:** proposed)

## Problem Statement

The `.docs/` vault is growing, but finding relevant information depends on manual tag matching or grep. We need a way to "bootstrap" an agent's knowledge of the vault by providing semantic meaning search, but without the overhead and dependency weight of a full vector database like FAISS or HNSW (as seen in the abandoned `leann-mcp` stub).

## Considerations

- **Dependency Minimalism:** Avoid heavy libraries (numpy, torch, faiss) in the core `docs.py` tool.
- **Agent Integration:** The search must be easily consumable by an agent via a CLI or future MCP.
- **Accuracy:** Summaries must capture the intent of ADRs, Plans, and Research documents.
- **Performance:** For a vault of <1000 documents, a pure-Python search on JSON-cached summaries is efficient.

## Constraints

- No external binary dependencies.
- Use existing Gemini CLI capabilities for reasoning/summarization.
- Metadata (tags, date, feature) must be used to boost search relevance.

## Implementation

We will implement a **Synthetic Semantic Search** system:

1. **Indexing (`docs index`)**: For each document, ask Gemini to generate a dense, keyword-rich "Semantic Signature" (e.g., a 50-word summary containing core concepts, technologies, and decisions).
2. **Storage**: Persist these signatures in `.gemini/vault_index.json` along with metadata.
3. **Search (`docs search`)**:
    - **Step 1**: Filter documents by tags/date if provided.
    - **Step 2**: Use Gemini to rank the "Semantic Signatures" of the remaining documents against the user's query.
    - **Optimization**: For very large vaults, use a simple TF-IDF or Jaccard similarity in Python as a pre-filter before LLM ranking.

## Rationale

This approach bypasses the need for local embedding models while still providing "meaning-aware" search. It leverages the existing LLM's reasoning power to bridge the gap between a user's intent and the document content.

## Consequences

- **Latency**: Indexing is slow (calls LLM per doc), but searching is fast (calls LLM once for ranking).
- **Cost**: Uses LLM tokens for indexing.
- **Portability**: Highly portable as it only requires Python and the Gemini CLI.
- **Future-Proof**: Can be easily upgraded to real vector embeddings if the environment allows.
