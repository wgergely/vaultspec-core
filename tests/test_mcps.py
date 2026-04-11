"""Tests for MCP server registry: collection, CRUD, sync, and lifecycle."""

from __future__ import annotations

import json
import shutil
from uuid import uuid4

import pytest

from tests.constants import PROJECT_ROOT
from vaultspec_core.config import reset_config


def _make_workspace(tmp: object = None):
    """Create a minimal workspace with .vaultspec/rules/mcps/ directory."""
    path = PROJECT_ROOT / ".pytest-tmp" / f"mcps-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    mcps_dir = path / ".vaultspec" / "rules" / "mcps"
    mcps_dir.mkdir(parents=True, exist_ok=True)
    return path, mcps_dir


def _init_context(path):
    """Bootstrap a WorkspaceContext pointing at the given path."""
    from vaultspec_core.config.workspace import resolve_workspace
    from vaultspec_core.core.types import init_paths

    reset_config()
    # Create minimal .vaultspec structure for workspace resolution
    fw_dir = path / ".vaultspec"
    fw_dir.mkdir(parents=True, exist_ok=True)
    layout = resolve_workspace(target_override=path)
    return init_paths(layout)


@pytest.mark.unit
class TestServerName:
    def test_builtin_suffix(self):
        from vaultspec_core.core.mcps import _server_name

        assert _server_name("vaultspec-core.builtin.json") == "vaultspec-core"

    def test_json_suffix(self):
        from vaultspec_core.core.mcps import _server_name

        assert _server_name("my-server.json") == "my-server"

    def test_multi_dot_builtin(self):
        from vaultspec_core.core.mcps import _server_name

        assert _server_name("foo.bar.builtin.json") == "foo.bar"

    def test_multi_dot_json(self):
        from vaultspec_core.core.mcps import _server_name

        assert _server_name("foo.bar.json") == "foo.bar"

    def test_no_json_suffix(self):
        from vaultspec_core.core.mcps import _server_name

        assert _server_name("something") == "something"


