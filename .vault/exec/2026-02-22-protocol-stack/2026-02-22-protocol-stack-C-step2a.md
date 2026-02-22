---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
---

# `protocol-stack` Track C `Step 2a`

Added 6 missing CLI flags to close the CLI/backend parity gap.

- Modified: `src/vaultspec/subagent_cli.py`

## Description

Added `--resume-session`, `--max-turns`, `--budget`, `--effort`,
`--output-format`, and `--mcp-servers` arguments to `run_parser`. Updated
`command_run()` to parse `--mcp-servers` as JSON and pass all 6 new params
to `run_subagent()`. Added `import json` to support MCP servers parsing.

All 6 parameters were already accepted by `run_subagent()` at
`src/vaultspec/orchestration/subagent.py:199-220`.

## Tests

Verified `run_subagent()` signature accepts all params. CLI argument
definitions follow existing patterns (type, choices, defaults).
