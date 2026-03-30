"""Base abstractions and shared helpers for execution providers.

This module defines the common provider contract, model-registry integration,
workspace include resolution, executable lookup, and prompt assembly used by
provider implementations. It enforces the shared security boundary for
resolving workspace-scoped prompt and rules files while leaving
provider-specific file conventions to concrete implementations.

Typical usage is to subclass ``ExecutionProvider``, bind a ``ModelRegistry``
and capability semantics from ``CapabilityLevel``, and implement the
provider's workspace-specific prompt or rules loading behavior on top of the
shared resolution helpers.
"""

from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from ...core.enums import CapabilityLevel, ModelRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "ExecutionProvider",
    "resolve_executable",
    "resolve_includes",
]


def resolve_includes(
    content: str,
    base_dir: pathlib.Path,
    root_dir: pathlib.Path,
    warnings: list[str] | None = None,
) -> str:
    """Recursively resolve ``@path/to/file.md`` includes within Markdown content.

    Lines beginning with ``@`` are treated as include directives. Paths are
    resolved relative to ``base_dir`` first, then relative to ``root_dir``
    as a fallback. Resolved paths must remain inside ``root_dir`` to prevent
    path-traversal reads.

    Args:
        content: Markdown source text that may contain ``@include`` lines.
        base_dir: Directory of the file being processed (used for relative
            resolution first).
        root_dir: Workspace root used as the fallback resolution base and as
            the security boundary.
        warnings: Optional list to append include-failure messages to, so
            callers can propagate them into
            :class:`~vaultspec_core.core.types.SyncResult`.

    Returns:
        Markdown string with all include directives replaced by the content
        of the referenced files, wrapped in HTML comments indicating the
        source path. Missing or out-of-bounds includes are replaced with
        an HTML error comment.
    """
    resolved_root = root_dir.resolve()
    lines = content.split("\n")
    resolved_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("@"):
            resolved_lines.append(line)
            continue

        include_path_str = stripped[1:].strip()

        # Skip URLs
        if include_path_str.startswith(("http://", "https://")):
            resolved_lines.append(line)
            continue

        # Normalize backslashes for cross-platform compatibility
        normalized = include_path_str.replace("\\", "/")

        # Try base_dir first (relative to including file), then root_dir
        include_path = None
        candidate = (base_dir / normalized).resolve()
        if candidate.exists():
            include_path = candidate
        else:
            candidate = (root_dir / normalized).resolve()
            if candidate.exists():
                include_path = candidate

        if include_path is None:
            msg = f"Include resolution failed: {include_path_str} - path not found"
            logger.warning(
                "Include resolution failed: %s  - path not found",
                include_path_str,
            )
            if warnings is not None:
                warnings.append(msg)
            resolved_lines.append(
                f"<!-- ERROR: Missing include: {include_path_str} -->"
            )
            continue

        try:
            if not include_path.is_relative_to(resolved_root):
                msg = (
                    f"Include resolution failed: {include_path_str}"
                    " - path outside workspace"
                )
                logger.warning(
                    "Include resolution failed: %s  - path outside workspace",
                    include_path_str,
                )
                if warnings is not None:
                    warnings.append(msg)
                resolved_lines.append(
                    f"<!-- ERROR: Path outside workspace: {include_path_str} -->"
                )
                continue

            included_content = include_path.read_text(encoding="utf-8")
            display_path = str(include_path.relative_to(resolved_root)).replace(
                "\\", "/"
            )
            resolved_lines.append(f"\n<!-- Included from {display_path} -->\n")
            resolved_lines.append(
                resolve_includes(
                    included_content, include_path.parent, root_dir, warnings
                )
            )
            resolved_lines.append(f"\n<!-- End of {display_path} -->\n")
        except Exception as e:
            msg = f"Include resolution failed: {include_path_str} - {e}"
            logger.warning("Include resolution failed: %s  - %s", include_path_str, e)
            if warnings is not None:
                warnings.append(msg)
            resolved_lines.append(f"<!-- ERROR: Include failed: {e} -->")

    return "\n".join(resolved_lines)


