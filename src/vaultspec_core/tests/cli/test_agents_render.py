"""Per-provider agent render tests for #76.

Covers the renderer factory in :mod:`vaultspec_core.core.agents`:
``transform_agent`` dispatch, ``_render_claude_agent``,
``_render_gemini_agent``, the Claude->Gemini tool mapping, and a
parametrized regression guard over every source agent under
``.vaultspec/agents/``.

Every check here is offline and deterministic: it reads the shipped source
agents, renders them, and asserts against the vocabulary this package
declares. Nothing in this module reaches a network or a provider binary.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, cast

import pytest

from vaultspec_core.builtins import builtins_root
from vaultspec_core.core.agents import (
    _CLAUDE_ONLY_HOST_TOOLS,
    _CLAUDE_TO_GEMINI_TOOLS,
    _render_claude_agent,
    _render_codex_agent,
    _render_gemini_agent,
    _render_passthrough_agent,
    _toml_multiline,
    transform_agent,
)
from vaultspec_core.core.enums import GeminiBuiltinTool, Tool
from vaultspec_core.vaultcore import parse_frontmatter

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


# The shipped source agents are a sibling of the renderer under test and live
# inside the distributed package, so they are addressed through the package's
# own accessor rather than by walking out to a repository root.
_AGENTS_SRC = builtins_root() / "agents"
_GEMINI_TOOL_SET = frozenset(t.value for t in GeminiBuiltinTool)


def _fm(rendered: str) -> dict[str, object]:
    meta, _body = parse_frontmatter(rendered)
    return meta


class TestRenderClaudeAgent:
    def test_injects_name_from_filename_stem(self):
        out = _render_claude_agent("vaultspec-researcher.md", {}, "body")
        assert _fm(out)["name"] == "vaultspec-researcher"

    def test_preserves_description(self):
        out = _render_claude_agent("x.md", {"description": "Hello world"}, "body")
        assert _fm(out)["description"] == "Hello world"

    def test_preserves_tools_verbatim(self):
        meta = {"tools": ["Glob", "Grep", "Read", "Bash"]}
        out = _render_claude_agent("x.md", meta, "body")
        assert _fm(out)["tools"] == ["Glob", "Grep", "Read", "Bash"]

    def test_drops_authoring_keys(self):
        meta = {"tier": "HIGH", "mode": "read-write"}
        rendered_meta = _fm(_render_claude_agent("x.md", meta, "body"))
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta

    def test_explicit_model_wins_over_tier(self):
        # An explicit model overrides the tier-derived default.
        meta = {"model": "claude-opus-5", "tier": "LOW"}
        out = _render_claude_agent("x.md", meta, "body")
        assert _fm(out)["model"] == "claude-opus-5"

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            ("HIGH", "claude-opus-5"),
            ("STANDARD", "claude-sonnet-5"),
            ("LOW", "claude-haiku-4-5"),
        ],
    )
    def test_tier_resolves_to_current_model(self, tier: str, expected: str):
        out = _render_claude_agent("x.md", {"tier": tier}, "body")
        assert _fm(out)["model"] == expected

    def test_omits_model_when_no_tier_or_model(self):
        rendered_meta = _fm(_render_claude_agent("x.md", {}, "body"))
        assert rendered_meta == {"name": "x"}
        assert "model" not in rendered_meta

    def test_body_is_preserved(self):
        out = _render_claude_agent("x.md", {}, "# Heading\n\ncontent")
        assert "# Heading\n\ncontent" in out


class TestRenderGeminiAgent:
    def test_injects_name(self):
        out = _render_gemini_agent("vaultspec-writer.md", {}, "body")
        assert _fm(out)["name"] == "vaultspec-writer"

    def test_preserves_description(self):
        out = _render_gemini_agent("x.md", {"description": "An agent"}, "body")
        assert _fm(out)["description"] == "An agent"

    def test_maps_every_known_tool(self):
        meta = {"tools": list(_CLAUDE_TO_GEMINI_TOOLS.keys())}
        out = _render_gemini_agent("x.md", meta, "body")
        assert _fm(out)["tools"] == list(_CLAUDE_TO_GEMINI_TOOLS.values())

    def test_drops_authoring_keys(self):
        meta = {"tier": "MEDIUM", "mode": "read-only", "tools": ["Read"]}
        rendered_meta = _fm(_render_gemini_agent("x.md", meta, "body"))
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta

    def test_drops_unknown_tool_and_warns(self):
        warnings: list[str] = []
        meta = {"tools": ["Read", "BogusTool", "Bash"]}
        out = _render_gemini_agent("vaultspec-x.md", meta, "body", warnings=warnings)
        assert _fm(out)["tools"] == ["read_file", "run_shell_command"]
        assert any("BogusTool" in w for w in warnings)
        assert any("vaultspec-x" in w for w in warnings)

    def test_unknown_tool_without_warnings_accumulator(self):
        meta = {"tools": ["BogusTool"]}
        rendered_meta = _fm(_render_gemini_agent("x.md", meta, "body"))
        assert "tools" not in rendered_meta

    def test_empty_tools_list(self):
        rendered_meta = _fm(_render_gemini_agent("x.md", {"tools": []}, "body"))
        assert "tools" not in rendered_meta

    def test_no_tools_key(self):
        rendered_meta = _fm(_render_gemini_agent("x.md", {}, "body"))
        assert "tools" not in rendered_meta

    def test_non_string_tool_entries_ignored(self):
        meta = {"tools": ["Read", 42, None, "Grep"]}
        out = _render_gemini_agent("x.md", meta, "body")
        assert _fm(out)["tools"] == ["read_file", "grep_search"]


class TestCodexMultilinePrompt:
    """Codex agent prompts must round-trip through a TOML parser (#143).

    ``_render_codex_agent`` frames the body with a leading and trailing
    newline, and TOML strips the first newline after the opening delimiter, so
    the parsed prompt carries a single trailing newline; the body content
    itself must survive verbatim.
    """

    @staticmethod
    def _roundtrip(body: str) -> str:
        rendered = _render_codex_agent("worker.md", {"description": "d"}, body)
        return tomllib.loads(rendered)["agents"]["worker"]["prompt"]

    def test_plain_body_uses_literal_string(self):
        out = _toml_multiline("hello\nworld")
        assert out.startswith("'''")
        assert self._roundtrip("hello\nworld") == "hello\nworld\n"

    def test_body_with_triple_single_quotes_is_valid_toml(self):
        body = "before '''quoted''' after"
        out = _toml_multiline(body)
        # A literal string cannot hold ''', so the basic form is used instead.
        assert out.startswith('"""')
        assert self._roundtrip(body) == body + "\n"

    def test_body_with_backslashes_and_quotes_round_trips(self):
        body = "path C:\\x '''y''' \"z\""
        assert self._roundtrip(body) == body + "\n"


class TestCodexModelResolution:
    """Codex agent ``model`` resolution: explicit -> generic gpt -> tier."""

    @staticmethod
    def _model(meta: dict[str, object]) -> object:
        rendered = _render_codex_agent(
            "worker.md", {**meta, "description": "d"}, "body"
        )
        return tomllib.loads(rendered)["agents"]["worker"].get("model")

    def test_explicit_codex_model_wins_over_tier(self):
        assert (
            self._model({"codex_model": "gpt-5.6-sol", "tier": "LOW"}) == "gpt-5.6-sol"
        )

    def test_generic_openai_model_is_reused(self):
        assert self._model({"model": "gpt-5.6-luna"}) == "gpt-5.6-luna"

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            ("HIGH", "gpt-5.6-sol"),
            ("STANDARD", "gpt-5.6-terra"),
            ("LOW", "gpt-5.6-luna"),
        ],
    )
    def test_tier_resolves_to_current_model(self, tier: str, expected: str):
        assert self._model({"tier": tier}) == expected

    def test_non_openai_generic_model_without_tier_yields_no_model(self):
        # A Claude identifier in the generic field is not an OpenAI model and
        # there is no tier to fall back on, so no model key is emitted.
        assert self._model({"model": "claude-opus-5"}) is None

    def test_no_model_without_tier_or_model(self):
        assert self._model({}) is None


