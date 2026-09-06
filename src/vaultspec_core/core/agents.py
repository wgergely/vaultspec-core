"""Manage canonical agent definitions and sync them to tool destinations.

This module owns the source-side lifecycle for managed agent documents under
the framework tree. It collects agent markdown, scaffolds new definitions, and
delegates cross-tool propagation to the shared sync engine.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Protocol, cast

from . import types as _t
from .enums import (
    CapabilityLevel,
    ClaudeModels,
    CodexModels,
    GeminiBuiltinTool,
    Tool,
)
from .exceptions import ResourceExistsError
from .helpers import (
    atomic_write,
    build_file,
    collect_md_resources,
    ensure_dir,
    launch_editor,
)
from .sync import sync_files
from .types import SyncResult

logger = logging.getLogger(__name__)

__all__ = ["codex_managed_agent_names", "sanitize_legacy_codex_agents"]


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# Static mapping from the Claude tool vocabulary used in
# .vaultspec/agents/*.md to Gemini CLI's first-party tool identifiers.
# Source agents are authored against Claude names; the Gemini renderer maps
# at sync time so the source files stay single-authored.
# Mapping from the Claude tool vocabulary used in
# `.vaultspec/agents/*.md` to canonical Gemini built-in tool
# identifiers (`GeminiBuiltinTool` enum members), whose values are frozen
# against gemini-cli v0.47.0 - see that enum's docstring.
_CLAUDE_TO_GEMINI_TOOLS: dict[str, GeminiBuiltinTool] = {
    "Read": GeminiBuiltinTool.READ_FILE,
    "Write": GeminiBuiltinTool.WRITE_FILE,
    "Edit": GeminiBuiltinTool.REPLACE,
    "Glob": GeminiBuiltinTool.GLOB,
    "Grep": GeminiBuiltinTool.GREP_SEARCH,
    "Bash": GeminiBuiltinTool.RUN_SHELL_COMMAND,
    "WebFetch": GeminiBuiltinTool.WEB_FETCH,
    "WebSearch": GeminiBuiltinTool.GOOGLE_WEB_SEARCH,
}

# Host-orchestration tools a persona needs to report back to - and coordinate
# with - the orchestrator that dispatched it, especially when it runs as a
# background teammate rather than in the foreground. They address the host's
# team channel and shared task list, not the project, so a `read-only` persona
# carrying them still mutates nothing.
#
# Gemini CLI exposes no counterpart, so they are dropped from the Gemini render
# deliberately and silently: the unknown-tool warning exists to catch typos in
# authored sources, and warning about a tool that is Claude-only by design would
# fire on every sync of every shipped persona.
_CLAUDE_ONLY_HOST_TOOLS: frozenset[str] = frozenset(
    {"SendMessage", "TaskCreate", "TaskList", "TaskUpdate"}
)


def _stem(name: str) -> str:
    return Path(name).stem


def _coerce_tools(meta: dict[str, Any]) -> list[str]:
    raw = meta.get("tools")
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    return [item for item in items if isinstance(item, str) and item]


def _render_passthrough_agent(
    _name: str,
    meta: dict[str, Any],
    body: str,
    *,
    warnings: list[str] | None = None,  # noqa: ARG001
) -> str:
    """Default agent rendering: emit source frontmatter unchanged.

    Used for any provider not explicitly registered in
    :data:`_AGENT_RENDERERS`. Preserves the historical behaviour of
    :func:`transform_agent`.
    """
    return build_file(meta, body)


def _resolve_tier_model(
    meta: dict[str, Any], registry: type[ClaudeModels | CodexModels]
) -> str | None:
    """Resolve a persona ``tier`` to a provider model identifier.

    Maps the authoring ``tier`` (``LOW``/``STANDARD``/``HIGH``) to a
    :class:`~vaultspec_core.core.enums.CapabilityLevel` and looks the model up
    in *registry*. Returns ``None`` when no ``tier`` is authored, so personas
    that omit the field emit no ``model`` rather than a defaulted one.

    Args:
        meta: Frontmatter dict from the agent source file.
        registry: The provider model registry to resolve against.

    Returns:
        The provider model identifier string, or ``None`` when ``tier`` is
        absent or blank.
    """
    tier = meta.get("tier")
    if not isinstance(tier, str) or not tier.strip():
        return None
    level = CapabilityLevel.from_tier(tier)
    return registry.from_level(level).value


def _render_claude_agent(
    name: str,
    meta: dict[str, Any],
    body: str,
    *,
    warnings: list[str] | None = None,  # noqa: ARG001
) -> str:
    """Render an agent definition for Claude.

    Stamps ``name`` from the filename stem, preserves ``description`` and
    ``tools`` (verbatim, in the Claude vocabulary), and resolves ``model``:
    an explicit ``model`` in the source wins, otherwise the authoring
    ``tier`` is mapped to the current Claude model via
    :class:`~vaultspec_core.core.enums.ClaudeModels`. Drops vaultspec
    authoring keys (``tier``, ``mode``) so the file Claude reads is clean
    rather than merely tolerated.
    """
    fm: dict[str, Any] = {"name": _stem(name)}
    description = meta.get("description")
    if isinstance(description, str) and description.strip():
        fm["description"] = description.strip()

    tools = _coerce_tools(meta)
    if tools:
        fm["tools"] = tools

    model = meta.get("model")
    if isinstance(model, str) and model.strip():
        fm["model"] = model.strip()
    else:
        resolved = _resolve_tier_model(meta, ClaudeModels)
        if resolved is not None:
            fm["model"] = resolved

    return build_file(fm, body)


def _render_gemini_agent(
    name: str,
    meta: dict[str, Any],
    body: str,
    *,
    warnings: list[str] | None = None,
) -> str:
    """Render an agent definition for Gemini CLI.

    Builds a frontmatter dict that satisfies Gemini's strict schema:
    requires ``name``, drops vaultspec authoring keys, and maps every
    entry of ``tools`` from Claude vocabulary to Gemini vocabulary via
    :data:`_CLAUDE_TO_GEMINI_TOOLS`. Unmapped source tools are dropped
    and a warning is appended to *warnings* (if provided) so a single
    typo in one source file does not break the whole sync. The
    host-orchestration tools in :data:`_CLAUDE_ONLY_HOST_TOOLS` have no
    Gemini counterpart by design and are dropped without a warning.
    """
    fm: dict[str, Any] = {"name": _stem(name)}
    description = meta.get("description")
    if isinstance(description, str) and description.strip():
        fm["description"] = description.strip()

    mapped: list[str] = []
    for tool_name in _coerce_tools(meta):
        if tool_name in _CLAUDE_ONLY_HOST_TOOLS:
            continue
        gemini_name = _CLAUDE_TO_GEMINI_TOOLS.get(tool_name)
        if gemini_name is None:
            msg = (
                f"Agent {_stem(name)!r}: unknown source tool {tool_name!r} "
                f"has no Gemini equivalent; dropping."
            )
            logger.warning(msg)
            if warnings is not None:
                warnings.append(msg)
            continue
        mapped.append(gemini_name.value)
    if mapped:
        fm["tools"] = mapped

    return build_file(fm, body)


def _render_antigravity_agent(
    name: str,
    meta: dict[str, Any],
    body: str,
    *,
    warnings: list[str] | None = None,  # noqa: ARG001
) -> str:
    """Render an agent definition for Antigravity.

    Antigravity discovers workspace subagents at ``.agents/agents/<name>.md``
    and requires exactly two frontmatter keys: ``name`` and ``description``.
    Everything else it accepts (``tools``, ``model``, ``mainAgent``,
    ``subagent``, ``commandExecutionPolicy``, ``mcpServers``, ``skills``) is
    optional and carries a documented default, so this renderer emits the
    required pair and nothing more. vaultspec authoring keys (``tier``,
    ``mode``) are dropped, as they are for every other first-class provider.

    Three deliberate omissions, each load-bearing:

    ``tools``
        Antigravity's tool vocabulary is *not* Gemini CLI's: it names
        ``view_file``, ``replace_file_content``, ``grep_search`` and
        ``run_command`` where Gemini names ``read_file``, ``replace``,
        ``grep_search`` and ``run_shell_command``, so
        :data:`_CLAUDE_TO_GEMINI_TOOLS` cannot be reused. Google publishes no
        complete enumeration of the accepted values - only a four-item
        ``e.g.`` list - and documents a standing defect whereby an unmapped or
        misspelled entry can hang the subagent process at execution time. An
        agent that declares no tool restriction loads; one that declares a
        guessed name may not run at all, so the field is omitted until the
        vocabulary can be pinned to a primary source the way
        :class:`~vaultspec_core.core.enums.GeminiBuiltinTool` is.

    ``subagent``
        Defaults to ``true``, which is exactly what these personas are for.
        Emitting the default would add a key that can only drift.

    ``commandExecutionPolicy``
        Defaults to ``sandbox``. The alternatives (``off``, ``auto``,
        ``eager``) all trade away the operator's shell-execution safety
        posture, and that is not a choice a sync tool should make on their
        behalf.

    Antigravity also accepts a multi-file form - a ``<name>/agent.md``
    directory - for agents that ship sidecar assets. Sources under
    ``.vaultspec/agents/`` are single self-contained markdown files with no
    sidecars, so the single-file form is rendered; the directory form remains
    available if a source ever needs one.
    """
    fm: dict[str, Any] = {"name": _stem(name)}
    description = meta.get("description")
    if isinstance(description, str) and description.strip():
        fm["description"] = description.strip()

    return build_file(fm, body)


class _AgentRenderer(Protocol):
    def __call__(
        self,
        name: str,
        meta: dict[str, Any],
        body: str,
        *,
        warnings: list[str] | None = None,
    ) -> str: ...


_AGENT_RENDERERS: dict[Tool, _AgentRenderer] = {
    Tool.CLAUDE: _render_claude_agent,
    Tool.GEMINI: _render_gemini_agent,
    Tool.ANTIGRAVITY: _render_antigravity_agent,
}


def collect_agents(
    warnings: list[str] | None = None,
) -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect agent definitions from .vaultspec/agents/.

    Args:
        warnings: Optional list to append parse-error messages to, so callers
            can propagate them into :class:`~vaultspec_core.core.types.SyncResult`.

    Returns:
        A mapping of filename to a three-tuple of
        ``(source_path, frontmatter_dict, body_text)``.
    """
    return collect_md_resources(_t.get_context().agents_src_dir, warnings=warnings)


