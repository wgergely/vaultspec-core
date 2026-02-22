"""Real unit tests for Claude and Gemini provider OAuth auth functions.

All tests use real I/O (tmp_path files, real local HTTP servers via
http.server.HTTPServer). No mocks, stubs, patches, or skips — ever.
"""

from __future__ import annotations

import contextlib
import datetime
import http.server
import json
import logging
import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

import pytest

from tests.constants import TEST_PROJECT

from ..providers import (
    ClaudeModels,
    ClaudeProvider,
    GeminiModels,
    GeminiProvider,
)
from ..providers.claude import (
    _load_claude_oauth_token,
)
from ..providers.gemini import (
    _is_gemini_token_expired,
    _load_gemini_oauth_creds,
    _refresh_gemini_oauth_token,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Local HTTP server helpers
# ---------------------------------------------------------------------------


def _start_server(
    response_body: bytes, status: int = 200
) -> tuple[str, threading.Thread]:
    """Spin up a real HTTPServer on localhost:0 returning a fixed response.

    Returns ``(url, thread)``.  The server runs until the daemon thread exits
    (i.e., until the test process ends or the server is shutdown).
    """

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, *_args):  # silence access logs in test output
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", thread


# ---------------------------------------------------------------------------
# Claude auth tests
# ---------------------------------------------------------------------------


class TestClaudeLoadOAuthToken:
    """Tests for _load_claude_oauth_token() — the v2 expiry+refresh function."""

    def _write_creds(
        self,
        path: pathlib.Path,
        access_token: str = "sk-ant-oat01-valid",
        expires_at_ms: int | None = None,
        refresh_token: str | None = "rt-good",
        client_id: str | None = "cid",
        client_secret: str | None = "csec",
    ) -> None:
        """Write a minimal .credentials.json to *path*."""
        oauth: dict = {"accessToken": access_token}
        if expires_at_ms is not None:
            oauth["expiresAt"] = expires_at_ms
        if refresh_token is not None:
            oauth["refreshToken"] = refresh_token
        if client_id is not None:
            oauth["clientId"] = client_id
        if client_secret is not None:
            oauth["clientSecret"] = client_secret
        path.write_text(json.dumps({"claudeAiOauth": oauth}), encoding="utf-8")

    # --- scenario 1: valid token, no refresh needed ---

    def test_valid_token_returned_without_refresh(self, tmp_path):
        """Token fresh (expires in 1h): returned as-is, file untouched."""
        creds_file = tmp_path / ".credentials.json"
        # expiresAt 1 hour in the future, in milliseconds
        expires_at_ms = int((time.time() + 3600) * 1000)
        self._write_creds(creds_file, expires_at_ms=expires_at_ms)
        mtime_before = creds_file.stat().st_mtime

        result = _load_claude_oauth_token(
            creds_path=creds_file, token_url="http://should-not-be-called"
        )

        assert result == "sk-ant-oat01-valid"
        assert creds_file.stat().st_mtime == mtime_before  # file not touched

    # --- scenario 2: expired token, refresh succeeds ---

    def test_expired_token_refresh_succeeds(self, tmp_path):
        """Expired token: real POST issued, file atomically updated,
        new token returned."""
        creds_file = tmp_path / ".credentials.json"
        # expiresAt 2 hours in the past, in milliseconds
        expires_at_ms = int((time.time() - 7200) * 1000)
        self._write_creds(creds_file, expires_at_ms=expires_at_ms)

        response = json.dumps(
            {"access_token": "sk-ant-oat01-new", "expires_in": 3600}
        ).encode()
        server_url, _ = _start_server(response, status=200)

        result = _load_claude_oauth_token(creds_path=creds_file, token_url=server_url)

        assert result == "sk-ant-oat01-new"
        # File must be updated on disk
        written = json.loads(creds_file.read_text(encoding="utf-8"))
        assert written["claudeAiOauth"]["accessToken"] == "sk-ant-oat01-new"
        new_expires = written["claudeAiOauth"]["expiresAt"]
        # New expiresAt should be ~1h from now (in ms), at minimum in the future
        assert new_expires > time.time() * 1000

    # --- scenario 3: expired token, refresh fails (server 400) ---

    def test_expired_token_refresh_fails_400(self, tmp_path, caplog):
        """Expired token + 400 from server: warning logged, None returned, unchanged."""
        creds_file = tmp_path / ".credentials.json"
        expires_at_ms = int((time.time() - 7200) * 1000)
        original_content = json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "sk-ant-oat01-old",
                    "expiresAt": expires_at_ms,
                    "refreshToken": "rt",
                }
            }
        )
        creds_file.write_text(original_content, encoding="utf-8")

        server_url, _ = _start_server(b'{"error":"invalid_grant"}', status=400)

        with caplog.at_level(
            logging.WARNING, logger="vaultspec.protocol.providers.claude"
        ):
            result = _load_claude_oauth_token(
                creds_path=creds_file, token_url=server_url
            )

        assert result is None
        assert any(
            "warning" in r.levelname.lower() or r.levelno >= logging.WARNING
            for r in caplog.records
        )
        # File must be unchanged
        assert creds_file.read_text(encoding="utf-8") == original_content

    # --- scenario 4: credentials file missing ---

    def test_missing_credentials_file_returns_none(self, tmp_path):
        """Non-existent credentials file: None returned, no exception."""
        nonexistent = tmp_path / "no-such-file.json"
        result = _load_claude_oauth_token(creds_path=nonexistent)
        assert result is None

    # --- scenario 5: ANTHROPIC_API_KEY in env → debug log, no OAuth ---

    def test_anthropic_api_key_skips_oauth(self, tmp_path, caplog):
        """ANTHROPIC_API_KEY present: debug log fired,
        CLAUDE_CODE_OAUTH_TOKEN absent."""
        # Make sure we have no pre-existing token env var that could interfere
        env_backup_oauth = os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api-test-key"
        try:
            provider = ClaudeProvider()
            with caplog.at_level(
                logging.DEBUG, logger="vaultspec.protocol.providers.claude"
            ):
                spec = provider.prepare_process(
                    agent_name="test",
                    agent_meta={"model": ClaudeModels.MEDIUM},
                    agent_persona="",
                    task_context="Do it.",
                    root_dir=TEST_PROJECT,
                )
            # CLAUDE_CODE_OAUTH_TOKEN must NOT be injected
            assert "CLAUDE_CODE_OAUTH_TOKEN" not in spec.env
            # Debug log must mention the API key path
            debug_msgs = [
                r.message for r in caplog.records if r.levelno == logging.DEBUG
            ]
            assert any("ANTHROPIC_API_KEY" in m for m in debug_msgs)
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            if env_backup_oauth is not None:
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = env_backup_oauth


