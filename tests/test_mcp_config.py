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

    def test_vaultspec_core_entry_exists(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        assert "vaultspec-core" in data["mcpServers"]

    def test_command_is_uv(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        server = data["mcpServers"]["vaultspec-core"]
        assert server["command"] == "uv"

    def test_args_include_run(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        server = data["mcpServers"]["vaultspec-core"]
        assert "run" in server["args"]
        assert "vaultspec-mcp" in server["args"]

    def test_uses_target_dir_env(self):
        data = json.loads((PROJECT_ROOT / "mcp.json").read_text())
        server = data["mcpServers"]["vaultspec-core"]
        assert server["env"]["VAULTSPEC_TARGET_DIR"] == "."
