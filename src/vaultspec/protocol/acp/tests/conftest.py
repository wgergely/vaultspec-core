"""ACP bridge unit test fixtures and helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from ...providers import ClaudeModels
from ..claude_bridge import ClaudeACPBridge


class AsyncItemIterator:
    """Async iterator over a fixed list, for testing async-for loops."""

    def __init__(self, items: list, raise_exc: Exception | None = None):
        self._items = list(items)
        self._index = 0
        self._raise_exc = raise_exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._raise_exc is not None:
            exc = self._raise_exc
            self._raise_exc = None
            raise exc
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class SDKClientRecorder:
    """Records calls made to SDK client methods.

    A plain recorder that tracks method invocations via simple lists and
    counters.  Optional hooks allow tests to inject side effects (e.g.
    raising errors or mutating bridge state during a call).
    """

    def __init__(
        self,
        *,
        messages: list | None = None,
        connect_error: Exception | None = None,
        stream_error: Exception | None = None,
    ):
        self.messages = messages or []
        self.connect_error = connect_error
        self.stream_error = stream_error
        self.connect_calls: list[tuple[tuple, dict]] = []
        self.query_calls: list[Any] = []
        self.disconnect_count: int = 0
        self.interrupt_count: int = 0
        self._interrupt_hook: Exception | Callable[..., None] | None = None
        self._query_hook: Callable[..., Any] | None = None

    async def connect(self, *args, **kwargs):
        self.connect_calls.append((args, kwargs))
        if self.connect_error:
            raise self.connect_error

    async def query(self, prompt):
        # prompt may be a plain string or an async generator of message dicts
        if self._query_hook:
            # If hook returns True, skip default recording
            if asyncio.iscoroutinefunction(self._query_hook):
                if await self._query_hook(prompt):
                    return
            elif self._query_hook(prompt):
                return

        if hasattr(prompt, "__aiter__"):
            items = [item async for item in prompt]
            self.query_calls.append(items)
        else:
            self.query_calls.append(prompt)

    async def interrupt(self):
        self.interrupt_count += 1
        if self._interrupt_hook is not None:
            if isinstance(self._interrupt_hook, BaseException):
                raise self._interrupt_hook
            self._interrupt_hook()

    def disconnect(self):
        self.disconnect_count += 1

    def receive_messages(self):
        return AsyncItemIterator(self.messages, raise_exc=self.stream_error)

    def receive_response(self):
        """Simulate receive_response generator used by the bridge."""
        return AsyncItemIterator(self.messages, raise_exc=self.stream_error)


class ConnRecorder:
    """Records calls to ACP connection session_update."""

    def __init__(self):
        self.session_update_calls: list[dict] = []

    async def session_update(self, **kwargs):
        self.session_update_calls.append(kwargs)


def make_test_client(messages=None):
    """Build an SDKClientRecorder with optional pre-built messages."""
    return SDKClientRecorder(messages=messages)


def make_test_conn():
    """Build a ConnRecorder for ACP connection assertions."""
    return ConnRecorder()


def make_di_bridge(*, client=None, **bridge_kwargs):
    """Create a :class:`ClaudeACPBridge` with DI'd SDK factories.

    Uses constructor-injected ``client_factory`` and ``options_factory``
    instead of monkeypatching module globals.

    Returns ``(bridge, holder, captured_options)`` where:

    - **bridge**: the configured :class:`ClaudeACPBridge`
    - **holder**: ``SimpleNamespace`` with ``.client`` -- swap mid-test
      to simulate reconnection scenarios
    - **captured_options**: ``dict`` populated with the kwargs from the
      most recent ``options_factory()`` call
    """
    test_client = client or SDKClientRecorder()
    captured_options: dict[str, object] = {}
    holder = SimpleNamespace(client=test_client)

    def _options_factory(**kwargs):
        captured_options.clear()
        captured_options.update(kwargs)
        return SimpleNamespace(**kwargs)

    bridge_kwargs.setdefault("model", ClaudeModels.MEDIUM)
    bridge_kwargs.setdefault("debug", False)

    bridge = ClaudeACPBridge(
        client_factory=lambda _opts: holder.client,
        options_factory=_options_factory,
        **bridge_kwargs,
    )
    return bridge, holder, captured_options


@pytest.fixture
async def bridge():
    """Create a ClaudeACPBridge instance with default settings."""
    b = ClaudeACPBridge(model=ClaudeModels.MEDIUM, debug=False)
    yield b
    await b.close()


@pytest.fixture
async def bridge_debug():
    """Create a ClaudeACPBridge instance with debug enabled."""
    b = ClaudeACPBridge(model=ClaudeModels.MEDIUM, debug=True)
    yield b
    await b.close()


@pytest.fixture
def test_conn():
    """Create a test ACP connection recorder."""
    return ConnRecorder()


@pytest.fixture
def connected_bridge(bridge, test_conn):
    """A bridge with a test connection already set via on_connect."""
    bridge.on_connect(test_conn)
    return bridge
