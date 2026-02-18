# From Scratch: Your First Governed Feature

This tutorial walks you through the full vaultspec pipeline using a concrete
example: adding a `/health` endpoint to a web service. By the end, you will
have created a complete audit trail in `.vault/` — research findings, an
architectural decision record, a plan, execution records, and a code review.

The five phases map to five CLI skills:

| Phase    | Skill              | Artifact                      |
|----------|--------------------|-------------------------------|
| Research | vaultspec-research | `.vault/research/...`         |
| Specify  | vaultspec-adr      | `.vault/adr/...`              |
| Plan     | vaultspec-write    | `.vault/plan/...`             |
| Execute  | vaultspec-execute  | `.vault/exec/.../steps`       |
| Verify   | vaultspec-review   | `.vault/exec/.../review`      |

---

## 1. Setup

Clone the repository and install dependencies:

```bash
git clone https://github.com/wgergely/vaultspec
cd vaultspec
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify the CLI is available:

```bash
python .vaultspec/lib/scripts/cli.py --help
```

The `.vault/` directory is created automatically the first time you invoke a
skill. It holds all your project's documented decisions and execution records.

---

## 2. Research

Before writing any code, you gather evidence. The `vaultspec-research` skill
dispatches a research sub-agent that searches the codebase, queries
documentation, and synthesizes findings into a structured artifact.

**Invoke the skill:**

```text
/vaultspec-research
```

The agent will ask for a topic. Provide:

> Research best practices for implementing a `/health` HTTP endpoint in a
> Python ASGI web service. Consider response format, status codes, dependency
> checking, and observability.

The sub-agent produces a file at:

```text
.vault/research/2026-02-18-health-endpoint-research.md
```

**Sample output:**

```markdown
---
tags:
  - "#research"
  - "#health-endpoint"
date: "2026-02-18"
related:
  - "[[2026-02-18-health-endpoint-adr]]"
---

# `health-endpoint` research: HTTP health check patterns

Research into standard `/health` endpoint implementations for Python ASGI
services, focusing on response format, status codes, and observability.

## Findings

### Response format

The two dominant conventions are plain-text `OK` and structured JSON.
JSON is preferred when the endpoint needs to report sub-system status
(database, cache, external APIs). The IETF Health Check Response Format
(RFC draft) defines a `application/health+json` content type with fields
`status`, `checks`, and `version`.

### Status codes

- `200 OK` — service is healthy and ready to receive traffic
- `503 Service Unavailable` — service is running but not ready
  (dependency failure, still warming up)

### Dependency checking

A shallow health check returns immediately. A deep check queries each
dependency (database ping, cache roundtrip) and reports per-component
status. Prefer shallow for load-balancer liveness probes; expose deep
as a separate `/ready` endpoint.

### Implementation options

| Option       | Pros                        | Cons                          |
|--------------|-----------------------------|-------------------------------|
| Starlette     | Already a dependency        | Manual JSON serialisation     |
| FastAPI       | Auto-schema, OpenAPI docs   | Not yet in project deps       |
| Plain ASGI    | Zero overhead               | Boilerplate-heavy             |

**Recommendation:** Implement using Starlette (already in `pyproject.toml`)
with a JSON response body. Use a shallow check for the liveness probe.
```

---

## 3. Specify

With research in hand, you formalise the decision in an Architectural Decision
Record (ADR). The `vaultspec-adr` skill reads the research artifact and
produces a structured decision document.

**Invoke the skill:**

```text
/vaultspec-adr
```

Reference the research artifact when prompted:

> Based on [[2026-02-18-health-endpoint-research]], create an ADR for
> implementing a `/health` endpoint using Starlette with a shallow JSON
> response.

The agent produces:

```text
.vault/adr/2026-02-18-health-endpoint-adr.md
```

**Sample output:**

```markdown
---
tags:
  - "#adr"
  - "#health-endpoint"
date: "2026-02-18"
related:
  - "[[2026-02-18-health-endpoint-research]]"
---

# `health-endpoint` adr: Starlette JSON health check | (**status:** `accepted`)

## Problem Statement

The service has no liveness probe. Kubernetes and load balancers need a
reliable signal that the process is running and able to serve traffic.

## Considerations

- Starlette is already a declared dependency (`starlette>=0.27.0`)
- The endpoint must respond in under 50 ms to avoid probe timeouts
- Response body should be machine-readable JSON
- No external dependencies should be checked (shallow liveness probe)

## Constraints

- Must not introduce new runtime dependencies
- Must return `200` when healthy, `503` when not ready
- Response schema: `{"status": "ok", "version": "<semver>"}`

## Implementation

Add a `GET /health` route to the existing Starlette application. Return a
`JSONResponse` with `status` and `version` fields. Read the version from
the package metadata (`importlib.metadata`).

## Rationale

Starlette is already present, so no new dependency is needed. A shallow
check is sufficient for a liveness probe — deep dependency checks belong
on a separate `/ready` endpoint introduced in a future ADR.

## Consequences

- Kubernetes liveness probe can be configured to `GET /health`
- The endpoint exposes the running package version, aiding debugging
- A future `/ready` endpoint will handle dependency checks
```

> **Important:** The ADR represents a decision. If you disagree with the
> agent's recommendation, edit the file before proceeding. The plan will be
> grounded in whatever the ADR says.

---

## 4. Plan

With an accepted ADR, you produce an execution plan. The `vaultspec-write`
skill reads the ADR and breaks the work into concrete, assignable steps.

**Invoke the skill:**

```text
/vaultspec-write
```

Reference the ADR:

> Write an implementation plan for [[2026-02-18-health-endpoint-adr]].

The agent produces:

```text
.vault/plan/2026-02-18-health-endpoint-phase1-plan.md
```

**Sample output:**

```markdown
---
tags:
  - "#plan"
  - "#health-endpoint"
