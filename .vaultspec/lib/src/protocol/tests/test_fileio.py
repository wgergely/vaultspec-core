from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_file_io_passthrough(mock_root_dir, test_agent_md):
    pass
