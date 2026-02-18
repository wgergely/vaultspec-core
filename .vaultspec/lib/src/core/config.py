"""Centralized configuration for the vaultspec framework.

Provides a single ``VaultSpecConfig`` dataclass that collects every
configurable value used across the project.  Values are resolved in
priority order:

    1. Explicit ``overrides`` dict (for DI / testing)
    2. ``VAULTSPEC_*`` environment variable
    3. Dataclass default

A module-level singleton is managed by :func:`get_config` /
:func:`reset_config` for convenient access without passing the config
object everywhere.

Only stdlib imports are used — no third-party dependencies.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper parsers (defined before the registry so they can be referenced)
# ---------------------------------------------------------------------------


def parse_csv_list(value: str) -> list[str]:
    """Split a comma-separated string into a list of stripped, non-empty items."""
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_or_none(value: str) -> int | None:
    """Parse *value* as an ``int``, returning ``None`` on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_float_or_none(value: str) -> float | None:
    """Parse *value* as a ``float``, returning ``None`` on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# VaultSpecConfig
# ---------------------------------------------------------------------------


@dataclass
class VaultSpecConfig:
    """Central configuration for the vaultspec framework.

    Every configurable constant used by any module should appear here with
    its production default.  Instances are normally created via
    :meth:`from_environment`, which reads env vars and applies overrides.
    """

    # -- Agent -----------------------------------------------------------------
    root_dir: Path = field(default_factory=Path.cwd)
    agent_mode: str = "read-write"
    system_prompt: str | None = None
    max_turns: int | None = None
    budget_usd: float | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    effort: str | None = None
    output_format: str | None = None
    fallback_model: str | None = None
    include_dirs: list[str] = field(default_factory=list)

    # -- MCP -------------------------------------------------------------------
    mcp_root_dir: Path | None = None
    mcp_port: int = 10010
    mcp_host: str = "0.0.0.0"
    mcp_ttl_seconds: float = 3600.0

    # -- A2A -------------------------------------------------------------------
    a2a_default_port: int = 10010
    a2a_host: str = "localhost"

    # -- Storage ---------------------------------------------------------------
    docs_dir: str = ".vault"
    framework_dir: str = ".vaultspec"
    lance_dir: str = ".lance"
    index_metadata_file: str = "index_meta.json"

    # -- Tool directories ------------------------------------------------------
    claude_dir: str = ".claude"
    gemini_dir: str = ".gemini"
    antigravity_dir: str = ".antigravity"

    # -- Orchestration ---------------------------------------------------------
    task_engine_ttl_seconds: float = 3600.0

    # -- RAG -------------------------------------------------------------------
    graph_ttl_seconds: float = 300.0
    embedding_batch_size: int = 64
    max_embed_chars: int = 8000
    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embedding_dimension: int = 768

    # -- I/O -------------------------------------------------------------------
    io_buffer_size: int = 8192
    terminal_output_limit: int = 1_000_000

    # -- Server ----------------------------------------------------------------
    mcp_poll_interval: float = 5.0

    # -- Editor ----------------------------------------------------------------
    editor: str = "zed -w"

    @classmethod
    def from_environment(
        cls,
        overrides: dict[str, Any] | None = None,
    ) -> VaultSpecConfig:
        """Create a config from environment variables and optional overrides.

        Resolution order per attribute:

        1. *overrides* dict (keyed by ``attr_name``)
        2. ``VAULTSPEC_*`` env var
        3. Dataclass default

        Raises:
            ValueError: If a required variable has no value from any source.
        """
        overrides = overrides or {}
        kwargs: dict[str, Any] = {}

        for var in CONFIG_REGISTRY:
            # 1. Explicit override
            if var.attr_name in overrides:
                kwargs[var.attr_name] = overrides[var.attr_name]
                continue

            # 2. VAULTSPEC_* env var
            raw: str | None = os.environ.get(var.env_name)
            source: str | None = var.env_name if raw is not None else None

            # 3. Default
            if raw is None:
                if var.required:
                    raise ValueError(
                        f"Required config variable {var.env_name} "
                        f"(attr: {var.attr_name}) is not set and no "
                        f"override was provided."
                    )
                # Skip — dataclass default will apply
                continue

            # Parse the raw string value into the target type
            parsed = _parse_raw(var, raw, source)
            if parsed is _SENTINEL:
                continue  # parse failed, fall back to default
            kwargs[var.attr_name] = parsed

        return cls(**kwargs)


# Sentinel for parse failures
_SENTINEL = object()


def _parse_raw(var: ConfigVariable, raw: str, source: str | None) -> Any:
    """Parse a raw env-var string into the type expected by *var*.

    Returns ``_SENTINEL`` if parsing fails (caller should fall back to
    the dataclass default).
    """
    try:
        if var.var_type is bool:
            return raw.lower() in ("1", "true", "yes")

        if var.var_type is int:
            value = int(raw)
        elif var.var_type is float:
            value = float(raw)
        elif var.var_type is Path:
            return Path(raw)
        elif var.var_type is list:
            return parse_csv_list(raw)
        elif var.var_type is _OptionalInt:
            value_or_none = parse_int_or_none(raw)
            if value_or_none is None:
                logger.error(
                    "Could not parse %s=%r as int (source: %s); using default",
                    var.attr_name,
                    raw,
                    source,
                )
                return _SENTINEL
            value = value_or_none
        elif var.var_type is _OptionalFloat:
            value_or_none = parse_float_or_none(raw)
            if value_or_none is None:
                logger.error(
                    "Could not parse %s=%r as float (source: %s); using default",
                    var.attr_name,
                    raw,
                    source,
                )
                return _SENTINEL
            value = value_or_none
        else:
            # str or Optional[str] — no conversion needed
            value = raw

        # Validate options
        if var.options is not None and value not in var.options:
            logger.error(
                "%s=%r is not one of %s (source: %s); using default",
                var.attr_name,
                value,
                var.options,
                source,
            )
            return _SENTINEL

        # Validate range
        if (
            var.min_value is not None
            and isinstance(value, (int, float))
            and value < var.min_value
        ):
            logger.error(
                "%s=%r is below minimum %s (source: %s); using default",
                var.attr_name,
                value,
                var.min_value,
                source,
            )
            return _SENTINEL
        if (
            var.max_value is not None
            and isinstance(value, (int, float))
            and value > var.max_value
        ):
            logger.error(
                "%s=%r exceeds maximum %s (source: %s); using default",
                var.attr_name,
                value,
                var.max_value,
                source,
            )
            return _SENTINEL

        return value

    except (ValueError, TypeError) as exc:
        logger.error(
            "Failed to parse %s=%r (source: %s): %s; using default",
            var.attr_name,
            raw,
            source,
            exc,
        )
        return _SENTINEL


# ---------------------------------------------------------------------------
# ConfigVariable registry
# ---------------------------------------------------------------------------

# Type sentinels for Optional[int] / Optional[float] — we cannot use
# ``int | None`` as a registry *value* because the registry needs a single
# type token to drive parsing.


class _OptionalInt:
    """Sentinel type for registry entries that parse to ``int | None``."""


class _OptionalFloat:
    """Sentinel type for registry entries that parse to ``float | None``."""


@dataclass
class ConfigVariable:
    """Metadata for one configurable variable.

    Used by :meth:`VaultSpecConfig.from_environment` to drive env-var
    resolution, parsing, and validation.
    """

    env_name: str
    attr_name: str
    var_type: type
    default: Any
    description: str
    required: bool = False
    options: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None


CONFIG_REGISTRY: list[ConfigVariable] = [
    # -- Agent -----------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_ROOT_DIR",
        attr_name="root_dir",
        var_type=Path,
        default=None,
        description="Workspace root directory.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_AGENT_MODE",
        attr_name="agent_mode",
        var_type=str,
        default="read-write",
        description="Agent permission mode.",
        options=["read-write", "read-only"],
    ),
    ConfigVariable(
        env_name="VAULTSPEC_SYSTEM_PROMPT",
        attr_name="system_prompt",
        var_type=str,
        default=None,
        description="Custom system prompt for agent sessions.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_MAX_TURNS",
        attr_name="max_turns",
        var_type=_OptionalInt,
        default=None,
        description="Maximum conversation turns for agent sessions.",
        min_value=1,
    ),
    ConfigVariable(
        env_name="VAULTSPEC_BUDGET_USD",
        attr_name="budget_usd",
        var_type=_OptionalFloat,
        default=None,
        description="Budget cap in USD for agent sessions.",
        min_value=0,
    ),
    ConfigVariable(
        env_name="VAULTSPEC_ALLOWED_TOOLS",
        attr_name="allowed_tools",
        var_type=list,
        default=[],
        description="Comma-separated list of allowed tool names.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_DISALLOWED_TOOLS",
        attr_name="disallowed_tools",
        var_type=list,
        default=[],
        description="Comma-separated list of disallowed tool names.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_EFFORT",
        attr_name="effort",
        var_type=str,
        default=None,
        description="Effort level hint for agent sessions.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_OUTPUT_FORMAT",
        attr_name="output_format",
        var_type=str,
        default=None,
        description="Output format for agent responses.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_FALLBACK_MODEL",
        attr_name="fallback_model",
        var_type=str,
        default=None,
        description="Fallback model identifier for agent sessions.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_INCLUDE_DIRS",
        attr_name="include_dirs",
        var_type=list,
        default=[],
        description="Comma-separated list of directories to include.",
    ),
    # -- MCP -------------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_MCP_ROOT_DIR",
        attr_name="mcp_root_dir",
        var_type=Path,
        default=None,
        description="Root directory for MCP server. Required in MCP context.",
        required=False,  # only required when MCP server starts — validated there
    ),
    ConfigVariable(
        env_name="VAULTSPEC_MCP_PORT",
        attr_name="mcp_port",
        var_type=int,
        default=10010,
        description="Port for MCP server.",
        min_value=1,
        max_value=65535,
    ),
    ConfigVariable(
        env_name="VAULTSPEC_MCP_HOST",
        attr_name="mcp_host",
        var_type=str,
        default="0.0.0.0",
        description="Host address for MCP server.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_MCP_TTL_SECONDS",
        attr_name="mcp_ttl_seconds",
        var_type=float,
        default=3600.0,
        description="Task TTL in seconds for MCP server.",
        min_value=0,
    ),
    # -- A2A -------------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_A2A_DEFAULT_PORT",
        attr_name="a2a_default_port",
        var_type=int,
        default=10010,
        description="Default port for A2A agent cards.",
        min_value=1,
        max_value=65535,
    ),
    ConfigVariable(
        env_name="VAULTSPEC_A2A_HOST",
        attr_name="a2a_host",
        var_type=str,
        default="localhost",
        description="Default host for A2A agent cards.",
    ),
    # -- Storage ---------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_DOCS_DIR",
        attr_name="docs_dir",
        var_type=str,
        default=".vault",
        description="Documentation vault directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_FRAMEWORK_DIR",
        attr_name="framework_dir",
        var_type=str,
        default=".vaultspec",
        description="Framework directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_LANCE_DIR",
        attr_name="lance_dir",
        var_type=str,
        default=".lance",
        description="LanceDB vector store directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_INDEX_METADATA_FILE",
        attr_name="index_metadata_file",
        var_type=str,
        default="index_meta.json",
        description="Index metadata filename within lance directory.",
    ),
    # -- Tool directories ------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_CLAUDE_DIR",
        attr_name="claude_dir",
        var_type=str,
        default=".claude",
        description="Claude tool directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_GEMINI_DIR",
        attr_name="gemini_dir",
        var_type=str,
        default=".gemini",
        description="Gemini tool directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_ANTIGRAVITY_DIR",
        attr_name="antigravity_dir",
        var_type=str,
        default=".antigravity",
        description="Antigravity tool directory name.",
    ),
    # -- Orchestration ---------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_TASK_ENGINE_TTL_SECONDS",
        attr_name="task_engine_ttl_seconds",
        var_type=float,
        default=3600.0,
        description="Task engine TTL in seconds.",
        min_value=0,
    ),
    # -- RAG -------------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_GRAPH_TTL_SECONDS",
        attr_name="graph_ttl_seconds",
        var_type=float,
        default=300.0,
        description="Graph cache TTL in seconds for search re-ranking.",
        min_value=0,
    ),
    ConfigVariable(
        env_name="VAULTSPEC_EMBEDDING_BATCH_SIZE",
        attr_name="embedding_batch_size",
        var_type=int,
        default=64,
        description="Batch size for GPU embedding inference.",
        min_value=1,
    ),
    ConfigVariable(
        env_name="VAULTSPEC_MAX_EMBED_CHARS",
        attr_name="max_embed_chars",
        var_type=int,
        default=8000,
        description="Max characters per document for embedding truncation.",
        min_value=100,
    ),
    # -- I/O -------------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_IO_BUFFER_SIZE",
        attr_name="io_buffer_size",
        var_type=int,
        default=8192,
        description="I/O read buffer size in bytes.",
        min_value=1,
    ),
    ConfigVariable(
        env_name="VAULTSPEC_TERMINAL_OUTPUT_LIMIT",
        attr_name="terminal_output_limit",
        var_type=int,
        default=1_000_000,
        description="Terminal output byte limit for subprocess capture.",
        min_value=1,
    ),
    # -- RAG model -------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_EMBEDDING_MODEL",
        attr_name="embedding_model",
        var_type=str,
        default="nomic-ai/nomic-embed-text-v1.5",
        description="Sentence-transformer model name for embeddings.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_EMBEDDING_DIMENSION",
        attr_name="embedding_dimension",
        var_type=int,
        default=768,
        description="Embedding vector dimension. Auto-detected from model at runtime.",
        min_value=1,
    ),
    # -- Server ----------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_MCP_POLL_INTERVAL",
        attr_name="mcp_poll_interval",
        var_type=float,
        default=5.0,
        description="Agent file polling interval in seconds for MCP server.",
        min_value=0.5,
    ),
    # -- Editor ----------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_EDITOR",
        attr_name="editor",
        var_type=str,
        default="zed -w",
        description="Default editor command for creating rules/agents/skills.",
    ),
]


# ---------------------------------------------------------------------------
# Global singleton management
# ---------------------------------------------------------------------------

_cached_config: VaultSpecConfig | None = None


def get_config(overrides: dict[str, Any] | None = None) -> VaultSpecConfig:
    """Return the global ``VaultSpecConfig`` instance.

    If *overrides* is provided a fresh instance is created (not cached).
    Otherwise the cached singleton is returned, creating it on first call.
    """
    global _cached_config

    if overrides is not None:
        return VaultSpecConfig.from_environment(overrides)

    if _cached_config is None:
        _cached_config = VaultSpecConfig.from_environment()
    return _cached_config


def reset_config() -> None:
    """Clear the cached singleton so the next :func:`get_config` recreates it."""
    global _cached_config
    _cached_config = None
