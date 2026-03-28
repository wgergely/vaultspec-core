"""Tests for the v2.0 manifest module."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.manifest import (
    MANIFEST_VERSION,
    ManifestData,
    add_providers,
    read_manifest,
    read_manifest_data,
    remove_provider,
    write_manifest,
    write_manifest_data,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


def _manifest_path(root: Path) -> Path:
    return root / ".vaultspec" / "providers.json"


def _write_raw(root: Path, payload: dict) -> None:
    path = _manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class TestReadManifestData:
    def test_missing_file_returns_default(self, tmp_path):
        data = read_manifest_data(tmp_path)
        assert data.installed == set()
        assert data.version == "2.0"
        assert data.serial == 0

    def test_malformed_json_returns_default(self, tmp_path):
        path = _manifest_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")

        data = read_manifest_data(tmp_path)
        assert data.installed == set()
        assert data.serial == 0

    def test_v1_manifest_gets_defaults_for_new_fields(self, tmp_path):
        _write_raw(tmp_path, {"installed": ["claude", "gemini"]})

        data = read_manifest_data(tmp_path)
        assert data.installed == {"claude", "gemini"}
        assert data.version == "1.0"
        assert data.vaultspec_version == ""
        assert data.installed_at == ""
        assert data.serial == 0
        assert data.provider_state == {}
        assert data.gitignore_managed is False

    def test_v2_manifest_all_fields(self, tmp_path):
        payload = {
            "version": "2.0",
            "vaultspec_version": "0.1.4",
            "installed_at": "2026-03-27T12:00:00Z",
            "serial": 5,
            "installed": ["claude"],
            "provider_state": {"claude": {"synced": "true"}},
            "gitignore_managed": True,
        }
        _write_raw(tmp_path, payload)

        data = read_manifest_data(tmp_path)
        assert data.version == "2.0"
        assert data.vaultspec_version == "0.1.4"
        assert data.installed_at == "2026-03-27T12:00:00Z"
        assert data.serial == 5
        assert data.installed == {"claude"}
        assert data.provider_state == {"claude": {"synced": "true"}}
        assert data.gitignore_managed is True


class TestWriteManifestData:
    def test_creates_valid_json(self, tmp_path):
        data = ManifestData(
            installed={"claude", "gemini"},
            vaultspec_version="0.1.4",
        )
        write_manifest_data(tmp_path, data)

        raw = json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert raw["version"] == MANIFEST_VERSION
        assert raw["vaultspec_version"] == "0.1.4"
        assert sorted(raw["installed"]) == ["claude", "gemini"]
        assert raw["gitignore_managed"] is False

    def test_auto_increments_serial(self, tmp_path):
        data = ManifestData(serial=3)
        write_manifest_data(tmp_path, data)

        raw = json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert raw["serial"] == 4

    def test_forces_current_version(self, tmp_path):
        data = ManifestData(version="1.0")
        write_manifest_data(tmp_path, data)

        raw = json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert raw["version"] == MANIFEST_VERSION


class TestBackwardCompat:
    def test_read_manifest_returns_set(self, tmp_path):
        _write_raw(tmp_path, {"installed": ["claude", "gemini"]})
        result = read_manifest(tmp_path)
        assert isinstance(result, set)
        assert result == {"claude", "gemini"}

    def test_write_manifest_accepts_set(self, tmp_path):
        write_manifest(tmp_path, {"claude"})
        result = read_manifest(tmp_path)
        assert result == {"claude"}

    def test_write_manifest_preserves_v2_fields(self, tmp_path):
        payload = {
            "version": "2.0",
            "vaultspec_version": "0.1.4",
            "installed_at": "2026-03-27T12:00:00Z",
            "serial": 2,
            "installed": ["claude"],
            "provider_state": {"claude": {"synced": "true"}},
            "gitignore_managed": True,
        }
        _write_raw(tmp_path, payload)

        write_manifest(tmp_path, {"claude", "gemini"})

        data = read_manifest_data(tmp_path)
        assert data.vaultspec_version == "0.1.4"
        assert data.installed_at == "2026-03-27T12:00:00Z"
        assert data.provider_state == {"claude": {"synced": "true"}}
        assert data.gitignore_managed is True
        assert data.installed == {"claude", "gemini"}


class TestAddProviders:
    def test_adds_to_empty_manifest(self, tmp_path):
        result = add_providers(tmp_path, ["claude"])
        assert result == {"claude"}
        assert read_manifest(tmp_path) == {"claude"}

    def test_preserves_v2_fields(self, tmp_path):
        payload = {
            "version": "2.0",
            "vaultspec_version": "0.1.4",
            "serial": 1,
            "installed": ["claude"],
            "provider_state": {"claude": {"synced": "true"}},
            "gitignore_managed": True,
        }
        _write_raw(tmp_path, payload)

        add_providers(tmp_path, ["gemini"])

        data = read_manifest_data(tmp_path)
        assert data.installed == {"claude", "gemini"}
        assert data.vaultspec_version == "0.1.4"
        assert data.provider_state == {"claude": {"synced": "true"}}
        assert data.gitignore_managed is True
        assert data.serial == 2


class TestRemoveProvider:
    def test_removes_existing(self, tmp_path):
        _write_raw(tmp_path, {"installed": ["claude", "gemini"]})
        result = remove_provider(tmp_path, "claude")
        assert result == {"gemini"}
        assert read_manifest(tmp_path) == {"gemini"}

    def test_preserves_v2_fields(self, tmp_path):
        payload = {
            "version": "2.0",
            "vaultspec_version": "0.1.4",
            "serial": 3,
            "installed": ["claude", "gemini"],
            "provider_state": {"claude": {"synced": "true"}},
            "gitignore_managed": True,
        }
        _write_raw(tmp_path, payload)

        remove_provider(tmp_path, "gemini")

        data = read_manifest_data(tmp_path)
        assert data.installed == {"claude"}
        assert data.vaultspec_version == "0.1.4"
        assert data.provider_state == {"claude": {"synced": "true"}}
        assert data.serial == 4

    def test_remove_nonexistent_is_noop(self, tmp_path):
        _write_raw(tmp_path, {"installed": ["claude"]})
        result = remove_provider(tmp_path, "gemini")
        assert result == {"claude"}

    def test_remove_provider_cleans_provider_state(self, tmp_path):
        payload = {
            "version": "2.0",
            "serial": 1,
            "installed": ["claude", "gemini"],
            "provider_state": {
                "claude": {"synced": "true"},
                "gemini": {"synced": "true"},
            },
        }
        _write_raw(tmp_path, payload)

        remove_provider(tmp_path, "claude")

        data = read_manifest_data(tmp_path)
        assert "claude" not in data.installed
        assert "claude" not in data.provider_state
        assert "gemini" in data.provider_state


class TestMalformedSerial:
    def test_malformed_serial_returns_default(self, tmp_path):
        payload = {
            "version": "2.0",
            "installed": ["claude"],
            "serial": "abc",
        }
        _write_raw(tmp_path, payload)

        data = read_manifest_data(tmp_path)
        # int("abc") raises ValueError - read_manifest_data should not crash
        assert isinstance(data, ManifestData)
        assert data.serial == 0
        assert data.installed == {"claude"}
