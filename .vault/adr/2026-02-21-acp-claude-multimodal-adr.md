---
tags:
  - "#adr"
  - "#acp-claude-multimodal"
date: "2026-02-21"
related:
  - "[[2026-02-21-claude-sdk-query-signature-research]]"
  - "[[2026-02-21-acp-claude-prompt-audit-research]]"
---
# ACP Claude Multi-Modal Prompt Support | (**status:** `proposed`)

## Context

The current `claude_bridge.py` implementation in `src/vaultspec` flattens all prompts to a single text string via `_extract_prompt_text`. This explicitly ignores `ImageContentBlock` (containing base64 data) and `ResourceContentBlock` (containing file URIs).

The ACP protocol and the reference implementation (`acp-claude-code`) support multi-modal inputs. The reference implementation:
1.  Advertises `image: true` and `embeddedContext: true` in `initialize`.
2.  Constructs a `UserMessage` with a mix of text and image blocks.
3.  Converts resource URIs (e.g., `file:///foo`) into text pointers (e.g., `@/foo`) which the Claude CLI understands.

Our bridge's failure to handle these results in data loss: users dragging images or files into the chat see them "sent", but the agent receives only the text portion of their message.

## Decision

We will upgrade the `ClaudeACPBridge` to support multi-modal prompts by implementing the following changes:

1.  **Advertise Capabilities**: Update `initialize()` to return `PromptCapabilities(image=True, embedded_context=True)`.

2.  **Refactor Prompt Construction**: Replace `_extract_prompt_text` with `_build_sdk_message_content(prompt)`. This function will iterate over the ACP content blocks and produce a list of blocks suitable for the Claude SDK:
    *   **Text**: Pass through as text.
    *   **Images**: Convert ACP `ImageContentBlock` (mime_type, data) to the SDK's expected image dictionary format `{type: "image", source: {type: "base64", media_type: ..., data: ...}}`.
    *   **Resources**: Convert ACP `ResourceContentBlock` (uri) to a text string `@<path>` (stripping `file://` prefix) and append it to the text content. This matches the behavior of the reference implementation which relies on the underlying Claude CLI to parse `@path` references.

3.  **Update Prompt Execution**: In `prompt()`, verify if `sdk_client.query()` accepts a structured message list. If the Python SDK `query()` wrapper expects a string, we may need to bypass it or construct a `UserMessage` object if supported. *Verification*: The Python SDK `ClaudeSDKClient.query` typically sends the argument as the user message. We need to ensure we pass the structured content correctly.

## Consequences

**Positive:**
*   Users can send images to Claude via ACP.
*   Users can reference files using drag-and-drop (ACP resources), which will be correctly interpreted by Claude as context.
*   Parity with the reference `acp-claude-code` implementation is achieved.

**Negative:**
*   Slight increase in complexity in `claude_bridge.py`.
*   Dependency on Claude CLI's `@path` parsing behavior for resources (which is standard for Claude Code but implicit).

## Compliance

*   **Tags**: `#adr`, `#acp-claude-multimodal`
*   **Related**: `[[2026-02-21-acp-claude-prompt-audit-research]]`
