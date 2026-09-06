"""Runtime configuration model and singleton access for vaultspec.

Centralizes typed defaults, ``VAULTSPEC_*`` env-var parsing, and the
:func:`get_config` singleton pattern. Key exports: :class:`VaultSpecConfig`,
:class:`ConfigVariable`, :data:`CONFIG_REGISTRY`, :func:`get_config`,
:func:`reset_config`, and three parse helpers. Consumed by every module
that reads workspace settings; re-exported via :mod:`vaultspec_core.config`.
"""

from __future__ import annotations

import logging
import os
import threading
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


def parse_int_or_none(value: str | None) -> int | None:
    """Parse *value* as an ``int``, returning ``None`` on failure.

    Args:
        value: String to parse.

    Returns:
        Parsed integer, or ``None`` if the string cannot be converted.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_float_or_none(value: str | None) -> float | None:
    """Parse *value* as a ``float``, returning ``None`` on failure.

    Args:
        value: String to parse.

    Returns:
        Parsed float, or ``None`` if the string cannot be converted.
    """
    if value is None:
        return None
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
        index_dir: Subdirectory of :attr:`docs_dir` that holds auto-generated
            feature index files (``<feature>.index.md``).
        framework_dir: Framework directory name.
        claude_dir: Claude tool directory name.
        gemini_dir: Gemini tool directory name.
        io_buffer_size: I/O read buffer size in bytes.
        terminal_output_limit: Terminal output byte limit for subprocess capture.
        lock_timeout_seconds: Total budget, in seconds, that a single
            :func:`~vaultspec_core.core.helpers.advisory_lock` acquisition may
            spend waiting before it reports a timeout instead of blocking on.
        editor: Default editor command for creating rules/skills.
    """

    # -- Root ------------------------------------------------------------------
    target_dir: Path = field(default_factory=Path.cwd)

    # -- Storage ---------------------------------------------------------------
    docs_dir: str = DirName.VAULT.value
    index_dir: str = DirName.INDEX.value
    framework_dir: str = DirName.VAULTSPEC.value

    # -- Tool directories ------------------------------------------------------
    claude_dir: str = DirName.CLAUDE.value
    gemini_dir: str = DirName.GEMINI.value
    antigravity_dir: str = DirName.ANTIGRAVITY.value

    # -- I/O -------------------------------------------------------------------
    io_buffer_size: int = 8192
    terminal_output_limit: int = 1_000_000

    # -- Concurrency -----------------------------------------------------------
    lock_timeout_seconds: float = 120.0

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
                # Skip  - dataclass default will apply
                continue

            # Parse the raw string value into the target type
            parsed = _parse_raw(var, raw, source)
            if parsed is _SENTINEL:
                continue  # parse failed, fall back to default
            kwargs[var.attr_name] = parsed

        return cls(**kwargs)


# Sentinel for parse failures
_SENTINEL = object()


# Type sentinels for Optional[int] / Optional[float]  - we cannot use
# ``int | None`` as a registry *value* because the registry needs a single
# type token to drive parsing.


class _OptionalInt:
    """Sentinel type for registry entries that parse to ``int | None``."""


class _OptionalFloat:
    """Sentinel type for registry entries that parse to ``float | None``."""


def _parse_bool(raw: str) -> bool:
    """Parse a boolean environment variable value."""
    return raw.lower() in ("1", "true", "yes")


# Maps a registry ``var_type`` to its ``(converter, skip_validation)`` pair.
# ``skip_validation`` is ``True`` for types (``bool``, ``Path``, ``list``)
# whose values bypass the options/range validation applied to the rest.
# Types absent from this table (``str`` / ``Optional[str]``) need no
# conversion and are handled by the ``_convert_raw_value`` fallback.
_TYPE_CONVERTERS: dict[type, tuple[Any, bool]] = {
    bool: (_parse_bool, True),
    int: (int, False),
    float: (float, False),
    Path: (Path, True),
    list: (parse_csv_list, True),
    _OptionalInt: (parse_int_or_none, False),
    _OptionalFloat: (parse_float_or_none, False),
}


