---
tags:
  - "#exec"
  - "#claude-acp-multimodal"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-claude-multimodal-plan]]"
---
# Code Review: Multi-Modal Prompt Support

## 1. Summary

**Status:** **Pass**

The implementation correctly enables multi-modal support (images and resources) for the Claude ACP bridge. The code aligns with the plan and successfully replaces the previous lossy text extraction logic.

## 2. Findings

### 2.1. Safety & Robustness
*   `_build_sdk_message_payload` uses `getattr` or `hasattr` checks (`hasattr(block, "text")`, `getattr(block, "mime_type")`) effectively preventing crashes on malformed blocks.
*   The fallback to `image/jpeg` for images without a mime type is a reasonable default.
*   URI handling correctly strips `file://` prefix before converting to `@path`.

### 2.2. Intent Alignment
*   **Plan Goal:** Advertise capabilities. -> **Verified:** `initialize` sets `image=True` and `embedded_context=True`.
*   **Plan Goal:** Construct structured payload. -> **Verified:** `_build_sdk_message_payload` constructs a valid list of content dictionaries.
*   **Plan Goal:** Stream execution. -> **Verified:** `_to_async_iter` correctly wraps the payload for `sdk_client.query()`.

### 2.3. Quality & Tests
*   New tests in `test_bridge_prompt.py` provide good coverage of the prompt construction logic.
*   Mocking of `query` verifies that the structured payload is actually passed to the SDK.
*   Code style is consistent with the project.

## 3. Recommendations (Non-Blocking)

*   **Future Improvement:** If `ResourceContentBlock` supports remote URIs (http), the current logic assumes they are local file paths or passes the URI string directly. This is acceptable for now but could be refined.
*   **Future Improvement:** The text accumulation logic puts all text at the end. This is a simplification. Ideally, text and images would interleave exactly as provided in the input list. However, given `text_parts` accumulation, this is a known trade-off for cleaner code and is acceptable.

## 4. Conclusion

The changes are safe to merge and deploy.
