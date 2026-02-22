---
name: vaultspec-test-marketing
description: >-
  Begin a comprehensive marketing audit using a supervised team of agents.
  Assesses release readiness, packaging, competitive positioning, and feature
  gap analysis.
---
# Marketing Audit Skill (vaultspec-test-marketing)

When to use this skill:

- When assessing the maturity and release readiness of the project.
- When evaluating packaging, distribution, and CI/CD pipeline completeness.
- When conducting competitive analysis or feature gap identification.
- Before public releases to ensure marketing materials and documentation are
  adequate.

**Announce at start:** "I'm using the `vaultspec-test-marketing` skill to
conduct a marketing audit."

**Save findings to:**
`.vault/audit/yyyy-mm-dd-marketing-audit-{scope}.md`

## Audit Focus

### Packaging and Distribution

Evaluate the current state of packaging and distribution. Does it exist? Is
there a clear CI/CD pipeline for releases? Are there any issues with the
current packaging and distribution process that could hinder the project's
ability to reach a wider audience? What dependencies does the project have?
Do we provide an installer? Is there a docker image? Is there a clear release
process? Are there any blockers to releasing the project to the public?

### Marketing Materials

The audit will include an assessment of the marketability and positioning of
the project. The audit must address:

- **Competitors/Alternatives**: Identify and analyze competitors or
  alternative solutions in the market. This includes evaluating their
  strengths and weaknesses, as well as how our project differentiates itself
  from them. What are the unique selling points of our project? How does it
  compare to existing solutions in terms of features, performance, and user
  experience?
- **Feature Gap Analysis**: Identify any gaps in the project's features
  compared to competitors or user expectations. This includes evaluating the
  current feature set and identifying any missing features that could enhance
  the project's value proposition. Are there any critical features that are
  currently missing? How do these gaps impact the overall user experience and
  marketability of the project?

## Team Composition

- **ResearchSupervisor**: This Opus agent supervises the team in read-only
  mode. The Supervisor's role is to oversee the research process. It will
  read the individual research agent reports and identify potential gaps, or
  request more work from the research agents if necessary.
- **ResearchAgent1-3**: These Sonnet agents are responsible for conducting
  the online research tasks. Both team lead and ResearchSupervisor can request
  work and reports.
- **MarketingSupervisor**: This Opus agent supervises the marketing team in
  read-only mode and researches high-level documentation status and bootstraps
  the marketing team with the necessary information to conduct the audit. The
  MarketingSupervisor will also step in to review the work of the marketing
  agents and ensure that it meets the standards of quality and relevance. It
  will request revisions or additional work from the marketing agents if
  necessary, and will provide feedback and guidance to ensure that the
  marketing audit is comprehensive and accurate.
- **MarketingAgent1-3**: These Sonnet agents are responsible for conducting
  the marketing audit tasks. They will focus on different aspects of the
  marketing audit, such as user documentation, ease of setup, packaging and
  distribution, and marketing materials. They will work in parallel to ensure
  a comprehensive audit of the marketing aspects of the project and report
  back to the team lead.
- **Feature Gap Analyst**: This Opus agent is responsible for conducting the
  feature gap analysis. It requires all previous research and marketing audit
  reports to conduct its analysis. It will identify any gaps in the project's
  features compared to competitors or user expectations, and will provide a
  detailed report on its findings. The Feature Gap Analyst will also provide
  recommendations for addressing any identified gaps, and will work with the
  marketing team to ensure that the project's value proposition is clear and
  compelling.

The team lead must never itself perform any heavy lifting and must instead
only focus on managing the work and flow of the team, stepping in when agents
are stuck, in a loop, or in need of further instructions. The team lead is the
only agent that can communicate with the user and must ensure that all
communication is clear, concise, and informative. The team lead is also
responsible for ensuring that all agents are working effectively and
efficiently, and that the overall goals of the audit are being met.

## Lifecycle

The team is to be kept alive, even after the audit is complete as the user
might request new work or ask follow up questions. The team should be ready to
respond to any new requests or questions from the user, and should continue
to provide support and assistance as needed.

## Persistence

- Every agent must persist their report to disk so that user and other agents
  have access to the information.
- The team lead must ensure that all reports are organized and easily
  accessible for review and reference.
- The team lead should maintain a clear record of all communications and
  decisions made during the audit process, to ensure transparency and
  accountability.

## Implementation

- User approved shutdown of the team. Verify that every research, decision,
  and ADR report is persisted to disk and organized in a way that they can be
  easily accessed and reviewed by the user. Ensure that all agents have
  completed their work and that there are no outstanding tasks or issues
  before shutting down the team. The team lead should provide a final report
  summarizing the findings of the audit and any recommendations for improving
  the code health of the project.
- Spawn new team with:
  - **Supervisor**: This Opus agent supervises the team in read-only mode.
    The Supervisor's role is to step in when detecting "low-effort" work and
    code. This is the quality enforcer who will reject any work that doesn't
    pass the bar. The supervisor internalizes every research report and
    audits, ADRs and implementation plans. It will compel the coding agents
    to finish and complete every task and will not allow any "low-effort" work
    to be accepted. It will also ensure that all work meets the standards of
    quality and relevance, and will request revisions or additional work from
    the coding agents if necessary.
  - **Coder1-{n}**: A mix and match of Sonnet and Opus agents responsible for
    coding work. Does not execute tests. Focuses solely on writing code that
    compiles and runs, without any regard for test outcomes. Works in parallel
    with Coder2.
  - **TestRunner1-{n}**: Read-only Haiku test runners responsible for running
    tests and reporting failures. This is the ONLY agent that runs tests. It
    does not write code or modify the codebase in any way. Its sole
    responsibility is to execute tests and report the results.
- The team lead will manage the workflow of the team, ensuring that all
  agents are working effectively and efficiently, and that the overall goals
  of the audit are being met. The team lead will always delegate work to the
  coding agents and test runners, and will step in to provide guidance and
  support as needed.

## Artifact Linking

- Any persisted markdown files must be linked against other persisted
  documents using quoted `"[[wiki-links]]"`.
- DO NOT use `@ref` style links or `[label](path)` style links.

### Frontmatter & Tagging Mandate

Every document MUST strictly adhere to the following schema:

- **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
  - **Directory Tag**: Exactly `#audit`.
  - **Feature Tag**: Exactly one kebab-case `#{feature}` tag.
  - *Syntax:* `tags: ["#audit", "#feature"]` (Must be quoted strings in a
    list).
- **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
  - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
- **`date`**: MUST use `yyyy-mm-dd` format.
- **No `feature` key**: Use `tags:` exclusively for feature identification.
