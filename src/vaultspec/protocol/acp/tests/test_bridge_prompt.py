"""Tests for prompt handling in ClaudeACPBridge.

Covers:
- Prompt capabilities advertisement.
- Prompt payload construction (Text, Image, Resource).
- Query execution with structured payload.
"""

from __future__ import annotations

import pytest
from acp.schema import (
    ImageContentBlock,
    InitializeRequest,
    ResourceContentBlock,
    TextContentBlock,
)

from tests.constants import TEST_PROJECT

from ..claude_bridge import _build_sdk_message_payload
from .conftest import (
    SDKClientRecorder,
    make_di_bridge,
    make_test_conn,
)

pytestmark = [pytest.mark.unit]


class TestPromptCapabilities:
    """Test advertisement of prompt capabilities."""

    @pytest.mark.asyncio
    async def test_initialize_advertises_capabilities(self):
        """initialize() returns prompt_capabilities with image and embedded_context."""
        bridge, _holder, _captured = make_di_bridge()

        request = InitializeRequest(protocol_version=1)
        response = await bridge.initialize(**request.model_dump())

        caps = response.agent_capabilities.prompt_capabilities
        assert caps.image is True
        assert caps.embedded_context is True


class TestPromptConstruction:
    """Test _build_sdk_message_payload logic."""

    def test_text_only(self):
        """Text blocks are concatenated into a single text block."""
        blocks = [
            TextContentBlock(type="text", text="Hello"),
            TextContentBlock(type="text", text="World"),
        ]
        payload = _build_sdk_message_payload(blocks)

        assert payload["type"] == "user"
        content = payload["message"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Hello\nWorld"

    def test_image_block(self):
        """Image blocks are converted to SDK image dicts."""
        blocks = [
            ImageContentBlock(type="image", data="base64data", mime_type="image/png")
        ]
        payload = _build_sdk_message_payload(blocks)

        content = payload["message"]["content"]
        assert len(content) == 1
        img = content[0]
        assert img["type"] == "image"
        assert img["source"]["type"] == "base64"
        assert img["source"]["media_type"] == "image/png"
        assert img["source"]["data"] == "base64data"

    def test_resource_block(self):
        """Resource blocks are converted to @path text references."""
        blocks = [
            TextContentBlock(type="text", text="Look at this:"),
            ResourceContentBlock(
                type="resource_link", uri="file:///path/to/file.txt", name="file.txt"
            ),
        ]
        payload = _build_sdk_message_payload(blocks)

        # Should be merged into one text block
        content = payload["message"]["content"]
        assert len(content) == 1
        text_content = content[0]["text"]
        assert "Look at this:" in text_content
        assert "@/path/to/file.txt" in text_content

    def test_mixed_content(self):
        """Mixed text, image, and resource are handled correctly."""
        blocks = [
            TextContentBlock(type="text", text="See image:"),
            ImageContentBlock(type="image", data="img", mime_type="image/jpeg"),
            ResourceContentBlock(
                type="resource_link", uri="file:///foo.txt", name="foo"
            ),
        ]
        payload = _build_sdk_message_payload(blocks)

        content = payload["message"]["content"]
        assert len(content) == 2

        # Image comes first
        assert content[0]["type"] == "image"

        # Text comes last
        text_block = content[1]
        assert text_block["type"] == "text"
        assert "See image:" in text_block["text"]
        assert "@/foo.txt" in text_block["text"]


class TestPromptExecution:
    """Test prompt() execution flow."""

    @pytest.mark.asyncio
    async def test_prompt_passes_structured_payload(self):
        """prompt() passes a structured dict (via async iter) to query()."""
        test_client = SDKClientRecorder()

        # Capture what query receives
        captured_payloads = []

        async def _mock_query(prompt_stream):
            async for msg in prompt_stream:
                captured_payloads.append(msg)
            return True  # Skip default recording

        test_client._query_hook = _mock_query

        bridge, _holder, _captured = make_di_bridge(client=test_client)
        bridge.on_connect(make_test_conn())
        await bridge.new_session(cwd=str(TEST_PROJECT))

        blocks = [TextContentBlock(type="text", text="test")]
        await bridge.prompt(prompt=blocks, session_id="s1")

        assert len(captured_payloads) == 1
        msg = captured_payloads[0]
        assert msg["type"] == "user"
        assert msg["message"]["content"][0]["text"] == "test"
