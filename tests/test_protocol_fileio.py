from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pytest  # noqa: E402

from acp_dispatch import DispatchResult, run_dispatch  # noqa: E402


class TestFileIOProtocol:
    """Live file I/O tests via real agent dispatch."""

    @pytest.mark.asyncio
    async def test_readonly_dispatch_no_outside_writes(self):
        """Read-only mode dispatch does not write files outside .docs/."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="Describe your favorite croissant recipe in one paragraph.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        assert isinstance(result, DispatchResult)
        # In read-only mode, written_files should be empty or .docs/-only.
        for path in result.written_files:
            normalized = path.replace("\\", "/")
            assert normalized.startswith(".docs/"), (
                f"Read-only dispatch wrote outside .docs/: {path}"
            )

    @pytest.mark.asyncio
    async def test_dispatch_completes_with_response(self):
        """Agent dispatch completes and returns response text (file I/O exercised internally)."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="What is the best bakery in Paris? One sentence.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        assert len(result.response_text) > 0
        assert isinstance(result.written_files, list)
