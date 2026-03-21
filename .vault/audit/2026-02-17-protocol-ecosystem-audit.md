---
tags:
  - '#audit'
  - '#protocol'
date: '2026-02-17'
related:
  - '[[2026-02-17-audit-summary-audit]]'
---

# Protocol Ecosystem & Feature Gap Analysis

**Date**: 2026-02-17
**Author**: ProductResearch-B (Protocol Ecosystem Analyst)
**Cross-reference**: [2026-02-17-competitive-landscape-audit.md](2026-02-17-competitive-landscape-audit.md)

______________________________________________________________________

## Executive Summary

Vaultspec's three-protocol stack (MCP + ACP + A2A) is architecturally sound and ahead of most competitors in protocol breadth. However, the ecosystem has evolved rapidly since vaultspec's initial implementation. This report maps the current protocol landscape, identifies feature gaps, and recommends specific integrations that would strengthen vaultspec's position.

**Key findings:**

- ACP has expanded from Zed-only to JetBrains, Neovim, Emacs, and Kiro, with a live registry
- A2A has moved to Linux Foundation governance with v0.3 (gRPC support) and 100+ enterprise partners
- AAIF (Agentic AI Foundation) now stewards MCP, AGENTS.md, and Goose under Linux Foundation
- Spec-Driven Development (SDD) has gone mainstream with dedicated tools (Kiro, GitHub Spec-Kit)
- RAG has evolved toward agentic and graph-based architectures
- Embedding models have leaped forward (Qwen3-Embedding family, variable dimensions, matryoshka)

______________________________________________________________________

## 1. Protocol Ecosystem Maps

### 1.1 MCP (Model Context Protocol) — Industry Standard

**Status**: De facto universal standard. Under AAIF/Linux Foundation governance.

| Dimension                  | State of the Art (Feb 2026)        | vaultspec Status    |
| -------------------------- | ---------------------------------- | ------------------- |
| SDK version                | Python SDK latest                  | v1.26.0 (current)   |
| Server count               | 1000+ community-built              | 1 (vs-subagent-mcp) |
| OAuth Resource Server auth | Spec-mandated since 2025           | Not implemented     |
| MCP Registry               | Preview (GA planned 2026)          | Not integrated      |
| .well-known discovery      | Supported in spec                  | Not implemented     |
| MCP Gateway pattern        | Enterprise pattern (Kong, MintMCP) | Not implemented     |
| OWASP MCP Top 10           | Published and maintained           | Not addressed       |

**Ecosystem adoption:**

1. MCP04: Software Supply Chain Attacks
1. MCP05: Command Injection & Execution
1. MCP06: Prompt Injection via Contextual Payloads
1. MCP07: Insufficient Authentication & Authorization
1. MCP08: Lack of Audit & Telemetry
1. MCP09: Shadow MCP Servers
1. MCP10: Context Injection & Over-Sharing

**Notable vulnerabilities disclosed (Jan 2026):** CVE-2025-68143/44/45 in Anthropic's own Git MCP server — RCE via prompt injection. BlueRock found 36.7% of 7,000+ MCP servers exposed to SSRF. This underscores that MCP security is not hypothetical.

### 1.2 ACP (Agent Client Protocol) — Editor-Agent Standard

**Status**: Multi-editor standard. Active development by Zed Industries.

| Dimension       | State of the Art (Feb 2026)         | vaultspec Status                   |
| --------------- | ----------------------------------- | ---------------------------------- |
| SDK version     | v0.8.1                              | v0.8.0 (one minor behind)          |
| Editor support  | Zed, JetBrains, Neovim, Emacs, Kiro | Claude Code/Gemini CLI integration |
| ACP Registry    | Live (joint Zed + JetBrains)        | Not registered                     |
| Agent discovery | Registry-based                      | Manual configuration               |

| Registered agents | Claude Code, Codex CLI, Copilot CLI, Gemini CLI, OpenCode, Auggie | Not listed |

Key development --- ACP Registry (Jan 2026):

- Joint launch by Zed and JetBrains
- Developers register once, available in all ACP-compatible editors
- JetBrains Koog agent framework now has native ACP support
- Amazon Kiro adopted ACP for IDE integration

