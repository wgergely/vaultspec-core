from __future__ import annotations

import pytest

from tests._windows_temp_compat import install_windows_temp_compat
from vaultspec_core.config import VaultSpecConfig, get_config, reset_config
from vaultspec_core.testing import CorpusManifest, build_synthetic_vault

install_windows_temp_compat()


@pytest.fixture(scope="session")
def synthetic_vault(tmp_path_factory) -> CorpusManifest:
    """Read-only baseline synthetic vault shared across tests.

    Generated once per session into ``tmp_path_factory.mktemp("vault")``.
    Tests that need to mutate the corpus must request a function-scoped
    variant or build their own via ``build_synthetic_vault(tmp_path, ...)``.
    """
    root = tmp_path_factory.mktemp("vault")
    return build_synthetic_vault(root, n_docs=24, seed=42)


@pytest.fixture
def vaultspec_config():
    """Provide a fresh VaultSpecConfig from current environment.

    Resets the singleton before and after to ensure test isolation.
    """
    reset_config()
    cfg = get_config()
    yield cfg
    reset_config()


@pytest.fixture
def config_override():
    """Factory fixture: call with overrides dict to get a custom config.

    Example::

        def test_custom_port(config_override):
            cfg = config_override({"mcp_port": 9999})
            assert cfg.mcp_port == 9999
    """
    created: list[VaultSpecConfig] = []

    def _make(overrides: dict) -> VaultSpecConfig:
        cfg = VaultSpecConfig.from_environment(overrides=overrides)
        created.append(cfg)
        return cfg

    yield _make
    reset_config()


@pytest.fixture
def clean_config():
    """Reset the config singleton before and after the test."""
    reset_config()
    yield
    reset_config()
