"""Tests for mcp.json configuration validity."""

import json

import pytest
from tests.constants import PROJECT_ROOT


@pytest.mark.unit
class TestMcpConfig:
    def test_mcp_json_exists(self):
        assert (PROJECT_ROOT / "mcp.json").exists()

    def test_mcp_json_valid_json(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        assert isinstance(data, dict)

    def test_has_mcp_servers(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        assert "mcpServers" in data

    def test_vs_subagent_entry_exists(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        assert "vs-subagent-mcp" in data["mcpServers"]

    def test_command_is_python(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        server = data["mcpServers"]["vs-subagent-mcp"]
        assert server["command"] == "python"

    def test_args_include_serve(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        server = data["mcpServers"]["vs-subagent-mcp"]
        assert "serve" in server["args"]

    def test_entry_point_exists(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        server = data["mcpServers"]["vs-subagent-mcp"]
        # Find the script path in args
        script = server["args"][0]  # .vaultspec/lib/scripts/subagent.py
        assert (PROJECT_ROOT / script).exists()
