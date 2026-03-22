"""Tests for dev-repo protection guard."""

import pytest

from vaultspec_core.core.guards import (
    DevRepoProtectionError,
    _cached_is_dev_repo,
    guard_dev_repo,
    is_dev_repo,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the LRU cache between tests."""
    _cached_is_dev_repo.cache_clear()
    yield
    _cached_is_dev_repo.cache_clear()


# ── is_dev_repo ────────────────────────────────────────────────────


def test_detects_dev_repo_with_matching_pyproject(tmp_path):
    """A pyproject.toml with name = 'vaultspec-core' triggers detection."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "vaultspec-core"\n', encoding="utf-8")
    assert is_dev_repo(tmp_path) is True


def test_ignores_dir_without_pyproject(tmp_path):
    """A directory without pyproject.toml is not the dev repo."""
    assert is_dev_repo(tmp_path) is False


def test_ignores_different_project_name(tmp_path):
    """A pyproject.toml with a different project name is not the dev repo."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "my-cool-project"\n', encoding="utf-8")
    assert is_dev_repo(tmp_path) is False


def test_ignores_malformed_pyproject(tmp_path):
    """A malformed pyproject.toml does not cause a crash."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("this is not valid toml {{{{", encoding="utf-8")
    assert is_dev_repo(tmp_path) is False


def test_ignores_pyproject_without_project_table(tmp_path):
    """A pyproject.toml with no [project] table is not the dev repo."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[build-system]\nrequires = ["hatchling"]\n', encoding="utf-8")
    assert is_dev_repo(tmp_path) is False


# ── guard_dev_repo ─────────────────────────────────────────────────


def test_guard_raises_on_dev_repo(tmp_path):
    """guard_dev_repo raises DevRepoProtectionError for the dev repo."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "vaultspec-core"\n', encoding="utf-8")
    with pytest.raises(DevRepoProtectionError, match="source repository"):
        guard_dev_repo(tmp_path)


def test_guard_passes_on_normal_dir(tmp_path):
    """guard_dev_repo does not raise for a normal project directory."""
    guard_dev_repo(tmp_path)


def test_guard_respects_env_override(tmp_path, monkeypatch):
    """The VAULTSPEC_ALLOW_DEV_WRITES env var bypasses the guard."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "vaultspec-core"\n', encoding="utf-8")

    monkeypatch.setenv("VAULTSPEC_ALLOW_DEV_WRITES", "1")
    guard_dev_repo(tmp_path)  # should not raise


def test_guard_env_override_truthy_values(tmp_path, monkeypatch):
    """All documented truthy values bypass the guard."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "vaultspec-core"\n', encoding="utf-8")

    for val in ("1", "true", "yes", "True", "YES"):
        _cached_is_dev_repo.cache_clear()
        monkeypatch.setenv("VAULTSPEC_ALLOW_DEV_WRITES", val)
        guard_dev_repo(tmp_path)  # should not raise


def test_guard_env_override_falsy_does_not_bypass(tmp_path, monkeypatch):
    """Non-truthy env values do not bypass the guard."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "vaultspec-core"\n', encoding="utf-8")

    monkeypatch.setenv("VAULTSPEC_ALLOW_DEV_WRITES", "0")
    with pytest.raises(DevRepoProtectionError):
        guard_dev_repo(tmp_path)
