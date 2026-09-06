"""Local project configuration manager for `.vaultspec/config.toml`."""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

from .editor import EditorTrust, validate_editor_command
from .exceptions import EditorResolutionError, VaultSpecError
from .helpers import atomic_write, ensure_dir

KNOWN_KEYS = {"editor"}

#: Configuration keys whose value is a command this package executes. Their
#: values are validated on write *and* on read: the config file is committed
#: with the workspace, so a value in it is reachable by the act of cloning a
#: repository, and a file written by an older version or edited by hand would
#: otherwise bypass a write-time check entirely.
_EXECUTED_KEYS = {"editor"}


def _accept_editor_candidate(command: str, source: str, trust: EditorTrust) -> bool:
    """Decide whether one rung of the editor ladder yields a usable command.

    The two ways a rung can fail are deliberately asymmetrical.

    A command whose program is simply *absent from* ``PATH`` describes a
    configuration that no longer applies - a machine without that editor
    installed - so the ladder falls through to the next rung, which is the
    long-standing behaviour every caller relies on.

    A command that is *refused* is a different matter: it named something
    reachable that this package will not execute. Falling through would run
    some other editor and say nothing, hiding the refusal from the only person
    who can act on it, so a refusal propagates.

    Structural validation runs before the ``PATH`` lookup, because a command
    carrying shell metacharacters or control characters is malformed whether
    or not its program happens to be installed.

    Args:
        command: The candidate editor command from this rung.
        source: Human-readable description of the rung, for error messages.
        trust: The trust tier of the rung.

    Returns:
        ``True`` when *command* should be used, ``False`` when the ladder
        should fall through to the next rung.

    Raises:
        EditorValidationError: When *command* is malformed, or when it
            resolves but names a program an untrusted channel may not name.
    """
    tokens = validate_editor_command(command, source=source, trust="trusted")
    if shutil.which(tokens[0]) is None:
        return False
    if trust == "untrusted":
        validate_editor_command(command, source=source, trust=trust)
    return True


def get_local_config_path(target_dir: Path | None = None) -> Path:
    """Get the path to `.vaultspec/config.toml`."""
    if target_dir is None:
        try:
            from .types import get_context

            target_dir = get_context().target_dir
        except Exception:
            target_dir = Path.cwd()
    return target_dir / ".vaultspec" / "config.toml"


def read_local_config(target_dir: Path | None = None) -> dict[str, Any]:
    """Read the local configuration file."""
    path = get_local_config_path(target_dir)
    if not path.is_file():
        return {}
    try:
        content = path.read_text(encoding="utf-8")
        return tomllib.loads(content)
    except Exception as e:
        raise VaultSpecError(f"Failed to parse config file at '{path}': {e}") from e


def write_local_config(data: dict[str, Any], target_dir: Path | None = None) -> None:
    """Write the local configuration file atomically.

    Args:
        data: The full configuration mapping to persist.
        target_dir: Workspace root whose ``.vaultspec/config.toml`` to write.

    Raises:
        VaultSpecError: When *data* carries an unknown key, or when the write
            itself fails.
        EditorValidationError: When a key this package later executes carries
            a value it would refuse to run. Refusing at write time keeps an
            unusable value out of a file that gets committed and shared; the
            read path validates independently, so this is convenience rather
            than the security boundary.
    """
    path = get_local_config_path(target_dir)
    ensure_dir(path.parent)

    # Check that all keys in data are known
    for k in data:
        if k not in KNOWN_KEYS:
            keys_str = ", ".join(sorted(KNOWN_KEYS))
            raise VaultSpecError(
                f"Unknown configuration key '{k}'. Valid keys: {keys_str}"
            )

    for k in _EXECUTED_KEYS & set(data):
        value = data[k]
        if value:
            validate_editor_command(
                str(value),
                source=f"the project-local config key {k!r}",
                trust="untrusted",
            )

    # Serialize to simple TOML format
    lines: list[str] = []
    for k, v in sorted(data.items()):
        if isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {str(v).lower()}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')

    content = "\n".join(lines)
    if content:
        content += "\n"

    try:
        atomic_write(path, content)
    except Exception as e:
        raise VaultSpecError(f"Failed to write config file at '{path}': {e}") from e