@pytest.mark.unit
class TestCollectMcpServers:
    def test_empty_directory(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            result = collect_mcp_servers()
            assert result == {}
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_missing_directory(self):
        path = PROJECT_ROOT / ".pytest-tmp" / f"mcps-missing-{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        try:
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            result = collect_mcp_servers()
            assert result == {}
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_single_builtin(self):
        path, mcps_dir = _make_workspace()
        try:
            config = {"command": "uv", "args": ["run", "test"]}
            (mcps_dir / "test-server.builtin.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            result = collect_mcp_servers()
            assert "test-server" in result
            assert result["test-server"][1] == config
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_custom_definition(self):
        path, mcps_dir = _make_workspace()
        try:
            config = {"command": "node", "args": ["server.js"]}
            (mcps_dir / "custom-mcp.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            result = collect_mcp_servers()
            assert "custom-mcp" in result
            assert result["custom-mcp"][1] == config
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_parse_error_captured_in_warnings(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "bad.json").write_text("not valid json", encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            warnings: list[str] = []
            result = collect_mcp_servers(warnings=warnings)
            assert result == {}
            assert len(warnings) == 1
            assert "bad.json" in warnings[0]
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_non_object_json_rejected(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "array.json").write_text("[1, 2, 3]", encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            warnings: list[str] = []
            result = collect_mcp_servers(warnings=warnings)
            assert result == {}
            assert len(warnings) == 1
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_mixed_builtin_and_custom(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "core.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            (mcps_dir / "custom.json").write_text(
                json.dumps({"command": "node"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            result = collect_mcp_servers()
            assert len(result) == 2
            assert "core" in result
            assert "custom" in result
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestMcpList:
    def test_lists_with_source_classification(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "builtin-srv.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            (mcps_dir / "custom-srv.json").write_text(
                json.dumps({"command": "node"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_list

            items = mcp_list()
            names = {i["name"]: i["source"] for i in items}
            assert names["builtin-srv"] == "Built-in"
            assert names["custom-srv"] == "Custom"
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestMcpAdd:
    def test_creates_definition_file(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_add

            result = mcp_add("my-server", config={"command": "test"})
            assert result.exists()
            content = json.loads(result.read_text(encoding="utf-8"))
            assert content["command"] == "test"
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_raises_on_existing_without_force(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "exists.json").write_text("{}", encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.exceptions import ResourceExistsError
            from vaultspec_core.core.mcps import mcp_add

            with pytest.raises(ResourceExistsError):
                mcp_add("exists")
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_overwrites_with_force(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "exists.json").write_text("{}", encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_add

            result = mcp_add("exists", config={"command": "new"}, force=True)
            content = json.loads(result.read_text(encoding="utf-8"))
            assert content["command"] == "new"
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestMcpRemove:
    def test_removes_json_file(self):
        path, mcps_dir = _make_workspace()
        try:
            target_file = mcps_dir / "removable.json"
            target_file.write_text("{}", encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_remove

            result = mcp_remove("removable")
            assert result == target_file
            assert not target_file.exists()
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_removes_builtin_file(self):
        path, mcps_dir = _make_workspace()
        try:
            target_file = mcps_dir / "removable.builtin.json"
            target_file.write_text("{}", encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_remove

            mcp_remove("removable")
            assert not target_file.exists()
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_raises_when_not_found(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.exceptions import ResourceNotFoundError
            from vaultspec_core.core.mcps import mcp_remove

            with pytest.raises(ResourceNotFoundError):
                mcp_remove("nonexistent")
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestMcpSync:
    def test_creates_mcp_json_from_scratch(self):
        path, mcps_dir = _make_workspace()
        try:
            config = {"command": "uv", "args": ["run", "test"]}
            (mcps_dir / "test-srv.builtin.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            result = mcp_sync()
            assert result.added == 1
            assert result.skipped == 0

            mcp_json = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert mcp_json["mcpServers"]["test-srv"] == config
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_idempotent_sync(self):
        path, mcps_dir = _make_workspace()
        try:
            config = {"command": "uv", "args": ["run", "test"]}
            (mcps_dir / "test-srv.builtin.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            mcp_sync()
            result = mcp_sync()
            assert result.added == 0
            assert result.skipped == 1
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_preserves_user_entries(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "managed.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            # Pre-populate .mcp.json with a user entry
            user_config = {
                "mcpServers": {"user-server": {"command": "custom", "args": []}}
            }
            (path / ".mcp.json").write_text(json.dumps(user_config), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            result = mcp_sync()
            assert result.added == 1

            mcp_json = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "user-server" in mcp_json["mcpServers"]
            assert "managed" in mcp_json["mcpServers"]
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_warns_on_diff_without_force(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "srv.builtin.json").write_text(
                json.dumps({"command": "new"}), encoding="utf-8"
            )
            existing = {"mcpServers": {"srv": {"command": "old"}}}
            (path / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            result = mcp_sync(force=False)
            assert result.skipped == 1
            assert result.updated == 0
            assert any("--force" in w for w in result.warnings)
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_force_overwrites_diff(self):
        path, mcps_dir = _make_workspace()
        try:
            new_config = {"command": "new"}
            (mcps_dir / "srv.builtin.json").write_text(
                json.dumps(new_config), encoding="utf-8"
            )
            existing = {"mcpServers": {"srv": {"command": "old"}}}
            (path / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            result = mcp_sync(force=True)
            assert result.updated == 1

            mcp_json = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert mcp_json["mcpServers"]["srv"] == new_config
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_dry_run_does_not_write(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "srv.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            result = mcp_sync(dry_run=True)
            assert result.added == 1
            assert not (path / ".mcp.json").exists()
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestMcpUninstall:
    def test_removes_managed_entries(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "managed.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            mcp_data = {
                "mcpServers": {
                    "managed": {"command": "uv"},
                    "user": {"command": "custom"},
                }
            }
            (path / ".mcp.json").write_text(json.dumps(mcp_data), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_uninstall

            removed = mcp_uninstall(path)
            assert "managed" in removed

            remaining = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "managed" not in remaining["mcpServers"]
            assert "user" in remaining["mcpServers"]
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_deletes_file_when_empty(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "only.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            mcp_data = {"mcpServers": {"only": {"command": "uv"}}}
            (path / ".mcp.json").write_text(json.dumps(mcp_data), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_uninstall

            mcp_uninstall(path)
            assert not (path / ".mcp.json").exists()
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_fallback_to_vaultspec_core_when_no_registry(self):
        path = PROJECT_ROOT / ".pytest-tmp" / f"mcps-uninstall-{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        try:
            mcp_data = {"mcpServers": {"vaultspec-core": {"command": "uv"}}}
            (path / ".mcp.json").write_text(json.dumps(mcp_data), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_uninstall

            removed = mcp_uninstall(path)
            assert "vaultspec-core" in removed
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestInstallSeedsMcps:
    def test_install_creates_mcp_json_from_registry(self):
        path = PROJECT_ROOT / ".pytest-tmp" / f"mcps-install-{uuid4().hex}"
        try:
            path.mkdir(parents=True, exist_ok=True)
            reset_config()

            from vaultspec_core.core.commands import install_run

            install_run(
                path=path, provider="all", upgrade=False, dry_run=False, force=False
            )

            mcp_json = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "vaultspec-core" in mcp_json["mcpServers"]
            server = mcp_json["mcpServers"]["vaultspec-core"]
            assert server["command"] == "uv"
            expected_args = ["run", "python", "-m", "vaultspec_core.mcp_server.app"]
            assert server["args"] == expected_args
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)
