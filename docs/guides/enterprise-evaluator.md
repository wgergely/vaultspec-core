# vaultspec for Enterprise

Enterprise adoption of AI coding agents is accelerating. So is regulatory
scrutiny of what those agents produce. The EU AI Act entered full enforcement
in August 2026. SOC 2 auditors are asking about AI in the SDLC. Regulated
industries — financial services, healthcare, defence — are discovering that
"we used an AI" is not an acceptable answer when an auditor asks why a
critical system was implemented a particular way.

The problem is not the AI. The problem is the absence of governance around
the AI. AI agents that operate without documented specifications, human
approval gates, and persistent audit trails produce outputs that cannot be
traced, justified, or defended under audit.

vaultspec is the governance layer. It enforces a structured pipeline that
makes AI-assisted development auditable by design.

## Security Model

Enterprise evaluation typically starts here. Key properties:

**No external data transmission for core features.** Research, ADRs, plans,
execution, and review all operate against local files. The `.vault/` directory
never leaves your infrastructure unless you commit it to a repository you
control.

**Local GPU for semantic search.** The RAG search feature runs on a local
NVIDIA GPU. Embeddings are computed locally and stored in a local LanceDB
index. No document content is sent to an external embedding service.

**Self-hosted deployment.** vaultspec has no cloud dependency. The framework
runs entirely within your infrastructure. There is no telemetry, no
call-home, and no vendor lock-in beyond your choice of LLM provider for the
agents themselves.

**Protocol stack visibility.** The framework uses three open protocols:

| Protocol | Purpose | Body |
| :--- | :--- | :--- |
| MCP | Agent-to-tool communication | Anthropic / AAIF |
| ACP | Orchestrator-to-agent dispatch | Zed Industries |
| A2A | Horizontal agent coordination | Google / AAIF |

All three are open, documented protocols. No proprietary communication
channels.

## Regulatory Alignment

### EU AI Act

The EU AI Act requires providers and operators of high-risk AI systems to
maintain technical documentation demonstrating human oversight and
traceability of AI decisions. vaultspec's artifact trail satisfies these
requirements by construction:

- **Research artifacts** document the problem space and the information the
  AI operated on.
- **Architecture Decision Records** document decisions, alternatives, and
  rationale — directly satisfying Article 13 (transparency) requirements.
- **Implementation plans with human approval gates** satisfy Article 14
  (human oversight) requirements.
- **Execution records and code reviews** provide the audit trail required
  under Article 17 (quality management).

The `.vault/` directory, committed to version control, is a complete,
timestamped, tamper-evident record of AI governance for every feature.

### SOC 2 and Internal Audit

SOC 2 Type II audits increasingly include questions about AI in the SDLC.
Common audit questions and vaultspec's answers:

- *How do you ensure AI-generated code is reviewed before deployment?*
  The `vaultspec-review` phase is mandatory. Code review artifacts are
  persisted to `.vault/exec/` and must pass before the execution phase is
  marked complete.
- *How do you ensure AI agents operate within approved boundaries?*
  Agent behavior is governed by rules in `.vaultspec/rules/` and by approved
  implementation plans. Agents do not improvise; they execute against plans
  that have been approved by a human.
- *What documentation exists for AI-generated architectural decisions?*
  Every significant decision produces an ADR in `.vault/adr/`. ADRs are
  version-controlled and linked to the research that grounded them.

## Deployment Architecture

```text
Your infrastructure
  .vaultspec/          # Framework rules, agents, skills, templates
  .vault/              # Audit trail (research, ADRs, plans, exec records)
  .venv/               # Python environment
  LLM provider API     # Claude, Gemini, or local model (outbound only)
```

The only external dependency is outbound API calls to your chosen LLM
provider. If your organization uses a private LLM deployment (Azure OpenAI,
Vertex AI, or a self-hosted model), vaultspec can be configured to route
all model calls through it. No vault content leaves your infrastructure.

## Integration with Existing Workflows

vaultspec is designed to complement, not replace, existing SDLC tooling:

- **Git** — The `.vault/` directory is committed to your repository.
  All artifact history is in git history.
- **CI/CD** — The framework includes GitHub Actions workflows for automated
  testing and PyPI publishing. The audit trail is part of the repository,
  so CI pipelines can verify its completeness.
- **Code review tools** — vaultspec review artifacts can be referenced in
  PR descriptions. Reviewers gain context from the ADR and plan without
  needing to reconstruct it from code alone.
- **Issue tracking** — Research artifacts and ADRs can link to Jira or
  GitHub Issues, closing the loop between requirements and implementation
  decisions.

## Evaluator Checklist

For a structured evaluation, verify the following:

- [ ] `cli.py doctor` passes in your environment
- [ ] A research artifact is produced for a sample problem
- [ ] An ADR is generated and references the research
- [ ] A plan is generated, presented for approval, and approved
- [ ] Execution produces step records in `.vault/exec/`
- [ ] A code review artifact is produced and linked to the execution records
- [ ] The complete `.vault/` chain is committed to git and auditable

## Further Reading

- [Concepts](../concepts.md) — governance model, agent architecture, and
  protocol stack in depth
- [Configuration](../configuration.md) — environment variables, LLM provider
  configuration, and deployment options
- [CLI Reference](../cli-reference.md) — full command reference including
  `doctor`, `config sync`, and `system sync`
- [Search Guide](../search-guide.md) — GPU requirements, local RAG
  architecture, and search capabilities