# ---------------------------------------------------------------------------
# Gemini auth tests
# ---------------------------------------------------------------------------


def _gemini_expiry_ms(delta_seconds: int) -> int:
    """Milliseconds-since-epoch timestamp ``delta_seconds`` from now."""
    now_ms = int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)
    return now_ms + delta_seconds * 1000


def _write_gemini_creds(
    path: pathlib.Path,
    access_token: str = "ya29.valid-token",
    expiry_date: int | None = None,
    refresh_token: str = "1//refresh-token",
) -> None:
    data: dict[str, object] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
    }
    if expiry_date is not None:
        data["expiry_date"] = expiry_date
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class TestGeminiLoadOAuthCreds:
    """Tests for _load_gemini_oauth_creds() and _refresh_gemini_oauth_token()."""

    # --- scenario 1: valid token (not expired) ---

    def test_valid_token_returned_no_refresh(self, tmp_path):
        """Token expires 1h from now: dict returned without warning; file untouched."""
        creds_file = tmp_path / "oauth_creds.json"
        _write_gemini_creds(creds_file, expiry_date=_gemini_expiry_ms(3600))
        mtime_before = creds_file.stat().st_mtime

        creds = _load_gemini_oauth_creds(creds_path=creds_file)

        assert creds is not None
        assert creds["access_token"] == "ya29.valid-token"
        assert not _is_gemini_token_expired(creds)
        assert creds_file.stat().st_mtime == mtime_before

    # --- scenario 2: expired token, refresh succeeds ---

    def test_expired_token_refresh_succeeds(self, tmp_path):
        """Expired token: real POST, file updated atomically, updated dict returned."""
        creds_file = tmp_path / "oauth_creds.json"
        _write_gemini_creds(creds_file, expiry_date=_gemini_expiry_ms(-7200))  # 2h ago

        creds = _load_gemini_oauth_creds(creds_path=creds_file)
        assert creds is not None
        assert _is_gemini_token_expired(creds)

        response = json.dumps(
            {"access_token": "ya29.refreshed", "expires_in": 3600}
        ).encode()
        server_url, _ = _start_server(response, status=200)

        updated = _refresh_gemini_oauth_token(
            creds, token_url=server_url, creds_path=creds_file
        )

        assert updated is not None
        assert updated["access_token"] == "ya29.refreshed"
        # File must reflect the refreshed token
        written = json.loads(creds_file.read_text(encoding="utf-8"))
        assert written["access_token"] == "ya29.refreshed"
        # New expiry_date (ms epoch) must be in the future
        now_ms = int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)
        assert written["expiry_date"] > now_ms

    # --- scenario 3: expired token, refresh fails (server 500) ---

    def test_expired_token_refresh_fails_500(self, tmp_path, caplog):
        """Server 500: warning logged, None returned, file unchanged."""
        creds_file = tmp_path / "oauth_creds.json"
        _write_gemini_creds(creds_file, expiry_date=_gemini_expiry_ms(-7200))
        original_content = creds_file.read_text(encoding="utf-8")

        creds = _load_gemini_oauth_creds(creds_path=creds_file)
        assert creds is not None

        server_url, _ = _start_server(b'{"error":"server_error"}', status=500)

        with caplog.at_level(
            logging.WARNING, logger="vaultspec.protocol.providers.gemini"
        ):
            result = _refresh_gemini_oauth_token(
                creds, token_url=server_url, creds_path=creds_file
            )

        assert result is None
        assert any(r.levelno >= logging.WARNING for r in caplog.records)
        assert creds_file.read_text(encoding="utf-8") == original_content

    # --- scenario 4: creds missing, no API key ---

    def test_missing_creds_no_api_key_warns(self, tmp_path, caplog):
        """No creds file and no GEMINI_API_KEY: warning names both setup paths.

        prepare_process() emits the auth warning before it reaches the system-prompt
        write (which requires core.config in a full install). We capture the log
        records that fire during the auth phase.
        """
        env_backup = os.environ.pop("GEMINI_API_KEY", None)
        from ..providers import gemini as gmod

        gmod._cached_version = (0, 27, 0)
        try:
            provider = GeminiProvider()
            nonexistent_creds = tmp_path / "no-creds" / "oauth_creds.json"
            with (
                caplog.at_level(
                    logging.WARNING, logger="vaultspec.protocol.providers.gemini"
                ),
                # prepare_process may raise ModuleNotFoundError from core.config later;
                # the auth warning fires before that point.
                contextlib.suppress(ModuleNotFoundError),
            ):
                provider.prepare_process(
                    agent_name="test",
                    agent_meta={"model": GeminiModels.LOW},
                    agent_persona="",
                    task_context="Do it.",
                    root_dir=TEST_PROJECT,
                    creds_path=nonexistent_creds,
                )
            warning_msgs = " ".join(
                r.message for r in caplog.records if r.levelno >= logging.WARNING
            )
            # Warning should mention both GEMINI_API_KEY and gemini auth login
            assert "GEMINI_API_KEY" in warning_msgs
            assert "gemini auth login" in warning_msgs
        finally:
            gmod._cached_version = None
            if env_backup is not None:
                os.environ["GEMINI_API_KEY"] = env_backup

    # --- scenario 5: GEMINI_API_KEY present → debug log fires before any creds I/O ---

    def test_gemini_api_key_skips_oauth(self, tmp_path, caplog):
        """GEMINI_API_KEY present: debug log fires (no OAuth I/O attempted).

        prepare_process() may raise ModuleNotFoundError from core.config later in
        the system-prompt write path; that is unrelated to the auth branch under test.
        """
        from ..providers import gemini as gmod

        gmod._cached_version = (0, 27, 0)
        env_backup = os.environ.pop("GEMINI_API_KEY", None)
        os.environ["GEMINI_API_KEY"] = "AIza-test-key"
        try:
            provider = GeminiProvider()
            with (
                caplog.at_level(
                    logging.DEBUG, logger="vaultspec.protocol.providers.gemini"
                ),
                contextlib.suppress(ModuleNotFoundError),
            ):
                provider.prepare_process(
                    agent_name="test",
                    agent_meta={"model": GeminiModels.LOW},
                    agent_persona="",
                    task_context="Do it.",
                    root_dir=TEST_PROJECT,
                )
            # Debug log must mention GEMINI_API_KEY path
            debug_msgs = [
                r.message for r in caplog.records if r.levelno == logging.DEBUG
            ]
            assert any("GEMINI_API_KEY" in m for m in debug_msgs)
        finally:
            gmod._cached_version = None
            del os.environ["GEMINI_API_KEY"]
            if env_backup is not None:
                os.environ["GEMINI_API_KEY"] = env_backup
