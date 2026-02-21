---
tags: ["#research", "#acp-claude-audit"]
related: ["[[2026-02-21-acp-claude-audit-research.md]]"]
date: 2026-02-21
---

# ACP Claude Prompt Handling Audit

## 1. Executive Summary

A targeted audit of `src/vaultspec/protocol/acp/claude_bridge.py` reveals that the implementation **drops all images and resource links** from prompts. It flattens the input to a single text string, ignoring non-text blocks. This contrasts with `tmp-ref/acp-claude-code`, which fully supports multi-modal inputs.

## 2. Findings

### 2.1. Dropped Content (Images & Resources)

*   **Current Code (`claude_bridge.py`):**
    ```python
    def _extract_prompt_text(prompt):
        parts = []
        for block in prompt:
            if isinstance(block, TextContentBlock):
                parts.append(block.text)
            elif hasattr(block, "text"):
                parts.append(str(block.text))
        return "
".join(parts)
    ```
    This function iterates through the ACP prompt blocks but **explicitly ignores** `ImageContentBlock` (which has `data`, not `text`) and `ResourceContentBlock` (which has `uri`).

*   **Reference (`agent.ts`):**
    Iterates blocks and constructs a complex `UserMessage`:
    *   **Images:** Converted to `{type: "image", source: {type: "base64", ...}}`.
    *   **Resources:** URIs are converted to text pointers (e.g., `file://foo` -> `@foo`).

### 2.2. Flattened Prompt Execution

*   **Current Code:**
    ```python
    prompt_text = _extract_prompt_text(prompt)
    await sdk_client.query(prompt_text)
    ```
    The `sdk_client.query()` method in the Python SDK *can* accept a string or a list of messages. However, `claude_bridge.py` forces it to be a string.

### 2.3. Missing Capabilities Advertisement

*   **Current Code (`initialize`):**
    Returns `AgentCapabilities(load_session=True, session_capabilities=...)`.
    It does **not** set `prompt_capabilities`.
*   **Reference:**
    Sets `promptCapabilities: { image: true, audio: false, embeddedContext: true }`.

## 3. Recommendations

1.  **Update `initialize`:** Advertise `image` and `embedded_context` support.
2.  **Refactor `prompt`:**
    *   Do not flatten to string.
    *   Construct a proper `UserMessage` payload for the SDK.
    *   Map ACP `ImageContentBlock` to SDK image blocks.
    *   Map ACP `ResourceContentBlock` to text pointers (or SDK resource blocks if supported).
3.  **Update `_extract_prompt_text`:** Deprecate or replace with a `_convert_prompt_to_sdk_message` function.
