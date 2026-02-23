"""Helper utilities for vaultspec resource management."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _yaml_load(text: str) -> dict[str, Any]:
    """Parse a YAML string and return a dict, defaulting to empty dict on empty input.

    Args:
        text: A YAML-formatted string to parse.

    Returns:
        Parsed key-value mapping, or an empty dict if *text* is empty or null.
    """
    return yaml.safe_load(text) or {}


class _LiteralStr(str):
    """Marker type for strings that should use YAML literal block scalar."""


def _literal_representer(dumper: yaml.Dumper, data: _LiteralStr) -> yaml.ScalarNode:
    """Represent a _LiteralStr value using YAML literal block scalar style (``|``).

    Args:
        dumper: The PyYAML Dumper instance performing serialization.
        data: The string value to represent with literal block style.

    Returns:
        A YAML ScalarNode configured with ``|`` block scalar style.
    """
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(_LiteralStr, _literal_representer)


def _yaml_dump(data: dict[str, Any]) -> str:
    """Serialize a dict to YAML, using literal block style for multi-line values.

    Args:
        data: Key-value mapping to serialize.

    Returns:
        YAML string representation with multi-line string values rendered as
        literal block scalars (``|``).
    """
    prepared = {}
    for k, v in data.items():
        if isinstance(v, str) and "\n" in v:
            prepared[k] = _LiteralStr(v)
        else:
            prepared[k] = v
    return yaml.dump(
        prepared, default_flow_style=False, allow_unicode=True, sort_keys=False
    ).rstrip("\n")


def build_file(frontmatter: dict[str, Any], body: str) -> str:
    """Assemble a Markdown file with YAML frontmatter.

    Args:
        frontmatter: Key-value pairs to serialize as the YAML front matter block.
        body: Markdown body text to place after the closing ``---`` delimiter.

    Returns:
        A string of the form ``---\\n<yaml>\\n---\\n\\n<body>``.
    """
    fm_str = _yaml_dump(frontmatter)
    return f"---\n{fm_str}\n---\n\n{body}"


def ensure_dir(path: Path) -> None:
    """Create *path* and all intermediate parents if they do not already exist.

    Args:
        path: Directory path to create.
    """
    path.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically via tmp + rename.

    Args:
        path: Destination file path to write.
        content: Text content to write, encoded as UTF-8.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.error("atomic_write failed for %s: %s", path, exc)
        raise


def resolve_model(tool: str, tier: str) -> str | None:
    """Resolve a capability tier name to a concrete model identifier string.

    Args:
        tool: Provider name (e.g. ``"claude"`` or ``"gemini"``).
        tier: Capability level name (e.g. ``"LOW"``, ``"MEDIUM"``, ``"HIGH"``).

    Returns:
        The best model identifier for the given provider and capability level,
        or ``None`` if the provider is unknown or the tier cannot be resolved.
    """
    from .types import PROVIDERS

    if not PROVIDERS or tool not in PROVIDERS:
        return None
    try:
        from ..protocol.providers import CapabilityLevel

        level = CapabilityLevel[tier.upper()]
    except (ImportError, KeyError, AttributeError) as exc:
        logger.warning(
            "Could not resolve model for tool=%r tier=%r: %s", tool, tier, exc
        )
        return None
    return PROVIDERS[tool].get_best_model_for_capability(level)


def _launch_editor(editor: str, file_path: str) -> None:
    """Launch editor, handling Windows .cmd/.bat wrappers.

    Args:
        editor: Editor command string (may include flags, e.g. ``"code --wait"``).
        file_path: Absolute path to the file to open in the editor.
    """
    parts = editor.split()
    resolved = shutil.which(parts[0]) or parts[0]
    if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
        subprocess.call(["cmd.exe", "/c", resolved, *parts[1:], file_path])
    else:
        subprocess.call([resolved, *parts[1:], file_path])
