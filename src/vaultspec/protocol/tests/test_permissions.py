"""Tests for SubagentClient permission handling.

Covers the scenario where only reject options are available, verifying
that the client falls back to selecting a reject option rather than
auto-approving.
"""

from __future__ import annotations

import pytest
from acp.schema import (
    PermissionOption,
    ToolCallUpdate,
)

from ..acp import SubagentClient

pytestmark = [pytest.mark.unit]


class TestPermissionDenial:
    """Tests for permission denial scenarios in SubagentClient."""

    @pytest.fixture
    def client(self, test_root_dir):
        return SubagentClient(root_dir=test_root_dir, debug=False)

    @pytest.mark.asyncio
    async def test_permission_request_denied_when_only_reject_options(self, client):
        """When only reject options exist, client selects the first reject."""
        options = [
            PermissionOption(
                option_id="reject-write",
                name="Reject Write",
                kind="reject_once",
            ),
            PermissionOption(
                option_id="reject-always",
                name="Reject Always",
                kind="reject_always",
            ),
        ]
        tool_call = ToolCallUpdate(tool_call_id="tc-deny-1")
        result = await client.request_permission(
            options=options, session_id="s1", tool_call=tool_call
        )
        # With no allow options, the for/else clause selects the first option
        assert result.outcome.outcome == "selected"
        assert result.outcome.optionId == "reject-write"

    @pytest.mark.asyncio
    async def test_permission_reject_always_is_selected_over_reject_once(self, client):
        """Verifies fallback to first option regardless of reject type."""
        options = [
            PermissionOption(
                option_id="reject-always",
                name="Reject Always",
                kind="reject_always",
            ),
            PermissionOption(
                option_id="reject-once",
                name="Reject Once",
                kind="reject_once",
            ),
        ]
        tool_call = ToolCallUpdate(tool_call_id="tc-deny-2")
        result = await client.request_permission(
            options=options, session_id="s1", tool_call=tool_call
        )
        # Falls through to first option
        assert result.outcome.optionId == "reject-always"

    @pytest.mark.asyncio
    async def test_permission_allow_preferred_over_reject(self, client):
        """When both allow and reject exist, allow is selected."""
        options = [
            PermissionOption(
                option_id="reject-it",
                name="Reject",
                kind="reject_once",
            ),
            PermissionOption(
                option_id="allow-it",
                name="Allow",
                kind="allow_once",
            ),
        ]
        tool_call = ToolCallUpdate(tool_call_id="tc-deny-3")
        result = await client.request_permission(
            options=options, session_id="s1", tool_call=tool_call
        )
        assert result.outcome.optionId == "allow-it"