date: "2026-02-18"
related:
  - "[[2026-02-18-health-endpoint-adr]]"
  - "[[2026-02-18-health-endpoint-research]]"
---

# `health-endpoint` `phase1` plan

Implement a `/health` liveness endpoint on the Starlette application,
returning `{"status": "ok", "version": "<semver>"}` with HTTP 200.

## Proposed Changes

Per [[2026-02-18-health-endpoint-adr]]:

- Add a `health_handler` async function in `src/server/routes.py`
- Register the route in the Starlette app factory
- Read version from `importlib.metadata.version("vaultspec")`
- Add a unit test in `tests/test_health.py`

## Tasks

- Task 1: Implement `health_handler` in `src/server/routes.py`
- Task 2: Register `/health` route in the app factory
- Task 3: Write unit test `tests/test_health.py`
- Task 4: Update `docs/api.md` with endpoint documentation

## Verification

Run `pytest tests/test_health.py -v` — all tests pass.
Manually `curl http://localhost:8000/health` and verify:

- Status code: `200`
- Body: `{"status": "ok", "version": "0.1.0"}`
```

> **Approval gate:** Review the plan and confirm you are happy with the scope
> before continuing. Once you approve, execution begins.

---

## 5. Execute

With an approved plan, you dispatch implementation sub-agents.
`vaultspec-execute` reads the plan and assigns each task to the appropriate
specialist agent.

**Invoke the skill:**

```text
/vaultspec-execute
```

Reference the plan:

> Execute [[2026-02-18-health-endpoint-phase1-plan]].

The orchestrator dispatches agents in sequence (or in parallel where tasks are
independent). Each task produces a step record:

```text
.vault/exec/2026-02-18-health-endpoint/
  2026-02-18-health-endpoint-phase1-step1-exec.md
  2026-02-18-health-endpoint-phase1-step2-exec.md
  2026-02-18-health-endpoint-phase1-step3-exec.md
  2026-02-18-health-endpoint-phase1-step4-exec.md
  2026-02-18-health-endpoint-phase1-summary.md
```

**Sample step record** (`step1-exec.md`):

```markdown
---
tags:
  - "#exec"
  - "#health-endpoint"
date: "2026-02-18"
related:
  - "[[2026-02-18-health-endpoint-phase1-plan]]"
---

# `health-endpoint` `phase1` `step1`

Implemented `health_handler` async function in `src/server/routes.py`.

- Modified: `[[src/server/routes.py]]`

## Description

Added an async handler that reads the package version via
`importlib.metadata.version("vaultspec")` and returns a `JSONResponse`
with `{"status": "ok", "version": version}`. Handles `PackageNotFoundError`
gracefully by falling back to `"unknown"`.

## Tests

No tests at this step — test coverage added in step 3. Static type check
(`ty check src/server/routes.py`) passes with zero errors.
```

Each sub-agent commits only to what is described in its assigned step. Agents
do not modify files outside their scope. The `vaultspec-code-reviewer` agent
automatically audits each step before marking it complete.

---

## 6. Verify

After execution, `vaultspec-review` performs a holistic audit of all changes
against the original ADR and plan.

**Invoke the skill:**

```text
/vaultspec-review
```

Reference the execution summary:

> Review the changes in [[2026-02-18-health-endpoint-phase1-summary]].

The reviewer checks:

- **Feature completeness** — does the implementation cover every task in
  the plan?
- **ADR compliance** — does the code match the decisions in the ADR?
- **Safety** — no panics, no unhandled exceptions, no exposed secrets
- **Test coverage** — tests exist and pass

The reviewer produces:

```text
.vault/exec/2026-02-18-health-endpoint/2026-02-18-health-endpoint-review.md
```

A clean review outputs **PASS**. If issues are found, the reviewer issues a
**REVISION REQUIRED** with specific findings, and you loop back to execute
the fixes before re-reviewing.

---

## What You've Built

After completing all five phases, your `.vault/` directory contains:

```text
.vault/
  research/
    2026-02-18-health-endpoint-research.md   # evidence gathered
  adr/
    2026-02-18-health-endpoint-adr.md        # decision recorded
  plan/
    2026-02-18-health-endpoint-phase1-plan.md  # work scoped
  exec/
    2026-02-18-health-endpoint/
      2026-02-18-health-endpoint-phase1-step1-exec.md
      2026-02-18-health-endpoint-phase1-step2-exec.md
      2026-02-18-health-endpoint-phase1-step3-exec.md
      2026-02-18-health-endpoint-phase1-step4-exec.md
      2026-02-18-health-endpoint-phase1-summary.md
      2026-02-18-health-endpoint-review.md   # audit trail closed
```

Every decision is traceable. Six months from now, a new contributor can open
`.vault/adr/2026-02-18-health-endpoint-adr.md` and understand exactly why
the endpoint was built the way it was — without reading git blame or hunting
through Slack.

---

## Next Steps

- Add a `/ready` deep-check endpoint following the same pipeline
- Explore the `vaultspec-reference` skill to audit how other projects
  implement health checks before writing your next ADR
- Read the [ADR template](.vaultspec/templates/ADR.md) to understand every
  frontmatter field