**Implications for vaultspec:** ACP is no longer a niche Zed-only protocol. It is becoming the universal agent-to-editor interoperability layer. Vaultspec's ACP bridge (claude_bridge.py, client.py) positions it to participate, but it is not registered in the ACP Registry.

### 1.3 A2A (Agent-to-Agent Protocol) — Agent Network Standard

**Status**: Linux Foundation project. v0.3 released with gRPC support.

| Dimension          | State of the Art (Feb 2026)     | vaultspec Status                          |
| ------------------ | ------------------------------- | ----------------------------------------- |
| SDK version        | v0.3.x (a2a-sdk)                | v0.3.22 installed, production code exists |
| Agent Card         | .well-known/agent.json standard | agent_card.py implements generation       |
| Discovery          | HTTP-based .well-known          | discovery.py implemented                  |
| Executors          | Multiple implementations exist  | claude_executor.py, gemini_executor.py    |
| Server             | A2AStarletteApplication         | server.py implemented                     |
| gRPC support       | v0.3 feature                    | Not implemented                           |
| Push notifications | Spec-supported                  | Disabled in capabilities                  |

| Task state machine | 9 states (submitted through auth-required) | state_map.py maps 7 states |
| Enterprise adoption | S&P Global, ServiceNow, Tyson Foods | Framework-only |

**v0.3 protocol updates:**

- gRPC support (alongside HTTP/JSON-RPC)
- Security card signing
- Extended Python client-side SDK support
- LangGraph v0.2 integration (A2A as first-class protocol target)

**Vaultspec's A2A implementation** is architecturally complete (agent cards, discovery, executors, server, state mapping) but lacks the v0.3 additions (gRPC, security signing). The zero-production-import note from MEMORY.md suggests A2A may be implemented but not yet actively used in real workflows.

### 1.4 Protocol Integration: MCP + A2A + ACP Together

- **MCP** = resource/tool layer (vertical: agent connects to tools/data)
- **A2A** = network/collaboration layer (horizontal: agents talk to agents)
  This is exactly the architecture vaultspec has adopted. LangGraph v0.2 (Jan 2026) validated this pattern by shipping A2A and MCP as first-class protocol targets. The industry metaphor is "TCP/IP for agentic AI" — MCP is the transport, A2A is the application protocol, ACP is the session layer.
  **Vaultspec advantage:** Very few frameworks implement all three protocols. Most implement MCP only, or MCP + one other. Vaultspec's three-protocol stance is architecturally prescient.

______________________________________________________________________

## 2. AAIF (Agentic AI Foundation) Progress

**Formed**: December 2025, under Linux Foundation
**Co-founders**: Anthropic, Block, OpenAI (with Google, Microsoft, AWS, Bloomberg, Cloudflare support)
**Anchor projects contributed**:

| Project | Origin | Purpose |

|\---------|--------|---------|
| MCP | Anthropic | Agent-to-tool protocol |
| AGENTS.md | OpenAI | Machine-readable project guidance for agents |
| Goose | Block | Open-source local-first AI agent framework |

**Key observations:**

- AAIF operates as a directed fund (proven Linux Foundation governance model)
- A2A is a separate Linux Foundation project (not under AAIF, but complementary)
- AGENTS.md has been adopted by 60,000+ open-source projects
- Goose is Apache 2.0, MCP-native, multi-model, desktop + CLI
- Cisco joined AAIF in early 2026

**Gap for vaultspec:** AGENTS.md and Goose are now industry standards. Vaultspec does not generate or consume AGENTS.md files, and has no Goose integration.

______________________________________________________________________

## 3. Spec-Driven Development (SDD) Landscape

Vaultspec's core methodology — spec-driven development — has gone from niche to mainstream in 2026.

### 3.1 Competing SDD Tools

| Tool | Origin | Methodology | Status |

|\------|--------|-------------|--------|
| **Amazon Kiro** | AWS | Spec -> Design -> Tasks -> Implementation | IDE (VS Code fork), cloud-agnostic |
| **GitHub Spec-Kit** | GitHub | Constitution -> Specify -> Plan -> Tasks | CLI + slash commands |
| **BMAD-METHOD** | Community | Multi-agent spec-driven | Open-source |
| **vaultspec** | Independent | Research -> Specify -> Plan -> Execute -> Verify | Framework + RAG + protocols |

