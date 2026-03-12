"""Define the runtime configuration model and singleton access for vaultspec.

This module centralizes typed defaults, environment-variable parsing, and the
global `get_config()` access pattern used throughout the package. It is the
authoritative source for configuration semantics such as model selection,
filesystem naming, and integration flags.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.enums import DirName

logger = logging.getLogger(__name__)

__all__ = [
    "CONFIG_REGISTRY",
    "ConfigVariable",
    "VaultSpecConfig",
    "get_config",
    "parse_csv_list",
    "parse_float_or_none",
    "parse_int_or_none",
    "reset_config",
]


def parse_csv_list(value: str) -> list[str]:
    """Split a comma-separated string into a list of stripped, non-empty items.

    Args:
        value: Comma-separated string to split.

    Returns:
        List of non-empty, whitespace-stripped tokens.
    """
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_or_none(value: str) -> int | None:
    """Parse *value* as an ``int``, returning ``None`` on failure.

    Args:
        value: String to parse.

    Returns:
        Parsed integer, or ``None`` if the string cannot be converted.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_float_or_none(value: str) -> float | None:
    """Parse *value* as a ``float``, returning ``None`` on failure.

    Args:
        value: String to parse.

    Returns:
        Parsed float, or ``None`` if the string cannot be converted.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@dataclass
class VaultSpecConfig:
    """Central configuration for the vaultspec framework.

    Every configurable constant used by any module should appear here with
    its production default. Instances are normally created via
    :meth:`from_environment`, which reads env vars and applies overrides.

    Attributes:
        target_dir: The root directory for the workspace (where .vault/ and
            .vaultspec/ live).
        docs_dir: Documentation vault directory name.
        framework_dir: Framework directory name.
        claude_dir: Claude tool directory name.
        gemini_dir: Gemini tool directory name.
        io_buffer_size: I/O read buffer size in bytes.
        terminal_output_limit: Terminal output byte limit for subprocess capture.
        editor: Default editor command for creating rules/skills.
    """

    # -- Root ------------------------------------------------------------------
    target_dir: Path = field(default_factory=Path.cwd)

    # -- Storage ---------------------------------------------------------------
    docs_dir: str = DirName.VAULT.value
    framework_dir: str = DirName.VAULTSPEC.value

    # -- Tool directories ------------------------------------------------------
    claude_dir: str = DirName.CLAUDE.value
    gemini_dir: str = DirName.GEMINI.value
    antigravity_dir: str = DirName.ANTIGRAVITY.value

    # -- I/O -------------------------------------------------------------------
    io_buffer_size: int = 8192
    terminal_output_limit: int = 1_000_000

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

        Args:
            overrides: Optional mapping of attribute name to value that takes
                precedence over environment variables and defaults.

        Returns:
            A fully-populated ``VaultSpecConfig`` instance.

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

    Args:
        var: The ``ConfigVariable`` metadata that describes the expected type
            and validation constraints.
        raw: The raw string value read from the environment variable.
        source: Human-readable source label for error messages (typically the
            env var name), or ``None``.

    Returns:
        The parsed and validated value, or ``_SENTINEL`` if parsing or
        validation fails (caller should fall back to the dataclass default).
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
            exc_info=True,
        )
        return _SENTINEL


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

    Attributes:
        env_name: The ``VAULTSPEC_*`` environment variable name.
        attr_name: The corresponding attribute name on ``VaultSpecConfig``.
        var_type: The target Python type for parsing (e.g. ``int``, ``Path``).
        default: The default value when neither override nor env var is set.
        description: Human-readable description of the variable's purpose.
        required: If ``True``, raises ``ValueError`` when no value is found.
        options: Allowed string values; ``None`` means no restriction.
        min_value: Minimum numeric value (inclusive); ``None`` means no minimum.
        max_value: Maximum numeric value (inclusive); ``None`` means no maximum.
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
    # -- Root ------------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_TARGET_DIR",
        attr_name="target_dir",
        var_type=Path,
        default=None,
        description="The root directory for the workspace (where .vault/ and "
        ".vaultspec/ live).",
    ),
    # -- Storage ---------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_DOCS_DIR",
        attr_name="docs_dir",
        var_type=str,
        default=DirName.VAULT.value,
        description="Documentation vault directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_FRAMEWORK_DIR",
        attr_name="framework_dir",
        var_type=str,
        default=DirName.VAULTSPEC.value,
        description="Framework directory name.",
    ),
    # -- Tool directories ------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_CLAUDE_DIR",
        attr_name="claude_dir",
        var_type=str,
        default=DirName.CLAUDE.value,
        description="Claude tool directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_GEMINI_DIR",
        attr_name="gemini_dir",
        var_type=str,
        default=DirName.GEMINI.value,
        description="Gemini tool directory name.",
    ),
    ConfigVariable(
        env_name="VAULTSPEC_ANTIGRAVITY_DIR",
        attr_name="antigravity_dir",
        var_type=str,
        default=DirName.ANTIGRAVITY.value,
        description="Agent tool directory name.",
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
    # -- Editor ----------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_EDITOR",
        attr_name="editor",
        var_type=str,
        default="zed -w",
        description="Default editor command for creating rules/skills.",
    ),
]


_cached_config: VaultSpecConfig | None = None


def get_config(overrides: dict[str, Any] | None = None) -> VaultSpecConfig:
    """Return the global ``VaultSpecConfig`` instance.

    If *overrides* is provided a fresh instance is created (not cached).
    Otherwise the cached singleton is returned, creating it on first call.

    Args:
        overrides: Optional attribute overrides passed directly to
            :meth:`VaultSpecConfig.from_environment`. When provided, the
            result is not cached.

    Returns:
        The current (or freshly created) ``VaultSpecConfig`` singleton.
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
