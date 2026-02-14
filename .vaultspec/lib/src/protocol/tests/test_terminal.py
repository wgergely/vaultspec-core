from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_terminal_interaction(mock_root_dir, test_agent_md):
    # Setup mock for terminal creation and output
    pass