**Key differentiators of each:**

- **Kiro**: Deep IDE integration, "Agent Steering" (product.md, structure.md, tech.md), spec-first UX. Recently adopted ACP.
- **vaultspec**: 5-phase workflow, documentation vault (.vault/), RAG-powered context, three-protocol stack, GPU-accelerated embeddings, verification layer.

| Architecture | Description | Maturity |

| **Agentic RAG** | Autonomous agents decide what/when/how to retrieve | Emerging (2026 frontier) |
| **GraphRAG** | Knowledge graphs + vector search combined | Emerging |
**Vaultspec's current approach:** Advanced RAG with GPU-accelerated embeddings via sentence-transformers + LanceDB. This is solid but increasingly baseline in 2026.

- No reranking step after initial retrieval
- No cross-document relationship tracking

### 4.2 Embedding Model Landscape (2026)

| Model | Parameters | MTEB Rank | Features |
| ----- | ---------- | --------- | -------- |

| **Qwen3-Embedding-8B** | 8B | #1 multilingual | Variable dims (32-1024), instruction-aware |
| **Qwen3-Embedding-4B** | 4B | Top-5 | Good quality/size balance |
| **Qwen3-Embedding-0.6B** | 0.6B | Strong for size | Lightweight, fast |
| **BGE-M3** | 568M | High | Dense + sparse + multi-vector |
| **NV-Embed-v2** | ~1B | Top-10 | NVIDIA GPU optimized |
| **EmbeddingGemma-300M** | 300M | Strong | On-device, multilingual |
| **nomic-embed-text-v1.5** | 137M | Mid-tier | vaultspec's current model |

**Vaultspec's current model:** nomic-embed-text-v1.5 (137M parameters) via sentence-transformers.

**Gap analysis:**

- nomic-embed-text-v1.5 is a 2024-era model; 2025-2026 models significantly outperform it
- Variable-dimension embeddings (matryoshka) would allow trading accuracy for speed/storage
- Instruction-aware embeddings (Qwen3) improve retrieval quality by encoding query intent
- vaultspec has an RTX 4080 SUPER (16GB VRAM) — it can easily run 4B or even 8B embedding models that dramatically outperform the current 137M model
- Current MAX_EMBED_CHARS=8000 truncation; newer models handle 32K+ token contexts

**Performance comparison estimate (RTX 4080 SUPER):**

| Model                | Size | Expected Throughput | Quality vs nomic-v1.5     |
| -------------------- | ---- | ------------------- | ------------------------- |
| nomic-v1.5 (current) | 137M | ~33 docs/sec        | Baseline                  |
| Qwen3-Embedding-0.6B | 600M | ~20-25 docs/sec     | Significantly better      |
| Qwen3-Embedding-4B   | 4B   | ~5-8 docs/sec       | Much better               |
| BGE-M3               | 568M | ~18-22 docs/sec     | Better + hybrid retrieval |

The throughput decrease is offset by dramatically better retrieval quality, and 214 docs indexes in under 30 seconds even at 5 docs/sec.

### 4.3 LanceDB Capabilities (2026)

Vaultspec uses LanceDB as its vector store. LanceDB has added significant capabilities:

| Feature                      | LanceDB Status       | Vaultspec Usage          |
| ---------------------------- | -------------------- | ------------------------ |
| GPU-accelerated indexing     | Supported (IVF/HNSW) | Not used (CPU indexing)  |
| Full-text search             | Supported            | Not used                 |
| Hybrid search (vector + FTS) | Supported            | Not used                 |
| Multimodal storage           | Supported            | Not used                 |
| Enterprise auto-GPU indexing | Enterprise only      | N/A                      |
| Serverless cloud             | Available            | Local only (appropriate) |

**Opportunity:** LanceDB's hybrid search (vector + full-text) could significantly improve vaultspec's retrieval quality with minimal code changes.

______________________________________________________________________

## 5. AI Agent Verification & Evaluation

### 5.1 Industry State of the Art

