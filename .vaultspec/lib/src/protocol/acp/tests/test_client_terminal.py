"""Terminal sandbox tests for SubagentClient.

Covers: create_terminal read-only guard in SubagentClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from protocol.acp.client import SubagentClient

pytestmark = [pytest.mark.unit]


class TestCreateTerminalReadOnly:
    """Verify that create_terminal is blocked in read-only mode."""

    @pytest.mark.asyncio
    async def test_create_terminal_denied_readonly(self, tmp_path):
        """SubagentClient(mode='read-only').create_terminal() raises ValueError."""
        client = SubagentClient(root_dir=tmp_path, mode="read-only")
        with pytest.raises(ValueError):
            await client.create_terminal(
                command="bash",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    async def test_create_terminal_allowed_readwrite(self, tmp_path):
        """Terminal creation succeeds in read-write mode (subprocess mocked)."""
        client = SubagentClient(root_dir=tmp_path, mode="read-write")

        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.read = AsyncMock(return_value=b"")
        mock_proc.returncode = None

        with patch(
            "protocol.acp.client.asyncio.create_subprocess_exec", return_value=mock_proc
        ):
            response = await client.create_terminal(
                command="echo",
                session_id="test-session",
                args=["hello"],
            )
        assert response.terminal_id is not None
        assert len(response.terminal_id) > 0

    @pytest.mark.asyncio
    async def test_create_terminal_denied_message_mentions_readonly(self, tmp_path):
        """Error message from denied terminal creation mentions 'read-only'."""
        client = SubagentClient(root_dir=tmp_path, mode="read-only")
        with pytest.raises(ValueError, match="read-only"):
            await client.create_terminal(
                command="ls",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    async def test_default_mode_is_readwrite(self, tmp_path):
        """SubagentClient defaults to read-write mode."""
        client = SubagentClient(root_dir=tmp_path)
        assert client.mode == "read-write"
