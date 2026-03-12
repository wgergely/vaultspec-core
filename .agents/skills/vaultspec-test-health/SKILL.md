---
name: vaultspec-test-health
description: Start a product health audit using a supervised team of agents. Assesses
  code quality, maintainability, test integrity, and adherence to project standards.
---

# Product Health Audit Skill (vaultspec-test-health)

When to use this skill:

- When you need a comprehensive assessment of codebase health beyond test
  pass/fail metrics.
- When you suspect tests are masking underlying code quality issues (false
  positives, over-mocking, narrow coverage).
- Before major refactors or releases to establish a quality baseline.
- When `conftest.py` hygiene or test organization needs auditing.

**Announce at start:** "I'm using the `vaultspec-test-health` skill to conduct
a product health audit."

**Save findings to:**
`.vault/audit/yyyy-mm-dd-health-audit-{scope}.md`

## Audit Focus

Do NOT trust tests as a valid indicator for code health. Tests can be written
in a way that they pass without actually revealing the true functionality and
behavior of the codebase. Instead, focus on the quality of the code itself, its
maintainability, readability, and how well it adheres to the project mission
goals.

### Identify

- Tests that do not provide insight into the actual integration and production
  flow. This includes tests that are too narrowly focused, do not cover edge
  cases, are tautological, or are written in a way that they can pass without
  truly validating the functionality of the code.
- Mocks, patches, stubs, false positives. These are NOT acceptable and are
  indicative of bad programming. Tests must be written in a way that they
  reveal the true behavior of the codebase in a production environment.
- Stale or badly optimized or structured tests.
- Unittest module imports. These are NOT supported. Always favor pytest for
  testing in Python.
- `conftest.py` files. Ensure they do not contain duplicate fixtures,
  unsupported markers. Audit them to ensure they define every required
  high-level fixture required for successful e2e and integration testing. DO
  NOT allow tests to try to solve issues individually that should be
  centralized.

### Verify

- Python and rust unit tests that do not reside in their source module's test
  directory.
- Integration tests and e2e tests are the only tests to be kept in the main
  module's `tests/` directory.

> **Note:** Any monkey patching must be explicitly approved by the user and
> is generally discouraged. If monkey patching is necessary, it must be done
> in a way that does not obscure the true behavior of the codebase and must
> be clearly documented.

## Team Composition

- **Supervisor**: This Opus agent supervises the team in read-only mode. The
  Supervisor's role is to step in when detecting "low-effort" work and code.
  This is the quality enforcer who will reject any work that doesn't pass
  the bar.
- **Investigator1-3**: These Sonnet agents are responsible for reading the
  codebase, identifying issues, and providing detailed reports on code health.
  They will focus on different aspects of the codebase, such as
  maintainability, readability, and adherence to best practices. They will
  work in parallel to ensure a comprehensive audit of the codebase and report
  back to the team lead.
- **CodingAgent1-2**: Opus agents responsible for coding work. Does not
  execute tests. Focuses solely on writing code that compiles and runs,
  without any regard for test outcomes. Works in parallel with CodingAgent2.
- **TestRunner1-2**: Read-only Haiku test runners responsible for running
  tests and reporting failures. This is the ONLY agent that runs tests. It
  does not write code or modify the codebase in any way. Its sole
  responsibility is to execute tests and report the results.

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