| Tool/Framework | Focus                                   | Key Feature               |
| -------------- | --------------------------------------- | ------------------------- |
| **Maxim AI**   | Simulation + evaluation + observability | Comprehensive platform    |
| **Langfuse**   | Open-source tracing                     | Agent trajectory analysis |
| **Braintrust** | Evaluation + observability              | LLM-based rubric grading  |
| **Galileo**    | Hallucination detection                 | Guardrails                |

| **Anthropic Bloom** | Automated behavioral evals | Open-source (Anthropic) |

**Anthropic's evaluation framework (Jan 2026):**

- 20-50 real-failure-derived tasks are sufficient for meaningful evals

- Grade outcomes, not paths (agents find creative solutions)

- Combine deterministic tests + LLM-based rubrics

- Run evals in CI/CD as first line of defense

- Production monitoring for distribution drift

### 5.2 Vaultspec's Verification Layer

Vaultspec's current verification (`verification/api.py`) focuses on:

- Vault structure validation (directory layout)
- File naming conventions
- Metadata/tag compliance
- Content validation (YAML frontmatter)

**Gaps relative to industry:**

- No agent output evaluation (task success rate, trajectory analysis)
- No hallucination detection
- No groundedness checking (are claims supported by retrieved sources?)
- No CI/CD integration for automated verification
- No production telemetry or observability
- No eval framework for measuring spec compliance of generated code

______________________________________________________________________

## 6. Feature Gap Analysis

### 6.1 Critical Gaps (High Impact, Clear Path)

| Gap                         | What Exists in Ecosystem        | Vaultspec Status             | Recommendation                               |
| --------------------------- | ------------------------------- | ---------------------------- | -------------------------------------------- |
| **AGENTS.md support**       | 60,000+ projects, AAIF standard | Not implemented              | Generate AGENTS.md from vaultspec config     |
| **MCP security hardening**  | OWASP MCP Top 10 published      | No security measures         | Implement auth, input validation, sandboxing |
| **Embedding model upgrade** | Qwen3 family, BGE-M3            | nomic-embed-text-v1.5 (2024) | Upgrade to Qwen3-Embedding-0.6B or BGE-M3    |
| **Hybrid search**           | LanceDB native support          | Vector-only search           | Add full-text + vector hybrid retrieval      |
| **Agent eval framework**    | Anthropic's eval methodology    | Structure validation only    | Add outcome-based agent evaluation           |

### 6.2 Strategic Gaps (High Impact, Requires Design)

| Gap                          | What Exists in Ecosystem     | Vaultspec Status          | Recommendation                              |
| ---------------------------- | ---------------------------- | ------------------------- | ------------------------------------------- |
| **ACP Registry listing**     | Live registry, multi-editor  | Not registered            | Register vaultspec agents in ACP Registry   |
| **A2A v0.3 features**        | gRPC, security signing       | v0.3.22 SDK, partial impl | Add gRPC transport, card signing            |
| **Agentic RAG**              | LangGraph, LlamaIndex agents | Static retrieval          | Add iterative retrieve-evaluate-refine loop |
| **GraphRAG**                 | Microsoft GraphRAG, LightRAG | No knowledge graph        | Consider for cross-document relationships   |
| **MCP Registry integration** | Preview, GA planned 2026     | Not integrated            | Plan for when registry goes GA              |

### 6.3 Emerging Opportunities (Watch & Plan)

| Opportunity                       | Ecosystem Status                | Recommendation                            |
| --------------------------------- | ------------------------------- | ----------------------------------------- |
| **Goose integration**             | AAIF anchor project, MCP-native | Evaluate as complementary agent framework |
| **Variable-dimension embeddings** | Qwen3 supports 32-1024 dims     | Use for speed/quality tradeoff per query  |
| **Reranking models**              | Standard in production RAG      | Add reranking step (cross-encoder)        |

| **MCP Gateway** | Kong, MintMCP, enterprise pattern | Consider for multi-agent security |

______________________________________________________________________

## 7. Technology Trends

### 7.1 Where the Space is Heading

**Protocol convergence:**

- MCP + A2A + ACP is the emerging standard stack (vaultspec is aligned)

- AAIF provides neutral governance (reduces vendor lock-in risk)

- LangGraph v0.2 validates the MCP-for-tools + A2A-for-agents pattern
  **SDD maturation:**

- Amazon andialized architectures per use case

- GraphRAG for relationship-heavy domains

- Hybrid search becoming table stakes

