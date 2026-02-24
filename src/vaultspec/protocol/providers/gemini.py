"""Agent provider implementation for Google Gemini via the Gemini CLI ACP bridge."""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from ...core.enums import CapabilityLevel, GeminiModels, ModelRegistry
from .base import (
    AgentProvider,
    ProcessSpec,
    resolve_executable,
    resolve_includes,
)

logger = logging.getLogger(__name__)

__all__ = ["GeminiProvider"]

# Features only supported by the Claude provider
_CLAUDE_ONLY_FEATURES = (
    "max_turns",
    "budget",
    "disallowed_tools",
    "effort",
    "fallback_model",
)

_MIN_VERSION_WINDOWS = (0, 9, 0)  # v0.9.0 fixes Windows ACP hang
_MIN_VERSION_RECOMMENDED = (0, 27, 0)  # v0.27.0 has stable agent skills

# Public OAuth client credentials for the Gemini CLI (installed-app pattern).
# Safe to embed: https://developers.google.com/identity/protocols/oauth2#installed
_GEMINI_CLI_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
)
_GEMINI_CLI_CLIENT_SECRET = "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"

# Cache for version check result
_cached_version: tuple[int, ...] | None = None

# Overridable which function for testing
_which_fn: Callable[[str], str | None] = shutil.which

# Overridable default creds path for testing (None → ~/.gemini/oauth_creds.json)
_default_creds_path: pathlib.Path | None = None


def _load_gemini_oauth_creds(
    creds_path: pathlib.Path | None = None,
) -> dict | None:
    """Load ``~/.gemini/oauth_creds.json`` and return its parsed contents.

    Args:
        creds_path: Path to the credentials file. Defaults to
            ``~/.gemini/oauth_creds.json``. Injectable for testing.

    Returns:
        Parsed JSON dict, or ``None`` if the file is missing or unreadable.
    """
    path = (
        creds_path
        or _default_creds_path
        or pathlib.Path.home() / ".gemini" / "oauth_creds.json"
    )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _refresh_gemini_oauth_token(
    creds: dict,
    token_url: str | None = None,
    creds_path: pathlib.Path | None = None,
) -> dict | None:
    """Refresh the Gemini OAuth access token using the stored refresh_token.

    Uses the Gemini CLI's public OAuth client credentials as defaults when
    ``client_id`` / ``client_secret`` are absent from the credentials dict
    (the CLI embeds them in its binary rather than storing them on disk).

    On success, writes the updated creds atomically back to the credentials file
    and returns the updated dict. On failure, logs a warning and returns None.

    Args:
        creds: Parsed credentials dict (as returned by
            :func:`_load_gemini_oauth_creds`).
        token_url: OAuth token endpoint URL. Defaults to
            ``https://oauth2.googleapis.com/token``.
        creds_path: Path to write refreshed creds back to. Defaults to
            ``~/.gemini/oauth_creds.json``.

    Returns:
        Updated credentials dict with a fresh ``access_token`` and
        ``expiry_date``, or ``None`` on any failure.
    """
    url = token_url or "https://oauth2.googleapis.com/token"
    refresh_token = creds.get("refresh_token")
    client_id = creds.get("client_id", _GEMINI_CLI_CLIENT_ID)
    client_secret = creds.get("client_secret", _GEMINI_CLI_CLIENT_SECRET)

    if not refresh_token:
        logger.warning(
            "Gemini OAuth token refresh skipped: missing refresh_token in credentials."
        )
        return None

    payload = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()

    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                logger.warning(
                    "Gemini OAuth token refresh failed: HTTP %s."
                    " Subprocess may fail to authenticate.",
                    resp.status,
                )
                return None
            response_data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning(
            "Gemini OAuth token refresh failed: %s."
            " Subprocess may fail to authenticate.",
            exc,
        )
        return None

    updated = dict(creds)
    updated["access_token"] = response_data.get(
        "access_token", creds.get("access_token")
    )
    expires_in = response_data.get("expires_in", 3600)
    now_ms = int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)
    updated["expiry_date"] = now_ms + int(expires_in) * 1000

    # Atomic write-back
    target = creds_path or pathlib.Path.home() / ".gemini" / "oauth_creds.json"
    tmp = target.parent / f".oauth_creds_tmp_{uuid.uuid4().hex[:8]}.json"
    try:
        tmp.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    except Exception as exc:
        logger.warning("Gemini OAuth creds write-back failed: %s", exc)
        with contextlib.suppress(Exception):
            tmp.unlink(missing_ok=True)
        return None

    return updated


