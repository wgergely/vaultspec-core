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

    def test_custom_shadows_builtin_in_collect(self):
        """When both foo.builtin.json and foo.json exist, custom config wins."""
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "srv.builtin.json").write_text(
                json.dumps({"command": "old-builtin"}), encoding="utf-8"
            )
            (mcps_dir / "srv.json").write_text(
                json.dumps({"command": "new-custom"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            result = collect_mcp_servers()
            assert len(result) == 1
            assert result["srv"][1]["command"] == "new-custom"
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_empty_stem_filenames_skipped(self):
        """Files named '.json' or '.builtin.json' (no server name) are ignored."""
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / ".json").write_text(
                json.dumps({"command": "bad"}), encoding="utf-8"
            )
            (mcps_dir / ".builtin.json").write_text(
                json.dumps({"command": "also-bad"}), encoding="utf-8"
            )
            (mcps_dir / "valid.json").write_text(
                json.dumps({"command": "good"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import collect_mcp_servers

            result = collect_mcp_servers()
            assert len(result) == 1
            assert "valid" in result
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestMcpList:
    def test_shadowed_definition_shows_custom(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "srv.builtin.json").write_text(
                json.dumps({"command": "old"}), encoding="utf-8"
            )
            (mcps_dir / "srv.json").write_text(
                json.dumps({"command": "new"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_list

            items = mcp_list()
            assert len(items) == 1
            assert items[0]["name"] == "srv"
            assert "shadows" in items[0]["source"].lower()
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

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

    def test_created_file_stays_within_mcps_dir(self):
        """Security invariant: the written file must be inside mcps_dir."""
        path, mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_add

            result = mcp_add("legit-server", config={"command": "test"})
            assert result.resolve().is_relative_to(mcps_dir.resolve())
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

    def test_rejects_path_traversal(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.exceptions import VaultSpecError
            from vaultspec_core.core.mcps import mcp_add

            with pytest.raises(VaultSpecError, match="Invalid"):
                mcp_add("../evil")
            with pytest.raises(VaultSpecError, match="Invalid"):
                mcp_add("foo/../bar")
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_rejects_empty_name(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.exceptions import VaultSpecError
            from vaultspec_core.core.mcps import mcp_add

            with pytest.raises(VaultSpecError, match="empty"):
                mcp_add("")
            with pytest.raises(VaultSpecError, match="empty"):
                mcp_add("   ")
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_rejects_builtin_suffix(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.exceptions import VaultSpecError
            from vaultspec_core.core.mcps import mcp_add

            with pytest.raises(VaultSpecError, match="builtin"):
                mcp_add("fake.builtin")
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_rejects_non_dict_config(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.exceptions import VaultSpecError
            from vaultspec_core.core.mcps import mcp_add

            with pytest.raises(VaultSpecError, match="dict"):
                mcp_add("srv", config=[1, 2, 3])  # type: ignore[arg-type]
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

    def test_custom_removed_before_builtin(self):
        """When both exist, custom .json is removed first (revert semantics)."""
        path, mcps_dir = _make_workspace()
        try:
            builtin = mcps_dir / "srv.builtin.json"
            custom = mcps_dir / "srv.json"
            builtin.write_text(json.dumps({"command": "old"}), encoding="utf-8")
            custom.write_text(json.dumps({"command": "new"}), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_remove

            mcp_remove("srv")
            assert not custom.exists(), "Custom .json should be removed first"
            assert builtin.exists(), "Builtin should survive first removal"
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_removed_file_was_within_mcps_dir(self):
        """Security invariant: only files inside mcps_dir can be removed."""
        path, mcps_dir = _make_workspace()
        try:
            target = mcps_dir / "safe.json"
            target.write_text("{}", encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_remove

            result = mcp_remove("safe")
            assert result.resolve().is_relative_to(mcps_dir.resolve())
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_rejects_traversal_in_remove(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.exceptions import VaultSpecError
            from vaultspec_core.core.mcps import mcp_remove

            with pytest.raises(VaultSpecError, match="Invalid"):
                mcp_remove("../escape")
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_rejects_empty_name_in_remove(self):
        path, _mcps_dir = _make_workspace()
        try:
            _init_context(path)
            from vaultspec_core.core.exceptions import VaultSpecError
            from vaultspec_core.core.mcps import mcp_remove

            with pytest.raises(VaultSpecError, match="empty"):
                mcp_remove("")
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
class TestUninstallRemovesCustomMcps:
    def test_full_uninstall_removes_custom_mcp_entries(self):
        """Regression: uninstall must read registry BEFORE deleting .vaultspec/.

        If .vaultspec/ is deleted first, collect_mcp_servers() returns empty
        and only the hardcoded 'vaultspec-core' fallback is cleaned up,
        leaving custom entries behind.
        """
        path = PROJECT_ROOT / ".pytest-tmp" / f"mcps-uninstall-full-{uuid4().hex}"
        try:
            path.mkdir(parents=True, exist_ok=True)
            reset_config()

            from vaultspec_core.core.commands import install_run

            install_run(
                path=path, provider="all", upgrade=False, dry_run=False, force=False
            )

            # Add a custom MCP definition post-install
            mcps_dir = path / ".vaultspec" / "rules" / "mcps"
            (mcps_dir / "custom-rag.json").write_text(
                json.dumps({"command": "uv", "args": ["run", "rag-server"]}),
                encoding="utf-8",
            )

            # Sync so the custom entry lands in .mcp.json
            from vaultspec_core.core.mcps import mcp_sync

            mcp_sync(force=True)

            mcp_before = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "custom-rag" in mcp_before["mcpServers"]
            assert "vaultspec-core" in mcp_before["mcpServers"]

            # Full uninstall
            from vaultspec_core.core.commands import uninstall_run

            uninstall_run(path, provider="all", force=True)

            # Both managed entries should be gone
            if (path / ".mcp.json").exists():
                mcp_after = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
                servers = mcp_after.get("mcpServers", {})
                assert "custom-rag" not in servers, (
                    "Custom MCP entry survived uninstall"
                )
                assert "vaultspec-core" not in servers
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
class TestMcpSyncPrune:
    """Reconciling sync — prune orphans on companion uninstall."""

    def test_prune_removes_orphan_managed_entry(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "ephemeral.builtin.json").write_text(
                json.dumps({"command": "uv", "args": ["run", "ephemeral"]}),
                encoding="utf-8",
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            # First sync: install
            result = mcp_sync()
            assert result.added == 1
            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "ephemeral" in data["mcpServers"]
            assert data["_vaultspecManaged"] == ["ephemeral"]

            # Delete the source file to simulate companion uninstall
            (mcps_dir / "ephemeral.builtin.json").unlink()

            # Second sync with prune=True: should remove the orphan
            result = mcp_sync(prune=True)
            assert result.pruned == 1
            assert ("ephemeral", "[DELETE]") in result.items

            # File should be removed entirely (no managed, no servers)
            assert not (path / ".mcp.json").exists()
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_prune_default_false_leaves_orphans(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "stay.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            mcp_sync()
            (mcps_dir / "stay.builtin.json").unlink()

            # Default prune=False: orphan stays put
            result = mcp_sync()
            assert result.pruned == 0
            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "stay" in data["mcpServers"]
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_prune_preserves_user_added_entries(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "managed.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            user_data = {"mcpServers": {"my-tool": {"command": "custom", "args": []}}}
            (path / ".mcp.json").write_text(json.dumps(user_data), encoding="utf-8")
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            mcp_sync()
            (mcps_dir / "managed.builtin.json").unlink()

            result = mcp_sync(prune=True)
            assert result.pruned == 1

            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            # User entry survives the orphan prune
            assert "my-tool" in data["mcpServers"]
            assert "managed" not in data["mcpServers"]
            # No managed key remains since the only managed entry was pruned
            assert "_vaultspecManaged" not in data
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_user_added_with_shared_name_never_taken_over(self):
        """A user-added entry must not be taken over just because a
        source file appears with the same name later. The strict
        ownership rule: only entries created by mcp_sync itself
        enter the managed set.
        """
        path, mcps_dir = _make_workspace()
        try:
            # User pre-registers an entry — note: file already has the
            # _vaultspecManaged sidecar (empty), so legacy migration
            # does NOT take ownership.
            existing = {
                "mcpServers": {"shared": {"command": "user-binary"}},
                "_vaultspecManaged": [],
            }
            (path / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")

            # Source file with the same name appears
            (mcps_dir / "shared.builtin.json").write_text(
                json.dumps({"command": "vaultspec-binary"}), encoding="utf-8"
            )

            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            result = mcp_sync()
            # Should NOT add (entry already there) and NOT enter managed
            assert result.added == 0
            assert result.skipped == 1
            assert any("user-managed" in w for w in result.warnings), result.warnings

            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            # User's entry preserved unchanged
            assert data["mcpServers"]["shared"]["command"] == "user-binary"
            # Source name did NOT get added to managed set
            assert "shared" not in data.get("_vaultspecManaged", [])
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_legacy_migration_treats_pre_existing_as_managed(self):
        """Workspaces created before ownership tracking shipped have
        no `_vaultspecManaged` sidecar. The migration heuristic treats
        any pre-existing entry whose name matches a current source as
        managed (preserves the legacy 'differs, use --force' warning).
        """
        path, mcps_dir = _make_workspace()
        try:
            # Pre-existing .mcp.json without sidecar key (legacy)
            existing = {"mcpServers": {"legacy": {"command": "old"}}}
            (path / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
            (mcps_dir / "legacy.builtin.json").write_text(
                json.dumps({"command": "new"}), encoding="utf-8"
            )

            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            # First sync after upgrade — legacy migration kicks in
            result = mcp_sync(force=True)
            assert result.updated == 1

            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert data["mcpServers"]["legacy"]["command"] == "new"
            # Sidecar now persisted with the migrated entry
            assert data["_vaultspecManaged"] == ["legacy"]
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_managed_key_persisted_across_syncs(self):
        path, mcps_dir = _make_workspace()
        try:
            (mcps_dir / "alpha.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            (mcps_dir / "beta.builtin.json").write_text(
                json.dumps({"command": "uv"}), encoding="utf-8"
            )
            _init_context(path)
            from vaultspec_core.core.mcps import mcp_sync

            mcp_sync()
            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert data["_vaultspecManaged"] == ["alpha", "beta"]

            # Re-sync: managed set should remain identical
            mcp_sync()
            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert data["_vaultspecManaged"] == ["alpha", "beta"]
        finally:
            reset_config()
            shutil.rmtree(path, ignore_errors=True)

    def test_round_trip_install_uninstall_via_sync_provider(self):
        """End-to-end: install seeds an entry via sync_provider, then
        deleting the source and re-running sync_provider with force=True
        prunes the orphan cleanly. This is the canonical companion
        install/uninstall flow rag relies on.
        """
        path = PROJECT_ROOT / ".pytest-tmp" / f"mcp-roundtrip-{uuid4().hex}"
        try:
            path.mkdir(parents=True, exist_ok=True)
            reset_config()

            from vaultspec_core.core.commands import (
                install_run,
                sync_provider,
            )

            install_run(
                path=path,
                provider="all",
                upgrade=False,
                dry_run=False,
                force=False,
            )

            # Simulate a companion package dropping a source file
            mcps_dir = path / ".vaultspec" / "rules" / "mcps"
            (mcps_dir / "companion.builtin.json").write_text(
                json.dumps({"command": "uv", "args": ["run", "companion"]}),
                encoding="utf-8",
            )

            # Companion install: sync to propagate
            sync_provider("all", force=False)
            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "companion" in data["mcpServers"]
            assert "companion" in data["_vaultspecManaged"]

            # Companion uninstall: delete source + sync
            (mcps_dir / "companion.builtin.json").unlink()
            sync_provider("all", force=True)

            data = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
            assert "companion" not in data["mcpServers"]
            assert "companion" not in data.get("_vaultspecManaged", [])
            # vaultspec-core's own MCP entry is preserved
            assert "vaultspec-core" in data["mcpServers"]
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
