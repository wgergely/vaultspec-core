"""Agent provider implementation for Anthropic Claude via the Python ACP bridge."""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import (
    AgentProvider,
    CapabilityLevel,
    ClaudeModels,
    ModelRegistry,
    ProcessSpec,
    resolve_includes,
)

logger = logging.getLogger(__name__)

__all__ = ["ClaudeProvider"]

# Features only supported by the Gemini provider
_GEMINI_ONLY_FEATURES = ("approval_mode",)

_DEFAULT_CREDS_PATH = pathlib.Path.home() / ".claude" / ".credentials.json"
_DEFAULT_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
# Proactive refresh buffer: refresh if token expires within 5 minutes
_EXPIRY_BUFFER_SECONDS = 300


def _load_claude_oauth_token(
    creds_path: pathlib.Path | None = None,
    token_url: str | None = None,
) -> str | None:
    """Read and, if necessary, refresh the Claude OAuth access token.

    The child ``claude`` binary spawned by the SDK requires an explicit
    ``CLAUDE_CODE_OAUTH_TOKEN`` env var when ``CLAUDE_CODE_ENTRYPOINT=sdk-py``
    is set — it skips the interactive credentials-file auth flow in that mode.

    If the stored token is absent, expired, or expiring within the refresh
    buffer, a token refresh is attempted using the stored ``refreshToken``.
    On success the refreshed token is written back to the credentials file
    atomically.

    Args:
        creds_path: Path to the Claude credentials JSON file. Defaults to
            ``~/.claude/.credentials.json``. Injectable for testing.
        token_url: OAuth token endpoint URL. Defaults to the Anthropic console
            endpoint. Injectable for testing.

    Returns:
        A valid access token string, or ``None`` if authentication cannot be
        established (missing file, missing refresh token, network error, etc.).
    """
    if creds_path is None:
        creds_path = _DEFAULT_CREDS_PATH
    if token_url is None:
        token_url = _DEFAULT_TOKEN_URL

    try:
        data = json.loads(creds_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return None

    oauth = data.get("claudeAiOauth", {})
    access_token = oauth.get("accessToken")
    expires_at_ms = oauth.get("expiresAt")

    # If we have both a token and a valid expiry, check if still fresh
    if access_token and expires_at_ms is not None:
        # expiresAt is in milliseconds — divide by 1000 to convert to seconds
        expires_at_sec = expires_at_ms / 1000
        if expires_at_sec > time.time() + _EXPIRY_BUFFER_SECONDS:
            return access_token

    # Token absent, expired, or expiring soon — attempt refresh
    refresh_token = oauth.get("refreshToken")
    client_id = oauth.get("clientId")
    client_secret = oauth.get("clientSecret")

    if not refresh_token:
        logger.warning(
            "Claude OAuth token is expired or missing and no refreshToken is available "
            "in %s — child agents may fail to authenticate",
            creds_path,
        )
        return None

    try:
        payload = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                **({"client_id": client_id} if client_id else {}),
                **({"client_secret": client_secret} if client_secret else {}),
            }
        ).encode()
        req = urllib.request.Request(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                logger.warning(
                    "OAuth token refresh returned HTTP %s"
                    " — child agents may fail to authenticate",
                    resp.status,
                )
                return None
            response_data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "OAuth token refresh failed (%s) — child agents may fail to authenticate",
            exc,
        )
        return None

    new_access_token = response_data.get("access_token")
    if not new_access_token:
        logger.warning(
            "OAuth token refresh response missing 'access_token'"
            " — child agents may fail to authenticate"
        )
        return None

    # Compute new expiresAt in milliseconds
    if "expires_at" in response_data:
        # Server returned absolute timestamp in seconds
        new_expires_at_ms = int(response_data["expires_at"] * 1000)
    elif "expires_in" in response_data:
        new_expires_at_ms = int((time.time() + response_data["expires_in"]) * 1000)
    else:
        # Fallback: assume 1-hour validity
        new_expires_at_ms = int((time.time() + 3600) * 1000)

    # Write refreshed token back atomically (temp file in same dir for os.replace)
    oauth["accessToken"] = new_access_token
    oauth["expiresAt"] = new_expires_at_ms
    data["claudeAiOauth"] = oauth
    try:
        creds_dir = creds_path.parent
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=creds_dir,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp_path = tmp.name
            json.dump(data, tmp, indent=2)
        os.replace(tmp_path, creds_path)
    except OSError as exc:
        logger.warning(
            "Failed to write refreshed OAuth token to %s: %s", creds_path, exc
        )
        # Token is still usable even if we couldn't persist it
    return new_access_token


