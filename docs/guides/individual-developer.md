# Getting Started as a Solo Developer

You adopted an AI coding agent to move faster. It worked — until you tried
to explain to a future version of yourself why a module was structured the
way it was. There was no document. There was no decision record. There was
only the code, and the code no longer made sense.

This is the context problem. AI agents write code fast, but they have no
persistent memory. Every session starts from scratch. Without a document trail,
each session is disconnected from the ones before it. Decisions get
re-derived, architectures drift, and the codebase gradually becomes
something no one — human or AI — can confidently reason about.

vaultspec fixes this by building a `.vault/` knowledge base alongside your
code: research documents, Architecture Decision Records, implementation plans,
and execution logs that accumulate across sessions and give your next session
(and your next self) the context it needs.

## What You Get

- A personal audit trail that explains *why* decisions were made
- Decision rationale preserved across AI sessions
- A searchable vault of your own technical reasoning
- Governance without a team — enforced by the pipeline itself

## Quick Start Path

### Step 1: Install

```bash
git clone https://github.com/wgergely/vaultspec
cd vaultspec
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -e ".[dev]" --extra-index-url https://download.pytorch.org/whl/cu130
```

> **No NVIDIA GPU?** Install without `[rag]` extras and skip the index step.
> Research, ADRs, plans, and execution all work without a GPU. Only the
> semantic search feature requires one.

```bash
pip install -e ".[dev]"
```

### Step 2: Run the doctor

```bash
python .vaultspec/lib/scripts/cli.py doctor
```

The `doctor` command verifies your installation and reports any missing
dependencies. Fix anything flagged before continuing.

### Step 3: Start your first research session

Open your project in Claude Code or Gemini CLI. Then:

```text
Activate vaultspec-research to investigate [the problem you're solving].
```

The research agent will explore the problem space and persist findings to
`.vault/research/`. This is the grounding step that prevents your AI agent
from hallucinating a solution.

### Step 4: Create your first ADR

After reviewing the research findings:

```text
Activate vaultspec-adr to formalize the decision on [topic].
```

The ADR captures what you decided, why, and what alternatives you rejected.
It lives in `.vault/adr/` and becomes the binding document for all
subsequent implementation.

### Step 5: Plan and execute

```text
Activate vaultspec-write to create an implementation plan for [feature].
```

Review the generated plan, approve it, then:

```text
Activate vaultspec-execute to implement the plan.
```

A review runs automatically after execution. Nothing is marked complete until
it passes.

## The GPU Escape Hatch

Search requires an NVIDIA GPU with CUDA 13.0+. All other features — research,
ADRs, plans, execution, review — work without one.

If you don't have a compatible GPU, skip `[rag]` in your install command and
skip `python .vaultspec/lib/scripts/docs.py index`. You can still use the
full governed pipeline; you just won't have semantic search over your vault.

## What Ends Up in Your Vault

After a few features, your `.vault/` directory will contain:

```text
.vault/
  research/   # What you investigated and found
  adr/        # What you decided and why
  plan/       # How you planned to implement it
  exec/       # What was actually done, step by step
```

This is your technical memory. Commit it to version control. Future sessions
— and future you — will thank you for it.

## Further Reading

- [Getting Started](../getting-started.md) — full setup walkthrough
- [Concepts](../concepts.md) — SDD methodology and the pipeline in depth
- [CLI Reference](../cli-reference.md) — all available commands
- [Search Guide](../search-guide.md) — semantic search over your vault
