"""Subagent dispatch: spawn ACP agent processes and collect their output."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pathlib

from ..vaultcore import parse_frontmatter
from .utils import safe_read_text

__all__ = [
    "AgentNotFoundError",
    "get_provider_for_model",
    "list_available_agents",
    "load_agent",
    "run_subagent",
]

from ..protocol.providers import AgentProvider, ClaudeProvider, GeminiProvider
from ..protocol.types import (
    SubagentResult,
)

logger = logging.getLogger(__name__)

# Timeout (seconds) for the ACP handshake sequence (initialize + session setup).
_ACP_HANDSHAKE_TIMEOUT: float = 30.0

_CLAUDE_PATTERNS = ("claude-",)


def list_available_agents(content_root: pathlib.Path) -> None:
    """Print all agent names found under ``content_root/rules/agents/``.

    Args:
        content_root: Root directory of the vaultspec framework content tree.
    """
    agents_dir = content_root / "rules" / "agents"
    if not agents_dir.exists():
        logger.warning("No agents directory found at %s", agents_dir)
        return

    print(f"Agents in {agents_dir}:")
    for agent_file in sorted(agents_dir.glob("*.md")):
        print(f"  {agent_file.stem}")


_GEMINI_PATTERNS = ("gemini-",)


class AgentNotFoundError(Exception):
    """Raised when an agent definition file cannot be located on disk."""

    pass


def load_agent(
    agent_name: str,
    root_dir: pathlib.Path,
    provider_name: str | None = None,
    *,
    content_root: pathlib.Path | None = None,
) -> tuple[dict[str, str], str]:
    """Load an agent definition, searching provider-specific then canonical directories.

    Resolution order:
    1. ``{agents_base}/{provider_name}/{agent_name}.md`` (provider-specific)
    2. ``{agents_base}/{agent_name}.md`` (canonical fallback)

    Args:
        agent_name: Name of the agent to load (without ``.md`` extension).
        root_dir: Workspace root; used to resolve the framework directory when
            ``content_root`` is not supplied.
        provider_name: Optional provider subdirectory to search first (e.g.
            ``"claude"`` or ``"gemini"``).
        content_root: Explicit content root (e.g. ``.vaultspec/``).  In
            split-root mode agents live under the content tree, not
            ``root_dir``.  When ``None``, falls back to
            ``root_dir / framework_dir``.

    Returns:
        A ``(metadata_dict, persona_text)`` tuple parsed from the agent's
        Markdown frontmatter.

    Raises:
        AgentNotFoundError: If the agent file is not found in any search
            location.
    """
    from ..config import get_config

    if content_root is not None:
        agents_base = content_root / "rules" / "agents"
    else:
        fw_dir = get_config().framework_dir
        agents_base = root_dir / fw_dir / "rules" / "agents"

    searched = []
    # 1. Provider-specific: agents/<provider>/<name>.md
    if provider_name:
        p_path = agents_base / provider_name / f"{agent_name}.md"
        searched.append(p_path)
        if p_path.exists():
            return parse_frontmatter(p_path.read_text(encoding="utf-8"))

    # 2. Canonical: agents/<name>.md
    c_path = agents_base / f"{agent_name}.md"
    searched.append(c_path)
    if c_path.exists():
        return parse_frontmatter(c_path.read_text(encoding="utf-8"))

    raise AgentNotFoundError(f"Agent '{agent_name}' not found. Searched: {searched}")


def get_provider_for_model(model_name: str | None) -> AgentProvider:
    """Select the appropriate provider for the requested model name.

    Matches ``claude-*`` patterns to :class:`ClaudeProvider` and
    ``gemini-*`` patterns to :class:`GeminiProvider`.  Falls back to
    :class:`GeminiProvider` when the model name is ``None`` or unrecognised.

    Args:
        model_name: Model identifier string (e.g. ``"claude-opus-4-6"``).

    Returns:
        An instantiated :class:`AgentProvider` appropriate for the model.
    """
    if not model_name:
        return GeminiProvider()

    if any(p in model_name for p in _CLAUDE_PATTERNS):
        return ClaudeProvider()

    if any(p in model_name for p in _GEMINI_PATTERNS):
        return GeminiProvider()

    # Fallback: default to Gemini
    logger.warning("Unrecognised model '%s', defaulting to GeminiProvider", model_name)
    return GeminiProvider()


def _build_task_prompt(
    goal: str,
    context_files: list[pathlib.Path],
    plan_file: pathlib.Path | None,
    root_dir: pathlib.Path,
) -> str:
    """Construct a structured task prompt from a goal, optional plan, and context files.

    Sections are ordered: plan (if any), context files (if any), then the task
    goal.  Each section is separated by a blank line.

    Args:
        goal: The primary task description for the agent.
        context_files: Additional files whose contents are inlined into the
            prompt under ``# CONTEXT FILES``.
        plan_file: Optional plan document to include under ``# CURRENT PLAN``.
        root_dir: Workspace root passed to :func:`safe_read_text` for safe
            file reading.

    Returns:
        A multi-section Markdown string suitable for use as the agent prompt.
    """
    parts = []

    if plan_file:
        parts.append(f"# CURRENT PLAN\n{safe_read_text(plan_file, root_dir)}")

    if context_files:
        parts.append("# CONTEXT FILES")
        for cf in context_files:
            content = safe_read_text(cf, root_dir)
            parts.append(f"## File: {cf}\n{content}")

    parts.append(f"# TASK\n{goal}")

    return "\n\n".join(parts)


async def run_subagent(
    agent_name: str,
    root_dir: pathlib.Path,
    initial_task: str = "",
    context_files: list[pathlib.Path] | None = None,
    plan_file: pathlib.Path | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
    interactive: bool = False,
    debug: bool = False,
    quiet: bool = False,
    mode: str = "read-write",
    client_ref: list | None = None,
    resume_session_id: str | None = None,
    client_class: type[Any] = Any,  # Kept for signature compatibility but ignored
    provider_instance: AgentProvider | None = None,
    max_turns: int | None = None,
    budget: float | None = None,
    effort: str | None = None,
    output_format: str | None = None,
    content_root: pathlib.Path | None = None,
    mcp_servers: dict[str, Any] | None = None,
) -> SubagentResult:
    """Orchestrate the full agent lifecycle natively over the A2A protocol."""

    _ = client_ref
    _ = resume_session_id
    _ = client_class
    _ = effort
    _ = output_format

    if max_turns is not None and max_turns <= 0:
        raise ValueError(f"max_turns must be positive, got {max_turns}")
    if budget is not None and budget < 0:
        raise ValueError(f"budget must be non-negative, got {budget}")

    if context_files is None:
        context_files = []

    logger.info(
        "run_subagent (A2A): agent=%s model=%s provider=%s mode=%s task_len=%d",
        agent_name,
        model_override or "(from-spec)",
        provider_override or "(auto)",
        mode,
        len(initial_task),
    )

    # 1. Load agent metadata
    agent_meta, agent_persona = load_agent(
        agent_name,
        root_dir,
        provider_name=provider_override,
        content_root=content_root,
    )

    # 2. Assign provider
    provider_inst = provider_instance
    if not provider_inst:
        model = model_override or agent_meta.get("model")
        if not provider_override:
            provider_inst = get_provider_for_model(model)
        elif provider_override.lower() == "claude":
            provider_inst = ClaudeProvider()
        elif provider_override.lower() == "gemini":
            provider_inst = GeminiProvider()
        else:
            raise ValueError(f"Unknown provider '{provider_override}'")

    # 3. Build Prompt
    full_prompt = _build_task_prompt(initial_task, context_files, plan_file, root_dir)

    # 4. Construct A2A Server Process Spec
    # Note: prepare_process now returns a spec for 'a2a-serve'
    spec = provider_inst.prepare_process(
        agent_name,
        agent_meta,
        agent_persona,
        full_prompt,
        root_dir,
        model_override=model_override,
        mode=mode,
        mcp_servers=mcp_servers,
    )

    # 5. Spawn and Connect
    from ..protocol.a2a.server_manager import ServerProcessManager

    manager = ServerProcessManager(root_dir=root_dir)
    server = await manager.spawn(spec, cwd=str(root_dir), debug=debug)

    try:
        await manager.wait_ready(server)

        # Connect to A2A server
        from a2a.client.client_factory import ClientFactory
        from a2a.types import Message, Part, TextPart

        a2a_client = await ClientFactory.connect(f"http://127.0.0.1:{server.port}")

        req = Message(
            message_id="init-1",
            role="user",
            parts=[Part(root=TextPart(text=full_prompt))],
        )

        if not quiet:
            print(f"\\n[{agent_name} is thinking...]")

        full_response = []

        # 6. Stream events
        from a2a.types import TaskArtifactUpdateEvent

        async for event in a2a_client.send_message(req):
            if isinstance(event, tuple):
                _task, update = event
                if isinstance(update, TaskArtifactUpdateEvent):
                    for part in update.artifact.parts:
                        if isinstance(part.root, TextPart):
                            if not quiet and not update.append:
                                print(part.root.text, end="", flush=True)
                            if update.last_chunk:
                                full_response.append(part.root.text)
                                if not quiet:
                                    print()
            elif isinstance(event, Message):
                # Final message
                pass

        if interactive:
            print("\\n[Interactive session not supported natively in a2a-serve yet]")

    finally:
        await manager.shutdown(server)

    return SubagentResult(
        session_id=server.session_id,
        response_text="".join(full_response),
        written_files=[],  # TODO: Extract from A2A artifacts or task file mapping
    )
