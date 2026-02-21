"""Terminal sandbox tests for SubagentClient.

Covers: create_terminal read-only guard in SubagentClient.
"""

from __future__ import annotations

import shutil

import pytest

from tests.constants import TEST_PROJECT
from vaultspec.protocol.acp import SubagentClient

pytestmark = [pytest.mark.unit]


class TestCreateTerminalReadOnly:
    """Verify that create_terminal is blocked in read-only mode."""

    @pytest.mark.asyncio
    async def test_create_terminal_denied_readonly(self):
        """SubagentClient(mode='read-only').create_terminal() raises ValueError."""
        client = SubagentClient(root_dir=TEST_PROJECT, mode="read-only")
        with pytest.raises(ValueError):
            await client.create_terminal(
                command="bash",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skipif(
        not shutil.which("bash"),
        reason="bash not on PATH",
    )
    async def test_create_terminal_allowed_readwrite(self):
        """Terminal creation succeeds in read-write mode (requires bash on PATH)."""
        client = SubagentClient(root_dir=TEST_PROJECT, mode="read-write")
        try:
            await client.create_terminal(
                command="bash",
                session_id="test-session",
            )
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_create_terminal_denied_message_mentions_readonly(self):
        """Error message from denied terminal creation mentions 'read-only'."""
        client = SubagentClient(root_dir=TEST_PROJECT, mode="read-only")
        with pytest.raises(ValueError, match="read-only"):
            await client.create_terminal(
                command="ls",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    async def test_default_mode_is_readwrite(self):
        """SubagentClient defaults to read-write mode."""
        client = SubagentClient(root_dir=TEST_PROJECT)
        assert client.mode == "read-write"
