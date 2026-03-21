---
tags:
  - '#audit'
  - '#feature-documentation'
date: '2026-03-21'
related:
  - '[[2026-03-16-cli-restructure-plan]]'
  - '[[2026-03-21-builtins-build-strategy-adr]]'
---

# cli-release-readiness Code Review

<!-- Persistent log of audit findings appended below. -->

<!-- Use: {TOPIC}-### | {LEVEL} | {Summary} \n {DESCRIPTION} format-->

## Justfile Platform & UX

J-01 | HIGH | `npx --yes` downloads unpinned tools on every CI run
Lines 129, 131, 163, 165: `npx --yes @taplo/cli` and `npx --yes markdownlint-cli` resolve to `latest` with no version pin. Supply-chain risk and non-reproducible builds. No Docker fallback unlike lychee/actionlint.

J-02 | HIGH | `just dev publish` missing args gives raw just error, not usage hint
Line 229: `_dev-publish target tag` requires two positional args. Missing either gives an opaque just-level argument count error, not a helpful "Usage: just dev publish docker-ghcr <tag>" message. Foot-gun for release operations.

J-03 | MEDIUM | `$PWD` in Docker volume mounts may break on native Windows
Lines 120, 138: `-v "$PWD:/repo"` produces Windows-style paths. Git Bash usually translates but MSYS_NO_PATHCONV suppresses it. `$(pwd)` on lines 129, 163 has same risk.

J-04 | MEDIUM | `just dev` with no target gives just-level error, not help
Line 55: `target` is required positional. Bare `just dev` shows "got 0 arguments but takes at least 1" instead of listing targets.

J-05 | MEDIUM | `prod` and `dev` recipes lack `--list`-visible descriptions
Lines 25, 55: Block comments not picked up by `just --list`. Only `ci` has a single-line `#` comment.

J-06 | MEDIUM | CI runs Docker test unconditionally
Line 87: `just dev test all` includes `_dev-test docker` which requires Docker. No way to skip for Docker-less CI.

J-07 | MEDIUM | No tag format validation for publish
Line 233: `{{tag}}` interpolated directly into docker tag with no semver/format check.

J-08 | LOW | Inconsistent tool resolution - npx-only vs command-v-then-docker
Taplo/markdownlint are npx-only. Lychee/actionlint have `command -v || docker` pattern. Inconsistent.

J-09 | LOW | Missing `TMP` fallback in temp dir chain
Line 184: `${TMPDIR:-${TEMP:-/tmp}}` - missing `TMP` which some Windows envs set.

J-10 | LOW | No `clean` recipe for build artifacts

## CLI Help & Error UX

CLU-01 | HIGH | Provider arguments (`install`, `uninstall`, `sync`) accept arbitrary strings without validation
`root.py:112-115, 232-235, 329-331`: Invalid provider names like `vaultspec-core install foobar` are not rejected at the CLI level. Validation presumably happens deeper but may produce confusing errors.

CLU-02 | MEDIUM | `vault add` validation errors use Rich markup instead of `Error:` prefix
`vault_cmd.py:107-182`: All `vault add` validation paths use `console.print("[red]...[/red]")` while `root.py` and `_errors.py` use `typer.echo("Error: ...", err=True)`. Inconsistent error formatting.

CLU-03 | MEDIUM | `uninstall` without `--force` gives misleading "Nothing to remove" message
`root.py:324`: When `--force` is omitted, the message says vaultspec is not installed rather than "Use --force to confirm".

CLU-04 | MEDIUM | `spec rules/skills/agents add` print no confirmation on success
`spec_cmd.py:86-89, 273-276, 461-464`: After successful add, no output is printed. Contrast with `vault add` which prints "Created: {path}".

CLU-05 | MEDIUM | `vault add --date` accepts arbitrary strings without format validation
`vault_cmd.py:57-59`: No check that date matches YYYY-MM-DD. Malformed dates produce malformed filenames.

CLU-06 | MEDIUM | Mixed error output mechanisms across commands
Three patterns: `_handle_error(exc)`, `console.print("[red]...")`, and direct `typer.echo`. Inconsistent user experience.

CLU-07 | MEDIUM | `zip(labels, results, strict=True)` in sync can crash
`root.py:423`: Hardcoded 5 labels vs dynamic results count. If provider returns different count, unhandled `ValueError` traceback.

CLU-08 | LOW | `vault feature archive` has no `--dry-run` or `--force` guard
`vault_cmd.py:702-720`: Destructive operation (moves files) with no safety mechanism.

CLU-09 | LOW | `vault check structure` lacks `--feature` option unlike sibling checks
`vault_cmd.py:643-659`: Inconsistent filter surface across check subcommands.

CLU-10 | LOW | `spec hooks run` does not document valid event names in `--help`
`spec_cmd.py:718`: Only CLI.md documents the events; CLI `--help` has no hint.

CLU-11 | LOW | `vault add` DOC_TYPE valid values listed in docstring body, not argument help
`vault_cmd.py:53,81-83`: Typer renders argument `help=` more prominently than docstring body.

## Release Readiness

CLI-01 | HIGH | No top-level exception handler for unexpected errors
`root.py:491-493`, `__main__.py:11-12`: `app()` called with no try/except. Uncaught `OSError`, `PermissionError`, etc. produce raw tracebacks to users.

CLI-02 | MEDIUM | Mixed `typer.echo` / Rich `console.print` across CLI
~18 `typer.echo()` calls bypass Rich. `_errors.py` handles all `VaultSpecError` via `typer.echo`, meaning error messages skip the Windows UTF-8 safety built into `console.py`.

CLI-03 | MEDIUM | Return codes not set for warning scenarios
Commands with sync warnings (`root.py:427-436`) still exit 0. CI pipelines have no way to detect non-clean syncs.

CLI-04 | MEDIUM | MCP entry point imports full Typer framework
`mcp_server/app.py:17`: `vaultspec-mcp` pulls in Typer even though the MCP server does not need CLI infrastructure. Unnecessary startup latency.

CLI-05 | LOW | No `--quiet` flag at root level
Only `--debug` is exposed. No way to suppress informational output.

CLI-06 | LOW | Heavy runtime deps include MCP server stack even for CLI-only users
`pyproject.toml:17-29`: `httpx`, `mcp`, `pydantic`, `starlette`, `uvicorn` always installed. No `extras` split.

CLI-07 | LOW | Duplicate `dev` deps in both `optional-dependencies` and `dependency-groups`
`pyproject.toml:55-83`: Redundant definition that can drift apart.

CLI-08 | LOW | `get_version` fallback line-scans pyproject.toml fragily
`cli_common.py:53-55`: `line.split("=", 1)` could match wrong `version` keys.

CLI-09 | LOW | CI only tests Python 3.13, no 3.14 matrix
`.github/workflows/ci.yml:96`: No forward-compat testing.