def _convert_raw_value(var: ConfigVariable, raw: str) -> tuple[Any, bool]:
    """Convert *raw* into the type expected by *var*.

    Args:
        var: The ``ConfigVariable`` metadata that describes the expected type.
        raw: The raw string value read from the environment variable.

    Returns:
        A ``(value, skip_validation)`` tuple. ``skip_validation`` is ``True``
        for types (``bool``, ``Path``, ``list``) whose values bypass the
        options/range validation applied to the remaining types; ``value``
        is ``None`` for ``_OptionalInt``/``_OptionalFloat`` when parsing
        failed.

    Raises:
        ValueError: Propagated from ``int()``/``float()`` on malformed input.
        TypeError: Propagated from the underlying conversion call.
    """
    converter_entry = _TYPE_CONVERTERS.get(var.var_type)
    if converter_entry is None:
        # str or Optional[str]  - no conversion needed
        return raw, False
    converter, skip_validation = converter_entry
    return converter(raw), skip_validation


def _validate_value(var: ConfigVariable, value: Any, source: str | None) -> bool:
    """Validate an already-converted *value* against *var*'s constraints.

    Args:
        var: The ``ConfigVariable`` metadata describing the options/range
            constraints.
        value: The converted value to validate.
        source: Human-readable source label for error messages.

    Returns:
        ``True`` if *value* satisfies every configured constraint, ``False``
        otherwise (a matching error has already been logged).
    """
    if var.options is not None and value not in var.options:
        logger.error(
            "%s=%r is not one of %s (source: %s); using default",
            var.attr_name,
            value,
            var.options,
            source,
        )
        return False

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
        return False

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
        return False

    return True


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
        value, skip_validation = _convert_raw_value(var, raw)
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

    if var.var_type in (_OptionalInt, _OptionalFloat) and value is None:
        logger.error(
            "Could not parse %s=%r as %s (source: %s); using default",
            var.attr_name,
            raw,
            "int" if var.var_type is _OptionalInt else "float",
            source,
        )
        return _SENTINEL

    if skip_validation or _validate_value(var, value, source):
        return value
    return _SENTINEL


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
        env_name="VAULTSPEC_INDEX_DIR",
        attr_name="index_dir",
        var_type=str,
        default=DirName.INDEX.value,
        description=(
            "Subdirectory of docs_dir for auto-generated feature index files "
            "(<feature>.index.md)."
        ),
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
    # -- Concurrency -----------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_LOCK_TIMEOUT_SECONDS",
        attr_name="lock_timeout_seconds",
        var_type=float,
        default=120.0,
        description=(
            "Total seconds a single advisory-lock acquisition may wait "
            "before reporting a timeout. Covers both the in-process thread "
            "layer and the cross-process OS layer combined."
        ),
        min_value=0.0,
    ),
    # -- Editor ----------------------------------------------------------------
    ConfigVariable(
        env_name="VAULTSPEC_EDITOR",
        attr_name="editor",
        var_type=str,
        # Honour the standard $VISUAL / $EDITOR convention before the
        # built-in fallback, so an operator's existing editor choice is
        # respected without a vaultspec-specific variable.
        default=os.environ.get("VISUAL") or os.environ.get("EDITOR") or "zed -w",
        description="Default editor command for creating rules/skills.",
    ),
]


_cached_config: VaultSpecConfig | None = None
_config_lock = threading.Lock()


def get_config(overrides: dict[str, Any] | None = None) -> VaultSpecConfig:
    """Return the global ``VaultSpecConfig`` instance.

    If *overrides* is provided a fresh instance is created (not cached).
    Otherwise the cached singleton is returned, creating it on first call.
    Thread-safe: concurrent callers from the MCP server will not race
    on the read-modify of ``_cached_config``.

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

    with _config_lock:
        if _cached_config is None:
            _cached_config = VaultSpecConfig.from_environment()
        return _cached_config


def reset_config() -> None:
    """Clear the cached singleton so the next :func:`get_config` recreates it."""
    global _cached_config
    with _config_lock:
        _cached_config = None