def transform_agent(
    tool: Tool | str,
    name: str,
    meta: dict[str, Any],
    body: str,
    *,
    warnings: list[str] | None = None,
) -> str:
    """Transform an agent definition for a specific tool destination.

    Dispatches to the per-provider renderer registered in
    :data:`_AGENT_RENDERERS`. Providers without a registered renderer
    fall through to :func:`_render_passthrough_agent`, preserving the
    historical behaviour. The Codex path is dispatched separately by
    :func:`agents_sync` and never reaches this function.

    Args:
        tool: Target :class:`~vaultspec_core.core.enums.Tool`.
        name: Source filename. The stem is used to stamp ``name`` into
            the rendered frontmatter.
        meta: Frontmatter dict from the agent source file.
        body: Markdown body of the agent source file.
        warnings: Optional accumulator for non-fatal advisories raised
            by the renderer (currently used by the Gemini renderer to
            report unmapped tool names).

    Returns:
        Rendered file content with YAML frontmatter prepended.
    """
    tool = Tool(tool)
    renderer = _AGENT_RENDERERS.get(tool, _render_passthrough_agent)
    return renderer(name, meta, body, warnings=warnings)


def _toml_multiline(value: str) -> str:
    """Render *value* as a TOML multiline string.

    Prefers a literal (single-quote) multiline string so the body is preserved
    verbatim with no escape processing. A literal string cannot contain a
    ``'''`` run - it would terminate the string and there is no escape inside a
    literal - so a body carrying ``'''`` falls back to a basic (double-quote)
    multiline string with the minimal escaping required to stay valid TOML:
    backslashes are doubled and every ``"`` is escaped so no ``\"\"\"`` run can
    form. Both forms round-trip through a TOML parser to the original text.
    """
    if "'''" not in value:
        return f"'''\n{value}\n'''"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"""\n{escaped}\n"""'


