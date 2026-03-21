from __future__ import annotations

import json
import shutil
from uuid import uuid4

import pytest

from tests.constants import PROJECT_ROOT
from vaultspec_core.config import reset_config
from vaultspec_core.core.commands import install_run


@pytest.mark.unit
def test_init_run_scaffolds_antigravity_workspace_layout() -> None:
    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"init-run-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        # install_run bootstraps its own context
        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        assert (tmp_path / ".agents" / "rules").is_dir()
        assert (tmp_path / ".agents" / "workflows").is_dir()
        assert (tmp_path / ".agents" / "skills").is_dir()
        assert (tmp_path / ".codex" / "config.toml").is_file()
        assert not (tmp_path / ".agents" / "agents").exists()
        mcp_config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp_config["mcpServers"]["vaultspec-core"]
        assert server["command"] == "uv"
        assert server["args"] == ["run", "vaultspec-mcp"]
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)
