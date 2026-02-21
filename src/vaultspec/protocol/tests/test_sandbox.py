"""Unit tests for protocol.sandbox — vault-path detection and sandbox callbacks."""

import pytest

pytestmark = [pytest.mark.unit]

claude_sdk = pytest.importorskip("claude_agent_sdk")

from tests.constants import TEST_PROJECT  # noqa: E402
from vaultspec.protocol.sandbox import (  # noqa: E402
    _is_vault_path,
    _make_sandbox_callback,
)

TEST_PROJECT_STR = str(TEST_PROJECT)


class TestIsVaultPath:
    def test_path_inside_vault(self):
        vault_file = str(
            TEST_PROJECT / ".vault" / "adr" / "2026-02-05-editor-demo-architecture.md"
        )
        assert _is_vault_path(vault_file, TEST_PROJECT_STR) is True

    def test_path_outside_vault(self):
        other_file = str(TEST_PROJECT / "README.md")
        assert _is_vault_path(other_file, TEST_PROJECT_STR) is False

    def test_vault_root_itself(self):
        vault_dir = str(TEST_PROJECT / ".vault")
        assert _is_vault_path(vault_dir, TEST_PROJECT_STR) is True

    def test_invalid_path(self):
        assert _is_vault_path("", "") is False


class TestMakeSandboxCallback:
    def test_read_write_returns_none(self):
        result = _make_sandbox_callback("read-write", TEST_PROJECT_STR)
        assert result is None

    def test_read_only_returns_callable(self):
        result = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        assert callable(result)

    @pytest.mark.asyncio
    async def test_read_only_denies_bash(self):
        from claude_agent_sdk.types import ToolPermissionContext

        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        ctx = ToolPermissionContext()
        result = await callback("Bash", {}, ctx)
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_denies_write_outside_vault(self):
        from claude_agent_sdk.types import ToolPermissionContext

        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        outside_path = str(TEST_PROJECT / "src" / "main.py")
        ctx = ToolPermissionContext()
        result = await callback("Write", {"file_path": outside_path}, ctx)
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_allows_write_inside_vault(self):
        from claude_agent_sdk.types import ToolPermissionContext

        vault_path = str(TEST_PROJECT / ".vault" / "adr" / "test.md")
        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        ctx = ToolPermissionContext()
        result = await callback("Write", {"file_path": vault_path}, ctx)
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_allows_read_tools(self):
        from claude_agent_sdk.types import ToolPermissionContext

        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        ctx = ToolPermissionContext()
        result = await callback("Read", {}, ctx)
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_denies_edit_outside_vault(self):
        from claude_agent_sdk.types import ToolPermissionContext

        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        outside_path = str(TEST_PROJECT / "src" / "lib.py")
        ctx = ToolPermissionContext()
        result = await callback("Edit", {"file_path": outside_path}, ctx)
        assert result.behavior == "deny"

    @pytest.mark.asyncio
    async def test_read_only_allows_edit_inside_vault(self):
        from claude_agent_sdk.types import ToolPermissionContext

        vault_path = str(TEST_PROJECT / ".vault" / "research" / "notes.md")
        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        ctx = ToolPermissionContext()
        result = await callback("Edit", {"file_path": vault_path}, ctx)
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_allows_grep(self):
        from claude_agent_sdk.types import ToolPermissionContext

        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        ctx = ToolPermissionContext()
        result = await callback("Grep", {}, ctx)
        assert result.behavior == "allow"

    @pytest.mark.asyncio
    async def test_read_only_allows_glob(self):
        from claude_agent_sdk.types import ToolPermissionContext

        callback = _make_sandbox_callback("read-only", TEST_PROJECT_STR)
        ctx = ToolPermissionContext()
        result = await callback("Glob", {}, ctx)
        assert result.behavior == "allow"
