---
tags:
  - '#exec'
  - '#claude-acp-multimodal'
date: '2026-02-21'
related:
  - '[[2026-02-21-acp-claude-multimodal-plan]]'
---

# Step Record: Multi-Modal Prompt Support Implementation

## Description

Implemented multi-modal support for the ACP Claude bridge. This allows the bridge to correctly handle images and embedded resources (files) in prompts, instead of flattening everything to text.

## Changes

### `src/vaultspec/protocol/acp/claude_bridge.py`

1. **Capability Advertisement**: Updated `initialize` to return `PromptCapabilities(image=True, embedded_context=True)`.
1. **Prompt Refactoring**:
   - Added `_build_sdk_message_payload`: Converts ACP content blocks (Text, Image, Resource) into a structured list of dictionaries compatible with the Claude SDK message format.
   - Added `_to_async_iter`: Helper to wrap the message payload in an async iterable, as required by `sdk_client.query()`.
   - Updated `prompt()`: Replaced `_extract_prompt_text` with the new payload builder and streaming execution path.
1. **Cleanups**: Removed the obsolete `_extract_prompt_text` function.

### `src/vaultspec/protocol/acp/tests/test_bridge_prompt.py`

- Added a new test suite covering:
  - Capability advertisement.
  - Construction of mixed-content payloads (text + image + resource).
  - Verification that `query()` receives the structured payload.

## Verification

- Run `pytest src/vaultspec/protocol/acp/tests/test_bridge_prompt.py` -> Passed (6 tests).
- Verified that `ResourceContentBlock` URIs are converted to `@path` references for the Claude CLI context.
- Verified that `ImageContentBlock` data is passed as base64 image blocks.

## Notes

- The implementation relies on `ClaudeSDKClient.query` accepting an `AsyncIterable[dict]`, which was confirmed via inspection in Phase 1.
- Protocol version in tests was clamped to `1` to satisfy schema constraints (`<= 65535`).
