"""Unit tests for protocol.a2a.agent_card — A2A agent card generation."""

import pytest

pytestmark = [pytest.mark.unit]

a2a = pytest.importorskip("a2a")

from core.config import reset_config  # noqa: E402

from protocol.a2a.agent_card import agent_card_from_definition  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


class TestAgentCardFromDefinition:
    def test_creates_card_with_name(self):
        meta = {
            "description": "Test agent",
            "name": "vaultspec-researcher",
            "tags": ["test"],
        }
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.name == "vaultspec-researcher"

    def test_creates_card_with_url(self):
        meta = {"description": "Test agent"}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.url == "http://localhost:10099/"

    def test_creates_card_with_description(self):
        meta = {"description": "A research agent"}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.description == "A research agent"

    def test_default_description(self):
        meta = {}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert "vaultspec-researcher" in card.description

    def test_has_one_skill(self):
        meta = {"description": "Test", "name": "vaultspec-researcher", "tags": ["test"]}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert len(card.skills) == 1
        assert card.skills[0].id == "vaultspec-researcher"

    def test_capabilities(self):
        meta = {"description": "Test"}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.capabilities.streaming is True

    def test_uses_default_config_for_host_port(self):
        meta = {"description": "Test"}
        card = agent_card_from_definition("vaultspec-researcher", meta)
        assert "localhost" in card.url
        assert "10010" in card.url

    def test_version_is_set(self):
        meta = {"description": "Test"}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.version == "0.1.0"

    def test_default_input_output_modes(self):
        meta = {"description": "Test"}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.default_input_modes == ["text"]
        assert card.default_output_modes == ["text"]

    def test_skill_inherits_name_from_meta(self):
        meta = {"description": "Test", "name": "custom-name"}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.skills[0].name == "custom-name"

    def test_skill_name_defaults_to_agent_name(self):
        meta = {"description": "Test"}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.skills[0].name == "vaultspec-researcher"

    def test_skill_tags_from_meta(self):
        meta = {"description": "Test", "tags": ["a2a", "research"]}
        card = agent_card_from_definition(
            "vaultspec-researcher", meta, host="localhost", port=10099
        )
        assert card.skills[0].tags == ["a2a", "research"]