**Security urgency:**

- MCP security is now a top concern (OWASP Top 10, real CVEs)

- Every tool execution must be treated as a potential injection vector

- Authentication, sandboxing, and audit logging are no longer optional

**Embeddings leap:**

- 2024 models (nomic, E5) are being superseded by 2025-2026 models (Qwen3, BGE-M3)
- Instruction-aware embeddings significantly improve retrieval
- Variable-dimension embeddings enable speed/quality tradeoffs
- 16GB VRAM is sufficient for 4B+ parameter embedding models

### 7.2 Vaultspec's Strategic Position

**Strengths:**

- Three-protocol architecture (MCP + ACP + A2A) is ahead of the curve
- Spec-driven methodology is now industry-validated
- GPU-accelerated local inference is a differentiator
- Documentation vault concept is unique
- Verification layer provides governance that competitors lack

**Risks:**

- Kiro (AWS) and Spec-Kit (GitHub) have massive platform advantages
- Current embedding model is falling behind state of the art
- MCP security gaps could be exploited
- A2A implementation may be ahead of actual user demand
- No IDE integration limits accessibility

______________________________________________________________________

## 8. Recommendations

### Immediate (Next Sprint)

1. **Generate AGENTS.md from vaultspec config** — This is the lowest-effort, highest-signal improvement. AGENTS.md is adopted by 60,000+ projects and is now an AAIF standard. Vaultspec already has agent definitions and project metadata that can be automatically rendered as AGENTS.md.

1. **Upgrade embedding model** — Replace nomic-embed-text-v1.5 with Qwen3-Embedding-0.6B or BGE-M3. The RTX 4080 SUPER handles these easily. Expected retrieval quality improvement: 15-30% on standard benchmarks. Implementation: change model name in embeddings.py, adjust MAX_EMBED_CHARS.

1. **Enable LanceDB hybrid search** — Add full-text search alongside vector search. LanceDB supports this natively. Minimal code change, significant retrieval improvement for exact-match queries (function names, error codes, etc.).

### Short-Term (Next Quarter)

1. **Implement MCP security baseline** — Address OWASP MCP Top 10 items MCP01 (secrets), MCP05 (command injection), MCP07 (auth). Add input validation to the 5 MCP tools in vs-subagent-mcp.

1. **Register in ACP Registry** — Make vaultspec agents discoverable in Zed, JetBrains, Neovim, and Emacs. This is primarily a metadata/registration task.

1. **Add agent eval framework** — Following Anthropic's methodology: 20-50 real-failure tasks, outcome-based grading, CI/CD integration. Vaultspec's verification layer is the natural home for this.

### Medium-Term (Next 6 Months)

1. **Explore GraphRAG** — For cross-document relationship tracking in the vault. ADRs reference plans, plans reference specs, specs reference requirements — these relationships are currently lost in flat vector search.

1. **Consider MCP Registry integration** — When the registry reaches GA, publish vs-subagent-mcp for discoverability.

______________________________________________________________________

## 9. Sources

### Protocol Ecosystem

