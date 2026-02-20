"""Tests for the SessionLogger and cleanup_old_logs."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from core.config import reset_config

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _fresh_config():
    """Reset config singleton between tests."""
    reset_config()
    yield
    reset_config()


class TestSessionLogger:
    """Tests for orchestration.session_logger.SessionLogger."""

    def test_creates_log_directory(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        from orchestration.session_logger import SessionLogger

        logger = SessionLogger(tmp_path, "test-agent", task_id="abcd1234-0000")
        assert logger.log_dir.exists()
        assert logger.log_dir == tmp_path / ".vault" / "logs"

    def test_filename_format(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        from orchestration.session_logger import SessionLogger

        logger = SessionLogger(tmp_path, "my-agent", task_id="deadbeef-1234-5678")
        name = logger.log_file.name
        # Format: YYYY-MM-DDTHH-MM-SS_my-agent_deadbeef.jsonl
        assert name.endswith(".jsonl")
        assert "_my-agent_" in name
        assert "_deadbeef." in name

    def test_session_start_header(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        from orchestration.session_logger import SessionLogger

        logger = SessionLogger(tmp_path, "test-agent", task_id="abcd1234-0000")
        content = logger.log_file.read_text(encoding="utf-8").strip()
        entry = json.loads(content)
        assert entry["type"] == "session_start"
        assert entry["data"]["agent_name"] == "test-agent"
        assert entry["data"]["task_id"] == "abcd1234-0000"
        assert "start_time" in entry["data"]
        assert "root_dir" in entry["data"]

    def test_log_appends_jsonl(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        from orchestration.session_logger import SessionLogger

        logger = SessionLogger(tmp_path, "test-agent", task_id="abcd1234")
        logger.log("session_update", {"key": "value"})
        lines = logger.log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2  # session_start + session_update
        second = json.loads(lines[1])
        assert second["type"] == "session_update"
        assert second["data"]["key"] == "value"

    def test_log_path_workspace_relative(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        from orchestration.session_logger import SessionLogger

        logger = SessionLogger(tmp_path, "test-agent", task_id="abcd1234")
        rel = logger.log_path
        # Should be relative, starting with .vault/logs/
        assert ".vault" in rel
        assert "logs" in rel
        assert not Path(rel).is_absolute()

    def test_auto_generates_task_id(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        from orchestration.session_logger import SessionLogger

        logger = SessionLogger(tmp_path, "test-agent")
        assert logger._task_id is not None
        assert len(logger._task_id) > 8


class TestCleanupOldLogs:
    """Tests for cleanup_old_logs."""

    def test_deletes_old_files(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        monkeypatch.setenv("VAULTSPEC_LOG_RETENTION_DAYS", "7")
        from orchestration.session_logger import cleanup_old_logs

        log_dir = tmp_path / ".vault" / "logs"
        log_dir.mkdir(parents=True)
        # Old file (40 days ago)
        old = log_dir / "2025-01-01T00-00-00_agent_abcd1234.jsonl"
        old.write_text("{}\n")
        # Recent file (today)
        now = datetime.datetime.now(datetime.UTC)
        ts = now.strftime("%Y-%m-%dT%H-%M-%S")
        recent = log_dir / f"{ts}_agent_efgh5678.jsonl"
        recent.write_text("{}\n")

        deleted = cleanup_old_logs(tmp_path)
        assert deleted == 1
        assert not old.exists()
        assert recent.exists()

    def test_ignores_non_jsonl(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        monkeypatch.setenv("VAULTSPEC_LOG_RETENTION_DAYS", "1")
        from orchestration.session_logger import cleanup_old_logs

        log_dir = tmp_path / ".vault" / "logs"
        log_dir.mkdir(parents=True)
        txt = log_dir / "2025-01-01T00-00-00_agent_abcd.txt"
        txt.write_text("not a log\n")
        deleted = cleanup_old_logs(tmp_path)
        assert deleted == 0
        assert txt.exists()

    def test_returns_zero_when_no_dir(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("VAULTSPEC_DOCS_DIR", ".vault")
        monkeypatch.setenv("VAULTSPEC_LOGS_DIR", "logs")
        from orchestration.session_logger import cleanup_old_logs

        assert cleanup_old_logs(tmp_path) == 0


class TestDocTypeLogs:
    """Verify LOGS is recognized in vault structure."""

    def test_logs_is_valid_doctype(self):
        from vault.models import DocType, VaultConstants

        assert DocType.LOGS == "logs"
        assert "logs" in VaultConstants.SUPPORTED_DIRECTORIES

    def test_validate_vault_structure_accepts_logs(self, tmp_path: Path):
        from vault.models import VaultConstants

        logs_dir = tmp_path / ".vault" / "logs"
        logs_dir.mkdir(parents=True)
        errors = VaultConstants.validate_vault_structure(tmp_path)
        assert not any("logs" in e for e in errors)