def _coerce_codex_model(meta: dict[str, Any]) -> str | None:
    """Resolve the Codex model identifier for an agent.

    Resolution precedence: an explicit ``codex_model`` wins; otherwise a
    generic ``model`` is reused only when it is already an OpenAI identifier
    (``gpt-*`` or one carrying ``codex``); otherwise the authoring ``tier`` is
    mapped to the current Codex model via
    :class:`~vaultspec_core.core.enums.CodexModels`. Returns ``None`` when none
    of these apply, so the rendered agent table omits the ``model`` key.
    """
    explicit = meta.get("codex_model")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    generic = meta.get("model")
    if isinstance(generic, str):
        model = generic.strip()
        if model.startswith("gpt-") or "codex" in model:
            return model

    return _resolve_tier_model(meta, CodexModels)


def _coerce_codex_string(meta: dict[str, Any], key: str) -> str | None:
    value = meta.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def _render_codex_agent(name: str, meta: dict[str, Any], body: str) -> str:
    agent_name = Path(name).stem
    lines = [f"[agents.{_toml_quote(agent_name)}]"]

    description = meta.get("description")
    if isinstance(description, str) and description.strip():
        lines.append(f"description = {_toml_quote(description.strip())}")

    model = _coerce_codex_model(meta)
    if model:
        lines.append(f"model = {_toml_quote(model)}")

    approval_policy = _coerce_codex_string(meta, "codex_approval_policy")
    if approval_policy:
        lines.append(f"approval_policy = {_toml_quote(approval_policy)}")

    sandbox_mode = _coerce_codex_string(meta, "codex_sandbox_mode")
    if sandbox_mode:
        lines.append(f"sandbox_mode = {_toml_quote(sandbox_mode)}")

    tools = _coerce_string_list(meta.get("codex_tools"))
    if tools:
        rendered_tools = ", ".join(_toml_quote(tool) for tool in tools)
        lines.append(f"tools = [{rendered_tools}]")

    nickname_candidates = _coerce_string_list(meta.get("codex_nickname_candidates"))
    if nickname_candidates:
        rendered_nicknames = ", ".join(
            _toml_quote(candidate) for candidate in nickname_candidates
        )
        lines.append(f"nickname_candidates = [{rendered_nicknames}]")

    lines.append(f"prompt = {_toml_multiline(body.strip())}")
    return "\n".join(lines)


