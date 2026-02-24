---
tags:
  - "#plan"
  - "#gemini-acp-bridge"
date: "2026-02-22"
related:
  - "[[2026-02-22-gemini-acp-bridge-adr]]"
  - "[[2026-02-21-claude-acp-bidirectional-adr]]"
---
# Plan: Gemini ACP Bridge Implementation

## Overview
Implement a dedicated ACP bridge for the Gemini provider to achieve feature parity with Claude's bidirectional ACP implementation. This includes session persistence, planning interception, and rich tool support.

## Objectives
1.  Create `src/vaultspec/protocol/acp/gemini_bridge.py` mirroring the architecture of `claude_bridge.py`.
2.  Update `GeminiProvider` to spawn the bridge instead of the raw CLI.
3.  Add rigorous test coverage for the new bridge.
4.  Enable session resume in `GeminiA2AExecutor`.

## Task Steps

### Phase 1: Bridge Foundation
- [ ] Create `src/vaultspec/protocol/acp/gemini_bridge.py`.
- [ ] Implement `GeminiACPBridge` class inheriting from `acp.Agent`.
- [ ] Implement `initialize()` to advertise capabilities (session fork/list/resume).
- [ ] Implement `new_session()` to spawn `gemini --experimental-acp` in a subprocess.

### Phase 2: Protocol Normalization
- [ ] Implement `prompt()` to proxy messages between the bridge and the `gemini` subprocess.
- [ ] Implement `_emit_updates()` to normalize the incoming ACP stream from Gemini.
- [ ] Implement `TodoWrite` (or equivalent) interception to emit `AgentPlanUpdate`.
- [ ] Implement `ToolKind` mapping and `tool_call_contents` accumulation for diffs.

### Phase 3: Session Management
- [ ] Implement `_SessionState` to track `gemini_session_id` (if exposed by CLI) or handle context persistence.
- [ ] Implement `load_session()` and `resume_session()` logic.
- [ ] Implement non-destructive `cancel()` (interrupt the subprocess but keep it alive).

### Phase 4: Provider & Executor Integration
- [ ] Update `src/vaultspec/protocol/providers/gemini.py` to spawn the bridge in `prepare_process`.
- [ ] Update `src/vaultspec/protocol/a2a/executors/gemini_executor.py` to support `resume` via `context_id`.

### Phase 5: Verification
- [ ] Create `src/vaultspec/protocol/acp/tests/test_gemini_bridge.py` mirroring `test_bridge_*.py` for Claude.
- [ ] Run `pytest src/vaultspec/protocol/acp/tests/test_gemini_bridge.py`.
- [ ] Verify multi-turn interaction via `subagent_cli.py run -i -p gemini`.
- [ ] Verify A2A relay with `test_french_novel_relay.py`.

## Verification Strategy
- **Unit Tests**: Test the bridge logic using DI-injected recorders (no CLI dependency).
- **Integration Tests**: Test with a real `gemini` CLI subprocess.
- **E2E Tests**: Verify the full subagent lifecycle and A2A team coordination.