class TestTransformAgentDispatch:
    def test_claude_routes_to_claude_renderer(self):
        meta = {"tier": "HIGH", "tools": ["Glob"]}
        rendered_meta = _fm(transform_agent(Tool.CLAUDE, "a.md", meta, "body"))
        assert rendered_meta["name"] == "a"
        assert rendered_meta["tools"] == ["Glob"]
        assert "tier" not in rendered_meta

    def test_gemini_routes_to_gemini_renderer(self):
        meta = {"tier": "HIGH", "tools": ["Glob"]}
        rendered_meta = _fm(transform_agent(Tool.GEMINI, "a.md", meta, "body"))
        assert rendered_meta["name"] == "a"
        assert rendered_meta["tools"] == ["glob"]
        assert "tier" not in rendered_meta

    def test_unregistered_tool_falls_through_to_passthrough(self):
        meta = {"tier": "X", "tools": ["whatever"]}
        rendered_meta = _fm(transform_agent(Tool.ANTIGRAVITY, "a.md", meta, "body"))
        # Passthrough preserves source frontmatter, including authoring keys.
        assert rendered_meta["tier"] == "X"
        assert rendered_meta["tools"] == ["whatever"]

    def test_string_tool_name_is_coerced(self):
        rendered_meta = _fm(
            transform_agent("gemini", "a.md", {"tools": ["Read"]}, "body")
        )
        assert rendered_meta["tools"] == ["read_file"]

    def test_warnings_threaded_through(self):
        warnings: list[str] = []
        transform_agent(
            Tool.GEMINI,
            "a.md",
            {"tools": ["Bogus"]},
            "body",
            warnings=warnings,
        )
        assert warnings  # gemini renderer wrote into the accumulator

    def test_passthrough_renderer_ignores_warnings_kwarg(self):
        # Regression: every renderer in the registry must accept the
        # keyword-only `warnings` arg even when it does not use it.
        warnings: list[str] = []
        out = _render_passthrough_agent(
            "a.md", {"tools": ["Read"]}, "body", warnings=warnings
        )
        assert "Read" in out
        assert warnings == []


