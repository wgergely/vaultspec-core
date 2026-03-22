---
tags:
  - '#research'
  - '#marketing-audit'
date: '2026-02-18'
---

## Marketing Audit: Governance & SDD Positioning

## Executive Summary

Spec-driven development (SDD) has emerged in 2025 as one of the most significant methodological shifts in AI-assisted software engineering. vaultspec's Research→Specify→Plan→Execute→Verify pipeline and its emphasis on auditable, documented development workflows are well-aligned with both the emerging tooling landscape and deepening enterprise governance requirements. The window for positioning vaultspec as the gold-standard governed AI development framework is open — but competitors are moving fast.

______________________________________________________________________

## 1. Spec-Driven Development: Established Term, Growing Momentum

SDD is now a recognized, actively discussed methodology with industry endorsement from major organizations.

**Key findings:**

- Thoughtworks named spec-driven development one of "2025's key new AI-assisted engineering practices" — giving the term significant mainstream credibility. ([Thoughtworks](https://thoughtworks.medium.com/spec-driven-development-d85995a81387))
- AWS launched **Kiro** in August 2025, a VS Code fork explicitly built around spec-driven agentic development. Its workflow outputs user stories, acceptance criteria, technical design documents, and implementation tasks before any code is written. ([InfoQ](https://www.infoq.com/news/2025/08/aws-kiro-spec-driven-agent/))
- GitHub launched **Spec Kit** for Copilot. JetBrains published a spec-driven approach for its Junie agent. Red Hat Developer published a guide on SDD improving AI coding quality. ([JetBrains](https://blog.jetbrains.com/junie/2025/10/how-to-use-a-spec-driven-approach-for-coding-with-ai/), [Red Hat](https://developers.redhat.com/articles/2025/10/22/how-spec-driven-development-improves-ai-coding-quality))
- Martin Fowler's site published a comparative analysis of SDD tooling (Kiro, Spec-Kit, Tessl), lending authoritative recognition to the methodology. ([martinfowler.com](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html))

**Canonical workflow (as articulated across the ecosystem):** `Specify → Plan → Tasks → Implement`

vaultspec's pipeline (`Research → Specify → Plan → Execute → Verify`) extends this with two additional phases — upstream research grounding and downstream verification — which represents a more complete governance model than any current competitor.

**Comparison to TDD/BDD/DDD:**

- TDD focuses on test-first code quality; BDD on behavior-driven collaboration; DDD on domain modeling
- SDD is distinct: it is documentation-first with AI as the implementation engine
- SDD does not replace TDD/BDD — it wraps them, providing the specification layer that guides AI before tests are written

______________________________________________________________________

## 2. AI Agent Governance: Real Demand, Immature Tooling

Enterprise demand for governance is explicit and urgent, but the tooling ecosystem has not yet produced a comprehensive governed development framework.

### 2.1 Enterprise Governance Requirements

- A survey found **99% of enterprise AI developers** are exploring or building AI agents (IBM/Morning Consult, 2025).
- **Nearly 70%** of respondents estimated that over 40% of their organization's code was AI-generated in 2024. ([Checkmarx](https://checkmarx.com/blog/ai-is-writing-your-code-whos-keeping-it-secure/))
- In an August 2025 survey of 18 CTOs, **16 reported production disasters** directly caused by AI-generated code. ([ainvest.com](https://www.ainvest.com/news/ai-assisted-coding-tools-risks-vibe-coding-balancing-innovation-enterprise-software-sustainability-2512/))
- Enterprises are moving from open experimentation to centralized "AI enablement" teams with strict policies on data privacy, IP, and model hosting. ([MIT Technology Review](https://www.technologyreview.com/2025/11/05/1127477/from-vibe-coding-to-context-engineering-2025-in-software-development/))

### 2.2 What Enterprises Need from Governed AI Development

Governance frameworks articulate four pillars: **transparency, accountability, security, and ethics**. In the development context this translates to:

- Audit trails for AI-generated code decisions
- Human-in-the-loop checkpoints (especially pre-deployment)
- Documentation of *why* choices were made, not just *what* was built
- Cross-functional accountability across design, development, and review

Sources: [WitnessAI](https://witness.ai/blog/agentic-ai-governance-framework/), [IMDA Agentic AI Framework](https://www.imda.gov.sg/-/media/imda/files/about/emerging-tech-and-research/artificial-intelligence/mgf-for-agentic-ai.pdf), [Microsoft CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)

### 2.3 Current Tool Landscape: Governance Gaps

| Tool                      | Spec-Driven | Audit Trail       | ADR-backed | Verify Phase | Agent Dispatch |
| ------------------------- | ----------- | ----------------- | ---------- | ------------ | -------------- |
| AWS Kiro                  | Yes         | Partial           | No         | No           | No             |
| GitHub Copilot + Spec-Kit | Partial     | Audit logs        | No         | No           | Limited        |
| Cursor / Windsurf         | No          | No                | No         | No           | No             |
| **vaultspec**             | **Yes**     | **Yes (.vault/)** | **Yes**    | **Yes**      | **Yes**        |

No existing tool enforces a full Research→Specify→Plan→Execute→Verify pipeline. No competitor generates ADR-backed decisions as first-class artifacts. No competitor provides session-persistent context as a governance mechanism.

______________________________________________________________________

## 3. Regulatory Tailwinds: The EU AI Act and Beyond

The regulatory environment strongly supports the vaultspec positioning.

### 3.1 EU AI Act Timeline

- **February 2025**: AI literacy requirements took effect for organizations deploying AI in the EU.
- **August 2025**: GPAI model rules took effect — technical documentation and training content summaries required.
- **August 2026**: Full transparency and accountability rules apply to all operators. ([SIG](https://www.softwareimprovementgroup.com/blog/eu-ai-act-summary/), [DataGuard](https://www.dataguard.com/eu-ai-act/timeline))

### 3.2 Compliance Requirements Directly Addressable by vaultspec

The EU AI Act and enterprise compliance frameworks demand:

- **Audit logs** of AI decisions and human review steps — vaultspec's `.vault/exec/` records satisfy this
- **Documentation of AI-generated code review** — vaultspec-code-review enforces mandatory post-execution review
- **Rationale for architectural decisions** — ADRs in `.vault/adr/` provide traceable decision records
- **Risk documentation** — research artifacts in `.vault/research/` document pre-decision analysis

Penalties for non-compliance reach €10 million or 2% of annual turnover. ([Andersen Lab](https://andersenlab.co.uk/blueprint/eu-ai-act))

### 3.3 US Federal Context

Executive Order 14179 (January 2025) focuses on AI leadership, but federal agencies still require accountability frameworks (see [US GAO AI Accountability Framework](https://www.gao.gov/products/gao-21-519sp)). NIST AI RMF remains the primary US reference.

______________________________________________________________________

## 4. Architecture Decision Records: Mainstream, But Manual

ADR adoption has matured significantly and has strong enterprise backing — but the tooling remains fragmented and largely manual.

**Key findings:**

- AWS documents best practices for ADRs across projects with 10–100+ team members. ([AWS Architecture Blog](https://aws.amazon.com/blogs/architecture/master-architecture-decision-records-adrs-best-practices-for-effective-decision-making/))
- Microsoft's Azure Well-Architected Framework explicitly recommends ADRs. ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record))
- The UK Government Digital Service introduced a formal ADR framework in December 2025 for joined-up, auditable technology decisions across the public sector. ([UK Government Blog](https://technology.blog.gov.uk/2025/12/08/the-architecture-decision-record-adr-framework-making-better-technology-decisions-across-the-public-sector/))
- Research on **AgenticAKM** (Agentic Architecture Knowledge Management) demonstrates that LLM-powered agents can extract, generate, and validate ADRs from codebases — with significantly better results than simple LLM calls. ([arXiv:2602.04445](https://arxiv.org/html/2602.04445v1))

**The gap vaultspec fills:** While ADRs are broadly endorsed, no AI coding tool generates them automatically as part of the development workflow. vaultspec is the only framework where ADRs are a *required first-class artifact* before execution proceeds.

______________________________________________________________________

## 5. Context Persistence: The Unsolved Problem

Context loss between AI sessions is a critical pain point across the industry.

**Key findings:**

- The dominant framing in 2025 shifted from "AI memory" to **"context engineering"** — the systematic management of what context AI agents receive. ([MIT Technology Review](https://www.technologyreview.com/2025/11/05/1127477/from-vibe-coding-to-context-engineering-2025-in-software-development/))
- Vector store, summarization, and graph-based memory architectures are all being explored. None is a solved standard. ([The New Stack](https://thenewstack.io/memory-for-ai-agents-a-new-paradigm-of-context-engineering/))
- OneContext offers a "persistent context layer for AI coding agents" as a separate product, underscoring that this is an unsolved, commercially significant problem.
- The core critique of current retention approaches: AI systems "knew what happened but not *why* it mattered." ([Sphere Inc.](https://www.sphereinc.com/blogs/ai-memory-and-context/))

**vaultspec's answer:** `.vault/` is a documentation-as-memory system. Research artifacts, ADRs, plans, and exec records collectively constitute a *semantic memory* of why decisions were made — not just what happened. This is RAG-indexed and queryable, which is architecturally superior to session-based retention.

______________________________________________________________________

## 6. Market Positioning Implications

### Differentiated Claims (evidence-backed)

1. **"The only framework that enforces the complete Research→Specify→Plan→Execute→Verify pipeline"** — no competitor implements all 5 phases as mandatory workflow
1. **"ADR-backed every decision"** — no competitor makes architecture decision records a first-class, required workflow artifact
1. **"Built for EU AI Act compliance"** — `.vault/` audit trail + mandatory human review directly addresses transparency/accountability requirements
1. **"Documentation as memory"** — RAG-indexed `.vault/` solves context persistence at a deeper level than vector-store retention
1. **"Governed, not governed by vibes"** — directly positions against the "vibe coding → production disasters" narrative

### Target Segments

- **Enterprise engineering teams** concerned about AI code reliability and audit trails
- **Organizations in regulated industries** (finance, healthcare, government) facing EU AI Act or equivalent
- **Platform engineering / AI enablement teams** building internal standards for AI-assisted development
- **Teams already using ADRs** who want AI to generate and enforce them automatically

### Competitive Risks

- **AWS Kiro** is the closest structural competitor and has significant distribution advantage via AWS ecosystem
- GitHub Copilot's enterprise governance features (audit logs, agent control plane) address the compliance angle but not the workflow structure
- The methodology is becoming established enough that larger players may add SDD-like features to existing tools

______________________________________________________________________

## Sources

- [Thoughtworks: Spec-Driven Development](https://thoughtworks.medium.com/spec-driven-development-d85995a81387)
- [SoftwareSeni: Spec-Driven Development Complete Guide](https://www.softwareseni.com/spec-driven-development-in-2025-the-complete-guide-to-using-ai-to-write-production-code/)
- [JetBrains: Spec-Driven Approach for AI Coding](https://blog.jetbrains.com/junie/2025/10/how-to-use-a-spec-driven-approach-for-coding-with-ai/)
- [Red Hat: How SDD Improves AI Coding Quality](https://developers.redhat.com/articles/2025/10/22/how-spec-driven-development-improves-ai-coding-quality)
- [Martin Fowler: SDD Tools Analysis](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)
- [InfoQ: AWS Kiro Spec-Driven Agent IDE](https://www.infoq.com/news/2025/08/aws-kiro-spec-driven-agent/)
- [Kiro.dev](https://kiro.dev/)
- [AWS: Kiro Project Init](https://aws.amazon.com/startups/prompt-library/kiro-project-init)
- [IMDA: Model AI Governance Framework for Agentic AI](https://www.imda.gov.sg/-/media/imda/files/about/emerging-tech-and-research/artificial-intelligence/mgf-for-agentic-ai.pdf)
- [WitnessAI: Agentic AI Governance Framework](https://witness.ai/blog/agentic-ai-governance-framework/)
- [Microsoft: AI Agent Governance](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- [Palo Alto Networks: Agentic AI Governance](https://www.paloaltonetworks.com/cyberpedia/what-is-agentic-ai-governance)
- [MIT Technology Review: Vibe Coding to Context Engineering](https://www.technologyreview.com/2025/11/05/1127477/from-vibe-coding-to-context-engineering-2025-in-software-development/)
- [ainvest: Risks of Vibe Coding](https://www.ainvest.com/news/ai-assisted-coding-tools-risks-vibe-coding-balancing-innovation-enterprise-software-sustainability-2512/)
- [Checkmarx: 2025 CISO Guide to AI-Generated Code](https://checkmarx.com/blog/ai-is-writing-your-code-whos-keeping-it-secure/)
- [SIG: EU AI Act Summary](https://www.softwareimprovementgroup.com/blog/eu-ai-act-summary/)
- [DataGuard: EU AI Act Timeline](https://www.dataguard.com/eu-ai-act/timeline)
- [Andersen Lab: EU AI Act 2026 Strategy](https://andersenlab.co.uk/blueprint/eu-ai-act)
- [US GAO: AI Accountability Framework](https://www.gao.gov/products/gao-21-519sp)
- [AWS Architecture Blog: ADR Best Practices](https://aws.amazon.com/blogs/architecture/master-architecture-decision-records-adrs-best-practices-for-effective-decision-making/)
- [Microsoft Learn: Architecture Decision Records](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- [UK Government: ADR Framework](https://technology.blog.gov.uk/2025/12/08/the-architecture-decision-record-adr-framework-making-better-technology-decisions-across-the-public-sector/)
- [arXiv: AgenticAKM](https://arxiv.org/html/2602.04445v1)
- [The New Stack: Memory for AI Agents](https://thenewstack.io/memory-for-ai-agents-a-new-paradigm-of-context-engineering/)
- [Sphere Inc: AI Memory vs Context](https://www.sphereinc.com/blogs/ai-memory-and-context/)
- [GitHub: Copilot Code Review](https://docs.github.com/en/copilot/concepts/agents/code-review)
- [ISACA: AI Governance Triad 2025](https://www.isaca.org/resources/news-and-trends/industry-news/2025/collaboration-and-the-new-triad-of-ai-governance)
