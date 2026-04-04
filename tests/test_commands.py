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
        expected = ["run", "python", "-m", "vaultspec_core.mcp_server.app"]
        assert server["args"] == expected
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_install_run_scaffolds_precommit_config() -> None:
    import yaml

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"install-precommit-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        # install_run bootstraps its own context
        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        precommit_path = tmp_path / ".pre-commit-config.yaml"
        assert precommit_path.is_file()

        config = yaml.safe_load(precommit_path.read_text(encoding="utf-8"))
        repos = config.get("repos", [])
        assert len(repos) == 1

        local_repo = repos[0]
        assert local_repo.get("repo") == "local"

        hooks = local_repo.get("hooks", [])
        hook_ids = {h.get("id") for h in hooks}

        assert "vault-doctor" in hook_ids
        assert "vault-doctor-deep" in hook_ids

    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)
