---
tags: ['#plan', '#vault-doctor-suite']
date: '2026-02-24'
related:
  - '[[2026-02-24-vault-doctor-suite-adr]]'
  - '[[2026-02-24-vault-doctor-suite-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p1-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p2-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p3-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p4-plan]]'
  - '[[2026-02-24-vault-doctor-suite-p5-plan]]'
---

# `vault-doctor-suite` P6 plan: Integration, Pre-commit Hooks, MCP Tool, and Docs

This phase is the integration and hardening layer. It runs the full check
suite against the real project vault (`test-project/.vault/` if present, else
the project's own `.vault/`), wires the two pre-commit hook entries, exposes
`vault_doctor` as an MCP tool in `src/vaultspec/mcp_server/vault_tools.py`,
and updates all documentation to remove `vault audit` references and describe
the new `vault doctor` interface.

Phase 6 is a strict dependent of Phases 1–5. All check domains must be
registered before the integration test can be meaningful.

## Proposed Changes

### Full suite integration test (`src/vaultspec/doctor/tests/test_suite.py`)

Runs `CheckRegistry.run(root_dir)` against the project's own `.vault/`
directory (the live vault used throughout development). Asserts:

- Runner completes without raising an exception.
- Return value is `list[DoctorResult]`.
- No `Severity.ERROR` results on the project vault in its committed state
  (i.e., the project vault is self-consistent with respect to all checks).

This is the highest-value integration test: if the project's own vault
triggers an ERROR, something is genuinely wrong.

### Pre-commit hooks (`.pre-commit-config.yaml`)

Two new hooks are added under the existing `local` repo block:

```yaml

- id: vault-doctor
  name: Vault Doctor (drift + structure)
  entry: uv run python -m vaultspec vault doctor --severity error
  language: system
  types: [markdown]
  pass_filenames: true

- id: vault-doctor-deep
  name: Vault Doctor (chain + links)
  entry: uv run python -m vaultspec vault doctor --category chain --category links --severity error
  language: system
  types: [markdown]
  pass_filenames: true
```

The existing `check-naming` hook (`vault audit --verify`) was removed in Phase
1 (P1-S6). This step adds the replacement hooks in Phase 6. Both are opt-in by
design — they are defined in `.pre-commit-config.yaml` so teams can enable them
in their own config.

### MCP tool (`src/vaultspec/mcp_server/vault_tools.py`)

`vault_tools.py` currently contains a stub `register_tools` function with no
implementations. This step implements `vault_doctor` as a FastMCP tool:

```python
async def vault_doctor(
    categories: list[str] | None = None,
    severity: str = "info",
    fix: bool = False,
    dry_run: bool = False,
    feature: str | None = None,
    input_paths: list[str] | None = None,
) -> list[dict]
```

Returns a list of serialised `DoctorResult` dicts matching the JSON output
format of `vault doctor --json`. Uses the `CheckRegistry` imported from
`src/vaultspec/doctor/registry.py`.

### Documentation updates

Four files require changes:

| File                               | Change                                                                                              |
| ---------------------------------- | --------------------------------------------------------------------------------------------------- |
| `.vaultspec/docs/cli-reference.md` | Remove `vault audit` section; add `vault doctor` full flag reference                                |
| `.vaultspec/docs/concepts.md`      | Add "Doctor Suite" concept section; describe check categories, severity model, and dry-run contract |
| `AGENTS.md`                        | Replace `vault audit` entry with `vault doctor`; note `--category`, `--fix`, `--dry-run`            |
| `vault_cli.py` module docstring    | Update command list: remove `audit`, add `doctor`                                                   |

## Tasks

- P6-S1: Full suite integration test in `test_suite.py` against project `.vault/`
- P6-S2: Add `vault-doctor` and `vault-doctor-deep` hooks to `.pre-commit-config.yaml`
- P6-S3: Implement `vault_doctor` MCP tool in `mcp_server/vault_tools.py`
- P6-S4: Update `cli-reference.md`, `concepts.md`, `AGENTS.md`, and `vault_cli.py` docstring

## Steps

- Name: Full suite integration test — `CheckRegistry.run()` against project `.vault/`; assert no ERRORs
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p6-s1-exec.md`
- Executing sub-agent: vaultspec-code-reviewer
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-plan]\], \[[2026-02-24-vault-doctor-suite-p2-plan]\], \[[2026-02-24-vault-doctor-suite-p3-plan]\], \[[2026-02-24-vault-doctor-suite-p4-plan]\], \[[2026-02-24-vault-doctor-suite-p5-plan]\]

______________________________________________________________________

- Name: Add `vault-doctor` and `vault-doctor-deep` pre-commit hooks to `.pre-commit-config.yaml`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p6-s2-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-plan]\]

______________________________________________________________________

- Name: Implement `vault_doctor` MCP tool in `mcp_server/vault_tools.py`
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p6-s3-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-p1-plan]\], \[[2026-02-24-vault-doctor-suite-plan]\]

______________________________________________________________________

- Name: Update docs — `cli-reference.md`, `concepts.md`, `AGENTS.md`, `vault_cli.py` docstring
- Step summary: `.vault/exec/2026-02-24-vault-doctor-suite/2026-02-24-vault-doctor-suite-p6-s4-exec.md`
- Executing sub-agent: vaultspec-standard-executor
- References: \[[2026-02-24-vault-doctor-suite-adr]\], \[[2026-02-24-vault-doctor-suite-plan]\]

## Parallelization

S1 is the correctness gate — run it first to confirm no regressions before
adding the hooks. S2, S3, and S4 are independent of each other and can run in
parallel once S1 passes.

## Verification

- `python -m pytest src/vaultspec/doctor/tests/test_suite.py -v` exits 0 with
  all tests passing.

- `CheckRegistry.run(root_dir=Path(".vault"))` on the project vault returns
  zero `Severity.ERROR` results.

- `.pre-commit-config.yaml` contains both `vault-doctor` and `vault-doctor-deep`
  hook entries with correct `entry`, `types: [markdown]`, and
  `pass_filenames: true`.

- `mcp_server/vault_tools.py` `register_tools` function registers at least
  one tool (`vault_doctor`) on the `FastMCP` instance.

- `vault_doctor(categories=["drift"], severity="info")` returns a valid JSON-
  serialisable list (tested via `json.dumps` on the return value).

- `vault_doctor(dry_run=True)` without `fix=True` raises or returns an error
  result — the dry-run guard from Phase 1 propagates through the MCP layer.

- `.vaultspec/docs/cli-reference.md` no longer contains a `vault audit`
  section; it contains a `vault doctor` section with the full flag table.

- `AGENTS.md` no longer references `vault audit` as an available tool.

- `vault_cli.py` module docstring lists `doctor` as a command and does not list
  `audit`.

- All existing tests (`graph/`, `verification/`, `hooks/`, `mcp_server/`) pass
  without regressions introduced by this phase.
