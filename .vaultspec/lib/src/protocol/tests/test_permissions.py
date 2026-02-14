from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_permission_request_denied(mock_root_dir, test_agent_md):
    # Setup similar to lifecycle test but mock permission denial
    pass
