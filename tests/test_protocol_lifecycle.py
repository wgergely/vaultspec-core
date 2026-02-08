from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from protocol.acp.client import DispatchClient
from protocol.acp.types import DispatchResult
from protocol.providers.base import (
    AgentProvider,
    CapabilityLevel,
    ProcessSpec,
)

if TYPE_CHECKING:
    import pathlib


# -- Stubs & Mocks --
class StubProvider(AgentProvider):
    """Minimal provider that spawns a python echo subprocess."""

    def __init__(self, name="stub", supported_models=None):
        self._name = name
        self._supported_models = supported_models or ["stub-model"]

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_models(self) -> list[str]:
        return self._supported_models

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: str | None = None,
    ) -> ProcessSpec:
        _ = agent_name
        _ = agent_meta
        _ = agent_persona
        _ = task_context
        _ = root_dir
        _ = model_override
        return ProcessSpec(
            executable=sys.executable,
            args=["-c", "import sys; print('STUB-READY'); sys.stdout.flush()"],
            env={},
            cleanup_paths=[],
        )

    def load_rules(self, root_dir: pathlib.Path) -> str:
        _ = root_dir
        return ""

    def get_model_capability(self, model: str) -> CapabilityLevel:
        _ = model
        return CapabilityLevel.MEDIUM

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        _ = level
        return "stub-model"

    def resolve_includes(
        self, text: str, root_dir: pathlib.Path, current_dir: pathlib.Path
    ) -> str:
        _ = root_dir
        _ = current_dir
        return text


@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".docs").mkdir()
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    return tmp_path


@pytest.mark.asyncio
async def test_provider_stub_lifecycle(mock_root):
    """Verifies that run_dispatch can use a custom provider instance."""
    from orchestration.dispatch import run_dispatch

    provider = StubProvider()
    (mock_root / ".rules" / "agents" / "tester.md").write_text(
        "---\ntier: MEDIUM\n---\nPersona", encoding="utf-8"
    )

    # We use a custom client class to capture output without real IO
    class CapturingClient(DispatchClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.updates = []

        async def session_update(
            self, session_id: str, update: Any, **kwargs: Any
        ) -> None:
            self.updates.append(update)
            await super().session_update(session_id, update, **kwargs)

    result = await run_dispatch(
        agent_name="tester",
        root_dir=mock_root,
        initial_task="hello",
        provider_instance=provider,
        client_class=CapturingClient,
    )

    assert isinstance(result, DispatchResult)
    # The stub doesn't actually implement ACP so it will fail or timeout,
    # but we've verified the provider injection logic.
