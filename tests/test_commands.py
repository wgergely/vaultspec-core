from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from click.exceptions import Exit

from tests.constants import PROJECT_ROOT
from vaultspec_core.config import reset_config
from vaultspec_core.core import types as _t
from vaultspec_core.core.commands import init_run
from vaultspec_core.core.commands import test_run as run_test_command


@pytest.mark.unit
def test_init_run_scaffolds_antigravity_workspace_layout() -> None:
    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"init-run-{uuid4().hex}"
    original_target = _t.TARGET_DIR
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        _t.TARGET_DIR = tmp_path
        reset_config()

        init_run(force=False, providers="all")

        assert (tmp_path / ".agents" / "rules").is_dir()
        assert (tmp_path / ".agents" / "workflows").is_dir()
        assert (tmp_path / ".agents" / "skills").is_dir()
        assert (tmp_path / ".codex" / "config.toml").is_file()
        assert not (tmp_path / ".agents" / "agents").exists()
        mcp_config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp_config["mcpServers"]["vaultspec-core"]
        assert server["command"] == "vaultspec-mcp"
        assert server["args"] == []
        assert server["env"]["VAULTSPEC_TARGET_DIR"] == str(tmp_path.resolve())
    finally:
        _t.TARGET_DIR = original_target
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_test_run_uses_uv_pytest(tmp_path: Path) -> None:
    original_target = _t.TARGET_DIR
    original_cache = os.environ.get("UV_CACHE_DIR")
    cache_dir = (
        Path(tempfile.gettempdir()) / "vaultspec-pytest" / f"uv-cache-{uuid4().hex}"
    )

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["UV_CACHE_DIR"] = str(cache_dir)
        _t.TARGET_DIR = PROJECT_ROOT

        with pytest.raises(Exit) as exc_info:
            run_test_command(
                category="unit",
                module="cli",
                extra_args=["-q", "-k", "test_help_flag"],
            )

        assert exc_info.value.exit_code == 0
    finally:
        _t.TARGET_DIR = original_target
        if original_cache is None:
            os.environ.pop("UV_CACHE_DIR", None)
        else:
            os.environ["UV_CACHE_DIR"] = original_cache
        shutil.rmtree(cache_dir, ignore_errors=True)