def _source_agent_files() -> list[Path]:
    if not _AGENTS_SRC.exists():
        return []
    return sorted(_AGENTS_SRC.glob("*.md"))


# Fail loudly at collection time rather than silently producing zero
# parametrized tests if the source-agent directory is ever moved or empty.
_SOURCE_AGENTS = _source_agent_files()
assert _SOURCE_AGENTS, (
    f"No source agents found under {_AGENTS_SRC}; the parametrized "
    "regression guard would silently produce zero tests."
)


@pytest.mark.parametrize("agent_path", _SOURCE_AGENTS, ids=lambda p: p.name)
class TestSourceAgentCoverage:
    """Regression guard: every shipped source agent renders cleanly."""

    def test_gemini_render_satisfies_schema(self, agent_path: Path):
        meta, body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
        warnings: list[str] = []
        rendered = transform_agent(
            Tool.GEMINI, agent_path.name, meta, body, warnings=warnings
        )
        rendered_meta = _fm(rendered)

        assert rendered_meta.get("name") == agent_path.stem
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta

        rendered_tools = rendered_meta.get("tools", [])
        assert isinstance(rendered_tools, list)
        rendered_tools = cast("list[str]", rendered_tools)
        for tool_name in rendered_tools:
            assert tool_name in _GEMINI_TOOL_SET, (
                f"{agent_path.name}: rendered tool {tool_name!r} is not "
                f"in the Gemini tool vocabulary"
            )

        # No source agent should currently produce a warning. If this
        # ever fails, the source file uses a Claude tool name that
        # has no Gemini mapping; either map it or remove it from the
        # source.
        assert warnings == [], f"{agent_path.name}: {warnings}"

    def test_claude_render_strips_authoring_keys(self, agent_path: Path):
        meta, body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
        rendered = transform_agent(Tool.CLAUDE, agent_path.name, meta, body)
        rendered_meta = _fm(rendered)
        assert rendered_meta.get("name") == agent_path.stem
        assert "tier" not in rendered_meta
        assert "mode" not in rendered_meta

    def test_declares_team_relay_tool(self, agent_path: Path):
        # A persona dispatched as a background teammate has no final message
        # the orchestrator reads; without SendMessage its findings are lost
        # and the failure is silent (#290).
        meta, _body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
        tools = meta.get("tools", [])
        assert isinstance(tools, list)
        assert "SendMessage" in cast("list[str]", tools), (
            f"{agent_path.name}: no team relay tool; findings would be "
            f"discarded when the persona runs in background dispatch"
        )

    def test_claude_render_preserves_host_tools(self, agent_path: Path):
        meta, body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
        rendered_tools = _fm(
            transform_agent(Tool.CLAUDE, agent_path.name, meta, body)
        ).get("tools", [])
        assert isinstance(rendered_tools, list)
        assert "SendMessage" in cast("list[str]", rendered_tools)