def _build_codex_agents_body(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
) -> str:
    """Render Codex agent definitions as TOML content (body only)."""
    rendered_agents: list[str] = []
    for name, (_path, meta, body) in sorted(sources.items()):
        rendered_agents.append(_render_codex_agent(name, meta, body))
    if not rendered_agents:
        return ""
    return "\n\n".join(rendered_agents)


# Legacy sentinel markers used by pre-tag-system releases to delimit the
# Codex agents region. Workspaces installed before the ``<vaultspec>`` tag
# system landed carry these instead of (or in addition to) the managed block.
_LEGACY_AGENTS_BEGIN = "# BEGIN VAULTSPEC MANAGED CODEX AGENTS"
_LEGACY_AGENTS_END = "# END VAULTSPEC MANAGED CODEX AGENTS"

# A TOML table header (``[table]`` or ``[a.b]``) at the start of a line.
_TOML_TABLE_HEADER_RE = re.compile(r"^\s*\[")
# An ``[agents.<name>]`` table header, with either a quoted or a bare key.
_AGENTS_TABLE_RE = re.compile(
    r'^\s*\[agents\.(?:"(?P<quoted>[^"]+)"|(?P<bare>[^\]]+))\]\s*$'
)
# A TOML key-value assignment regex (matches key = value,
# where key can be quoted or bare)
_TOML_KEY_ASSIGNMENT_RE = re.compile(
    r"^\s*(?:\"(?P<quoted_d>[^\"]+)\"|'(?P<quoted_s>[^']+)'|(?P<bare>[^=\s#]+))\s*="
)


