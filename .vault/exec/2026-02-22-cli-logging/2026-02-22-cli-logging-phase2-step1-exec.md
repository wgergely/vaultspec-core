---
tags:
  - "#exec"
  - "#cli-logging"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-logging-plan]]"
---
# `cli-logging` phase-2 step-1

Phase 2: Agent feed formatting — restyle tool calls, thinking, and responses
in SubagentClient with Rich Console.

- Modified: `src/vaultspec/protocol/acp/client.py`

## Description

- Added `rich.console.Console` import and module-level `_console` instance
  (`stderr=True, highlight=False`)
- Tool calls: replaced `logger.info("[tool] %s (%s)", title, id)` with
  `_console.print(f"({update.title})", style="dim")` — dim text, no ID
- Agent messages: replaced `logger.info("[agent] %s", text)` with
  `_console.print(text, end="")` — no prefix, normal color
- Agent thinking: replaced `logger.debug("[thought] %s", text)` with
  `_console.print(text, style="italic", end="")` — no prefix, italic
- All guarded behind `not self.quiet` (unchanged)
- Callback short-circuits verified intact — when `on_message_chunk`,
  `on_thought_chunk`, `on_tool_update` are set, `_console.print()` is
  never reached

## Tests

- ACP protocol tests: 423 passed
- Callback passthrough verified by code inspection (no changes needed)
