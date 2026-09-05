---
tags:
  - '#audit'
  - '#scaffold-tag-validation'
date: '2026-09-05'
modified: '2026-09-05'
body_schema: 'body-v2'
body_hash: 'sha256:ba8460db4905d72dcb3229120c72aef781d02cfdf3d162fd2c9542700dc53cac'
related: []
---
# `scaffold-tag-validation` audit: `Creation tag validation`

## Scope

Review the shared creation guard in `src/vaultspec_core/vaultcore/hydration.py`, its CLI and MCP callers, their reference descriptions, and the shipped template tag instructions. This enforces the existing two-tag taxonomy; it does not change the taxonomy or validate arbitrary custom templates. Code review found no blocking findings.

## Findings

### invalid-tag-write | high | Unsupported tags were written before validation

Resolved. The shared creator rejects supplied tags outside the required directory and feature pair before template lookup or filesystem writes. Repeated required tags are discarded without changing the caller's fields. Regression tests compare file bytes and paths across failed creation, overwrite, and preview attempts. CLI text and JSON errors use the existing domain-error handler; MCP reports an item failure without creating its document or index.

Nine shared-creation regression cases failed before implementation. Four CLI cases and the MCP case independently failed because creation reported success. The first implementation exposed a plain-ValueError reporting problem in all four JSON cases; using the existing domain error corrected it. The final suite passed 84 tests across `vaultcore/tests/test_resolve.py`, `tests/cli/test_vault_cli.py`, and `mcp_server/tests/test_create_tool.py` in 208.60 seconds. Ruff and focused ty checks passed. Tests used real temporary files and the in-memory MCP transport, without mocking the creation guard.

### read-migration | high | A read request triggered an unrelated migration

Open, tracked separately as GitHub issue 443. The attempt to read architecture grounding through MCP find removed 47 tracked summaries via the execution-ledger migration. All 47 were restored from HEAD; no tracked migration changes remain. Runtime cache or manifest effects may remain. Further graph-backed reads and the full live-vault check were withheld to avoid repeating that mutation. This audit's metadata was validated by the owning creation command; no claim of a completed full-vault check is made.

## Recommendations

Merge the tag guard and its reference corrections. The published version is still 0.1.73, so public documentation must mark the corrected behavior as unreleased. Resolve the read-triggered migration before using that path for read-only verification. The shared local environment has inconsistent pydantic-core installation metadata; verification used a frozen isolated environment instead of modifying it.