def _is_agent_key_assignment(line: str, names: set[str]) -> bool:
    """Return True if line is a key assignment for a name in *names*."""
    match = _TOML_KEY_ASSIGNMENT_RE.match(line)
    if match is None:
        return False
    quoted_d = match.group("quoted_d")
    if quoted_d is not None:
        return quoted_d in names
    quoted_s = match.group("quoted_s")
    if quoted_s is not None:
        return quoted_s in names
    bare = match.group("bare")
    return bare.strip() in names if bare else False


def _agents_table_name(line: str) -> str | None:
    """Return the agent name from an ``[agents.<name>]`` header, else ``None``."""
    match = _AGENTS_TABLE_RE.match(line)
    if match is None:
        return None
    quoted = match.group("quoted")
    if quoted is not None:
        return quoted
    bare = match.group("bare")
    return bare.strip() if bare else None


def _advance_multiline_state(line: str, state: str | None) -> str | None:
    """Track open TOML multiline-string delimiters across physical lines.

    *state* is the currently-open triple-delimiter (``'''`` or ``\"\"\"``) or
    ``None`` when outside a multiline string. Returns the state after
    consuming *line*. Used so structural ``[table]`` headers embedded inside
    an agent ``prompt`` body are not mistaken for real table headers.
    """
    cursor = 0
    length = len(line)
    while cursor < length:
        if state is None:
            single = line.find("'''", cursor)
            double = line.find('"""', cursor)
            candidates = [pos for pos in (single, double) if pos != -1]
            if not candidates:
                return None
            opener = min(candidates)
            state = line[opener : opener + 3]
            cursor = opener + 3
        else:
            close = line.find(state, cursor)
            if close == -1:
                return state
            cursor = close + 3
            state = None
    return state


def _strip_legacy_sentinel_block(content: str) -> str:
    """Remove a legacy ``# BEGIN/END VAULTSPEC MANAGED CODEX AGENTS`` block.

    The sentinel block is entirely vaultspec-owned, so it is removed wholesale.
    Returns *content* unchanged when no sentinel block is present.
    """
    if _LEGACY_AGENTS_BEGIN not in content:
        return content
    out: list[str] = []
    skipping = False
    for line in content.splitlines():
        stripped = line.strip()
        if not skipping and stripped == _LEGACY_AGENTS_BEGIN:
            skipping = True
            continue
        if skipping:
            if stripped == _LEGACY_AGENTS_END:
                skipping = False
            continue
        out.append(line)
    return "\n".join(out)


def _strip_agent_tables_in_segment(lines: list[str], names: set[str]) -> list[str]:
    """Drop ``[agents.<name>]`` tables whose name is in *names* from *lines*.

    Walks *lines* honouring TOML multiline-string state so a ``[`` inside a
    prompt body is never mistaken for a table boundary. A matched table is
    removed from its header through the line before the next real table header
    (or end of segment), including any intervening blank lines.
    """
    out: list[str] = []
    state: str | None = None
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        if state is None and _agents_table_name(line) in names:
            index += 1
            while index < total:
                inner = lines[index]
                if state is None and _TOML_TABLE_HEADER_RE.match(inner):
                    break
                state = _advance_multiline_state(inner, state)
                index += 1
            continue
        if state is None and _is_agent_key_assignment(line, names):
            index += 1
            while index < total:
                inner = lines[index]
                if state is None and (
                    _TOML_TABLE_HEADER_RE.match(inner)
                    or _TOML_KEY_ASSIGNMENT_RE.match(inner)
                ):
                    break
                state = _advance_multiline_state(inner, state)
                index += 1
            continue
        state = _advance_multiline_state(line, state)
        out.append(line)
        index += 1
    return out


