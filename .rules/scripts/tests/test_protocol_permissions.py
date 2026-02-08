"""Live permission protocol tests using real agents.

Tests that the ACP dispatch framework correctly handles permission enforcement
during real agent dispatch. Uses french-croissant in read-only mode to verify
that permission requests are auto-approved and read-only constraints hold.

Requires GEMINI_API_KEY to be set.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from acp_dispatch import DispatchResult, run_dispatch


class TestPermissionProtocol:
    """Live permission enforcement tests via real agent dispatch."""

    @pytest.mark.asyncio
    async def test_readonly_dispatch_enforces_constraints(self):
        """Read-only dispatch completes with permission enforcement active."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="Describe the perfect croissant.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        assert isinstance(result, DispatchResult)
        assert len(result.response_text) > 0
        # Read-only mode should not produce writes outside .docs/
        for path in result.written_files:
            normalized = path.replace("\\", "/")
            assert normalized.startswith(".docs/"), (
                f"Read-only dispatch wrote outside .docs/: {path}"
            )

    @pytest.mark.asyncio
    async def test_readwrite_dispatch_completes(self):
        """Read-write dispatch completes without permission errors."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="Say bonjour.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-write",
        )
        assert isinstance(result, DispatchResult)
        assert len(result.response_text) > 0