def resolve_executable(name: str, which_fn=None) -> tuple[str, list[str]]:
    """Resolve an executable name, handling Windows .cmd/.bat wrappers.

    On Windows, tools installed via npm/uv often appear as .cmd batch
    scripts that cannot be directly launched by subprocess or
    asyncio.create_subprocess_exec. This function wraps them with
    ``cmd.exe /c`` so they execute correctly.

    Args:
        name: Executable name to resolve (e.g. ``"gemini"``).
        which_fn: Optional replacement for ``shutil.which`` (injectable for
            testing).

    Returns:
        (executable, prefix_args)  - prepend prefix_args to the command's
        argument list when constructing the subprocess call.
    """
    import shutil
    import sys

    _which = which_fn or shutil.which
    path = _which(name) or name

    if sys.platform == "win32" and path.lower().endswith((".cmd", ".bat")):
        return "cmd.exe", ["/c", path]
    return path, []


class ExecutionProvider(abc.ABC):
    """Abstract base class for all vaultspec-core execution providers.

    Subclasses bind a :class:`~vaultspec_core.core.enums.ModelRegistry` and
    implement workspace-specific system-prompt and rules loading. Shared
    helpers (:func:`resolve_includes`, :func:`resolve_executable`) and
    prompt assembly (:meth:`construct_system_prompt`) are provided here.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The name of the provider (e.g., 'gemini', 'claude')."""

    @property
    @abc.abstractmethod
    def models(self) -> ModelRegistry:
        """The model registry class for this provider."""

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        """Return the model ID that best matches the requested capability level.

        Args:
            level: Desired capability tier.

        Returns:
            Model ID string; falls back to the MEDIUM model when the level
            is not found in the registry.
        """
        return self.models.from_level(level)

    @abc.abstractmethod
    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load the provider-specific top-level system prompt file.

        Args:
            root_dir: Workspace root directory.

        Returns:
            System prompt text, or an empty string if no file exists.
        """

    @abc.abstractmethod
    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Load and inline-resolve provider-specific rules files.

        Args:
            root_dir: Workspace root directory.

        Returns:
            Concatenated rules text with all ``@include`` directives resolved,
            or an empty string if no rules directory exists.
        """

    def construct_system_prompt(
        self,
        persona: str,
        rules: str,
        system_instructions: str = "",
    ) -> str:
        """Build a combined system prompt from instructions, persona, and rules.

        Sections are labelled with Markdown headings and joined with blank
        lines. Empty sections are omitted.

        Args:
            persona: Instructions / behavioural instructions.
            rules: Pre-resolved rules text.
            system_instructions: Optional global system instructions to
                prepend before the persona section.

        Returns:
            Combined system prompt string, or an empty string when all inputs
            are blank.
        """
        parts = []
        if system_instructions.strip():
            parts.append(f"# SYSTEM INSTRUCTIONS\n{system_instructions}")
        if persona.strip():
            parts.append(f"# INSTRUCTIONS\n{persona}")
        if rules.strip():
            parts.append(f"# SYSTEM RULES & CONTEXT\n{rules}")
        return "\n\n".join(parts)

    def _validate_include_dirs(
        self,
        include_dirs: str,
        root_dir: pathlib.Path,
    ) -> list[str]:
        """Validate a comma-separated list of include directories for path traversal.

        Each directory is resolved relative to ``root_dir`` and kept only if the
        resolved path stays within ``root_dir``.

        Args:
            include_dirs: Comma-separated directory paths (relative to root).
            root_dir: Workspace root used as the security boundary.

        Returns:
            List of validated directory strings that are safe to pass to the model.
        """
        validated: list[str] = []
        for d in (x.strip() for x in include_dirs.split(",") if x.strip()):
            try:
                resolved = (root_dir / d).resolve()
                if resolved.is_relative_to(root_dir.resolve()):
                    validated.append(d)
                else:
                    logger.warning(
                        "include_dirs path '%s' rejected: outside workspace root",
                        d,
                    )
            except (ValueError, OSError) as exc:
                logger.warning("include_dirs path '%s' rejected: %s", d, exc)
        return validated
