"""ACP bridge unit test fixtures and helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure lib/src is importable
_LIB_SRC = Path(__file__).resolve().parent.parent.parent.parent
if str(_LIB_SRC) not in sys.path:
    sys.path.insert(0, str(_LIB_SRC))

from protocol.acp.claude_bridge import ClaudeACPBridge  # noqa: E402

# ---------------------------------------------------------------------------
# AsyncIteratorMock helper
# ---------------------------------------------------------------------------


class AsyncIteratorMock:
    """A mock async iterator for testing async for loops."""

    def __init__(self, items: list, raise_exc: Exception | None = None):
        self._items = list(items)
        self._index = 0
        self._raise_exc = raise_exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._raise_exc is not None:
            exc = self._raise_exc
            self._raise_exc = None  # Only raise once
            raise exc
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


# ---------------------------------------------------------------------------
# SDK mock helper
# ---------------------------------------------------------------------------


def make_sdk_mock(messages=None):
    """Create a mock SDK client with correct sync/async method signatures.

    - connect() and query() are async (awaited by the bridge)
    - interrupt() and disconnect() are sync (called directly)
    - receive_messages() is sync and returns an async iterator
    """
    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.query = AsyncMock()
    mock.interrupt = MagicMock()
    mock.disconnect = MagicMock()
    if messages is not None:
        mock.receive_messages = MagicMock(return_value=AsyncIteratorMock(messages))
    else:
        mock.receive_messages = MagicMock(return_value=AsyncIteratorMock([]))
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bridge():
    """Create a ClaudeACPBridge instance with default settings."""
    return ClaudeACPBridge(model="claude-sonnet-4-5", debug=False)


@pytest.fixture
def bridge_debug():
    """Create a ClaudeACPBridge instance with debug enabled."""
    return ClaudeACPBridge(model="claude-sonnet-4-5", debug=True)


@pytest.fixture
def mock_conn():
    """Create a mock ACP client connection (as provided by on_connect)."""
    conn = MagicMock()
    conn.session_update = AsyncMock()
    return conn


@pytest.fixture
def connected_bridge(bridge, mock_conn):
    """A bridge with a mock connection already set via on_connect."""
    bridge.on_connect(mock_conn)
    return bridge