def codex_managed_agent_names(content: str) -> set[str]:
    """Return agent names declared inside the managed ``agents`` block."""
    from .tags import TagError, find_blocks

    try:
        blocks = find_blocks(content)
    except TagError:
        return set()
    managed = next((b for b in blocks if b.block_type == "agents"), None)
    if managed is None:
        return set()
    lines = content.splitlines()
    names: set[str] = set()
    for line in lines[managed.content_start - 1 : managed.content_end]:
        name = _agents_table_name(line)
        if name is not None:
            names.add(name)
    return names


def sanitize_legacy_codex_agents(content: str, names: set[str]) -> str:
    """Strip stale duplicate agent tables that collide with the managed block.

    Removes the legacy sentinel block wholesale, then removes any
    ``[agents.<name>]`` table for a name in *names* that lives outside the
    managed ``<vaultspec type="agents">`` block. The managed block itself is
    preserved verbatim so the subsequent upsert owns the canonical copy.
    Returns *content* unchanged when there is nothing stale to remove.
    """
    if not content:
        return content

    sanitized = _strip_legacy_sentinel_block(content)
    if names:
        from .tags import TagError, find_blocks

        try:
            blocks = find_blocks(sanitized)
        except TagError:
            blocks = []
        managed = next((b for b in blocks if b.block_type == "agents"), None)
        lines = sanitized.splitlines()
        if managed is None:
            kept = _strip_agent_tables_in_segment(lines, names)
        else:
            pre = lines[: managed.start_line - 1]
            mid = lines[managed.start_line - 1 : managed.end_line]
            post = lines[managed.end_line :]
            kept = (
                _strip_agent_tables_in_segment(pre, names)
                + mid
                + _strip_agent_tables_in_segment(post, names)
            )
        sanitized = "\n".join(kept)

    if sanitized and not sanitized.endswith("\n"):
        sanitized += "\n"
    return sanitized