# Personas expected to participate in an orchestrator's shared task list:
# the executors that work the Steps, and the coordinator that tracks them.
_SHARED_TASK_LIST_PERSONAS = {
    "vaultspec-high-executor": {"TaskList", "TaskUpdate"},
    "vaultspec-standard-executor": {"TaskList", "TaskUpdate"},
    "vaultspec-low-executor": {"TaskList", "TaskUpdate"},
    "vaultspec-project-coordinator": {"TaskCreate", "TaskList", "TaskUpdate"},
}


class TestSourceAgentTeamTools:
    """Shipped personas declare the host tools their dispatch shape needs."""

    @pytest.mark.parametrize(
        ("stem", "expected"),
        sorted(_SHARED_TASK_LIST_PERSONAS.items()),
        ids=sorted(_SHARED_TASK_LIST_PERSONAS),
    )
    def test_task_list_participants_declare_task_tools(
        self, stem: str, expected: set[str]
    ):
        agent_path = _AGENTS_SRC / f"{stem}.md"
        assert agent_path.is_file(), f"missing shipped persona {agent_path}"
        meta, _body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
        tools = set(cast("list[str]", meta.get("tools", [])))
        assert expected <= tools, f"{stem}: missing {sorted(expected - tools)}"

    def test_every_declared_host_tool_is_recognized(self):
        # Guards a typo in a source persona from silently rendering a host
        # tool the Gemini renderer would then warn about.
        known = set(_CLAUDE_TO_GEMINI_TOOLS) | set(_CLAUDE_ONLY_HOST_TOOLS)
        for agent_path in _SOURCE_AGENTS:
            meta, _body = parse_frontmatter(agent_path.read_text(encoding="utf-8"))
            tools = set(cast("list[str]", meta.get("tools", [])))
            assert tools <= known, f"{agent_path.name}: unknown {sorted(tools - known)}"


class TestClaudeOnlyHostTools:
    """Host-orchestration tools are Claude-only and drop silently elsewhere."""

    def test_gemini_drops_host_tools_without_warning(self):
        warnings: list[str] = []
        meta = {"tools": ["Read", *sorted(_CLAUDE_ONLY_HOST_TOOLS), "Bash"]}
        out = _render_gemini_agent("x.md", meta, "body", warnings=warnings)
        assert _fm(out)["tools"] == ["read_file", "run_shell_command"]
        assert warnings == []

    def test_unknown_tool_still_warns_alongside_host_tools(self):
        warnings: list[str] = []
        meta = {"tools": ["SendMessage", "BogusTool"]}
        _render_gemini_agent("x.md", meta, "body", warnings=warnings)
        assert any("BogusTool" in w for w in warnings)
        assert not any("SendMessage" in w for w in warnings)

    def test_claude_keeps_host_tools_verbatim(self):
        meta = {"tools": ["Read", "SendMessage", "TaskUpdate"]}
        out = _render_claude_agent("x.md", meta, "body")
        assert _fm(out)["tools"] == ["Read", "SendMessage", "TaskUpdate"]
