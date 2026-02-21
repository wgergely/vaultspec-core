---
tags: ["#exec", "#claude-acp-multimodal"]
related: ["[[2026-02-21-acp-claude-multimodal-plan.md]]"]
date: 2026-02-21
---

# Phase Summary: Multi-Modal Prompt Support

## Overview

Successfully implemented multi-modal prompt support for the Claude ACP bridge. This feature allows users to send images and use file references (via drag-and-drop resources) in their conversations with the Claude agent.

## Completed Work

1.  **Capability Advertisement:**
    *   Updated `initialize()` to advertise `image` and `embedded_context` support.
2.  **Prompt Payload Construction:**
    *   Replaced the lossy `_extract_prompt_text` function with `_build_sdk_message_payload`.
    *   Implemented mapping for `ImageContentBlock` (to base64 image dicts) and `ResourceContentBlock` (to `@path` text references).
3.  **Execution Path:**
    *   Updated `prompt()` to pass a structured async iterable of messages to the SDK, bypassing the simple string check.
4.  **Testing:**
    *   Created `src/vaultspec/protocol/acp/tests/test_bridge_prompt.py`.
    *   Verified all 6 tests pass.

## Outcome

The bridge now has feature parity with the reference implementation regarding prompt handling. Images are preserved, and local file resources are correctly interpreted as context pointers for the Claude CLI.

## Next Steps

*   None. This task is complete.