def get_config_value(key: str, target_dir: Path | None = None) -> Any:
    """Get a configuration value, returning None if not set."""
    if key not in KNOWN_KEYS:
        keys_str = ", ".join(sorted(KNOWN_KEYS))
        raise VaultSpecError(
            f"Unknown configuration key '{key}'. Valid keys: {keys_str}"
        )
    data = read_local_config(target_dir)
    return data.get(key)


def set_config_value(key: str, value: Any, target_dir: Path | None = None) -> None:
    """Set a configuration value."""
    if key not in KNOWN_KEYS:
        keys_str = ", ".join(sorted(KNOWN_KEYS))
        raise VaultSpecError(
            f"Unknown configuration key '{key}'. Valid keys: {keys_str}"
        )
    data = read_local_config(target_dir)
    data[key] = value
    write_local_config(data, target_dir)


def unset_config_value(key: str, target_dir: Path | None = None) -> None:
    """Unset a configuration value. If not present, this is a no-op."""
    if key not in KNOWN_KEYS:
        keys_str = ", ".join(sorted(KNOWN_KEYS))
        raise VaultSpecError(
            f"Unknown configuration key '{key}'. Valid keys: {keys_str}"
        )
    data = read_local_config(target_dir)
    if key in data:
        del data[key]
        write_local_config(data, target_dir)


def resolve_editor(
    editor_override: str | None = None, target_dir: Path | None = None
) -> str:
    """Resolve the editor command to use based on the precedence rules.

    Order:
      1. editor_override (e.g. from --editor flag)
      2. local config `editor` value
      3. VAULTSPEC_EDITOR env var
      4. VISUAL env var
      5. EDITOR env var
      6. "vi" fallback

    Every rung is validated by :mod:`vaultspec_core.core.editor` before it is
    returned. The first two rungs - the flag and the committed config file -
    are treated as untrusted channels and must additionally name a known
    editor program; the environment rungs are structurally validated only, and
    are therefore the way to use an editor the allowlist does not know.

    Args:
        editor_override: The per-invocation ``--editor`` value, if any.
        target_dir: Workspace root whose ``.vaultspec/config.toml`` to consult.

    Returns:
        The resolved editor command string, which may carry arguments.

    Raises:
        EditorValidationError: When a rung names something this package will
            not execute. Not silently skipped: a refusal is reported rather
            than quietly demoted to the next rung.
        EditorResolutionError: When no rung yields a working editor.
    """
    sources_tried: list[str] = []

    if editor_override:
        sources_tried.append(f"--editor flag ({editor_override!r})")
        if _accept_editor_candidate(editor_override, "the --editor flag", "untrusted"):
            return editor_override

    local_editor = get_config_value("editor", target_dir)
    if local_editor:
        sources_tried.append(f"local config 'editor' ({local_editor!r})")
        if _accept_editor_candidate(
            str(local_editor),
            "the project-local config key 'editor'",
            "untrusted",
        ):
            return str(local_editor)

    vaultspec_editor = os.environ.get("VAULTSPEC_EDITOR")
    if vaultspec_editor:
        sources_tried.append(f"$VAULTSPEC_EDITOR env var ({vaultspec_editor!r})")
        if _accept_editor_candidate(
            vaultspec_editor, "the $VAULTSPEC_EDITOR environment variable", "trusted"
        ):
            return vaultspec_editor

    visual_env = os.environ.get("VISUAL")
    if visual_env:
        sources_tried.append(f"$VISUAL env var ({visual_env!r})")
        if _accept_editor_candidate(
            visual_env, "the $VISUAL environment variable", "trusted"
        ):
            return visual_env

    editor_env = os.environ.get("EDITOR")
    if editor_env:
        sources_tried.append(f"$EDITOR env var ({editor_env!r})")
        if _accept_editor_candidate(
            editor_env, "the $EDITOR environment variable", "trusted"
        ):
            return editor_env

    sources_tried.append("fallback 'vi'")
    if shutil.which("vi"):
        return "vi"

    raise EditorResolutionError(
        "Could not resolve a working text editor from any of the configured sources.\n"
        "Sources tried:\n" + "\n".join(f"  - {src}" for src in sources_tried),
        hint=(
            "Configure a valid editor using the `--editor` flag, project-local config "
            "(`vaultspec-core config set editor <value>`), or the VISUAL/EDITOR "
            "environment variables."
        ),
    )