def _is_gemini_token_expired(creds: dict) -> bool:
    """Return True if the OAuth access_token expires within 5 minutes.

    Gemini CLI stores ``expiry_date`` as milliseconds since Unix epoch.

    Args:
        creds: Parsed credentials dict containing an ``expiry_date`` key
            (milliseconds since epoch).

    Returns:
        ``True`` if the token is absent, unparseable, or expires within
        300 seconds; ``False`` otherwise.
    """
    expiry_ms = creds.get("expiry_date")
    if expiry_ms is None:
        return True
    try:
        expiry_s = int(expiry_ms) / 1000
    except (TypeError, ValueError):
        return True
    now_s = datetime.datetime.now(datetime.UTC).timestamp()
    return expiry_s <= now_s + 300


class GeminiProvider(AgentProvider):
    """Provider for Google Gemini models via the Gemini CLI ACP bridge.

    Spawns ``vaultspec.protocol.acp.gemini_bridge`` as a subprocess and
    handles OAuth credential refresh, system-prompt temp-file injection, and
    environment variable forwarding for Gemini-specific agent features.
    """

    @property
    def name(self) -> str:
        """Return the provider identifier string.

        Returns:
            The string ``"gemini"``.
        """
        return "gemini"

    @property
    def models(self) -> ModelRegistry:
        """Return the Gemini model registry.

        Returns:
            The :class:`GeminiModels` registry class.
        """
        return GeminiModels

    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load ``.gemini/SYSTEM.md`` if it exists (deployed by CLI sync).

        Args:
            root_dir: Workspace root directory.

        Returns:
            File contents as a string, or an empty string if the file is absent.
        """
        system_file = root_dir / ".gemini" / "SYSTEM.md"
        if not system_file.exists():
            return ""
        return system_file.read_text(encoding="utf-8")

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Load and inline-resolve rules from ``.gemini/rules/``.

        All ``*.md`` files in the rules directory are read in sorted order and
        their ``@include`` directives are resolved recursively.

        Args:
            root_dir: Workspace root directory.

        Returns:
            Concatenated rules text, or an empty string if the directory does
            not exist.
        """
        rules_dir = root_dir / ".gemini" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            content = rule_file.read_text(encoding="utf-8")
            resolved = resolve_includes(content, rules_dir, root_dir)
            all_rules.append(resolved)

        return "\n\n".join(all_rules)

    @staticmethod
    def check_version(
        executable: str, *, run_fn: Callable[..., Any] | None = None
    ) -> tuple[int, ...] | None:
        """Check Gemini CLI version and warn/fail based on known-good baselines.

        Args:
            executable: Path or name of the ``gemini`` CLI binary to check.
            run_fn: Replacement for ``subprocess.run`` (injectable for testing).

        Returns:
            Parsed version tuple (e.g. ``(0, 27, 0)``), or ``None`` if the
            version could not be determined.

        Raises:
            RuntimeError: If the CLI version is below the Windows minimum
                (:data:`_MIN_VERSION_WINDOWS`) when running on Windows.
        """
        global _cached_version
        if _cached_version:
            return _cached_version

        _run = run_fn or subprocess.run
        exe, prefix = resolve_executable(executable)
        try:
            res = _run(
                [exe, *prefix, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            # Match "gemini v0.27.0" or just "v0.27.0"
            match = re.search(r"v(\d+)\.(\d+)\.(\d+)", res.stdout)
            if not match:
                return None

            version = tuple(int(x) for x in match.groups())
            _cached_version = version

            # Enforcement
            if sys.platform == "win32" and version < _MIN_VERSION_WINDOWS:
                msg = (
                    f"Gemini CLI version {version} is below minimum "
                    f"{_MIN_VERSION_WINDOWS} for Windows."
                )
                raise RuntimeError(msg)

            return version
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            return None

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: str | None = None,
        mode: str = "read-write",
        mcp_servers: dict[str, Any] | None = None,
        *,
        creds_path: pathlib.Path | None = None,
    ) -> ProcessSpec:
        """Build a ProcessSpec for launching the Gemini CLI ACP bridge subprocess.

        Validates the Gemini CLI version, loads system prompt and rules,
        performs OAuth token refresh if needed, writes the system prompt to a
        temporary file for ``GEMINI_SYSTEM_MD``, selects the appropriate model,
        and maps agent YAML metadata to environment variables consumed by the bridge.

        Args:
            agent_name: Name of the agent being dispatched (unused but kept
                for interface consistency).
            agent_meta: Parsed metadata from the agent's YAML front matter.
            agent_persona: Agent persona / behavioural instructions.
            task_context: Initial task description passed to the agent.
            root_dir: Workspace root directory.
            model_override: Optional model ID to use instead of the tier
                default derived from ``agent_meta``.
            mode: Sandbox mode forwarded to the bridge (``"read-only"`` or
                ``"read-write"``).
            creds_path: Override path for the Gemini OAuth credentials file.
                Defaults to ``~/.gemini/oauth_creds.json``. Injectable for testing.
            mcp_servers: Optional MCP server configurations forwarded to the bridge.

        Returns:
            ProcessSpec ready for the orchestration layer to spawn.

        Raises:
            RuntimeError: If the Gemini CLI is below the minimum supported version
                on Windows.
        """
        _ = agent_name

        # Warn on Claude-only features
        for key in _CLAUDE_ONLY_FEATURES:
            if agent_meta.get(key):
                logger.warning(
                    "Feature '%s' is not supported by %s provider; ignoring",
                    key,
                    self.name,
                )

        # Validate Gemini CLI is available and meets minimum version.
        # The bridge spawns the CLI internally, but we fail fast here.
        _raw_executable = _which_fn("gemini") or "gemini"
        self.check_version(_raw_executable)

        # Load system instructions, rules, and construct full prompt
        system_instructions = self.load_system_prompt(root_dir)
        rules = self.load_rules(root_dir)
        system_prompt = self.construct_system_prompt(
            agent_persona,
            rules,
            system_instructions,
        )

        # Prepare Environment
        env = os.environ.copy()

        # Auth wrangling — see
        # .vault/adr/2026-02-21-gemini-provider-auth-strategy-adr.md
        if "GEMINI_API_KEY" in env:
            logger.debug(
                "GEMINI_API_KEY present — using API key path, skipping OAuth wrangling"
            )
        elif (creds := _load_gemini_oauth_creds(creds_path)) is not None:
            if _is_gemini_token_expired(creds):
                logger.debug(
                    "Gemini OAuth token expired or near expiry — attempting refresh"
                )
                refreshed = _refresh_gemini_oauth_token(creds, creds_path=creds_path)
                if refreshed is None:
                    logger.warning(
                        "Gemini OAuth token refresh failed."
                        " Subprocess may fail to authenticate."
                    )
                else:
                    logger.debug("Gemini OAuth token refreshed successfully")
            else:
                logger.debug("Gemini OAuth credentials valid — no refresh needed")
        else:
            logger.warning(
                "No Gemini authentication found. Set GEMINI_API_KEY (from AI Studio) "
                "or run 'gemini auth login' to create ~/.gemini/oauth_creds.json. "
                "The subprocess may hang waiting for interactive auth."
            )

        cleanup_paths: list[pathlib.Path] = []

        # Write system prompt to temp file for GEMINI_SYSTEM_MD.
        # The bridge forwards GEMINI_* env vars to the child CLI process.
        if system_prompt:
            from ...config import get_config

            tmp_dir = root_dir / get_config().framework_dir / ".tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            system_file = tmp_dir / f"system-{uuid.uuid4().hex[:8]}.md"
            system_file.write_text(system_prompt, encoding="utf-8")
            env["GEMINI_SYSTEM_MD"] = str(system_file)
            cleanup_paths.append(system_file)

        # Determine Model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        # Bridge configuration via environment variables.
        # The bridge reads these in its constructor and forwards them
        # to the child Gemini CLI process as appropriate flags.
        env["VAULTSPEC_ROOT_DIR"] = str(root_dir)
        env["VAULTSPEC_AGENT_MODE"] = mode

        if agent_meta.get("allowed_tools"):
            env["VAULTSPEC_ALLOWED_TOOLS"] = agent_meta["allowed_tools"]

        approval = agent_meta.get("approval_mode")
        if approval and approval != "default":
            env["VAULTSPEC_GEMINI_APPROVAL_MODE"] = approval

        fmt = agent_meta.get("output_format")
        if fmt and fmt != "text":
            env["VAULTSPEC_OUTPUT_FORMAT"] = fmt

        include_dirs = agent_meta.get("include_dirs", "")
        if include_dirs:
            validated = self._validate_include_dirs(include_dirs, root_dir)
            if validated:
                env["VAULTSPEC_INCLUDE_DIRS"] = ",".join(validated)

        return ProcessSpec(
            executable=sys.executable,
            args=[
                "-m",
                "vaultspec",
                "subagent",
                "--root",
                str(root_dir),  # Ensure proper workspace context
                "a2a-serve",
                "--executor",
                self.name,
                "--model",
                model,
                "--agent",
                agent_name,
                "--port",
                "0",
            ],
            env=env,
            cleanup_paths=cleanup_paths,
            initial_prompt_override=task_context,
            session_meta={"model": model},
            mcp_servers=mcp_servers,
            protocol="a2a",
        )