class ClaudeProvider(AgentProvider):
    """Provider for Anthropic Claude models via the Python ACP bridge.

    Spawns ``vaultspec.protocol.acp.claude_bridge`` as a subprocess and
    handles credential wrangling, system-prompt construction, and environment
    variable forwarding for all Claude-specific agent features.
    """

    @property
    def name(self) -> str:
        """Return the provider identifier string.

        Returns:
            The string ``"claude"``.
        """
        return "claude"

    @property
    def models(self) -> ModelRegistry:
        """Return the Claude model registry.

        Returns:
            The :class:`ClaudeModels` registry class.
        """
        return ClaudeModels

    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load ``.claude/CLAUDE.md`` if it exists.

        Args:
            root_dir: Workspace root directory.

        Returns:
            File contents as a string, or an empty string if the file is absent.
        """
        system_file = root_dir / ".claude" / "CLAUDE.md"
        if not system_file.exists():
            return ""
        return system_file.read_text(encoding="utf-8")

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Load and inline-resolve rules from ``.claude/rules/``.

        All ``*.md`` files in the rules directory are read in sorted order and
        their ``@include`` directives are resolved recursively.

        Args:
            root_dir: Workspace root directory.

        Returns:
            Concatenated rules text, or an empty string if the directory does
            not exist.
        """
        rules_dir = root_dir / ".claude" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            content = rule_file.read_text(encoding="utf-8")
            resolved = resolve_includes(content, rules_dir, root_dir)
            all_rules.append(resolved)

        return "\n\n".join(all_rules)

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: str | None = None,
        mode: str = "read-write",
    ) -> ProcessSpec:
        """Build a ProcessSpec for launching the Claude ACP bridge subprocess.

        Loads system prompt and rules, selects the appropriate model,
        handles OAuth credential injection, and maps agent YAML metadata to
        environment variables consumed by the bridge.

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

        Returns:
            ProcessSpec ready for the orchestration layer to spawn.
        """
        _ = agent_name

        # Warn on Gemini-only features
        for key in _GEMINI_ONLY_FEATURES:
            if agent_meta.get(key):
                logger.warning(
                    "Feature '%s' is not supported by %s provider; ignoring",
                    key,
                    self.name,
                )

        # Load system instructions and rules
        system_instructions = self.load_system_prompt(root_dir)
        rules = self.load_rules(root_dir)

        # Construct system context
        system_context = self.construct_system_prompt(
            agent_persona,
            rules,
            system_instructions,
        )

        # Determine model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        # Prepare environment
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        # Ensure child claude processes can authenticate. When the SDK spawns
        # claude with CLAUDE_CODE_ENTRYPOINT=sdk-py it skips the interactive
        # credentials-file auth flow, so we must supply the token explicitly.
        if "ANTHROPIC_API_KEY" in env:
            logger.debug(
                "ANTHROPIC_API_KEY present"
                " — using API key path, skipping OAuth wrangling"
            )
        elif "CLAUDE_CODE_OAUTH_TOKEN" not in env:
            token = _load_claude_oauth_token()
            if token:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = token
            else:
                logger.warning(
                    "No Claude OAuth token found in ~/.claude/.credentials.json "
                    "and ANTHROPIC_API_KEY is not set"
                    " — child agents may fail to authenticate"
                )

        env["VAULTSPEC_ROOT_DIR"] = str(root_dir)
        env["VAULTSPEC_AGENT_MODE"] = mode
        if system_context:
            env["VAULTSPEC_SYSTEM_PROMPT"] = system_context

        # Safety & control features from agent YAML
        if agent_meta.get("max_turns"):
            env["VAULTSPEC_MAX_TURNS"] = agent_meta["max_turns"]
        if agent_meta.get("budget"):
            env["VAULTSPEC_BUDGET_USD"] = agent_meta["budget"]
        if agent_meta.get("allowed_tools"):
            env["VAULTSPEC_ALLOWED_TOOLS"] = agent_meta["allowed_tools"]
        if agent_meta.get("disallowed_tools"):
            env["VAULTSPEC_DISALLOWED_TOOLS"] = agent_meta["disallowed_tools"]
        if agent_meta.get("effort"):
            env["VAULTSPEC_EFFORT"] = agent_meta["effort"]
        if agent_meta.get("output_format"):
            env["VAULTSPEC_OUTPUT_FORMAT"] = agent_meta["output_format"]
        if agent_meta.get("fallback_model"):
            env["VAULTSPEC_FALLBACK_MODEL"] = agent_meta["fallback_model"]
        include_dirs = agent_meta.get("include_dirs", "")
        if include_dirs:
            validated = self._validate_include_dirs(include_dirs, root_dir)
            if validated:
                env["VAULTSPEC_INCLUDE_DIRS"] = ",".join(validated)

        return ProcessSpec(
            executable=sys.executable,
            args=[
                "-m",
                "vaultspec.protocol.acp.claude_bridge",
                "--model",
                model,
            ],
            env=env,
            cleanup_paths=[],
            initial_prompt_override=task_context,
            session_meta={"model": model},
        )