- [MCP Roadmap](https://modelcontextprotocol.io/development/roadmap)

- [A Year of MCP Review (Pento)](https://www.pento.ai/blog/a-year-of-mcp-2025-review)

- [MCP Wikipedia](https://en.wikipedia.org/wiki/Model_Context_Protocol)

- [ACP Progress Report (Zed)](https://zed.dev/blog/acp-progress-report)

- [JetBrains ACP Agent Registry](https://blog.jetbrains.com/ai/2026/01/acp-agent-registry/)

- [JetBrains x Zed ACP](https://blog.jetbrains.com/ai/2025/10/jetbrains-zed-open-interoperability-for-ai-coding-agents-in-your-ide/)

- [Auggie ACP Support](https://www.augmentcode.com/blog/auggie-acp-zed-neovim-emacs)

- [Kiro Adopts ACP](https://kiro.dev/blog/kiro-adopts-acp/)

- [A2A Protocol (Google)](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)

- [A2A Getting Upgrade (Google Cloud)](https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade)

- [A2A Linux Foundation](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents)

- [A2A Python SDK Guide](https://towardsdatascience.com/multi-agent-communication-with-the-a2a-python-sdk/)

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)

### AAIF & Standards

- [AAIF Announcement (Linux Foundation)](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)
- [AAIF Official Site](https://aaif.io/)
- [OpenAI AAIF Co-founding](https://openai.com/index/agentic-ai-foundation/)
- [Block AAIF Announcement](https://block.xyz/inside/block-anthropic-and-openai-launch-the-agentic-ai-foundation)
- [Cisco Joins AAIF](https://blogs.cisco.com/news/innovation-happens-in-the-open-cisco-joins-the-agentic-ai-foundation-aaif)
- [AGENTS.md Standard](https://agents.md/)
- [AGENTS.md GitHub](https://github.com/agentsmd/agents.md)
- [Goose (Block)](https://github.com/block/goose)

### MCP + A2A Integration

- [MCP vs A2A Guide](https://onereach.ai/blog/guide-choosing-mcp-vs-a2a-protocols/)
- [Agent Protocol Stack (TCP/IP Metaphor)](https://subhadipmitra.com/blog/2026/agent-protocol-stack/)
- [Top AI Agent Protocols 2026](https://getstream.io/blog/ai-agent-protocols/)

### Security

- [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/)
- [MCP Authentication Guide](https://www.infisign.ai/blog/what-is-mcp-authentication-authorization)
- [MCP Security Best Practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices)
- [Anthropic/Microsoft MCP Server Flaws](https://securityboulevard.com/2026/01/anthropic-microsoft-mcp-server-flaws-shine-a-light-on-ai-security-risks/)
- [MCP Azure Security Guide (Microsoft)](https://microsoft.github.io/mcp-azure-security-guide/)

### SDD Tools

- [SDD with AI Agents (Medium)](https://medium.com/@dave-patten/spec-driven-development-with-ai-agents-from-build-to-runtime-diagnostics-415025fb1d62)
- [Zencoder SDD Guide](https://docs.zencoder.ai/user-guides/tutorials/spec-driven-development-guide)
- [SDD Unpacking (Thoughtworks)](https://www.thoughtworks.com/en-us/insights/blog/agile-engineering-practices/spec-driven-development-unpacking-2025-new-engineering-practices)
- [SDD 3 Tools (Martin Fowler)](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)
- [Kiro (Amazon)](https://kiro.dev/)
- [GitHub Spec-Kit](https://github.com/github/spec-kit/blob/main/spec-driven.md)
- [SDD InfoQ](https://www.infoq.com/articles/spec-driven-development/)

### RAG & Embeddings

- [RAG Survey 2026 (arXiv)](https://arxiv.org/html/2506.00054v1)
- [State of RAG 2026 (Squirro)](https://squirro.com/squirro-blog/state-of-rag-genai)
- [10 RAG Architectures 2026](https://newsletter.rakeshgohel.com/p/10-types-of-rag-architectures-and-their-use-cases-in-2026)
- [Top Agentic RAG Frameworks 2026](https://research.aimultiple.com/agentic-rag/)
- [GraphRAG Guide (Meilisearch)](https://www.meilisearch.com/blog/graph-rag)
- [Microsoft GraphRAG](https://microsoft.github.io/graphrag/)
- [GraphRAG.com](https://graphrag.com/)
- [Best Embedding Models 2026](https://www.openxcell.com/blog/best-embedding-models/)
- [Open-Source Embedding Models (BentoML)](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)
- [Qwen3-Embedding](https://github.com/QwenLM/Qwen3-Embedding)
- [Embedding Millions with Qwen3 (Daft)](https://www.daft.ai/blog/embedding-millions-of-text-documents-with-qwen3)
- [LanceDB GPU Indexing](https://docs.lancedb.com/indexing/gpu-indexing)

### Verification & Evaluation

- [Demystifying Evals for AI Agents (Anthropic)](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Top 5 AI Agent Evaluation Tools 2026](https://www.getmaxim.ai/articles/top-5-ai-agent-evaluation-tools-in-2026/)
- [Bloom Auto Evals (Anthropic)](https://alignment.anthropic.com/2025/bloom-auto-evals/)
- [AI Agent Observability Tools 2026](https://research.aimultiple.com/agentic-monitoring/)
- [Agent Reliability Tools (Braintrust)](https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026)
