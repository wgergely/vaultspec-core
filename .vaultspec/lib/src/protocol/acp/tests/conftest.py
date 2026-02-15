"""ACP bridge unit test fixtures and helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

# Ensure lib/src is importable
_LIB_SRC = Path(__file__).resolve().parent.parent.parent.parent
if str(_LIB_SRC) not in sys.path:
    sys.path.insert(0, str(_LIB_SRC))

# Canonical test fixture root (git-tracked seed corpus)
_PROJECT_ROOT = _LIB_SRC.parents[2]
TEST_PROJECT = _PROJECT_ROOT / "test-project"

from claude_agent_sdk import (  # noqa: E402, I001
    AssistantMessage as _AssistantMessage,
    ResultMessage as _ResultMessage,
    SystemMessage as _SystemMessage,
    TextBlock as _TextBlock,
    ThinkingBlock as _ThinkingBlock,
    ToolResultBlock as _ToolResultBlock,
    ToolUseBlock as _ToolUseBlock,
    UserMessage as _UserMessage,
)
from protocol.acp.claude_bridge import ClaudeACPBridge  # noqa: E402

# ---------------------------------------------------------------------------
# AsyncIteratorMock helper
# ---------------------------------------------------------------------------


class AsyncIteratorMock:
    """A fake async iterator for testing async for loops."""

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
# _CallArgs — thin wrapper for .call_args.kwargs pattern
# ---------------------------------------------------------------------------


class _CallArgs:
    """Thin wrapper so code can do ``.call_args.kwargs``."""

    def __init__(self, data: dict):
        self.kwargs = data


# ---------------------------------------------------------------------------
# FakeSyncMethod / FakeAsyncMethod — trackable callable methods
# ---------------------------------------------------------------------------


class FakeSyncMethod:
    """A callable sync method that records calls with assertion helpers.

    Used for SDK methods like ``interrupt()`` and ``disconnect()`` that
    tests assert on with patterns like ``obj.assert_called_once()``,
    ``obj.reset_mock()``, ``obj.side_effect = ...``.
    """

    def __init__(self):
        self._calls: list[tuple] = []
        self.side_effect: Exception | Callable[..., object] | None = None

    def __call__(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        if self.side_effect is not None:
            if isinstance(self.side_effect, BaseException):
                raise self.side_effect
            if callable(self.side_effect):
                return self.side_effect(*args, **kwargs)

    @property
    def call_count(self):
        return len(self._calls)

    @property
    def call_args(self):
        if not self._calls:
            return None
        _args, kwargs = self._calls[-1]
        return _CallArgs(kwargs)

    def assert_called_once(self):
        assert len(self._calls) == 1, f"Expected 1 call, got {len(self._calls)}"

    def assert_not_called(self):
        assert len(self._calls) == 0, f"Expected 0 calls, got {len(self._calls)}"

    def reset_mock(self):
        self._calls.clear()


class FakeAsyncMethod:
    """A callable async method that records calls and provides assertion helpers.

    Mimics the subset of MagicMock/AsyncMock API used in the ACP tests:
    - ``await obj(...)``
    - ``obj.assert_called_once()``
    - ``obj.assert_not_called()``
    - ``obj.call_args.kwargs``
    - ``obj.call_count``
    - ``obj.reset_mock()``
    """

    def __init__(self):
        self._calls: list[tuple[tuple, dict]] = []
        self.side_effect: Exception | Callable[..., object] | None = None

    async def __call__(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        if self.side_effect is not None:
            if isinstance(self.side_effect, BaseException):
                raise self.side_effect
            if callable(self.side_effect):
                result = self.side_effect(*args, **kwargs)
                if hasattr(result, "__await__"):
                    return await result
                return result

    @property
    def call_count(self):
        return len(self._calls)

    @property
    def call_args(self):
        if not self._calls:
            return None
        _args, kwargs = self._calls[-1]
        return _CallArgs(kwargs)

    def assert_called_once(self):
        assert len(self._calls) == 1, f"Expected 1 call, got {len(self._calls)}"

    def assert_called_once_with(self, *expected_args):
        assert len(self._calls) == 1, f"Expected 1 call, got {len(self._calls)}"
        if expected_args:
            actual_args = self._calls[0][0]
            assert actual_args == expected_args, (
                f"Expected args {expected_args}, got {actual_args}"
            )

    def assert_awaited_once(self):
        self.assert_called_once()

    def assert_awaited_once_with(self, *expected_args, **expected_kwargs):
        self.assert_called_once()
        if expected_args:
            actual_args = self._calls[0][0]
            assert actual_args == expected_args
        if expected_kwargs:
            actual_kwargs = self._calls[0][1]
            assert actual_kwargs == expected_kwargs

    def assert_not_called(self):
        assert len(self._calls) == 0, f"Expected 0 calls, got {len(self._calls)}"

    def reset_mock(self):
        self._calls.clear()


# ---------------------------------------------------------------------------
# FakeSDKClient — replaces make_sdk_mock()
# ---------------------------------------------------------------------------


class FakeSDKClient:
    """Fake SDK client with correct sync/async method signatures.

    - connect is a FakeAsyncMethod (awaited by the bridge)
    - query is a FakeAsyncMethod (awaited by the bridge)
    - interrupt is a FakeSyncMethod (called directly)
    - disconnect is a FakeSyncMethod (called directly)
    - receive_messages() is sync and returns an async iterator

    Method objects support assertion helpers:
    ``mock_client.disconnect.assert_called_once()``,
    ``mock_client.disconnect.reset_mock()``, etc.
    """

    def __init__(self, messages=None):
        self._messages = messages

        # Tracked method objects
        self.connect = FakeAsyncMethod()
        self.query = FakeAsyncMethod()
        self.interrupt = FakeSyncMethod()
        self.disconnect = FakeSyncMethod()

    def receive_messages(self):
        items = self._messages if self._messages is not None else []
        return AsyncIteratorMock(items)


def make_sdk_mock(messages=None):
    """Create a FakeSDKClient (drop-in replacement for old MagicMock-based helper)."""
    return FakeSDKClient(messages=messages)


# ---------------------------------------------------------------------------
# FakeConn — replaces MagicMock() for ACP client connection
# ---------------------------------------------------------------------------


class FakeConn:
    """Fake ACP client connection with session_update tracking.

    ``session_update`` is a ``FakeAsyncMethod`` so tests can do:
    - ``await mock_conn.session_update(session_id=..., update=...)``
    - ``mock_conn.session_update.assert_called_once()``
    - ``mock_conn.session_update.call_args.kwargs``
    """

    def __init__(self):
        self.session_update = FakeAsyncMethod()


# ---------------------------------------------------------------------------
# FakeNamespace — replaces MagicMock() for arbitrary attribute bags
# ---------------------------------------------------------------------------


class FakeNamespace:
    """An object that accepts arbitrary attribute assignment.

    Replaces ``MagicMock()`` used as a simple attribute bag, e.g.,
    ``mock_client._options = MagicMock()`` / ``mock_client._options.model = "x"``.
    """

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def model_dump(self):
        return vars(self).copy()


# ---------------------------------------------------------------------------
# Fake SDK types — replaces MagicMock(spec=SDKType)
# ---------------------------------------------------------------------------


class FakeTextBlock(_TextBlock):
    """Stand-in for claude_agent_sdk.TextBlock (passes isinstance checks)."""

    def __init__(self, text: str = ""):
        super().__init__(text=text)


class FakeThinkingBlock(_ThinkingBlock):
    """Stand-in for claude_agent_sdk.ThinkingBlock (passes isinstance checks)."""

    def __init__(self, thinking: str = ""):
        super().__init__(thinking=thinking, signature="")


class FakeToolUseBlock(_ToolUseBlock):
    """Stand-in for claude_agent_sdk.ToolUseBlock (passes isinstance checks)."""

    def __init__(self, id: str = "", name: str = ""):
        super().__init__(id=id, name=name, input={})


class FakeToolResultBlock(_ToolResultBlock):
    """Stand-in for claude_agent_sdk.ToolResultBlock (passes isinstance checks)."""

    def __init__(self, is_error: bool = False):
        super().__init__(tool_use_id="", is_error=is_error)


class FakeAssistantMessage(_AssistantMessage):
    """Stand-in for claude_agent_sdk.AssistantMessage (passes isinstance checks)."""

    def __init__(self, content: list | None = None):
        super().__init__(content=content or [], model="fake-model")


class FakeUserMessage(_UserMessage):
    """Stand-in for claude_agent_sdk.UserMessage (passes isinstance checks)."""

    def __init__(
        self,
        parent_tool_use_id: str | None = None,
        content: list | None = None,
    ):
        super().__init__(
            content=content or [],
            parent_tool_use_id=parent_tool_use_id,
        )


class FakeSystemMessage(_SystemMessage):
    """Stand-in for claude_agent_sdk.SystemMessage (passes isinstance checks)."""

    def __init__(self, subtype: str = "system"):
        super().__init__(subtype=subtype, data={})


class FakeResultMessage(_ResultMessage):
    """Stand-in for claude_agent_sdk.ResultMessage (passes isinstance checks)."""

    def __init__(self, result: str | dict | None = None, is_error: bool = False):
        # Convert non-string results to str for the SDK base class,
        # preserving the original value for bridge code that checks type.
        result_str = None
        if isinstance(result, str):
            result_str = result
        elif result is not None:
            result_str = str(result)
        super().__init__(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=is_error,
            num_turns=0,
            session_id="",
            result=result_str,
        )
        # Store original for tests that check non-string result
        self._original_result = result


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
    """Create a fake ACP client connection (as provided by on_connect)."""
    return FakeConn()


@pytest.fixture
def connected_bridge(bridge, mock_conn):
    """A bridge with a fake connection already set via on_connect."""
    bridge.on_connect(mock_conn)
    return bridge
