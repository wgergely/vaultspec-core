---
tags:
  - "#plan"
  - "#acp-claude-multimodal"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-claude-multimodal-adr.md]]"
  - "[[2026-02-21-acp-claude-prompt-audit-research.md]]"
---

# Implementation Plan: ACP Claude Multi-Modal Prompt Support

Enable multi-modal support (images and embedded resources) in the Claude ACP bridge, aligning with the ACP protocol and reference implementation.

## 1. Verification (Micro-Research)

Before coding, we must confirm the data structure expected by `ClaudeSDKClient.query()`.

*   **Task:** Inspect `claude_agent_sdk` (if source available) or write a script to inspect `ClaudeSDKClient.query` signature. We need to know if we can pass a list of dicts (the raw API message format) or if it enforces a string.
*   **Contingency:** If `query()` enforces string, we may need to bypass it or construct a `UserMessage` object if the SDK exposes one that `query` accepts.

## 2. Implementation

### 2.1. Advertise Capabilities
*   **File:** `src/vaultspec/protocol/acp/claude_bridge.py`
*   **Method:** `initialize`
*   **Change:** Update `prompt_capabilities` to include `image=True` and `embedded_context=True`.

### 2.2. Prompt Construction Logic
*   **File:** `src/vaultspec/protocol/acp/claude_bridge.py`
*   **New Method:** `_build_sdk_message_payload(prompt: list[ContentBlock]) -> Any`
    *   Iterate over input blocks.
    *   **Text:** Append text string.
    *   **Image:** Create dict: `{'type': 'image', 'source': {'type': 'base64', 'media_type': block.mime_type, 'data': block.data}}`.
    *   **Resource:** Extract URI. If `file://`, strip prefix and append `@path` to a text buffer.
    *   **Return:** A structure suitable for `sdk_client.query()`. Likely a list of content blocks (dicts) or a single string if that's all it supports (in which case we fail for images, but we'll know from Phase 1). Assuming SDK supports structured input: return the list.

### 2.3. Update Prompt Execution
*   **File:** `src/vaultspec/protocol/acp/claude_bridge.py`
*   **Method:** `prompt`
*   **Change:** Call `_build_sdk_message_payload` instead of `_extract_prompt_text`. Pass result to `sdk_client.query()`.

## 3. Testing

*   **File:** `src/vaultspec/protocol/acp/tests/test_bridge_streaming.py` (or new `test_bridge_prompt.py`)
*   **Test:** `test_prompt_construction_text_only`: Verify simple text behavior preserved.
*   **Test:** `test_prompt_construction_with_image`: Verify image block conversion.
*   **Test:** `test_prompt_construction_with_resource`: Verify `@path` conversion.
*   **Test:** `test_prompt_passes_structure_to_query`: Mock `sdk_client` and assert `query` receives the structured payload.

## Execution Order

1.  **Phase 1** (Verification)
2.  **Phase 2** (Implementation) & **Phase 3** (Testing) - Can be executed by `vaultspec-standard-executor`.
