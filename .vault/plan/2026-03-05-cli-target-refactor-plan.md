---
tags:
  - '#plan'
  - '#cli-architecture'
date: 2026-03-05
related:
  - '[[2026-03-05-cli-path-resolution-adr]]'
  - '[[2026-03-05-cli-engine-typer-adr]]'
  - '[[2026-03-05-cli-architecture-audit]]'
  - '[[2026-03-23-cli-architecture-research]]'
---

# `cli-target-refactor` plan

Migrate the `vaultspec` CLI from `argparse` to `Typer` + `Rich`, deprecating split paths (`--root`/`--content-dir`) in favor of a unified `--target` architecture.

## Context

As discovered in the extensive `2026-03-05-cli-architecture-audit`, the current `argparse` implementation is fundamentally broken regarding global flag inheritance, `--help` intercepts, and `sys.argv` routing. Furthermore, the `agent-removal` plan has stripped out the sub-agent tools, meaning the surviving CLI commands (`vault`, `rules`, `hooks`, `doctor`, `mcp`, `sync`) must be stabilized.

This plan implements both the path resolution overhaul (`2026-03-05-cli-path-resolution-adr`) and the underlying engine replacement (`2026-03-05-cli-engine-typer-adr`).

## Prerequisite Blocker

The repository is currently broken. `agent-removal` deleted `AGENTS_SRC_DIR` but left hanging imports in `src/vaultspec/core/__init__.py`, preventing the CLI from booting.
**Phase 0 MUST fix the `core/__init__.py` ImportError before proceeding.**

## Tasks

- Phase 0: Un-brick the Repository

  - Name: Fix hanging imports from agent-removal
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase0-step1.md`
  - Executing sub-agent: `vaultspec-simple-executor`
  - Description: Remove `AGENTS_SRC_DIR` from `src/vaultspec/core/__init__.py` and fix any other `ImportError` crashes preventing `uv run vaultspec` from executing.

- Phase 1: Config Layer Overhaul

  - Name: Refactor WorkspaceLayout to Target paradigm
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase1-step1.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - Description: Update `WorkspaceLayout` dataclass in `src/vaultspec/config/workspace.py` to use `target_dir`, `vault_dir`, `vaultspec_dir`. Ensure `resolve_workspace()` eagerly resolves the target path to prevent traversal bugs. Drop the legacy `Path` fallback in `init_paths()`.
  - Name: Update Config Registry
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase1-step2.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - Description: Delete `VAULTSPEC_ROOT_DIR` and `VAULTSPEC_CONTENT_DIR` from `src/vaultspec/config/config.py` in favor of `VAULTSPEC_TARGET_DIR`.

- Phase 2: Typer Engine Bootstrap

  - Name: Install Typer and build master cli.py
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase2-step1.md`
  - Executing sub-agent: `vaultspec-complex-executor`
  - Description: Add `typer>=0.12.0` to `pyproject.toml`. Create `src/vaultspec/cli.py` containing the master `@typer.Typer()` app and a global callback that parses `--target`, `--verbose`, and `--debug`. It must instantiate `WorkspaceLayout`, load the singleton config, and inject it via `ctx.obj`.
  - Name: Unify Logging
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase2-step2.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - Description: Replace the contents of `src/vaultspec/logging_config.py` to strictly use `rich.logging.RichHandler`. Remove the idempotency locks and allow the Typer callback to dictate the global log level.

- Phase 3: Subcommand Porting, IO Governance & Type Stripping

  - Name: Refactor core function signatures
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase3-step1.md`
  - Executing sub-agent: `vaultspec-complex-executor`
  - Description: Remove `args: argparse.Namespace` from all functions in `src/vaultspec/core/`. Replace with native Python kwargs. Pass `cfg: VaultSpecConfig` down explicitly. Convert `sys.exit()` to `raise typer.Exit()`.
  - Name: IO Purge and Printer Deprecation
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase3-step2.md`
  - Executing sub-agent: `vaultspec-complex-executor`
  - Description: Delete `src/vaultspec/printer.py`. Run global replacements across `core/` to change `print(...)` and `printer.out(...)` to `typer.echo` or `rich.print`. Map `out_json` to `typer.echo(json.dumps())`.
  - Name: Port subcommands to Typer
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase3-step3.md`
  - Executing sub-agent: `vaultspec-complex-executor`
  - Description: Rewrite `vault_cli.py`, `spec_cli.py`, `hooks_cli.py`, and `mcp_server/app.py` as Typer command groups. Update `__main__.py` to point to the new Typer `app()`. Ensure `mcp` command forces `RichHandler` to output ONLY to `sys.stderr` to protect JSON-RPC. Use `vaultspec.cli_common.run_async()` for async commands, do NOT use `async def` on Typer endpoints.

- Phase 4: Initialization Upgrade & Hooks Isolation

  - Name: Fix init scaffold loops
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase4-step1.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - Description: Update `init_run` to accept `--providers`. Force `init_run` to call `reset_config()` and re-resolve the workspace *after* writing the `framework.md` file, so it doesn't read stale configuration data when scaffolding the provider directories.
  - Name: Secure Hook execution context
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase4-step2.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - Description: Update `src/vaultspec/hooks/engine.py` to clone `os.environ`, inject `VAULTSPEC_TARGET_DIR`, and pass `cwd=TARGET_DIR` into `subprocess.Popen`.

- Phase 5: Test Suite Migration

  - Name: Migrate to CliRunner
  - Step summary: `.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase5-step1.md`
  - Executing sub-agent: `vaultspec-complex-executor`
  - Description: Delete `test_printer.py`. Replace `subprocess.run(sys.executable...)` in `tests/cli/conftest.py` with `typer.testing.CliRunner`. Run global search/replace for `--root` -> `--target` across the test suite.

## Verification

1. Run `uv run vaultspec --target /tmp/test-workspace init --providers=all` and verify the terminal displays Rich-formatted success output.
1. Verify `/tmp/test-workspace/.vaultspec/rules/system/framework.md` and `/tmp/test-workspace/.gemini/rules/` exist.
1. Run `uv run vaultspec doctor --target /tmp/test-workspace` and verify the new "Workspace Root: /tmp/test-workspace" diagnostic appears.
1. Run `uv run pytest` and confirm all tests pass using the new `CliRunner` architecture.
1. Run `uv run vaultspec mcp --target /tmp/test-workspace` and verify zero logs leak to `stdout`.
