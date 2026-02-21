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

from .base import (
    AgentProvider,
    CapabilityLevel,
    GeminiModels,
    ModelRegistry,
    ProcessSpec,
    resolve_executable,
    resolve_includes,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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

# Cache for version check result
_cached_version: tuple[int, ...] | None = None

# Overridable which function for testing
_which_fn: Callable[[str], str | None] = shutil.which


def _load_gemini_oauth_creds(
    creds_path: pathlib.Path | None = None,
) -> dict | None:
    """Load ~/.gemini/oauth_creds.json and return its parsed contents, or None."""
    path = creds_path or pathlib.Path.home() / ".gemini" / "oauth_creds.json"
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

    On success, writes the updated creds atomically back to the credentials file
    and returns the updated dict. On failure, logs a warning and returns None.
    """
    url = token_url or creds.get("token_uri", "https://oauth2.googleapis.com/token")
    refresh_token = creds.get("refresh_token")
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")

    if not all([refresh_token, client_id, client_secret]):
        logger.warning(
            "Gemini OAuth token refresh skipped: missing refresh_token,"
            " client_id, or client_secret in credentials."
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
    expiry_dt = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        seconds=int(expires_in)
    )
    updated["expiry"] = expiry_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

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
    """Return True if the OAuth access_token expires within 5 minutes."""
    expiry_str = creds.get("expiry")
    if not expiry_str:
        return True
    try:
        expiry_str_normalized = expiry_str.replace("Z", "+00:00")
        expiry_dt = datetime.datetime.fromisoformat(expiry_str_normalized)
    except ValueError:
        try:
            expiry_dt = datetime.datetime.strptime(
                expiry_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.UTC)
        except ValueError:
            return True
    buffer = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=300)
    return expiry_dt <= buffer


class GeminiProvider(AgentProvider):
    """Provider for Google Gemini models via Gemini CLI."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def models(self) -> ModelRegistry:
        return GeminiModels

    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Loads .gemini/SYSTEM.md if it exists (deployed by CLI sync)."""
        system_file = root_dir / ".gemini" / "SYSTEM.md"
        if not system_file.exists():
            return ""
        return system_file.read_text(encoding="utf-8")

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Loads and resolves nested rules from .gemini/rules/."""
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

        Returns the parsed version tuple or None if version could not be determined.
        Pass ``run_fn`` to inject a replacement for ``subprocess.run`` (testing).
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
        *,
        creds_path: pathlib.Path | None = None,
    ) -> ProcessSpec:
        _ = agent_name

        # Warn on Claude-only features
        for key in _CLAUDE_ONLY_FEATURES:
            if agent_meta.get(key):
                logger.warning(
                    "Feature '%s' is not supported by %s provider; ignoring",
                    key,
                    self.name,
                )

        #  Locate executable and check version
        _raw_executable = _which_fn("gemini") or "gemini"
        self.check_version(_raw_executable)
        executable, prefix_args = resolve_executable("gemini", _which_fn)

        #  Load system instructions, rules, and construct full prompt
        system_instructions = self.load_system_prompt(root_dir)
        rules = self.load_rules(root_dir)
        system_prompt = self.construct_system_prompt(
            agent_persona,
            rules,
            system_instructions,
        )

        #  Prepare Environment
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

        # Write system prompt to temp file for GEMINI_SYSTEM_MD
        if system_prompt:
            from vaultspec.core import get_config

            tmp_dir = root_dir / get_config().framework_dir / ".tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            system_file = tmp_dir / f"system-{uuid.uuid4().hex[:8]}.md"
            system_file.write_text(system_prompt, encoding="utf-8")
            env["GEMINI_SYSTEM_MD"] = str(system_file)
            cleanup_paths.append(system_file)

        #  Determine Model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        #  Build Args (Gemini CLI has no --system flag)
        args = ["--experimental-acp", "--model", model]
        if mode == "read-only":
            args.append("--sandbox")

        # Tool control
        allowed = agent_meta.get("allowed_tools", "")
        if allowed:
            for tool in (t.strip() for t in allowed.split(",") if t.strip()):
                args.extend(["--allowed-tools", tool])

        # Approval mode (Gemini-specific: default|auto_edit|yolo|plan)
        approval = agent_meta.get("approval_mode")
        if approval and approval != "default":
            args.extend(["--approval-mode", approval])

        # Output format (text|json|stream-json)
        fmt = agent_meta.get("output_format")
        if fmt and fmt != "text":
            args.extend(["--output-format", fmt])

        # Additional workspace directories (validated against traversal)
        include_dirs = agent_meta.get("include_dirs", "")
        if include_dirs:
            for d in self._validate_include_dirs(include_dirs, root_dir):
                args.extend(["--include-directories", d])

        return ProcessSpec(
            executable=executable,
            args=prefix_args + args,
            env=env,
            cleanup_paths=cleanup_paths,
            initial_prompt_override=task_context,
        )