def _sync_codex_agents(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
    prune: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    from .tags import TagError, has_block, strip_block, upsert_block

    result = SyncResult()
    codex_cfg = _t.get_context().tool_configs.get(Tool.CODEX)
    if codex_cfg is None or codex_cfg.native_config_file is None:
        return result

    path = codex_cfg.native_config_file
    existed = path.exists()
    raw_existing = path.read_text(encoding="utf-8") if existed else ""
    body = _build_codex_agents_body(sources)
    managed_names = {Path(name).stem for name in sources}
    existing = sanitize_legacy_codex_agents(raw_existing, managed_names)

    abs_path = str(path).replace("\\", "/")

    # Issue 149: Prune obsolete agents directory if prune is True
    if prune:
        agents_dir = path.parent / "agents"
        if agents_dir.is_dir():
            for child in sorted(agents_dir.iterdir()):
                if child.is_file():
                    child_abs = str(child).replace("\\", "/")
                    result.items.append((child_abs, "[DELETE]"))
                    if not dry_run:
                        child.unlink()
                    result.pruned += 1
            if not dry_run:
                import contextlib

                with contextlib.suppress(OSError):
                    agents_dir.rmdir()

    if not body:
        if prune and existed:
            new_content = existing
            if has_block(existing, "agents"):
                try:
                    new_content = strip_block(existing, "agents")
                except TagError as e:
                    logger.warning("Cannot prune agents from %s: %s", path, e)
                    result.errors.append(str(e))
                    return result
            if new_content == raw_existing:
                result.skipped = 1
                return result
            if dry_run:
                result.items.append((abs_path, "[DELETE]"))
            else:
                atomic_write(path, new_content)
            result.pruned = 1
        else:
            result.skipped = 1
        return result

    try:
        new_content = upsert_block(existing, "agents", body, comment_prefix="# ")
    except TagError as e:
        logger.warning("Cannot sync agents to %s: %s", path, e)
        result.errors.append(str(e))
        return result

    # Compare against the raw on-disk content, not the sanitized copy, so a
    # file carrying only stale legacy duplicates (managed block already
    # correct) is still rewritten rather than reported unchanged.
    if raw_existing == new_content:
        result.skipped = len(sources) if sources else 1
        return result

    action = "[UPDATE]" if existed else "[ADD]"
    if dry_run:
        result.items.append((abs_path, action))
    else:
        ensure_dir(path.parent)
        atomic_write(path, new_content)

    if existed:
        result.updated = 1
    else:
        result.added = 1
    return result


def agents_list() -> list[dict[str, str]]:
    """Return a list of agent metadata dicts.

    Each dict contains ``"name"`` and ``"description"``.
    """
    sources = collect_agents()
    items: list[dict[str, str]] = []
    for name, (_path, meta, _body) in sources.items():
        items.append({"name": name, "description": meta.get("description", "")})
    return items


def agents_add(
    name: str,
    description: str = "",
    force: bool = False,
    *,
    body: str | None = None,
    dry_run: bool = False,
    interactive: bool | None = None,
) -> Path:
    """Scaffold a new agent definition.

    Args:
        name: Agent name.
        description: Short description.
        force: Whether to overwrite existing.
        body: Optional direct body content to override scaffold.
        dry_run: If ``True``, return the target path without writing.
        interactive: Override TTY detection.  ``None`` means auto-detect.

    Returns:
        Path to the created (or would-be-created) agent file.

    Raises:
        ResourceExistsError: If the agent exists and *force* is ``False``.
    """
    agents_src_dir = _t.get_context().agents_src_dir
    ensure_dir(agents_src_dir)

    file_name = name if name.endswith(".md") else f"{name}.md"
    file_path = agents_src_dir / file_name

    if file_path.exists() and not force:
        raise ResourceExistsError(
            f"Agent '{file_name}' exists.",
            hint="Use --force to overwrite, or --dry-run to preview",
        )

    if dry_run:
        return file_path

    body_content = body
    is_interactive = interactive if interactive is not None else sys.stdin.isatty()

    if body_content is None:
        if is_interactive and not description:
            body_content = "# Instructions\n\nAdd agent instructions here.\n"
            fm = {"name": name, "description": description}
            content = build_file(fm, body_content)
            atomic_write(file_path, content)
            from ..config import get_config

            editor = get_config().editor
            logger.info("Opening editor (%s) for %s...", editor, file_path)
            try:
                launch_editor(editor, str(file_path))
                logger.info("Agent saved to %s", file_path)
            except Exception as e:
                logger.error("Error opening editor: %s", e)
            return file_path
        else:
            if not sys.stdin.isatty():
                body_content = sys.stdin.read()
            if not body_content:
                body_content = "# Instructions\n\nAdd agent instructions here.\n"

    fm = {"name": name, "description": description}
    content = build_file(fm, body_content)
    atomic_write(file_path, content)
    logger.info("Created agent: %s", file_path)
    return file_path


def agents_sync(dry_run: bool = False, prune: bool = False) -> SyncResult:
    """Sync all agent definitions to every configured tool destination.

    Args:
        dry_run: If ``True``, log planned actions without writing files.
        prune: If ``True``, remove destination agents not present in sources.

    Returns:
        Accumulated :class:`~vaultspec_core.core.types.SyncResult` across
        all active tool destinations.
    """
    parse_warnings: list[str] = []
    render_warnings: list[str] = []
    sources = collect_agents(warnings=parse_warnings)
    total = SyncResult()

    from .manifest import installed_tool_configs

    active_configs = installed_tool_configs()
    for tool_type, cfg in active_configs.items():
        if tool_type is Tool.CODEX or cfg.agents_dir is None:
            continue
        result = sync_files(
            sources=sources,
            dest_dir=cfg.agents_dir,
            transform_fn=lambda _tool, n, m, b, _tt=tool_type: transform_agent(
                _tt, n, m, b, warnings=render_warnings
            ),
            dest_path_fn=lambda dest_dir, name: dest_dir / name,
            prune=prune,
            dry_run=dry_run,
            label=f"Agents -> {tool_type.value}",
        )
        total.merge(result)
        total.per_tool[tool_type.value] = result

    if Tool.CODEX in active_configs:
        codex_result = _sync_codex_agents(sources, prune=prune, dry_run=dry_run)
        total.merge(codex_result)
        total.per_tool[Tool.CODEX.value] = codex_result
    total.warnings.extend(parse_warnings)
    total.warnings.extend(render_warnings)
    return total
