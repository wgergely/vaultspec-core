"""Per-provider agent render tests for #76.

Covers the renderer factory in :mod:`vaultspec_core.core.agents`:
``transform_agent`` dispatch, ``_render_claude_agent``,
``_render_gemini_agent``, the Claude->Gemini tool mapping, and a
parametrized regression guard over every source agent under
``.vaultspec/rules/agents/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultspec_core.core.agents import (
    _CLAUDE_TO_GEMINI_TOOLS,
    _render_claude_agent,
    _render_gemini_agent,
    _render_passthrough_agent,
    transform_agent,
)
from vaultspec_core.core.enums import Tool
from vaultspec_core.vaultcore import parse_frontmatter

pytestmark = [pytest.mark.unit]


_REPO_ROOT = Path(__file__).resolve().parents[4]
_AGENTS_SRC = _REPO_ROOT / ".vaultspec" / "rules" / "agents"
_GEMINI_TOOL_SET = frozenset(_CLAUDE_TO_GEMINI_TOOLS.values())


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

    def test_preserves_model_when_set(self):
        out = _render_claude_agent("x.md", {"model": "claude-opus-4-6"}, "body")
        assert _fm(out)["model"] == "claude-opus-4-6"

    def test_omits_optional_keys_when_absent(self):
        rendered_meta = _fm(_render_claude_agent("x.md", {}, "body"))
        assert rendered_meta == {"name": "x"}

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
        assert _fm(out)["tools"] == ["read_file", "shell"]
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
        assert _fm(out)["tools"] == ["read_file", "grep"]


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
